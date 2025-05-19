import time
from concurrent.futures import ThreadPoolExecutor
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message

CC_LIST = [("127.0.0.1", 9000), ("127.0.0.1", 9001)]  # ADDED: 支持连接多个 CC 控制器

def connect_to_cc(cc_ip, cc_port, node_id):  # ADDED: 封装每个连接逻辑
    sock = network.create_client_socket(cc_ip, cc_port)

    # 构造一个 HELLO 消息
    hello = message_pb2.Hello()
    hello.node_id = node_id
    hello.version = "1.0"
    data = message.encode_envelope(message_pb2.Envelope.HELLO, hello)

    print(f"[{node_id}] Sending HELLO to {cc_ip}:{cc_port}...")
    network.send_message(sock, data)

    # 构造一个 FLOW_REQUEST 消息
    time.sleep(1)
    flow_req = message_pb2.FlowRequest()
    flow_req.src_cluster = 1
    flow_req.dst_cluster = 2
    flow_req.match_fields["ip_dst"] = "10.0.0.1"
    data = message.encode_envelope(message_pb2.Envelope.FLOW_REQUEST, flow_req)

    #print("[AC] Sending FLOW_REQUEST...")
    print(f"[{node_id}] Sending FLOW_REQUEST to {cc_ip}:{cc_port}...")
    network.send_message(sock, data)

    sock.close()

def run_ac():
    with ThreadPoolExecutor(max_workers=len(CC_LIST)) as executor:
        for i, (ip, port) in enumerate(CC_LIST):
            node_id = f"AC-{i}"
            executor.submit(connect_to_cc, ip, port, node_id)

if __name__ == '__main__':
    run_ac()

