"""
Synchronization Protocol Module for Multi-CC Communication

This module implements a synchronization protocol to ensure conflict-free
communication between multiple Cluster Controllers (CCs) and the Area Controller (AC).

Features:
- Message sequencing and acknowledgment
- Timeout and heartbeat mechanisms
- Thread-safe operations with locks
- Eventual consistency guarantees
- Modular design for future extensions (RL-routing, flow mechanisms)
"""

import threading
import time
from typing import Dict, Optional, Any, Callable, Set
from collections import defaultdict, deque
from dataclasses import dataclass, field
import queue


@dataclass
class MessageContext:
    """Context for tracking message lifecycle"""
    msg_id: int
    cluster_id: int
    timestamp: float
    msg_type: str
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 10.0
    
    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.timeout
    
    def should_retry(self) -> bool:
        return self.retry_count < self.max_retries and not self.is_expired()


@dataclass
class ClusterHealth:
    """Track health status of a cluster controller"""
    cluster_id: int
    last_heartbeat: float = field(default_factory=time.time)
    last_message: float = field(default_factory=time.time)
    is_active: bool = True
    failure_count: int = 0
    message_count: int = 0
    
    def mark_alive(self):
        """Mark cluster as alive with current timestamp"""
        self.last_heartbeat = time.time()
        self.is_active = True
        self.failure_count = 0
    
    def mark_message(self):
        """Record message activity"""
        self.last_message = time.time()
        self.message_count += 1
    
    def mark_failure(self):
        """Record a failure"""
        self.failure_count += 1
        if self.failure_count >= 3:
            self.is_active = False
    
    def is_timeout(self, timeout: float = 30.0) -> bool:
        """Check if cluster has timed out"""
        return time.time() - self.last_heartbeat > timeout


