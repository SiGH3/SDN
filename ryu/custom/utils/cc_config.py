import os, sys, re
from typing import Dict, List, Tuple

def parse_user_flags(conf_user_flags: str = "") -> Dict[str, str]:
    raw = conf_user_flags or ""
    if not raw:
        for a in sys.argv:
            if a.startswith("--user-flags="):
                raw = a.split("=", 1)[1]
                break
    if not raw:
        env_keys = ["CLUSTER_ID","DST_CLUSTER","DST_CLUSTERS","AC_HOST","AC_PORT",
                    "BOUNDARY_SWITCH","BOUNDARY_SWITCHES","PORT_CAPACITY_BPS",
                    "LINKS","LINK_KEY"]
        parts = []
        for k in env_keys:
            v = os.getenv(k)
            if v is not None:
                parts.append(f"{k.lower()}={v}")
        raw = ",".join(parts)
    print(f"[CC] raw user_flags='{raw}'")

    # 逗号续接支持：cluster_id=1,boundary_switches=br1,br2
    flags: Dict[str,str] = {}
    cur_key = None
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            k, v = token.split("=", 1)
            k = k.strip(); v = v.strip()
            flags[k] = v
            cur_key = k
        else:
            if cur_key and cur_key in flags:
                flags[cur_key] += f",{token}"
    return flags

def norm_boundary_name(name: str, cluster_id: int) -> str:
    if name.startswith("br"):
        return name
    if re.fullmatch(r"c\d+-b\d+", name):
        return name
    return name

def build_topology_config(flags: Dict[str,str]) -> Dict:
    cid = int(flags.get("cluster_id", 1))
    ac_host = flags.get("ac_host", "127.0.0.1")
    ac_port = int(flags.get("ac_port", 10000))
    port_capacity_bps = float(flags.get("port_capacity_bps", 1_000_000_000))
    if "dst_clusters" in flags:
        dst_clusters = [int(x) for x in flags["dst_clusters"].replace(",", ";").split(";") if x.strip()]
    else:
        dst_clusters = [int(flags.get("dst_cluster", 2))]

    bs_raw = flags.get("boundary_switches") or flags.get("boundary_switch", f"br{cid}")
    boundary_switches: List[str] = []
    for item in bs_raw.split(","):
        nm = norm_boundary_name(item.strip(), cid)
        if nm:
            boundary_switches.append(nm)
    if not boundary_switches:
        boundary_switches = [f"br{cid}"]

    # 静态链路（可为空；自动发现后可不用）
    link_defs: List[Tuple[str, str, int]] = []
    links_raw = flags.get("links", "")
    for item in links_raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        sw, lk = item.split(":", 1)
        sw = norm_boundary_name(sw.strip(), cid)
        m = re.fullmatch(r"c(\d+)-b(\d+)", sw)
        pno = int(m.group(2)) if m else 1
        link_defs.append((sw, lk.strip(), pno))
    if not link_defs and "link_key" in flags:
        sw = boundary_switches[0]
        m = re.fullmatch(r"c(\d+)-b(\d+)", sw)
        pno = int(m.group(2)) if m else 1
        link_defs.append((sw, flags["link_key"], pno))

    return {
        "cluster_id": cid,
        "ac_host": ac_host,
        "ac_port": ac_port,
        "port_capacity_bps": port_capacity_bps,
        "dst_clusters": dst_clusters,
        "boundary_switches": boundary_switches,
        "link_defs": link_defs,
    }