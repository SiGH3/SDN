# NS-3 Routing Performance Testing - Quick Reference

## Overview
This document provides the exact commands to run the NS-3 routing performance comparison tool as requested.

## Requirements
```bash
pip install matplotlib
```

## Test Commands

### 1. Three-Cluster Scenario (C1→C3) - Basic Verification
```bash
cd ryu/custom/simulation
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3 --time 1
```

**Expected Output:**
- Algorithm 1 (Baseline): Selects optimal path based on hop count
- Algorithm 2 (Cluster-Aware): Selects path considering delay, loss, and intra-cluster cost
- Shows performance metrics: delay (ms), loss rate, hop count

### 2. Five-Cluster Scenario (C1→C4) - Scalability Verification
```bash
cd ryu/custom/simulation
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4 --time 1
```

**Expected Output:**
- Demonstrates multi-hop routing (2+ hops)
- Shows scalability of hierarchical routing
- Compares performance across longer paths

### 3. Complete Comparison with Graphs (Both Scenarios)
```bash
cd ryu/custom/simulation
python3 performance_comparison.py --all --time 1
```

**Generated Files:**
- `performance_comparison.png`: Bar charts comparing delay, loss, and hop count
- `improvement_comparison.png`: Performance improvement percentages

### 4. Test Different Time Slices

**3-Cluster at time=5 (lower loss rates):**
```bash
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3 --time 5
```

**5-Cluster at time=2 (alternative network state):**
```bash
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4 --time 2
```

### 5. Custom Weight Parameters

**Delay-sensitive routing (α=0.5):**
```bash
python3 performance_comparison.py --all --alpha 0.5 --beta 0.2 --gamma 0.3
```

**Loss-sensitive routing (β=0.5):**
```bash
python3 performance_comparison.py --all --alpha 0.3 --beta 0.5 --gamma 0.2
```

**Cluster-cost-sensitive routing (γ=0.5):**
```bash
python3 performance_comparison.py --all --alpha 0.25 --beta 0.25 --gamma 0.5
```

**Balanced (default):**
```bash
python3 performance_comparison.py --all --alpha 0.4 --beta 0.3 --gamma 0.3
```

## Output Interpretation

### Terminal Output Structure
1. **Scenario Header**: Shows source and destination
2. **Metric Loading**: Confirms data loaded successfully
3. **Algorithm 1 Results**: 
   - Path selected
   - Cost in hops
   - Performance metrics (delay, loss, hop count)
4. **Algorithm 2 Results**:
   - Weight formula used
   - Path selected
   - Weighted cost
   - Performance metrics
5. **Performance Comparison**:
   - Improvement percentages
   - Interpretation message

### Performance Metrics

**End-to-end delay (ms):**
- Sum of inter-cluster link delays + intra-cluster delays for all clusters in path
- Lower is better

**Average loss rate:**
- Average packet loss across all inter-cluster links in path
- Lower is better
- Displayed as decimal (e.g., 0.0350 = 3.5%)

**Hop count:**
- Number of inter-cluster hops
- Lower means shorter path but not necessarily better performance

### Graph Files

**performance_comparison.png:**
- Three side-by-side bar charts
- Blue bars: Baseline algorithm
- Green bars: Cluster-aware algorithm
- Shows absolute values for each scenario

**improvement_comparison.png:**
- Shows percentage improvements
- Positive values: Cluster-aware performs better
- Negative values: Baseline performs better
- Zero values: Same performance (often same path selected)

## Data Files Location

```
ryu/custom/simulation/
├── ns3_data/
│   ├── 3_cluster/
│   │   ├── cluster_metrics.csv       # Time slices 1-5
│   │   └── intercluster_links.csv    # Symmetric links
│   └── 5_cluster/
│       ├── cluster_metrics.csv       # Time slices 1-2
│       └── intercluster_links.csv    # Symmetric links
```

## Algorithm Details

### Algorithm 1: Baseline Dijkstra
- Weight: w(edge) = 1 (uniform hop count)
- Selects minimum hop-count path
- No consideration of link quality or cluster characteristics

### Algorithm 2: Cluster-Aware Weighted Dijkstra
- Weight: w(C_u→C_v) = α·D_norm + β·L_norm + γ·C_intra
- D_norm: Normalized inter-cluster delay
- L_norm: Normalized inter-cluster packet loss
- C_intra: Normalized intra-cluster cost
- Selects path with best composite metric

## Network Topologies

### 3-Cluster Topology
```
    C1 -------- C2
     \          /
      \        /
       \      /
        \    /
         \  /
          C3
```
- Full mesh connectivity
- All clusters can reach all others
- Direct C1→C3 link available

### 5-Cluster Topology
```
    C1 ------- C2
    |           |
    |           |
    C5          C3
     \         /
      \       /
       \     /
        \   /
         C4
```
- Ring formation with shortcuts
- C1→C4 requires multi-hop routing
- Multiple path options available

## Troubleshooting

**"No path found" error:**
- Check CSV files exist and are readable
- Verify time slice exists in data
- Check topology connectivity

**Graphs not generated:**
```bash
pip install matplotlib
```

**Different results than expected:**
- Verify using correct time slice (--time)
- Check weight parameters (α, β, γ)
- Confirm using correct scenario (3_cluster vs 5_cluster)

## For Research Papers

**Terminal Output:**
- Take screenshots of full output for protocol demonstration
- Shows step-by-step algorithm execution
- Demonstrates metric normalization and path selection

**Graph Files:**
- 300 DPI resolution, suitable for publication
- Clear comparison between algorithms
- Professional formatting with labels and legends

**Recommended Figures:**
1. Terminal output showing both algorithms
2. performance_comparison.png for absolute metrics
3. improvement_comparison.png for relative performance

## Quick Test Summary

**Minimal test (no graphs):**
```bash
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3
```

**Full test (with graphs):**
```bash
python3 performance_comparison.py --all
```

**Custom weights test:**
```bash
python3 performance_comparison.py --all --alpha 0.5 --beta 0.3 --gamma 0.2
```

All commands should be run from the `ryu/custom/simulation/` directory.
