# NS-3 Routing Performance Comparison Tool

This tool compares hierarchical SDN routing algorithms using real NS-3 simulation data with **CC-AC protocol interaction simulation**.

## Overview

The tool evaluates two routing strategies across multiple scenarios:
- **Algorithm 1 (Baseline)**: Standard Dijkstra with uniform hop-count weights
- **Algorithm 2 (Cluster-Aware)**: Weighted Dijkstra with multi-dimensional metrics

### CC-AC Protocol Simulation

The tool simulates the complete message exchange between Cluster Controllers (CC) and Aggregation Controller (AC):

1. **Phase 1: CC Metric Collection**
   - CCs collect local cluster metrics (delay, loss, queue length)
   - CCs measure inter-cluster link metrics

2. **Phase 2: CC→AC Metric Reporting**
   - CCs send `INTERCLUSTER_LINK_METRICS` messages to AC
   - AC receives and stores all inter-cluster link metrics

3. **Phase 3: Cross-Cluster Flow Request**
   - Host initiates cross-cluster communication
   - Source CC sends `FLOW_REQUEST` to AC

4. **Phase 4: AC Path Computation**
   - AC computes cluster-level path using routing algorithms
   - AC sends `FLOW_REPLY` with path segments to CCs

5. **Phase 5: Flow Installation**
   - CCs install forwarding flows based on path segments
   - Cross-cluster routing path established

This simulation demonstrates the hierarchical SDN control plane interaction without requiring actual deployment.

## Scenarios

### 3-Cluster Scenario (Basic Verification)
- **Topology**: 3 clusters with full mesh connectivity
- **Test Flow**: C1 → C3
- **Purpose**: Verify algorithm correctness and baseline comparison
- **Data Location**: `ns3_data/3_cluster/`

### 5-Cluster Scenario (Scalability Verification)
- **Topology**: 5 clusters in ring formation
- **Test Flow**: C1 → C4  
- **Purpose**: Demonstrate scalability and multi-hop routing
- **Data Location**: `ns3_data/5_cluster/`

## NS-3 Data Files

Each scenario includes:
- `cluster_metrics.csv`: Internal cluster metrics (delay, loss, queue length)
- `intercluster_links.csv`: Inter-cluster link metrics (delay, loss) - symmetric links

## Usage

### Run Individual Scenarios

**3-Cluster Scenario (C1→C3):**
```bash
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3
```

**5-Cluster Scenario (C1→C4):**
```bash
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4
```

### Run All Scenarios with Graphs

```bash
python3 performance_comparison.py --all
```

This generates:
- `performance_comparison.png`: Side-by-side bar charts for delay, loss, and hop count
- `improvement_comparison.png`: Performance improvement percentages

### Advanced Options

**Specify time slice:**
```bash
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3 --time 2
```

**Custom weight parameters (α, β, γ):**
```bash
python3 performance_comparison.py --all --alpha 0.5 --beta 0.3 --gamma 0.2
```

Weight formula: `w(C_u → C_v) = α·D_norm + β·L_norm + γ·C_intra`

Where:
- `α`: Weight for inter-cluster delay
- `β`: Weight for inter-cluster packet loss
- `γ`: Weight for intra-cluster cost

**Examples for different QoS requirements:**

*Real-time applications (delay-sensitive):*
```bash
python3 performance_comparison.py --all --alpha 0.5 --beta 0.2 --gamma 0.3
```

*Reliable applications (loss-sensitive):*
```bash
python3 performance_comparison.py --all --alpha 0.3 --beta 0.5 --gamma 0.2
```

*Balanced:*
```bash
python3 performance_comparison.py --all --alpha 0.4 --beta 0.3 --gamma 0.3  # Default
```

## Output Interpretation

### Terminal Output

The tool displays:
1. **Metric Loading**: Shows normalized inter-cluster and intra-cluster metrics
2. **Algorithm 1 Results**: Path selection and performance metrics using baseline
3. **Algorithm 2 Results**: Path selection and performance metrics using cluster-aware
4. **Performance Comparison**: Improvement percentages for delay and loss

