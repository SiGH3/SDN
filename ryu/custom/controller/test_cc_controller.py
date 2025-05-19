from concurrent.futures import ThreadPoolExecutor  # ADDED
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message

def handle_hello(hello_msg):
    print(f"[CC] Received HELLO from {hello_msg.node_id}, version {hello_msg.version}")

def handle_flow_request(flow_req_msg):
    print(f"[CC] Received FLOW_REQUEST from cluster {flow_req_msg.src_cluster} to {flow_req_msg.dst_cluster}")
    print(f"[CC] Match fields: {dict(flow_req_msg.match_fields)}")

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
            elif envelope.type == message_pb2.Envelope.FLOW_REQUEST:
                handle_flow_request(envelope.flow_request)
            else:
                print("[CC] Unknown message type")
        except Exception as e:
            print(f"[CC] Error handling connection from {addr}: {e}")
            break
    conn.close()


def run_cc(port):  # MODIFIED: 可指定端口
    print(f"[*] CC Controller starting on port {port}...")
    server = network.create_server_socket('0.0.0.0', port)
    print("[CC] Waiting for connection...")

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

    

