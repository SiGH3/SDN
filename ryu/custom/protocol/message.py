from . import message_pb2

def encode_envelope(msg_type, msg_body):
    envelope = message_pb2.Envelope()
    envelope.type = msg_type

    if msg_type == message_pb2.Envelope.HELLO:
        envelope.hello.CopyFrom(msg_body)
    elif msg_type == message_pb2.Envelope.FLOW_REQUEST:
        envelope.flow_request.CopyFrom(msg_body)
    else:
        raise ValueError("Unknown message type")

    return envelope.SerializeToString()

def decode_envelope(data):
    envelope = message_pb2.Envelope()
    envelope.ParseFromString(data)
    return envelope
