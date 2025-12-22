# 三集群最小演示（协议联通版）

目标：在不依赖 OVS/Mininet 的前提下，最小化跑通中央控制器（AC）与三个集群控制器（CC1/CC2/CC3）之间的自定义“东西向”协议交互：HELLO、FLOW_REQUEST、FLOW_REPLY。

本演示基于现有测试脚本：
- AC 端：`ryu/custom/controller/test_ac_controller.py`
- CC 端：`ryu/custom/controller/test_cc_controller.py`

注意：这是“协议联通版”，用于验证协议消息与会话；不下发 OpenFlow 规则，不需要 OVS/Mininet。

---

## 1. 端口与角色规划
- AC 监听：10000
- 三个 CC 分别监听：
  - CC1: 9000（代表集群 1）
  - CC2: 9001（代表集群 2）
  - CC3: 9002（代表集群 3）

连接关系：
- AC 会主动作为客户端连接三个 CC 的监听端口并发送 HELLO（AC→CC）。
- CC 会作为客户端连接 AC 的监听端口发送 FLOW_REQUEST（CC→AC）。

> 现有 CC 脚本默认构造的 FLOW_REQUEST 为 src_cluster=2, dst_cluster=1。你可按需要修改 `test_cc_controller.py` 的 `send_flow_request_to_ac` 函数以覆盖 src/dst。

---

## 2. 启动顺序
1) 启动 AC（默认 10000）：
   - python3 -m ryu.custom.controller.test_ac_controller 10000

2) 启动 3 个 CC 实例（不同端口）：
   - CC1：python3 -m ryu.custom.controller.test_cc_controller 9000
   - CC2：python3 ryu/custom/controller/test_cc_controller 9001
   - CC3：python3 ryu/custom/controller/test_cc_controller 9002

建议每个进程独立终端窗口，便于观察日志。

---

## 3. 期望看到的关键日志
- 在 CC 侧（当 AC 主动连接到各 CC 端口时）：
  - "[CC] Connected by (('127.0.0.1', <port>), <...>)"
  - 收到 AC 的 HELLO 后，CC 会触发一次向 AC 发送 FLOW_REQUEST（代码中 `handle_hello` 调用 `send_flow_request_to_ac`）。
  - 随后 CC 会打印："[CC] Sending FLOW_REQUEST to AC"，并在收到回复后打印 "[CC] Received FLOW_REPLY" 以及路径 Path: ...

- 在 AC 侧（接收来自 CC 的 FLOW_REQUEST）：
  - "[AC] Received connection from ..."
  - "[AC] Received FLOW_REQUEST from ..."
  - "[AC] Calculating path: Cluster <src> → Cluster <dst>"
  - "[AC] Sending FLOW_REPLY to requester via same connection"

> AC 中的演示拓扑 `TOPO` 目前内置了 1↔2 两个方向的路径示意，如需 1↔3、2↔3，请在 `test_ac_controller.py` 的 `TOPO` 变量中补充（字符串数组即可，CC 端仅打印）。

---

## 4. 修改建议（可选）
- 多集群路径：将 AC 的 `TOPO` 扩展为：
  ```python
  TOPO = {
      1: {2: ["c1-b1", "c2-b2"], 3: ["c1-b1", "c3-b3"]},
      2: {1: ["c2-b2", "c1-b1"], 3: ["c2-b2", "c3-b3"]},
      3: {1: ["c3-b3", "c1-b1"], 2: ["c3-b3", "c2-b2"]},
  }
  ```
  仅为演示打印用，不影响协议流程。

- 请求来源区分：可复制三份 `test_cc_controller.py`（或通过环境变量）让 CC1/CC2/CC3 各自发送不同的 `src_cluster` 与 `dst_cluster`，便于验证 AC 的不同路径返回。

---

## 5. 故障排查
- 若 CC 未收到 AC 的 HELLO：
  - 确认 AC 是否成功连接到 CC 的监听端口（AC 终端应打印 "Received connection from ..."）。
  - 确认双方使用的 network/message 编解码一致（`send_message/receive_message` vs `send_envelope/receive_envelope`）。若日志显示类型不匹配，建议统一走 `message.encode_envelope` + `network.send_message` 与 `network.receive_message` + `message.decode_envelope` 的组合。

- 若 AC 未收到 FLOW_REQUEST：
  - 确认 CC 端线程是否已触发 `send_flow_request_to_ac`（收到 HELLO 后会触发）。
  - 确认 AC 的 10000 端口处于监听状态，且本机环回可达。

- 若 AC 回复的路径在 CC 端打印为空：
  - 检查 AC 的 `TOPO` 中是否存在 `src_cluster -> dst_cluster` 的条目。

---

## 6. 下一步（接入南向与真实转发）
当协议联通验证通过后，可继续：
- 在 CC 侧引入 Ryu OpenFlow1.3 应用，完成域内拓扑与主机学习；
- 将 AC 的 `FLOW_REPLY` 扩展为包含 per-cluster 段的 ingress/egress 边界信息；
- CC 收到 `FLOW_REPLY` 后在本域计算段内路径并下发 OpenFlow 规则；
- 使用 Mininet/OVS 或 Mininet-WiFi 构建 3 集群的仿真拓扑，验证跨域连通性（ping/iperf）。

---

## 7. 文件位置与入口
- AC：`ryu/custom/controller/test_ac_controller.py`
- CC：`ryu/custom/controller/test_cc_controller.py`
- 本说明：`ryu/custom/demo/3cluster-demo.md`

如需将说明集成到更完整的 README 或生成自动化启动脚本（如一键启动 AC + 3×CC），请告知需要的形式。
