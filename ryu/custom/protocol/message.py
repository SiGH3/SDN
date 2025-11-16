from . import message_pb2

def encode_envelope(msg_type, msg_body):
    envelope = message_pb2.Envelope()
    envelope.type = msg_type

    # 运行期类型校验，防止把 Envelope 当作 body 传入
    expected = {
        message_pb2.Envelope.HELLO: message_pb2.Hello,
        message_pb2.Envelope.FLOW_MOD: message_pb2.FlowMod,
        message_pb2.Envelope.FLOW_REQUEST: message_pb2.FlowRequest,
        message_pb2.Envelope.FLOW_REPLY: message_pb2.FlowReply,
        message_pb2.Envelope.ERROR: message_pb2.ErrorMsg,
        message_pb2.Envelope.KEEPALIVE: message_pb2.Keepalive,
        message_pb2.Envelope.TOPOLOGY_UPDATE: message_pb2.TopologyUpdate,
        message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE: message_pb2.InterClusterLinkUpdate,
    }
    exp_type = expected.get(msg_type)
    if exp_type is None:
        raise ValueError(f"Unknown message type: {msg_type}")
    if not isinstance(msg_body, exp_type):
        raise TypeError(f"encode_envelope expects {exp_type.__name__} for type {msg_type}, got {type(msg_body).__name__}")

    if msg_type == message_pb2.Envelope.HELLO:
        envelope.hello.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_MOD:
        envelope.flow_mod.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_REQUEST:
        envelope.flow_request.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_REPLY:
        envelope.flow_reply.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.ERROR:
        envelope.error.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.KEEPALIVE:
        envelope.keepalive.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.TOPOLOGY_UPDATE:
        envelope.topology_update.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE:
        envelope.intercluster_link_update.CopyFrom(msg_body)

    return envelope.SerializeToString()

def decode_envelope(data):
    envelope = message_pb2.Envelope()
    envelope.ParseFromString(data)
    return envelope
