#!/usr/bin/env python3
"""
Performance Comparison Tool for Hierarchical SDN Routing Algorithms

Compares baseline Dijkstra vs cluster-aware weighted routing across multiple scenarios:
- 3-cluster scenario (C1→C3): Basic verification  
- 5-cluster scenario (C1→C4): Scalability verification

Generates performance comparison graphs showing:
- End-to-end delay
- Packet loss rate
- Hop count
- Overall improvement metrics

Usage:
    # Run 3-cluster scenario
    python performance_comparison.py --scenario 3_cluster --src 1 --dst 3
    
    # Run 5-cluster scenario
    python performance_comparison.py --scenario 5_cluster --src 1 --dst 4
    
    # Run both scenarios and generate comprehensive comparison
    python performance_comparison.py --all
"""

import csv
import sys
import argparse
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import heapq

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available. Graphs will not be generated.")
    print("Install with: pip install matplotlib")

# Terminal colors
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")


def print_section(text):
    """Print section title"""
    print(f"\n{Colors.OKBLUE}{Colors.BOLD}[{text}]{Colors.ENDC}")


def print_success(text):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.OKCYAN}→ {text}{Colors.ENDC}")


def print_metric(label, value, unit=""):
    """Print metric with consistent formatting"""
    print(f"  • {label}: {value:.4f} {unit}")


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_protocol_message(direction: str, msg_type: str, content: Dict):
    """Print protocol message in formatted style"""
    arrow = "→" if "CC→AC" in direction else "←"
    color = Colors.OKCYAN if "CC→AC" in direction else Colors.OKGREEN
    
    print(f"\n{color}{Colors.BOLD}[{direction}] {msg_type}{Colors.ENDC}")
    for key, value in content.items():
        if isinstance(value, (list, tuple)):
            print(f"  • {key}:")
            for item in value:
                print(f"    - {item}")
        elif isinstance(value, dict):
            print(f"  • {key}:")
            for k, v in value.items():
                print(f"    - {k}: {v}")
        else:
            print(f"  • {key}: {value}")


def simulate_protocol_exchange(metrics: 'NetworkMetrics', src: int, dst: int):
    """Simulate CC-AC protocol message exchange"""
    
    print_section("CC-AC Protocol Interaction Simulation")
    print_info("Demonstrating hierarchical SDN protocol message flow")
    
    # Phase 1: CC collects metrics
    print(f"\n{Colors.BOLD}Phase 1: CC Metric Collection{Colors.ENDC}")
    print_info(f"CC-{src} collects local cluster metrics and inter-cluster link measurements")
    
    # Simulate CC collecting cluster metrics
    cluster_data = {}
    for cluster_id in metrics.cluster_metrics.keys():
        cluster_metric = metrics.cluster_metrics[cluster_id]
        cluster_data[f"C{cluster_id}"] = {
            'avg_delay': f"{cluster_metric.get('delay', 0):.2f} ms",
            'packet_loss': f"{cluster_metric.get('loss', 0):.4f}",
            'queue_len': f"{cluster_metric.get('queue', 0):.2f}"
        }
    
    print(f"  Collected metrics from {len(cluster_data)} cluster(s)")
    
    # Simulate CC collecting inter-cluster link metrics
    link_data = {}
    for (u, v), link_metric in metrics.intercluster_links.items():
        link_key = f"C{u}→C{v}"
        link_data[link_key] = {
            'delay': f"{link_metric.get('delay', 0):.2f} ms",
            'loss': f"{link_metric.get('loss', 0):.4f}"
        }
    
    print(f"  Measured {len(link_data)} inter-cluster link(s)")
    
    # Phase 2: CC reports metrics to AC via INTERCLUSTER_LINK_METRICS
    print(f"\n{Colors.BOLD}Phase 2: CC Reports Metrics to AC{Colors.ENDC}")
    
    # Simulate INTERCLUSTER_LINK_METRICS message from each CC
    for cluster_id in metrics.cluster_metrics.keys():
        cluster_links = [(u, v) for (u, v) in metrics.intercluster_links.keys() if u == cluster_id]
        
        if cluster_links:
            metric_entries = []
            for (u, v) in cluster_links:
                link_metric = metrics.intercluster_links[(u, v)]
                metric_entries.append(
                    f"link_key=C{u}→C{v}, latency={link_metric.get('delay', 0):.2f}ms, "
                    f"loss={link_metric.get('loss', 0):.4f}"
                )
            
            print_protocol_message(
                "CC→AC",
                "INTERCLUSTER_LINK_METRICS",
                {
                    'cluster_id': cluster_id,
                    'num_links': len(cluster_links),
                    'metrics': metric_entries
                }
            )
    
    print_success("AC received and stored all inter-cluster link metrics")
    
    # Phase 3: Host initiates cross-cluster communication
    print(f"\n{Colors.BOLD}Phase 3: Cross-Cluster Flow Request{Colors.ENDC}")
    print_info(f"Host in C{src} wants to communicate with host in C{dst}")
    print_info(f"CC-{src} detects cross-cluster traffic and requests path from AC")
    
    # Simulate FLOW_REQUEST message
    print_protocol_message(
        "CC→AC",
        "FLOW_REQUEST",
        {
            'src_cluster': src,
            'dst_cluster': dst,
            'match_fields': {
                'dst_ip': f"10.{dst}0.0.10",
                'src_ip': f"10.{src}0.0.10"
            }
        }
    )
    
    # Phase 4: AC computes path and sends FLOW_REPLY
    print(f"\n{Colors.BOLD}Phase 4: AC Path Computation and Reply{Colors.ENDC}")
    print_info("AC uses routing algorithm to compute cluster-level path")
    print_info("AC considers inter-cluster link metrics and cluster internal costs")


