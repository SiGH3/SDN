# Multi-CC Synchronization Protocol

## Overview

The Multi-CC Synchronization Protocol provides conflict-free communication between multiple Cluster Controllers (CCs) and the Area Controller (AC) in the distributed SDN architecture. It ensures data consistency, handles failures gracefully, and maintains eventual consistency across the system.

## Architecture

### Components

1. **SyncProtocol**: Core synchronization layer
   - Message sequencing and tracking
   - Heartbeat monitoring
   - Connection management
   - Health status tracking

2. **ThreadSafeStateManager**: State management layer
   - Thread-safe link endpoint storage
   - Cluster topology graph
   - Pending request queue
   - Batch operations support

3. **AC Controller**: Area Controller with synchronization
   - Processes messages from multiple CCs
   - Coordinates inter-cluster routing
   - Monitors CC health
   - Handles failover scenarios

## Features

### 1. Message Synchronization

**Message Tracking**:
- Each message is assigned a unique ID
- Messages are tracked until acknowledged
- Automatic timeout for stale messages
- Retry mechanism with exponential backoff

**Example**:
```python
from ryu.custom.controller.sync_protocol import SyncProtocol

sync = SyncProtocol()

# Track a message
ctx = sync.track_message(cluster_id=1, msg_type="LINK_UPDATE")

# Process message...

# Acknowledge completion
sync.acknowledge_message(ctx.msg_id)
```

### 2. Heartbeat Monitoring

**Health Tracking**:
- Periodic heartbeat from each CC
- Timeout detection for failed CCs
- Automatic recovery detection
- Configurable intervals and timeouts

**Configuration**:
```python
sync = SyncProtocol(
    heartbeat_interval=10.0,  # Check every 10 seconds
    heartbeat_timeout=30.0     # Timeout after 30 seconds
)

# Set callbacks
def on_timeout(cluster_id):
    print(f"Cluster {cluster_id} failed!")

def on_recovery(cluster_id):
    print(f"Cluster {cluster_id} recovered!")

sync.set_timeout_callback(on_timeout)
sync.set_recovery_callback(on_recovery)
```

### 3. Thread-Safe State Management

**Concurrent Access**:
- All state operations are protected by locks
- No race conditions during concurrent updates
- Atomic batch operations
- Consistent snapshots

**Example**:
```python
from ryu.custom.controller.state_manager import ThreadSafeStateManager

state = ThreadSafeStateManager()

# Thread-safe link update
state.update_link_endpoint("link1", cluster_id=1, "sw1", port_no=10)

# Thread-safe graph operations
state.add_cluster(1)
state.add_cluster(2)
state.add_edge(1, 2, link_key="link1")

# Calculate path safely
path = state.calculate_path(src=1, dst=3)
```

### 4. Eventual Consistency

**Pending Request Handling**:
- Requests queue when topology incomplete
- Automatic retry when topology changes
- Filtered processing for efficiency
- Guaranteed eventual delivery

### 5. Priority Message Queue

**Message Ordering**:
- Priority-based message processing
- Fair scheduling across CCs
- Prevents starvation
- Configurable queue size

## Testing

### Unit Tests

Run unit tests for individual components:

```bash
cd /home/runner/work/SDN/SDN
PYTHONPATH=/home/runner/work/SDN/SDN:$PYTHONPATH python ryu/tests/unit/test_sync_protocol.py
PYTHONPATH=/home/runner/work/SDN/SDN:$PYTHONPATH python ryu/tests/unit/test_state_manager.py
```

### Integration Tests

Run integration tests for multi-CC scenarios:

```bash
PYTHONPATH=/home/runner/work/SDN/SDN:$PYTHONPATH python ryu/tests/integration/test_multi_cc_sync.py
```

### Test Coverage

- **Sync Protocol**: 17 unit tests
- **State Manager**: 17 unit tests  
- **Integration**: 5 multi-CC scenario tests
- **Coverage**: Concurrent operations, failures, recovery, stress testing

## Configuration

### Recommended Settings

**Development/Testing**:
```python
SYNC = SyncProtocol(
    heartbeat_interval=5.0,   # Fast detection
    heartbeat_timeout=15.0,    # Short timeout
    max_pending=1000           # Moderate queue
)
```

**Production**:
```python
SYNC = SyncProtocol(
    heartbeat_interval=10.0,   # Balance load
    heartbeat_timeout=30.0,    # Avoid false positives
    max_pending=10000          # Large queue
)
```

## References

- [AC Controller Implementation](../controller/test_ac_controller.py)
- [Sync Protocol Module](../controller/sync_protocol.py)
- [State Manager Module](../controller/state_manager.py)
- [Unit Tests](../../tests/unit/)
- [Integration Tests](../../tests/integration/)
