# Cross-Cluster ARP Proxy Testing Guide

## Overview

This guide explains how to test cross-cluster communication with ARP proxy support in your SDN deployment. The ARP proxy enables hosts in different clusters to communicate by resolving cross-cluster ARP requests automatically.

## Architecture

**Setup:**
- **AC + CC1 + CC2**: All on machine 10.255.0.1/24
- **OVS1** (10.255.0.2): Cluster 1 boundary switch with host h1 (10.10.0.10)
- **OVS2** (10.255.1.2): Cluster 2 boundary switch with host h2 (10.10.0.2)
- **Control Plane**: Ad-hoc networks CtrlNet1 (channel 1) and CtrlNet2 (channel 6)
- **Data Plane**: Ad-hoc network DataNet (channel 11) with GRE tunnels

## How ARP Proxy Works

### Problem
When h2 (10.10.0.2) tries to ping h1 (10.10.0.10):
1. h2 sends ARP request: "Who has 10.10.0.10?"
2. Without ARP proxy, this broadcast stays in cluster 2
3. h2 never learns h1's MAC address
4. ICMP packets are never sent

### Solution
With ARP proxy enabled:
1. **CC2 intercepts cross-cluster ARP requests**
   - Detects that 10.10.0.10 belongs to cluster 1
   - Generates an ARP reply with a **virtual gateway MAC** (02:00:00:00:0c:01)

2. **h2 gets the virtual MAC**
   - h2 now knows "10.10.0.10 is at 02:00:00:00:0c:01"
   - h2 sends IP packets with dst_mac=02:00:00:00:0c:01

3. **CC2 installs forwarding flows**
   - Matches on dst_ip=10.10.0.10 AND dst_mac=02:00:00:00:0c:01
   - Forwards to boundary port (GRE tunnel to cluster 1)

4. **CC1 receives and forwards**
   - AC has provided routing path [2, 1]
   - CC1 installs flows to forward to local host h1

## Configuration

### IP to Cluster Mapping

**IMPORTANT**: The default heuristic in `_get_cluster_from_ip()` assumes:
- Last octet >= 10: Cluster 1 (e.g., 10.10.0.10, 10.10.0.20, etc.)
- Last octet 1-9: Cluster 2 (e.g., 10.10.0.2, 10.10.0.5, etc.)

**For your specific topology**, you should customize the mapping in `my_simple_switch_13.py`:

```python
def _get_cluster_from_ip(self, ip_addr):
    # Explicit mapping for your hosts
    ip_map = {
        "10.10.0.10": 1,  # h1 in cluster 1
        "10.10.0.20": 2,  # h2 in cluster 2  
        # Add more hosts here
    }
    if ip_addr in ip_map:
        return ip_map[ip_addr]
    
    # Fallback heuristic
    parts = ip_addr.split('.')
    if len(parts) == 4:
        last_octet = int(parts[3])
        if last_octet >= 10:
            return 1
        elif last_octet >= 1:
            return 2
    return None
```

For custom mappings, modify `_get_cluster_from_ip()` in `my_simple_switch_13.py`:

```python
def _get_cluster_from_ip(self, ip_addr):
    # Custom mapping for your topology
    if ip_addr == "10.10.0.10":
        return 1  # h1 in cluster 1
    elif ip_addr == "10.10.0.2":
        return 2  # h2 in cluster 2
    # ... add more mappings as needed
```

### Virtual Gateway MACs

Each cluster gets a unique virtual gateway MAC:
- Cluster 1: `02:00:00:00:0c:01`
- Cluster 2: `02:00:00:00:0c:02`
- Cluster N: `02:00:00:00:0c:0N`

These MACs are used as ARP proxy responses for cross-cluster traffic.

## Testing Steps

### 1. Start Controllers

**Terminal 1 - AC:**
```bash
cd ~/SDN
export PYTHONPATH=~/SDN:$PYTHONPATH
python3 -m ryu.custom.controller.test_ac_controller 10000
```

**Terminal 2 - CC1:**
```bash
export CLUSTER_ID=1 AC_HOST=127.0.0.1 AC_PORT=10000 LINK_REANNOUNCE_SEC=5
ryu-manager --observe-links --ofp-tcp-listen-port 6653 \
  --ofp-listen-host 10.255.1.1 \
  ryu.custom.my_simple_switch_13 ryu.topology.switches
```

**Terminal 3 - CC2:**
```bash
export CLUSTER_ID=2 AC_HOST=127.0.0.1 AC_PORT=10000 LINK_REANNOUNCE_SEC=5
ryu-manager --observe-links --ofp-tcp-listen-port 6654 \
  --ofp-listen-host 10.255.2.1 \
  ryu.custom.my_simple_switch_13 ryu.topology.switches
```

### 2. Verify Topology Discovery

Check AC logs for:
```
[AC] Cluster edges: [(1, 2)]
[AC] LINK_EP snapshot shows GRE tunnel links
```

Check CC logs for:
```
[CC] LLDP跨域邻居: local=dpid:XXX peer_dpid=YYY
[CC] auto-detected boundary switch dpid:XXX
```

### 3. Test Cross-Cluster Ping

**On OVS2 (cluster 2), ping h1 in cluster 1:**
```bash
sudo ip netns exec h2 ping 10.10.0.10 -c 5
```

### 4. Expected Log Output

