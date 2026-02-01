#!/usr/bin/env python3
"""
Routing Strategy Simulation and Comparison Tool

This standalone tool simulates the hierarchical SDN routing mechanism:
1. Reads network metrics from NS-3 simulation CSV files
2. Simulates CC metric reporting to AC
3. Demonstrates baseline vs cluster-aware routing strategies
4. Generates performance comparison graphs for research paper

Usage:
    python routing_simulator.py --intercluster intercluster_links.csv \
                                --cluster cluster_metrics.csv \
                                --flows flows.csv
"""

import csv
import sys
import time
import argparse
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import heapq

# Terminal colors for better visualization
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


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


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def normalize_min_max(values: List[float]) -> List[float]:
    """
    Min-Max normalization: x̂ = (x - x_min) / (x_max - x_min)
    
    Args:
        values: List of values to normalize
        
    Returns:
        Normalized values in range [0, 1]
    """
    if not values or len(set(values)) == 1:
        return [0.0] * len(values)
    vmin, vmax = min(values), max(values)
    if vmax == vmin:
        return [0.0] * len(values)
    return [(v - vmin) / (vmax - vmin) for v in values]


class NetworkMetrics:
    """Stores and manages network metrics from NS-3 simulation"""
    
    def __init__(self):
        # Inter-cluster link metrics: {(src, dst): {'delay': float, 'loss': float}}
        self.intercluster_links = defaultdict(dict)
        # Cluster internal metrics: {cluster_id: {'delay': float, 'loss': float, 'queue': float}}
        self.cluster_metrics = defaultdict(dict)
        # Topology: {cluster_id: [neighbor_cluster_ids]}
        self.topology = defaultdict(set)
        
    def load_intercluster_links(self, filepath: str, time_slice: int = 1):
        """Load inter-cluster link metrics from CSV"""
        print_section("Loading Inter-Cluster Link Metrics")
        
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
                
                print_info(f"Link C{src}→C{dst}: delay={delay:.2f}ms, loss={loss:.4f}")
        
        print_success(f"Loaded {len(self.intercluster_links)} inter-cluster links")
        
    def load_cluster_metrics(self, filepath: str, time_slice: int = 1):
        """Load cluster internal metrics from CSV"""
        print_section("Loading Cluster Internal Metrics")
        
        with open(filepath, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                t = int(row['time'])
                if t != time_slice:
                    continue
                    
                cid = int(row['cluster_id'])
                avg_delay = float(row['avg_delay'])
                packet_loss = float(row['packet_loss'])
                avg_queue = float(row['avg_queue_len'])
                
                self.cluster_metrics[cid] = {
                    'delay': avg_delay,
                    'loss': packet_loss,
                    'queue': avg_queue
                }
                
                print_info(f"Cluster {cid}: internal_delay={avg_delay:.2f}ms, "
                          f"loss={packet_loss:.4f}, queue={avg_queue:.2f}")
        
        print_success(f"Loaded metrics for {len(self.cluster_metrics)} clusters")
        
    def normalize_metrics(self):
        """Normalize all metrics to [0, 1] range"""
        print_section("Normalizing Metrics (Min-Max)")
        
        # Normalize inter-cluster delays
        delays = [m['delay'] for m in self.intercluster_links.values()]
        norm_delays = normalize_min_max(delays)
        for (link, norm_delay) in zip(self.intercluster_links.keys(), norm_delays):
            self.intercluster_links[link]['norm_delay'] = norm_delay
            
        # Normalize inter-cluster losses
        losses = [m['loss'] for m in self.intercluster_links.values()]
        norm_losses = normalize_min_max(losses)
        for (link, norm_loss) in zip(self.intercluster_links.keys(), norm_losses):
            self.intercluster_links[link]['norm_loss'] = norm_loss
            
        # Normalize cluster internal delays
        cluster_delays = [m['delay'] for m in self.cluster_metrics.values()]
        norm_cluster_delays = normalize_min_max(cluster_delays)
        for (cid, norm_delay) in zip(self.cluster_metrics.keys(), norm_cluster_delays):
            self.cluster_metrics[cid]['norm_delay'] = norm_delay
            
        print_success("All metrics normalized to [0, 1] range")


class ClusterController:
    """Simulates a Cluster Controller (CC)"""
    
    def __init__(self, cluster_id: int, metrics: Dict):
        self.cluster_id = cluster_id
        self.metrics = metrics
        
    def report_metrics_to_ac(self):
        """Simulate CC reporting metrics to AC"""
        print(f"\n{Colors.OKCYAN}[CC-{self.cluster_id}] Reporting metrics to AC:{Colors.ENDC}")
        print(f"  • Internal delay: {self.metrics['delay']:.2f} ms "
              f"(normalized: {self.metrics['norm_delay']:.3f})")
        print(f"  • Packet loss: {self.metrics['loss']:.4f}")
        print(f"  • Queue length: {self.metrics['queue']:.2f}")
        
        return {
            'cluster_id': self.cluster_id,
            'intra_cluster_cost': self.metrics['norm_delay'],  # Use normalized delay as cost
            'raw_delay': self.metrics['delay'],
            'raw_loss': self.metrics['loss']
        }


class AggregationController:
    """Simulates the Aggregation Controller (AC)"""
    
    def __init__(self, metrics: NetworkMetrics):
        self.metrics = metrics
        self.intra_cluster_costs = {}
        
    def receive_cc_reports(self, cc_list: List[ClusterController]):
        """Receive and store CC metric reports"""
        print_section("AC Receiving CC Metric Reports")
        
        for cc in cc_list:
            report = cc.report_metrics_to_ac()
            self.intra_cluster_costs[report['cluster_id']] = report['intra_cluster_cost']
            
        print_success(f"AC received reports from {len(cc_list)} clusters")
        
    def baseline_dijkstra(self, src: int, dst: int) -> Tuple[List[int], float]:
        """
        Algorithm 1: Baseline Cluster-Level Dijkstra
        Uses uniform edge weights (1 per hop)
        """
        print_section(f"Algorithm 1: Baseline Dijkstra (C{src} → C{dst})")
        print_info("Using uniform weights: w(edge) = 1 (hop count only)")
        
        # Initialize
        distances = {c: float('inf') for c in self.metrics.cluster_metrics.keys()}
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
                
            # Explore neighbors
            for v in self.metrics.topology.get(u, []):
                # Uniform weight = 1
                new_dist = dist + 1
                
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
            current = predecessors.get(current)
            if current is None:
                return [], float('inf')
        path.append(src)
        path.reverse()
        
        print_success(f"Path found: {' → '.join(f'C{c}' for c in path)}")
        print_info(f"Total cost: {distances[dst]:.2f} hops")
        
        return path, distances[dst]
    
    def cluster_aware_weighted_dijkstra(self, src: int, dst: int, 
                                       alpha: float = 0.4, beta: float = 0.3, 
                                       gamma: float = 0.3) -> Tuple[List[int], float]:
        """
        Algorithm 3: Cluster-Aware Weighted Dijkstra
        Edge weight = α·D_norm + β·L_norm + γ·C_intra
        """
        print_section(f"Algorithm 3: Cluster-Aware Weighted Dijkstra (C{src} → C{dst})")
        print_info(f"Weight formula: w = α·delay + β·loss + γ·intra_cost")
        print_info(f"Parameters: α={alpha}, β={beta}, γ={gamma}")
        
        # Initialize
        distances = {c: float('inf') for c in self.metrics.cluster_metrics.keys()}
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
                
            # Explore neighbors
            for v in self.metrics.topology.get(u, []):
                # Calculate composite weight
                link_metrics = self.metrics.intercluster_links.get((u, v), {})
                norm_delay = link_metrics.get('norm_delay', 0.0)
                norm_loss = link_metrics.get('norm_loss', 0.0)
                intra_cost = self.intra_cluster_costs.get(u, 0.0)
                
                weight = alpha * norm_delay + beta * norm_loss + gamma * intra_cost
                new_dist = dist + weight
                
                print(f"  Edge C{u}→C{v}: delay={norm_delay:.3f}, loss={norm_loss:.3f}, "
                      f"intra={intra_cost:.3f} → weight={weight:.3f}")
                
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
            current = predecessors.get(current)
            if current is None:
                return [], float('inf')
        path.append(src)
        path.reverse()
        
        print_success(f"Path found: {' → '.join(f'C{c}' for c in path)}")
        print_info(f"Total cost: {distances[dst]:.4f}")
        
        return path, distances[dst]
    
    def install_flows(self, path: List[int], algorithm: str):
        """Simulate flow installation to CCs along path"""
        print(f"\n{Colors.OKGREEN}[AC] Installing flows for path: "
              f"{' → '.join(f'C{c}' for c in path)}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}Algorithm used: {algorithm}{Colors.ENDC}")
        
        for i, cluster in enumerate(path):
            if i == 0:
                role = "Source"
            elif i == len(path) - 1:
                role = "Destination"
            else:
                role = "Intermediate"
            print(f"  → CC-{cluster}: Role={role}")


def calculate_path_metrics(path: List[int], metrics: NetworkMetrics) -> Dict:
    """Calculate actual path performance metrics"""
    if len(path) < 2:
        return {'delay': 0, 'loss': 0, 'hops': 0}
    
    total_delay = 0
    total_loss = 0
    
    for i in range(len(path) - 1):
        src, dst = path[i], path[i+1]
        link = metrics.intercluster_links.get((src, dst), {})
        total_delay += link.get('delay', 0)
        total_loss += link.get('loss', 0)
        
        # Add intra-cluster delay for source cluster
        cluster_metric = metrics.cluster_metrics.get(src, {})
        total_delay += cluster_metric.get('delay', 0)
    
    return {
        'delay': total_delay,
        'loss': total_loss / (len(path) - 1) if len(path) > 1 else 0,
        'hops': len(path) - 1
    }


def compare_algorithms(ac: AggregationController, flows: List[Tuple[int, int]]):
    """Compare baseline vs cluster-aware routing for multiple flows"""
    print_header("ROUTING ALGORITHM COMPARISON")
    
    results = {
        'baseline': {'paths': [], 'delays': [], 'losses': [], 'hops': []},
        'cluster_aware': {'paths': [], 'delays': [], 'losses': [], 'hops': []}
    }
    
    for src, dst in flows:
        print(f"\n{Colors.BOLD}{'─'*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}Flow: C{src} → C{dst}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'─'*80}{Colors.ENDC}")
        
        # Baseline algorithm
        base_path, base_cost = ac.baseline_dijkstra(src, dst)
        if base_path:
            base_metrics = calculate_path_metrics(base_path, ac.metrics)
            results['baseline']['paths'].append(base_path)
            results['baseline']['delays'].append(base_metrics['delay'])
            results['baseline']['losses'].append(base_metrics['loss'])
            results['baseline']['hops'].append(base_metrics['hops'])
            
            print(f"\n{Colors.OKCYAN}Baseline Performance:{Colors.ENDC}")
            print(f"  • End-to-end delay: {base_metrics['delay']:.2f} ms")
            print(f"  • Average loss: {base_metrics['loss']:.4f}")
            print(f"  • Hop count: {base_metrics['hops']}")
        
        time.sleep(0.5)  # Pause for readability
        
        # Cluster-aware algorithm
        aware_path, aware_cost = ac.cluster_aware_weighted_dijkstra(src, dst)
        if aware_path:
            aware_metrics = calculate_path_metrics(aware_path, ac.metrics)
            results['cluster_aware']['paths'].append(aware_path)
            results['cluster_aware']['delays'].append(aware_metrics['delay'])
            results['cluster_aware']['losses'].append(aware_metrics['loss'])
            results['cluster_aware']['hops'].append(aware_metrics['hops'])
            
            print(f"\n{Colors.OKGREEN}Cluster-Aware Performance:{Colors.ENDC}")
            print(f"  • End-to-end delay: {aware_metrics['delay']:.2f} ms")
            print(f"  • Average loss: {aware_metrics['loss']:.4f}")
            print(f"  • Hop count: {aware_metrics['hops']}")
        
        # Comparison
        if base_path and aware_path:
            delay_improvement = ((base_metrics['delay'] - aware_metrics['delay']) / 
                               base_metrics['delay'] * 100)
            loss_improvement = ((base_metrics['loss'] - aware_metrics['loss']) / 
                              base_metrics['loss'] * 100) if base_metrics['loss'] > 0 else 0
            
            print(f"\n{Colors.BOLD}Improvement:{Colors.ENDC}")
            print(f"  • Delay: {delay_improvement:+.1f}%")
            print(f"  • Loss: {loss_improvement:+.1f}%")
            
            if delay_improvement > 0:
                print_success("Cluster-aware routing provides better performance!")
            elif delay_improvement < -5:
                print_warning("Baseline routing performed better for this flow")
            else:
                print_info("Similar performance between algorithms")
        
        time.sleep(0.5)
    
    return results


def generate_comparison_plots(results: Dict):
    """Generate performance comparison plots"""
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend for headless environments
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print_warning("matplotlib not installed. Skipping plot generation.")
        print_info("Install with: pip install matplotlib")
        return
    
    print_section("Generating Performance Comparison Plots")
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    fig.suptitle('Routing Algorithm Performance Comparison', fontsize=14, fontweight='bold')
    
    # Plot 1: Average End-to-End Delay
    ax1 = axes[0]
    baseline_avg_delay = np.mean(results['baseline']['delays'])
    aware_avg_delay = np.mean(results['cluster_aware']['delays'])
    
    bars1 = ax1.bar(['Baseline\nDijkstra', 'Cluster-Aware\nWeighted'], 
                    [baseline_avg_delay, aware_avg_delay],
                    color=['#3498db', '#2ecc71'])
    ax1.set_ylabel('Average Delay (ms)', fontweight='bold')
    ax1.set_title('End-to-End Delay', fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.2f}ms',
                ha='center', va='bottom', fontweight='bold')
    
    # Plot 2: Average Packet Loss
    ax2 = axes[1]
    baseline_avg_loss = np.mean(results['baseline']['losses'])
    aware_avg_loss = np.mean(results['cluster_aware']['losses'])
    
    bars2 = ax2.bar(['Baseline\nDijkstra', 'Cluster-Aware\nWeighted'],
                    [baseline_avg_loss * 100, aware_avg_loss * 100],
                    color=['#3498db', '#2ecc71'])
    ax2.set_ylabel('Average Packet Loss (%)', fontweight='bold')
    ax2.set_title('Packet Loss Rate', fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)
    
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.3f}%',
                ha='center', va='bottom', fontweight='bold')
    
    # Plot 3: Average Hop Count
    ax3 = axes[2]
    baseline_avg_hops = np.mean(results['baseline']['hops'])
    aware_avg_hops = np.mean(results['cluster_aware']['hops'])
    
    bars3 = ax3.bar(['Baseline\nDijkstra', 'Cluster-Aware\nWeighted'],
                    [baseline_avg_hops, aware_avg_hops],
                    color=['#3498db', '#2ecc71'])
    ax3.set_ylabel('Average Hop Count', fontweight='bold')
    ax3.set_title('Path Length', fontweight='bold')
    ax3.grid(axis='y', alpha=0.3)
    
    for bar in bars3:
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}',
                ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    
    output_file = 'routing_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print_success(f"Saved plot to: {output_file}")
    
    # Note: plt.show() removed for headless operation
    # Graphs are saved to files and do not require display


