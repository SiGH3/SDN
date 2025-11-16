from collections import defaultdict

# 选路策略（可按需调整）
ROUTING_POLICY = {
    "metric": "composite",   # hops | latency | load | composite
    "alpha": {               # composite 权重
        "hops": 1.0,
        "latency": 0.0,
        "load": 0.0,
    },
    "max_hops": 8,           # 限制最大跳数
    "max_paths": 128,        # 限制候选路径数
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
        paths = self.enumerate_paths(src, dst, policy.get("max_hops", 8), policy.get("max_paths", 128))
        if not paths:
            return []
        scored = [(self.path_cost(p, policy), p) for p in paths]
        scored.sort(key=lambda x: (x[0][0], x[0][1]))
        return scored[0][1]

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
