"""
Unit tests for synchronization protocol module
"""

import unittest
import time
import threading
from ryu.custom.controller.sync_protocol import SyncProtocol, MessageContext, ClusterHealth


class TestMessageContext(unittest.TestCase):
    """Test MessageContext dataclass"""
    
    def test_message_context_creation(self):
        ctx = MessageContext(
            msg_id=1,
            cluster_id=1,
            timestamp=time.time(),
            msg_type="TEST"
        )
        self.assertEqual(ctx.msg_id, 1)
        self.assertEqual(ctx.cluster_id, 1)
        self.assertEqual(ctx.msg_type, "TEST")
        self.assertFalse(ctx.is_expired())
        self.assertTrue(ctx.should_retry())
    
    def test_message_expiry(self):
        old_time = time.time() - 20
        ctx = MessageContext(
            msg_id=1,
            cluster_id=1,
            timestamp=old_time,
            msg_type="TEST",
            timeout=10.0
        )
        self.assertTrue(ctx.is_expired())
        self.assertFalse(ctx.should_retry())


class TestClusterHealth(unittest.TestCase):
    """Test ClusterHealth tracking"""
    
    def test_cluster_health_initialization(self):
        health = ClusterHealth(cluster_id=1)
        self.assertEqual(health.cluster_id, 1)
        self.assertTrue(health.is_active)
        self.assertEqual(health.failure_count, 0)
        self.assertFalse(health.is_timeout(timeout=30.0))
    
    def test_mark_alive(self):
        health = ClusterHealth(cluster_id=1)
        health.failure_count = 5
        health.is_active = False
        
        health.mark_alive()
        
        self.assertTrue(health.is_active)
        self.assertEqual(health.failure_count, 0)
    
    def test_mark_failure(self):
        health = ClusterHealth(cluster_id=1)
        
        # Mark failures until inactive
        for _ in range(3):
            health.mark_failure()
        
        self.assertFalse(health.is_active)
        self.assertEqual(health.failure_count, 3)
    
    def test_timeout_detection(self):
        health = ClusterHealth(cluster_id=1)
        health.last_heartbeat = time.time() - 40
        
        self.assertTrue(health.is_timeout(timeout=30.0))
        self.assertFalse(health.is_timeout(timeout=50.0))


