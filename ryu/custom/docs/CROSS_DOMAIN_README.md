# 跨域通信测试完整解决方案

## 概述

本文档提供了在三台独立机器上进行跨域（多集群）SDN通信测试的完整解决方案。该方案实现了：

- **聚合控制器(AC)**: 中央控制器，负责跨域路径计算和流表下发协调
- **集群控制器(CC)**: 本地控制器，负责各自集群内的OpenFlow流表管理
- **自动拓扑发现**: 通过LLDP自动发现跨域链路
- **跨域路径计算**: AC根据拓扑信息计算最优跨域路径
- **分布式流表下发**: CC接收AC指令后在本域内下发OpenFlow流表

## 文档结构

```
ryu/custom/
├── docs/
│   ├── CROSS_DOMAIN_TEST.md          # 详细配置和测试文档（完整版）
│   ├── CROSS_DOMAIN_QUICKSTART.md    # 快速参考卡（速查版）
│   ├── MY_SIMPLE_SWITCH_INTEGRATION.md  # CC实现说明
│   └── SYNC_PROTOCOL.md              # 同步协议详情
├── scripts/
│   └── setup_cross_domain_test.sh    # 自动化配置脚本
├── controller/
│   ├── test_ac_controller.py         # AC实现（协议测试版）
│   └── test_cc_controller.py         # CC实现（协议测试版）
└── my_simple_switch_13.py            # CC实现（生产版，连接真实OVS）
```

## 拓扑架构

```
┌─────────────────────────────────────────────────────────────┐
│  机器1: 172.30.1.137 (控制器节点)                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │    AC    │  │   CC1    │  │   CC2    │                  │
│  │ :10000   │  │  :6653   │  │  :6654   │                  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
└───────┼─────────────┼─────────────┼────────────────────────┘
        │             │             │
        │             │             │
        └─────────────┼─────────────┼────────── AC ↔ CC 通信
                      │             │
                      │             │
        ┌─────────────┘             └─────────────┐
        │                                         │
        │ OpenFlow                    OpenFlow    │
        │                                         │
┌───────┴────────┐                       ┌───────┴────────┐
│  机器2:          │                       │  机器3:          │
│  192.168.179.133│  ←─── VXLAN 隧道 ───→ │ 172.168.157.128 │
│  ┌──────────┐   │                       │  ┌──────────┐   │
│  │ OVS br-c1│   │                       │  │ OVS br-c2│   │
│  │ (集群1)   │   │                       │  │ (集群2)   │   │
│  └────┬─────┘   │                       │  └────┬─────┘   │
│       │ veth-h1 │                       │       │ veth-h2 │
│  10.0.1.10/24   │                       │  10.0.2.20/24   │
└─────────────────┘                       └─────────────────┘
     集群1边界节点                              集群2边界节点
```

## 测试流程

```
1. 主机h1 (10.0.1.10) ping 主机h2 (10.0.2.20)
   ↓
2. OVS br-c1 收到数据包，查询流表未命中
   ↓
3. Packet-In 发送到 CC1
   ↓
4. CC1 检测到目标IP属于集群2（跨域流量）
   ↓
5. CC1 封装FlowRequest消息上报AC
   消息内容: {src_cluster: 1, dst_cluster: 2, match: {ip_dst: 10.0.2.20}}
   ↓
6. AC接收FlowRequest
   - 查询拓扑数据库
   - 计算跨域路径: [1, 2]
   - 确定边界端口信息
   ↓
7. AC生成FlowReply消息
   - 为集群1生成段: ingress=无, egress=vxlan-c2端口, tunnel_id=100
   - 为集群2生成段: ingress=vxlan-c1端口, egress=veth-h2端口
   ↓
8. AC分别发送FlowReply给CC1和CC2
   ↓
9. CC1接收FlowReply
   - 解析路径和段信息
   - 在br-c1上下发OpenFlow规则:
     match: ip_dst=10.0.2.20
     action: output:vxlan-c2
   ↓
10. CC2接收FlowReply
    - 解析路径和段信息
    - 在br-c2上下发OpenFlow规则:
      match: ip_dst=10.0.2.20
      action: output:veth-h2
   ↓
11. 流表下发完成，后续数据包可以直接转发
   ↓
12. ping成功！
```

## 快速开始

### 方式1: 使用自动化脚本（推荐）

在每台机器上运行：
```bash
cd /path/to/SDN
bash ryu/custom/scripts/setup_cross_domain_test.sh
```

根据提示选择机器角色（控制器节点/集群1边界/集群2边界）并配置。

### 方式2: 手动配置

参考详细文档 [CROSS_DOMAIN_TEST.md](CROSS_DOMAIN_TEST.md) 中的步骤三至五。

## 验证要点

### 1. 控制器连接验证

在机器1（控制器节点）的日志中查看：

