r"""
SDN lab topology: three OpenFlow 1.3 switches in a line, two hosts per switch.

    h1   h2        h3   h4        h5   h6
      \ /            \ /            \ /
      s1 ----------- s2 ----------- s3
                      |
            Ryu controller (ofctl_rest, TCP 6653 / REST 8080)

Every host link is shaped to 100 Mbit/s and the inter-switch links to
20 Mbit/s with Linux HTB (Mininet TCLink).
"""
from functools import partial

from mininet.link import TCLink
from mininet.node import OVSSwitch, RemoteController
from mininet.net import Mininet
from mininet.topo import Topo

HOST_BW = 100   # Mbit/s
TRUNK_BW = 20   # Mbit/s


class LinearSDNTopo(Topo):
    def build(self):
        s1, s2, s3 = (self.addSwitch(f"s{i}", protocols="OpenFlow13") for i in (1, 2, 3))
        for i, sw in zip(range(1, 7), (s1, s1, s2, s2, s3, s3)):
            host = self.addHost(f"h{i}", ip=f"10.0.0.{i}/24")
            self.addLink(host, sw, bw=HOST_BW)
        self.addLink(s1, s2, bw=TRUNK_BW)
        self.addLink(s2, s3, bw=TRUNK_BW)


def build_network(controller_ip="127.0.0.1", controller_port=6653):
    """Create the network attached to a remote (Ryu) controller.

    `datapath="user"` runs Open vSwitch in userspace, so the lab also works on
    hosts without the openvswitch kernel module (containers, WSL, cloud VMs).
    """
    switch = partial(OVSSwitch, datapath="user", protocols="OpenFlow13")
    controller = partial(RemoteController, ip=controller_ip, port=controller_port)
    return Mininet(topo=LinearSDNTopo(), switch=switch, controller=controller,
                   link=TCLink, autoSetMacs=True)


def disable_offload(net):
    """The userspace datapath does not complete veth checksum offload, so TCP/UDP
    packets would arrive with bad checksums. Disable TX offload on every host."""
    for h in net.hosts:
        for intf in h.intfNames():
            h.cmd(f"ethtool -K {intf} tx off rx off >/dev/null 2>&1")


if __name__ == "__main__":
    from mininet.cli import CLI
    from mininet.log import setLogLevel

    setLogLevel("info")
    net = build_network()
    net.start()
    CLI(net)
    net.stop()
