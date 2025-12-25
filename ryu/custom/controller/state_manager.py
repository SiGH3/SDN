"""
Thread-Safe State Manager for AC Controller

This module provides thread-safe wrappers for managing distributed state
in the Area Controller, including topology, links, and pending requests.
"""

import threading
from typing import Dict, Set, List, Tuple, Optional, Any
from collections import defaultdict
from ryu.custom.controller.ac_topology import ClusterGraph


class ThreadSafeStateManager:
    """
    Thread-safe manager for AC controller state
    
    Provides synchronized access to:
    - Link endpoints (LINK_EP)
    - Cluster graph (GRAPH)
    - Pending requests (PENDING)
    """
    
    def __init__(self):
        # Link endpoint mapping: link_key -> { cluster_id: (switch_id, port_no) }
        self._link_ep: Dict[str, Dict[int, Tuple[str, int]]] = defaultdict(dict)
        self._link_ep_lock = threading.RLock()
        
        # Cluster topology graph
        self._graph = ClusterGraph()
        self._graph_lock = threading.RLock()
        
        # Pending flow requests
        self._pending: List[Dict[str, Any]] = []
        self._pending_lock = threading.RLock()
    
    # ==================== Link Endpoint Operations ====================
    
    def update_link_endpoint(self, link_key: str, cluster_id: int, 
                            switch_id: str, port_no: int) -> bool:
        """
        Update link endpoint information
        
        Args:
            link_key: Unique link identifier
            cluster_id: Cluster ID
            switch_id: Switch identifier
            port_no: Port number
            
        Returns:
            True if this is a new endpoint, False if updated existing
        """
        with self._link_ep_lock:
            is_new = cluster_id not in self._link_ep[link_key]
            self._link_ep[link_key][cluster_id] = (switch_id, port_no)
            return is_new
    
    def get_link_endpoint(self, link_key: str) -> Dict[int, Tuple[str, int]]:
        """Get all endpoints for a link"""
        with self._link_ep_lock:
            return dict(self._link_ep.get(link_key, {}))
    
    def get_all_link_endpoints(self) -> Dict[str, Dict[int, Tuple[str, int]]]:
        """Get all link endpoints (snapshot)"""
        with self._link_ep_lock:
            return {
                lk: dict(eps) 
                for lk, eps in self._link_ep.items()
            }
    
    def is_link_complete(self, link_key: str, min_endpoints: int = 2) -> bool:
        """Check if a link has enough endpoints to be valid"""
        with self._link_ep_lock:
            return len(self._link_ep.get(link_key, {})) >= min_endpoints
    
    def get_link_clusters(self, link_key: str) -> Set[int]:
        """Get cluster IDs connected by a link"""
        with self._link_ep_lock:
            return set(self._link_ep.get(link_key, {}).keys())
    
    # ==================== Graph Operations ====================
    
    def add_cluster(self, cluster_id: int) -> bool:
        """Add a cluster to the graph"""
        with self._graph_lock:
            return self._graph.add_cluster(cluster_id)
    
    def add_edge(self, cluster_a: int, cluster_b: int, link_key: str = None) -> bool:
        """Add an edge between clusters"""
        with self._graph_lock:
            return self._graph.add_edge(cluster_a, cluster_b, link_key)
    
    def update_topology(self, topo_msg: Any) -> Tuple[int, List[str], bool]:
        """Update cluster topology from message"""
        with self._graph_lock:
            return self._graph.update_topology(topo_msg)
    
    def update_edge_metric(self, cluster_a: int, cluster_b: int,
                          latency: float = None, load: float = None,
                          weight: float = None) -> bool:
        """Update edge metrics between clusters"""
        with self._graph_lock:
            return self._graph.update_edge_metric(
                cluster_a, cluster_b, latency, load, weight
            )
    
    def calculate_path(self, src: int, dst: int, policy: dict = None) -> List[int]:
        """Calculate best path between clusters"""
        with self._graph_lock:
            return self._graph.best_path(src, dst, policy or {})
    
    def build_segments(self, path: List[int]) -> List[Dict[str, Any]]:
        """Build flow segments from path"""
        with self._graph_lock:
            return self._graph.build_segments(path)
    
    def get_cluster_edges(self) -> Set[Tuple[int, int]]:
        """Get all cluster edges (snapshot)"""
        with self._graph_lock:
            return set(self._graph.cluster_edges)
    
    def get_cluster_boundaries(self, cluster_id: int) -> Set[str]:
        """Get boundary switches for a cluster"""
        with self._graph_lock:
            return set(self._graph.cluster_boundaries.get(cluster_id, []))
    
    # ==================== Pending Request Operations ====================
    
    def add_pending_request(self, conn: Any, src: int, dst: int, 
                           match: Dict[str, str]) -> None:
        """Add a pending flow request"""
        with self._pending_lock:
            self._pending.append({
                'conn': conn,
                'src': src,
                'dst': dst,
                'match': match
            })
    
    def get_pending_count(self) -> int:
        """Get number of pending requests"""
        with self._pending_lock:
            return len(self._pending)
    
    def process_pending_requests(self, 
                                processor: callable,
                                filter_clusters: Set[int] = None) -> int:
        """
        Process pending requests and remove successful ones
        
        Args:
            processor: Callable that takes (src, dst, match) and returns bool
            filter_clusters: Only process requests involving these clusters
            
        Returns:
            Number of requests successfully processed
        """
        with self._pending_lock:
            remaining = []
            processed_count = 0
            
            for req in self._pending:
                src, dst = req['src'], req['dst']
                
                # Skip if not in filter
                if filter_clusters and src not in filter_clusters and dst not in filter_clusters:
                    remaining.append(req)
                    continue
                
                # Try to process
                try:
                    success = processor(src, dst, req['match'])
                    if success:
                        processed_count += 1
                    else:
                        remaining.append(req)
                except Exception as e:
                    print(f"[StateManager] Error processing pending request: {e}")
                    remaining.append(req)
            
            self._pending[:] = remaining
            return processed_count
    
    def clear_pending_requests(self) -> int:
        """Clear all pending requests and return count"""
        with self._pending_lock:
            count = len(self._pending)
            self._pending.clear()
            return count
    
    # ==================== Batch Operations ====================
    
    def batch_update_links(self, updates: List[Tuple[str, int, str, int]]) -> Tuple[Set[str], Set[int]]:
        """
        Batch update multiple link endpoints
        
        Args:
            updates: List of (link_key, cluster_id, switch_id, port_no)
            
        Returns:
            Tuple of (changed_links, affected_clusters)
        """
        changed_links = set()
        affected_clusters = set()
        
        with self._link_ep_lock:
            for link_key, cluster_id, switch_id, port_no in updates:
                was_new = self.update_link_endpoint(link_key, cluster_id, switch_id, port_no)
                if was_new:
                    changed_links.add(link_key)
                    affected_clusters.add(cluster_id)
        
        return changed_links, affected_clusters
    
    def sync_link_to_graph(self, link_key: str) -> Set[int]:
        """
        Synchronize a link from LINK_EP to graph edges
        
        Args:
            link_key: Link to synchronize
            
        Returns:
            Set of affected cluster IDs
        """
        affected = set()
        
        with self._link_ep_lock, self._graph_lock:
            endpoints = self._link_ep.get(link_key, {})
            if len(endpoints) < 2:
                return affected
            
            cluster_ids = sorted(endpoints.keys())
            
            # Add all clusters to graph
            for cid in cluster_ids:
                self._graph.add_cluster(cid)
                affected.add(cid)
            
            # Add edges between all pairs
            for i in range(len(cluster_ids)):
                for j in range(i + 1, len(cluster_ids)):
                    self._graph.add_edge(cluster_ids[i], cluster_ids[j], link_key)
        
        return affected
    
    # ==================== Statistics and Debugging ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get state manager statistics"""
        with self._link_ep_lock, self._graph_lock, self._pending_lock:
            complete_links = sum(
                1 for eps in self._link_ep.values() if len(eps) >= 2
            )
            
            return {
                'total_links': len(self._link_ep),
                'complete_links': complete_links,
                'cluster_nodes': len(self._graph.cluster_boundaries),
                'cluster_edges': len(self._graph.cluster_edges),
                'pending_requests': len(self._pending),
            }
    
    def dump_state(self) -> Dict[str, Any]:
        """Dump complete state for debugging"""
        with self._link_ep_lock, self._graph_lock, self._pending_lock:
            return {
                'link_endpoints': {
                    lk: {cid: (sw, port) for cid, (sw, port) in eps.items()}
                    for lk, eps in self._link_ep.items()
                },
                'cluster_edges': sorted(list(self._graph.cluster_edges)),
                'cluster_boundaries': {
                    cid: sorted(list(bounds))
                    for cid, bounds in self._graph.cluster_boundaries.items()
                },
                'pending_count': len(self._pending),
            }
