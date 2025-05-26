import socket
import struct
from ryu.custom.protocol import message_pb2

def create_server_socket(ip, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #允许套接字在处于 TIME_WAIT 状态时仍然可以绑定相同地址和端口
    server.bind((ip, port))
    server.listen()
    return server

def create_client_socket(ip, port):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((ip, port))
    return client




def send_envelope(sock, envelope):
    data = envelope.SerializeToString()
    length = struct.pack('!I', len(data))  # 4-byte length prefix, network byte order
    sock.sendall(length + data)


def receive_envelope(sock):
    raw_len = recvall(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack('!I', raw_len)[0]
    data = recvall(sock, msg_len)
    if not data:
        return None
    envelope = message_pb2.Envelope()
    envelope.ParseFromString(data)
    return envelope


def recvall(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data




def send_message(sock, data):
    # 先发送长度，再发送数据（防止粘包）
    sock.sendall(len(data).to_bytes(4, byteorder='big') + data)

def receive_message(sock):
    # 先接收长度
    length_bytes = sock.recv(4)
    if not length_bytes:
        return None
    length = int.from_bytes(length_bytes, byteorder='big')
    # 再接收正文
    data = b''
    while len(data) < length:
        more = sock.recv(length - len(data))
        if not more:
            raise EOFError('Socket closed prematurely')
        data += more
    return data
