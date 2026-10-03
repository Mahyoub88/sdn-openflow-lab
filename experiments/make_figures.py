#!/usr/bin/env python3
"""Build the README figures (SVG charts + frame comparison) from results/results.json."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                     # noqa: E402
from matplotlib.patches import FancyBboxPatch      # noqa: E402
from PIL import Image, ImageDraw, ImageFont        # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images")
os.makedirs(OUT, exist_ok=True)
r = json.load(open(os.path.join(ROOT, "results", "results.json")))

BLUE, INK, SEC, GRID, BG = "#2a78d6", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"svg.fonttype": "none", "font.family": "DejaVu Sans", "axes.edgecolor": GRID,
                     "axes.labelcolor": SEC, "xtick.color": SEC, "ytick.color": SEC,
                     "figure.facecolor": BG, "axes.facecolor": BG})


def style(ax, title, ylabel):
    ax.set_title(title, color=INK, loc="left", fontsize=11)
    ax.set_ylabel(ylabel)
    ax.yaxis.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)


def bars(labels, vals, fmt, title, ylabel, xlabel, fn, ymax=None, note=None):
    fig, ax = plt.subplots(figsize=(7, 3.6))
    b = ax.bar(labels, vals, color=BLUE, width=0.55)
    for rect, v in zip(b, vals):
        ax.text(rect.get_x() + rect.get_width() / 2, v, fmt.format(v), ha="center", va="bottom",
                color=INK, fontsize=9)
    style(ax, title, ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ymax:
        ax.set_ylim(0, ymax)
    if note:
        fig.text(0.01, 0.01, note, color=SEC, fontsize=7.5)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
    else:
        fig.tight_layout()
    fig.savefig(os.path.join(OUT, fn))
    plt.close(fig)


# Experiment 1
st = r["experiment1"]
bars(["Empty tables", "Flows pushed\nvia REST", "s3 table\ncleared", "s3 restored\nfrom s3.json"],
     [st[0]["pingall_loss_pct"], st[1]["h4_to_h6_loss_pct"], st[2]["h4_to_h6_loss_pct"], st[3]["h4_to_h6_loss_pct"]],
     "{:.0f}%", "Experiment 1 — h4 → h6 ping loss at each step", "Packet loss (%)", None,
     "exp1_h4_h6_loss.svg", 115, "Step 1 is the pingAll loss across all hosts with no flows installed.")

# Experiment 2
runs = r["experiment2"]["runs"]
labels = ["No meter" if x["meter_kbps"] is None else f"{x['meter_kbps']} kbps" for x in runs]
xl = f"OpenFlow meter on s1 (video ≈ {r['experiment2']['video_kbps']} kbps)"
bars(labels, [x["psnr_db"] for x in runs], "{:.1f}", "Received video PSNR vs meter rate", "PSNR (dB)", xl,
     "exp2_psnr.svg", 46)
bars(labels, [x["ssim"] for x in runs], "{:.3f}", "Received video SSIM vs meter rate", "SSIM", xl,
     "exp2_ssim.svg", 1.1)
bars(labels, [x["received_bytes"] / 1e6 for x in runs], "{:.2f}",
     f"Bytes received at h6 (source {r['experiment2']['source_bytes'] / 1e6:.2f} MB)", "Received (MB)", xl,
     "exp2_received.svg")

# Topology
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 5)


def box(x, y, t, w=1.2, h=0.6, fc="#cde2fb"):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.05", fc=fc, ec=BLUE, lw=1.2))
    ax.text(x, y, t, ha="center", va="center", color=INK, fontsize=9)


sw = {"s1": 2, "s2": 5, "s3": 8}
ax.plot([2, 8], [2.4, 2.4], color=SEC, lw=2, zorder=0)
for k, x in sw.items():
    box(x, 2.4, k)
for x in (3.5, 6.5):
    ax.text(x, 2.6, "20 Mbit/s", ha="center", color=SEC, fontsize=7.5)
for i, x in enumerate((1.4, 2.6, 4.4, 5.6, 7.4, 8.6)):
    ax.plot([x, (2, 5, 8)[i // 2]], [0.8, 2.1], color=SEC, lw=1, zorder=0)
    box(x, 0.8, f"h{i + 1}\n10.0.0.{i + 1}", w=0.95, h=0.7, fc="#ffffff")
box(5, 4.3, "Ryu controller — ofctl_rest\nOpenFlow 1.3 :6653   REST :8080", w=4.2, h=0.8, fc="#ffffff")
for x in (2, 5, 8):
    ax.plot([x, 5], [2.7, 3.9], color=BLUE, lw=1, ls="--", zorder=0)
ax.text(9.6, 4.3, "REST client\n(Python / Postman)", ha="right", va="center", color=SEC, fontsize=8)
ax.annotate("", xy=(7.1, 4.3), xytext=(8.3, 4.3), arrowprops=dict(arrowstyle="->", color=SEC))
fig.tight_layout(); fig.savefig(os.path.join(OUT, "topology.svg")); plt.close(fig)

# Frame comparison (t = 6 s)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
names = {"no_meter": "No meter", "meter_3000kbps": "Meter 3000 kbps",
         "meter_1500kbps": "Meter 1500 kbps", "meter_800kbps": "Meter 800 kbps"}
by = {x["scenario"]: x for x in runs}
items = [("source", "Source video (sent by h1)")] + [
    (k, f"{v}  ·  PSNR {by[k]['psnr_db']:.1f} dB · SSIM {by[k]['ssim']:.3f}") for k, v in names.items()]
W, H = 480, 270
canvas = Image.new("RGB", (W * 2 + 30, (H + 34) * 3 + 10), BG)
d = ImageDraw.Draw(canvas)
for i, (k, cap) in enumerate(items):
    x, y = 10 + (i % 2) * (W + 10), 10 + (i // 2) * (H + 34)
    canvas.paste(Image.open(os.path.join(ROOT, "results", "frames", f"{k}.png")).convert("RGB").resize((W, H)), (x, y + 24))
    d.text((x, y + 3), cap, fill=INK, font=font)
canvas.save(os.path.join(OUT, "exp2_frames_t6s.webp"), "WEBP", quality=70, method=6)
print("figures written to", OUT)
