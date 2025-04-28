import struct
import json

from ryu.custom.protocol.message import FlowRequest, Protocol


def encode_flow_request(request: FlowRequest) -> bytes:
    """将FlowRequest编码为二进制"""
    match_data = json.dumps(request.match).encode()
    return struct.pack(
        "!IIII", 
        Protocol.MAGIC,
        Protocol.TYPE_FLOW_MOD,
        request.src,
        request.dst
    ) + match_data

def decode_message(data: bytes):
    """解析消息头并返回类型和体"""
    magic, type_, _, _ = struct.unpack("!IIII", data[:16])
    if magic != Protocol.MAGIC:
        raise ValueError("Invalid magic number")
    return type_, data[16:]