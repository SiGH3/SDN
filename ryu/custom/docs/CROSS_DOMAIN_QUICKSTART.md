# 跨域通信测试快速参考卡

## 快速启动指南

### 1. 机器1（控制器节点 172.30.1.137）

#### 方式A: 使用自动化脚本
```bash
cd /path/to/SDN
bash ryu/custom/scripts/setup_cross_domain_test.sh
# 选择 1) 控制器节点
```

#### 方式B: 手动启动（3个终端）
```bash
# 终端1 - AC
cd /path/to/SDN
export PYTHONPATH=$(pwd):$PYTHONPATH
python3 -m ryu.custom.controller.test_ac_controller 10000

# 终端2 - CC1
export CLUSTER_ID=1 AC_HOST=172.30.1.137 AC_PORT=10000 DST_CLUSTERS=2
ryu-manager --observe-links --ofp-tcp-listen-port 6653 ryu/custom/my_simple_switch_13.py

# 终端3 - CC2
export CLUSTER_ID=2 AC_HOST=172.30.1.137 AC_PORT=10000 DST_CLUSTERS=1
ryu-manager --observe-links --ofp-tcp-listen-port 6654 ryu/custom/my_simple_switch_13.py
```

### 2. 机器2（集群1边界 192.168.179.133）

```bash
# 方式A: 自动化脚本
bash ryu/custom/scripts/setup_cross_domain_test.sh
# 选择 2) 集群1边界节点

# 方式B: 手动配置
sudo ovs-vsctl add-br br-c1
sudo ovs-vsctl set bridge br-c1 other-config:datapath-id=0000000000000001
sudo ovs-vsctl set-controller br-c1 tcp:172.30.1.137:6653
sudo ovs-vsctl set-fail-mode br-c1 secure

# 添加测试主机接口
sudo ovs-vsctl add-port br-c1 veth-h1 -- set interface veth-h1 type=internal
sudo ip link set veth-h1 up
sudo ip addr add 10.0.1.10/24 dev veth-h1

# 添加VXLAN到集群2
sudo ovs-vsctl add-port br-c1 vxlan-c2 -- set interface vxlan-c2 \
    type=vxlan options:remote_ip=172.168.157.128 options:key=100
```

### 3. 机器3（集群2边界 172.168.157.128）

```bash
# 方式A: 自动化脚本
bash ryu/custom/scripts/setup_cross_domain_test.sh
# 选择 3) 集群2边界节点

# 方式B: 手动配置
sudo ovs-vsctl add-br br-c2
sudo ovs-vsctl set bridge br-c2 other-config:datapath-id=0000000000000002
sudo ovs-vsctl set-controller br-c2 tcp:172.30.1.137:6654
sudo ovs-vsctl set-fail-mode br-c2 secure

# 添加测试主机接口
sudo ovs-vsctl add-port br-c2 veth-h2 -- set interface veth-h2 type=internal
sudo ip link set veth-h2 up
sudo ip addr add 10.0.2.20/24 dev veth-h2

# 添加VXLAN到集群1
sudo ovs-vsctl add-port br-c2 vxlan-c1 -- set interface vxlan-c1 \
    type=vxlan options:remote_ip=192.168.179.133 options:key=100
```

## 验证检查清单

### ✓ 机器1检查

- [ ] AC日志显示: `[AC] Listening for CC connections on 0.0.0.0:10000...`
- [ ] CC1日志显示: `[CC] FLAGS OK cluster=1 ... ac=172.30.1.137:10000`
- [ ] CC2日志显示: `[CC] FLAGS OK cluster=2 ... ac=172.30.1.137:10000`
- [ ] AC日志显示: `[AC] HELLO from CC-1 v1.0`
- [ ] AC日志显示: `[AC] HELLO from CC-2 v1.0`
- [ ] AC日志显示: `[AC] KEEPALIVE from cluster 1`
- [ ] AC日志显示: `[AC] KEEPALIVE from cluster 2`
- [ ] AC日志显示: `[AC] Cluster edges: [(1, 2)]`

### ✓ 机器2检查

- [ ] `sudo ovs-vsctl show` 显示 `is_connected: true`
- [ ] `sudo ovs-ofctl show br-c1` 可以执行
- [ ] `ping -I veth-h1 10.0.1.10` 成功（本地回环）
- [ ] CC1日志显示: `[CC] LLDP跨域邻居: ... peer_dpid=2`

### ✓ 机器3检查

- [ ] `sudo ovs-vsctl show` 显示 `is_connected: true`
- [ ] `sudo ovs-ofctl show br-c2` 可以执行
- [ ] `ping -I veth-h2 10.0.2.20` 成功（本地回环）
- [ ] CC2日志显示: `[CC] LLDP跨域邻居: ... peer_dpid=1`

