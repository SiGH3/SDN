"""
Unit tests for thread-safe state manager module
"""

import unittest
import threading
from ryu.custom.controller.state_manager import ThreadSafeStateManager
from ryu.custom.protocol import message_pb2


class TestThreadSafeStateManager(unittest.TestCase):
    """Test ThreadSafeStateManager"""
    
    def setUp(self):
        self.manager = ThreadSafeStateManager()
    
    def test_link_endpoint_update(self):
        """Test link endpoint updates"""
        is_new = self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.assertTrue(is_new)
        
        # Update same endpoint
        is_new = self.manager.update_link_endpoint("link1", 1, "sw1", 11)
        self.assertFalse(is_new)
        
        # Add different cluster
        is_new = self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        self.assertTrue(is_new)
    
    def test_get_link_endpoint(self):
        """Test retrieving link endpoints"""
        self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        
        endpoints = self.manager.get_link_endpoint("link1")
        self.assertEqual(len(endpoints), 2)
        self.assertIn(1, endpoints)
        self.assertIn(2, endpoints)
        self.assertEqual(endpoints[1], ("sw1", 10))
        self.assertEqual(endpoints[2], ("sw2", 20))
    
    def test_link_completion(self):
        """Test link completion detection"""
        self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.assertFalse(self.manager.is_link_complete("link1"))
        
        self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        self.assertTrue(self.manager.is_link_complete("link1"))
    
    def test_link_clusters(self):
        """Test getting clusters for a link"""
        self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        self.manager.update_link_endpoint("link1", 3, "sw3", 30)
        
        clusters = self.manager.get_link_clusters("link1")
        self.assertEqual(clusters, {1, 2, 3})
    
    def test_add_cluster(self):
        """Test adding clusters to graph"""
        result = self.manager.add_cluster(1)
        self.assertTrue(result)
        
        boundaries = self.manager.get_cluster_boundaries(1)
        self.assertIsNotNone(boundaries)
    
    def test_add_edge(self):
        """Test adding edges between clusters"""
        self.manager.add_cluster(1)
        self.manager.add_cluster(2)
        
        result = self.manager.add_edge(1, 2, "link1")
        self.assertTrue(result)
        
        edges = self.manager.get_cluster_edges()
        self.assertIn((1, 2), edges)
    
    def test_update_edge_metric(self):
        """Test updating edge metrics"""
        self.manager.add_cluster(1)
        self.manager.add_cluster(2)
        self.manager.add_edge(1, 2)
        
        result = self.manager.update_edge_metric(1, 2, latency=5.0, load=0.8)
        self.assertTrue(result)
    
    def test_calculate_path(self):
        """Test path calculation"""
        # Create simple 3-node path: 1 -> 2 -> 3
        self.manager.add_cluster(1)
        self.manager.add_cluster(2)
        self.manager.add_cluster(3)
        self.manager.add_edge(1, 2)
        self.manager.add_edge(2, 3)
        
        path = self.manager.calculate_path(1, 3)
        self.assertIsNotNone(path)
        self.assertEqual(path[0], 1)
        self.assertEqual(path[-1], 3)
    
    def test_pending_requests(self):
        """Test pending request management"""
        self.manager.add_pending_request("conn1", 1, 2, {"key": "value"})
        self.manager.add_pending_request("conn2", 2, 3, {"key": "value2"})
        
        count = self.manager.get_pending_count()
        self.assertEqual(count, 2)
    
    def test_process_pending_requests(self):
        """Test processing pending requests"""
        self.manager.add_pending_request("conn1", 1, 2, {"key": "value"})
        self.manager.add_pending_request("conn2", 2, 3, {"key": "value2"})
        
        processed = []
        
        def processor(src, dst, match):
            processed.append((src, dst))
            return src == 1  # Only process first request
        
        count = self.manager.process_pending_requests(processor)
        
        self.assertEqual(count, 1)
        self.assertEqual(len(processed), 2)
        self.assertEqual(self.manager.get_pending_count(), 1)
    
    def test_filtered_pending_processing(self):
        """Test filtered pending request processing"""
        self.manager.add_pending_request("conn1", 1, 2, {"key": "value"})
        self.manager.add_pending_request("conn2", 2, 3, {"key": "value2"})
        self.manager.add_pending_request("conn3", 3, 4, {"key": "value3"})
        
        def processor(src, dst, match):
            return True  # Process all
        
        # Only process requests involving cluster 2
        count = self.manager.process_pending_requests(processor, filter_clusters={2})
        
        # Should process 2 requests (1->2 and 2->3)
        self.assertEqual(count, 2)
        self.assertEqual(self.manager.get_pending_count(), 1)
    
    def test_batch_update_links(self):
        """Test batch link updates"""
        updates = [
            ("link1", 1, "sw1", 10),
            ("link1", 2, "sw2", 20),
            ("link2", 2, "sw2", 21),
            ("link2", 3, "sw3", 30),
        ]
        
        changed_links, affected_clusters = self.manager.batch_update_links(updates)
        
        self.assertEqual(len(changed_links), 2)
        self.assertIn("link1", changed_links)
        self.assertIn("link2", changed_links)
        self.assertEqual(affected_clusters, {1, 2, 3})
    
    def test_sync_link_to_graph(self):
        """Test synchronizing links to graph"""
        # Add link endpoints
        self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        
        # Sync to graph
        affected = self.manager.sync_link_to_graph("link1")
        
        self.assertEqual(affected, {1, 2})
        
        # Check edge was created
        edges = self.manager.get_cluster_edges()
        self.assertIn((1, 2), edges)
    
    def test_concurrent_link_updates(self):
        """Test thread-safe concurrent link updates"""
        def update_links(cluster_id):
            for i in range(100):
                link_key = f"link{i % 10}"
                self.manager.update_link_endpoint(
                    link_key, cluster_id, f"sw{cluster_id}", 10 + i
                )
        
        threads = [
            threading.Thread(target=update_links, args=(i,))
            for i in range(1, 6)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify all updates completed
        all_endpoints = self.manager.get_all_link_endpoints()
        self.assertGreater(len(all_endpoints), 0)
    
    def test_concurrent_graph_operations(self):
        """Test thread-safe concurrent graph operations"""
        def add_edges(start_cluster):
            for i in range(10):
                c1 = start_cluster + i
                c2 = start_cluster + i + 1
                self.manager.add_cluster(c1)
                self.manager.add_cluster(c2)
                self.manager.add_edge(c1, c2)
        
        threads = [
            threading.Thread(target=add_edges, args=(i * 10,))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Verify edges were added
        edges = self.manager.get_cluster_edges()
        self.assertGreater(len(edges), 0)
    
    def test_stats_collection(self):
        """Test statistics collection"""
        self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        self.manager.add_cluster(1)
        self.manager.add_cluster(2)
        self.manager.add_edge(1, 2)
        self.manager.add_pending_request("conn1", 1, 2, {})
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats['total_links'], 1)
        self.assertEqual(stats['complete_links'], 1)
        self.assertEqual(stats['cluster_nodes'], 2)
        self.assertEqual(stats['cluster_edges'], 1)
        self.assertEqual(stats['pending_requests'], 1)
    
    def test_state_dump(self):
        """Test state dumping for debugging"""
        self.manager.update_link_endpoint("link1", 1, "sw1", 10)
        self.manager.update_link_endpoint("link1", 2, "sw2", 20)
        self.manager.add_cluster(1)
        self.manager.add_cluster(2)
        self.manager.add_edge(1, 2)
        
        state = self.manager.dump_state()
        
        self.assertIn('link_endpoints', state)
        self.assertIn('cluster_edges', state)
        self.assertIn('cluster_boundaries', state)
        self.assertIn('pending_count', state)


if __name__ == '__main__':
    unittest.main()
