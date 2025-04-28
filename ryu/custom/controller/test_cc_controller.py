from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message

def handle_hello(hello_msg):
    print(f"[CC] Received HELLO from {hello_msg.node_id}, version {hello_msg.version}")

def handle_flow_request(flow_req_msg):
    print(f"[CC] Received FLOW_REQUEST from cluster {flow_req_msg.src_cluster} to {flow_req_msg.dst_cluster}")
    print(f"[CC] Match fields: {dict(flow_req_msg.match_fields)}")

def run_cc():
    server = network.create_server_socket('0.0.0.0', 9000)
    print("[CC] Waiting for connection...")
    conn, addr = server.accept()
    print(f"[CC] Connected by {addr}")

    while True:
        try:
            data = network.receive_message(conn)
            if data is None:
                print("[CC] Connection closed")
                break

            envelope = message.decode_envelope(data)
            if envelope.type == message_pb2.Envelope.HELLO:
                handle_hello(envelope.hello)
            elif envelope.type == message_pb2.Envelope.FLOW_REQUEST:
                handle_flow_request(envelope.flow_request)
            else:
                print("[CC] Unknown message type")
        except Exception as e:
            print(f"[CC] Error: {e}")
            break

    conn.close()

if __name__ == '__main__':
    run_cc()