def simulate_flow_reply(path: List[int], src: int, dst: int):
    """Simulate FLOW_REPLY message from AC to CC"""
    
    # Simulate path computation complete
    print_success(f"Path computed: {' → '.join(f'C{c}' for c in path)}")
    
    # Simulate FLOW_REPLY message
    segments = []
    for i in range(len(path)):
        cluster_id = path[i]
        ingress = "entry_port" if i == 0 else f"from_C{path[i-1]}"
        egress = "exit_port" if i == len(path) - 1 else f"to_C{path[i+1]}"
        segments.append(f"C{cluster_id}: ingress={ingress}, egress={egress}")
    
    print_protocol_message(
        "AC→CC",
        "FLOW_REPLY",
        {
            'path': [f"C{c}" for c in path],
            'num_hops': len(path) - 1,
            'segments': segments,
            'match_fields': {
                'dst_ip': f"10.{dst}0.0.10",
                'src_ip': f"10.{src}0.0.10"
            }
        }
    )
    
    # Phase 5: CCs install flows
    print(f"\n{Colors.BOLD}Phase 5: Flow Installation{Colors.ENDC}")
    for cluster_id in path:
        print_info(f"CC-{cluster_id} installs forwarding flows based on path segment")
    
    print_success("Cross-cluster routing path established!")
    print_info("Host traffic can now flow across clusters")


def normalize_min_max(values: List[float]) -> List[float]:
    """Min-Max normalization: x̂ = (x - x_min) / (x_max - x_min)"""
    if not values or len(set(values)) == 1:
        return [0.0] * len(values)
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return [0.0] * len(values)
    return [(v - vmin) / (vmax - vmin) for v in values]