class TestSyncProtocol(unittest.TestCase):
    """Test SyncProtocol synchronization"""
    
    def setUp(self):
        self.sync = SyncProtocol(heartbeat_interval=1.0, heartbeat_timeout=5.0)
    
    def tearDown(self):
        self.sync.stop()
    
    def test_message_id_generation(self):
        msg_ids = set()
        for _ in range(100):
            msg_id = self.sync.next_msg_id()
            self.assertNotIn(msg_id, msg_ids)
            msg_ids.add(msg_id)
    
    def test_connection_registration(self):
        conn1 = "conn1"
        conn2 = "conn2"
        
        self.sync.register_connection(1, conn1)
        self.sync.register_connection(2, conn2)
        
        self.assertEqual(self.sync.get_connection(1), conn1)
        self.assertEqual(self.sync.get_connection(2), conn2)
        self.assertEqual(self.sync.get_cluster_id(conn1), 1)
        self.assertEqual(self.sync.get_cluster_id(conn2), 2)
    
    def test_connection_replacement(self):
        conn1 = "conn1"
        conn2 = "conn2"
        
        # Register initial connection
        self.sync.register_connection(1, conn1)
        self.assertEqual(self.sync.get_connection(1), conn1)
        
        # Replace with new connection
        self.sync.register_connection(1, conn2)
        self.assertEqual(self.sync.get_connection(1), conn2)
        self.assertIsNone(self.sync.get_cluster_id(conn1))
    
    def test_connection_unregistration(self):
        conn = "conn1"
        
        self.sync.register_connection(1, conn)
        cluster_id = self.sync.unregister_connection(conn)
        
        self.assertEqual(cluster_id, 1)
        self.assertIsNone(self.sync.get_connection(1))
        self.assertIsNone(self.sync.get_cluster_id(conn))
    
    def test_heartbeat_recording(self):
        self.sync.record_heartbeat(1)
        
        active_clusters = self.sync.get_active_clusters()
        self.assertIn(1, active_clusters)
        self.assertTrue(self.sync.is_cluster_active(1))
    
    def test_message_tracking(self):
        ctx = self.sync.track_message(1, "TEST_MSG")
        
        self.assertIsNotNone(ctx.msg_id)
        self.assertEqual(ctx.cluster_id, 1)
        self.assertEqual(ctx.msg_type, "TEST_MSG")
        
        # Acknowledge message
        acknowledged = self.sync.acknowledge_message(ctx.msg_id)
        self.assertTrue(acknowledged)
        
        # Try acknowledging again
        acknowledged = self.sync.acknowledge_message(ctx.msg_id)
        self.assertFalse(acknowledged)
    
    def test_message_queue(self):
        # Enqueue messages with different priorities
        self.assertTrue(self.sync.enqueue_message(2, 1, "low_priority"))
        self.assertTrue(self.sync.enqueue_message(1, 1, "high_priority"))
        self.assertTrue(self.sync.enqueue_message(3, 1, "lowest_priority"))
        
        # Dequeue should respect priority
        msg1 = self.sync.dequeue_message(timeout=1.0)
        self.assertIsNotNone(msg1)
        priority1, _, _, data1 = msg1
        self.assertEqual(priority1, 1)
        self.assertEqual(data1, "high_priority")
        
        msg2 = self.sync.dequeue_message(timeout=1.0)
        self.assertIsNotNone(msg2)
        priority2, _, _, data2 = msg2
        self.assertEqual(priority2, 2)
        self.assertEqual(data2, "low_priority")
    
    def test_concurrent_message_id_generation(self):
        """Test thread-safe message ID generation"""
        msg_ids = []
        lock = threading.Lock()
        
        def generate_ids():
            for _ in range(100):
                msg_id = self.sync.next_msg_id()
                with lock:
                    msg_ids.append(msg_id)
        
        threads = [threading.Thread(target=generate_ids) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Check all IDs are unique
        self.assertEqual(len(msg_ids), len(set(msg_ids)))
    
    def test_timeout_detection(self):
        """Test timeout detection in monitoring loop"""
        timeout_detected = threading.Event()
        
        def on_timeout(cid):
            if cid == 1:
                timeout_detected.set()
        
        self.sync.set_timeout_callback(on_timeout)
        
        # Register and record heartbeat
        self.sync.register_connection(1, "conn1")
        self.sync.record_heartbeat(1)
        
        # Wait for timeout (heartbeat_timeout is 5s, check every 0.5s)
        timeout_detected.wait(timeout=8.0)
        
        # Should have timed out
        self.assertTrue(timeout_detected.is_set())
        self.assertFalse(self.sync.is_cluster_active(1))
    
    def test_recovery_detection(self):
        """Test cluster recovery detection"""
        recovered = threading.Event()
        
        def on_recovery(cid):
            if cid == 1:
                recovered.set()
        
        self.sync.set_recovery_callback(on_recovery)
        
        # Register cluster
        self.sync.register_connection(1, "conn1")
        self.sync.record_heartbeat(1)
        
        # Wait for timeout
        time.sleep(6.0)
        self.assertFalse(self.sync.is_cluster_active(1))
        
        # Send heartbeat to recover
        self.sync.record_heartbeat(1)
        
        # Wait for recovery detection
        recovered.wait(timeout=2.0)
        self.assertTrue(recovered.is_set())
        self.assertTrue(self.sync.is_cluster_active(1))
    
    def test_stats_collection(self):
        """Test statistics collection"""
        self.sync.register_connection(1, "conn1")
        self.sync.register_connection(2, "conn2")
        self.sync.record_heartbeat(1)
        self.sync.record_heartbeat(2)
        self.sync.track_message(1, "TEST")
        self.sync.enqueue_message(1, 1, "data")
        
        stats = self.sync.get_stats()
        
        self.assertEqual(stats['active_clusters'], 2)
        self.assertEqual(stats['total_clusters'], 2)
        self.assertEqual(stats['active_connections'], 2)
        self.assertGreaterEqual(stats['pending_messages'], 0)
        self.assertGreaterEqual(stats['queue_size'], 0)


if __name__ == '__main__':
    unittest.main()
