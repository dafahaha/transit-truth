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


def test_untouched_english_template_is_never_published():
    """A submitter who leaves the examples in place must not create a row.

    The old parser read ``[0-100, e.g. 55.7]`` by taking the first number in
    the string and published relay="[e.g. Example Relay]" with score 0.0.
    """
    brd = _load()
    template = (REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "audit_result.md").read_text(
        encoding="utf-8"
    )
    assert brd.parse_issue(_issue(template)) is None


def test_placeholder_values_are_missing_values():
    brd = _load()
    # Bracket examples are template text, not a relay name or a score.
    assert brd.parse_issue(_issue("中转站: [e.g. Example Relay]\n总分: 78")) is None
    assert brd.parse_issue(_issue("中转站: x\n总分: [0-100, e.g. 55.7]")) is None
    # "N/A" stays a legitimate empty value for optional fields.
    entry = brd.parse_issue(_issue("中转站: x\n总分: 78\nToken 膨胀率: N/A"))
    assert entry is not None and entry["token_inflation_pct"] is None


def test_numbers_are_whole_strings_not_first_digits():
    brd = _load()
    assert brd.parse_issue(_issue("中转站: x\n总分: about 78")) is None
    assert brd.parse_issue(_issue("中转站: x\n总分: 78 out of 100")) is None
    # The documented written forms still work, including units.
    entry = brd.parse_issue(
        _issue("中转站: x\n总分: 78/100\nToken 差异率: -17.2%\n平均延迟: 1571ms")
    )
    assert entry is not None
    assert entry["overall_score"] == 78.0
    assert entry["token_inflation_pct"] == -17.2
    assert entry["avg_latency_ms"] == 1571.0


def test_unclosed_comment_fails_closed():
    brd = _load()
    assert brd.parse_issue(_issue("中转站: x\n总分: <!-- 0-100")) is None


def test_field_names_are_case_insensitive():
    brd = _load()
    entry = brd.parse_issue(_issue("- **name**: LowRelay\n- **overall score**: 60"))
    assert entry is not None
    assert entry["relay"] == "LowRelay"
    assert entry["overall_score"] == 60.0


def test_evidence_block_is_archived_not_dropped():
    """The snapshot must carry the raw numbers, not just the scores.

    Otherwise -17.2% exists only in the issue, and the repository cannot
    reproduce it after the issue link dies.
    """
    brd = _load()
    body = PLAIN + (
        '\n```json\n{"audit_id": "a1", "checks": [{"name": "tokenizer", "score": 90}]}\n```\n'
    )
    entry = brd.parse_issue(_issue(body))
    assert entry is not None
    assert entry["evidence"]["audit_id"] == "a1"
    assert entry["evidence"]["checks"][0]["score"] == 90


def test_score_gap_against_evidence_is_disclosed():
    """A submitted score whose archived checks average to a different number
    must carry the discrepancy, not look self-consistent on the page."""
    brd = _load()
    body = PLAIN + (
        '\n```json\n{"checks": [{"score": 90}, {"score": 85}, {"score": 55}]}\n```\n'
    )
    entry = brd.parse_issue(_issue(body))
    assert entry is not None
    assert entry["overall_score"] == 78.0
    assert entry["score_checks_mean"] == 76.7
    assert "历史权重未留档" in entry["score_note"]


def test_no_score_note_when_evidence_matches():
    brd = _load()
    body = PLAIN + '\n```json\n{"checks": [{"score": 78}]}\n```\n'
    entry = brd.parse_issue(_issue(body))
    assert entry is not None
    assert "score_note" not in entry


def test_template_evidence_skeleton_is_not_archived():
    """An untouched template carries an empty JSON skeleton; it is not data."""
    brd = _load()
    template = (
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "audit_result.yml"
    ).read_text(encoding="utf-8")
    assert brd.parse_issue(_issue(template)) is None
    entry = brd.parse_issue(_issue(PLAIN))
    assert entry is not None and entry["evidence"] is None


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


def test_fetch_issues_reads_every_page(monkeypatch):
    mod = _load()
    calls = []

    def fake_get(url, token):
        calls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        if page == 1:
            return [{"number": i} for i in range(100)]
        if page == 2:
            return [{"number": 100}]
        raise AssertionError(f"should stop after a short page, saw {page}")

    monkeypatch.setattr(mod, "_get", fake_get)
    assert len(mod.fetch_issues(None)) == 101
    assert len(calls) == 2


def test_main_does_not_rewrite_when_entries_are_unchanged(monkeypatch, tmp_path):
    """A scheduled run with no new submission must not create a timestamp-only
    commit. The file keeps the generated_at of the last real data change."""
    import json

    mod = _load()
    out = tmp_path / "audit_results.json"
    monkeypatch.setattr(mod, "OUT", out)
    monkeypatch.setattr(mod, "fetch_issues", lambda token: [_issue(PLAIN)])

    assert mod.main() == 0
    first = json.loads(out.read_text(encoding="utf-8"))

    assert mod.main() == 0
    second = json.loads(out.read_text(encoding="utf-8"))
    assert second == first