class NetworkMetrics:
    """Stores and manages network metrics from NS-3 simulation"""
    
    def __init__(self):
        self.intercluster_links = defaultdict(dict)
        self.cluster_metrics = defaultdict(dict)
        self.topology = defaultdict(set)
        
    def load_intercluster_links(self, filepath: str, time_slice: int = 1):
        """Load inter-cluster link metrics from CSV"""
        print_section(f"Loading Inter-Cluster Link Metrics (time={time_slice})")
        
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = int(row['time'])
                if t != time_slice:
                    continue
                    
                src = int(row['src_cluster'])
                dst = int(row['dst_cluster'])
                delay = float(row['delay'])
                loss = float(row['loss'])
                
                self.intercluster_links[(src, dst)] = {
                    'delay': delay,
                    'loss': loss
                }
                self.topology[src].add(dst)
        
        print_success(f"Loaded {len(self.intercluster_links)} inter-cluster links")
        
        # Normalize inter-cluster metrics
        all_delays = [m['delay'] for m in self.intercluster_links.values()]
        all_losses = [m['loss'] for m in self.intercluster_links.values()]
        
        norm_delays = normalize_min_max(all_delays)
        norm_losses = normalize_min_max(all_losses)
        
        for i, (edge, metrics) in enumerate(self.intercluster_links.items()):
            metrics['delay_norm'] = norm_delays[i]
            metrics['loss_norm'] = norm_losses[i]
    
    def load_cluster_metrics(self, filepath: str, time_slice: int = 1):
        """Load cluster internal metrics from CSV"""
        print_section(f"Loading Cluster Internal Metrics (time={time_slice})")
        
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = int(row['time'])
                if t != time_slice:
                    continue
                    
                cid = int(row['cluster_id'])
                avg_delay = float(row['avg_delay'])
                packet_loss = float(row['packet_loss'])
                
                self.cluster_metrics[cid] = {
                    'delay': avg_delay,
                    'loss': packet_loss
                }
        
        print_success(f"Loaded metrics for {len(self.cluster_metrics)} clusters")
        
        # Normalize cluster metrics
        all_delays = [m['delay'] for m in self.cluster_metrics.values()]
        norm_delays = normalize_min_max(all_delays)
        
        for i, (cid, metrics) in enumerate(self.cluster_metrics.items()):
            metrics['delay_norm'] = norm_delays[i]


class RoutingAlgorithm:
    """Implements routing algorithms for comparison"""
    
    def __init__(self, metrics: NetworkMetrics):
        self.metrics = metrics
        
    def dijkstra_baseline(self, src: int, dst: int) -> Tuple[List[int], float]:
        """
        Algorithm 1: Baseline Dijkstra with uniform weights
        Uses hop count only (weight = 1 per edge)
        """
        distances = {node: float('inf') for node in self.metrics.topology.keys()}
        distances[src] = 0
        predecessors = {}
        pq = [(0, src)]
        visited = set()
        
        while pq:
            dist, u = heapq.heappop(pq)
            
            if u in visited:
                continue
            visited.add(u)
            
            if u == dst:
                break
                
            for v in self.metrics.topology.get(u, []):
                # Uniform weight = 1 (hop count)
                weight = 1
                new_dist = dist + weight
                
                if new_dist < distances[v]:
                    distances[v] = new_dist
                    predecessors[v] = u
                    heapq.heappush(pq, (new_dist, v))
        
        # Reconstruct path
        if dst not in predecessors and src != dst:
            return [], float('inf')
            
        path = []
        current = dst
        while current != src:
            path.append(current)
            if current not in predecessors:
                return [], float('inf')
            current = predecessors[current]
        path.append(src)
        path.reverse()
        
        return path, distances[dst]
    
    def cluster_aware_weighted(self, src: int, dst: int, 
                               alpha: float = 0.4, 
                               beta: float = 0.3, 
                               gamma: float = 0.3) -> Tuple[List[int], float]:
        """
        Algorithm 3: Cluster-Aware Weighted Dijkstra
        
        Edge weight: w(C_u → C_v) = α·D_norm + β·L_norm + γ·C_intra(u)
        where:
          D_norm = normalized inter-cluster delay
          L_norm = normalized inter-cluster loss
          C_intra = normalized intra-cluster cost
        """
        distances = {node: float('inf') for node in self.metrics.topology.keys()}
        distances[src] = 0
        predecessors = {}
        pq = [(0, src)]
        visited = set()
        
        while pq:
            dist, u = heapq.heappop(pq)
            
            if u in visited:
                continue
            visited.add(u)
            
            if u == dst:
                break
                
            for v in self.metrics.topology.get(u, []):
                # Get normalized metrics
                edge_metrics = self.metrics.intercluster_links.get((u, v), {})
                delay_norm = edge_metrics.get('delay_norm', 0)
                loss_norm = edge_metrics.get('loss_norm', 0)
                
                cluster_metrics = self.metrics.cluster_metrics.get(u, {})
                intra_cost = cluster_metrics.get('delay_norm', 0)
                
                # Composite weight formula
                weight = alpha * delay_norm + beta * loss_norm + gamma * intra_cost
                new_dist = dist + weight
                
                if new_dist < distances[v]:
                    distances[v] = new_dist
                    predecessors[v] = u
                    heapq.heappush(pq, (new_dist, v))
        
        # Reconstruct path
        if dst not in predecessors and src != dst:
            return [], float('inf')
            
        path = []
        current = dst
        while current != src:
            path.append(current)
            if current not in predecessors:
                return [], float('inf')
            current = predecessors[current]
        path.append(src)
        path.reverse()
        
        return path, distances[dst]
    
    def calculate_path_metrics(self, path: List[int]) -> Dict[str, float]:
        """Calculate actual performance metrics for a path"""
        if not path or len(path) < 2:
            return {'delay': 0, 'loss': 0, 'hops': 0}
        
        total_delay = 0
        total_loss = 0
        
        # Sum inter-cluster link delays and losses
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            edge = self.metrics.intercluster_links.get((u, v), {})
            total_delay += edge.get('delay', 0)
            total_loss += edge.get('loss', 0)
        
        # Add intra-cluster delays for all clusters in path
        for cluster in path:
            cluster_metric = self.metrics.cluster_metrics.get(cluster, {})
            total_delay += cluster_metric.get('delay', 0)
        
        # Average loss rate
        avg_loss = total_loss / (len(path) - 1) if len(path) > 1 else 0
        
        return {
            'delay': total_delay,
            'loss': avg_loss,
            'hops': len(path) - 1
        }


