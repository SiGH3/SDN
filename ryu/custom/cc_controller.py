from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto.ofproto_v1_3 import OFPT_EXPERIMENTER
from message_utils import create_cluster_info_message, parse_path_info

class CCController(app_manager.RyuApp):
    OFP_VERSIONS = [13]

    def __init__(self, *args, **kwargs):
        super(CCController, self).__init__(*args, **kwargs)
        self.datapath = None

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, MAIN_DISPATCHER)
    def switch_features_handler(self, ev):
        """CC 在连接时自动上报集群信息"""
        self.datapath = ev.msg.datapath
        msg = create_cluster_info_message(self.datapath, "Cluster1", ["A", "B", "C"], ["B"])
        self.datapath.send_msg(msg)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def handle_packet_in(self, ev):
        """处理 AC 下发的路径控制信息"""
        msg = ev.msg
        if msg.msg_type == OFPT_EXPERIMENTER:
            src_cluster, dst_cluster, path_nodes = parse_path_info(msg.data)
            self.logger.info(f"接收路径信息: {src_cluster} → {dst_cluster}，路径: {path_nodes}")
