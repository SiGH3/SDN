#!/usr/bin/env python3
"""
Test script for the new routing algorithms:
1. Baseline: Dijkstra shortest path
2. Improved: Cluster-aware weighted Dijkstra
"""

from ryu.custom.controller.ac_topology import ClusterGraph, ROUTING_POLICY

def test_baseline_dijkstra():
    """Test Algorithm 1: Cluster-Level Shortest Path (Baseline)"""
    print("\n" + "="*60)
    print("Test 1: Baseline Dijkstra Algorithm")
    print("="*60)
    
    # Create graph: C1 -- C2 -- C3 -- C4
    #                     |           |
    #                     +--- C5 ----+
    graph = ClusterGraph()
    
    # Add clusters
    for cid in [1, 2, 3, 4, 5]:
        graph.add_cluster(cid)
    
    # Add edges (uniform weight = 1)
    graph.add_edge(1, 2)
    graph.add_edge(2, 3)
    graph.add_edge(3, 4)
    graph.add_edge(2, 5)
    graph.add_edge(5, 4)
    
    print(f"Cluster edges: {sorted(graph.cluster_edges)}")
    
    # Test path calculation using Dijkstra
    policy = {"algorithm": "dijkstra", "metric": "hops"}
    
    test_cases = [
        (1, 4, [1, 2, 3, 4]),  # Expected: 1->2->3->4 (3 hops)
        (1, 5, [1, 2, 5]),     # Expected: 1->2->5 (2 hops)
        (1, 3, [1, 2, 3]),     # Expected: 1->2->3 (2 hops)
        (4, 1, [4, 3, 2, 1]),  # Expected: 4->3->2->1 (3 hops)
    ]
    
    all_passed = True
    for src, dst, expected in test_cases:
        path = graph.dijkstra_shortest_path(src, dst, policy)
        status = "✓" if path == expected else "✗"
        all_passed = all_passed and (path == expected)
        print(f"{status} Path C{src}->C{dst}: {path} (expected: {expected})")
    
    print(f"\nBaseline Dijkstra: {'PASSED' if all_passed else 'FAILED'}")
    return all_passed


