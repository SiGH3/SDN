import time
import threading
from concurrent.futures import ThreadPoolExecutor
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message

# from ryu.custom.protocol.message_pb2 import FlowInstall  # ADDED



CC_LIST = [("127.0.0.1", 9000), ("127.0.0.1", 9001), ("127.0.0.1", 9002)]  # ADDED: 支持连接多个 CC 控制器


def connect_to_cc(cc_ip, cc_port, node_id):
    sock = network.create_client_socket(cc_ip, cc_port)

    # 构造并发送 HELLO 消息
    envelope = message_pb2.Envelope()
    envelope.msg_type = message_pb2.Envelope.HELLO
    envelope.hello.node_id = node_id
    envelope.hello.version = "1.0"
    print(f"[{node_id}] Sending HELLO to {cc_ip}:{cc_port}...")
    network.send_envelope(sock, envelope)

    #sock.close()  # 可选：如果 AC 和 CC 未来用新的连接通信，则可以关闭；否则可改为保持连接



# AC 启动监听 socket，接收 CC 消息
def start_ac_server(ip="0.0.0.0",port=10000):
    server = network.create_server_socket(ip,port)
    print(f"[AC] Listening for CC connections on {ip}:{port}...")

    while True:
        conn, addr = server.accept()
        print(f"[AC] Received connection from {addr}")
        threading.Thread(target=handle_cc_connection, args=(conn,addr)).start()



def handle_cc_connection(conn,addr):
    print(f"[AC] Received connection from {addr}")
    while True:
        envelope = network.receive_envelope(conn)
        if not envelope:
            print(f"[AC] Connection from {addr} closed.")
            break

        if envelope.type == message_pb2.Envelope.HELLO:
            print(f"[AC] Received HELLO from {addr}")
        elif envelope.type == message_pb2.Envelope.FLOW_REQUEST:
            print(f"[AC] Received FLOW_REQUEST from {addr}, computing path...")

            handle_flow_request(conn,envelope.flow_request)

# 示例拓扑
TOPO = {
    1: {2: ["s1", "s2", "s3"]},  # 表示从集群1到2的路径为一组交换机
    2: {1: ["s3", "s2", "s1"]},
}


# 示例路径下发
# def handle_flow_request(req):
#     print(f"[AC] Calculating path: Cluster {req.src_cluster} → Cluster {req.dst_cluster}")
#     path = TOPO.get(req.src_cluster, {}).get(req.dst_cluster, [])
#     print(f"[AC] Match fields: {dict(req.match_fields)}")
#     ## TODO: 实际路径规划和向对应 CC 下发 FLOW_REPLY



def handle_flow_request(conn,req):
    print(f"[AC] Calculating path: Cluster {req.src_cluster} → Cluster {req.dst_cluster}")
    path = TOPO.get(req.src_cluster, {}).get(req.dst_cluster, [])

    print(f"[AC] Match fields: {dict(req.match_fields)}")

    if not path:
        print("[AC] No path found.")
        return

    # 构造 FLOW_REPLY 消息
    reply_msg = message_pb2.FlowReply()
    reply_msg.path.extend(path)
    reply_msg.match_fields.update(req.match_fields)

    # 包装成 Envelope
    reply_envelope = message_pb2.Envelope()
    reply_envelope.type = message_pb2.Envelope.FLOW_REPLY
    reply_envelope.flow_reply.CopyFrom(reply_msg)

    # 发送给目标集群对应的 CC
    try:
        print(f"[AC] Sending FLOW_REPLY to requester via same connection")
        data = message.encode_envelope(reply_envelope.type, reply_msg)
        network.send_message(conn, data)
    except Exception as e:
        print(f"[AC] Failed to send FLOW_REPLY via conn: {e}")



def run_ac():
    # 启动监听线程（server）
    threading.Thread(target=start_ac_server, daemon=True).start()

    # 启动 client 线程连接多个 CC
    with ThreadPoolExecutor(max_workers=len(CC_LIST)) as executor:
        for i, (ip, port) in enumerate(CC_LIST):
            node_id = f"AC-{i}"
            executor.submit(connect_to_cc, ip, port, node_id)



if __name__ == '__main__':
    # threading.Thread(target=start_ac_server).start()
    run_ac()
    while True:
        time.sleep(10)  # MOD: 主线程保活，等待 server 子线程接收连接

