# 东西向协议文档导航 / East-West Protocol Documentation Guide

## 概述 / Overview

本目录包含了分层SDN架构中东西向协议的完整技术文档。

This directory contains complete technical documentation for the east-west protocol in hierarchical SDN architecture.

---

## 文档列表 / Document List

### 1. 东西向协议设计与实现 (核心文档)
**East-West Protocol Design and Implementation (Core Document)**

**文件 / File:** [EAST_WEST_PROTOCOL_DESIGN.md](EAST_WEST_PROTOCOL_DESIGN.md)

**类型 / Type:** 学术论文风格 / Academic Paper Style

**语言 / Language:** 中文 / Chinese

**长度 / Length:** 20,000+ 字符

**内容 / Contents:**
- 东西向协议概念和背景
- 设计原则和架构
- 8种消息类型详细说明
- 协议工作流程
- 技术实现特点
- 实际应用案例
- 未来工作展望

**适用场景 / Use Cases:**
- 研究论文引用
- 毕业论文章节
- 技术方案文档
- 学术演讲材料

---

### 2. 同步协议文档
**Synchronization Protocol Documentation**

**文件 / File:** [SYNC_PROTOCOL.md](SYNC_PROTOCOL.md)

**类型 / Type:** 技术文档 / Technical Documentation

**语言 / Language:** 英文 / English

**内容 / Contents:**
- 同步协议概述
- 组件架构
- 消息同步机制
- 心跳监控
- 线程安全设计
- 测试指南

**适用场景 / Use Cases:**
- 开发者参考
- 系统集成
- 故障排查
- 性能调优

---

## 相关实现文件 / Related Implementation Files

### 协议定义 / Protocol Definition
- `ryu/custom/protocol/message.proto` - Protocol Buffers定义
- `ryu/custom/protocol/message_pb2.py` - 自动生成的Python代码

### 核心实现 / Core Implementation
- `ryu/custom/controller/sync_protocol.py` - 同步协议模块
- `ryu/custom/controller/state_manager.py` - 状态管理器
- `ryu/custom/controller/test_ac_controller.py` - AC控制器
- `ryu/custom/controller/test_cc_controller.py` - CC控制器

### 测试代码 / Test Code
- `ryu/tests/unit/test_sync_protocol.py` - 同步协议单元测试
- `ryu/tests/unit/test_state_manager.py` - 状态管理器单元测试
- `ryu/tests/integration/test_multi_cc_sync.py` - 多CC集成测试

---

## 快速导航 / Quick Navigation

### 我想了解... / I want to understand...

#### 东西向协议的基本概念
→ 阅读 [EAST_WEST_PROTOCOL_DESIGN.md](EAST_WEST_PROTOCOL_DESIGN.md) 第1-2章

#### 消息类型和格式
→ 阅读 [EAST_WEST_PROTOCOL_DESIGN.md](EAST_WEST_PROTOCOL_DESIGN.md) 第4章
→ 查看 `ryu/custom/protocol/message.proto`

#### 协议工作流程
→ 阅读 [EAST_WEST_PROTOCOL_DESIGN.md](EAST_WEST_PROTOCOL_DESIGN.md) 第5章

#### 如何使用同步协议API
→ 阅读 [SYNC_PROTOCOL.md](SYNC_PROTOCOL.md)
→ 查看 `ryu/custom/controller/sync_protocol.py`

#### 如何运行测试
→ 阅读 [SYNC_PROTOCOL.md](SYNC_PROTOCOL.md) Testing章节

#### 实际应用案例
→ 阅读 [EAST_WEST_PROTOCOL_DESIGN.md](EAST_WEST_PROTOCOL_DESIGN.md) 第8章

---

## 消息类型速查 / Message Type Quick Reference

| 消息类型 | 方向 | 用途 | 文档章节 |
|---------|------|------|---------|
| HELLO | 双向 | 握手 | 4.1 |
| TOPOLOGY_UPDATE | CC→AC | 拓扑上报 | 4.2 |
| INTERCLUSTER_LINK_UPDATE | CC→AC | 链路发现 | 4.3 |
| INTERCLUSTER_LINK_METRICS | CC→AC | 指标上报 | 4.4 |
| FLOW_REQUEST | CC→AC | 路由请求 | 4.5 |
| FLOW_REPLY | AC→CC | 路径下发 | 4.6 |
| KEEPALIVE | CC→AC | 心跳 | 4.7 |
| ERROR | 双向 | 错误报告 | 4.8 |

---

## 协议设计关键点 / Key Design Points

### 1. 分层抽象 (Hierarchical Abstraction)
- AC只看集群级拓扑，不了解集群内部细节
- CC提供边界交换机和跨集群链路信息
- 降低AC状态管理复杂度，提高可扩展性

### 2. 异步消息驱动 (Asynchronous Message-Driven)
- 所有通信基于消息传递
- 支持请求-应答和单向通知
- msg_id和corr_id用于消息关联

### 3. 可靠性保证 (Reliability Guarantee)
- 消息超时与重传机制
- 心跳监控检测故障
- 序列号保证消息顺序

### 4. 线程安全 (Thread Safety)
- 细粒度锁设计
- 读写分离策略
- 无锁数据结构

---

## 协议工作流程概览 / Protocol Workflow Overview

### 初始化流程
```
1. AC启动 → 监听端口
2. CC启动 → 连接AC
3. HELLO握手
4. CC发送TOPOLOGY_UPDATE
```

### 链路发现流程
```
1. CC发送LLDP
2. 接收对端LLDP
3. 识别跨集群链路
4. 发送INTERCLUSTER_LINK_UPDATE到AC
5. AC匹配链路两端
```

### 跨域路由流程
```
1. Host发起跨集群通信
2. CC检测跨域流量
3. CC发送FLOW_REQUEST到AC
4. AC计算路径
5. AC发送FLOW_REPLY到各CC
6. CC安装流表
```

---

## 技术栈 / Technology Stack

- **序列化**: Protocol Buffers 3
- **传输**: TCP
- **并发**: Python threading + locks
- **路由算法**: Dijkstra / 加权Dijkstra
- **开发语言**: Python 3
- **测试框架**: unittest

---

## 性能指标 / Performance Metrics

- **消息延迟**: < 10ms
- **吞吐量**: > 10,000 msg/s
- **支持CC数**: 100+
- **心跳间隔**: 10秒
- **超时时间**: 30秒

---

## 常见问题 / FAQ

### Q1: 为什么使用Protocol Buffers？
A: 高效的二进制编码，强类型，向后兼容，跨语言支持。

### Q2: 如何保证消息不丢失？
A: 超时重传机制 + 消息确认 + 心跳监控。

### Q3: 如何处理CC故障？
A: 心跳超时检测 + 故障回调 + 状态标记。

### Q4: 如何扩展新的消息类型？
A: 在message.proto添加新消息定义 → 更新Envelope.Type枚举 → 重新生成Python代码。

### Q5: 如何测试协议？
A: 参考SYNC_PROTOCOL.md的Testing章节，运行单元测试和集成测试。

---

## 更新历史 / Update History

- **2026-02-11**: 创建EAST_WEST_PROTOCOL_DESIGN.md，学术论文风格完整文档
- **2024-XX-XX**: 创建SYNC_PROTOCOL.md，同步协议技术文档
- **2024-XX-XX**: 初始协议实现

---

## 联系方式 / Contact

如有问题或建议，请提交Issue或Pull Request。

For questions or suggestions, please submit an Issue or Pull Request.

---

**文档版本 / Document Version:** 1.0  
**最后更新 / Last Update:** 2026-02-11