def test_cluster_aware_weighted():
    """Test Algorithm 3: Cluster-Aware Weighted Path Computation"""
    print("\n" + "="*60)
    print("Test 2: Cluster-Aware Weighted Dijkstra")
    print("="*60)
    
    # Create a better example graph with two alternative paths
    # C1 -- C2 -- C3 -- C4
    #  |               /
    #  +---- C5 ------+
    graph = ClusterGraph()
    
    # Add clusters
    for cid in [1, 2, 3, 4, 5]:
        graph.add_cluster(cid)
    
    # Add edges
    graph.add_edge(1, 2)  # C1 -> C2
    graph.add_edge(2, 3)  # C2 -> C3
    graph.add_edge(3, 4)  # C3 -> C4
    graph.add_edge(1, 5)  # C1 -> C5
    graph.add_edge(5, 4)  # C5 -> C4
    
    # Set intra-cluster costs (simulating CC reports)
    graph.update_intra_cluster_cost(1, cost=1.0)  # C1: 1 hop internal
    graph.update_intra_cluster_cost(2, cost=5.0)  # C2: 5 hops internal (very expensive!)
    graph.update_intra_cluster_cost(3, cost=5.0)  # C3: 5 hops internal (very expensive!)
    graph.update_intra_cluster_cost(4, cost=1.0)  # C4: 1 hop internal
    graph.update_intra_cluster_cost(5, cost=1.0)  # C5: 1 hop internal
    
    print(f"Cluster edges: {sorted(graph.cluster_edges)}")
    print("Intra-cluster costs:")
    for cid in [1, 2, 3, 4, 5]:
        cost = graph.intra_cluster_costs[cid].get("cost", 0)
        print(f"  C{cid}: {cost}")
    
    # Test WITHOUT intra-cluster costs (should prefer shorter hop path)
    print("\n--- Without intra-cluster costs (baseline) ---")
    policy_no_intra = {
        "algorithm": "cluster_aware",
        "metric": "hops",
        "use_intra_cluster_cost": False
    }
    
    path1 = graph.cluster_aware_weighted_path(1, 4, policy_no_intra)
    print(f"Path C1->C4 (no intra-cost): {path1}")
    print(f"  Both paths have 2 inter-cluster hops, so either is valid")
    
    # Calculate and compare path costs WITHOUT intra-costs
    paths_to_compare = [
        [1, 2, 3, 4],  # Path through C2, C3
        [1, 5, 4],     # Path through C5
    ]
    print(f"\n  Path comparison (no intra-costs):")
    for p in paths_to_compare:
        cost = 0.0
        for i in range(len(p) - 1):
            cost += 1.0  # Each inter-cluster link = 1
        print(f"    {p}: cost = {cost}")
    
    # Test WITH intra-cluster costs (should prefer C5 path)
    print("\n--- With intra-cluster costs ---")
    policy_with_intra = {
        "algorithm": "cluster_aware",
        "metric": "hops",
        "use_intra_cluster_cost": True
    }
    
    path2 = graph.cluster_aware_weighted_path(1, 4, policy_with_intra)
    print(f"Path C1->C4 (with intra-cost): {path2}")
    print(f"  Expected: [1, 5, 4] (avoids expensive C2 and C3)")
    
    # Calculate and compare path costs WITH intra-costs
    print(f"\n  Path comparison (with intra-costs):")
    for p in paths_to_compare:
        cost = 0.0
        breakdown = []
        for i in range(len(p) - 1):
            src_c = p[i]
            inter_cost = 1.0
            intra_cost = graph.intra_cluster_costs[src_c].get("cost", 0.0)
            hop_cost = inter_cost + intra_cost
            cost += hop_cost
            breakdown.append(f"{src_c}->: inter={inter_cost}+intra={intra_cost}={hop_cost}")
        print(f"    {p}: cost = {cost}")
        for b in breakdown:
            print(f"        {b}")
    
    # The path through C5 should be chosen (cost = 4.0 vs 16.0)
    passed = path2 == [1, 5, 4]
    print(f"\nCluster-Aware Weighted: {'PASSED' if passed else 'FAILED'}")
    if not passed:
        print(f"  Note: Expected [1, 5, 4], got {path2}")
    return passed


def test_policy_selection():
    """Test algorithm selection via policy"""
    print("\n" + "="*60)
    print("Test 3: Algorithm Selection via Policy")
    print("="*60)
    
    graph = ClusterGraph()
    
    # Simple linear graph: C1 -- C2 -- C3
    for cid in [1, 2, 3]:
        graph.add_cluster(cid)
    graph.add_edge(1, 2)
    graph.add_edge(2, 3)
    
    print(f"Cluster edges: {sorted(graph.cluster_edges)}")
    
    # Test different algorithm selections
    algorithms = [
        ("dijkstra", "Baseline Dijkstra"),
        ("cluster_aware", "Cluster-Aware Weighted"),
        ("dfs", "Legacy DFS"),
    ]
    
    all_passed = True
    for algo, desc in algorithms:
        policy = {"algorithm": algo, "max_hops": 8, "max_paths": 128}
        path = graph.best_path(1, 3, policy)
        expected = [1, 2, 3]
        status = "✓" if path == expected else "✗"
        all_passed = all_passed and (path == expected)
        print(f"{status} {desc:30s}: {path}")
    
    print(f"\nAlgorithm Selection: {'PASSED' if all_passed else 'FAILED'}")
    return all_passed


def main():
    print("\n" + "#"*60)
    print("# Testing New Routing Algorithms")
    print("#"*60)
    
    results = []
    
    # Run tests
    results.append(("Baseline Dijkstra", test_baseline_dijkstra()))
    results.append(("Cluster-Aware Weighted", test_cluster_aware_weighted()))
    results.append(("Algorithm Selection", test_policy_selection()))
    
    # Summary
    print("\n" + "#"*60)
    print("# Test Summary")
    print("#"*60)
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:12s} - {test_name}")
    
    all_passed = all(passed for _, passed in results)
    print(f"\n{'='*60}")
    print(f"Overall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print(f"{'='*60}\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
