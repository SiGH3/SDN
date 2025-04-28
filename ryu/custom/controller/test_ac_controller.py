import time
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message

def run_ac():
    sock = network.create_client_socket('127.0.0.1', 9000)

    # 构造一个 HELLO 消息
    hello = message_pb2.Hello()
    hello.node_id = "AC"
    hello.version = "1.0"
    data = message.encode_envelope(message_pb2.Envelope.HELLO, hello)

    print("[AC] Sending HELLO...")
    network.send_message(sock, data)

    # 构造一个 FLOW_REQUEST 消息
    time.sleep(1)
    flow_req = message_pb2.FlowRequest()
    flow_req.src_cluster = 1
    flow_req.dst_cluster = 2
    flow_req.match_fields["ip_dst"] = "10.0.0.1"
    data = message.encode_envelope(message_pb2.Envelope.FLOW_REQUEST, flow_req)

    print("[AC] Sending FLOW_REQUEST...")
    network.send_message(sock, data)

    sock.close()

if __name__ == '__main__':
    run_ac()
