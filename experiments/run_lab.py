#!/usr/bin/env python3
"""
Run both SDN experiments end to end and write all evidence to results/.

  Experiment 1 - configuration automation over the REST API
      * empty flow tables  -> no connectivity
      * flows pushed by REST -> full connectivity
      * s3 flow table wiped -> h4 cannot reach h6
      * s3 table restored from automation/flows/s3.json -> h4 reaches h6 again

  Experiment 2 - video streaming with controller-enforced rate limits
      * h1 streams an H.264 MPEG-TS video to h6 over UDP
      * the controller installs an OpenFlow 1.3 meter on s1 for that flow
      * received quality (PSNR / SSIM, frames decoded, loss) is measured
        for each meter rate - the only thing that changes between runs is
        METER_RATES_KBPS below.

Usage (as root, with Ryu running:  ryu-manager ryu.app.ofctl_rest):
    sudo python3 experiments/run_lab.py
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "topology"), os.path.join(ROOT, "automation")]

from mininet.log import setLogLevel                     # noqa: E402
from sdn_topo import build_network, disable_offload      # noqa: E402
from ryu_rest import RyuREST                             # noqa: E402
import flow_builder                                      # noqa: E402

RES = os.path.join(ROOT, "results")
LOG = os.path.join(RES, "logs")
FRAMES = os.path.join(RES, "frames")
VIDEO_SRC = os.path.join(RES, "video_src.ts")

METER_RATES_KBPS = [None, 3000, 1500, 800]   # None = no meter (baseline)
VIDEO_KBPS = 2500                              # target video bitrate
VIDEO_SECONDS = 12


def ping(src, dst, count=3):
    out = src.cmd(f"ping -c {count} -W 1 {dst.IP()}")
    m = re.search(r"(\d+)% packet loss", out)
    return (int(m.group(1)) if m else 100), out


def wait_for_switches(rest, n=3, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if len(rest.switches()) >= n:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("switches did not connect to the controller")


def experiment1(net, rest, report):
    h4, h6 = net.get("h4", "h6")
    steps = []

    loss = net.pingAll(timeout="1")
    steps.append({"step": "1. empty flow tables", "pingall_loss_pct": loss})

    table = flow_builder.build_flows(net)
    t0 = time.time()
    for sw in ("s1", "s2", "s3"):
        flow_builder.install(rest, table[sw])
    steps.append({"step": "2. flows installed via REST",
                  "rest_calls": sum(len(v) for v in table.values()),
                  "install_seconds": round(time.time() - t0, 3)})
    time.sleep(1)
    steps[-1]["pingall_loss_pct"] = net.pingAll(timeout="1")
    l, out = ping(h4, h6)
    steps[-1]["h4_to_h6_loss_pct"] = l

    with open(os.path.join(LOG, "exp1_s3_flows_before.json"), "w") as f:
        json.dump(rest.flows(3), f, indent=2)

    rest.clear_flows(3)
    time.sleep(1)
    l, out = ping(h4, h6)
    steps.append({"step": "3. s3 flow table cleared via REST", "h4_to_h6_loss_pct": l})
    open(os.path.join(LOG, "exp1_ping_after_clear.txt"), "w").write(out)
    with open(os.path.join(LOG, "exp1_s3_flows_cleared.json"), "w") as f:
        json.dump(rest.flows(3), f, indent=2)

    entries = json.load(open(os.path.join(flow_builder.FLOW_DIR, "s3.json")))
    t0 = time.time()
    flow_builder.install(rest, entries)
    restore_s = round(time.time() - t0, 3)
    time.sleep(1)
    l, out = ping(h4, h6)
    steps.append({"step": "4. s3 restored from s3.json via REST", "rest_calls": len(entries),
                  "restore_seconds": restore_s, "h4_to_h6_loss_pct": l})
    open(os.path.join(LOG, "exp1_ping_after_restore.txt"), "w").write(out)
    with open(os.path.join(LOG, "exp1_s3_flows_restored.json"), "w") as f:
        json.dump(rest.flows(3), f, indent=2)

    report["experiment1"] = steps


def make_source_video():
    if os.path.exists(VIDEO_SRC):
        return
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc2=size=640x360:rate=25", "-t", str(VIDEO_SECONDS),
                    "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{VIDEO_KBPS}k",
                    "-maxrate", f"{VIDEO_KBPS}k", "-bufsize", f"{VIDEO_KBPS // 2}k",
                    "-g", "25", "-pix_fmt", "yuv420p", "-f", "mpegts", VIDEO_SRC], check=True)


def quality(recv):
    """PSNR / SSIM of the received stream against the source, plus decodable frames."""
    def metric(filt, rx):
        p = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "info", "-err_detect", "ignore_err",
                            "-i", recv, "-i", VIDEO_SRC, "-lavfi", filt, "-f", "null", "-"],
                           capture_output=True, text=True)
        m = re.search(rx, p.stderr)
        return float(m.group(1)) if m else None
    psnr = metric("[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]psnr", r"PSNR .*average:([\d.inf]+)")
    ssim = metric("[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[a][b]ssim", r"SSIM .*All:([\d.]+)")
    p = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                        "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", recv],
                       capture_output=True, text=True)
    digits = re.findall(r"\d+", p.stdout)
    frames = int(digits[0]) if digits else 0
    return psnr, ssim, frames


def experiment2(net, rest, report):
    make_source_video()
    h1, h6 = net.get("h1", "h6")
    s1_dpid = 1
    runs = []
    for rate in METER_RATES_KBPS:
        tag = "no_meter" if rate is None else f"meter_{rate}kbps"
        recv = os.path.join(RES, f"video_recv_{tag}.ts")
        if os.path.exists(recv):
            os.remove(recv)
        flow = {"dpid": s1_dpid, "table_id": 0, "priority": 300,
                "match": {"eth_type": 2048, "ip_proto": 17, "ipv4_dst": h6.IP(), "udp_dst": 5004}}
        if rate is not None:
            rest.add_meter({"dpid": s1_dpid, "flags": "KBPS", "meter_id": 1,
                            "bands": [{"type": "DROP", "rate": rate}]})
            port = flow_builder._port_toward(net, net.get("s1"), h6)
            rest.add_flow(dict(flow, actions=[{"type": "METER", "meter_id": 1},
                                              {"type": "OUTPUT", "port": port}]))
        time.sleep(1)
        rx = h6.popen(["ffmpeg", "-y", "-loglevel", "error", "-i",
                       "udp://0.0.0.0:5004?fifo_size=1000000&overrun_nonfatal=1&timeout=5000000",
                       "-c", "copy", "-f", "mpegts", recv])
        time.sleep(1)
        h1.cmd(f"ffmpeg -loglevel error -re -i {VIDEO_SRC} -c copy -f mpegts "
               f"'udp://10.0.0.6:5004?pkt_size=1316'")
        try:
            rx.wait(timeout=15)
        except subprocess.TimeoutExpired:
            rx.terminate()
            rx.wait()
        dropped = None
        if rate is not None:
            ms = rest.meter_stats(s1_dpid)
            with open(os.path.join(LOG, f"exp2_meter_stats_{tag}.json"), "w") as f:
                json.dump(ms, f, indent=2)
            dropped = sum(b.get("packet_band_count", 0) for m in ms for b in m.get("band_stats", []))
            rest.delete_flow(dict(flow, actions=[]))
            rest.delete_meter({"dpid": s1_dpid, "meter_id": 1})
        size = os.path.getsize(recv) if os.path.exists(recv) else 0
        psnr, ssim, frames = quality(recv) if size else (None, None, 0)
        if size:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "6", "-i", recv,
                            "-frames:v", "1", os.path.join(FRAMES, f"{tag}.png")])
        runs.append({"scenario": tag, "meter_kbps": rate, "received_bytes": size,
                     "decoded_frames": frames, "meter_dropped_packets": dropped,
                     "psnr_db": psnr, "ssim": ssim})
        print(runs[-1], flush=True)
    src_frames = quality(VIDEO_SRC)[2]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "6", "-i", VIDEO_SRC,
                    "-frames:v", "1", os.path.join(FRAMES, "source.png")])
    report["experiment2"] = {"video_kbps": VIDEO_KBPS, "seconds": VIDEO_SECONDS,
                             "source_bytes": os.path.getsize(VIDEO_SRC),
                             "source_frames": src_frames, "runs": runs}


def main():
    setLogLevel("warning")
    os.makedirs(LOG, exist_ok=True)
    os.makedirs(FRAMES, exist_ok=True)
    rest = RyuREST(log_path=os.path.join(LOG, "rest_calls.jsonl"))
    open(rest.log_path, "w").close()
    net = build_network()
    net.start()
    disable_offload(net)
    report = {"started": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        wait_for_switches(rest)
        experiment1(net, rest, report)
        experiment2(net, rest, report)
    finally:
        net.stop()
    with open(os.path.join(RES, "results.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
