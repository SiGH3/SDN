# 跨域通信测试配置与方法

## 一、测试场景说明

本文档描述如何在三台独立的VMware Ubuntu虚拟机上进行跨域通信测试：

### 拓扑结构
- **机器1（控制器节点）**: IP 172.30.1.137
  - 运行AC（聚合控制器）: 端口 10000
  - 运行CC1（集群1控制器）: 端口 6653
  - 运行CC2（集群2控制器）: 端口 6654

- **机器2（集群1边界节点）**: IP 192.168.179.133
  - 运行OVS交换机（集群1边界节点）
  - 连接到CC1（172.30.1.137:6653）

- **机器3（集群2边界节点）**: IP 172.168.157.128
  - 运行OVS交换机（集群2边界节点）
  - 连接到CC2（172.30.1.137:6654）

### 通信流程
1. 集群1的节点发起到集群2节点的通信请求
2. CC1检测到跨域通信，封装请求上报AC
3. AC根据拓扑信息计算跨域路径
4. AC下发路径给相关的CC（CC1和CC2）
5. CC1和CC2分别在各自域内通过OpenFlow下发流表给节点

## 二、前置准备

### 2.1 环境要求
- 三台Ubuntu虚拟机（推荐Ubuntu 18.04或20.04）
- Python 3.6+
- Open vSwitch 2.9+
- Ryu SDN框架

### 2.2 安装依赖

在所有机器上安装基础依赖：
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip openvswitch-switch
```

在机器1（控制器节点）上安装Ryu和项目依赖：
```bash
cd /path/to/SDN
pip3 install -r pip-requirements.txt
pip3 install ryu
```

### 2.3 验证网络连通性

确保三台机器之间网络互通：
```bash
# 在机器2上
ping 172.30.1.137

# 在机器3上
ping 172.30.1.137

# 在机器1上
ping 192.168.179.133
ping 172.168.157.128
```

## 三、机器1配置（控制器节点 172.30.1.137）

### 3.1 配置环境变量

创建AC启动脚本 `start_ac.sh`:
```bash
#!/bin/bash
cd /path/to/SDN
export PYTHONPATH=/path/to/SDN:$PYTHONPATH

echo "启动AC控制器（端口10000）..."
python3 -m ryu.custom.controller.test_ac_controller 10000
```

创建CC1启动脚本 `start_cc1.sh`:
```bash
#!/bin/bash
cd /path/to/SDN
export PYTHONPATH=/path/to/SDN:$PYTHONPATH

# CC1配置
export CLUSTER_ID=1
export AC_HOST=172.30.1.137
export AC_PORT=10000
export DST_CLUSTERS=2

echo "启动CC1控制器（集群1，OpenFlow端口6653）..."
ryu-manager \
    --observe-links \
    --ofp-tcp-listen-port 6653 \
    ryu/custom/my_simple_switch_13.py
```

创建CC2启动脚本 `start_cc2.sh`:
```bash
#!/bin/bash
cd /path/to/SDN
export PYTHONPATH=/path/to/SDN:$PYTHONPATH

# CC2配置
export CLUSTER_ID=2
export AC_HOST=172.30.1.137
export AC_PORT=10000
export DST_CLUSTERS=1

echo "启动CC2控制器（集群2，OpenFlow端口6654）..."
ryu-manager \
    --observe-links \
    --ofp-tcp-listen-port 6654 \
    ryu/custom/my_simple_switch_13.py
```

### 3.2 赋予脚本执行权限
```bash
chmod +x start_ac.sh start_cc1.sh start_cc2.sh
```

### 3.3 启动控制器（按顺序）

打开3个终端窗口：

**终端1 - 启动AC**:
```bash
./start_ac.sh
```

等待看到：
```
[AC] Listening for CC connections on 0.0.0.0:10000...
```

**终端2 - 启动CC1**:
```bash
./start_cc1.sh
```

**终端3 - 启动CC2**:
```bash
./start_cc2.sh
```

观察CC日志，应看到：
```
[CC] FLAGS OK cluster=1 boundaries=[] dst_clusters=[2] ac=172.30.1.137:10000
[CC] Persistent connection established to AC 172.30.1.137:10000
```

## 四、机器2配置（集群1边界节点 192.168.179.133）

### 4.1 创建OVS网桥

```bash
# 删除已存在的网桥（如果有）
sudo ovs-vsctl del-br br-c1 2>/dev/null

# 创建集群1的网桥
sudo ovs-vsctl add-br br-c1
sudo ovs-vsctl set bridge br-c1 other-config:datapath-id=0000000000000001

