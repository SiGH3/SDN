from concurrent.futures import ThreadPoolExecutor  # ADDED
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message
import threading

def handle_connection(conn, addr):  # ADDED: 单独处理每个连接
    print(f"[CC] Connected by {addr}")
    while True:
        try:
            data = network.receive_message(conn)
            if data is None:
                print(f"[CC] Connection from {addr} closed")
                break

            envelope = message.decode_envelope(data)
            if envelope.type == message_pb2.Envelope.HELLO:
                handle_hello(envelope.hello)
            elif envelope.type == message_pb2.Envelope.FLOW_REPLY:
                handle_flow_reply(envelope.flow_reply)
            else:
                print("[CC] Unknown message type")
        except Exception as e:
            print(f"[CC] Error handling connection from {addr}: {e}")
            break
    conn.close()


def handle_hello(hello_msg):
    print(f"[CC] Received HELLO from {hello_msg.node_id}, version {hello_msg.version}")
    # 示例（触发一次）
    send_flow_request_to_ac("127.0.0.1", 10000)


# def handle_flow_request(flow_req_msg):
#     print(f"[CC] Received FLOW_REQUEST from cluster {flow_req_msg.src_cluster} to {flow_req_msg.dst_cluster}")
#     print(f"[CC] Match fields: {dict(flow_req_msg.match_fields)}")

def handle_flow_reply(flow_reply_msg):
    print("[CC] Received FLOW_REPLY")
    print(f"[CC] Path: {' → '.join(flow_reply_msg.path)}")



def send_flow_request_to_ac(ac_ip, ac_port):
    sock = network.create_client_socket(ac_ip, ac_port)
    print(f"[CC] Connecting to AC at {ac_ip}:{ac_port}")

    # 构造 FLOW_REQUEST 消息
    flow_req = message_pb2.FlowRequest()
    flow_req.src_cluster = 2
    flow_req.dst_cluster = 1
    flow_req.match_fields["ip_dst"] = "10.0.0.100"

    data = message.encode_envelope(message_pb2.Envelope.FLOW_REQUEST, flow_req)
    print("[CC] Sending FLOW_REQUEST to AC")
    network.send_message(sock, data)
    # sock.close()

    try:
        reply_data = network.receive_message(sock)
        if reply_data:
            envelope = message.decode_envelope(reply_data)
            if envelope.type == message_pb2.Envelope.FLOW_REPLY:
                handle_flow_reply(envelope.flow_reply)
            else:
                print(f"[CC] Unexpected reply type: {envelope.type}")
        else:
            print("[CC] No reply data received")
    except Exception as e:
        print(f"[CC] Error receiving FLOW_REPLY: {e}")

    sock.close()



def run_cc(port):  # MODIFIED: 可指定端口
    print(f"[*] CC Controller starting on port {port}...")
    server = network.create_server_socket('0.0.0.0', port)
    print("[CC] Waiting for connection...")

    # 启动客户端连接 AC 并发送 FLOW_REQUEST
    threading.Thread(target=send_flow_request_to_ac, args=("127.0.0.1", 10000), daemon=True).start()

    with ThreadPoolExecutor(max_workers=10) as executor:  # ADDED
        while True:
            conn, addr = server.accept()
            executor.submit(handle_connection, conn, addr)  # ADDED: 每个连接分配线程

    




#if __name__ == '__main__':
#   port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
#   run_cc()

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 test_cc_controller.py <port>")
        sys.exit(1)

    port = int(sys.argv[1])
    run_cc(port)

    

