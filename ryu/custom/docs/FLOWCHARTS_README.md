# 流程图文档导航 / Flowcharts Documentation Guide

## 概述 / Overview

本文档提供拓扑发现和跨域链路建立流程图的快速导航指南。

This document provides a quick navigation guide for topology discovery and cross-domain link establishment flowcharts.

---

## 主要文档 / Main Document

### 📊 TOPOLOGY_DISCOVERY_FLOWCHARTS.md

**位置 / Location:** `ryu/custom/docs/TOPOLOGY_DISCOVERY_FLOWCHARTS.md`

**大小 / Size:** 22KB, 22,000+ 字符

**语言 / Language:** 中文 (Chinese)

---

## 文档内容概览 / Content Overview

### 1. 拓扑发现流程 (Topology Discovery Process)

**包含内容：**
- 系统初始化流程（AC和CC启动）
- LLDP拓扑发现机制
- 端口分类逻辑（主机/内部/边界端口）
- 边界拓扑上报（TOPOLOGY_UPDATE消息）
- AC拓扑信息存储

**可视化：**
- Mermaid流程图（20+节点）
- 详细步骤说明
- 代码示例
- 消息格式示例

**跳转到：** [第1节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#1-拓扑发现流程)

---

### 2. 跨域链路建立流程 (Cross-Domain Link Establishment)

**包含内容：**
- LLDP包在集群间交换
- 跨集群链路识别
- Link Key生成算法
- 链路信息上报（INTERCLUSTER_LINK_UPDATE消息）
- AC链路匹配和确认
- 集群拓扑图构建

**可视化：**
- Mermaid流程图（双向流程）
- 详细阶段说明
- Link Key算法详解
- AC匹配逻辑

**跳转到：** [第2节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#2-跨域链路建立流程)

---

### 3. 完整系统流程 (Complete System Flow)

**包含内容：**
- 时间线视图（T0到T6+）
- 多集群初始化过程
- 顺序链路发现
- 持续维护操作

**可视化：**
- 时间线图表
- 多集群场景示例

**跳转到：** [第3节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#3-完整的系统初始化与链路发现流程)

---

### 4. 时序图 (Sequence Diagrams)

**包含内容：**
- AC与多个CC的交互
- 单链路建立详细时序
- 多集群场景完整流程
- 故障场景处理

**可视化：**
- Mermaid时序图
- 详细时间戳标注
- 消息流向清晰

**跳转到：** [第4节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#4-时序图)

---

### 5. 关键技术点 (Key Technical Points)

**包含内容：**
- LLDP自定义TLV实现
- Link Key生成算法保证双向一致
- AC链路匹配可靠性机制
- 实际部署示例

**跳转到：** [第5节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#5-关键技术点总结)

---

### 6. 附录 (Appendices)

**包含内容：**
- ASCII艺术流程图
- 纯文本格式可视化
- 兼容所有查看器

**跳转到：** [附录](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#附录ascii艺术流程图)

---

## 快速查找 / Quick Find

### 按主题查找 / Find by Topic

| 主题 | 位置 |
|------|------|
| AC启动过程 | [1.2节 - 步骤1](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤1-系统初始化) |
| CC启动过程 | [1.2节 - 步骤1](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤1-系统初始化) |
| HELLO握手 | [1.2节 - 步骤2](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤2-握手建立连接) |
| LLDP发送 | [1.2节 - 步骤3](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤3-lldp拓扑发现) |
| 端口分类 | [1.2节 - 步骤3](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤3-lldp拓扑发现) |
| TOPOLOGY_UPDATE | [1.2节 - 步骤4](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤4-边界拓扑上报) |
| LLDP包交换 | [2.2节 - 阶段1](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段1-lldp包交换) |
| Link Key生成 | [2.2节 - 阶段2](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段2-链路标识生成) |
| INTERCLUSTER_LINK_UPDATE | [2.2节 - 阶段3](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段3-链路信息上报) |
| AC链路匹配 | [2.2节 - 阶段4](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段4-ac链路匹配) |
| 拓扑图更新 | [2.2节 - 阶段5](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段5-拓扑图更新) |
| 时间线 | [3.1节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#31-时间线视图) |
| 多集群场景 | [3.2节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#32-多集群场景完整流程) |
| 单链路时序 | [4.1节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#41-单链路建立详细时序) |
| 故障处理 | [4.2节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#42-故障场景处理) |
| LLDP TLV | [5.1节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#51-lldp自定义tlv) |
| Link Key算法 | [5.2节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#52-link-key生成确保双向一致) |
| 可靠性机制 | [5.3节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#53-ac链路匹配的可靠性) |
| 部署示例 | [5.4节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#54-实际部署示例) |

### 按消息类型查找 / Find by Message Type

| 消息类型 | 相关章节 |
|---------|---------|
| HELLO | [1.2节 - 步骤2](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤2-握手建立连接) |
| TOPOLOGY_UPDATE | [1.2节 - 步骤4](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤4-边界拓扑上报) |
| INTERCLUSTER_LINK_UPDATE | [2.2节 - 阶段3](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段3-链路信息上报) |
| INTERCLUSTER_LINK_METRICS | [2.1节 - 末尾](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#21-跨域链路建立总体流程图) |
| KEEPALIVE | [3.1节 - T6+](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#31-时间线视图) |

### 按组件查找 / Find by Component

| 组件 | 相关章节 |
|-----|---------|
| AC (聚合控制器) | [1.2节 - 步骤1](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤1-系统初始化), [2.2节 - 阶段4](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段4-ac链路匹配) |
| CC (集群控制器) | [1.2节 - 步骤1](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤1-系统初始化), [1.2节 - 步骤3](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤3-lldp拓扑发现) |
| LLDP模块 | [1.2节 - 步骤3](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#步骤3-lldp拓扑发现), [5.1节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#51-lldp自定义tlv) |
| 拓扑图 (ClusterGraph) | [2.2节 - 阶段5](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段5-拓扑图更新) |
| 链路匹配器 | [2.2节 - 阶段4](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#阶段4-ac链路匹配) |

---

## 图表类型 / Diagram Types

### Mermaid流程图 / Mermaid Flowcharts
- **拓扑发现流程图**：20+节点，包含决策点和分支
- **跨域链路建立流程图**：双向流程，包含并行路径
- **多集群时序图**：AC与3个CC的完整交互

### ASCII艺术图 / ASCII Art Diagrams
- **拓扑发现ASCII流程图**：纯文本格式，兼容所有编辑器
- **跨域链路建立ASCII流程图**：清晰的流程展示

---

## 关键概念说明 / Key Concepts

### 1. LLDP (Link Layer Discovery Protocol)
链路层发现协议，用于自动发现网络拓扑。本项目使用LLDP的自定义TLV来传递cluster_id，实现跨集群链路识别。

### 2. Link Key
链路标识符，用于AC匹配来自两端CC的链路报告。通过对端点信息排序生成，确保双向一致性。

### 3. Boundary Port (边界端口)
连接不同集群的端口。通过LLDP包中的cluster_id识别。

### 4. Topology Update (拓扑更新)
CC向AC报告本集群的边界拓扑信息，包括边界交换机和边界端口列表。

### 5. Inter-Cluster Link (跨集群链路)
连接不同集群的物理链路，通过双向LLDP发现和AC匹配确认。

---

## 实际应用场景 / Real-World Scenarios

### 场景1: 3集群环形拓扑
**文档位置：** [5.4节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#54-实际部署示例)

**描述：**
- Cluster 1, 2, 3形成环形
- 无线adhoc网络连接
- 完整的链路发现过程

### 场景2: 链路故障检测
**文档位置：** [4.2节](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#42-故障场景处理)

**描述：**
- LLDP超时检测
- AC链路删除
- 路由重计算触发

### 场景3: 单端报告超时
**文档位置：** [4.2节 - 场景1](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#42-故障场景处理)

**描述：**
- 只有一端CC报告链路
- AC超时处理
- 可能原因分析

---

## 代码参考 / Code References

### 实现文件
- **LLDP处理：** `ryu/custom/controller/cc_controller.py`
- **链路匹配：** `ryu/custom/controller/ac_controller.py`
- **协议定义：** `ryu/custom/protocol/message.proto`
- **状态管理：** `ryu/custom/controller/state_manager.py`

### 相关文档
- **协议设计：** `EAST_WEST_PROTOCOL_DESIGN.md`
- **协议导航：** `README_PROTOCOL_DOCS.md`
- **协议摘要：** `PROTOCOL_DOCS_SUMMARY.txt`

---

## 使用建议 / Usage Recommendations

### 学习路径 / Learning Path

**初学者：**
1. 先阅读 [完整系统流程 (第3节)](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#3-完整的系统初始化与链路发现流程) 了解全局
2. 然后阅读 [拓扑发现流程 (第1节)](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#1-拓扑发现流程) 的Mermaid图
3. 最后阅读 [跨域链路建立 (第2节)](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#2-跨域链路建立流程) 的详细步骤

**开发者：**
1. 参考 [关键技术点 (第5节)](TOPOLOGY_DISCOVERY_FLOWCHARTS.md#5-关键技术点总结) 了解实现细节
2. 查看代码示例和算法实现
3. 参考故障场景进行测试设计

**研究者：**
1. 使用Mermaid图和时序图作为论文插图
2. 参考技术细节部分撰写技术方案
3. 引用实际部署示例作为实验场景

### 论文写作 / Paper Writing

**适用章节：**
- **系统架构章节：** 使用第1节和第2节的流程图
- **协议设计章节：** 引用第5节的技术点
- **实验设置章节：** 参考第5.4节的部署示例
- **性能评估章节：** 使用第3.1节的时间线分析

**图表建议：**
- Mermaid图可以导出为PNG/SVG用于论文
- ASCII图适合作为附录
- 时序图适合展示协议交互

### 开发参考 / Development Reference

**调试时：**
- 参考时序图了解正常流程
- 对照故障场景排查问题
- 检查消息格式是否符合定义

**扩展时：**
- 参考Link Key生成算法设计新的标识符
- 参考AC匹配逻辑实现新的匹配规则
- 遵循现有的消息格式和流程

---

## 更新历史 / Update History

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-03-04 | v1.0 | 初始版本，包含完整的拓扑发现和链路建立流程图 |

---

## 反馈与贡献 / Feedback & Contribution

如有建议或发现问题，请：
- 参考 `EAST_WEST_PROTOCOL_DESIGN.md` 了解协议全貌
- 查看实现代码确认细节
- 提供具体的改进建议

---

**相关文档 / Related Documents:**
- [东西向协议设计文档](EAST_WEST_PROTOCOL_DESIGN.md)
- [协议文档导航](README_PROTOCOL_DOCS.md)
- [同步协议文档](SYNC_PROTOCOL.md)
