import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from ryu.custom.controller.ac_topology import ROUTING_POLICY, ClusterGraph
from ryu.custom.utils import network
from ryu.custom.protocol import message_pb2, message
from collections import defaultdict

# Import synchronization modules
from ryu.custom.controller.sync_protocol import SyncProtocol
from ryu.custom.controller.state_manager import ThreadSafeStateManager

# Global instances
SYNC = SyncProtocol(heartbeat_interval=10.0, heartbeat_timeout=30.0)
STATE = ThreadSafeStateManager()

# Legacy global for backward compatibility (now proxied through STATE)
LINK_EP = defaultdict(dict)  # link_key -> { cluster_id: (switch_id, port_no) }

def _on_intercluster_link_update(env, peer_sock=None):
    """Handle inter-cluster link updates with proper synchronization"""
    lu = env.intercluster_link_update
    cid = int(lu.cluster_id)
    
    # Record message activity
    SYNC.record_message(cid)
    
    # Track message for eventual consistency
    msg_ctx = SYNC.track_message(cid, "LINK_UPDATE", timeout=15.0)

    changed = set()
    for le in lu.links:
        # Update thread-safe state
        STATE.update_link_endpoint(le.link_key, cid, le.switch_id, le.port_no)
        # Also update legacy LINK_EP for backward compatibility
        LINK_EP[le.link_key][cid] = (le.switch_id, le.port_no)
        changed.add(le.link_key)

    # Synchronize links to graph and collect affected clusters
    affected = set()
    for lk in changed:
        affected_clusters = STATE.sync_link_to_graph(lk)
        affected.update(affected_clusters)

    # Acknowledge message processing
    SYNC.acknowledge_message(msg_ctx.msg_id)

    if affected:
        _incremental_retry(affected)


CC_LIST = []  # 主动连接的 CC 列表，如需主动连接可填: [("127.0.0.1", 9000), ("127.0.0.1", 9001)]

def _register_cluster_conn(cluster_id: int, conn):
    """Register cluster connection - delegated to SYNC"""
    SYNC.register_connection(cluster_id, conn)
    print(f"[AC] Registered connection for cluster {cluster_id}")

def _unregister_conn(conn):
    """Unregister connection - delegated to SYNC"""
    cluster_id = SYNC.unregister_connection(conn)
    if cluster_id is not None:
        print(f"[AC] Unregistered connection for cluster {cluster_id}")
    return cluster_id

def _drain_pending_if_possible():
    """Process pending requests - delegated to STATE"""
    def processor(src, dst, match):
        return _compute_and_distribute_flow(src, dst, match)
    
    processed = STATE.process_pending_requests(processor)
    remaining = STATE.get_pending_count()
    
    if remaining > 0:
        print(f"[AC] Processed {processed} requests, {remaining} remaining")


def handle_flow_request(conn, req):
    """Handle flow request with synchronization"""
    src = int(req.src_cluster)
    dst = int(req.dst_cluster)
    mf = dict(req.match_fields)
    print(f"[AC] Calculating path: Cluster {src} → Cluster {dst}")
    print(f"[AC] Match fields: {mf}")
    
    # Record activity
    SYNC.record_message(src)
    
    # Register connection if not already known
    if SYNC.get_cluster_id(conn) is None:
        _register_cluster_conn(src, conn)
    
    # Try to compute and distribute flow
    if not _compute_and_distribute_flow(src, dst, mf):
        STATE.add_pending_request(conn, src, dst, mf)
        print(f"[AC] No path yet for {src}->{dst}, request pending")


def update_topology_with_conn(conn, topo_msg):
    """Update topology with synchronization"""
    cid = int(topo_msg.cluster_id)
    _register_cluster_conn(cid, conn)
    
    # Record activity
    SYNC.record_message(cid)
    
    # Update state through thread-safe manager
    cid, boundaries, changed = STATE.update_topology(topo_msg)
    print(f"[AC] Boundaries[{cid}] -> {boundaries}")
    
    # Boundary change triggers retry
    if changed:
        _incremental_retry({cid})

def _incremental_retry(affected_clusters: set[int]):
    """Retry pending requests for affected clusters"""
    def processor(src, dst, match):
        return _compute_and_distribute_flow(src, dst, match)
    
    processed = STATE.process_pending_requests(processor, filter_clusters=affected_clusters)
    remaining = STATE.get_pending_count()
    
    if processed > 0 or remaining > 0:
        print(f"[AC] Incremental retry: processed {processed}, {remaining} remaining")