class SyncProtocol:
    """
    Synchronization protocol for managing CC-AC communication
    
    This class provides:
    - Message ordering and sequencing
    - Heartbeat monitoring
    - Connection management
    - Thread-safe operations
    """
    
    def __init__(self, heartbeat_interval: float = 10.0, 
                 heartbeat_timeout: float = 30.0,
                 max_pending: int = 1000):
        """
        Initialize synchronization protocol
        
        Args:
            heartbeat_interval: Interval between heartbeats in seconds
            heartbeat_timeout: Timeout for detecting dead CCs in seconds
            max_pending: Maximum number of pending messages
        """
        # Message tracking
        self._msg_counter = 0
        self._msg_counter_lock = threading.Lock()
        self._pending_messages: Dict[int, MessageContext] = {}
        self._pending_lock = threading.Lock()
        
        # Connection tracking
        self._cluster_conn: Dict[int, Any] = {}
        self._conn_cluster: Dict[Any, int] = {}
        self._conn_lock = threading.Lock()
        
        # Health monitoring
        self._cluster_health: Dict[int, ClusterHealth] = {}
        self._health_lock = threading.Lock()
        
        # Configuration
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.max_pending = max_pending
        
        # Message queue with priority
        self._message_queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_pending)
        
        # Callbacks
        self._on_cc_timeout: Optional[Callable[[int], None]] = None
        self._on_cc_recovered: Optional[Callable[[int], None]] = None
        
        # Monitoring thread
        self._stop_flag = threading.Event()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            name="sync-monitor", 
            daemon=True
        )
        self._monitor_thread.start()
    
    def next_msg_id(self) -> int:
        """Generate next message ID atomically"""
        with self._msg_counter_lock:
            self._msg_counter += 1
            return self._msg_counter
    
    def register_connection(self, cluster_id: int, conn: Any) -> None:
        """
        Register a connection for a cluster controller
        
        Args:
            cluster_id: Cluster identifier
            conn: Connection object (socket or similar)
        """
        with self._conn_lock:
            # Clean up old connection if exists
            old_conn = self._cluster_conn.get(cluster_id)
            if old_conn and old_conn is not conn:
                self._conn_cluster.pop(old_conn, None)
            
            self._cluster_conn[cluster_id] = conn
            self._conn_cluster[conn] = cluster_id
        
        # Initialize health tracking
        with self._health_lock:
            if cluster_id not in self._cluster_health:
                self._cluster_health[cluster_id] = ClusterHealth(cluster_id)
            self._cluster_health[cluster_id].mark_alive()
    
    def unregister_connection(self, conn: Any) -> Optional[int]:
        """
        Unregister a connection
        
        Args:
            conn: Connection object
            
        Returns:
            Cluster ID if found, None otherwise
        """
        with self._conn_lock:
            cluster_id = self._conn_cluster.pop(conn, None)
            if cluster_id is not None:
                # Only remove from cluster_conn if it still points to this conn
                if self._cluster_conn.get(cluster_id) is conn:
                    self._cluster_conn.pop(cluster_id, None)
        
        # Mark as potentially failed
        if cluster_id is not None:
            with self._health_lock:
                if cluster_id in self._cluster_health:
                    self._cluster_health[cluster_id].mark_failure()
        
        return cluster_id
    
    def get_connection(self, cluster_id: int) -> Optional[Any]:
        """Get active connection for a cluster"""
        with self._conn_lock:
            return self._cluster_conn.get(cluster_id)
    
    def get_cluster_id(self, conn: Any) -> Optional[int]:
        """Get cluster ID for a connection"""
        with self._conn_lock:
            return self._conn_cluster.get(conn)
    
    def record_heartbeat(self, cluster_id: int) -> None:
        """Record heartbeat from a cluster"""
        with self._health_lock:
            if cluster_id not in self._cluster_health:
                self._cluster_health[cluster_id] = ClusterHealth(cluster_id)
            
            was_inactive = not self._cluster_health[cluster_id].is_active
            self._cluster_health[cluster_id].mark_alive()
            
            # Notify recovery if cluster was previously inactive
            if was_inactive and self._on_cc_recovered:
                self._on_cc_recovered(cluster_id)
    
    def record_message(self, cluster_id: int) -> None:
        """Record message activity from a cluster"""
        with self._health_lock:
            if cluster_id not in self._cluster_health:
                self._cluster_health[cluster_id] = ClusterHealth(cluster_id)
            self._cluster_health[cluster_id].mark_message()
    
    def get_active_clusters(self) -> Set[int]:
        """Get set of active cluster IDs"""
        with self._health_lock:
            return {cid for cid, health in self._cluster_health.items() if health.is_active}
    
    def is_cluster_active(self, cluster_id: int) -> bool:
        """Check if a cluster is active"""
        with self._health_lock:
            health = self._cluster_health.get(cluster_id)
            return health.is_active if health else False
    
    def track_message(self, cluster_id: int, msg_type: str, 
                     timeout: float = 10.0, max_retries: int = 3) -> MessageContext:
        """
        Track a new message for eventual consistency
        
        Args:
            cluster_id: Cluster sending the message
            msg_type: Type of message
            timeout: Message timeout in seconds
            max_retries: Maximum retry attempts
            
        Returns:
            MessageContext for tracking the message
        """
        msg_id = self.next_msg_id()
        ctx = MessageContext(
            msg_id=msg_id,
            cluster_id=cluster_id,
            timestamp=time.time(),
            msg_type=msg_type,
            timeout=timeout,
            max_retries=max_retries
        )
        
        with self._pending_lock:
            self._pending_messages[msg_id] = ctx
        
        return ctx
    
    def acknowledge_message(self, msg_id: int) -> bool:
        """
        Acknowledge message completion
        
        Args:
            msg_id: Message identifier
            
        Returns:
            True if message was pending, False otherwise
        """
        with self._pending_lock:
            return self._pending_messages.pop(msg_id, None) is not None
    
    def enqueue_message(self, priority: int, cluster_id: int, 
                       message_data: Any) -> bool:
        """
        Enqueue a message for processing
        
        Args:
            priority: Message priority (lower = higher priority)
            cluster_id: Source cluster
            message_data: Message payload
            
        Returns:
            True if enqueued successfully, False if queue full
        """
        try:
            self._message_queue.put_nowait((priority, time.time(), cluster_id, message_data))
            return True
        except queue.Full:
            return False
    
    def dequeue_message(self, timeout: float = 1.0) -> Optional[tuple]:
        """
        Dequeue next message for processing
        
        Args:
            timeout: Timeout for waiting
            
        Returns:
            Tuple of (priority, timestamp, cluster_id, message_data) or None
        """
        try:
            return self._message_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _monitor_loop(self):
        """Background monitoring loop for health checks"""
        while not self._stop_flag.is_set():
            try:
                with self._health_lock:
                    now = time.time()
                    for cluster_id, health in list(self._cluster_health.items()):
                        if health.is_active and health.is_timeout(self.heartbeat_timeout):
                            health.is_active = False
                            print(f"[Sync] Cluster {cluster_id} timed out "
                                  f"(last heartbeat {now - health.last_heartbeat:.1f}s ago)")
                            if self._on_cc_timeout:
                                self._on_cc_timeout(cluster_id)
                
                # Clean up expired pending messages
                with self._pending_lock:
                    expired = [
                        msg_id for msg_id, ctx in self._pending_messages.items()
                        if ctx.is_expired()
                    ]
                    for msg_id in expired:
                        self._pending_messages.pop(msg_id, None)
                
                time.sleep(self.heartbeat_interval / 2)
            except Exception as e:
                print(f"[Sync] Monitor loop error: {e}")
                time.sleep(1.0)
    
    def set_timeout_callback(self, callback: Callable[[int], None]):
        """Set callback for CC timeout events"""
        self._on_cc_timeout = callback
    
    def set_recovery_callback(self, callback: Callable[[int], None]):
        """Set callback for CC recovery events"""
        self._on_cc_recovered = callback
    
    def stop(self):
        """Stop the synchronization protocol"""
        self._stop_flag.set()
        if self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get synchronization statistics"""
        with self._health_lock, self._pending_lock, self._conn_lock:
            return {
                'active_clusters': len([h for h in self._cluster_health.values() if h.is_active]),
                'total_clusters': len(self._cluster_health),
                'active_connections': len(self._cluster_conn),
                'pending_messages': len(self._pending_messages),
                'queue_size': self._message_queue.qsize(),
                'msg_counter': self._msg_counter,
            }
