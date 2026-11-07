"""Regression tests for the public leaderboard parser.

These lock the two failure modes that used to hit real submitters:

* an untouched issue-form hint (``<!-- 0-100 -->``) was parsed as the value,
  so an honest submission could land on the board as a red 0;
* the English markdown template used ``- Name:`` and ``- Overall score:``,
  which the parser did not read at all, so the submission vanished silently.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_ranking_data.py"


def _load():
    spec = importlib.util.spec_from_file_location("build_ranking_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _issue(body: str, number: int = 1) -> dict:
    return {
        "number": number,
        "html_url": f"https://github.com/dafahaha/transit-truth/issues/{number}",
        "user": {"login": "dafahaha"},
        "labels": [{"name": "audit-result"}],
        "title": "[audit-result] relay / model",
        "body": body,
    }


PLAIN = """审计结果
基本信息
中转站: wolfai
Base URL: https://wolfai.top/v1
模型: gpt-4o
审计模式: quick
审计时间: 2026-09-14T17:19:32.537Z
评分
信任分: 78/100
信任等级: medium
Token 对比
Token 差异率: -17.2%
延迟与协议
平均延迟: 1571ms
"""

FORM_FILLED = """## 基本信息

- **中转站名称**: demo-relay
- **Base URL**: https://demo.example/v1
- **模型名称**: gpt-4o
- **审计模式**: deep

## 审计结果

- **总分**: 55.7
- **信任等级**: high
- **Token 膨胀率**: N/A
- **平均延迟 (ms)**: 1856

## 贡献者信息
- **GitHub 用户名**: @dafahaha
"""

FORM_UNTOUCHED = """## 基本信息

- **中转站名称**: <!-- 例如 wolfai.top -->
- **总分**: <!-- 0-100，例如 55.7 -->
"""

ENGLISH = """## Relay

- **Name**: ao-relay
- **Base URL**: https://ao.example/v1
- **Model**: gpt-4o-mini
- **Tested at**: 2026-10-01

## Result

- **Overall score**: 85/100
- **Trust level**: high
"""


def test_plain_markdown_submission_is_parsed():
    brd = _load()
    entry = brd.parse_issue(_issue(PLAIN))
    assert entry is not None
    assert entry["relay"] == "wolfai"
    assert entry["overall_score"] == 78.0
    assert entry["trust_level"] == "medium"
    assert entry["audit_mode"] == "quick"
    # These two used to be null even though the body carried them.
    assert entry["token_inflation_pct"] == -17.2
    assert entry["avg_latency_ms"] == 1571.0


def test_form_comments_are_not_values():
    brd = _load()
    # Filled form: values win, trailing hints and the untouched N/A are ignored.
    entry = brd.parse_issue(_issue(FORM_FILLED))
    assert entry is not None
    assert entry["relay"] == "demo-relay"
    assert entry["overall_score"] == 55.7
    assert entry["contributor"] == "@dafahaha"
    assert entry["token_inflation_pct"] is None

    # Untouched form: every value is still a comment, so nothing is published.
    assert brd.parse_issue(_issue(FORM_UNTOUCHED)) is None


def test_english_template_is_parsed():
    brd = _load()
    entry = brd.parse_issue(_issue(ENGLISH, number=2))
    assert entry is not None
    assert entry["relay"] == "ao-relay"
    assert entry["model"] == "gpt-4o-mini"
    assert entry["overall_score"] == 85.0
    assert entry["trust_level"] == "high"


def test_score_must_be_in_range():
    brd = _load()
    assert brd.parse_issue(_issue("中转站: x\n信任分: 990")) is None
    assert brd.parse_issue(_issue("中转站: x\n信任分: -5")) is None
    assert brd.parse_issue(_issue("中转站: x\nBase URL: y")) is None


def test_markdown_parser_matches_python_parser_fields():
    """The browser fallback reads the same submission; its field list must not
    drift again (that divergence is what made CI and the page disagree)."""
    ranking = (REPO_ROOT / "docs" / "ranking.html").read_text(encoding="utf-8")
    for alias in ("中转站名称", "信任分", "总分", "模型名称", "Overall score", "Name"):
        assert alias in ranking, f"ranking.html fallback lost alias {alias}"
