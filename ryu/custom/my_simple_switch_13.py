import eventlet
eventlet.monkey_patch()  # 必须在任何 Ryu/OSLO 导入之前

from oslo_config import cfg
CONF = cfg.CONF
if not hasattr(CONF, 'observe_links'):
    CONF.register_cli_opt(cfg.BoolOpt('observe_links', default=True))
CONF.observe_links = True

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, lldp, ether_types
from ryu.lib.packet import packet as pktlib  # 修复: 补充 pktlib 用于构造 LLDP 帧
import time  # 新增
from ryu.lib import hub
from collections import defaultdict

from ryu.custom.protocol import message_pb2, message
from ryu.custom.utils import network

class MySimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    def __init__(self, *args, **kwargs):
        super(MySimpleSwitch13, self).__init__(*args, **kwargs)
        import os  # 移除标准 queue
        self.cluster_id = int(os.getenv("CLUSTER_ID", "1"))
        # self.boundary_switches = [x for x in os.getenv("BOUNDARY_SWITCHES", "").split(",") if x]
        self.boundary_switches = []
        self.dst_clusters = [int(x) for x in os.getenv("DST_CLUSTERS", "").split(",") if x]
        self.ac_host = os.getenv("AC_HOST", "127.0.0.1")
        self.ac_port = int(os.getenv("AC_PORT", "10000"))

        self.logger.info(f"[CC] raw user_flags='cluster_id={self.cluster_id},dst_clusters={','.join(map(str,self.dst_clusters))},ac_host={self.ac_host},ac_port={self.ac_port},boundary_switches={','.join(self.boundary_switches)}'")
        self.logger.info(f"[CC] FLAGS OK cluster={self.cluster_id} boundaries={self.boundary_switches} dst_clusters={self.dst_clusters} ac={self.ac_host}:{self.ac_port}")
        self.logger.info(f"[CC] boundary_count={len(self.boundary_switches)} repr={self.boundary_switches}")

        self._local_dpids = set()
        self._dpid_name = {}   # dpid -> human name
        # self._link_seen = set()  # 移除永久去重
        self._link_last_sent = {}  # 新增：link_key -> last_ts
        self._lk_resend_sec = float(os.getenv("LINK_REANNOUNCE_SEC", "10"))  # 重发周期秒

        self._send_q = hub.Queue()      # 使用 eventlet 友好的队列
        hub.spawn(self._ac_pump_loop)

        self._datapaths = {}              # dpid -> datapath
        self._ports = defaultdict(list)   # dpid -> [port_no,...]
        self._lldp_tx_threads = {}        # dpid -> greenthread
        self._pending_links = {}  # lk -> (local_name, local_port, peer_dpid, peer_port)
        
        # Message tracking for synchronization
        self._msg_counter = 0
        self._msg_counter_lock = hub.Semaphore()
        
        # Start background loops
        hub.spawn(self._periodic_advertise_loop)
        hub.spawn(self._heartbeat_loop)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self._datapaths[dp.id] = dp
        elif ev.state == DEAD_DISPATCHER:
            self._datapaths.pop(dp.id, None)
            self._ports.pop(dp.id, None)

    def _request_port_desc(self, dp):
        req = dp.ofproto_parser.OFPPortDescStatsRequest(dp, 0)
        dp.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def _port_desc_reply(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        ports = []
        for p in ev.msg.body:
            # 过滤保留端口（>= OFPP_MAX）
            if int(p.port_no) >= ofp.OFPP_MAX:
                continue
            ports.append(int(p.port_no))
        self._ports[dp.id] = ports
        self.logger.info(f"[CC] ports dpid={dp.id} -> {ports}")

        # NEW: 端口就绪后立即发送一轮 LLDP，避免等待线程导致“卡住”
        for pno in ports:
            try:
                self._send_lldp(dp, dp.id, int(pno))
            except Exception as e:
                self.logger.debug(f"[CC] initial LLDP tx error dpid={dp.id} port={pno}: {e}")

        # NEW: 若线程尚未启动，补充启动
        if dp.id not in self._lldp_tx_threads:
            self._lldp_tx_threads[dp.id] = hub.spawn(self._lldp_tx_loop, dp.id)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto; parser = dp.ofproto_parser

        # 确保 PacketIn 发送完整包
        dp.send_msg(parser.OFPSetConfig(datapath=dp,
                                        flags=0,
                                        miss_send_len=ofp.OFPCML_NO_BUFFER))
        dp.send_msg(parser.OFPGetConfigRequest(dp))

        self._local_dpids.add(dp.id)

        # 映射 dpid -> 预设边界名（按发现顺序），不足时回退 dpid:xxxx
        new_switch = dp.id not in self._dpid_name
        if new_switch:
            idx = len(self._dpid_name)
            name = self.boundary_switches[idx] if idx < len(self.boundary_switches) else f"dpid:{dp.id:016x}"
            self._dpid_name[dp.id] = name
            self.logger.info(f"[CC] map dpid={dp.id} -> name={name}")
            # Send topology update to AC when new switch discovered
            hub.spawn(lambda: (hub.sleep(0.5), self._send_topology_update()))

        # 优先级最高：LLDP punt 给控制器
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, priority=65535,
            match=parser.OFPMatch(eth_type=ether_types.ETH_TYPE_LLDP),
            instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                                       [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                                                               ofp.OFPCML_NO_BUFFER)])]
        ))
        # table-miss
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp, priority=0,
            match=parser.OFPMatch(),
            instructions=[parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                                       [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                                                               ofp.OFPCML_NO_BUFFER)])]
        ))

        # 查询端口并启动本地 LLDP 发送线程
        self._request_port_desc(dp)
        if dp.id not in self._lldp_tx_threads:
            self._lldp_tx_threads[dp.id] = hub.spawn(self._lldp_tx_loop, dp.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if not eth or eth.ethertype != ether_types.ETH_TYPE_LLDP:
            return
        pkt_lldp = pkt.get_protocol(lldp.lldp)
        if not pkt_lldp:
            return

        peer_dpid, peer_port = None, None
        local_port = msg.match.get("in_port")
        try:
            for tlv in pkt_lldp.tlvs:
                if isinstance(tlv, lldp.ChassisID):
                    s = tlv.chassis_id.decode(errors="ignore") if isinstance(tlv.chassis_id, (bytes, bytearray)) else str(tlv.chassis_id)
                    if s.startswith("dpid:"):
                        try:
                            peer_dpid = int(s.split("dpid:")[1], 16)
                        except Exception:
                            self.logger.info(f"[CC] bad chassis_id '{s}'")
                if isinstance(tlv, lldp.PortID):
                    if isinstance(tlv.port_id, (bytes, bytearray)):
                        peer_port = int.from_bytes(tlv.port_id, byteorder='big', signed=False)
                        self.logger.info(f"[DEBUG] parsed peer_port from bytes -> {peer_port} (len={len(tlv.port_id)}, subtype={tlv.subtype})")
                    else:
                        p_str = str(tlv.port_id)
                        if p_str.isdigit():
                            peer_port = int(p_str)
                            self.logger.info(f"[DEBUG] parsed peer_port from str -> {peer_port} (subtype={tlv.subtype})")
                        else:
                            self.logger.info(f"[DEBUG] non-numeric PortID '{p_str}', skip numeric port parse")
        except Exception as e:
            self.logger.warning(f"[CC] LLDP parse error: {e}")
            return

        if peer_dpid is None or peer_port is None:
            self.logger.info("[CC] LLDP missing peer_dpid/peer_port, skip")
            return

        # 忽略本机或同域
        if peer_dpid == dp.id or peer_dpid in self._local_dpids:
            return

        local_name = self._dpid_name.get(dp.id, f"dpid:{dp.id:016x}")
        if local_name not in self.boundary_switches:
            self.boundary_switches.append(local_name)
            self.logger.info(f"[CC] auto-detected boundary switch {local_name}")
            self._send_topology_update()

        lk = self._make_link_key(dp.id, local_port, peer_dpid, peer_port)
        # 记录到缓存，供周期性重发
        self._pending_links[lk] = (local_name, int(local_port), int(peer_dpid), int(peer_port))

        # 首次强制上报；后续按时间窗抑制
        now = time.time()
        first = lk not in self._link_last_sent
        last = self._link_last_sent.get(lk, 0)
        if not first and now - last < self._lk_resend_sec:
            self.logger.debug(f"[CC] suppress resend within {self._lk_resend_sec}s: {lk}")
            return
        self._link_last_sent[lk] = now

        upd = message_pb2.InterClusterLinkUpdate()
        upd.cluster_id = self.cluster_id
        le_local = upd.links.add(); le_local.switch_id = local_name; le_local.port_no = int(local_port); le_local.link_key = lk
        le_peer = upd.links.add();  le_peer.switch_id = f"dpid:{peer_dpid:016x}"; le_peer.port_no = int(peer_port); le_peer.link_key = lk
        
        # Create envelope with message ID for tracking
        envelope = message_pb2.Envelope()
        envelope.type = message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE
        envelope.msg_id = self._next_msg_id()
        envelope.intercluster_link_update.CopyFrom(upd)
        data = envelope.SerializeToString()
        
        self.logger.info(f"[CC] LLDP跨域邻居: local={local_name}:{local_port} peer_dpid={peer_dpid}:{peer_port} lk={lk} msg_id={envelope.msg_id} -> send update bytes={len(data)}")
        self._send_bytes(data)

    def _make_link_key(self, a_dpid, a_port, b_dpid, b_port):
        ends = sorted([(int(a_dpid), int(a_port)), (int(b_dpid), int(b_port))])
        return f"lk-{ends[0][0]}:{ends[0][1]}-{ends[1][0]}:{ends[1][1]}"

    def _ac_pump_loop(self):
        # 建立连接并先发 HELLO
        sock = None; backoff = 1
        try:
            # 清空队列
            while not self._send_q.empty():
                self._send_q.get_nowait()
        except Exception:
            pass
        while sock is None:
            try:
                sock = network.create_client_socket(self.ac_host, self.ac_port)
            except Exception:
                hub.sleep(backoff); backoff = min(5, backoff * 2)

        hello = message_pb2.Hello()
        hello.node_id = f"CC-{self.cluster_id}"
        hello.version = "1.0"
        network.send_message(sock, message.encode_envelope(message_pb2.Envelope.HELLO, hello))

        # 初始拓扑
        self._send_topology_update()
        hub.spawn(self._ac_reader, sock)

        # 非阻塞发送循环：队列空时小睡避免卡死
        while True:
            try:
                data = self._send_q.get_nowait()
            except hub.QueueEmpty:
                hub.sleep(0.2)
                continue
            try:
                network.send_message(sock, data)
            except Exception:
                self.logger.warning("[CC] AC send failed, reconnecting...")
                sock = None; backoff = 1
                while sock is None:
                    try:
                        sock = network.create_client_socket(self.ac_host, self.ac_port)
                    except Exception:
                        hub.sleep(backoff); backoff = min(5, backoff * 2)
                try:
                    network.send_message(sock, message.encode_envelope(message_pb2.Envelope.HELLO, hello))
                except Exception:
                    pass
                hub.spawn(self._ac_reader, sock)

    def _send_bytes(self, data: bytes):
        try:
            self._send_q.put_nowait(data)
        except Exception:
            self.logger.warning("[CC] send queue full, drop")
    
    def _next_msg_id(self):
        """Generate next message ID atomically"""
        with self._msg_counter_lock:
            self._msg_counter += 1
            return self._msg_counter
    
    def _heartbeat_loop(self):
        """Send periodic heartbeats to AC for health monitoring"""
        heartbeat_interval = 10.0  # seconds
        while True:
            try:
                hub.sleep(heartbeat_interval)
                keepalive = message_pb2.Keepalive()
                keepalive.ts_ms = int(time.time() * 1000)
                data = message.encode_envelope(message_pb2.Envelope.KEEPALIVE, keepalive)
                self._send_bytes(data)
                self.logger.debug(f"[CC] Heartbeat sent to AC")
            except Exception as e:
                self.logger.debug(f"[CC] Heartbeat error: {e}")

    def _periodic_advertise_loop(self):
        interval = max(1.0, self._lk_resend_sec / 2.0)
        self.logger.info(f"[CC] Periodic advertise loop started: interval={interval}s, resend_sec={self._lk_resend_sec}s")
        loop_count = 0
        while True:
            try:
                hub.sleep(interval)
                loop_count += 1
                now = time.time()
                pending_count = len(self._pending_links)
                
                # Log more frequently initially
                if loop_count <= 5 or loop_count % 5 == 0:
                    self.logger.info(f"[CC] Periodic loop #{loop_count}: checking {pending_count} pending links")
                
                resent_count = 0
                for lk, (lname, lport, pdpid, pport) in list(self._pending_links.items()):
                    last = self._link_last_sent.get(lk, 0)
                    elapsed = now - last
                    if elapsed >= self._lk_resend_sec:
                        upd = message_pb2.InterClusterLinkUpdate()
                        upd.cluster_id = self.cluster_id
                        le_local = upd.links.add(); le_local.switch_id = lname; le_local.port_no = int(lport); le_local.link_key = lk
                        le_peer  = upd.links.add(); le_peer.switch_id  = f"dpid:{pdpid:016x}"; le_peer.port_no = int(pport); le_peer.link_key = lk
                        
                        # Create envelope with message ID
                        envelope = message_pb2.Envelope()
                        envelope.type = message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE
                        envelope.msg_id = self._next_msg_id()
                        envelope.intercluster_link_update.CopyFrom(upd)
                        data = envelope.SerializeToString()
                        
                        self.logger.info(f"[CC] RE-ADVERTISE lk={lk} {lname}:{lport} <-> dpid:{pdpid:016x}:{pport} msg_id={envelope.msg_id} elapsed={elapsed:.1f}s")
                        self._send_bytes(data)
                        self._link_last_sent[lk] = now
                        resent_count += 1
                    else:
                        self.logger.debug(f"[CC] Skip lk={lk}: elapsed={elapsed:.1f}s < {self._lk_resend_sec}s")
                
                if resent_count > 0:
                    self.logger.info(f"[CC] Periodic loop #{loop_count}: re-sent {resent_count}/{pending_count} links")
            except Exception as e:
                self.logger.warning(f"[CC] Periodic advertise error: {e}", exc_info=True)

    def _send_topology_update(self):
        topo = message_pb2.TopologyUpdate()
        topo.cluster_id = self.cluster_id
        topo.boundary_switches.extend(self.boundary_switches)
        if hasattr(topo, "local_dpids"):
            for dpid in sorted(self._local_dpids):
                topo.local_dpids.append(int(dpid))
        else:
            self.logger.debug("[CC] proto TopologyUpdate.local_dpids not found, skip")
        data = message.encode_envelope(message_pb2.Envelope.TOPOLOGY_UPDATE, topo)
        self._send_bytes(data)

    def _ac_reader(self, sock):
        while True:
            try:
                data = network.receive_message(sock)
                if data is None:
                    self.logger.warning("[CC] AC connection closed")
                    break
                env = message.decode_envelope(data)
                if env.type == message_pb2.Envelope.FLOW_REPLY:
                    fr = env.flow_reply
                    self.logger.info(f"[CC] FLOW_REPLY path={list(fr.path)} segments={len(fr.segments)} match={dict(fr.match_fields)}")
            except Exception as e:
                self.logger.warning(f"[CC] AC reader error: {e}")
                break

    def _lldp_tx_loop(self, dpid: int):
        burst = 3
        interval = 2.0
        loop_count = 0
        name = self._dpid_name.get(dpid, f"dpid:{dpid:016x}")
        self.logger.info(f"[CC] LLDP TX loop started for {name} (dpid={dpid}): interval={interval}s")
        while dpid in self._datapaths:
            dp = self._datapaths.get(dpid)
            if not dp:
                self.logger.warning(f"[CC] LLDP TX loop: datapath {name} disappeared")
                break
            ports = self._ports.get(dpid, [])
            if not ports:
                # 尚未拿到端口，重试拉取
                loop_count += 1
                self.logger.warning(f"[CC] LLDP TX loop #{loop_count} for {name}: no ports yet, waiting...")
                try:
                    self._request_port_desc(dp)
                except Exception:
                    pass
                hub.sleep(1.0)
                continue
            # 启动初期做几轮快速 burst，后续按固定周期
            rounds = 3 if burst > 0 else 1
            loop_count += 1
            sent_count = 0
            for _ in range(rounds):
                for pno in ports:
                    try:
                        self._send_lldp(dp, dpid, int(pno))
                        sent_count += 1
                    except Exception as e:
                        self.logger.warning(f"[CC] LLDP tx error dpid={dpid} port={pno}: {e}")
                burst = max(0, burst - 1)
            
            # Log every iteration for first 5, then every 5th iteration
            if loop_count <= 5 or loop_count % 5 == 0:
                self.logger.info(f"[CC] LLDP TX loop #{loop_count} for {name}: sent {sent_count} packets to {len(ports)} ports")
            
            hub.sleep(interval)

    def _send_lldp(self, dp, dpid: int, port_no: int):
        # 构造 LLDP 帧：dst=01:80:c2:00:00:0e, src 任意本地 MAC
        eth = ethernet.ethernet(dst=lldp.LLDP_MAC_NEAREST_BRIDGE,
                                src='02:00:00:00:00:01',
                                ethertype=ether_types.ETH_TYPE_LLDP)
        tlvs = [
            lldp.ChassisID(subtype=lldp.ChassisID.SUB_LOCALLY_ASSIGNED,
                           chassis_id=f"dpid:{dpid:016x}".encode()),
            lldp.PortID(subtype=lldp.PortID.SUB_LOCALLY_ASSIGNED,
                        port_id=int(port_no).to_bytes(4, 'big')),
            lldp.TTL(ttl=120),
            lldp.End()
        ]
        try:
            p = pktlib.Packet()
            p.add_protocol(eth)
            p.add_protocol(lldp.lldp(tlvs))
            p.serialize()
        except Exception as e:
            self.logger.error(f"[CC] build LLDP packet failed dpid={dpid} port={port_no}: {e}")
            return

        parser = dp.ofproto_parser; ofp = dp.ofproto
        actions = [parser.OFPActionOutput(port_no)]
        out = parser.OFPPacketOut(datapath=dp,
                                  buffer_id=ofp.OFP_NO_BUFFER,
                                  in_port=ofp.OFPP_CONTROLLER,
                                  actions=actions,
                                  data=p.data)
        try:
            dp.send_msg(out)
            self.logger.debug(f"[CC] LLDP sent dpid={dpid} port={port_no}")
        except Exception as e:
            self.logger.error(f"[CC] send LLDP failed dpid={dpid} port={port_no}: {e}")