## 跨域通信测试

### 测试步骤

1. **在机器2执行ping测试**:
   ```bash
   ping -I veth-h1 10.0.2.20
   ```

2. **观察CC1日志** (机器1上):
   ```
   [CC] *** CROSS-CLUSTER TRAFFIC DETECTED ***
   [CC]     Source: 10.0.1.10 (cluster 1)
   [CC]     Destination: 10.0.2.20 (cluster 2)
   [CC] Sending FLOW_REQUEST to AC
   ```

3. **观察AC日志** (机器1上):
   ```
   [AC] Calculating path: Cluster 1 → Cluster 2
   [AC] FLOW_REPLY segment sent to cluster 1 for path [1, 2]
   [AC] FLOW_REPLY segment sent to cluster 2 for path [1, 2]
   ```

4. **观察CC1和CC2日志** (机器1上):
   ```
   [CC] Received FLOW_REPLY
   [CC] Path: 1 → 2
   ```

5. **验证流表下发**:
   ```bash
   # 在机器2
   sudo ovs-ofctl dump-flows br-c1
   
   # 在机器3
   sudo ovs-ofctl dump-flows br-c2
   ```

### 预期结果

✓ ping通（可能有少量丢包是正常的，第一个包用于路径发现）
✓ AC计算出路径 [1, 2]
✓ CC1和CC2都收到FLOW_REPLY
✓ 流表被正确下发到OVS

## 常用命令速查

### OVS命令
```bash
# 查看网桥配置
sudo ovs-vsctl show

# 查看流表
sudo ovs-ofctl dump-flows br-c1

# 查看端口状态
sudo ovs-ofctl show br-c1

# 删除所有流表
sudo ovs-ofctl del-flows br-c1

# 查看端口统计
sudo ovs-ofctl dump-ports br-c1

# 重启OVS
sudo systemctl restart openvswitch-switch
```

### 网络测试
```bash
# ping测试（指定源接口）
ping -I veth-h1 10.0.2.20

# tcpdump抓包
sudo tcpdump -i vxlan-c2 -n

# iperf带宽测试（推荐使用iperf3）
# 在机器3（10.0.2.20）启动服务器
iperf3 -s -B 10.0.2.20
# 或使用iperf2
iperf -s -B 10.0.2.20

# 在机器2（10.0.1.10）启动客户端连接到机器3
iperf3 -c 10.0.2.20 -B 10.0.1.10
# 或使用iperf2
iperf -c 10.0.2.20 -B 10.0.1.10

# 查看路由表
ip route

# 查看接口状态
ip addr show
```

### 控制器日志
```bash
# 实时查看AC日志
tail -f /path/to/ac.log

# 搜索关键词
grep "FLOW_REQUEST" /path/to/cc1.log

# 查看最近的错误
grep -i error /path/to/ac.log | tail -20
```

## 故障快速排查

### 问题: OVS无法连接到CC
```bash
# 检查端口监听
netstat -tlnp | grep 6653
netstat -tlnp | grep 6654

# 测试连通性
telnet 172.30.1.137 6653
telnet 172.30.1.137 6654

# 检查防火墙
sudo ufw allow 6653
sudo ufw allow 6654
sudo ufw allow 10000
```

### 问题: 跨域链路未发现
```bash
# 检查VXLAN状态
sudo ovs-vsctl list interface vxlan-c2

# 测试VXLAN连通性
ping 172.168.157.128  # 从机器2

# 查看LLDP包
sudo tcpdump -i any ether proto 0x88cc -vv
```

### 问题: ping不通
```bash
# 检查流表
sudo ovs-ofctl dump-flows br-c1

# 检查端口状态
sudo ip link show veth-h1

# 检查IP配置
ip addr show veth-h1

# 手动添加流表测试
sudo ovs-ofctl add-flow br-c1 "ip,nw_dst=10.0.2.0/24,actions=output:2"
```

## 清理环境

```bash
# 机器1: 停止所有控制器（Ctrl+C）

# 机器2: 清理OVS
sudo ovs-vsctl del-br br-c1

# 机器3: 清理OVS
sudo ovs-vsctl del-br br-c2
```

## 更多信息

详细文档: `ryu/custom/docs/CROSS_DOMAIN_TEST.md`
配置脚本: `ryu/custom/scripts/setup_cross_domain_test.sh`
示例代码: `ryu/custom/controller/test_ac_controller.py`
         `ryu/custom/my_simple_switch_13.py`
