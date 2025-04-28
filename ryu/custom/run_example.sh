#!/bin/bash
# 记得加执行权限 chmod +x run_example.sh

export PYTHONPATH=$PYTHONPATH:/home/zjx/SDN


# 先启动CC
gnome-terminal -- bash -c "python3 controller/test_cc_controller.py; exec bash"

sleep 1

# 再启动AC
python3 controller/test_ac_controller.py
