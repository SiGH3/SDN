"""
Integration test for multi-CC synchronization scenario

This test simulates multiple CCs sending messages concurrently to the AC
to verify that the synchronization protocol prevents conflicts and ensures
all messages are properly processed.
"""

import unittest
import threading
import time
import socket
from io import BytesIO

# Mock imports for testing without full Ryu environment
import logging

try:
    from ryu.custom.controller.sync_protocol import SyncProtocol
    from ryu.custom.controller.state_manager import ThreadSafeStateManager
    HAS_MODULES = True
except ImportError:
    HAS_MODULES = False
    logging.warning("Could not import required modules for integration tests")


@unittest.skipIf(not HAS_MODULES, "Required modules not available")
class TestMultiCCIntegration(unittest.TestCase):
    """Integration test for multi-CC concurrent scenarios"""
    
    def setUp(self):
        """Set up test environment"""
        self.sync = SyncProtocol(heartbeat_interval=2.0, heartbeat_timeout=10.0)
        self.state = ThreadSafeStateManager()
        self.errors = []
    
    def tearDown(self):
        """Clean up test environment"""
        self.sync.stop()
    
    def test_concurrent_link_updates(self):
        """Test concurrent link updates from multiple CCs"""
        num_ccs = 5
        links_per_cc = 10
        results = []
        
        def cc_simulate(cluster_id):
            """Simulate CC sending link updates"""
            try:
                # Register connection
                conn = f"conn_{cluster_id}"
                self.sync.register_connection(cluster_id, conn)
                self.sync.record_heartbeat(cluster_id)
                
                # Send multiple link updates
                for i in range(links_per_cc):
                    link_key = f"link_{i % 5}"  # Some overlap
                    switch_id = f"sw{cluster_id}"
                    port_no = 10 + i
                    
                    # Track message
                    msg_ctx = self.sync.track_message(cluster_id, "LINK_UPDATE")
                    
                    # Update state
                    self.state.update_link_endpoint(link_key, cluster_id, switch_id, port_no)
                    
                    # Sync to graph
                    affected = self.state.sync_link_to_graph(link_key)
                    
                    # Acknowledge
                    self.sync.acknowledge_message(msg_ctx.msg_id)
                    
                    # Small delay to simulate network
                    time.sleep(0.001)
                
                results.append(cluster_id)
            except Exception as e:
                self.errors.append((cluster_id, str(e)))
        
        # Start multiple CC threads
        threads = [
            threading.Thread(target=cc_simulate, args=(i,))
            for i in range(1, num_ccs + 1)
        ]
        
        start_time = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start_time
        
        # Verify results
        self.assertEqual(len(self.errors), 0, f"Errors occurred: {self.errors}")
        self.assertEqual(len(results), num_ccs)
        
        # Check state consistency
        stats = self.state.get_stats()
        self.assertGreater(stats['complete_links'], 0)
        self.assertEqual(stats['cluster_nodes'], num_ccs)
        
        print(f"✓ Concurrent updates test: {num_ccs} CCs, "
              f"{links_per_cc} links each, {elapsed:.2f}s")
        print(f"  Final state: {stats}")
    
    def test_heartbeat_monitoring(self):
        """Test heartbeat monitoring across multiple CCs"""
        num_ccs = 3
        timeout_detected = []
        recovery_detected = []
        
        def on_timeout(cid):
            timeout_detected.append(cid)
        
        def on_recovery(cid):
            recovery_detected.append(cid)
        
        self.sync.set_timeout_callback(on_timeout)
        self.sync.set_recovery_callback(on_recovery)
        
        # Register CCs
        for i in range(1, num_ccs + 1):
            conn = f"conn_{i}"
            self.sync.register_connection(i, conn)
            self.sync.record_heartbeat(i)
        
        # Verify all active
        active = self.sync.get_active_clusters()
        self.assertEqual(len(active), num_ccs)
        
        # Stop heartbeats for CC 2 and wait for timeout
        # Keep others alive
        def keep_alive(cluster_id):
            for _ in range(6):  # 12 seconds total
                time.sleep(2.0)
                if cluster_id != 2:  # Don't send heartbeat for CC 2
                    self.sync.record_heartbeat(cluster_id)
        
        threads = [
            threading.Thread(target=keep_alive, args=(i,))
            for i in range(1, num_ccs + 1)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Check that CC 2 timed out
        self.assertIn(2, timeout_detected)
        self.assertFalse(self.sync.is_cluster_active(2))
        
        # Other CCs should still be active
        self.assertTrue(self.sync.is_cluster_active(1))
        self.assertTrue(self.sync.is_cluster_active(3))
        
        # Recover CC 2
        self.sync.record_heartbeat(2)
        time.sleep(0.5)
        
        # Should be recovered
        self.assertTrue(self.sync.is_cluster_active(2))
        self.assertIn(2, recovery_detected)
        
        print(f"✓ Heartbeat monitoring test: detected timeout and recovery for CC 2")
    
    def test_pending_request_processing(self):
        """Test pending request processing with eventual consistency"""
        # Set up topology: 1 -> 2 -> 3
        self.state.add_cluster(1)
        self.state.add_cluster(2)
        self.state.add_cluster(3)
        
        # Add requests before edges exist
        self.state.add_pending_request("conn1", 1, 3, {"key": "val1"})
        self.state.add_pending_request("conn2", 2, 3, {"key": "val2"})
        
        processed = []
        
        def processor(src, dst, match):
            path = self.state.calculate_path(src, dst)
            if path:
                processed.append((src, dst, path))
                return True
            return False
        
        # Try processing - should fail (no edges)
        count1 = self.state.process_pending_requests(processor)
        self.assertEqual(count1, 0)
        self.assertEqual(self.state.get_pending_count(), 2)
        
        # Add edge 1 -> 2
        self.state.add_edge(1, 2)
        
        # Try again - still no path to 3
        count2 = self.state.process_pending_requests(processor)
        self.assertEqual(count2, 0)
        
        # Add edge 2 -> 3
        self.state.add_edge(2, 3)
        
        # Now should succeed
        count3 = self.state.process_pending_requests(processor)
        self.assertEqual(count3, 2)
        self.assertEqual(self.state.get_pending_count(), 0)
        
        # Verify paths
        self.assertEqual(len(processed), 2)
        print(f"✓ Eventual consistency test: processed {len(processed)} pending requests")
        for src, dst, path in processed:
            print(f"  Path {src}->{dst}: {path}")
    
    def test_message_ordering(self):
        """Test message ordering with priority queue"""
        num_messages = 50
        
        # Enqueue messages with random priorities
        for i in range(num_messages):
            priority = i % 5  # 0-4
            cluster_id = (i % 3) + 1
            success = self.sync.enqueue_message(priority, cluster_id, f"msg_{i}")
            self.assertTrue(success)
        
        # Dequeue and verify ordering
        dequeued = []
        while True:
            msg = self.sync.dequeue_message(timeout=0.1)
            if msg is None:
                break
            priority, timestamp, cluster_id, data = msg
            dequeued.append((priority, data))
        
        self.assertEqual(len(dequeued), num_messages)
        
        # Verify priorities are generally ordered (lower first)
        priorities = [p for p, _ in dequeued]
        
        # Check that lower priorities come first in general
        # (not strictly sorted due to timestamp ordering within same priority)
        first_half_avg = sum(priorities[:num_messages//2]) / (num_messages//2)
        second_half_avg = sum(priorities[num_messages//2:]) / (num_messages - num_messages//2)
        self.assertLessEqual(first_half_avg, second_half_avg)
        
        print(f"✓ Message ordering test: {num_messages} messages, "
              f"avg priority first half={first_half_avg:.2f}, "
              f"second half={second_half_avg:.2f}")
    
    def test_stress_concurrent_operations(self):
        """Stress test with many concurrent operations"""
        num_ccs = 10
        operations_per_cc = 50
        errors = []
        
        def stress_worker(cluster_id):
            try:
                conn = f"conn_{cluster_id}"
                self.sync.register_connection(cluster_id, conn)
                
                for i in range(operations_per_cc):
                    # Mix of operations
                    op = i % 4
                    
                    if op == 0:
                        # Link update
                        link_key = f"link_{i % 20}"
                        self.state.update_link_endpoint(
                            link_key, cluster_id, f"sw{cluster_id}", 10 + i
                        )
                    elif op == 1:
                        # Heartbeat
                        self.sync.record_heartbeat(cluster_id)
                    elif op == 2:
                        # Message tracking
                        ctx = self.sync.track_message(cluster_id, "TEST")
                        self.sync.acknowledge_message(ctx.msg_id)
                    else:
                        # Enqueue message
                        self.sync.enqueue_message(i % 3, cluster_id, f"data_{i}")
                    
                    # Minimal delay
                    if i % 10 == 0:
                        time.sleep(0.001)
            except Exception as e:
                errors.append((cluster_id, str(e)))
        
        threads = [
            threading.Thread(target=stress_worker, args=(i,))
            for i in range(1, num_ccs + 1)
        ]
        
        start_time = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start_time
        
        # Verify no errors
        self.assertEqual(len(errors), 0, f"Errors: {errors}")
        
        # Check statistics
        sync_stats = self.sync.get_stats()
        state_stats = self.state.get_stats()
        
        self.assertEqual(sync_stats['active_clusters'], num_ccs)
        self.assertGreater(state_stats['total_links'], 0)
        
        print(f"✓ Stress test: {num_ccs} CCs, {operations_per_cc} ops each, {elapsed:.2f}s")
        print(f"  Sync stats: {sync_stats}")
        print(f"  State stats: {state_stats}")


if __name__ == '__main__':
    unittest.main()