def run_scenario(scenario_name: str, data_dir: str, src: int, dst: int, 
                 time_slice: int = 1, alpha: float = 0.4, beta: float = 0.3, gamma: float = 0.3):
    """Run routing comparison for a single scenario"""
    
    print_header(f"Scenario: {scenario_name} (C{src} → C{dst})")
    
    # Load metrics
    metrics = NetworkMetrics()
    intercluster_file = f"{data_dir}/intercluster_links.csv"
    cluster_file = f"{data_dir}/cluster_metrics.csv"
    
    metrics.load_intercluster_links(intercluster_file, time_slice)
    metrics.load_cluster_metrics(cluster_file, time_slice)
    
    # Simulate CC-AC protocol interaction
    simulate_protocol_exchange(metrics, src, dst)
    
    # Run algorithms
    routing = RoutingAlgorithm(metrics)
    
    print_section("Algorithm 1: Baseline Dijkstra")
    baseline_path, baseline_cost = routing.dijkstra_baseline(src, dst)
    print_info(f"Path: {' → '.join(f'C{c}' for c in baseline_path)}")
    print_info(f"Cost: {baseline_cost:.2f} hops")
    
    baseline_metrics = routing.calculate_path_metrics(baseline_path)
    print_metric("End-to-end delay", baseline_metrics['delay'], "ms")
    print_metric("Average loss", baseline_metrics['loss'], "")
    print_metric("Hop count", baseline_metrics['hops'], "")
    
    print_section("Algorithm 3: Cluster-Aware Weighted Dijkstra")
    print_info(f"Weight formula: w = {alpha}·delay + {beta}·loss + {gamma}·intra_cost")
    cluster_path, cluster_cost = routing.cluster_aware_weighted(src, dst, alpha, beta, gamma)
    print_info(f"Path: {' → '.join(f'C{c}' for c in cluster_path)}")
    print_info(f"Cost: {cluster_cost:.4f}")
    
    cluster_metrics = routing.calculate_path_metrics(cluster_path)
    print_metric("End-to-end delay", cluster_metrics['delay'], "ms")
    print_metric("Average loss", cluster_metrics['loss'], "")
    print_metric("Hop count", cluster_metrics['hops'], "")
    
    # Simulate FLOW_REPLY for the selected path (using cluster-aware result)
    simulate_flow_reply(cluster_path, src, dst)
    
    # Calculate improvements
    print_section("Performance Comparison")
    delay_imp = ((baseline_metrics['delay'] - cluster_metrics['delay']) / baseline_metrics['delay'] * 100) if baseline_metrics['delay'] > 0 else 0
    loss_imp = ((baseline_metrics['loss'] - cluster_metrics['loss']) / baseline_metrics['loss'] * 100) if baseline_metrics['loss'] > 0 else 0
    
    print_metric("Delay improvement", delay_imp, "%")
    print_metric("Loss improvement", loss_imp, "%")
    
    if delay_imp > 0 or loss_imp > 0:
        print_success("Cluster-aware routing shows improvement!")
    elif baseline_path == cluster_path:
        print_info("Both algorithms selected the same optimal path")
    else:
        print_info("Different paths with different trade-offs")
    
    return {
        'scenario': scenario_name,
        'src': src,
        'dst': dst,
        'baseline': baseline_metrics,
        'cluster_aware': cluster_metrics,
        'baseline_path': baseline_path,
        'cluster_path': cluster_path,
        'delay_improvement': delay_imp,
        'loss_improvement': loss_imp
    }


