import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from ryu.custom.controller.ac_topology import ROUTING_POLICY, ClusterGraph
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message
from collections import defaultdict
LINK_EP = defaultdict(dict)  # link_key -> { cluster_id: (switch_id, port_no) }

def _on_intercluster_link_update(env, peer_sock=None):
    lu = env.intercluster_link_update
    cid = int(lu.cluster_id)

    changed = set()
    for le in lu.links:
        LINK_EP[le.link_key][cid] = (le.switch_id, le.port_no)
        changed.add(le.link_key)

    affected = set()
    for lk in changed:
        ep = LINK_EP.get(lk, {})
        if len(ep) < 2:
            continue
        cids = sorted(int(x) for x in ep.keys())
        for c in cids:
            GRAPH.add_cluster(c); affected.add(c)
        for i in range(len(cids)):
            for j in range(i+1, len(cids)):
                GRAPH.add_edge(cids[i], cids[j], link_key=lk)

    if affected:
        _incremental_retry(affected)

GRAPH = ClusterGraph()                  # 跨集群图
PENDING = []                            # [(req, peer_sock)]
PENDING_LOCK = threading.Lock()         # 修复：原先未导入 threading

CC_LIST = []  # 主动连接的 CC 列表，如需主动连接可填: [("127.0.0.1", 9000), ("127.0.0.1", 9001)]

CLUSTER_CONN = {}              # cluster_id -> latest conn
CONN_CLUSTER = {}              # conn -> cluster_id

def _register_cluster_conn(cluster_id: int, conn):
    # 覆盖最新连接，并清理旧连接的逆向索引
    old = CLUSTER_CONN.get(cluster_id)
    CLUSTER_CONN[cluster_id] = conn
    CONN_CLUSTER[conn] = cluster_id
    if old and old is not conn:
        CONN_CLUSTER.pop(old, None)

def _unregister_conn(conn):
    cid = CONN_CLUSTER.pop(conn, None)
    if cid is not None:
        # 仅当当前映射仍指向该 conn 时才移除
        if CLUSTER_CONN.get(cid) is conn:
            CLUSTER_CONN.pop(cid, None)

def _drain_pending_if_possible():
    with PENDING_LOCK:
        if not PENDING:
            return
        remain = []
        for item in PENDING:
            ok = _compute_and_distribute_flow(item['src'], item['dst'], item['match'])
            if not ok:
                remain.append(item)
        PENDING[:] = remain
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
            PENDING.append({'conn': conn, 'src': src, 'dst': dst, 'match': mf})
        print(f"[AC] No path yet for {src}->{dst}, request pending")


def update_topology_with_conn(conn, topo_msg):
    cid = int(topo_msg.cluster_id)
    _register_cluster_conn(cid, conn)
    cid, boundaries, changed = GRAPH.update_topology(topo_msg)
    print(f"[AC] Boundaries[{cid}] -> {boundaries}")
    # 边界变化也尝试一次重算
    _incremental_retry({cid})

def _incremental_retry(affected_clusters: set[int]):
    with PENDING_LOCK:
        if not PENDING:
            return
        remain = []
        for item in PENDING:
            if item['src'] in affected_clusters or item['dst'] in affected_clusters:
                ok = _compute_and_distribute_flow(item['src'], item['dst'], item['match'])
                if not ok:
                    remain.append(item)
            else:
                remain.append(item)
        PENDING[:] = remain
        if remain:
            print(f"[AC] Pending requests remaining after incremental retry: {len(remain)}")


def handle_envelope(conn, envelope):
    t = envelope.type
    if t == message_pb2.Envelope.HELLO:
        nid = envelope.hello.node_id
        if nid.startswith("CC-"):
            try:
                cid = int(nid.split("-")[1])
                _register_cluster_conn(cid, conn)
            except Exception:
                pass
        print(f"[AC] HELLO from {envelope.hello.node_id} v{envelope.hello.version}")
    elif t == message_pb2.Envelope.TOPOLOGY_UPDATE:
        update_topology_with_conn(conn, envelope.topology_update)
    elif t == message_pb2.Envelope.INTERCLUSTER_LINK_UPDATE:
        lu = envelope.intercluster_link_update
        print(f"[AC] LinkUpdate from C{lu.cluster_id}:")
        for le in lu.links:
            print(f"    key={le.link_key} sw={le.switch_id} port={le.port_no}")
        # 使用全局 LINK_EP 聚合
        _on_intercluster_link_update(envelope)
        from pprint import pprint
        print("[AC] LINK_EP snapshot:")
        pprint({lk: list(ep.items()) for lk, ep in LINK_EP.items()})
        # 新增：打印当前域间边集合
        if GRAPH.cluster_edges:
            edges = sorted(list(GRAPH.cluster_edges))
            print(f"[AC] Cluster edges: {edges}")
        else:
            print("[AC] Cluster edges: []")
    elif t == message_pb2.Envelope.FLOW_REQUEST:
        handle_flow_request(conn, envelope.flow_request)
    elif t == message_pb2.Envelope.KEEPALIVE:
        print("[AC] KEEPALIVE")
    elif t == message_pb2.Envelope.INTERCLUSTER_LINK_METRICS:
        met = envelope.intercluster_link_metrics
        affected = set()
        for entry in met.metrics:
            lk = entry.link_key
            endpoints = GRAPH.link_index.get(lk, [])
            cids = {e[0] for e in endpoints}
            if len(cids) >= 2:
                a, b = sorted(list(cids))[:2]
                GRAPH.update_edge_metric(a, b,
                                         latency=entry.latency_ms / 1000.0,
                                         load=entry.load,
                                         weight=entry.load)
                affected.update([a, b])
        print(f"[AC] Metrics update cluster={met.cluster_id} entries={len(met.metrics)}")
        if affected:
            _incremental_retry(affected)
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
        # 清理连接映射
        _unregister_conn(conn)
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
    # 优先使用新接口，否则降级
    path = None
    try:
        path = GRAPH.best_path(src, dst, ROUTING_POLICY)
    except Exception:
        path = GRAPH.calculate_path(src, dst, policy=ROUTING_POLICY)
    if not path:
        return False

    segments = None
    try:
        segments = GRAPH.build_segments(path)
    except Exception:
        # 简化：仅通知路径，源域下发一段
        segments = [{"cluster_id": src, "ingress_border": "", "egress_border": "", "tunnel_id": ""}]

    ok_any = False
    for seg in segments:
        cid = int(seg["cluster_id"])
        conn = CLUSTER_CONN.get(cid)
        if not conn:
            print(f"[AC] No active connection for cluster {cid}, skip segment")
            continue
        reply = message_pb2.FlowReply()
        reply.path.extend([str(x) for x in path])
        reply.match_fields.update(match_fields)
        new_seg = reply.segments.add()
        new_seg.cluster_id = cid
        new_seg.ingress_border = seg.get("ingress_border", "")
        new_seg.egress_border = seg.get("egress_border", "")
        new_seg.tunnel_id = seg.get("tunnel_id", "")
        try:
            data = message.encode_envelope(message_pb2.Envelope.FLOW_REPLY, reply)
            network.send_message(conn, data)
            print(f"[AC] FLOW_REPLY segment sent to cluster {cid} for path {path}")
            ok_any = True
        except Exception as e:
            print(f"[AC] Send segment to cluster {cid} failed: {e}")
            # 连接可能失效，移除映射，留待下一次重算
            _unregister_conn(conn)
    return ok_any


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

