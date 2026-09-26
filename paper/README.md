# Same-Family API Verification — Workshop Paper

A compact, submission-ready version of the TransitTruth behavioral-fingerprinting study.

- **`main.tex`** — LaTeX source (self-contained, two-column, Times; modeled on the NeurIPS style).
- **`main.pdf`** — compiled paper (4 pages of main text + references).
- **`fig_results.png`** — results figure generated from real data.
- **`make_figure.py`** — script that reproduces the figure from the reported statistics.

## Abstract (short)

Can a black-box auditor distinguish a model from a *same-family* sibling — e.g. gpt-4o vs. gpt-4o-mini, which share an identical tokenizer? Across 26 low-cost probes, six of eight behavioral probes separate the two models (p < 0.05), with an animal probe reaching total variation distance 0.90, while tokenizer probes are provably identical. Combined with chi-square/KS tests and Bayesian updating, a held-out sample is assigned to the correct model with 91.3% posterior probability at a cost under $0.01 per audit.

## Build

```bash
pdflatex main.tex
pdflatex main.tex   # second pass for references
```

## Target venues

Suitable for short-paper / workshop tracks on AI safety, trustworthy ML, LLM security, or empirical NLP (e.g. NeurIPS/ICML/ICLR/ACL-affiliated workshops). Before formal submission, swap the preamble for the venue's official style package; the body, figures, and bibliography transfer unchanged.

## Relation to the technical report

`../docs/tech_report.pdf` is the full 20-page report with appendices and the complete methodology; this paper is the condensed, archival version focused on the same-family discrimination result.
