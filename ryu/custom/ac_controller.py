from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto.ofproto_v1_3 import OFPT_EXPERIMENTER
from ryu.lib import hub
from message_utils import parse_cluster_info, create_path_info_message

class ACController(app_manager.RyuApp):
    OFP_VERSIONS = [13]

    def __init__(self, *args, **kwargs):
        super(ACController, self).__init__(*args, **kwargs)
        self.cluster_info = {}  # 记录集群拓扑
        self.datapaths = {}

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def handle_packet_in(self, ev):
        """处理 CC 发送的集群信息"""
        msg = ev.msg
        datapath = msg.datapath
        if msg.msg_type == OFPT_EXPERIMENTER:
            cluster_id, members, edge_nodes = parse_cluster_info(msg.data)
            self.cluster_info[cluster_id] = {"members": members, "edges": edge_nodes}
            self.logger.info(f"收到集群 {cluster_id} 信息: {members}, 边界节点: {edge_nodes}")

    def send_path_info(self, src_cluster, dst_cluster, path_nodes):
        """向 CC 发送路径控制信息"""
        for dp in self.datapaths.values():
            msg = create_path_info_message(dp, src_cluster, dst_cluster, path_nodes)
            dp.send_msg(msg)