**AC日志**:
```
[AC] Listening for CC connections on 0.0.0.0:10000...
[AC] HELLO from CC-1 v1.0
[AC] HELLO from CC-2 v1.0
[AC] Boundaries[1] -> ['dpid:0000000000000001']
[AC] Boundaries[2] -> ['dpid:0000000000000002']
```

**CC1日志**:
```
[CC] FLAGS OK cluster=1 boundaries=[] dst_clusters=[2] ac=172.30.1.137:10000
[CC] Persistent connection established to AC 172.30.1.137:10000
[CC] map dpid=1 -> name=dpid:0000000000000001
```

**CC2日志**:
```
[CC] FLAGS OK cluster=2 boundaries=[] dst_clusters=[1] ac=172.30.1.137:10000
[CC] Persistent connection established to AC 172.30.1.137:10000
[CC] map dpid=2 -> name=dpid:0000000000000002
```

### 2. 跨域链路发现验证

**CC1日志**:
```
[CC] LLDP跨域邻居: local=dpid:0000000000000001:1 peer_dpid=2:1 lk=lk-1:1-2:1
```

**AC日志**:
```
[AC] LinkUpdate from C1:
    key=lk-1:1-2:1 sw=dpid:0000000000000001 port=1
[AC] LinkUpdate from C2:
    key=lk-1:1-2:1 sw=dpid:0000000000000002 port=1
[AC] Cluster edges: [(1, 2)]
```

### 3. 跨域流量测试验证

在机器2执行:
```bash
ping -I veth-h1 10.0.2.20
```

**CC1日志（机器1）**:
```
[CC] *** CROSS-CLUSTER TRAFFIC DETECTED ***
[CC]     Source: 10.0.1.10 (cluster 1)
[CC]     Destination: 10.0.2.20 (cluster 2)
[CC] Sending FLOW_REQUEST to AC
```

**AC日志（机器1）**:
```
[AC] Calculating path: Cluster 1 → Cluster 2
[AC] Match fields: {'ip_dst': '10.0.2.20'}
[AC] FLOW_REPLY segment sent to cluster 1 for path [1, 2]
[AC] FLOW_REPLY segment sent to cluster 2 for path [1, 2]
```

**CC1和CC2日志（机器1）**:
```
[CC] Received FLOW_REPLY
[CC] Path: 1 → 2
```

### 4. 流表验证

在机器2:
```bash
sudo ovs-ofctl dump-flows br-c1 | grep "10.0.2.20"
```

应该看到类似的流表项（匹配目标IP 10.0.2.20）。

在机器3:
```bash
sudo ovs-ofctl dump-flows br-c2
```

应该看到相应的转发规则。

## 关键配置参数

### 控制器节点（机器1）

| 参数 | 值 | 说明 |
|------|-----|------|
| AC端口 | 10000 | AC监听端口，CC连接该端口 |
| CC1 OpenFlow端口 | 6653 | CC1监听端口，OVS连接该端口 |
| CC2 OpenFlow端口 | 6654 | CC2监听端口，OVS连接该端口 |
| CLUSTER_ID (CC1) | 1 | 集群1的ID |
| CLUSTER_ID (CC2) | 2 | 集群2的ID |

### 边界节点（机器2和3）

| 参数 | 机器2（集群1） | 机器3（集群2） |
|------|---------------|---------------|
| 网桥名称 | br-c1 | br-c2 |
| DataPath ID | 0000000000000001 | 0000000000000002 |
| 控制器地址 | tcp:172.30.1.137:6653 | tcp:172.30.1.137:6654 |
| 测试主机IP | 10.0.1.10/24 | 10.0.2.20/24 |
| VXLAN端口 | vxlan-c2 | vxlan-c1 |
| VXLAN远端IP | 172.168.157.128 | 192.168.179.133 |
| VXLAN Key | 100 | 100 |

## 故障排查流程图

```
┌─────────────────┐
│   ping不通？     │
└────────┬────────┘
         │
    ┌────▼─────┐ NO  ┌────────────────────┐
    │ AC收到   ├────►│ 检查CC到AC的连接    │
    │ Request? │     │ netstat -tlnp 10000│
    └────┬─────┘     └────────────────────┘
         │ YES
    ┌────▼─────┐ NO  ┌────────────────────┐
    │ AC计算出 ├────►│ 检查跨域链路发现    │
    │ 路径？   │     │ AC日志看Cluster edges│
    └────┬─────┘     └────────────────────┘
         │ YES
    ┌────▼─────┐ NO  ┌────────────────────┐
    │ CC收到   ├────►│ 检查AC到CC的连接    │
    │ Reply?   │     │ CC日志看FLOW_REPLY │
    └────┬─────┘     └────────────────────┘
         │ YES
    ┌────▼─────┐ NO  ┌────────────────────┐
    │ 流表下发 ├────►│ 检查OpenFlow连接    │
    │ 成功？   │     │ ovs-vsctl show     │
    └────┬─────┘     └────────────────────┘
         │ YES
    ┌────▼─────┐ NO  ┌────────────────────┐
    │ VXLAN隧道├────►│ 检查VXLAN配置      │
    │ 通？     │     │ ovs-vsctl list int │
    └────┬─────┘     └────────────────────┘
         │ YES
    ┌────▼─────┐
    │ 应该能通！│
    └──────────┘
```

