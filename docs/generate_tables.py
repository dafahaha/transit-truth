#!/usr/bin/env python3
"""Generate all distribution / TVD / chi-square tables for the tech report
directly from data/baselines/*.json. No hand-entered numbers.

Run:  python docs/generate_tables.py
"""
import json, os
from collections import Counter
import numpy as np
from scipy import stats

BASE = os.path.join(os.path.dirname(__file__), "..", "data", "baselines")

def load(name):
    with open(os.path.join(BASE, name), encoding="utf-8") as f:
        return json.load(f)

def norm(k):
    return k.strip().rstrip(".").strip().lower()

mini = load("gpt-4o-mini.json")
full = load("gpt-4o.json")

def dist(d, p):
    return d["behavioral"][p]["response_distribution"]

def agg(d, p):
    raw = dist(d, p)
    out = {}
    for k, v in raw.items():
        nk = norm(k)
        out[nk] = out.get(nk, 0) + v
    return out

PROBES = [
    ("beh-number-1-10", "Number 1-10", 10),
    ("beh-random-100", "Number 1-100", 100),
    ("beh-dice-roll", "Die roll", 6),
    ("beh-coin-flip", "Coin flip", 2),
    ("beh-random-letter", "Letter", 26),
    ("beh-random-day", "Weekday", 7),
    ("beh-random-color", "Color (open)", None),
    ("beh-random-animal", "Animal (open)", None),
]

print("=== Table: single-model fingerprints (gpt-4o-mini, normalized) ===")
for pid, name, J in PROBES:
    d = agg(mini, pid)
    top, cnt = max(d.items(), key=lambda x: x[1])
    n = sum(d.values())
    print(f"  {name:16s} top={top!r:12s} {cnt}/{n} = {cnt/n*100:.0f}%  unique={len(d)}")

print("\n=== Table: GoF chi-square vs uniform (closed-set, theoretical J) ===")
for pid, name, J in PROBES:
    if J is None:
        print(f"  {name:16s} open-ended, no unique uniform reference")
        continue
    d = agg(mini, pid)
    n = sum(d.values()); E = n/J
    chi2 = sum((v-E)**2/E for v in d.values()) + (J-len(d))*E**2/E
    p = 1 - stats.chi2.cdf(chi2, df=J-1)
    print(f"  {name:16s} J={J:3d} chi2={chi2:9.1f} p={p:.2e}")

print("\n=== Table: two-model homogeneity (TVD + chi-square p) ===")
rows = []
for pid, name, _ in PROBES:
    a = agg(mini, pid); b = agg(full, pid)
    cats = sorted(set(a) | set(b))
    n1 = sum(a.values()); n2 = sum(b.values())
    p1 = np.array([a.get(c,0)/n1 for c in cats])
    p2 = np.array([b.get(c,0)/n2 for c in cats])
    tvd = 0.5*np.sum(np.abs(p1-p2))
    obs = np.array([[a.get(c,0) for c in cats],[b.get(c,0) for c in cats]])
    chi2, pval, _, _ = stats.chi2_contingency(obs, correction=False)
    ta, ca = max(a.items(), key=lambda x: x[1])
    tb, cb = max(b.items(), key=lambda x: x[1])
    rows.append((name, ta, ca, n1, tb, cb, n2, tvd, pval))
rows.sort(key=lambda r: -r[7])
for name, ta, ca, n1, tb, cb, n2, tvd, pval in rows:
    print(f"  {name:16s} mini top={ta!r:10s} {ca/n1*100:3.0f}%  4o top={tb!r:10s} {cb/n2*100:3.0f}%  TVD={tvd:.2f}  p={pval:.4f}")

print("\n=== Animal-probe Okapi classifier (resubstitution) ===")
am = dist(mini, "beh-random-animal"); af = dist(full, "beh-random-animal")
y_true, y_pred = [], []
for k, c in af.items():
    for _ in range(c):
        y_true.append(1); y_pred.append(1 if k.lower() == "okapi" else 0)
for k, c in am.items():
    for _ in range(c):
        y_true.append(0); y_pred.append(1 if k.lower() == "okapi" else 0)
y_true = np.array(y_true); y_pred = np.array(y_pred)
TP = int(((y_pred==1)&(y_true==1)).sum()); FP = int(((y_pred==1)&(y_true==0)).sum())
FN = int(((y_pred==0)&(y_true==1)).sum()); TN = int(((y_pred==0)&(y_true==0)).sum())
acc = (TP+TN)/len(y_true)
def wilson(k, n, z=1.96):
    p=k/n; den=1+z*z/n; c=(p+z*z/(2*n))/den
    h=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return c-h, c+h
lo, hi = wilson(TP+TN, len(y_true))
print(f"  TP={TP} FP={FP} FN={FN} TN={TN}  accuracy={acc:.3f}  Wilson95%CI=[{lo:.3f},{hi:.3f}]")
