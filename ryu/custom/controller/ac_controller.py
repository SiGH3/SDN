from ryu.base import app_manager
from ryu.custom.protocol.message import FlowRequest
from ryu.custom.protocol.message_pb2 import encode_flow_request

class ACController(app_manager.RyuApp):
    def __init__(self):
        super().__init__()
        self.clusters = {}  # {cluster_id: (ip, port)}

    def handle_cross_cluster_request(self, src_cluster, dst_cluster, match):
        """处理跨集群流表请求并下发"""
        request = FlowRequest(src_cluster, dst_cluster, match)
        encoded = encode_flow_request(request)
        self._send_to_cluster(dst_cluster, encoded)