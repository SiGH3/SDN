import time
import threading
from concurrent.futures import ThreadPoolExecutor
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message
import sys
from collections import defaultdict
import socket  # NEW
from ryu.custom.controller.ac_topology import ClusterGraph, ROUTING_POLICY  # NEW

# NEW: 挂起请求队列
PENDING_LOCK = threading.Lock()
PENDING_REQS = []  # [{'conn': conn, 'src': int, 'dst': int, 'match': dict}]

CC_LIST = []  # 主动连接的 CC 列表，如需主动连接可填: [("127.0.0.1", 9000), ("127.0.0.1", 9001)]

CLUSTER_CONN = {}              # NEW: cluster_id -> latest conn
CONN_CLUSTER = {}              # NEW: conn -> cluster_id


# 移除本文件内的 ClusterGraph 定义，改为实例化外部的
GRAPH = ClusterGraph()

def _try_compute_and_reply(conn, src: int, dst: int, match_fields: dict) -> bool:
    path = GRAPH.shortest_path(src, dst)
    if not path:
        return False
    reply = message_pb2.FlowReply()
    reply.path.extend([str(x) for x in path])
    reply.match_fields.update(match_fields)
    # 每一跳生成一个 segment（进入下一集群前的出域段）
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        seg = reply.segments.add()
        seg.cluster_id = a
        seg.ingress_border = f"c{a}-b1"
        seg.egress_border = f"c{b}-b1"
        seg.tunnel_id = "demo-tni"
    try:
        data = message.encode_envelope(message_pb2.Envelope.FLOW_REPLY, reply)
        network.send_message(conn, data)
        print(f"[AC] FLOW_REPLY sent for {src}->{dst} path={path}")
        return True
    except Exception as e:
        print(f"[AC] Failed to send FLOW_REPLY: {e}")
        return False


def _drain_pending_if_possible():
    with PENDING_LOCK:
        if not PENDING_REQS:
            return
        remain = []
        for item in PENDING_REQS:
            ok = _compute_and_distribute_flow(item['src'], item['dst'], item['match'])
            if not ok:
                remain.append(item)
        PENDING_REQS[:] = remain
        if remain:
            print(f"[AC] Pending requests remaining: {len(remain)}")


def handle_flow_request(conn, req):
    src = int(req.src_cluster)
    dst = int(req.dst_cluster)
    mf = dict(req.match_fields)
    print(f"[AC] Calculating path: Cluster {src} → Cluster {dst}")
    print(f"[AC] Match fields: {mf}")
    # 仍记录发起方连接（避免还未发送拓扑时）
    if conn not in CONN_CLUSTER:
        _register_cluster_conn(src, conn)
    if not _compute_and_distribute_flow(src, dst, mf):
        with PENDING_LOCK:
            PENDING_REQS.append({'conn': conn, 'src': src, 'dst': dst, 'match': mf})
        print(f"[AC] No path yet for {src}->{dst}, request pending")


def _register_cluster_conn(cluster_id: int, conn):
    # 简单覆盖最新连接
    CLUSTER_CONN[cluster_id] = conn
    CONN_CLUSTER[conn] = cluster_id


def update_topology_with_conn(conn, topo_msg):
    cid = int(topo_msg.cluster_id)
    _register_cluster_conn(cid, conn)
    cid, boundaries, changed = GRAPH.update_topology(topo_msg)  # CHANGED
    print(f"[AC] Boundaries[{cid}] -> {boundaries}")
    if changed:
        _drain_pending_if_possible()

