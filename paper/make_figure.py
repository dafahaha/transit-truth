import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import numpy as np

# 苹果风格克制配色
INK   = "#1d1d1f"
GRAY  = "#86868b"
BLUE  = "#0a84ff"
TEAL  = "#5ea8a0"
LIGHT = "#dcdce0"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "text.color": INK,
    "axes.edgecolor": LIGHT,
    "axes.labelcolor": INK,
    "xtick.color": GRAY, "ytick.color": INK,
    "axes.linewidth": 0.8,
})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.1), gridspec_kw={"width_ratios":[1.15,1]})

# (a) TVD by probe —— 真实数据
probes = ["number 1-10","color","coin flip","random-100","day","dice roll","letter","animal"]
tvd    = [0.020, 0.220, 0.220, 0.380, 0.320, 0.400, 0.720, 0.900]
order = np.argsort(tvd)
probes = [probes[i] for i in order]; tvd = [tvd[i] for i in order]
colors = [BLUE if v >= 0.7 else (TEAL if v >= 0.4 else "#b8b8be") for v in tvd]
bars = ax1.barh(probes, tvd, color=colors, height=0.62, zorder=3)
ax1.set_xlim(0, 1.0)
ax1.set_xlabel("Total Variation Distance (TVD)")
ax1.xaxis.grid(True, color=LIGHT, linewidth=0.7, zorder=0)
ax1.set_axisbelow(True)
for s in ["top","right","left"]:
    ax1.spines[s].set_visible(False)
ax1.tick_params(left=False)
for b, v in zip(bars, tvd):
    ax1.text(v+0.02, b.get_y()+b.get_height()/2, f"{v:.2f}", va="center",
             fontsize=8.5, color=INK)
ax1.set_title("Same-family discrimination by probe (gpt-4o vs mini)",
              fontsize=9.5, color=INK, pad=10, loc="left", fontweight="bold")

# (b) animal probe: top vs other —— 真实聚合
labels = ["gpt-4o", "gpt-4o-mini"]
top    = [76, 16]
other  = [24, 84]
toplab = ["Okapi", "Dolphin"]
x = np.arange(2)
ax2.bar(x, top, color=BLUE, width=0.5, zorder=3, label="Top response")
ax2.bar(x, other, bottom=top, color=LIGHT, width=0.5, zorder=3, label="Other responses")
for i in range(2):
    ax2.text(i, top[i]/2, f"{toplab[i]}\n{top[i]}%", ha="center", va="center",
             color="white", fontsize=9, fontweight="bold")
    ax2.text(i, top[i]+other[i]/2, f"{other[i]}%", ha="center", va="center",
             color=GRAY, fontsize=9)
ax2.set_xticks(x); ax2.set_xticklabels(labels)
ax2.set_ylim(0,105); ax2.set_yticks([0,25,50,75,100])
ax2.set_ylabel("% of 50 samples")
for s in ["top","right"]:
    ax2.spines[s].set_visible(False)
ax2.set_title("Animal probe: near-perfect separator (TVD = 0.90)",
              fontsize=9.5, color=INK, pad=10, loc="left", fontweight="bold")
ax2.legend(frameon=False, fontsize=8.5, loc="upper center", bbox_to_anchor=(0.5,-0.16), ncol=2)

plt.tight_layout(w_pad=3)
out = r"D:\github项目\transit-truth\paper\fig_results.png"
plt.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
print("saved", out)
