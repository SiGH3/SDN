from concurrent.futures import ThreadPoolExecutor  # ADDED
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message
import threading
import time
import queue  # ADDED

# 简单配置（可通过命令行覆盖）
DEFAULT_AC_HOST = "127.0.0.1"
DEFAULT_AC_PORT = 10000
CLUSTER_ID = 2  # 默认集群ID
DST_CLUSTER = 1  # 默认演示目的集群

# ---------------- 持久客户端通道（CC -> AC） ----------------
class PersistentACClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port  
        self.sock = None
        self.send_q = queue.Queue()
        self.stop_flag = threading.Event()
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._connect_and_pump, name="ac-client-pump", daemon=True).start()

    def stop(self):
        self.stop_flag.set()
        with self.lock:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send(self, data: bytes):
        # 放入队列，等待发送线程复用长连接发送
        self.send_q.put(data)

    def _connect(self):
        backoff = 1
        while not self.stop_flag.is_set():
            try:
                sock = network.create_client_socket(self.host, self.port)
                print(f"[CC] Persistent connection established to AC {self.host}:{self.port}")
                return sock
            except Exception as e:
                print(f"[CC] Connect to AC failed: {e}, retry in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)
        return None

    def _reader_loop(self, sock):
        # 读取 AC 的回复并分发（与 server 侧 handle_connection 共用处理逻辑）
        try:
            while not self.stop_flag.is_set():
                data = network.receive_message(sock)
                if data is None:
                    print("[CC] Persistent connection closed by AC (reader)")
                    break
                envelope = message.decode_envelope(data)
                if envelope.type == message_pb2.Envelope.HELLO:
                    handle_hello(envelope.hello)
                elif envelope.type == message_pb2.Envelope.FLOW_REPLY:
                    handle_flow_reply(envelope.flow_reply)
                else:
                    print(f"[CC] (reader) Unknown or unhandled message type: {envelope.type}")
        except Exception as e:
            print(f"[CC] Reader loop error: {e}")

    def _send_hello(self, sock):
        try:
            hello = message_pb2.Hello()
            hello.node_id = f"CC-{CLUSTER_ID}"
            hello.version = "1.0"
            network.send_message(sock, message.encode_envelope(message_pb2.Envelope.HELLO, hello))
        except Exception as e:
            print(f"[CC] Failed to send HELLO on persistent conn: {e}")

    def _drain_send_queue(self, sock):
        # 将队列中的数据发送到 AC
        try:
            # 非阻塞取一条，若无则阻塞等待一会儿
            try:
                data = self.send_q.get(timeout=1.0)
            except queue.Empty:
                return True  # 没有数据，连接保持即可
            network.send_message(sock, data)
            return True
        except Exception as e:
            print(f"[CC] Send on persistent conn failed: {e}")
            return False

    def _connect_and_pump(self):
        while not self.stop_flag.is_set():
            sock = self._connect()
            if sock is None:
                break
            with self.lock:
                self.sock = sock
            # 连接建立后先发 HELLO
            self._send_hello(sock)
            # NEW: 先上报一次拓扑与域间链路，再发送 FlowRequest
            try:
                advertise_topology_once(self.host, self.port, CLUSTER_ID)
                advertise_intercluster_links_once(self.host, self.port, CLUSTER_ID)
            except Exception as e:
                print(f"[CC] Initial advertise failed: {e}")
            # 连接建立后，再发送一次 FlowRequest
            send_flow_request_to_ac(self.host, self.port)
            # 启动接收线程
            reader = threading.Thread(target=self._reader_loop, args=(sock,), name="ac-client-reader", daemon=True)
            reader.start()
            # 发送循环
            try:
                while not self.stop_flag.is_set():
                    ok = self._drain_send_queue(sock)
                    if not ok:
                        break
                print("[CC] Persistent sender loop exiting, will reconnect")
            finally:
                with self.lock:
                    try:
                        if self.sock:
                            self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
            reader.join(timeout=1.0)
            # 重连前稍等
            time.sleep(1.0)

# 全局持久连接实例
AC_PERSISTENT = None

# ---------------- 原有接收/处理（server 侧保持不变） ----------------
def handle_connection(conn, addr):
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
    # 可选：若保留 server 侧被动接收，也可以在握手后再次触发一次 FlowRequest
    # send_flow_request_to_ac(DEFAULT_AC_HOST, DEFAULT_AC_PORT)

def handle_flow_reply(flow_reply_msg):
    print("[CC] Received FLOW_REPLY")
    if flow_reply_msg.path:
        print(f"[CC] Path: {' → '.join(flow_reply_msg.path)}")
    for seg in getattr(flow_reply_msg, "segments", []):
        print(f"[CC] Segment: cluster={seg.cluster_id}, ingress={seg.ingress_border}, egress={seg.egress_border}, tunnel={seg.tunnel_id}")

# ---------------- 改为复用持久连接或一次性发送均可，这里给一次性示例 ----------------
def send_flow_request_once(ac_ip, ac_port, src_cluster, dst_cluster):
    try:
        sock = network.create_client_socket(ac_ip, ac_port)
        req = message_pb2.FlowRequest()
        req.src_cluster = int(src_cluster)
        req.dst_cluster = int(dst_cluster)
        req.match_fields["ip_dst"] = "10.0.0.100"
        data = message.encode_envelope(message_pb2.Envelope.FLOW_REQUEST, req)
        print(f"[CC] Sending FLOW_REQUEST to AC {ac_ip}:{ac_port}")
        network.send_message(sock, data)

        # 等待 AC 的回复
        resp = network.receive_message(sock)
        if resp:
            env = message.decode_envelope(resp)
            if env.type == message_pb2.Envelope.FLOW_REPLY:
                handle_flow_reply(env.flow_reply)
            else:
                print(f"[CC] Unexpected reply type: {env.type}")
        sock.close()
    except Exception as e:
        print(f"[CC] FLOW_REQUEST failed: {e}")

def send_flow_request_to_ac(ac_ip, ac_port):
    # 通过持久连接发送（回复由 reader_loop 接收）
    req = message_pb2.FlowRequest()
    req.src_cluster = CLUSTER_ID
    req.dst_cluster = DST_CLUSTER
    req.match_fields["ip_dst"] = "10.0.0.100"
    data = message.encode_envelope(message_pb2.Envelope.FLOW_REQUEST, req)
    print("[CC] Sending FLOW_REQUEST to AC (persistent)")
    AC_PERSISTENT.send(data)

def advertise_topology_once(ac_ip, ac_port, cluster_id):
    topo = message_pb2.TopologyUpdate()
    topo.cluster_id = cluster_id
    topo.boundary_switches.extend([f"c{cluster_id}-b1"])
    data = message.encode_envelope(message_pb2.Envelope.TOPOLOGY_UPDATE, topo)
    print(f"[CC] Advertising topology to AC {ac_ip}:{ac_port} -> cluster {cluster_id} (persistent)")
    AC_PERSISTENT.send(data)

def advertise_topology_loop(ac_ip, ac_port, cluster_id, interval=10):
    while True:
        advertise_topology_once(ac_ip, ac_port, cluster_id)
        time.sleep(interval)

def advertise_intercluster_links_once(ac_ip, ac_port, cluster_id):
    demo_links = {
        1: [
            {"switch_id": "c1-b1", "port_no": 1, "link_key": "c1c2"},
            {"switch_id": "c1-b2", "port_no": 2, "link_key": "c1c3"},
        ],
        2: [
            {"switch_id": "c2-b1", "port_no": 1, "link_key": "c1c2"},
        ],
        3: [
            {"switch_id": "c3-b1", "port_no": 1, "link_key": "c1c3"},
        ],
    }
    upd = message_pb2.InterClusterLinkUpdate()
    upd.cluster_id = cluster_id
    for l in demo_links.get(cluster_id, []):
        le = upd.links.add()
        le.switch_id = l["switch_id"]
        le.port_no = int(l["port_no"])
        le.link_key = l["link_key"]
    data = message.encode_envelope(message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE, upd)
    print(f"[CC] Advertising inter-cluster links to AC {ac_ip}:{ac_port} -> cluster {cluster_id} (persistent)")
    AC_PERSISTENT.send(data)

def advertise_intercluster_links_loop(ac_ip, ac_port, cluster_id, interval=10):
    while True:
        advertise_intercluster_links_once(ac_ip, ac_port, cluster_id)
        time.sleep(interval)

def keepalive_to_ac_loop(ac_ip, ac_port, interval=12):
    while True:
        try:
            ka = network.build_keepalive(CLUSTER_ID)  # 确保返回的是 Keepalive，而非 Envelope
            data = message.encode_envelope(message_pb2.Envelope.KEEPALIVE, ka)
            AC_PERSISTENT.send(data)
            print(f"[CC] KEEPALIVE queued to {ac_ip}:{ac_port}")
        except Exception as e:
            print(f"[CC] Keepalive enqueue failed: {e}")
        time.sleep(interval)

def run_cc(port):
    print(f"[*] CC Controller starting on port {port} (cluster_id={CLUSTER_ID})...")
    server = network.create_server_socket('0.0.0.0', port)
    print("[CC] Waiting for connection...")

    # 启动持久客户端连接（复用一个 TCP 连接 CC->AC）
    global AC_PERSISTENT
    AC_PERSISTENT = PersistentACClient(DEFAULT_AC_HOST, DEFAULT_AC_PORT)
    AC_PERSISTENT.start()

    # 保留并通过持久连接发送的周期性上报
    threading.Thread(target=advertise_topology_loop, args=(DEFAULT_AC_HOST, DEFAULT_AC_PORT, CLUSTER_ID), daemon=True).start()
    threading.Thread(target=advertise_intercluster_links_loop, args=(DEFAULT_AC_HOST, DEFAULT_AC_PORT, CLUSTER_ID), daemon=True).start()
    threading.Thread(target=keepalive_to_ac_loop, args=(DEFAULT_AC_HOST, DEFAULT_AC_PORT), daemon=True).start()

    # 移除原先“一次性直连发送 FlowRequest”的线程（已改为在持久连接建立后发送）

    with ThreadPoolExecutor(max_workers=10) as executor:
        while True:
            conn, addr = server.accept()
            executor.submit(handle_connection, conn, addr)

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 -m ryu.custom.controller.test_cc_controller <port> [cluster_id] [ac_host] [ac_port] [dst_cluster]")
        sys.exit(1)
    port = int(sys.argv[1])
    if len(sys.argv) >= 3:
        CLUSTER_ID = int(sys.argv[2])
    if len(sys.argv) >= 4:
        DEFAULT_AC_HOST = sys.argv[3]
    if len(sys.argv) >= 5:
        DEFAULT_AC_PORT = int(sys.argv[4])
    if len(sys.argv) >= 6:
        DST_CLUSTER = int(sys.argv[5])
    run_cc(port)



