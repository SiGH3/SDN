from typing import List, Tuple, Dict
import hashlib

def is_boundary_switch(name: str, cluster_id: int, allowed_prefixes: List[str]) -> bool:
    # 简单规则：显式列表优先，否则允许 c<cluster_id>-bX 或 brX
    if name in allowed_prefixes:
        return True
    if name.startswith(f"c{cluster_id}-b"):
        return True
    if name.startswith("br"):
        # 若你用 br 映射，每集群自己的桥名列表应在 allowed_prefixes 中更可靠
        return True
    return False

def make_link_key(src_sw: str, src_port: int, dst_sw: str, dst_port: int) -> str:
    # 稳定且与方向无关的 key
    a = f"{src_sw}:{src_port}"
    b = f"{dst_sw}:{dst_port}"
    s, t = sorted([a, b])
    h = hashlib.sha1(f"{s}|{t}".encode()).hexdigest()[:12]
    return f"lk-{s}-{t}-{h}"

def build_intercluster_links(cluster_id: int,
                             discovered_links: List[Tuple[str, int, str, int]],
                             boundary_names: List[str]) -> List[Tuple[str, str, int]]:
    """
    输入:
      discovered_links: [(src_sw, src_port_no, dst_sw, dst_port_no), ...]
      boundary_names: 本集群内认为是“边界交换机”的名称列表
    输出:
      [(switch_id, link_key, port_no), ...] 供 CC 上报
    规则:
      - 只保留 src_sw 或 dst_sw 在 boundary_names 内的端点（本集群端）
      - 为每条边生成 link_key；同一边在两个集群各自上报一个端点即可
    """
    out = []
    for ssw, sport, dsw, dport in discovered_links:
        # 取本集群一侧（边界交换机）
        if ssw in boundary_names:
            lk = make_link_key(ssw, sport, dsw, dport)
            out.append((ssw, lk, sport))
        elif dsw in boundary_names:
            lk = make_link_key(ssw, sport, dsw, dport)
            out.append((dsw, lk, dport))
        # 非边界的链路忽略
    return out
