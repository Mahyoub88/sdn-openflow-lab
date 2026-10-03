"""
Build the proactive forwarding table for every switch from the live topology.

For each switch:
  * ARP (eth_type 0x0806)         -> FLOOD            (priority 100)
  * eth_dst == <host MAC>         -> output:<port>    (priority 200)
The port toward each host is derived from the Mininet links, so the same code
works for any tree topology. The generated entries are also written to
automation/flows/<switch>.json so they can be replayed from Postman/curl.
"""
import json
import os

FLOW_DIR = os.path.join(os.path.dirname(__file__), "flows")


def _port_toward(net, switch, host):
    """Port on `switch` that leads to `host` (direct link, else next switch on the path)."""
    import networkx as nx

    g = nx.Graph()
    for link in net.links:
        a, b = link.intf1.node.name, link.intf2.node.name
        g.add_edge(a, b)
    path = nx.shortest_path(g, switch.name, host.name)
    nxt = net.get(path[1])
    for intf in switch.intfList():
        if intf.link and nxt in (intf.link.intf1.node, intf.link.intf2.node) and intf.name != "lo":
            return switch.ports[intf]
    raise RuntimeError(f"no port from {switch.name} to {host.name}")


def build_flows(net):
    os.makedirs(FLOW_DIR, exist_ok=True)
    table = {}
    for sw in net.switches:
        dpid = int(sw.dpid, 16)
        entries = [{"dpid": dpid, "table_id": 0, "priority": 100,
                    "match": {"eth_type": 2054}, "actions": [{"type": "OUTPUT", "port": "FLOOD"}]}]
        for h in net.hosts:
            entries.append({"dpid": dpid, "table_id": 0, "priority": 200,
                            "match": {"eth_dst": h.MAC()},
                            "actions": [{"type": "OUTPUT", "port": _port_toward(net, sw, h)}]})
        table[sw.name] = entries
        with open(os.path.join(FLOW_DIR, f"{sw.name}.json"), "w") as f:
            json.dump(entries, f, indent=2)
    return table


def install(rest, entries):
    for e in entries:
        rest.add_flow(e)
