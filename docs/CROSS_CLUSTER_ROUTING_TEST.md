# Cross-Cluster Flow Routing Test Guide

## Overview
This guide explains how to test the cross-cluster flow routing functionality where:
1. CC detects cross-cluster traffic and sends FlowRequest to AC
2. AC calculates the shortest path at cluster level
3. AC sends FlowReply with path segments to all involved CCs
4. Each CC installs OpenFlow rules for the traffic

## Architecture

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│  Cluster 1   │──────│  Cluster 2   │──────│  Cluster 3   │
│  (10.0.1.0/24)│      │ (10.0.2.0/24)│      │ (10.0.3.0/24)│
│      CC1     │      │      CC2     │      │      CC3     │
└──────┬───────┘      └──────┬───────┘      └──────┬───────┘
       │                     │                     │
       └─────────────────────┴─────────────────────┘
                             │
                      ┌──────▼───────┐
                      │      AC      │
                      │  (Port 10000)│
                      └──────────────┘
```

## Prerequisites

1. **Start AC Controller:**
```bash
cd ~/SDN
export PYTHONPATH=~/SDN:$PYTHONPATH
python3 -m ryu.custom.controller.test_ac_controller 10000
```

2. **Start CC Controllers:**

Terminal 1 (CC1):
```bash
export CLUSTER_ID=1 AC_HOST=127.0.0.1 AC_PORT=10000 LINK_REANNOUNCE_SEC=5
ryu-manager --observe-links --ofp-tcp-listen-port 6633 ryu.custom.my_simple_switch_13 ryu.topology.switches
```

Terminal 2 (CC2):
```bash
export CLUSTER_ID=2 AC_HOST=127.0.0.1 AC_PORT=10000 LINK_REANNOUNCE_SEC=5
ryu-manager --observe-links --ofp-tcp-listen-port 6654 ryu.custom.my_simple_switch_13 ryu.topology.switches
```

Terminal 3 (CC3):
```bash
export CLUSTER_ID=3 AC_HOST=127.0.0.1 AC_PORT=10000 LINK_REANNOUNCE_SEC=5
ryu-manager --observe-links --ofp-tcp-listen-port 6664 ryu.custom.my_simple_switch_13 ryu.topology.switches
```

3. **Wait for topology discovery:**
Look for these messages in AC logs:
```
[AC] Cluster edges: [(1, 2), (1, 3), (2, 3)]
```

## Test Case 1: Direct Path (C1 → C3)

### Network Setup
- Host h1 in C1 with IP: 10.0.1.10
- Host h3 in C3 with IP: 10.0.3.10

### Test Steps

1. **Generate cross-cluster traffic:**
```bash
# From h1 in Cluster 1
ping 10.0.3.10
```

2. **Expected CC1 Logs:**
```
[CC] Learn MAC XX:XX:XX:XX:XX:XX on dpid=YYYY port=Z
[CC] Cross-cluster IP packet: 10.0.1.10 -> 10.0.3.10
[CC] Sending FlowRequest: C1->C3, src=10.0.1.10, dst=10.0.3.10, msg_id=N
```

3. **Expected AC Logs:**
```
[AC] Calculating path: Cluster 1 → Cluster 3
[AC] Match fields: {'src_ip': '10.0.1.10', 'dst_ip': '10.0.3.10', 'src_mac': '...', 'dst_mac': '...'}
[AC] FLOW_REPLY segment sent to cluster 1 for path [1, 3]
[AC] FLOW_REPLY segment sent to cluster 3 for path [1, 3]
```

4. **Expected CC1 Logs (after receiving reply):**
```
[CC] FLOW_REPLY path=['1', '3'] segments=1 match={'src_ip': '10.0.1.10', 'dst_ip': '10.0.3.10', ...}
[CC] Installing flows for path: ['1', '3']
[CC] Found boundary port X on dpid=YYYY for cross-cluster traffic
[CC] Installed flow on dpid=YYYY: dst_ip=10.0.3.10 -> port=X
```

5. **Expected CC3 Logs (after receiving reply):**
```
[CC] FLOW_REPLY path=['1', '3'] segments=1 match={'src_ip': '10.0.1.10', 'dst_ip': '10.0.3.10', ...}
[CC] Installing flows for path: ['1', '3']
[CC] Installed flow on dpid=ZZZZ: dst_ip=10.0.3.10 -> port=Y
```

6. **Verify flow installation:**
```bash
# On switches in C1
ovs-ofctl dump-flows s1 | grep "nw_dst=10.0.3.10"

