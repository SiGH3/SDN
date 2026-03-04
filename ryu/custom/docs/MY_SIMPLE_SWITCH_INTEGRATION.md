# 使用 my_simple_switch_13.py 作为CC与AC集成指南

## 概述

现在CC的实现在 `my_simple_switch_13.py` 中，它通过OpenFlow协议连接到真实的OVS交换机。此文档说明如何启动AC和多个CC实例，以测试分布式SDN架构的同步协议。

## 已实现的同步功能

### CC端 (my_simple_switch_13.py)
1. **心跳机制**: 每10秒向AC发送KEEPALIVE消息
2. **消息序列化**: 所有消息带有唯一msg_id用于追踪
3. **链路更新同步**: 使用消息ID和时间戳避免冲突
4. **自动重连**: AC断开后自动重连并重发HELLO

### AC端 (test_ac_controller.py)
1. **SyncProtocol**: 心跳监控、超时检测、连接管理
2. **StateManager**: 线程安全的状态管理
3. **健康追踪**: 监控每个CC的健康状态
4. **统计报告**: 每30秒打印活跃CC数量

## 启动步骤

### 1. 启动AC控制器

```bash
cd ~/SDN
export PYTHONPATH=~/SDN:$PYTHONPATH
python3 -m ryu.custom.controller.test_ac_controller 10000
```

**预期输出**:
```
[AC] Listening for CC connections on 0.0.0.0:10000...
```

### 2. 启动CC实例（连接到OVS）

每个CC需要独立的终端窗口。

**CC1 (集群1)**:
```bash
cd ~/SDN
export PYTHONPATH=~/SDN:$PYTHONPATH
export CLUSTER_ID=1
export AC_HOST=127.0.0.1
export AC_PORT=10000
ryu-manager --observe-links ryu/custom/my_simple_switch_13.py
```

**CC2 (集群2)**:
```bash
cd ~/SDN
export PYTHONPATH=~/SDN:$PYTHONPATH
export CLUSTER_ID=2
export AC_HOST=127.0.0.1
export AC_PORT=10000
ryu-manager --observe-links ryu/custom/my_simple_switch_13.py
```

**CC3 (集群3)**:
```bash
cd ~/SDN
export PYTHONPATH=~/SDN:$PYTHONPATH
export CLUSTER_ID=3
export AC_HOST=127.0.0.1
export AC_PORT=10000
ryu-manager --observe-links ryu/custom/my_simple_switch_13.py
```

### 3. 连接OVS交换机

在每个CC对应的网络域中，启动OVS交换机并连接到相应的CC：

**集群1的交换机**:
```bash
# 假设CC1监听在6633端口（Ryu默认）
sudo ovs-vsctl set-controller br0 tcp:127.0.0.1:6633
```

**集群2的交换机**:
```bash
# 需要指定不同的控制器端口
# 在启动CC2时添加: --ofp-tcp-listen-port 6634
sudo ovs-vsctl set-controller br1 tcp:127.0.0.1:6634
```

**集群3的交换机**:
```bash
# 在启动CC3时添加: --ofp-tcp-listen-port 6635
sudo ovs-vsctl set-controller br2 tcp:127.0.0.1:6635
```

## 预期日志输出

### AC端日志
```
[AC] HELLO from CC-1 v1.0
[AC] Boundaries[1] -> []
[AC] HELLO from CC-2 v1.0
[AC] Boundaries[2] -> []
[AC] KEEPALIVE from cluster 1
[AC] KEEPALIVE from cluster 2
[AC] LinkUpdate from C1:
    key=lk-... sw=s1 port=1
[AC] Stats - Sync: {'active_clusters': 2, ...}
```

### CC端日志
```
[CC] FLAGS OK cluster=1 boundaries=[] dst_clusters=[] ac=127.0.0.1:10000
[CC] Persistent connection established to AC 127.0.0.1:10000
[CC] ports dpid=1 -> [1, 2, 3]
[CC] Heartbeat sent to AC
[CC] LLDP跨域邻居: local=s1:1 peer_dpid=0x02:2 lk=lk-1:1-2:2 msg_id=5
[CC] RE-ADVERTISE lk=lk-1:1-2:2 s1:1 <-> dpid:0x02:2 msg_id=12
```

