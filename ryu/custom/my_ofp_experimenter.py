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


#CC to AC
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#| Experimenter = 0xFF000001  | Exp_type = 1  | Cluster ID (4B)  |
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#|       成员节点数量 (1B)      | 成员节点列表 (可变长)         |
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#|       边界节点数量 (1B)      |  边界节点列表 (可变长)        |
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+


#AC to CC
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#| Experimenter = 0xFF000002  | Exp_type = 2  | 源集群 ID (4B)   |
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
#|  目的集群 ID (4B)  |  路径节点数量 (1B)  | 路径列表 (可变长) |
#+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
