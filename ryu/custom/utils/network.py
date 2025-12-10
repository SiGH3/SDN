import socket
import struct
import time
from typing import Optional

from ryu.custom.protocol import message_pb2

_LEN_STRUCT = struct.Struct("!I")
_MAX_FRAME = 16 * 1024 * 1024  # 16MB 上限

def create_server_socket(host: str, port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(128)
    return s

def create_client_socket(host: str, port: int, timeout: Optional[float] = 5.0) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if timeout is not None:
        s.settimeout(timeout)
    s.connect((host, port))
    s.settimeout(None)
    return s

def send_message(sock: socket.socket, payload: bytes) -> None:
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    length = len(payload)
    if length > _MAX_FRAME:
        raise ValueError("payload too large")
    header = _LEN_STRUCT.pack(length)
    sock.sendall(header + payload)

def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)

def receive_message(sock: socket.socket) -> Optional[bytes]:
    hdr = _recv_exact(sock, _LEN_STRUCT.size)
    if hdr is None:
        return None
    (length,) = _LEN_STRUCT.unpack(hdr)
    if length > _MAX_FRAME:
        # 丢弃过大帧
        _ = _recv_exact(sock, length)
        return None
    body = _recv_exact(sock, length)
    return body

def build_keepalive(cluster_id: int) -> message_pb2.Keepalive:
    # proto 当前只有 ts_ms 字段，不含 cluster_id；若需 cluster_id 请扩展 Keepalive
    ka = message_pb2.Keepalive()
    ka.ts_ms = int(time.time() * 1000)
    return ka

def safe_close(sock: Optional[socket.socket]) -> None:
    if not sock:
        return
    try:
        sock.close()
    except Exception:
        pass
