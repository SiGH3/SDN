#!/bin/bash
# 记得加执行权限 chmod +x run_example.sh

export PYTHONPATH=$PYTHONPATH:/home/zjx/SDN

# 启动AC
gnome-terminal --title="AC" -- bash -c "python3 controller/test_ac_controller.py; exec bash"

sleep 2

# 启动CC1:9000
gnome-terminal --title="CC-1" -- bash -c "python3 controller/test_cc_controller.py 9000; exec bash"

# 启动CC2:9001
gnome-terminal --title="CC-2" -- bash -c "python3 controller/test_cc_controller.py 9001; exec bash"

# 启动CC3:9002
gnome-terminal --title="CC-3" -- bash -c "python3 controller/test_cc_controller.py 9002; exec bash"





