import socket

def create_server_socket(ip, port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((ip, port))
    server.listen(5)
    return server

def create_client_socket(ip, port):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((ip, port))
    return client

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
