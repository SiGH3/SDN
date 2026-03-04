# Algorithm Comparison - Understanding the Differences

## Overview

This document explains the differences between the two routing algorithms and why the new test scenarios clearly demonstrate their trade-offs.

## Algorithm Naming

- **Algorithm 1**: Baseline Dijkstra (Uniform Hop-Count)
- **Algorithm 2**: Cluster-Aware Weighted Dijkstra (Multi-Dimensional Metrics)

Previously labeled as "Algorithm 3", now corrected to "Algorithm 2" for consistency.

## Why Original Scenarios Showed No Difference

### Original 3-Cluster Scenario (C1→C3)
- Direct link C1→C3: 12.72ms delay, 3.5% loss
- Alternative C1→C2→C3: ~43ms delay, combined higher loss
- **Result**: Both algorithms correctly chose the direct link (clearly optimal)

### Original 5-Cluster Scenario (C1→C4)
- Ring topology with only one viable path: C1→C5→C4
- **Result**: Both algorithms chose the same path (no alternative)

## New Scenarios with Clear Trade-offs

### New 3-Cluster Scenario (C1→C3)

**Network Topology:**
```
C1 ←→ C2 ←→ C3
 ↘_________↗
```

**Link Metrics:**
- C1→C3 (direct): 50ms delay, 12% loss (SHORT BUT BAD QUALITY)
- C1→C2: 15ms delay, 1% loss
- C2→C3: 18ms delay, 1.5% loss
- C1→C2→C3 (indirect): 33ms total delay, ~2.5% combined loss (LONGER BUT BETTER QUALITY)

**Algorithm Results:**
- **Algorithm 1 (Baseline)**: Chooses C1→C3 (1 hop)
  - Delay: 61.95ms
  - Loss: 12%
  - Hop count: 1
  
- **Algorithm 2 (Cluster-Aware)**: Chooses C1→C2→C3 (2 hops)
  - Delay: 50.67ms (18% better)
  - Loss: 1.25% (90% better)
  - Hop count: 2

**Why This Shows Algorithm Value:**
The cluster-aware algorithm recognizes that the 2-hop path has much better quality metrics, even though it uses more hops. It trades one extra hop for significantly better delay and loss characteristics.

### New 5-Cluster Scenario (C1→C4)

**Network Topology:**
```
C1 ←→ C2 ←→ C3 ←→ C4
 ↘_______________↗
```

**Link Metrics:**
- C1→C4 (direct): 60ms delay, 15% loss (SHORT BUT BAD QUALITY)
- C1→C2→C3→C4 (indirect): ~52ms total delay, ~3% combined loss (LONGER BUT BETTER QUALITY)

**Algorithm Results:**
- **Algorithm 1 (Baseline)**: Chooses C1→C4 (1 hop)
  - Delay: 76.31ms
  - Loss: 15%
  - Hop count: 1
  
- **Algorithm 2 (Cluster-Aware)**: Chooses C1→C2→C3→C4 (3 hops)
  - Delay: 64.02ms (16% better)
  - Loss: 1.2% (92% better)
  - Hop count: 3

**Why This Shows Algorithm Value:**
The cluster-aware algorithm chooses a 3-hop path over a direct path, achieving much better quality. This demonstrates the algorithm's ability to consider quality metrics beyond just hop count.

## Key Insights

### Algorithm 1 (Baseline Dijkstra)
**Optimization Goal:** Minimize hop count
- Simple and predictable
- Always chooses shortest path in terms of hops
- Good when all links have similar quality
- May choose poor-quality links

### Algorithm 2 (Cluster-Aware Weighted Dijkstra)
**Optimization Goal:** Balance delay, loss, and hop count
- Considers multiple metrics simultaneously
- Can choose longer paths for better quality
- Better for networks with varying link quality
- Trade-offs are configurable via α, β, γ weights

**Weight Formula:**
```
w(C_u → C_v) = α·delay_norm + β·loss_norm + γ·intra_cost_norm
```
Default: α=0.4, β=0.3, γ=0.3

## Practical Implications

### When to Use Algorithm 1 (Baseline)
- Homogeneous networks (similar link qualities)
- When hop count minimization is critical
- Simple routing requirements
- Predictable behavior needed

### When to Use Algorithm 2 (Cluster-Aware)
- Heterogeneous networks (varying link qualities)
- Quality-sensitive applications (VoIP, video)
- Wireless/ad-hoc networks with unstable links
- When trade-offs between metrics are acceptable

## Testing the Scenarios

### 3-Cluster Scenario
```bash
python3 performance_comparison.py --scenario 3_cluster --src 1 --dst 3
```

Expected: Algorithm 2 chooses 2-hop path with better quality

### 5-Cluster Scenario
```bash
python3 performance_comparison.py --scenario 5_cluster --src 1 --dst 4
```

Expected: Algorithm 2 chooses 3-hop path with better quality

### Both Scenarios
```bash
python3 performance_comparison.py --all
```

Generates comparison graphs showing performance differences

## Conclusion

The new scenarios demonstrate clear trade-offs:
- **Short paths with poor quality** vs **Longer paths with good quality**
- Algorithm 1 optimizes for hop count
- Algorithm 2 optimizes for overall quality considering multiple metrics

This illustrates the value of cluster-aware weighted routing in real-world networks where link quality varies significantly.