**CC2 (Source Cluster):**
```
[CC] ARP Request: who has 10.10.0.10? Tell 10.10.0.2 (76:b1:c8:5f:b0:f8)
[CC] ARP: src_cluster=2, dst_cluster=1, my_cluster=2
[CC] *** CROSS-CLUSTER ARP DETECTED ***
[CC]     ARP Request from cluster 2 for IP 10.10.0.10 in cluster 1
[CC]     Generating ARP proxy reply with virtual gateway MAC
[CC] ✓ Sent ARP Reply: 10.10.0.10 is at 02:00:00:00:0c:01
[CC] ✓ Installed cross-cluster rewrite flow: dst_ip=10.10.0.10, dst_mac=02:00:00:00:0c:01 -> port=X
[CC] *** CROSS-CLUSTER TRAFFIC DETECTED ***
[CC]     Source: 10.10.0.2 (cluster 2)
[CC]     Destination: 10.10.0.10 (cluster 1)
[CC] ===== SENDING FLOW REQUEST TO AC =====
```

**AC:**
```
[AC] Received FLOW_REQUEST: C2->C1
[AC] Calculating path: Cluster 2 → Cluster 1
[AC] FLOW_REPLY segment sent to cluster 2 for path [2, 1]
[AC] FLOW_REPLY segment sent to cluster 1 for path [2, 1]
```

**CC1 (Destination Cluster):**
```
[CC] ===== RECEIVED FLOW REPLY FROM AC =====
[CC]   Path: ['2', '1']
[CC] ✓ Installed flow on switch dpid=XXX: dst_ip=10.10.0.10 -> port=Y
```

**Result:**
```bash
PING 10.10.0.10 (10.10.0.10) 56(84) bytes of data.
64 bytes from 10.10.0.10: icmp_seq=1 ttl=64 time=5 ms
64 bytes from 10.10.0.10: icmp_seq=2 ttl=64 time=3 ms
64 bytes from 10.10.0.10: icmp_seq=3 ttl=64 time=4 ms
```

## Troubleshooting

### Issue: ARP proxy not triggering

**Symptoms:** Still seeing "Unknown local destination ff:ff:ff:ff:ff:ff, flooding"

**Solution:**
1. Check that `_get_cluster_from_ip()` correctly identifies the clusters
2. Verify the IP addresses match your topology
3. Add debug logging to see what cluster IDs are detected

### Issue: ARP reply sent but ping still fails

**Symptoms:** ARP proxy works but no ICMP replies

**Causes:**
1. **No GRE tunnel connection** - verify DataNet ad-hoc network is up
2. **Missing boundary port** - check `_pending_links` is populated
3. **Flow installation failed** - check for OpenFlow errors in CC logs

**Debug:**
```bash
# Check flows on OVS
sudo ovs-ofctl -O OpenFlow13 dump-flows br1

# Should see flows like:
# priority=20,ip,dl_dst=02:00:00:00:0c:01,nw_dst=10.10.0.10 actions=output:X
```

### Issue: High packet loss (> 50%)

**Symptoms:** Ping succeeds but with >50% loss

**Causes:**
1. Wireless interfaces added to OVS bridges causing interference
2. GRE tunnel packet size exceeding MTU

**Solution:**
1. Remove wireless interfaces from OVS bridges (keep only GRE tunnels)
2. Reduce MTU: `sudo ip link set gre12 mtu 1400`

### Issue: Bidirectional communication fails

**Symptoms:** h2 → h1 works, but h1 → h2 fails

**Solution:**
Both clusters need to handle ARP proxy. Test from both directions:
```bash
# From h2 to h1
sudo ip netns exec h2 ping 10.10.0.10

# From h1 to h2  
sudo ip netns exec h1 ping 10.10.0.2
```

## Advanced Configuration

### Custom IP-to-Cluster Mapping

For complex topologies with non-standard IP addressing:

```python
# In my_simple_switch_13.py
def _get_cluster_from_ip(self, ip_addr):
    # Define explicit mappings
    ip_to_cluster_map = {
        "10.10.0.10": 1,
        "10.10.0.11": 1,
        "10.10.0.2": 2,
        "10.10.0.3": 2,
        # Add more as needed
    }
    
    if ip_addr in ip_to_cluster_map:
        return ip_to_cluster_map[ip_addr]
    
    # Fallback to learned mappings
    if ip_addr in self._ip_to_cluster:
        return self._ip_to_cluster[ip_addr]
    
    return None
```

### Performance Tuning

**Flow Timeouts:**
```python
# In _install_cross_cluster_rewrite_flow()
idle_timeout=60,   # Increase for long-lived connections
hard_timeout=120,  # Increase for stable routes
```

**ARP Cache:**
```bash
# On hosts, increase ARP cache timeout to reduce re-ARP requests
sudo ip netns exec h2 ip neigh flush all
sudo ip netns exec h2 sysctl -w net.ipv4.neigh.default.gc_stale_time=600
```

## Verification Commands

**Check ARP table on host:**
```bash
sudo ip netns exec h2 ip neigh show
# Should show: 10.10.0.10 lladdr 02:00:00:00:0c:01 REACHABLE
```

**Check installed flows:**
```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows br2 | grep "nw_dst=10.10.0.10"
```

**Monitor packet flow:**
```bash
sudo ovs-appctl ofproto/trace br2 \
  in_port=h2-veth,icmp,nw_src=10.10.0.2,nw_dst=10.10.0.10
```

## Next Steps

With ARP proxy working, you can:

1. **Add more clusters** - the system scales automatically
2. **Implement QoS** - prioritize cross-cluster traffic
3. **Add load balancing** - distribute traffic across multiple GRE tunnels
4. **Enable fast failover** - automatic rerouting on link failures
5. **Integration with RL routing** - use learned paths instead of shortest-path

## References

- Main implementation: `ryu/custom/my_simple_switch_13.py`
- Protocol definitions: `ryu/custom/protocol/message.proto`
- AC controller: `ryu/custom/controller/test_ac_controller.py`
