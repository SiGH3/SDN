import struct
from ryu.ofproto.ofproto_v1_3_parser import OFPExperimenter

#Experimenter (4B)：实验者 ID（用于区分不同的厂商或自定义协议）。
#Exp_type (4B)：子类型，标识不同的自定义消息类型。
#Data (可变长)：具体的自定义数据内容。




class MyOFPExperimenter(OFPExperimenter):
    def __init__(self, datapath, experimenter, exp_type, data=None):
        super(MyOFPExperimenter, self).__init__(datapath, experimenter, exp_type, data)

    @classmethod
    def parser(cls, msg, datapath):
        experimenter, exp_type = struct.unpack_from('!II', msg.buf, 8)
        data = msg.buf[16:]
        return cls(datapath, experimenter, exp_type, data)
    #从 OpenFlow Experimenter 消息 解析 experimenter ID、exp_type、data
    #data为自定义数据
