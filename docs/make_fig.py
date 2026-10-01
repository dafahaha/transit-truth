#!/usr/bin/env python3
"""Regenerate paper/fig_results.png from the corrected, JSON-derived numbers.
Left: TVD across 8 behavioral probes (sorted desc). Right: animal probe Okapi vs Dolphin.
Run: python docs/make_fig.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

probes = ["Animal", "Letter", "Die roll", "Num 1-100", "Weekday",
          "Color", "Coin flip", "Num 1-10"]
tvd = [0.90, 0.72, 0.40, 0.38, 0.32, 0.22, 0.08, 0.02]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.6))

colors = ["#c0392b" if t >= 0.2 else "#95a5a6" for t in tvd]
ax1.barh(probes[::-1], tvd[::-1], color=colors[::-1])
ax1.set_xlabel("Total Variation Distance")
ax1.set_title("Same-family TVD (gpt-4o vs gpt-4o-mini)")
ax1.set_xlim(0, 1.0)
for i, v in enumerate(tvd[::-1]):
    ax1.text(v + 0.01, i, f"{v:.2f}", va="center", fontsize=8)

# Right: animal probe
labels = ["Okapi", "Dolphin", "Other"]
mini = [0, 16, 84]      # gpt-4o-mini: Okapi 0%, Dolphin 16%, Other 84%
full = [76, 0, 24]      # gpt-4o: Okapi 76%, Other 24%
x = np.arange(2); w = 0.35
ax2.bar(x - w/2, [mini[0], full[0]], w, label="Okapi", color="#2c3e50")
ax2.bar(x - w/2, [mini[1], full[1]], w, bottom=[mini[0], full[0]], label="Dolphin", color="#2980b9")
ax2.bar(x - w/2, [mini[2], full[2]], w,
        bottom=[mini[0]+mini[1], full[0]+full[1]], label="Other", color="#bdc3c7")
ax2.set_xticks(x); ax2.set_xticklabels(["gpt-4o-mini", "gpt-4o"])
ax2.set_ylabel("% of responses"); ax2.set_title("Animal probe")
ax2.legend(fontsize=8, loc="upper right")
ax2.set_ylim(0, 100)

plt.tight_layout()
out = "paper/fig_results.png"
plt.savefig(out, dpi=150, bbox_inches="tight")
print("wrote", out)
