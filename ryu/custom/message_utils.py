import struct
from my_ofp_experimenter import MyOFPExperimenter

# CC 发送集群信息报文
def create_cluster_info_message(datapath, cluster_id, members, edge_nodes):
    experimenter = 0xFF000001  # CC 上报集群信息
    exp_type = 1
    cluster_id_encoded = cluster_id.encode().ljust(4, b'\x00')  # 4B 长度
    members_encoded = ','.join(members).encode()
    edge_nodes_encoded = ','.join(edge_nodes).encode()
    
    data = struct.pack(f'!4sB{len(members_encoded)}sB{len(edge_nodes_encoded)}s', 
                        cluster_id_encoded, len(members), members_encoded, len(edge_nodes), edge_nodes_encoded)
    
    return MyOFPExperimenter(datapath, experimenter, exp_type, data)

# AC 解析 CC 发送的集群信息
def parse_cluster_info(data):
    cluster_id, member_count = struct.unpack_from('!4sB', data, 0)
    cluster_id = cluster_id.strip(b'\x00').decode()
    
    offset = 5
    members = data[offset:offset + member_count].decode().split(',')
    offset += member_count
    edge_count = struct.unpack_from('!B', data, offset)[0]
    offset += 1
    edge_nodes = data[offset:offset + edge_count].decode().split(',')
    
    return cluster_id, members, edge_nodes

# AC 发送路径控制信息
def create_path_info_message(datapath, src_cluster, dst_cluster, path_nodes):
    experimenter = 0xFF000002  # AC 发送路径信息
    exp_type = 2
    src_cluster_encoded = src_cluster.encode().ljust(4, b'\x00')
    dst_cluster_encoded = dst_cluster.encode().ljust(4, b'\x00')
    path_encoded = ','.join(path_nodes).encode()

    data = struct.pack(f'!4s4sB{len(path_encoded)}s', 
                        src_cluster_encoded, dst_cluster_encoded, len(path_nodes), path_encoded)
    
    return MyOFPExperimenter(datapath, experimenter, exp_type, data)

# CC 解析路径控制信息
def parse_path_info(data):
    src_cluster, dst_cluster, path_count = struct.unpack_from('!4s4sB', data, 0)
    src_cluster = src_cluster.strip(b'\x00').decode()
    dst_cluster = dst_cluster.strip(b'\x00').decode()
    
    path_nodes = data[9:].decode().split(',')
    
    return src_cluster, dst_cluster, path_nodes
