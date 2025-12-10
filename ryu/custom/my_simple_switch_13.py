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
from ryu.lib import hub
from collections import defaultdict

from ryu.custom.protocol import message_pb2, message
from ryu.custom.utils import network

class MySimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(MySimpleSwitch13, self).__init__(*args, **kwargs)
        import os, queue
        self.cluster_id = int(os.getenv("CLUSTER_ID", "1"))
        # 回退：使用手动 BOUNDARY_SWITCHES
        self.boundary_switches = [x for x in os.getenv("BOUNDARY_SWITCHES", "").split(",") if x]
        self.dst_clusters = [int(x) for x in os.getenv("DST_CLUSTERS", "").split(",") if x]
        self.ac_host = os.getenv("AC_HOST", "127.0.0.1")
        self.ac_port = int(os.getenv("AC_PORT", "10000"))

        self.logger.info(f"[CC] raw user_flags='cluster_id={self.cluster_id},dst_clusters={','.join(map(str,self.dst_clusters))},ac_host={self.ac_host},ac_port={self.ac_port},boundary_switches={','.join(self.boundary_switches)}'")
        self.logger.info(f"[CC] FLAGS OK cluster={self.cluster_id} boundaries={self.boundary_switches} dst_clusters={self.dst_clusters} ac={self.ac_host}:{self.ac_port}")
        self.logger.info(f"[CC] boundary_count={len(self.boundary_switches)} repr={self.boundary_switches}")

        self._local_dpids = set()
        self._dpid_name = {}   # dpid -> human name
        self._link_seen = set()

        self._send_q = queue.Queue()
        hub.spawn(self._ac_pump_loop)

        self._datapaths = {}              # dpid -> datapath
        self._ports = defaultdict(list)   # dpid -> [port_no,...]
        self._lldp_tx_threads = {}        # dpid -> greenthread

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
        if dp.id not in self._dpid_name:
            idx = len(self._dpid_name)
            name = self.boundary_switches[idx] if idx < len(self.boundary_switches) else f"dpid:{dp.id:016x}"
            self._dpid_name[dp.id] = name
            self.logger.info(f"[CC] map dpid={dp.id} -> name={name}")

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

        # 调试打印
        pkt_lldp = pkt.get_protocol(lldp.lldp)
        self.logger.info(f"[DEBUG] PACKETIN dpid={dp.id} in_port={msg.match.get('in_port')} pkt_len={len(msg.data)}")
        if pkt_lldp:
            for tlv in pkt_lldp.tlvs:
                try:
                    self.logger.info(f"[DEBUG] TLV type={type(tlv).__name__} repr={tlv}")
                except Exception:
                    pass

        if not eth or eth.ethertype != ether_types.ETH_TYPE_LLDP:
            return
        pkt_lldp = pkt.get_protocol(lldp.lldp)
        if not pkt_lldp:
            return

        # 解析对端 dpid/port
        peer_dpid, peer_port = None, None
        local_port = msg.match.get("in_port")
        try:
            for tlv in pkt_lldp.tlvs:
                if isinstance(tlv, lldp.ChassisID):
                    # chassis_id 通常是 'dpid:xxxxxxxx...' 字符串
                    s = tlv.chassis_id.decode(errors="ignore") if isinstance(tlv.chassis_id, (bytes, bytearray)) else str(tlv.chassis_id)
                    if s.startswith("dpid:"):
                        try:
                            peer_dpid = int(s.split("dpid:")[1], 16)
                        except Exception:
                            self.logger.info(f"[CC] bad chassis_id '{s}'")
                if isinstance(tlv, lldp.PortID):
                    # 统一处理：若为字节，直接按大端整数；否则尝试字符串转 int
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

        local_name = self._dpid_name.get(dp.id, f"dpid:{dp.id:016x}")
        # 如果用户没有显式给 boundary_switches（为空），就自动把本端交换机当作边界并上报
        # 如果用户给了 boundary_switches，则只有在该本端名字属于白名单时才上报
        if self.boundary_switches:
            if local_name not in self.boundary_switches:
            # 记录 debug 并不立即 return（可按需改为 return），这里建议记录并继续处理以便排查
                self.logger.debug(f"[CC] local_name={local_name} not in configured boundaries {self.boundary_switches} -> ignore LLDP")
                return
        else:
            # 把第一次看到的本端交换机名打印并加入边界，以便后续稳定
            if local_name not in self.boundary_switches:
                self.boundary_switches.append(local_name)
                self.logger.info(f"[CC] auto-added boundary {local_name}")

        # 忽略同域
        if peer_dpid in self._local_dpids:
            self.logger.info(f"[CC] LLDP peer in same cluster, ignore: peer_dpid={peer_dpid}")
            return

        lk = self._make_link_key(dp.id, local_port, peer_dpid, peer_port)
        if lk in self._link_seen:
            self.logger.info(f"[CC] duplicate link_key, skip: {lk}")
            return
        self._link_seen.add(lk)

        # 上报前加一条明确日志（便于确认执行到了）
        self.logger.info(f"[CC] WILL REPORT: local={local_name}:{local_port} peer_dpid={peer_dpid}:{peer_port} lk={lk}")

        # 双端上报：本端 + 对端 stub（方便 AC 聚合）
        upd = message_pb2.InterClusterLinkUpdate()
        upd.cluster_id = self.cluster_id

        le_local = upd.links.add()
        le_local.switch_id = local_name
        le_local.port_no = int(local_port)
        le_local.link_key = lk

        le_peer = upd.links.add()
        le_peer.switch_id = f"dpid:{peer_dpid:016x}"
        le_peer.port_no = int(peer_port)
        le_peer.link_key = lk

        data = message.encode_envelope(message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE, upd)
        self.logger.info(f"[CC] LLDP跨域邻居: local={local_name}:{local_port} peer_dpid={peer_dpid}:{peer_port} lk={lk} -> send update bytes={len(data)}")
        self._send_bytes(data)

    def _make_link_key(self, a_dpid, a_port, b_dpid, b_port):
        ends = sorted([(int(a_dpid), int(a_port)), (int(b_dpid), int(b_port))])
        return f"lk-{ends[0][0]}:{ends[0][1]}-{ends[1][0]}:{ends[1][1]}"

    def _ac_pump_loop(self):
        # 建立连接并先发 HELLO
        sock = None; backoff = 1
        try:
            with self._send_q.mutex:
                self._send_q.queue.clear()
        except Exception:
            pass
        while sock is None:
            try:
                sock = network.create_client_socket(self.ac_host, self.ac_port)
            except Exception:
                hub.sleep(backoff); backoff = min(5, backoff * 2)

        # HELLO 直接发送，保证时序
        hello = message_pb2.Hello()
        hello.node_id = f"CC-{self.cluster_id}"
        hello.version = "1.0"
        network.send_message(sock, message.encode_envelope(message_pb2.Envelope.HELLO, hello))

        # 初始拓扑（手动边界）
        self._send_topology_update()
        hub.spawn(self._ac_reader, sock)

        # 队列发送循环
        while True:
            data = self._send_q.get()
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

    def _send_topology_update(self):
        topo = message_pb2.TopologyUpdate()
        topo.cluster_id = self.cluster_id
        topo.boundary_switches.extend(self.boundary_switches)
        # 新增：上报本域 dpid 集合
        for dpid in sorted(self._local_dpids):
            topo.local_dpids.append(int(dpid))
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
        while dpid in self._datapaths:
            dp = self._datapaths.get(dpid)
            if not dp:
                break
            ports = self._ports.get(dpid, [])
            if not ports:
                # 尚未拿到端口，重试拉取
                try:
                    self._request_port_desc(dp)
                except Exception:
                    pass
                hub.sleep(1.0)
                continue
            # 启动初期做几轮快速 burst，后续按固定周期
            rounds = 3 if burst > 0 else 1
            for _ in range(rounds):
                for pno in ports:
                    try:
                        self._send_lldp(dp, dpid, int(pno))
                    except Exception as e:
                        self.logger.debug(f"[CC] LLDP tx error dpid={dpid} port={pno}: {e}")
                burst = max(0, burst - 1)
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