# 连接到CC1控制器
sudo ovs-vsctl set-controller br-c1 tcp:172.30.1.137:6653

# 设置失败模式为secure（重要：确保流表生效）
sudo ovs-vsctl set-fail-mode br-c1 secure

# 验证配置
sudo ovs-vsctl show
```

### 4.2 添加端口（示例）

添加内部主机接口：
```bash
# 添加内部端口用于测试主机
sudo ovs-vsctl add-port br-c1 veth-h1 -- set interface veth-h1 type=internal
sudo ip link set veth-h1 up
sudo ip addr add 10.0.1.10/24 dev veth-h1
```

添加到集群2的互联端口：
```bash
# 添加连接到机器3的端口
# 如果两台机器直接连接，使用物理端口名，如 eth1
sudo ovs-vsctl add-port br-c1 eth1

# 或创建VXLAN隧道（如果机器不在同一网段）
sudo ovs-vsctl add-port br-c1 vxlan-c2 -- set interface vxlan-c2 \
    type=vxlan \
    options:remote_ip=172.168.157.128 \
    options:key=100
```

### 4.3 验证OVS连接

```bash
# 检查控制器连接状态
sudo ovs-vsctl get-controller br-c1
# 应显示: tcp:172.30.1.137:6653

# 检查连接是否已建立
sudo ovs-vsctl show
# 应看到 "is_connected: true"

# 查看OpenFlow连接
sudo ovs-ofctl show br-c1
```

## 五、机器3配置（集群2边界节点 172.168.157.128）

### 5.1 创建OVS网桥

```bash
# 删除已存在的网桥（如果有）
sudo ovs-vsctl del-br br-c2 2>/dev/null

# 创建集群2的网桥
sudo ovs-vsctl add-br br-c2
sudo ovs-vsctl set bridge br-c2 other-config:datapath-id=0000000000000002

# 连接到CC2控制器
sudo ovs-vsctl set-controller br-c2 tcp:172.30.1.137:6654

# 设置失败模式为secure
sudo ovs-vsctl set-fail-mode br-c2 secure

# 验证配置
sudo ovs-vsctl show
```

### 5.2 添加端口（示例）

添加内部主机接口：
```bash
# 添加内部端口用于测试主机
sudo ovs-vsctl add-port br-c2 veth-h2 -- set interface veth-h2 type=internal
sudo ip link set veth-h2 up
sudo ip addr add 10.0.2.20/24 dev veth-h2
```

添加到集群1的互联端口：
```bash
# 添加连接到机器2的端口
# 如果两台机器直接连接，使用物理端口名
sudo ovs-vsctl add-port br-c2 eth1

# 或创建VXLAN隧道（对应机器2的配置）
sudo ovs-vsctl add-port br-c2 vxlan-c1 -- set interface vxlan-c1 \
    type=vxlan \
    options:remote_ip=192.168.179.133 \
    options:key=100
```

### 5.3 验证OVS连接

```bash
# 检查控制器连接状态
sudo ovs-vsctl get-controller br-c2
# 应显示: tcp:172.30.1.137:6654

# 检查连接是否已建立
sudo ovs-vsctl show

# 查看OpenFlow连接
sudo ovs-ofctl show br-c2
```

## 六、验证系统状态

### 6.1 在机器1（控制器节点）检查日志

**AC日志应显示**:
```
[AC] HELLO from CC-1 v1.0
[AC] Registered connection for cluster 1
[AC] Boundaries[1] -> ['dpid:0000000000000001']
[AC] HELLO from CC-2 v1.0
[AC] Registered connection for cluster 2
[AC] Boundaries[2] -> ['dpid:0000000000000002']
[AC] KEEPALIVE from cluster 1
[AC] KEEPALIVE from cluster 2
```

**CC1日志应显示**:
```
[CC] FLAGS OK cluster=1 boundaries=[] dst_clusters=[2] ac=172.30.1.137:10000
[CC] Persistent connection established to AC 172.30.1.137:10000
[CC] map dpid=1 -> name=dpid:0000000000000001
[CC] ports dpid=1 -> [1, 2, 3]
[CC] Heartbeat sent to AC
```

**CC2日志应显示**:
```
[CC] FLAGS OK cluster=2 boundaries=[] dst_clusters=[1] ac=172.30.1.137:10000
[CC] Persistent connection established to AC 172.30.1.137:10000
[CC] map dpid=2 -> name=dpid:0000000000000002
[CC] ports dpid=2 -> [1, 2, 3]
[CC] Heartbeat sent to AC
```

### 6.2 检查跨域链路发现

当两个OVS之间的链路建立后（无论是物理链接还是VXLAN隧道），应该看到：

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

## 七、跨域通信测试

### 7.1 准备测试环境

确保：
- 机器2上有主机接口：10.0.1.10/24 (veth-h1)
- 机器3上有主机接口：10.0.2.20/24 (veth-h2)
- 两个OVS之间的互联端口已配置且UP状态

### 7.2 执行ping测试

在机器2上执行：
```bash
# 从集群1主机ping集群2主机
sudo ip netns exec h1 ping 10.0.2.20