def handle_envelope(conn, envelope):
    t = envelope.type
    if t == message_pb2.Envelope.HELLO:
        # 从 node_id 中提取 cluster（格式 CC-<id>）
        nid = envelope.hello.node_id
        if nid.startswith("CC-"):
            try:
                cid = int(nid.split("-")[1])
                _register_cluster_conn(cid, conn)
            except Exception:
                pass
        print(f"[AC] HELLO from {envelope.hello.node_id} v{envelope.hello.version}")
    elif t == message_pb2.Envelope.FLOW_REQUEST:
        handle_flow_request(conn, envelope.flow_request)
    elif t == message_pb2.Envelope.TOPOLOGY_UPDATE:
        update_topology_with_conn(conn, envelope.topology_update)
    elif t == message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE:
        edges, changed = GRAPH.update_links(envelope.intercluster_link_update)  # CHANGED
        if changed:
            print(f"[AC] Inter-cluster edges: {edges}")
            _drain_pending_if_possible()
    elif t == message_pb2.Envelope.KEEPALIVE:
        print("[AC] KEEPALIVE")
    else:
        print(f"[AC] Unknown envelope type: {t}")


def handle_connection(conn, addr):
    print(f"[AC] Received connection from {addr}")
    try:
        while True:
            data = network.receive_message(conn)
            if data is None:
                print(f"[AC] Connection from {addr} closed.")
                break
            env = message.decode_envelope(data)
            handle_envelope(conn, env)
    except Exception as e:
        print(f"[AC] Error on connection {addr}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

def start_ac_server(host, port):
    server = network.create_server_socket(host, port)
    print(f"[AC] Listening for CC connections on {host}:{port}...")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_connection, args=(conn, addr), daemon=True).start()

def connect_to_cc(ip, port, node_id):
    # 可选：若需要 AC 主动连 CC（通常不需要），保持占位
    while True:
        try:
            sock = network.create_client_socket(ip, port)
            hello = message_pb2.Hello()
            hello.node_id = node_id
            hello.version = "1.0"
            data = message.encode_envelope(message_pb2.Envelope.HELLO, hello)
            network.send_message(sock, data)
            # 简单读一次后关闭
            resp = network.receive_message(sock)
            if resp:
                env = message.decode_envelope(resp)
                handle_envelope(sock, env)
            sock.close()
        except Exception:
            pass
        time.sleep(5)

def _compute_and_distribute_flow(src: int, dst: int, match_fields: dict):
    # 使用 OXP 风格最优路径
    path = GRAPH.best_path(src, dst, ROUTING_POLICY)  # CHANGED
    if not path:
        return False
    # 构造全局段并分发到各自 CC
    full_segments = GRAPH.build_segments(path)  # CHANGED

    for seg in full_segments:
        cid = seg["cluster_id"]
        conn = CLUSTER_CONN.get(cid)
        if not conn:
            print(f"[AC] No active connection for cluster {cid}, skip segment")
            continue
        reply = message_pb2.FlowReply()
        reply.path.extend([str(x) for x in path])
        reply.match_fields.update(match_fields)
        new_seg = reply.segments.add()
        new_seg.cluster_id = int(seg["cluster_id"])
        new_seg.ingress_border = seg["ingress_border"]
        new_seg.egress_border = seg["egress_border"]
        new_seg.tunnel_id = seg["tunnel_id"]
        try:
            data = message.encode_envelope(message_pb2.Envelope.FLOW_REPLY, reply)
            network.send_message(conn, data)
            print(f"[AC] FLOW_REPLY segment sent to cluster {cid} for path {path}")
        except Exception as e:
            print(f"[AC] Send segment to cluster {cid} failed: {e}")
    return True


def run_ac(port=10000):
    # 启动监听线程（server）
    threading.Thread(target=start_ac_server, args=("0.0.0.0", port), daemon=True).start()
    # 只有在需要主动连接 CC 时启动线程池
    if CC_LIST:
        with ThreadPoolExecutor(max_workers=len(CC_LIST)) as executor:
            for i, (ip, cport) in enumerate(CC_LIST):
                node_id = f"AC-{i}"
                executor.submit(connect_to_cc, ip, cport, node_id)


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    run_ac(port)
    while True:
        time.sleep(10)  # 主线程保活，等待 server 子线程接收连接

