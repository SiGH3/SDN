# Routing Strategy Simulation Tool

This tool simulates the hierarchical SDN routing mechanism for research paper demonstration.

**Location**: `/ryu/custom/simulation/` - Part of the custom SDN controller modules

## Purpose

This standalone simulation tool:
1. Reads network metrics from NS-3 simulation CSV files
2. Simulates CC (Cluster Controller) metric reporting to AC (Aggregation Controller)  
3. Demonstrates baseline vs cluster-aware routing strategies
4. Generates terminal output suitable for paper screenshots
5. Creates performance comparison graphs

## Features

- **Visual Terminal Output**: Color-coded messages showing CC→AC communication and routing decisions
- **Two Routing Algorithms**:
  - Algorithm 1: Baseline Cluster-Level Dijkstra (uniform hop-count weights)
  - Algorithm 2: Cluster-Aware Weighted Dijkstra (multi-dimensional metrics)
- **Performance Metrics**: End-to-end delay, packet loss, hop count
- **Comparison Graphs**: Bar charts comparing algorithm performance

## Requirements

```bash
pip install matplotlib numpy
```

## Usage

### Basic Usage

```bash
python routing_simulator.py \
    --intercluster sample_data/intercluster_links.csv \
    --cluster sample_data/cluster_metrics.csv \
    --time 1
```

### With Custom Weights

```bash
python routing_simulator.py \
    --intercluster sample_data/intercluster_links.csv \
    --cluster sample_data/cluster_metrics.csv \
    --time 1 \
    --alpha 0.5 \
    --beta 0.2 \
    --gamma 0.3
```

## Input File Formats

### intercluster_links.csv
```csv
time,src_cluster,dst_cluster,delay,loss
1,1,2,17.9147,0.0405983
1,2,3,25.4336,0.0649573
1,3,1,12.7227,0.0350427
1,1,3,30.5000,0.0800000
```

**Note**: The sample data now includes a full mesh topology with direct links between all cluster pairs (bidirectional), allowing the algorithms to demonstrate different path selection strategies. For example:
- C1→C3 direct link (1 hop, higher delay/loss)
- C1→C2→C3 via intermediate (2 hops, potentially lower per-link metrics)

### cluster_metrics.csv
```csv
time,cluster_id,avg_delay,packet_loss,avg_queue_len
1,1,4.8672,0.00512821,0
1,2,5.72267,0.00683761,0
1,3,7.084,0.00854701,0
```

## Output

### Terminal Output
- Formatted, color-coded display showing:
  - Metric loading and normalization
  - CC initialization and metric reporting
  - AC path calculation for both algorithms
  - Performance comparison for each flow
  - Overall statistics

### Graph Output
- `routing_comparison.png`: Bar charts showing:
  - Average end-to-end delay
  - Average packet loss rate  
  - Average hop count

## Algorithm Parameters

### Composite Weight Formula

```
w(C_u → C_v) = α·D_norm + β·L_norm + γ·C_intra

where:
  D_norm = normalized inter-cluster delay
  L_norm = normalized inter-cluster loss
  C_intra = normalized intra-cluster cost
  α, β, γ = weight coefficients (α + β + γ should ≈ 1.0)
```

### Recommended Weight Settings

**Real-time applications** (prioritize delay):
- α (delay) = 0.5
- β (loss) = 0.2  
- γ (intra-cluster) = 0.3

**Bulk data transfer** (prioritize stability):
- α (delay) = 0.3
- β (loss) = 0.4
- γ (intra-cluster) = 0.3

**Balanced** (equal weights):
- α = β = γ = 0.33

## For Paper Screenshots

1. **Terminal Output**: 
   - Run with `--time 1` for clean snapshot
   - Capture sections showing:
     - CC metric reporting
     - Algorithm execution with path computation
     - Performance comparison

2. **Performance Graphs**:
   - Use `routing_comparison.png` directly
   - Shows clear visual comparison between algorithms
   - Professional formatting suitable for publication

## Example Test Flows

The simulator tests three default flows:
- C1 → C3: Tests path through intermediate clusters
- C2 → C1: Tests reverse direction  
- C3 → C2: Tests alternative routing

Modify the `flows` list in `main()` to test different scenarios.

## Architecture

This tool is **independent** from the main SDN controller code:
- No dependencies on Ryu or OVS
- Pure Python simulation using NS-3 metrics
- Can run on any machine with Python 3.6+

## Notes

- Uses min-max normalization for all metrics
- Implements actual Dijkstra algorithm (not simplified)
- Maintains hierarchical separation (AC doesn't see cluster internals)
- CC reports abstract costs (normalized metrics)