# 或直接在veth接口上ping（如果没有使用netns）
ping -I veth-h1 10.0.2.20
```

### 7.3 观察日志输出

**预期在CC1看到**:
```
[CC] Packet-in: dpid=0000000000000001 port=1 src=xx:xx:xx:xx:xx:xx dst=yy:yy:yy:yy:yy:yy
[CC] *** CROSS-CLUSTER TRAFFIC DETECTED ***
[CC]     Source: 10.0.1.10 (cluster 1)
[CC]     Destination: 10.0.2.20 (cluster 2)
[CC]     This is NOT local traffic - need AC routing
[CC] Sending FLOW_REQUEST to AC (persistent)
```

**预期在AC看到**:
```
[AC] Received connection from ('172.30.1.137', <port>)
[AC] Calculating path: Cluster 1 → Cluster 2
[AC] Match fields: {'ip_dst': '10.0.2.20', ...}
[AC] Path calculation: [1, 2]
[AC] FLOW_REPLY segment sent to cluster 1 for path [1, 2]
[AC] FLOW_REPLY segment sent to cluster 2 for path [1, 2]
```

**预期在CC1和CC2看到**:
```
[CC] Received FLOW_REPLY
[CC] Path: 1 → 2
[CC] Segment: cluster=1, ingress=, egress=, tunnel=
```

### 7.4 验证流表下发

在机器2上检查流表：
```bash
sudo ovs-ofctl dump-flows br-c1
```

应该看到针对跨域流量的流表项（包含匹配10.0.2.20的规则）。

在机器3上检查流表：
```bash
sudo ovs-ofctl dump-flows br-c2
```

应该看到针对接收跨域流量的流表项。

### 7.5 使用tcpdump抓包验证

在机器2上：
```bash
# 抓取vxlan隧道上的包（如果使用VXLAN）
sudo tcpdump -i vxlan-c2 -n

# 或抓取物理端口
sudo tcpdump -i eth1 -n
```

在机器3上：
```bash
# 抓取vxlan隧道上的包
sudo tcpdump -i vxlan-c1 -n

# 或抓取物理端口
sudo tcpdump -i eth1 -n
```

## 八、故障排查

### 8.1 控制器连接问题

**问题**: OVS无法连接到CC
```bash
# 检查端口是否监听
netstat -tlnp | grep 6653
netstat -tlnp | grep 6654

# 检查防火墙
sudo ufw status
sudo ufw allow 6653
sudo ufw allow 6654
sudo ufw allow 10000

# 测试端口连通性
telnet 172.30.1.137 6653
telnet 172.30.1.137 6654
```

### 8.2 跨域链路未发现

**问题**: AC未显示cluster edges

检查项：
1. 确认两个OVS之间的端口状态为UP
```bash
sudo ovs-vsctl list interface
```

2. 确认LLDP功能正常
```bash
# 在机器1查看CC日志，应该看到LLDP发送
grep LLDP /path/to/cc1.log
```

3. 手动测试连通性
```bash
# 从机器2 ping 机器3的vxlan地址或物理IP
ping 172.168.157.128
```

### 8.3 流表未下发

**问题**: ping不通但日志显示路径已计算

检查项：
1. 确认OVS的fail-mode为secure
```bash
sudo ovs-vsctl get-fail-mode br-c1
```

2. 检查是否有默认流表
```bash
sudo ovs-ofctl dump-flows br-c1
```

3. 手动添加测试流表
```bash
# 在集群1添加转发到集群2的规则
sudo ovs-ofctl add-flow br-c1 "ip,nw_dst=10.0.2.0/24,actions=output:2"