### Graph Files

**`performance_comparison.png`:**
- Three bar charts showing delay, loss, and hop count
- Blue bars: Baseline algorithm
- Green bars: Cluster-aware algorithm
- Compare across scenarios

**`improvement_comparison.png`:**
- Bar chart showing improvement percentages
- Red bars: Delay improvement
- Orange bars: Loss improvement  
- Positive values indicate cluster-aware performs better

## Example Output

```
================================================================================
                         Scenario: 3-Cluster (C1 → C3)
================================================================================

[Algorithm 1: Baseline Dijkstra]
→ Path: C1 → C3
→ Cost: 1.00 hops
  • End-to-end delay: 24.6739 ms
  • Average loss: 0.0350
  • Hop count: 1.0000

[Algorithm 2: Cluster-Aware Weighted Dijkstra]
→ Weight formula: w = 0.4·delay + 0.3·loss + 0.3·intra_cost
→ Path: C1 → C3
→ Cost: 0.0000
  • End-to-end delay: 24.6739 ms
  • Average loss: 0.0350
  • Hop count: 1.0000

[Performance Comparison]
  • Delay improvement: 0.0000 %
  • Loss improvement: 0.0000 %
→ Both algorithms selected the same optimal path
```

## Requirements

- Python 3.6+
- matplotlib (for graph generation)

Install matplotlib:
```bash
pip install matplotlib
```

## Data Format

### cluster_metrics.csv
```csv
time,cluster_id,avg_delay,packet_loss,avg_queue_len
1,1,4.8672,0.00512821,0
1,2,5.72267,0.00683761,0
...
```

### intercluster_links.csv
```csv
time,src_cluster,dst_cluster,delay,loss
1,1,2,17.9147,0.0405983
1,2,1,17.9147,0.0405983  # Symmetric link
...
```

## Algorithms

### Algorithm 1: Baseline Dijkstra

Standard shortest path with uniform weights:
- Edge weight = 1 (hop count only)
- Finds minimum hop-count path
- Time complexity: O((V+E) log V)

### Algorithm 2: Cluster-Aware Weighted Dijkstra

Multi-dimensional weighted shortest path:
- Edge weight = α·D_norm + β·L_norm + γ·C_intra
- Considers inter-cluster delay, loss, and intra-cluster cost
- Enables QoS-aware routing
- Maintains hierarchical separation (AC doesn't see cluster internals)

## Research Benefits

This tool demonstrates:
1. **Correctness**: Both algorithms find valid paths
2. **Scalability**: Works with varying cluster counts (3, 5, ...)
3. **Adaptability**: Cluster-aware can select different paths based on metrics
4. **Trade-offs**: Shows delay vs loss vs hop-count trade-offs
5. **Hierarchical SDN**: AC operates on abstracted cluster-level topology

## Troubleshooting

**No graphs generated:**
- Install matplotlib: `pip install matplotlib`

**"No path found" errors:**
- Check CSV files have correct format
- Verify topology connectivity (all clusters reachable)
- Check time slice exists in data

**Import errors:**
- Ensure Python 3.6+ is installed
- Install required packages: `pip install matplotlib`

## Publication Use

These outputs are suitable for research papers:
- Terminal output: Screenshot for protocol demonstration
- Performance graphs: Publication-ready PNG figures (300 DPI)
- Improvement charts: Quantitative comparison visualization

## Directory Structure

```
simulation/
├── performance_comparison.py    # Main comparison tool
├── routing_simulator.py         # Legacy single-scenario tool
├── ns3_data/                    # NS-3 simulation data
│   ├── 3_cluster/
│   │   ├── cluster_metrics.csv
│   │   └── intercluster_links.csv
│   └── 5_cluster/
│       ├── cluster_metrics.csv
│       └── intercluster_links.csv
├── sample_data/                 # Sample/demo data
└── README_NS3.md                # This file
```
