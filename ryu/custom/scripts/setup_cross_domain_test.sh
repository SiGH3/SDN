#!/bin/bash
# 跨域通信测试自动化配置脚本
# 本脚本用于在三台机器上快速配置跨域通信测试环境

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测当前机器角色
detect_role() {
    echo "请选择当前机器的角色："
    echo "1) 控制器节点 (运行AC和CC)"
    echo "2) 集群1边界节点 (OVS - 192.168.179.133)"
    echo "3) 集群2边界节点 (OVS - 172.168.157.128)"
    read -p "请输入选择 [1-3]: " role
    echo "$role"
}

# 配置控制器节点 (机器1: 172.30.1.137)
setup_controller_node() {
    print_info "配置控制器节点..."
    
    # 获取SDN项目路径
    if [ -z "$SDN_PATH" ]; then
        read -p "请输入SDN项目的绝对路径 [默认: $HOME/SDN]: " SDN_PATH
        SDN_PATH=${SDN_PATH:-$HOME/SDN}
    fi
    
    if [ ! -d "$SDN_PATH" ]; then
        print_error "SDN项目路径不存在: $SDN_PATH"
        exit 1
    fi
    
    cd "$SDN_PATH"
    
    # 创建启动脚本目录
    mkdir -p scripts/cross_domain
    
    # 创建AC启动脚本
    cat > scripts/cross_domain/start_ac.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/../.."
export PYTHONPATH=$(pwd):$PYTHONPATH

echo "===================================="
echo "启动AC聚合控制器"
echo "端口: 10000"
echo "===================================="
python3 -m ryu.custom.controller.test_ac_controller 10000
EOF
    
    # 创建CC1启动脚本
    cat > scripts/cross_domain/start_cc1.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/../.."
export PYTHONPATH=$(pwd):$PYTHONPATH

# CC1配置
export CLUSTER_ID=1
export AC_HOST=172.30.1.137
export AC_PORT=10000
export DST_CLUSTERS=2

echo "===================================="
echo "启动CC1集群控制器"
echo "集群ID: 1"
echo "OpenFlow端口: 6653"
echo "AC地址: ${AC_HOST}:${AC_PORT}"
echo "目标集群: ${DST_CLUSTERS}"
echo "===================================="

ryu-manager \
    --observe-links \
    --ofp-tcp-listen-port 6653 \
    ryu/custom/my_simple_switch_13.py
EOF
    
    # 创建CC2启动脚本
    cat > scripts/cross_domain/start_cc2.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/../.."
export PYTHONPATH=$(pwd):$PYTHONPATH

# CC2配置
export CLUSTER_ID=2
export AC_HOST=172.30.1.137
export AC_PORT=10000
export DST_CLUSTERS=1

echo "===================================="
echo "启动CC2集群控制器"
echo "集群ID: 2"
echo "OpenFlow端口: 6654"
echo "AC地址: ${AC_HOST}:${AC_PORT}"
echo "目标集群: ${DST_CLUSTERS}"
echo "===================================="

ryu-manager \
    --observe-links \
    --ofp-tcp-listen-port 6654 \
    ryu/custom/my_simple_switch_13.py
EOF
    
    # 创建一键启动脚本（使用tmux）
    cat > scripts/cross_domain/start_all_controllers.sh << 'EOF'
#!/bin/bash
# 使用tmux在同一终端的不同窗格启动所有控制器

SESSION_NAME="cross_domain_controllers"

# 检查tmux是否安装
if ! command -v tmux &> /dev/null; then
    echo "错误: 需要安装tmux"
    echo "安装命令: sudo apt-get install tmux"
    exit 1
fi

# 如果会话已存在，先结束它
tmux has-session -t $SESSION_NAME 2>/dev/null && tmux kill-session -t $SESSION_NAME

# 创建新会话并启动AC
tmux new-session -d -s $SESSION_NAME -n "AC" "bash scripts/cross_domain/start_ac.sh"

# 创建新窗口启动CC1
tmux new-window -t $SESSION_NAME -n "CC1" "bash scripts/cross_domain/start_cc1.sh"

# 创建新窗口启动CC2
tmux new-window -t $SESSION_NAME -n "CC2" "bash scripts/cross_domain/start_cc2.sh"

# 切换到AC窗口
tmux select-window -t $SESSION_NAME:0

echo "===================================="
echo "所有控制器已在tmux会话中启动"
echo "===================================="
echo "使用以下命令连接到会话:"
echo "  tmux attach -t $SESSION_NAME"
echo ""
echo "在tmux中的操作:"
echo "  Ctrl+b 然后按 0/1/2 - 切换到AC/CC1/CC2窗口"
echo "  Ctrl+b 然后按 d     - 分离会话（保持后台运行）"
echo "  Ctrl+c              - 停止当前窗口的控制器"
echo ""
echo "停止所有控制器:"
echo "  tmux kill-session -t $SESSION_NAME"
echo "===================================="

# 自动连接到会话
tmux attach -t $SESSION_NAME
EOF
    
    # 赋予执行权限
    chmod +x scripts/cross_domain/*.sh
    
    print_info "控制器节点配置完成！"
    print_info "启动脚本已创建在: $SDN_PATH/scripts/cross_domain/"
    echo ""
    print_info "启动方式1 - 分别启动（推荐用于调试）:"
    echo "  终端1: ./scripts/cross_domain/start_ac.sh"
    echo "  终端2: ./scripts/cross_domain/start_cc1.sh"
    echo "  终端3: ./scripts/cross_domain/start_cc2.sh"
    echo ""
    print_info "启动方式2 - 使用tmux一键启动:"
    echo "  ./scripts/cross_domain/start_all_controllers.sh"
}

# 配置集群1边界节点 (机器2: 192.168.179.133)
setup_cluster1_node() {
    print_info "配置集群1边界节点..."
    
    # 检查OVS是否安装
    if ! command -v ovs-vsctl &> /dev/null; then
        print_error "Open vSwitch未安装"
        print_info "安装命令: sudo apt-get install openvswitch-switch"
        exit 1
    fi
    
    # 获取配置参数
    read -p "CC1控制器IP [默认: 172.30.1.137]: " CC1_IP
    CC1_IP=${CC1_IP:-172.30.1.137}
    
    read -p "CC1控制器端口 [默认: 6653]: " CC1_PORT
    CC1_PORT=${CC1_PORT:-6653}
    
    read -p "集群2边界节点IP (用于VXLAN) [默认: 172.168.157.128]: " CLUSTER2_IP
    CLUSTER2_IP=${CLUSTER2_IP:-172.168.157.128}
    
    # 创建配置脚本
    cat > /tmp/setup_cluster1_ovs.sh << EOF
#!/bin/bash
set -e

echo "清理已有配置..."
sudo ovs-vsctl del-br br-c1 2>/dev/null || true

echo "创建集群1网桥..."
sudo ovs-vsctl add-br br-c1
sudo ovs-vsctl set bridge br-c1 other-config:datapath-id=0000000000000001

echo "配置控制器连接..."
sudo ovs-vsctl set-controller br-c1 tcp:${CC1_IP}:${CC1_PORT}
sudo ovs-vsctl set-fail-mode br-c1 secure

echo "创建测试主机接口..."
sudo ovs-vsctl add-port br-c1 veth-h1 -- set interface veth-h1 type=internal
sudo ip link set veth-h1 up
sudo ip addr add 10.0.1.10/24 dev veth-h1 2>/dev/null || true

echo "创建到集群2的VXLAN隧道..."
sudo ovs-vsctl add-port br-c1 vxlan-c2 -- set interface vxlan-c2 \\
    type=vxlan \\
    options:remote_ip=${CLUSTER2_IP} \\
    options:key=100

echo "验证配置..."
sudo ovs-vsctl show
echo ""
echo "检查控制器连接..."
sudo ovs-ofctl show br-c1

echo ""
echo "===================================="
echo "集群1边界节点配置完成!"
echo "===================================="
echo "网桥: br-c1"
echo "DataPath ID: 0000000000000001"
echo "控制器: tcp:${CC1_IP}:${CC1_PORT}"
echo "测试主机IP: 10.0.1.10"
echo "VXLAN隧道到: ${CLUSTER2_IP}"
echo ""
echo "测试连接:"
echo "  ping -I veth-h1 10.0.2.20"
EOF
    
    chmod +x /tmp/setup_cluster1_ovs.sh
    print_info "配置脚本已创建: /tmp/setup_cluster1_ovs.sh"
    print_warn "需要root权限执行，是否立即执行? [y/N]"
    read -p "> " execute
    
    if [[ "$execute" =~ ^[Yy]$ ]]; then
        bash /tmp/setup_cluster1_ovs.sh
    else
        print_info "请手动执行: bash /tmp/setup_cluster1_ovs.sh"
    fi
}

# 配置集群2边界节点 (机器3: 172.168.157.128)
setup_cluster2_node() {
    print_info "配置集群2边界节点..."
    
    # 检查OVS是否安装
    if ! command -v ovs-vsctl &> /dev/null; then
        print_error "Open vSwitch未安装"
        print_info "安装命令: sudo apt-get install openvswitch-switch"
        exit 1
    fi
    
    # 获取配置参数
    read -p "CC2控制器IP [默认: 172.30.1.137]: " CC2_IP
    CC2_IP=${CC2_IP:-172.30.1.137}
    
    read -p "CC2控制器端口 [默认: 6654]: " CC2_PORT
    CC2_PORT=${CC2_PORT:-6654}
    
    read -p "集群1边界节点IP (用于VXLAN) [默认: 192.168.179.133]: " CLUSTER1_IP
    CLUSTER1_IP=${CLUSTER1_IP:-192.168.179.133}
    
    # 创建配置脚本
    cat > /tmp/setup_cluster2_ovs.sh << EOF
#!/bin/bash
set -e

echo "清理已有配置..."
sudo ovs-vsctl del-br br-c2 2>/dev/null || true

echo "创建集群2网桥..."
sudo ovs-vsctl add-br br-c2
sudo ovs-vsctl set bridge br-c2 other-config:datapath-id=0000000000000002

echo "配置控制器连接..."
sudo ovs-vsctl set-controller br-c2 tcp:${CC2_IP}:${CC2_PORT}
sudo ovs-vsctl set-fail-mode br-c2 secure

echo "创建测试主机接口..."
sudo ovs-vsctl add-port br-c2 veth-h2 -- set interface veth-h2 type=internal
sudo ip link set veth-h2 up
sudo ip addr add 10.0.2.20/24 dev veth-h2 2>/dev/null || true

echo "创建到集群1的VXLAN隧道..."
sudo ovs-vsctl add-port br-c2 vxlan-c1 -- set interface vxlan-c1 \\
    type=vxlan \\
    options:remote_ip=${CLUSTER1_IP} \\
    options:key=100

echo "验证配置..."
sudo ovs-vsctl show
echo ""
echo "检查控制器连接..."
sudo ovs-ofctl show br-c2

echo ""
echo "===================================="
echo "集群2边界节点配置完成!"
echo "===================================="
echo "网桥: br-c2"
echo "DataPath ID: 0000000000000002"
echo "控制器: tcp:${CC2_IP}:${CC2_PORT}"
echo "测试主机IP: 10.0.2.20"
echo "VXLAN隧道到: ${CLUSTER1_IP}"
echo ""
echo "测试连接:"
echo "  ping -I veth-h2 10.0.1.10"
EOF
    
    chmod +x /tmp/setup_cluster2_ovs.sh
    print_info "配置脚本已创建: /tmp/setup_cluster2_ovs.sh"
    print_warn "需要root权限执行，是否立即执行? [y/N]"
    read -p "> " execute
    
    if [[ "$execute" =~ ^[Yy]$ ]]; then
        bash /tmp/setup_cluster2_ovs.sh
    else
        print_info "请手动执行: bash /tmp/setup_cluster2_ovs.sh"
    fi
}

# 主函数
main() {
    echo "===================================="
    echo "跨域通信测试环境配置向导"
    echo "===================================="
    echo ""
    
    role=$(detect_role)
    
    case $role in
        1)
            setup_controller_node
            ;;
        2)
            setup_cluster1_node
            ;;
        3)
            setup_cluster2_node
            ;;
        *)
            print_error "无效的选择"
            exit 1
            ;;
    esac
    
    echo ""
    print_info "配置完成！请参考 ryu/custom/docs/CROSS_DOMAIN_TEST.md 进行测试"
}

# 运行主函数
main
