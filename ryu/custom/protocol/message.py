from . import message_pb2
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ryu.custom.protocol.message_pb2 import Envelope

def encode_envelope(msg_type: int, msg_body: Any) -> bytes:
    env = message_pb2.Envelope()
    env.type = msg_type
    if msg_type == message_pb2.Envelope.HELLO:
        env.hello.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_MOD:
        env.flow_mod.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_REQUEST:
        env.flow_request.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_REPLY:
        env.flow_reply.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.ERROR:
        env.error.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.KEEPALIVE:
        env.keepalive.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.TOPOLOGY_UPDATE:
        env.topology_update.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE:
        env.intercluster_link_update.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.INTERCLUSTER_LINK_METRICS:
        env.intercluster_link_metrics.CopyFrom(msg_body)
    else:
        raise ValueError(f"Unknown envelope type {msg_type}")
    return env.SerializeToString()

def decode_envelope(data: bytes) -> "Envelope":
    env = message_pb2.Envelope()
    env.ParseFromString(data)
    return env
