# CC-AC Protocol Interaction Simulation

## Overview

The performance comparison tool now includes comprehensive simulation of the CC-AC (Cluster Controller - Aggregation Controller) protocol message exchange, demonstrating the hierarchical SDN control plane interaction.

## Protocol Message Flow

### Phase 1: CC Metric Collection

**Description:** Each Cluster Controller collects local metrics and inter-cluster link measurements.

**What CC Collects:**
- Cluster internal metrics (average delay, packet loss, queue length)
- Inter-cluster link metrics (delay, loss) for all outgoing links
- Real data from NS-3 simulation files

**Output Example:**
```
Phase 1: CC Metric Collection
→ CC-1 collects local cluster metrics and inter-cluster link measurements
  Collected metrics from 3 cluster(s)
  Measured 6 inter-cluster link(s)
```

### Phase 2: CC Reports Metrics to AC (INTERCLUSTER_LINK_METRICS)

**Description:** Each CC sends INTERCLUSTER_LINK_METRICS message to AC with link metrics.

**Message Structure:**
```
[CC→AC] INTERCLUSTER_LINK_METRICS
  • cluster_id: 1
  • num_links: 2
  • metrics:
    - link_key=C1→C2, latency=17.91ms, loss=0.0406
    - link_key=C1→C3, latency=12.72ms, loss=0.0350
```

**Protocol Definition (from message.proto):**
```protobuf
message InterClusterLinkMetrics {
  uint32 cluster_id = 1;
  message MetricEntry {
    string link_key = 1;
    double latency_ms = 2;
    double load = 3;
    double loss_ratio = 4;
    double avail_bw_mbps = 5;
  }
  repeated MetricEntry metrics = 2;
}
```

