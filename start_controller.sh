#!/usr/bin/env bash
# Start Ryu with the ofctl_rest northbound API (OpenFlow :6653, REST :8080).
cd /opt/ryu && PYTHONPATH=/opt/ryu exec /opt/ryuenv/bin/python -m ryu.cmd.manager ryu.app.ofctl_rest
