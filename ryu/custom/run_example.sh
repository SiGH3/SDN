#!/bin/bash
# 记得加执行权限 chmod +x run_example.sh

export PYTHONPATH=$PYTHONPATH:/home/zjx/SDN


# 启动CC1:9000
gnome-terminal --title="CC-1" -- bash -c "python3 controller/test_cc_controller.py 9000; exec bash"

# 启动CC2:9001
gnome-terminal --title="CC-2" -- bash -c "python3 controller/test_cc_controller.py 9001; exec bash"


sleep 12

# 再启动AC
python3 controller/test_ac_controller.py
