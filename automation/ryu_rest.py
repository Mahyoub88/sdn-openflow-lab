"""
Minimal client for the Ryu `ofctl_rest` northbound REST API.

The same calls can be sent from Postman or curl; this module just wraps them so
the experiments are repeatable. Every request/response is appended to a JSON
Lines log for the record.
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8080"


class RyuREST:
    def __init__(self, base=BASE, log_path=None):
        self.base = base.rstrip("/")
        self.log_path = log_path

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            status = resp.status
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(json.dumps({"t": round(time.time(), 3), "method": method, "path": path,
                                    "body": body, "status": status}) + "\n")
        return json.loads(raw) if raw.strip().startswith(("{", "[")) else raw

    # --- topology / stats -------------------------------------------------
    def switches(self):
        return self._call("GET", "/stats/switches")

    def flows(self, dpid):
        return self._call("GET", f"/stats/flow/{dpid}")[str(dpid)]

    def port_stats(self, dpid):
        return self._call("GET", f"/stats/port/{dpid}")[str(dpid)]

    def meter_stats(self, dpid):
        return self._call("GET", f"/stats/meter/{dpid}")[str(dpid)]

    # --- flow programming -------------------------------------------------
    def add_flow(self, flow):
        return self._call("POST", "/stats/flowentry/add", flow)

    def delete_flow(self, flow):
        return self._call("POST", "/stats/flowentry/delete_strict", flow)

    def clear_flows(self, dpid):
        return self._call("DELETE", f"/stats/flowentry/clear/{dpid}")

    def add_meter(self, meter):
        return self._call("POST", "/stats/meterentry/add", meter)

    def delete_meter(self, meter):
        return self._call("POST", "/stats/meterentry/delete", meter)