## 性能测试

### 延迟测试
```bash
# 在机器2执行
ping -c 100 -I veth-h1 10.0.2.20
```

预期延迟: 根据网络环境，通常 < 10ms（局域网）

### 带宽测试
```bash
# 在机器3启动服务器
iperf -s -B 10.0.2.20

# 在机器2启动客户端
iperf -c 10.0.2.20 -B 10.0.1.10 -t 30
```

预期带宽: 取决于VXLAN隧道和物理网络，通常可达500Mbps+

### 吞吐量测试
```bash
# 测试小包处理能力
ping -f -I veth-h1 10.0.2.20  # flood ping
```

## 扩展场景

### 场景1: 添加第三个集群

1. 在机器1启动CC3:
   ```bash
   export CLUSTER_ID=3 AC_HOST=172.30.1.137 AC_PORT=10000 DST_CLUSTERS=1,2
   ryu-manager --observe-links --ofp-tcp-listen-port 6655 ryu/custom/my_simple_switch_13.py
   ```

2. 在新机器上配置OVS br-c3，连接到6655端口

3. 配置到其他集群的VXLAN隧道

### 场景2: 多个边界节点

每个集群可以有多个边界节点：
```bash
# CC配置中指定多个边界交换机
export BOUNDARY_SWITCHES="br1,br2,br3"
```

### 场景3: 使用物理端口代替VXLAN

如果机器直接连接或在同一L2网络：
```bash
# 在机器2
sudo ovs-vsctl add-port br-c1 eth1

# 在机器3
sudo ovs-vsctl add-port br-c2 eth1
```

## 常见问题(FAQ)

### Q1: 为什么第一个ping包会超时？
A: 第一个包用于触发路径发现和流表下发，这需要AC计算路径并通知CC下发流表，通常需要几百毫秒。后续包会直接转发。

### Q2: AC如何知道哪些端口是跨域链路？
A: CC通过LLDP协议自动发现跨域链路，并将发现的链路信息上报给AC。AC聚合来自所有CC的链路信息构建全局拓扑。

### Q3: 如果AC宕机会怎样？
A: 已下发的流表会继续工作，但无法处理新的跨域流量请求。建议实现AC的高可用性（HA）。

### Q4: 支持多路径负载均衡吗？
A: 当前实现计算单条路径。可以扩展AC的路径计算算法支持ECMP（等价多路径）。

### Q5: 如何监控系统状态？
A: 
- AC定期打印统计信息（活跃CC数量、待处理请求等）
- CC定期发送KEEPALIVE心跳
- 可通过日志或添加监控接口获取实时状态

### Q6: 流表有有效期吗？
A: OpenFlow流表支持idle_timeout和hard_timeout。当前实现使用默认设置（永久有效），可根据需要配置超时。

### Q7: 如何优化性能？
A:
- 使用proactive模式预下发流表（而非reactive）
- 使用硬件VTEP代替OVS VXLAN（更高性能）
- 优化AC的路径计算算法
- 使用流表缓存减少重复计算

## 贡献指南

欢迎改进和扩展！可以贡献的方向：

1. **功能增强**
   - 支持QoS和流量工程
   - 实现AC高可用（HA）
   - 添加负载均衡支持
   - 支持IPv6

2. **性能优化**
   - 优化路径计算算法
   - 实现流表预下发
   - 添加缓存机制

3. **可运维性**
   - 添加Web UI监控界面
   - 实现RESTful API
   - 添加告警机制
   - 集成日志聚合

4. **测试和文档**
   - 添加单元测试
   - 添加集成测试
   - 改进文档
   - 添加使用示例

## 相关资源

- [OpenFlow 1.3规范](https://www.opennetworking.org/software-defined-standards/specifications/)
- [Open vSwitch文档](http://docs.openvswitch.org/)
- [Ryu SDN框架](https://ryu.readthedocs.io/)
- [VXLAN RFC 7348](https://tools.ietf.org/html/rfc7348)

## 技术支持

遇到问题？
1. 查看 [CROSS_DOMAIN_TEST.md](CROSS_DOMAIN_TEST.md) 的故障排查章节
2. 查看 [CROSS_DOMAIN_QUICKSTART.md](CROSS_DOMAIN_QUICKSTART.md) 的快速排查命令
3. 提交Issue到GitHub仓库
4. 查看项目Wiki获取更多信息

## 许可证

本项目采用与主项目相同的许可证。