**Key Points:**
- Each CC reports its own outgoing links
- AC receives metrics from all CCs
- AC builds complete view of inter-cluster topology
- Maintains hierarchical separation (AC doesn't see cluster internals)

### Phase 3: Cross-Cluster Flow Request (FLOW_REQUEST)

**Description:** When host initiates cross-cluster communication, source CC sends FLOW_REQUEST to AC.

**Trigger:**
- Host in cluster C1 wants to reach host in cluster C3
- CC-1 detects traffic destined for remote cluster
- CC-1 requests routing path from AC

**Message Structure:**
```
[CC→AC] FLOW_REQUEST
  • src_cluster: 1
  • dst_cluster: 3
  • match_fields:
    - dst_ip: 10.30.0.10
    - src_ip: 10.10.0.10
```

**Protocol Definition (from message.proto):**
```protobuf
message FlowRequest {
  int32 src_cluster = 1;
  int32 dst_cluster = 2;
  map<string, string> match_fields = 3;
}
```

### Phase 4: AC Path Computation and Reply (FLOW_REPLY)

**Description:** AC computes cluster-level path and sends FLOW_REPLY to relevant CCs.

**AC Processing:**
1. Receives FLOW_REQUEST from source CC
2. Runs routing algorithm (Baseline or Cluster-Aware)
3. Considers inter-cluster link metrics
4. Considers cluster internal costs (if using Cluster-Aware)
5. Computes optimal cluster-level path
6. Constructs FLOW_REPLY with path segments

**Message Structure:**
```
[AC→CC] FLOW_REPLY
  • path: [C1, C3]
  • num_hops: 1
  • segments:
    - C1: ingress=entry_port, egress=to_C3
    - C3: ingress=from_C1, egress=exit_port
  • match_fields:
    - dst_ip: 10.30.0.10
    - src_ip: 10.10.0.10
```

**Protocol Definition (from message.proto):**
```protobuf
message FlowReply {
  repeated string path = 1;
  map<string, string> match_fields = 2;
  repeated Segment segments = 3;
}

message Segment {
  int32 cluster_id = 1;
  string ingress_border = 2;
  string egress_border = 3;
  string tunnel_id = 4;
}
```

**Key Points:**
- Path is sequence of cluster IDs (e.g., [C1, C5, C4])
- Each segment tells CC which ports to use
- Match fields identify the flow
- CCs use segments to install local forwarding rules

### Phase 5: Flow Installation

**Description:** Each CC in path installs forwarding flows based on its segment.

**Process:**
1. Each CC receives FLOW_REPLY from AC
2. CC extracts its segment from the path
3. CC installs OpenFlow rules:
   - Match on ingress port and flow fields
   - Forward to egress port
   - Decrement TTL for L3 routing
4. Cross-cluster path is established

**Output:**
```
Phase 5: Flow Installation
→ CC-1 installs forwarding flows based on path segment
→ CC-3 installs forwarding flows based on path segment
✓ Cross-cluster routing path established!
→ Host traffic can now flow across clusters
```

## Architecture Benefits

### Hierarchical Separation
- **AC View:** Only sees cluster-level topology
- **CC View:** Only manages local cluster
- **Benefit:** Scalability and management simplicity

### Protocol Abstraction
- CCs report abstract metrics (delay, loss)
- AC doesn't need cluster internal topology
- Maintains network-wide optimization capability

### East-West Communication
- Protocol enables CC-AC coordination
- Distributed metric collection
- Centralized path computation
- Local flow installation

## Simulation vs Real Implementation

### Simulation (Current)
- **Purpose:** Demonstrate protocol flow for research papers
- **Method:** Print formatted messages showing protocol exchange
- **Benefit:** No conflicts with physical platform deployment
- **Output:** Visual representation of message sequence

### Real Implementation (Physical Platform)
- **Purpose:** Actual cross-cluster routing
- **Method:** Protocol Buffers message exchange over TCP
- **Components:** AC controller + multiple CC controllers
- **Integration:** Works with real OVS switches and hosts

### Complementary Approach
- Simulation: Shows protocol design and interaction
- Real platform: Proves actual implementation works
- Both: Complete research story (design + validation)

## Usage

### Run Protocol Simulation

**3-Cluster Scenario:**
```bash
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3
```

**5-Cluster Scenario:**
```bash
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4
```

**Both Scenarios:**
```bash
python3 performance_comparison.py --all
```

### Output Features

**Color Coding:**
- 🔵 Blue headers: Major sections
- 🔷 Cyan (CC→AC): Messages from CC to AC
- 🟢 Green (AC→CC): Messages from AC to CC
- ✓ Success indicators: Completion markers

**Message Content:**
- Protocol message type (e.g., INTERCLUSTER_LINK_METRICS)
- All relevant fields from message.proto
- Actual values from NS-3 simulation data
- Clear phase separation

## Research Paper Usage

### Screenshots
The protocol simulation output is designed for research paper screenshots:
- Clear phase labeling (Phase 1-5)
- Protocol message structure visible
- Shows CC-AC interaction flow
- Demonstrates hierarchical control

### Figures
Can be used for:
- Protocol sequence diagrams
- Control plane interaction figures
- Message format illustrations
- System architecture diagrams

### Validation
Demonstrates:
- Protocol design completeness
- Message exchange correctness
- Hierarchical separation
- Practical implementation feasibility

## Technical Details

### Implementation
- **File:** `performance_comparison.py`
- **Functions:**
  - `simulate_protocol_exchange()`: Phases 1-4
  - `simulate_flow_reply()`: Phases 4-5
  - `print_protocol_message()`: Message formatting

### Integration
- Non-intrusive: Doesn't affect routing algorithms
- Modular: Can be enabled/disabled easily
- Compatible: Works with all scenarios
- Accurate: Follows message.proto definitions

### Data Sources
- **Cluster metrics:** From `cluster_metrics.csv`
- **Inter-cluster links:** From `intercluster_links.csv`
- **Path computation:** From routing algorithms
- **Message structure:** From `message.proto`

## Conclusion

The protocol simulation provides a complete view of the CC-AC interaction in hierarchical SDN, demonstrating:

1. **How CCs collect metrics** from NS-3 simulation data
2. **How CCs report to AC** via INTERCLUSTER_LINK_METRICS
3. **How flow requests are initiated** via FLOW_REQUEST
4. **How AC computes paths** using routing algorithms
5. **How paths are returned** via FLOW_REPLY
6. **How flows are installed** across multiple clusters

This simulation complements the physical platform deployment by showing the protocol design and interaction without requiring actual multi-controller setup.