# 在集群2添加转发到集群1的规则
sudo ovs-ofctl add-flow br-c2 "ip,nw_dst=10.0.1.0/24,actions=output:2"
```

### 8.4 AC收不到CC的消息

**问题**: CC日志显示发送成功，但AC无日志

检查项：
1. 确认AC端口10000正在监听
```bash
sudo netstat -tlnp | grep 10000
```

2. 检查网络路由
```bash
# 在机器1上
ip route
# 确保能路由到CC所在的网络
```

3. 抓包诊断
```bash
# 在机器1上抓10000端口的包
sudo tcpdump -i any -n port 10000
```

## 九、高级配置

### 9.1 配置多个主机

在机器2上创建多个主机：
```bash
# 创建network namespace模拟多主机
sudo ip netns add h1
sudo ip link add veth-h1 type veth peer name veth-h1-br
sudo ip link set veth-h1 netns h1
sudo ovs-vsctl add-port br-c1 veth-h1-br
sudo ip link set veth-h1-br up
sudo ip netns exec h1 ip link set veth-h1 up
sudo ip netns exec h1 ip addr add 10.0.1.10/24 dev veth-h1
sudo ip netns exec h1 ip route add default via 10.0.1.1
```

### 9.2 配置VLAN隔离

```bash
# 在OVS上配置VLAN
sudo ovs-vsctl set port veth-h1-br tag=100
sudo ovs-vsctl set port vxlan-c2 tag=100
```

### 9.3 启用OpenFlow日志

```bash
# 增加OVS日志级别（警告：会产生大量日志，仅用于调试）
sudo ovs-appctl vlog/set ofproto_dpif:dbg
sudo ovs-appctl vlog/set ofproto:dbg

# 查看日志
sudo journalctl -u openvswitch -f

# 恢复正常日志级别
sudo ovs-appctl vlog/set ofproto_dpif:info
sudo ovs-appctl vlog/set ofproto:info
```

**注意**: 调试日志会显著增加日志量，可能影响性能。生产环境应谨慎使用。

## 十、性能测试

### 10.1 使用iperf测试带宽

在机器3上（目标主机）：
```bash
# 启动iperf3服务器（推荐）
iperf3 -s -B 10.0.2.20

# 或使用iperf2
iperf -s -B 10.0.2.20
```

在机器2上（源主机）：
```bash
# 运行iperf3客户端
iperf3 -c 10.0.2.20 -B 10.0.1.10 -t 30

# 或使用iperf2
iperf -c 10.0.2.20 -B 10.0.1.10 -t 30
```

**说明**: `-B` 参数指定本地绑定地址（源IP），`-c` 参数指定目标服务器IP。

### 10.2 测试延迟

```bash
# 从机器2 ping 机器3，测量RTT
ping -c 100 -I veth-h1 10.0.2.20 | tail -1
```

### 10.3 测试吞吐量

```bash
# 使用dd和netcat测试
# 在机器3上
nc -l 5001 > /dev/null

# 在机器2上
dd if=/dev/zero bs=1M count=1000 | nc 10.0.2.20 5001
```

## 十一、清理和重置

### 11.1 停止所有服务

在机器1上：
```bash
# 按Ctrl+C停止各个终端中的AC和CC
```

### 11.2 清理OVS配置

在机器2和机器3上：
```bash
# 删除网桥
sudo ovs-vsctl del-br br-c1  # 机器2
sudo ovs-vsctl del-br br-c2  # 机器3

# 清理namespace（如果创建了）
sudo ip netns del h1
sudo ip netns del h2
```

### 11.3 重置测试环境

```bash
# 重启OVS服务
sudo systemctl restart openvswitch-switch

# 清理临时文件
rm -f /tmp/*.log
```

## 十二、参考文档

- [三集群最小演示](../demo/3cluster-demo.md)
- [my_simple_switch集成指南](MY_SIMPLE_SWITCH_INTEGRATION.md)
- [同步协议详情](SYNC_PROTOCOL.md)
- [Ryu官方文档](https://ryu.readthedocs.io/)
- [Open vSwitch文档](http://docs.openvswitch.org/)

## 十三、常见问题(FAQ)

**Q1: 为什么需要使用secure模式？**
A: secure模式确保当控制器连接断开时，OVS继续使用已有流表，而不是切换到普通交换机模式。

**Q2: VXLAN和物理连接哪个更好？**
A: 如果两台机器在不同网段，使用VXLAN；如果在同一网段或直连，使用物理端口性能更好。

**Q3: 如何确认跨域流量确实经过了AC？**
A: 查看AC日志中的"FLOW_REQUEST"和"FLOW_REPLY"消息，这些消息确认了跨域路径计算。

**Q4: 可以测试3个或更多集群吗？**
A: 可以，在机器1上启动更多CC实例（不同端口），在其他机器上配置相应的OVS连接。

**Q5: 性能瓶颈在哪里？**
A: 主要瓶颈在：1) AC的路径计算 2) 跨机器的网络带宽 3) OVS的流表查找速度。
