from collections import defaultdict
import heapq

# 选路策略（可按需调整）
ROUTING_POLICY = {
    "metric": "composite",   # hops | latency | load | composite | dijkstra
    "algorithm": "dijkstra",  # dijkstra | cluster_aware | dfs
    "alpha": {               # composite 权重
        "hops": 1.0,
        "latency": 0.0,
        "load": 0.0,
    },
    "max_hops": 8,           # 限制最大跳数
    "max_paths": 128,        # 限制候选路径数
    "use_intra_cluster_cost": False,  # 是否使用集群内部代价
}

class ClusterGraph:
    def __init__(self):
        # cid -> {boundary_switch}
        self.cluster_boundaries = defaultdict(set)
        # link_key -> [(cid, switch_id, port_no)]
        self.link_index = defaultdict(list)
        # {(a,b)}  a<b
        self.cluster_edges = set()
        # (a,b) a<b -> {"weight":1.0, "latency":1.0, "load":0.0}
        self.edge_metrics = {}
        # Intra-cluster costs: cid -> {"ingress": dpid, "egress": dpid, "cost": float}
        # For cluster-aware weighted routing
        self.intra_cluster_costs = defaultdict(lambda: {"cost": 0.0})

    def update_topology(self, topo_msg):
        cid = int(topo_msg.cluster_id)
        before = len(self.cluster_boundaries[cid])
        for sw in topo_msg.boundary_switches:
            self.cluster_boundaries[cid].add(sw)
        after = len(self.cluster_boundaries[cid])
        boundaries = sorted(self.cluster_boundaries[cid])
        changed = (after != before)
        return cid, boundaries, changed

    def update_links(self, link_msg):
        cid = int(link_msg.cluster_id)
        changed = False
        for le in link_msg.links:
            key = le.link_key
            entry = (cid, le.switch_id, int(le.port_no))
            if entry not in self.link_index[key]:
                self.link_index[key].append(entry)
            # 两端来自不同集群则形成域间边
            cids = {e[0] for e in self.link_index[key]}
            if len(cids) >= 2:
                a, b = sorted(list(cids))[:2]
                edge = (a, b)
                if edge not in self.cluster_edges:
                    self.cluster_edges.add(edge)
                    self.edge_metrics.setdefault(edge, {"weight": 1.0, "latency": 1.0, "load": 0.0})
                    changed = True
        edges_sorted = sorted(self.cluster_edges)
        return edges_sorted, changed

    def add_cluster(self, cid: int):
        """确保集群节点存在（幺等）。"""
        cid = int(cid)
        # 访问 cluster_boundaries 会自动创建默认集合
        _ = self.cluster_boundaries[cid]
        return True

    def add_edge(self, a: int, b: int, link_key: str = None):
        """显式向 graph 中添加一条边（a,b）。"""
        a = int(a); b = int(b)
        if a == b:
            return False
        e = (min(a, b), max(a, b))
        if e in self.cluster_edges:
            return False
        self.cluster_edges.add(e)
        # 初始化度量（若已有 link_key 可以更具体）
        self.edge_metrics.setdefault(e, {"weight": 1.0, "latency": 1.0, "load": 0.0})
        # 将 link_key 映射到 link_index 以便回溯（非必须）
        if link_key:
            # 保证 link_index 有该 key 并记下端点（用于后续基于 link_key 的查询）
            if link_key not in self.link_index:
                self.link_index[link_key] = []
            # 不刻意添加 cluster->switch mapping 这里仅保证存在
        return True

    def update_edge_metric(self, a: int, b: int, latency: float = None, load: float = None, weight: float = None):
        a = int(a); b = int(b)
        e = (min(a, b), max(a, b))
        m = self.edge_metrics.setdefault(e, {"weight": 1.0, "latency": 1.0, "load": 0.0})
        if latency is not None:
            m["latency"] = float(latency)
        if load is not None:
            m["load"] = float(load)
        if weight is not None:
            m["weight"] = float(weight)
        self.edge_metrics[e] = m
        return True

    def calculate_path(self, src: int, dst: int, policy: dict = None):
        """兼容旧接口：返回 best_path 的结果。"""
        if policy is None:
            policy = ROUTING_POLICY
        return self.best_path(src, dst, policy)
    
    def enumerate_paths(self, src: int, dst: int, max_hops: int, max_paths: int):
        if src == dst:
            return [[src]]
        adj = defaultdict(set)
        for a, b in self.cluster_edges:
            adj[a].add(b); adj[b].add(a)
        if src not in adj or dst not in adj:
            return []
        paths, path, visited = [], [src], {src}

        def dfs(u: int):
            if len(paths) >= max_paths: return
            if len(path) - 1 > max_hops: return
            if u == dst:
                paths.append(list(path)); return
            for v in adj[u]:
                if v in visited: continue
                visited.add(v); path.append(v)
                dfs(v)
                path.pop(); visited.remove(v)

        dfs(src)
        return paths

    def path_cost(self, p, policy: dict):
        hops = len(p) - 1
        if hops <= 0:
            return (float("inf"), hops)

        def edge_sum(key: str):
            s = 0.0
            for i in range(len(p) - 1):
                a, b = p[i], p[i + 1]
                e = (min(a, b), max(a, b))
                m = self.edge_metrics.get(e, {"weight": 1.0, "latency": 1.0, "load": 0.0})
                s += float(m.get(key, 0.0))
            return s

        metric = policy.get("metric", "composite")
        if metric == "hops":
            primary = float(hops)
        elif metric == "latency":
            primary = edge_sum("latency")
        elif metric == "load":
            primary = edge_sum("load")
        else:
            alpha = policy.get("alpha", {})
            primary = (
                alpha.get("hops", 1.0) * float(hops)
                + alpha.get("latency", 0.0) * edge_sum("latency")
                + alpha.get("load", 0.0) * edge_sum("load")
            )
        return (primary, hops)

    def best_path(self, src: int, dst: int, policy: dict):
        """
        Select routing algorithm based on policy.
        Supports: 'dijkstra' (baseline), 'cluster_aware' (improved), 'dfs' (legacy)
        """
        algorithm = policy.get("algorithm", "dijkstra")
        
        if algorithm == "dijkstra":
            # Baseline: Cluster-level Dijkstra with uniform weights
            return self.dijkstra_shortest_path(src, dst, policy)
        elif algorithm == "cluster_aware":
            # Improved: Cluster-aware weighted Dijkstra
            return self.cluster_aware_weighted_path(src, dst, policy)
        elif algorithm == "dfs":
            # Legacy: DFS enumeration with scoring
            paths = self.enumerate_paths(src, dst, policy.get("max_hops", 8), policy.get("max_paths", 128))
            if not paths:
                return []
            scored = [(self.path_cost(p, policy), p) for p in paths]
            scored.sort(key=lambda x: (x[0][0], x[0][1]))
            return scored[0][1]
        else:
            # Default to Dijkstra
            return self.dijkstra_shortest_path(src, dst, policy)

    def dijkstra_shortest_path(self, src: int, dst: int, policy: dict):
        """
        Algorithm 1: Cluster-Level Shortest Path (Baseline)
        
        Uses Dijkstra's algorithm to find shortest path in cluster-level graph.
        Edge weights are uniform (hop count = 1 per inter-cluster link).
        
        Input:
            src: Source cluster ID
            dst: Destination cluster ID
            policy: Routing policy dict
        
        Output:
            path: List of cluster IDs from src to dst, or [] if no path exists
        """
        if src == dst:
            return [src]
        
        # Build adjacency list
        adj = defaultdict(set)
        for a, b in self.cluster_edges:
            adj[a].add(b)
            adj[b].add(a)
        
        if src not in adj:
            # Source cluster has no edges
            return []
        
        # Initialize distance and predecessor
        distance = {src: 0}
        predecessor = {}
        
        # Priority queue: (distance, cluster_id)
        pq = [(0, src)]
        visited = set()
        
        while pq:
            dist_u, u = heapq.heappop(pq)
            
            if u in visited:
                continue
            visited.add(u)
            
            # Found destination
            if u == dst:
                break
            
            # Explore neighbors
            for v in adj[u]:
                if v in visited:
                    continue
                
                # Edge weight = 1 (uniform hop count)
                new_dist = dist_u + 1
                
                if v not in distance or new_dist < distance[v]:
                    distance[v] = new_dist
                    predecessor[v] = u
                    heapq.heappush(pq, (new_dist, v))
        
        # Reconstruct path
        if dst not in predecessor and dst != src:
            return []  # No path found
        
        path = []
        current = dst
        while current in predecessor:
            path.append(current)
            current = predecessor[current]
        path.append(src)
        path.reverse()
        
        return path
    
    def cluster_aware_weighted_path(self, src: int, dst: int, policy: dict):
        """
        Algorithm 3: Cluster-Aware Weighted Path Computation (Improved)
        
        Uses weighted Dijkstra incorporating:
        - Inter-cluster link costs (from edge_metrics)
        - Intra-cluster costs (from CC reports)
        
        Edge weight = w_inter(c_u, c_v) + w_intra(c_u)
        
        Input:
            src: Source cluster ID
            dst: Destination cluster ID
            policy: Routing policy dict
        
        Output:
            path: Optimized cluster path, or [] if no path exists
        """
        if src == dst:
            return [src]
        
        # Build adjacency list
        adj = defaultdict(set)
        for a, b in self.cluster_edges:
            adj[a].add(b)
            adj[b].add(a)
        
        if src not in adj:
            return []
        
        # Initialize distance and predecessor
        distance = {src: 0.0}
        predecessor = {}
        
        # Priority queue: (distance, cluster_id)
        pq = [(0.0, src)]
        visited = set()
        
        use_intra_cost = policy.get("use_intra_cluster_cost", False)
        
        while pq:
            dist_u, u = heapq.heappop(pq)
            
            if u in visited:
                continue
            visited.add(u)
            
            # Found destination
            if u == dst:
                break
            
            # Explore neighbors
            for v in adj[u]:
                if v in visited:
                    continue
                
                # Calculate edge weight
                edge = (min(u, v), max(u, v))
                
                # Inter-cluster link cost
                w_inter = 1.0  # Default uniform weight
                if edge in self.edge_metrics:
                    metrics = self.edge_metrics[edge]
                    # Use policy-specified metric
                    metric_type = policy.get("metric", "hops")
                    if metric_type == "latency":
                        w_inter = float(metrics.get("latency", 1.0))
                    elif metric_type == "load":
                        w_inter = float(metrics.get("load", 1.0))
                    elif metric_type == "composite":
                        alpha = policy.get("alpha", {})
                        w_inter = (
                            alpha.get("hops", 1.0) * 1.0 +  # 1 hop
                            alpha.get("latency", 0.0) * float(metrics.get("latency", 1.0)) +
                            alpha.get("load", 0.0) * float(metrics.get("load", 0.0))
                        )
                    else:
                        w_inter = float(metrics.get("weight", 1.0))
                
                # Intra-cluster cost (from source cluster u)
                w_intra = 0.0
                if use_intra_cost and u in self.intra_cluster_costs:
                    w_intra = float(self.intra_cluster_costs[u].get("cost", 0.0))
                
                # Total edge weight
                edge_weight = w_inter + w_intra
                new_dist = dist_u + edge_weight
                
                if v not in distance or new_dist < distance[v]:
                    distance[v] = new_dist
                    predecessor[v] = u
                    heapq.heappush(pq, (new_dist, v))
        
        # Reconstruct path
        if dst not in predecessor and dst != src:
            return []
        
        path = []
        current = dst
        while current in predecessor:
            path.append(current)
            current = predecessor[current]
        path.append(src)
        path.reverse()
        
        return path
    
    def update_intra_cluster_cost(self, cluster_id: int, cost: float, 
                                  ingress: str = None, egress: str = None):
        """
        Update intra-cluster cost for cluster-aware routing.
        Called by CC to report abstract cost for paths within the cluster.
        
        Input:
            cluster_id: Cluster ID
            cost: Abstract cost (e.g., hop_count, weighted metric)
            ingress: Optional ingress boundary switch
            egress: Optional egress boundary switch
        """
        cluster_id = int(cluster_id)
        self.intra_cluster_costs[cluster_id] = {
            "cost": float(cost),
            "ingress": ingress,
            "egress": egress
        }
        return True

    def build_segments(self, path):
        # 每一跳一个段：在 cluster a 出域到下一跳 cluster b
        segs = []
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            segs.append({
                "cluster_id": a,
                "ingress_border": f"c{a}-b1",
                "egress_border": f"c{b}-b1",
                "tunnel_id": "demo-tni",
            })
        return segs
