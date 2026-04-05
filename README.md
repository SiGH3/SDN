# SDN
ryu mininet-wifi ovs

## 跨域通信测试

本项目支持跨域（多集群）SDN控制器测试，包括聚合控制器(AC)和集群控制器(CC)的协同工作。

### 快速开始

- **快速参考**: [跨域通信快速参考卡](ryu/custom/docs/CROSS_DOMAIN_QUICKSTART.md)
- **详细文档**: [跨域通信测试配置与方法](ryu/custom/docs/CROSS_DOMAIN_TEST.md)
- **自动化脚本**: [setup_cross_domain_test.sh](ryu/custom/scripts/setup_cross_domain_test.sh)

### 测试场景

支持在多台独立机器上进行跨域通信测试：
- 控制器节点：运行AC和多个CC实例
- 边界节点：运行OVS交换机，连接到各自的CC控制器
- 通过LLDP自动发现跨域链路
- AC计算跨域路径并下发流表

### 使用方法

1. 在控制器节点运行配置脚本：
   ```bash
   bash ryu/custom/scripts/setup_cross_domain_test.sh
   ```

2. 选择角色并按提示配置

3. 执行跨域通信测试

详见文档以获取完整配置和测试步骤。

## 相关文档

- [三集群最小演示](ryu/custom/demo/3cluster-demo.md)
- [my_simple_switch集成指南](ryu/custom/docs/MY_SIMPLE_SWITCH_INTEGRATION.md)
- [同步协议详情](ryu/custom/docs/SYNC_PROTOCOL.md)