def main():
    parser = argparse.ArgumentParser(
        description='Simulate and compare routing algorithms using NS-3 metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python routing_simulator.py \\
        --intercluster data/intercluster_links.csv \\
        --cluster data/cluster_metrics.csv \\
        --time 1
        """
    )
    parser.add_argument('--intercluster', required=True, 
                       help='Path to intercluster_links.csv from NS-3')
    parser.add_argument('--cluster', required=True,
                       help='Path to cluster_metrics.csv from NS-3')
    parser.add_argument('--time', type=int, default=1,
                       help='Time slice to use from CSV (default: 1)')
    parser.add_argument('--alpha', type=float, default=0.4,
                       help='Weight for delay in composite metric (default: 0.4)')
    parser.add_argument('--beta', type=float, default=0.3,
                       help='Weight for loss in composite metric (default: 0.3)')
    parser.add_argument('--gamma', type=float, default=0.3,
                       help='Weight for intra-cluster cost (default: 0.3)')
    
    args = parser.parse_args()
    
    print_header("SDN HIERARCHICAL ROUTING SIMULATOR")
    print(f"{Colors.BOLD}Simulating AC/CC interaction and routing strategies{Colors.ENDC}")
    print(f"{Colors.BOLD}Data source: NS-3 network simulation (time={args.time}){Colors.ENDC}")
    
    # Load metrics
    metrics = NetworkMetrics()
    metrics.load_intercluster_links(args.intercluster, args.time)
    metrics.load_cluster_metrics(args.cluster, args.time)
    metrics.normalize_metrics()
    
    # Create Cluster Controllers
    print_section("Initializing Cluster Controllers (CCs)")
    ccs = []
    for cid, cluster_metric in metrics.cluster_metrics.items():
        cc = ClusterController(cid, cluster_metric)
        ccs.append(cc)
        print_success(f"CC-{cid} initialized")
    
    # Create Aggregation Controller
    print_section("Initializing Aggregation Controller (AC)")
    ac = AggregationController(metrics)
    print_success("AC initialized")
    
    # Simulate CC → AC metric reporting
    time.sleep(1)
    ac.receive_cc_reports(ccs)
    
    # Define test flows (modify based on your topology)
    flows = [
        (1, 3),  # C1 → C3
        (2, 1),  # C2 → C1
        (3, 2),  # C3 → C2
    ]
    
    # Compare algorithms
    time.sleep(1)
    results = compare_algorithms(ac, flows)
    
    # Summary
    print_header("SIMULATION SUMMARY")
    
    baseline_avg_delay = sum(results['baseline']['delays']) / len(results['baseline']['delays'])
    aware_avg_delay = sum(results['cluster_aware']['delays']) / len(results['cluster_aware']['delays'])
    improvement = (baseline_avg_delay - aware_avg_delay) / baseline_avg_delay * 100
    
    print(f"{Colors.BOLD}Average End-to-End Delay:{Colors.ENDC}")
    print(f"  • Baseline Dijkstra: {baseline_avg_delay:.2f} ms")
    print(f"  • Cluster-Aware Weighted: {aware_avg_delay:.2f} ms")
    print(f"  • Improvement: {improvement:+.1f}%")
    
    if improvement > 0:
        print_success("Cluster-aware routing provides better overall performance!")
    
    # Generate plots
    time.sleep(1)
    generate_comparison_plots(results)
    
    print(f"\n{Colors.OKGREEN}{Colors.BOLD}Simulation complete!{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Use the terminal output for paper screenshots{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Use routing_comparison.png for performance graphs{Colors.ENDC}")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Simulation interrupted by user{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.FAIL}Error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