def generate_comparison_graphs(results: List[Dict]):
    """Generate performance comparison bar charts"""
    
    if not HAS_MATPLOTLIB:
        print_warning("Matplotlib not available. Skipping graph generation.")
        return
    
    print_section("Generating Performance Comparison Graphs")
    
    # Prepare data
    scenarios = [r['scenario'] for r in results]
    
    baseline_delays = [r['baseline']['delay'] for r in results]
    cluster_delays = [r['cluster_aware']['delay'] for r in results]
    
    baseline_losses = [r['baseline']['loss'] * 100 for r in results]  # Convert to percentage
    cluster_losses = [r['cluster_aware']['loss'] * 100 for r in results]
    
    baseline_hops = [r['baseline']['hops'] for r in results]
    cluster_hops = [r['cluster_aware']['hops'] for r in results]
    
    # Create figure with 3 subplots
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    x = range(len(scenarios))
    width = 0.35
    
    # Delay comparison
    axes[0].bar([i - width/2 for i in x], baseline_delays, width, label='Baseline', color='#3498db', alpha=0.8)
    axes[0].bar([i + width/2 for i in x], cluster_delays, width, label='Cluster-Aware', color='#2ecc71', alpha=0.8)
    axes[0].set_xlabel('Scenario', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('End-to-End Delay (ms)', fontsize=12, fontweight='bold')
    axes[0].set_title('Delay Comparison', fontsize=14, fontweight='bold')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(scenarios)
    axes[0].legend()
    axes[0].grid(axis='y', alpha=0.3)
    
    # Loss comparison
    axes[1].bar([i - width/2 for i in x], baseline_losses, width, label='Baseline', color='#3498db', alpha=0.8)
    axes[1].bar([i + width/2 for i in x], cluster_losses, width, label='Cluster-Aware', color='#2ecc71', alpha=0.8)
    axes[1].set_xlabel('Scenario', fontsize=12, fontweight='bold')
    axes[1].set_ylabel('Packet Loss Rate (%)', fontsize=12, fontweight='bold')
    axes[1].set_title('Packet Loss Comparison', fontsize=14, fontweight='bold')
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(scenarios)
    axes[1].legend()
    axes[1].grid(axis='y', alpha=0.3)
    
    # Hop count comparison
    axes[2].bar([i - width/2 for i in x], baseline_hops, width, label='Baseline', color='#3498db', alpha=0.8)
    axes[2].bar([i + width/2 for i in x], cluster_hops, width, label='Cluster-Aware', color='#2ecc71', alpha=0.8)
    axes[2].set_xlabel('Scenario', fontsize=12, fontweight='bold')
    axes[2].set_ylabel('Hop Count', fontsize=12, fontweight='bold')
    axes[2].set_title('Hop Count Comparison', fontsize=14, fontweight='bold')
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(scenarios)
    axes[2].legend()
    axes[2].grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    output_file = 'performance_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print_success(f"Graph saved to: {output_file}")
    
    # Also create improvement chart
    fig2, ax = plt.subplots(figsize=(10, 6))
    
    delay_improvements = [r['delay_improvement'] for r in results]
    loss_improvements = [r['loss_improvement'] for r in results]
    
    x = range(len(scenarios))
    width = 0.35
    
    ax.bar([i - width/2 for i in x], delay_improvements, width, label='Delay Improvement', color='#e74c3c', alpha=0.8)
    ax.bar([i + width/2 for i in x], loss_improvements, width, label='Loss Improvement', color='#f39c12', alpha=0.8)
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_xlabel('Scenario', fontsize=12, fontweight='bold')
    ax.set_ylabel('Improvement (%)', fontsize=12, fontweight='bold')
    ax.set_title('Performance Improvement: Cluster-Aware vs Baseline', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    improvement_file = 'improvement_comparison.png'
    plt.savefig(improvement_file, dpi=300, bbox_inches='tight')
    print_success(f"Improvement graph saved to: {improvement_file}")


def main():
    parser = argparse.ArgumentParser(description='Performance Comparison Tool')
    parser.add_argument('--scenario', choices=['3_cluster', '5_cluster'], 
                       help='Scenario to run')
    parser.add_argument('--src', type=int, help='Source cluster ID')
    parser.add_argument('--dst', type=int, help='Destination cluster ID')
    parser.add_argument('--time', type=int, default=1, help='Time slice to analyze')
    parser.add_argument('--alpha', type=float, default=0.4, help='Weight for delay')
    parser.add_argument('--beta', type=float, default=0.3, help='Weight for loss')
    parser.add_argument('--gamma', type=float, default=0.3, help='Weight for intra-cluster cost')
    parser.add_argument('--all', action='store_true', help='Run all scenarios')
    
    args = parser.parse_args()
    
    base_dir = "ns3_data"
    
    results = []
    
    if args.all:
        # Run both scenarios
        print_header("Running All Scenarios")
        
        # 3-cluster scenario
        result1 = run_scenario(
            "3-Cluster (C1→C3)",
            f"{base_dir}/3_cluster",
            src=1, dst=3,
            time_slice=args.time,
            alpha=args.alpha, beta=args.beta, gamma=args.gamma
        )
        results.append(result1)
        
        # 5-cluster scenario
        result2 = run_scenario(
            "5-Cluster (C1→C4)",
            f"{base_dir}/5_cluster",
            src=1, dst=4,
            time_slice=args.time,
            alpha=args.alpha, beta=args.beta, gamma=args.gamma
        )
        results.append(result2)
        
        # Generate comparison graphs
        generate_comparison_graphs(results)
        
    elif args.scenario and args.src is not None and args.dst is not None:
        # Run specific scenario
        data_dir = f"{base_dir}/{args.scenario}"
        result = run_scenario(
            f"{args.scenario.replace('_', '-').title()}",
            data_dir,
            src=args.src, dst=args.dst,
            time_slice=args.time,
            alpha=args.alpha, beta=args.beta, gamma=args.gamma
        )
        results.append(result)
        
    else:
        parser.print_help()
        print("\nExample commands:")
        print("  python performance_comparison.py --scenario 3_cluster --src 1 --dst 3")
        print("  python performance_comparison.py --scenario 5_cluster --src 1 --dst 4")
        print("  python performance_comparison.py --all")
        return 1
    
    print_header("Comparison Complete")
    return 0


if __name__ == '__main__':
    sys.exit(main())
