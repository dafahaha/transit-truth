"""Cross-check the CI parser and the browser fallback on the same bodies.

The leaderboard has two parsers: ``scripts/build_ranking_data.py`` writes the
snapshot, ``docs/ranking.html`` parses issues live when the snapshot is
missing. They drifted before (the page accepted ``overall_score: 990`` and
turned a missing score into 0), which made the board disagree with itself.
This test feeds identical bodies to both and requires identical fields.

Skipped when node is unavailable; CI's ubuntu runner ships node.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_ranking_data.py"
RANKING = REPO_ROOT / "docs" / "ranking.html"

CASES = [
    "中转站: wolfai\n模型: gpt-4o\n信任分: 78/100\nToken 差异率: -17.2%\n平均延迟: 1571ms",
    "## 基本信息\n\n- **中转站名称**: demo-relay\n- **总分**: 55.7\n- **审计模式**: deep",
    "## Relay\n\n- **Name**: ao-relay\n- **Overall score**: 85/100\n- **Model**: gpt-4o-mini\n- **Audit mode**: quick",
    "中转站: x\n总分: 990",
    "中转站: x\n总分: -5",
    "中转站: x\n总分: about 78",
    "中转站: x\n总分: <!-- 0-100",
    "中转站: x\n总分: 0",
    "中转站: x\n总分: 100",
    "- **name**: LowRelay\n- **overall score**: 60",
    "中转站: x\n总分: N/A",
    "中转站: x\n总分: 78\nToken 膨胀率: N/A",
    "---\nrelay: front\noverall_score: 60\n---\n",
    "---\nrelay: front\noverall_score: 990\n---\n",
    "---\nrelay: front\n---\n",
    # Unicode digits are digits to Python's regex/int() and not to JavaScript;
    # accepting them on one side only makes the page disagree with the snapshot.
    "中转站: x\n总分: ７８",
    "中转站: x\n总分: 78abc",
    "中转站: x\n总分: +78",
    "中转站: x\n总分: 0078",
    "中转站: x\n总分: 78 / 100",
    "中转站: x\n总分: `78`",
    "---\nrelay: front\noverall_score: 78abc\n---\n",
    "---\nrelay: front\noverall_score: 78.5extra\n---\n",
    "---\nrelay: front\noverall_score: 78 %\n---\n",
    "---\nrelay: front\noverall_score: 78 / 100\n---\n",
    "---\noverall_score: 78\n---\n",
    "---\nrelay: front\noverall_score: 78\nsubmitter: someone-else\n---\n",
    "---\nrelay: [e.g. Example Relay]\noverall_score: 78\n---\n",
    # Both aliases present: label priority must be identical on both sides.
    "中转站: x\n总分: 78\n平均延迟: 1500ms\nAverage latency (ms): 2000",
    # Evidence block is archived by both sides; an empty skeleton is not.
    '中转站: x\n总分: 78\n```json\n{"checks": [{"score": 78}]}\n```',
]

FIELDS = (
    "relay",
    "model",
    "overall_score",
    "token_inflation_pct",
    "avg_latency_ms",
    "audit_mode",
    "base_url",
    "trust_level",
    "contributor",
    "tested_at",
    "submitter",
    "verified",
    "issue_number",
    "evidence",
)


def _load_python():
    spec = importlib.util.spec_from_file_location("build_ranking_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _issue(body: str) -> dict:
    return {
        "number": 1,
        "html_url": "https://github.com/dafahaha/transit-truth/issues/1",
        "user": {"login": "dafahaha"},
        "labels": [{"name": "audit-result"}],
        "title": "[audit-result] relay / model",
        "body": body,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _normalise(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    out = {}
    for field in FIELDS:
        value = entry.get(field)
        if field == "audit_mode":
            value = value or ""
        out[field] = value
    return out


def _js_results() -> list[dict | None]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    html = RANKING.read_text(encoding="utf-8")
    start = html.index("/* PARSER-BLOCK-START */")
    end = html.index("/* PARSER-BLOCK-END */")
    block = html[start:end]
    script = (
        "const fs = require('fs');\n"
        "const vm = require('vm');\n"
        "const block = " + json.dumps(block) + ";\n"
        "const bodies = " + json.dumps(CASES) + ";\n"
        "const sandbox = {};\n"
        "vm.createContext(sandbox);\n"
        "const runner = block + '\\nglobalThis.__parseIssue = parseIssue;';\n"
        "vm.runInContext(runner, sandbox);\n"
        "const out = bodies.map(b => {\n"
        "  const issue = {body: b, labels: [], user: {login: 'dafahaha'},\n"
        "    html_url: 'https://github.com/dafahaha/transit-truth/issues/1',\n"
        "    number: 1, title: '[audit-result] relay / model',\n"
        "    created_at: '2026-01-01T00:00:00Z'};\n"
        "  const e = sandbox.__parseIssue(issue);\n"
        "  if (!e) return null;\n"
        "  const r = {relay: e.relay, model: e.model, overall_score: e.overall_score,\n"
        "    token_inflation_pct: e.token_inflation_pct, avg_latency_ms: e.avg_latency_ms,\n"
        "    audit_mode: e.audit_mode || '', base_url: e.base_url,\n"
        "    trust_level: e.trust_level, contributor: e.contributor,\n"
        "    tested_at: e.tested_at, submitter: e.submitter, verified: e.verified,\n"
        "    issue_number: e.issue_number, evidence: e.evidence};\n"
        "  return r;\n"
        "});\n"
        "console.log(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_python_parser_agrees_with_browser_fallback_on_every_case():
    brd = _load_python()
    py = [_normalise(brd.parse_issue(_issue(body))) for body in CASES]
    js = _js_results()
    assert len(py) == len(js)
    # One hand-written expectation, so both parsers cannot drift together
    # and still pass by agreeing with each other.
    expected = {
        "relay": "wolfai",
        "model": "gpt-4o",
        "overall_score": 78.0,
        "token_inflation_pct": -17.2,
        "avg_latency_ms": 1571.0,
        "audit_mode": "unknown",
        "base_url": "",
        "trust_level": "unknown",
        "contributor": "",
        "tested_at": "2026-01-01T00:00:00Z",
        "submitter": "dafahaha",
        "verified": False,
        "issue_number": 1,
        "evidence": None,
    }
    assert py[0] == expected, py[0]
    assert js[0] == expected, js[0]
    for body, left, right in zip(CASES, py, js):
        if left is None or right is None:
            assert left is None and right is None, (body, left, right)
            continue
        for field in FIELDS:
            if field in ("overall_score", "token_inflation_pct", "avg_latency_ms"):
                if left[field] is None or right[field] is None:
                    assert left[field] is None and right[field] is None, (
                        body,
                        field,
                        left,
                        right,
                    )
                else:
                    assert abs(float(left[field]) - float(right[field])) < 1e-9, (
                        body,
                        field,
                        left,
                        right,
                    )
            else:
                assert left[field] == right[field], (body, field, left, right)
