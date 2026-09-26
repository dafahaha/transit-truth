# -*- coding: utf-8 -*-
"""Convert experiment_report.md to an academic-styled HTML (Apple-like minimalism)."""
import re
import markdown

SRC = r'D:\github项目\transit-truth\docs\experiment_report.md'
OUT = r'D:\github项目\transit-truth\docs\tech_report.html'

with open(SRC, encoding='utf-8') as f:
    md = f.read()

# Markdown -> HTML
body = markdown.markdown(md, extensions=['tables', 'fenced_code', 'sane_lists'])

# 数学公式：保留 $$ ... $$ 为排版（浏览器渲染 LaTeX 需要 MathJax，headless 打印不含）
# 用 HTML 上标/斜体近似即可：这里简单替换 $...$ 内的 ^ 为上标标记
def _inline_math(m):
    expr = m.group(1)
    expr = re.sub(r'\^2', '&sup2;', expr)
    expr = re.sub(r'\^', '<sup>', expr)
    expr = re.sub(r'<sup>(\w)', r'<sup>\1', expr)
    return '<span class="math">' + expr + '</span>'
body = re.sub(r'\$([^$]+)\$', _inline_math, body)

css = """
:root { --ink:#1d1d1f; --sub:#6e6e73; --accent:#0a84ff; --line:#e5e5ea; --bg:#ffffff; --code-bg:#f5f5f7; }
* { box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',Roboto,'Helvetica Neue',sans-serif;
  color:var(--ink); line-height:1.65; margin:0; background:var(--bg); }
.page { max-width:900px; margin:0 auto; padding:56px 40px 80px; }
header.title-block { text-align:center; padding:24px 0 28px; border-bottom:1px solid var(--line); margin-bottom:32px; }
h1 { font-size:30px; font-weight:700; letter-spacing:-0.02em; line-height:1.25; margin:0 0 10px; }
.subtitle { color:var(--sub); font-size:15px; margin-bottom:6px; }
.authors { font-size:16px; font-weight:600; margin-top:14px; }
.affil { color:var(--sub); font-size:13.5px; }
.abstract-box { background:var(--code-bg); border-radius:14px; padding:22px 26px; margin:24px 0 8px; }
.abstract-box h2 { margin-top:0; font-size:13px; text-transform:uppercase; letter-spacing:0.08em; color:var(--sub); }
.abstract-box p { font-size:14.5px; margin:8px 0; }
h2 { font-size:21px; font-weight:700; margin:38px 0 12px; letter-spacing:-0.01em; }
h3 { font-size:16.5px; font-weight:600; margin:26px 0 8px; }
p { font-size:15px; margin:10px 0; }
table { border-collapse:collapse; width:100%; margin:16px 0; font-size:13.5px; }
th { background:var(--code-bg); text-align:left; font-weight:600; }
th,td { border:1px solid var(--line); padding:8px 12px; }
tr:nth-child(even) td { background:#fafafa; }
code { background:var(--code-bg); border-radius:5px; padding:1.5px 6px; font-size:13px;
  font-family:'SF Mono',Menlo,Consolas,monospace; }
pre { background:var(--code-bg); border-radius:12px; padding:16px 20px; overflow-x:auto; }
pre code { background:none; padding:0; font-size:12.5px; }
blockquote { border-left:3px solid var(--accent); margin:14px 0; padding:2px 18px; color:var(--sub); }
.math { font-family:'STIX Two Math',Georgia,'Times New Roman',serif; font-style:italic; }
a { color:var(--accent); text-decoration:none; }
hr { border:none; border-top:1px solid var(--line); margin:36px 0; }
ul,ol { padding-left:26px; }
li { margin:5px 0; font-size:15px; }
@media print { .page { max-width:none; padding:20mm 16mm; } h2 { page-break-after:avoid; } table { page-break-inside:avoid; } }
"""

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Behavioral Fingerprinting of Large Language Models — Tech Report</title>
<style>{css}</style></head>
<body><div class="page">
{body}
<footer style="margin-top:48px;color:#6e6e73;font-size:12px;border-top:1px solid #e5e5ea;padding-top:16px">
TransitTruth Project · Tech Report · Generated 2026-09-26 · Data &amp; code: github.com/dafahaha/transit-truth
</footer></div></body></html>"""

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print('HTML written:', OUT, len(html), 'bytes')