# On switches in C3
ovs-ofctl dump-flows s3 | grep "nw_dst=10.0.3.10"
```

Expected output:
```
priority=10,ip,nw_dst=10.0.3.10 actions=output:PORT
```

## Test Case 2: Multi-Hop Path (C1 → C2 → C3)

If you disconnect the direct C1-C3 link, traffic should route through C2.

### Simulate link failure:
```bash
# Disconnect C1-C3 boundary switches (if physical)
# Or modify topology to remove C1-C3 link
```

### Expected Behavior

1. **AC calculates alternate path:**
```
[AC] Calculating path: Cluster 1 → Cluster 3
[AC] FLOW_REPLY segment sent to cluster 1 for path [1, 2, 3]
[AC] FLOW_REPLY segment sent to cluster 2 for path [1, 2, 3]
[AC] FLOW_REPLY segment sent to cluster 3 for path [1, 2, 3]
```

2. **All three CCs receive and install flows:**
- C1: Forward to boundary switch connected to C2
- C2: Forward from C1 boundary to C3 boundary
- C3: Forward to local host

## Test Case 3: Bidirectional Communication

Test return traffic (C3 → C1):

```bash
# From h3 in Cluster 3
ping 10.0.1.10
```

Expected: Similar FlowRequest/FlowReply exchange for reverse direction.

## Debugging

### Check cluster topology:
Look for in AC logs:
```
[AC] Cluster edges: [(1, 2), (1, 3), (2, 3)]
```

### Check boundary switches:
Look for in CC logs:
```
[CC] auto-detected boundary switch dpid:XXXX
[AC] Boundaries[1] -> ['dpid:XXXX', 'dpid:YYYY']
```

### Check flow request rate limiting:
FlowRequests are rate-limited to 1 per 5 seconds per (src, dst) pair to avoid spam.

### Common Issues

1. **No FlowRequest sent:**
   - Check if destination IP format is 10.0.X.Y where X is cluster ID
   - Verify source host is learned locally (check "Learn MAC" logs)

2. **FlowReply received but no flows installed:**
   - Check if boundary ports are discovered
   - Look for "Found boundary port" logs
   - If no boundary port found, flows will use FLOOD

3. **Ping fails after flow installation:**
   - Verify flows on all switches in path: `ovs-ofctl dump-flows sX`
   - Check if flows have correct match (dst_ip) and action (output port)
   - Flows have 30s idle timeout, 60s hard timeout

## Advanced: Custom IP-to-Cluster Mapping

The current implementation uses a simple mapping:
```python
# IP format: 10.0.X.Y where X = cluster_id
dst_cluster = int(dst_ip.split('.')[2])
```

For custom mappings, modify `_request_cross_cluster_path` in `my_simple_switch_13.py`:

```python
def _request_cross_cluster_path(self, src_ip, dst_ip, src_mac, dst_mac):
    # Custom mapping table
    ip_to_cluster = {
        '10.0.1.0/24': 1,
        '10.0.2.0/24': 2,
        '10.0.3.0/24': 3,
        '192.168.1.0/24': 1,
        '192.168.2.0/24': 2,
    }
    
    # Lookup destination cluster
    dst_cluster = lookup_cluster_by_ip(dst_ip, ip_to_cluster)
    ...
```

## Performance Considerations

1. **Flow timeout:** Idle timeout is 30s, hard timeout is 60s
   - Adjust in `_install_flow_from_reply` if needed
   
2. **Request rate limiting:** 5 seconds between requests for same (src, dst)
   - Adjust in `_request_cross_cluster_path` if needed

3. **Flow priority:** Currently set to 10
   - Adjust if you have other flows with conflicting priorities

## Next Steps

After basic testing works, you can extend to:

1. **Segment-based routing:** Use AC's segment information for precise port selection
2. **QoS support:** Add flow priorities based on traffic type
3. **Load balancing:** AC can provide multiple paths, CC chooses based on load
4. **Dynamic rerouting:** When links fail, AC recalculates and sends new FlowReplies
5. **Reinforcement learning:** Replace shortest-path with RL-based routing

## Monitoring

Watch all 4 terminals (AC + 3 CCs) simultaneously to see the complete message flow:
1. Host generates traffic
2. CC detects and sends FlowRequest
3. AC computes path
4. AC sends FlowReplies
5. CCs install flows
6. Subsequent packets flow directly (no more packet-ins)
