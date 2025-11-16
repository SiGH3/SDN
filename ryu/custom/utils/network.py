import socket
import time
from ryu.custom.protocol import message_pb2

def _tune_tcp_socket(sock: socket.socket):
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 20)
        if hasattr(socket, "TCP_KEEPINTVL"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 5)
        if hasattr(socket, "TCP_KEEPCNT"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except Exception:
        pass

def create_server_socket(ip, port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((ip, port))
    srv.listen()
    return srv

def create_client_socket(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((ip, port))
    _tune_tcp_socket(sock)
    return sock

def recvall(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data

def send_message(sock, data: bytes):
    # 长度前缀（uint32大端）+ 负载
    sock.sendall(len(data).to_bytes(4, 'big') + data)

def receive_message(sock):
    raw_len = recvall(sock, 4)
    if not raw_len:
        return None
    n = int.from_bytes(raw_len, 'big')
    return recvall(sock, n)

# 直接发送/接收 Envelope（由调用方构造/解析消息体）
def send_envelope(sock, envelope: message_pb2.Envelope):
    send_message(sock, envelope.SerializeToString())

def receive_envelope(sock):
    data = receive_message(sock)
    if not data:
        return None
    env = message_pb2.Envelope()
    env.ParseFromString(data)
    return env

# --- Keepalive helpers (demo) ---
def build_keepalive(cluster_id: int | None = None, ts_ms: int | None = None) -> message_pb2.Keepalive:
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    ka = message_pb2.Keepalive()
    # 若 proto 未定义 cluster_id 字段，可忽略
    if hasattr(ka, "cluster_id") and cluster_id is not None:
        ka.cluster_id = int(cluster_id)
    ka.ts_ms = ts_ms
    return ka

def build_keepalive_envelope(cluster_id: int | None = None, ts_ms: int | None = None) -> message_pb2.Envelope:
    ka = build_keepalive(cluster_id, ts_ms)
    env = message_pb2.Envelope()
    env.type = message_pb2.Envelope.KEEPALIVE
    env.keepalive.CopyFrom(ka)
    return env

def send_keepalive(sock, cluster_id: int | None = None):
    send_envelope(sock, build_keepalive_envelope(cluster_id))

def keepalive_loop(sock, interval_sec=10, cluster_id: int | None = None):
    while True:
        try:
            send_keepalive(sock, cluster_id)
        except Exception:
            pass
        time.sleep(interval_sec)
