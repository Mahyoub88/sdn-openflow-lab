#!/usr/bin/env bash
# One-time setup on Ubuntu 22.04/24.04 (VM, WSL2 or container). Run as root.
set -euo pipefail
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y mininet openvswitch-switch iproute2 \
    iputils-ping ethtool ffmpeg python3-networkx python3-matplotlib python3-pil git curl
# Open vSwitch daemons (userspace datapath works without the kernel module)
/usr/share/openvswitch/scripts/ovs-ctl start --system-id=random || true
# Ryu controller in its own Python 3.9 environment (Ryu does not run on Python 3.12+)
if [ ! -d /opt/ryuenv ]; then
    command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    ~/.local/bin/uv venv -p 3.9 /opt/ryuenv
    ~/.local/bin/uv pip install -p /opt/ryuenv/bin/python "setuptools<58" "eventlet==0.30.2" \
        msgpack netaddr oslo.config ovs routes tinyrpc webob packaging
    git clone --depth 1 https://github.com/faucetsdn/ryu /opt/ryu
fi
echo "Setup complete. Next: ./start_controller.sh, then sudo python3 experiments/run_lab.py"