## 环境变量配置

### CC端可配置环境变量
- `CLUSTER_ID`: 集群编号 (默认: 1)
- `AC_HOST`: AC的IP地址 (默认: 127.0.0.1)
- `AC_PORT`: AC的监听端口 (默认: 10000)
- `LINK_REANNOUNCE_SEC`: 链路重发周期秒数 (默认: 10)
- `BOUNDARY_SWITCHES`: 边界交换机名称，逗号分隔 (默认: 自动发现)
- `DST_CLUSTERS`: 目标集群列表，逗号分隔 (可选)

### 示例：配置多个边界交换机
```bash
export CLUSTER_ID=1
export AC_HOST=192.168.1.100
export AC_PORT=10000
export BOUNDARY_SWITCHES="s1,s2"
export DST_CLUSTERS="2,3"
ryu-manager --observe-links ryu/custom/my_simple_switch_13.py
```

## 同步机制说明

### 1. 心跳监控
- **CC→AC**: 每10秒发送KEEPALIVE
- **AC监控**: 30秒内未收到心跳视为超时
- **超时处理**: AC触发回调，可以标记CC为失效

### 2. 消息追踪
- 每条消息都有唯一的`msg_id`
- AC可以追踪消息处理状态
- 便于调试和问题定位

### 3. 链路同步
- CC检测到跨域链路后立即上报
- 每10秒重新通告一次（防止丢失）
- AC聚合来自所有CC的链路信息

### 4. 冲突避免
- AC使用线程安全的StateManager
- 所有状态更新都有锁保护
- 并发消息不会导致数据不一致

## 测试验证

### 1. 验证心跳
观察AC日志，应该看到定期的KEEPALIVE消息：
```
[AC] KEEPALIVE from cluster 1
[AC] KEEPALIVE from cluster 2
```

### 2. 验证统计
AC每30秒打印统计信息：
```
[AC] Stats - Sync: {'active_clusters': 2, 'total_clusters': 2, 'active_connections': 2, ...}
```

### 3. 验证链路发现
当CC检测到跨域链路时：
- CC日志显示: `[CC] LLDP跨域邻居: ...`
- AC日志显示: `[AC] LinkUpdate from C1:`

### 4. 模拟CC失效
停止一个CC (Ctrl+C)，观察AC日志：
```
[Sync] Cluster 1 timed out (last heartbeat 30.0s ago)
[AC] *** Cluster 1 TIMEOUT detected ***
```

## 故障排查

### 问题1: CC无法连接到AC
**症状**: CC日志显示 "AC send failed, reconnecting..."

**解决方案**:
1. 确认AC已启动且监听在正确端口: `netstat -tlnp | grep 10000`
2. 检查防火墙设置
3. 验证AC_HOST和AC_PORT环境变量

### 问题2: AC收不到心跳
**症状**: AC显示 "Cluster X timed out"

**解决方案**:
1. 检查CC是否正常运行
2. 查看CC日志确认心跳发送: `[CC] Heartbeat sent to AC`
3. 检查网络连接

### 问题3: 链路信息不同步
**症状**: AC未显示跨域链路

**解决方案**:
1. 确认交换机间有物理/虚拟连接
2. 检查LLDP是否正常工作
3. 查看CC日志确认LLDP检测: `[CC] LLDP跨域邻居: ...`

## 与test_cc_controller的区别

| 特性 | test_cc_controller.py | my_simple_switch_13.py |
|-----|----------------------|------------------------|
| 用途 | 协议测试，不连接OVS | 生产使用，连接真实OVS |
| OpenFlow | 不支持 | 完整支持 |
| LLDP | 不支持 | 自动发送和接收 |
| 拓扑发现 | 手动配置 | 自动发现 |
| 适用场景 | 单元测试、协议验证 | 实际网络部署 |

## 下一步

1. **性能测试**: 使用3个以上CC并发测试
2. **故障恢复**: 测试CC重启后的恢复
3. **负载测试**: 大量链路更新消息
4. **集成RL路由**: 在AC中集成强化学习路由算法

## 参考文档

- [同步协议详情](SYNC_PROTOCOL.md)
- [完整解决方案](MULTI_CC_SYNC_FIX.md)
- [三集群演示](demo/3cluster-demo.md)