def handle_envelope(conn, envelope):
    """Handle incoming envelope with heartbeat support"""
    t = envelope.type
    if t == message_pb2.Envelope.HELLO:
        nid = envelope.hello.node_id
        if nid.startswith("CC-"):
            try:
                cid = int(nid.split("-")[1])
                _register_cluster_conn(cid, conn)
                # Record heartbeat on HELLO
                SYNC.record_heartbeat(cid)
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
        cluster_edges = STATE.get_cluster_edges()
        if cluster_edges:
            edges = sorted(list(cluster_edges))
            print(f"[AC] Cluster edges: {edges}")
        else:
            print("[AC] Cluster edges: []")
    elif t == message_pb2.Envelope.FLOW_REQUEST:
        handle_flow_request(conn, envelope.flow_request)
    elif t == message_pb2.Envelope.KEEPALIVE:
        # Extract cluster_id from connection mapping
        cid = SYNC.get_cluster_id(conn)
        if cid is not None:
            SYNC.record_heartbeat(cid)
            print(f"[AC] KEEPALIVE from cluster {cid}")
        else:
            print("[AC] KEEPALIVE from unknown cluster")
    elif t == message_pb2.Envelope.INTERCLUSTER_LINK_METRICS:
        met = envelope.intercluster_link_metrics
        SYNC.record_message(met.cluster_id)
        affected = set()
        for entry in met.metrics:
            lk = entry.link_key
            # Get clusters from link endpoints
            cluster_ids = STATE.get_link_clusters(lk)
            if len(cluster_ids) >= 2:
                a, b = sorted(list(cluster_ids))[:2]
                STATE.update_edge_metric(a, b,
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
    """Compute and distribute flow with synchronization"""
    # Calculate path using thread-safe state
    path = STATE.calculate_path(src, dst, ROUTING_POLICY)
    if not path:
        return False

    # Build segments for intermediate hops
    segments = None
    try:
        segments = STATE.build_segments(path)
    except Exception:
        # Fallback: empty segments for all clusters
        segments = []

    # Send FlowReply to ALL clusters in the path, not just those with segments
    # Each cluster needs to know the full path to install appropriate flows
    ok_any = False
    for cid in path:
        # Get connection from SYNC
        conn = SYNC.get_connection(cid)
        if not conn:
            print(f"[AC] No active connection for cluster {cid}, skip")
            continue
        
        # Check if cluster is active
        if not SYNC.is_cluster_active(cid):
            print(f"[AC] Cluster {cid} is inactive, skip")
            continue
        
        reply = message_pb2.FlowReply()
        reply.path.extend([str(x) for x in path])
        reply.match_fields.update(match_fields)
        
        # Find segment for this cluster (if exists)
        seg_for_cluster = None
        for seg in segments:
            if int(seg["cluster_id"]) == cid:
                seg_for_cluster = seg
                break
        
        # Add segment info (empty if no specific segment)
        new_seg = reply.segments.add()
        new_seg.cluster_id = cid
        if seg_for_cluster:
            new_seg.ingress_border = seg_for_cluster.get("ingress_border", "")
            new_seg.egress_border = seg_for_cluster.get("egress_border", "")
            new_seg.tunnel_id = seg_for_cluster.get("tunnel_id", "")
        else:
            new_seg.ingress_border = ""
            new_seg.egress_border = ""
            new_seg.tunnel_id = ""
        
        try:
            data = message.encode_envelope(message_pb2.Envelope.FLOW_REPLY, reply)
            network.send_message(conn, data)
            print(f"[AC] FLOW_REPLY sent to cluster {cid} for path {path}")
            ok_any = True
        except Exception as e:
            print(f"[AC] Send to cluster {cid} failed: {e}")
            # 连接可能失效，移除映射，留待下一次重算
            _unregister_conn(conn)
    return ok_any


def run_ac(port=10000):
    """Run AC with monitoring and statistics"""
    # Set up timeout/recovery callbacks
    def on_timeout(cid):
        print(f"[AC] *** Cluster {cid} TIMEOUT detected ***")
        # Could trigger failover or alerts here
    
    def on_recovery(cid):
        print(f"[AC] *** Cluster {cid} RECOVERED ***")
        # Retry pending requests for recovered cluster
        _incremental_retry({cid})
    
    SYNC.set_timeout_callback(on_timeout)
    SYNC.set_recovery_callback(on_recovery)
    
    # Print statistics periodically
    def stats_loop():
        while True:
            time.sleep(30)
            sync_stats = SYNC.get_stats()
            state_stats = STATE.get_stats()
            print(f"[AC] Stats - Sync: {sync_stats}, State: {state_stats}")
    
    threading.Thread(target=stats_loop, name="stats-loop", daemon=True).start()
    
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

