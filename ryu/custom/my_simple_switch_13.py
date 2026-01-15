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
from ryu.lib.packet import ipv4, arp

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
        
        # Cross-cluster flow routing
        self._mac_to_port = {}  # (dpid, mac) -> port_no
        self._local_hosts = set()  # Set of MAC addresses in this cluster
        self._flow_requests_pending = {}  # (src_cluster, dst_cluster) -> timestamp
        
        # ARP proxy for cross-cluster communication
        # Virtual gateway MAC for each cluster (format: 02:00:00:00:XX:XX where XX is cluster_id)
        self._cluster_gateway_macs = {}  # cluster_id -> virtual_mac
        self._ip_to_mac = {}  # IP -> MAC mapping learned from ARP packets
        self._ip_to_cluster = {}  # IP -> cluster_id mapping
        
        # L3 Routing: Port classification
        self._gre_ports = {}  # dpid -> set of GRE/tunnel port numbers
        self._host_ports = {}  # dpid -> set of host-facing port numbers
        self._switch_mac = {}  # dpid -> MAC address for L3 routing
        
        # Start background loops
        hub.spawn(self._periodic_advertise_loop)
        hub.spawn(self._heartbeat_loop)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        dp = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            self._datapaths[dp.id] = dp
            # Start LLDP TX loop now that datapath is registered
            if dp.id not in self._lldp_tx_threads:
                self._lldp_tx_threads[dp.id] = hub.spawn(self._lldp_tx_loop, dp.id)
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
        gre_ports = set()
        host_ports = set()
        
        for p in ev.msg.body:
            # 过滤保留端口（>= OFPP_MAX）
            if int(p.port_no) >= ofp.OFPP_MAX:
                continue
            ports.append(int(p.port_no))
            
            # Classify ports: GRE tunnels vs host-facing ports
            port_name = p.name.decode() if isinstance(p.name, bytes) else str(p.name)
            if port_name.startswith('gre') or port_name.startswith('vxlan') or port_name.startswith('tun'):
                # GRE/tunnel ports for inter-cluster connectivity
                gre_ports.add(int(p.port_no))
                self.logger.info(f"[CC] Identified GRE/tunnel port: {port_name} (port {p.port_no})")
            elif not port_name.startswith('wlx'):  # Exclude wireless interfaces
                # Host-facing ports (veth, eth, etc.)
                host_ports.add(int(p.port_no))
                self.logger.info(f"[CC] Identified host-facing port: {port_name} (port {p.port_no})")
        
        self._ports[dp.id] = ports
        self._gre_ports[dp.id] = gre_ports
        self._host_ports[dp.id] = host_ports
        
        # Generate a virtual MAC for this switch for L3 routing
        if dp.id not in self._switch_mac:
            # Format: 02:00:00:CC:XX:XX where CC=cluster_id, XX:XX=dpid last 2 bytes
            self._switch_mac[dp.id] = f"02:00:00:{self.cluster_id:02x}:{(dp.id >> 8) & 0xff:02x}:{dp.id & 0xff:02x}"
            self.logger.info(f"[CC] Generated L3 router MAC for dpid={dp.id:016x}: {self._switch_mac[dp.id]}")
        
        self.logger.info(f"[CC] Port classification dpid={dp.id}: total={len(ports)}, GRE={len(gre_ports)}, host={len(host_ports)}")

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

        # 查询端口 (LLDP TX loop will be started when state becomes MAIN_DISPATCHER)
        self._request_port_desc(dp)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if not eth:
            return
        
        # Log all packet-ins for debugging
        in_port = msg.match.get('in_port', 'unknown')
        self.logger.info(f"[CC] Packet-in: dpid={dp.id:016x} port={in_port} src={eth.src} dst={eth.dst} ethertype={hex(eth.ethertype)}")
        
        # Handle LLDP packets for topology discovery
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            self._handle_lldp_packet(msg, dp, pkt, eth)
            return
        
        # Handle regular traffic for cross-cluster routing
        self._handle_data_packet(msg, dp, pkt, eth)
    
    def _handle_lldp_packet(self, msg, dp, pkt, eth):
        """Handle LLDP packets for topology discovery"""
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
    
    def _handle_data_packet(self, msg, dp, pkt, eth):
        """Handle data packets for cross-cluster routing"""
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match['in_port']
        
        # Learn MAC address to avoid FLOOD next time
        src_mac = eth.src
        dst_mac = eth.dst
        dpid = dp.id
        
        # Learn source MAC
        self._mac_to_port.setdefault(dpid, {})
        if src_mac not in self._mac_to_port[dpid]:
            self.logger.info(f"[CC] Learned local MAC: {src_mac} on switch dpid={dpid:016x} port={in_port}")
        self._mac_to_port[dpid][src_mac] = in_port
        self._local_hosts.add(src_mac)
        
        # Extract IP information for cross-cluster detection
        pkt_ipv4 = pkt.get_protocol(ipv4.ipv4)
        pkt_arp = pkt.get_protocol(arp.arp)
        
        src_ip = None
        dst_ip = None
        
        if pkt_ipv4:
            src_ip = pkt_ipv4.src
            dst_ip = pkt_ipv4.dst
        elif pkt_arp:
            src_ip = pkt_arp.src_ip
            dst_ip = pkt_arp.dst_ip
            # Learn IP->MAC mapping from ARP packets
            self._ip_to_mac[src_ip] = pkt_arp.src_mac
            # Learn IP->cluster mapping
            src_cluster_id = self._get_cluster_from_ip(src_ip)
            if src_cluster_id:
                self._ip_to_cluster[src_ip] = src_cluster_id
        
        # Handle ARP packets specially for cross-cluster communication
        if pkt_arp:
            if self._handle_arp_packet(msg, dp, pkt, eth, pkt_arp):
                # ARP handled (proxied or forwarded), don't continue
                return
        
        # Check destination cluster
        dst_cluster = None
        if dst_ip:
            dst_cluster = self._get_cluster_from_ip(dst_ip)
        
        # Check if destination is local
        out_port = self._mac_to_port.get(dpid, {}).get(dst_mac)
        
        # Determine if this is cross-cluster traffic
        if dst_cluster and dst_cluster != self.cluster_id:
            self.logger.info(f"[CC] *** CROSS-CLUSTER TRAFFIC DETECTED ***")
            self.logger.info(f"[CC]     Source: {src_ip} (cluster {self.cluster_id})")
            self.logger.info(f"[CC]     Destination: {dst_ip} (cluster {dst_cluster})")
            self.logger.info(f"[CC]     This is NOT local traffic - need AC routing")
            self._request_cross_cluster_path(src_ip, dst_ip, src_mac, dst_mac)
            # Still forward the packet (flood if no port known)
            if out_port is None:
                out_port = ofproto.OFPP_FLOOD
        elif out_port is None:
            # Unknown destination but same cluster - flood
            self.logger.info(f"[CC] Unknown local destination {dst_mac}, flooding")
            out_port = ofproto.OFPP_FLOOD
        else:
            # Known local destination
            self.logger.info(f"[CC] Forwarding to known local port {out_port}")
        
        # Install a flow to avoid packet_in next time for local traffic
        actions = [parser.OFPActionOutput(out_port)]
        
        # Send packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        dp.send_msg(out)
    
    def _get_cluster_from_ip(self, ip_addr):
        """Extract cluster ID from IP address"""
        try:
            # First check if we've explicitly learned this IP's cluster
            if ip_addr in self._ip_to_cluster:
                return self._ip_to_cluster[ip_addr]
            
            parts = ip_addr.split('.')
            if len(parts) == 4:
                # For the user's topology: 10.10.0.X format
                # h1 (10.10.0.10) is in cluster 1
                # h2 (10.10.0.2) is in cluster 2
                # Simple heuristic: last octet determines cluster
                last_octet = int(parts[3])
                
                # You can customize this mapping for your specific topology:
                if last_octet >= 10:  # e.g., .10, .11, .12... are cluster 1
                    return 1
                elif last_octet >= 1 and last_octet < 10:  # e.g., .2, .3... are cluster 2
                    return 2
                
                # Alternative: explicit IP mapping (uncomment and customize)
                # ip_map = {
                #     "10.10.0.10": 1,  # h1
                #     "10.10.0.2": 2,   # h2
                #     # Add more IPs here
                # }
                # if ip_addr in ip_map:
                #     return ip_map[ip_addr]
        except:
            pass
        return None
    
    def _get_gateway_mac_for_cluster(self, cluster_id):
        """Get or create virtual gateway MAC for a cluster"""
        if cluster_id not in self._cluster_gateway_macs:
            # Create virtual MAC: 02:00:00:00:0C:XX where XX is cluster_id
            self._cluster_gateway_macs[cluster_id] = f"02:00:00:00:0c:{cluster_id:02x}"
        return self._cluster_gateway_macs[cluster_id]
    
    def _handle_arp_packet(self, msg, dp, pkt, eth, pkt_arp):
        """
        Handle ARP packets with BIDIRECTIONAL cross-cluster ARP proxy support.
        Returns True if ARP was handled (proxied), False if normal processing should continue.
        """
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match['in_port']
        
        # Learn from both ARP requests and replies
        src_ip = pkt_arp.src_ip
        src_mac = pkt_arp.src_mac
        
        # Always learn IP->MAC mapping from any ARP packet
        if src_ip and src_mac:
            self._ip_to_mac[src_ip] = src_mac
            src_cluster_id = self._get_cluster_from_ip(src_ip)
            if src_cluster_id:
                self._ip_to_cluster[src_ip] = src_cluster_id
        
        # Learn from ARP replies too
        if pkt_arp.opcode == arp.ARP_REPLY:
            if pkt_arp.dst_ip and pkt_arp.dst_mac:
                self._ip_to_mac[pkt_arp.dst_ip] = pkt_arp.dst_mac
            return False  # Let reply through normally
        
        # Only proxy ARP requests
        if pkt_arp.opcode != arp.ARP_REQUEST:
            return False
        
        dst_ip = pkt_arp.dst_ip
        
        self.logger.info(f"[CC] ARP Request: who has {dst_ip}? Tell {src_ip} ({src_mac})")
        
        # Check if this is a cross-cluster ARP request
        dst_cluster = self._get_cluster_from_ip(dst_ip)
        src_cluster = self._get_cluster_from_ip(src_ip)
        
        self.logger.info(f"[CC] ARP: src_cluster={src_cluster}, dst_cluster={dst_cluster}, my_cluster={self.cluster_id}")
        
        # Proxy ARP if destination is in another cluster
        # This enables BIDIRECTIONAL communication by having each cluster proxy for remote IPs
        if dst_cluster and dst_cluster != self.cluster_id:
            self.logger.info(f"[CC] *** CROSS-CLUSTER ARP DETECTED ***")
            self.logger.info(f"[CC]     ARP Request from cluster {self.cluster_id} for IP {dst_ip} in cluster {dst_cluster}")
            self.logger.info(f"[CC]     Generating ARP proxy reply with virtual gateway MAC")
            
            # Get virtual gateway MAC for the destination cluster
            gateway_mac = self._get_gateway_mac_for_cluster(dst_cluster)
            
            # Send ARP reply with virtual gateway MAC
            self._send_arp_reply(dp, in_port, gateway_mac, dst_ip, src_mac, src_ip)
            
            # Install a flow for future IP packets to use this gateway MAC
            # This directs IP traffic destined to dst_cluster through the gateway
            self._install_cross_cluster_rewrite_flow(dp, dst_ip, dst_cluster, gateway_mac)
            
            # Request BIDIRECTIONAL cross-cluster path from AC for actual routing
            # The AC and flow installation will handle both directions
            self._request_cross_cluster_path(src_ip, dst_ip, src_mac, gateway_mac)
            
            return True  # ARP handled, don't flood
        
        # Local ARP or unknown - let normal flooding handle it
        return False
    
    def _send_arp_reply(self, dp, in_port, src_mac, src_ip, dst_mac, dst_ip):
        """Send an ARP reply packet"""
        ofproto = dp.ofproto
        parser = dp.ofproto_parser
        
        # Build ARP reply
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(
            ethertype=ether_types.ETH_TYPE_ARP,
            dst=dst_mac,
            src=src_mac))
        pkt.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=src_mac,
            src_ip=src_ip,
            dst_mac=dst_mac,
            dst_ip=dst_ip))
        pkt.serialize()
        
        # Send packet out
        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=pkt.data)
        dp.send_msg(out)
        
        self.logger.info(f"[CC] ✓ Sent ARP Reply: {src_ip} is at {src_mac} to {dst_ip} ({dst_mac}) on port {in_port}")
    
    def _install_cross_cluster_rewrite_flow(self, dp, dst_ip, dst_cluster, gateway_mac):
        """
        Install a flow with proper L3 routing behavior for cross-cluster traffic.
        Implements:
        - TTL decrement (L3 router behavior)
        - Source MAC rewrite to local switch MAC
        - Destination MAC rewrite to gateway MAC
        - Forward to GRE boundary port
        """
        parser = dp.ofproto_parser
        ofproto = dp.ofproto
        
        try:
            # Find GRE boundary port to the destination cluster
            out_port = None
            gre_ports = self._gre_ports.get(dp.id, set())
            
            # Prefer ports that are in discovered inter-cluster links
            for lk, (lname, lport, pdpid, pport) in self._pending_links.items():
                if lname == self._dpid_name.get(dp.id) and lport in gre_ports:
                    # This is a GRE boundary port with inter-cluster link
                    out_port = lport
                    self.logger.info(f"[CC] Found GRE boundary port {out_port} for cross-cluster traffic to cluster {dst_cluster}")
                    break
            
            # Fallback: use any GRE port if available
            if out_port is None and gre_ports:
                out_port = list(gre_ports)[0]
                self.logger.info(f"[CC] Using fallback GRE port {out_port} for cross-cluster traffic to cluster {dst_cluster}")
            
            if out_port is None:
                self.logger.warning(f"[CC] No GRE boundary port found for dpid={dp.id:016x}, cannot install cross-cluster flow")
                return
            
            # Get switch MAC for source rewriting
            switch_mac = self._switch_mac.get(dp.id, f"02:00:00:{self.cluster_id:02x}:00:00")
            
            # Match on destination IP and gateway MAC (from ARP proxy)
            match = parser.OFPMatch(
                eth_type=0x0800,
                eth_dst=gateway_mac,
                ipv4_dst=dst_ip)
            
            # L3 Router actions:
            # 1. Decrement TTL (proper L3 behavior)
            # 2. Rewrite source MAC to local switch MAC (L3 hop)
            # 3. Keep destination MAC as gateway (next cluster will rewrite)
            # 4. Forward to GRE boundary port
            actions = [
                parser.OFPActionDecNwTtl(),  # TTL - 1
                parser.OFPActionSetField(eth_src=switch_mac),  # Rewrite src MAC
                parser.OFPActionOutput(out_port)
            ]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            
            # Install flow with higher priority than normal forwarding
            mod = parser.OFPFlowMod(
                datapath=dp,
                priority=20,
                match=match,
                instructions=inst,
                idle_timeout=60,
                hard_timeout=120)
            dp.send_msg(mod)
            
            self.logger.info(f"[CC] ✓ Installed L3 cross-cluster flow: dst_ip={dst_ip}, dst_mac={gateway_mac} -> TTL-1, src_mac={switch_mac}, port={out_port}")
            
        except Exception as e:
            self.logger.error(f"[CC] Error installing cross-cluster rewrite flow: {e}", exc_info=True)
    
    def _request_cross_cluster_path(self, src_ip, dst_ip, src_mac, dst_mac):
        """Request cross-cluster path from AC"""
        try:
            src_cluster = self.cluster_id
            # Use _get_cluster_from_ip to determine destination cluster
            dst_cluster = self._get_cluster_from_ip(dst_ip)
            
            if dst_cluster is None:
                self.logger.warning(f"[CC] Cannot determine cluster ID for IP {dst_ip}")
                return
            
            if dst_cluster == src_cluster:
                # Same cluster, no need for cross-cluster routing
                self.logger.info(f"[CC] Same cluster {src_cluster}, no cross-cluster routing needed")
                return
            
            # Check if we already have a pending request
            req_key = (src_cluster, dst_cluster)
            now = time.time()
            if req_key in self._flow_requests_pending:
                last_req = self._flow_requests_pending[req_key]
                if now - last_req < 5.0:  # Don't spam requests
                    self.logger.info(f"[CC] FlowRequest for C{src_cluster}->C{dst_cluster} already pending (within 5s), skipping")
                    return
            
            self._flow_requests_pending[req_key] = now
            
            self.logger.info(f"[CC] ===== SENDING FLOW REQUEST TO AC =====")
            self.logger.info(f"[CC]   Source Cluster: {src_cluster}")
            self.logger.info(f"[CC]   Destination Cluster: {dst_cluster}")
            self.logger.info(f"[CC]   Source IP: {src_ip}")
            self.logger.info(f"[CC]   Destination IP: {dst_ip}")
            
            # Send FlowRequest to AC
            req = message_pb2.FlowRequest()
            req.src_cluster = src_cluster
            req.dst_cluster = dst_cluster
            req.match_fields['src_ip'] = src_ip
            req.match_fields['dst_ip'] = dst_ip
            req.match_fields['src_mac'] = src_mac
            req.match_fields['dst_mac'] = dst_mac
            
            envelope = message_pb2.Envelope()
            envelope.type = message_pb2.Envelope.FLOW_REQUEST
            envelope.msg_id = self._next_msg_id()
            envelope.flow_request.CopyFrom(req)
            data = envelope.SerializeToString()
            
            self.logger.info(f"[CC] FlowRequest sent: C{src_cluster}->C{dst_cluster}, msg_id={envelope.msg_id}, bytes={len(data)}")
            self._send_bytes(data)
            
        except Exception as e:
            self.logger.error(f"[CC] FlowRequest error: {e}", exc_info=True)

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
                    self.logger.info(f"[CC] ===== RECEIVED FLOW REPLY FROM AC =====")
                    self.logger.info(f"[CC]   Path: {list(fr.path)}")
                    self.logger.info(f"[CC]   Segments: {len(fr.segments)}")
                    self.logger.info(f"[CC]   Match fields: {dict(fr.match_fields)}")
                    self._install_flow_from_reply(fr)
            except Exception as e:
                self.logger.warning(f"[CC] AC reader error: {e}")
                break
    
    def _install_flow_from_reply(self, flow_reply):
        """
        Install flows based on FlowReply from AC - with proper L3 routing.
        Implements bidirectional flows with:
        - TTL decrement
        - MAC rewriting (src_mac to switch MAC, dst_mac to next-hop)
        - Proper port selection (GRE for egress, host-facing for ingress)
        """
        try:
            match_fields = dict(flow_reply.match_fields)
            path = list(flow_reply.path)
            
            self.logger.info(f"[CC] ===== INSTALLING L3 FLOWS FROM AC REPLY =====")
            self.logger.info(f"[CC]   Path to follow: {path}")
            self.logger.info(f"[CC]   Match fields: {match_fields}")
            
            # Find the segment for this cluster
            my_segment = None
            for seg in flow_reply.segments:
                if seg.cluster_id == self.cluster_id:
                    my_segment = seg
                    break
            
            if not my_segment:
                self.logger.warning(f"[CC] No segment for cluster {self.cluster_id} in reply, installing flows without segment info")
            else:
                self.logger.info(f"[CC] Found segment for cluster {self.cluster_id}")
            
            # Extract IPs and MACs
            dst_ip = match_fields.get('dst_ip')
            src_ip = match_fields.get('src_ip')
            original_src_mac = match_fields.get('src_mac')
            original_dst_mac = match_fields.get('dst_mac')
            
            if not dst_ip or not src_ip:
                self.logger.warning(f"[CC] Missing src_ip or dst_ip in match fields, cannot install flow")
                return
            
            # Determine cluster role based on path from AC (NOT from IP addresses!)
            # path = [src_cluster, intermediate_clusters..., dst_cluster]
            if not path or len(path) < 2:
                self.logger.warning(f"[CC] Invalid path {path}, cannot determine cluster role")
                return
            
            # Convert path elements to integers for comparison
            path_int = [int(c) for c in path]
            src_cluster = path_int[0]
            dst_cluster = path_int[-1]
            my_cluster = self.cluster_id
            
            # Determine role: source, intermediate, or destination
            is_source_cluster = (my_cluster == src_cluster)
            is_dest_cluster = (my_cluster == dst_cluster)
            is_intermediate_cluster = (my_cluster in path_int[1:-1]) if len(path_int) > 2 else False
            
            self.logger.info(f"[CC] Cluster role: src={src_cluster}, dst={dst_cluster}, my={my_cluster}, is_source={is_source_cluster}, is_dest={is_dest_cluster}, is_intermediate={is_intermediate_cluster}")
            
            # Install BIDIRECTIONAL L3 flows on each switch
            installed_count = 0
            for dpid, dp in self._datapaths.items():
                parser = dp.ofproto_parser
                ofproto = dp.ofproto
                
                switch_mac = self._switch_mac.get(dpid, f"02:00:00:{self.cluster_id:02x}:00:00")
                gre_ports = self._gre_ports.get(dpid, set())
                host_ports = self._host_ports.get(dpid, set())
                
                # === FORWARD FLOW: traffic going TO dst_ip ===
                if is_source_cluster or not is_dest_cluster:
                    # Source or intermediate cluster: forward to GRE port
                    egress_port = None
                    for lk, (lname, lport, pdpid, pport) in self._pending_links.items():
                        if lname == self._dpid_name.get(dpid) and lport in gre_ports:
                            egress_port = lport
                            break
                    if egress_port is None and gre_ports:
                        egress_port = list(gre_ports)[0]
                    
                    if egress_port:
                        # L3 forward flow: match dst_ip, dec TTL, rewrite MACs, output to GRE
                        match_fwd = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                        gateway_mac = self._get_gateway_mac_for_cluster(dst_cluster)
                        actions_fwd = [
                            parser.OFPActionDecNwTtl(),
                            parser.OFPActionSetField(eth_src=switch_mac),
                            parser.OFPActionSetField(eth_dst=gateway_mac),
                            parser.OFPActionOutput(egress_port)
                        ]
                        inst_fwd = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions_fwd)]
                        mod_fwd = parser.OFPFlowMod(datapath=dp, priority=15,
                                               match=match_fwd, instructions=inst_fwd,
                                               idle_timeout=30, hard_timeout=60)
                        dp.send_msg(mod_fwd)
                        self.logger.info(f"[CC] ✓ Installed L3 FORWARD flow: dst_ip={dst_ip} -> TTL-1, src_mac={switch_mac}, dst_mac={gateway_mac}, port={egress_port}")
                        installed_count += 1
                
                elif is_dest_cluster:
                    # Destination cluster: forward to host port
                    # Find host port for the destination MAC (learned from ARP)
                    dst_mac_learned = self._ip_to_mac.get(dst_ip)
                    ingress_port = None
                    
                    if dst_mac_learned and dpid in self._mac_to_port:
                        ingress_port = self._mac_to_port[dpid].get(dst_mac_learned)
                    
                    # Fallback: use any host port
                    if ingress_port is None and host_ports:
                        ingress_port = list(host_ports)[0]
                    
                    if ingress_port:
                        # L3 forward to local host: match dst_ip, dec TTL, rewrite dst_MAC to actual host MAC
                        match_fwd = parser.OFPMatch(eth_type=0x0800, ipv4_dst=dst_ip)
                        final_dst_mac = dst_mac_learned if dst_mac_learned else "ff:ff:ff:ff:ff:ff"
                        actions_fwd = [
                            parser.OFPActionDecNwTtl(),
                            parser.OFPActionSetField(eth_src=switch_mac),
                            parser.OFPActionSetField(eth_dst=final_dst_mac),
                            parser.OFPActionOutput(ingress_port)
                        ]
                        inst_fwd = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions_fwd)]
                        mod_fwd = parser.OFPFlowMod(datapath=dp, priority=15,
                                               match=match_fwd, instructions=inst_fwd,
                                               idle_timeout=30, hard_timeout=60)
                        dp.send_msg(mod_fwd)
                        self.logger.info(f"[CC] ✓ Installed L3 FORWARD flow to host: dst_ip={dst_ip} -> TTL-1, src_mac={switch_mac}, dst_mac={final_dst_mac}, port={ingress_port}")
                        installed_count += 1
                
                # === RETURN FLOW: traffic going back FROM dst_ip TO src_ip ===
                if is_dest_cluster or not is_source_cluster:
                    # Destination or intermediate cluster: return to GRE port
                    egress_port = None
                    for lk, (lname, lport, pdpid, pport) in self._pending_links.items():
                        if lname == self._dpid_name.get(dpid) and lport in gre_ports:
                            egress_port = lport
                            break
                    if egress_port is None and gre_ports:
                        egress_port = list(gre_ports)[0]
                    
                    if egress_port:
                        # L3 return flow: match src_ip (return destination), dec TTL, rewrite MACs, output to GRE
                        match_ret = parser.OFPMatch(eth_type=0x0800, ipv4_dst=src_ip)
                        gateway_mac = self._get_gateway_mac_for_cluster(src_cluster)
                        actions_ret = [
                            parser.OFPActionDecNwTtl(),
                            parser.OFPActionSetField(eth_src=switch_mac),
                            parser.OFPActionSetField(eth_dst=gateway_mac),
                            parser.OFPActionOutput(egress_port)
                        ]
                        inst_ret = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions_ret)]
                        mod_ret = parser.OFPFlowMod(datapath=dp, priority=15,
                                               match=match_ret, instructions=inst_ret,
                                               idle_timeout=30, hard_timeout=60)
                        dp.send_msg(mod_ret)
                        self.logger.info(f"[CC] ✓ Installed L3 RETURN flow: dst_ip={src_ip} -> TTL-1, src_mac={switch_mac}, dst_mac={gateway_mac}, port={egress_port}")
                        installed_count += 1
                
                elif is_source_cluster:
                    # Source cluster: return to host port
                    src_mac_learned = self._ip_to_mac.get(src_ip)
                    ingress_port = None
                    
                    if src_mac_learned and dpid in self._mac_to_port:
                        ingress_port = self._mac_to_port[dpid].get(src_mac_learned)
                    
                    # Fallback: use any host port
                    if ingress_port is None and host_ports:
                        ingress_port = list(host_ports)[0]
                    
                    if ingress_port:
                        # L3 return to local host: match src_ip (as destination), dec TTL, rewrite dst_MAC to actual host MAC
                        match_ret = parser.OFPMatch(eth_type=0x0800, ipv4_dst=src_ip)
                        final_dst_mac = src_mac_learned if src_mac_learned else "ff:ff:ff:ff:ff:ff"
                        actions_ret = [
                            parser.OFPActionDecNwTtl(),
                            parser.OFPActionSetField(eth_src=switch_mac),
                            parser.OFPActionSetField(eth_dst=final_dst_mac),
                            parser.OFPActionOutput(ingress_port)
                        ]
                        inst_ret = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions_ret)]
                        mod_ret = parser.OFPFlowMod(datapath=dp, priority=15,
                                               match=match_ret, instructions=inst_ret,
                                               idle_timeout=30, hard_timeout=60)
                        dp.send_msg(mod_ret)
                        self.logger.info(f"[CC] ✓ Installed L3 RETURN flow to host: dst_ip={src_ip} -> TTL-1, src_mac={switch_mac}, dst_mac={final_dst_mac}, port={ingress_port}")
                        installed_count += 1
            
            # Store IP-to-cluster mappings for future ARP proxy decisions
            if src_cluster:
                self._ip_to_cluster[src_ip] = src_cluster
            if dst_cluster:
                self._ip_to_cluster[dst_ip] = dst_cluster
            
            self.logger.info(f"[CC] ===== L3 BIDIRECTIONAL FLOW INSTALLATION COMPLETE: {installed_count} flows =====")
                
        except Exception as e:
            self.logger.error(f"[CC] Error installing flow from reply: {e}", exc_info=True)

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