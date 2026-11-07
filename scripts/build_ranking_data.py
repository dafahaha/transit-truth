#!/usr/bin/env python3
"""Build a static snapshot of the public leaderboard.

Why this exists: docs/ranking.html used to fetch api.github.com from the
visitor's browser. GitHub allows 60 unauthenticated requests per hour per IP,
so on shared/CGNAT networks the board silently degraded to a rate-limit error
exactly when a visitor arrived from a link. This script is run by a GitHub
Action (which has a token and therefore 5000 req/hour) and commits the parsed
result to docs/data/audit_results.json, so every visitor reads one static file
from the same Pages host and never touches the API.

Parsing mirrors docs/ranking.html: a submission is an issue (not a PR) that is
either labelled `audit-result` or titled `[audit-result] ...`, and its fields
may come from YAML front matter or from the plain-Markdown template.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "dafahaha/transit-truth"
API = f"https://api.github.com/repos/{REPO}/issues"
OUT = Path(__file__).resolve().parent.parent / "docs" / "data" / "audit_results.json"

TITLE_PREFIXES = ("[audit-result]", "[audit]")
LABEL = "audit-result"


def _get(url: str, token: str | None) -> object:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "transit-truth-ranking-builder")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch_issues(token: str | None, pages: int = 10) -> list[dict]:
    """Read every issue page, not just the newest 300.

    ``state=all`` is ordered by creation date, so a fixed page cap silently
    drops the oldest submissions from the board once the repo passes it.
    Ten pages is a deliberate ceiling: enough for a growing leaderboard,
    bounded enough that a runaway API response cannot hang the job.
    """
    items: list[dict] = []
    for page in range(1, pages + 1):
        batch = _get(f"{API}?state=all&per_page=100&page={page}", token)
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
    return items


def front_matter(body: str) -> dict[str, str] | None:
    m = re.match(r"^---\n([\s\S]*?)\n---", body)
    if not m:
        return None
    out: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
PLACEHOLDER_RE = re.compile(r"(?:e\.g\.|例如|example)", re.I)


def is_placeholder(raw: str) -> bool:
    """True when the value is still the template's example text.

    A submitter who does not delete `[e.g. Example Relay]` or
    `[0-100, e.g. 55.7]` must not be ranked: the literal is not a name, and
    the first number in that hint is 0.
    """
    text = raw.strip()
    if not text:
        return False
    if text.startswith("[") and text.endswith("]"):
        return True
    return bool(PLACEHOLDER_RE.search(text))


def clean_value(raw: str) -> str:
    """Strip the invisible HTML hints that issue forms leave in the body.

    GitHub renders `<!-- ... -->` as nothing, but it is still in the issue
    body. A submitter who leaves a hint untouched would otherwise have the
    hint parsed as the value: the score hint "0-100, e.g. 55.7" yields 0.
    An unclosed comment is the same failure with no closing tag, so it fails
    closed instead of leaking the digits inside the hint.
    """
    value = COMMENT_RE.sub("", raw)
    if "<!--" in value:
        return ""
    return value.replace("\u200b", "").strip().strip("`").strip()


def md_field(body: str, names: list[str]) -> str:
    """Read a field from either template style.

    Issuers write both `- **总分**: 78` (forms) and `信任分: 78/100` (hand
    written). Both must parse; the bold markers and the bullet are optional.
    Values still holding the template example are treated as missing.
    """
    for name in names:
        pattern = (
            rf"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?\s*{re.escape(name)}"
            rf"\s*(?:\*\*)?\s*[:：]\s*(.+)$"
        )
        m = re.search(pattern, body)
        if m:
            value = clean_value(m.group(1))
            if value and not is_placeholder(value):
                return value
    return ""


def parse_evidence(body: str) -> dict | None:
    """Keep the ``json`` block a submission is asked to paste.

    The snapshot used to store only scalars, so the headline numbers existed
    nowhere in the repository once the issue link died. The template already
    requires the block; archive it when it carries real content, and ignore
    the empty skeleton that ships in the template.
    """
    m = re.search(r"```json\s*([\s\S]*?)```", body, re.I)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("audit_id") and not data.get("checks"):
        return None
    return data


def parse_issue(issue: dict) -> dict | None:
    body = issue.get("body") or ""
    fm = front_matter(body)
    if fm is not None:
        # Front matter is parsed from arbitrary YAML, so it has no schema
        # enforcing a usable relay. The Markdown branch already refuses an
        # empty name; the front-matter branch must not fall back to
        # "unknown" or publish a template placeholder as a relay.
        relay_raw = str(fm.get("relay") or "")
        if not relay_raw or is_placeholder(relay_raw):
            return None
    if fm is None:
        relay = md_field(
            body, ["中转站名称", "中转站", "Relay", "Name", "Relay Service"]
        )
        if not relay:
            return None
        score_raw = md_field(
            body, ["信任分", "总分", "Trust score", "Overall score", "Score"]
        )
        fm = {
            "relay": relay,
            "base_url": md_field(body, ["Base URL"]),
            "model": md_field(body, ["模型名称", "模型", "Model", "Model audited"])
            or "unknown",
            "overall_score": score_raw,
            "trust_level": md_field(body, ["信任等级", "Trust level"]) or "unknown",
            "contributor": md_field(
                body, ["GitHub 用户名", "贡献者", "Contributor", "Submitted by"]
            ),
            "tested_at": md_field(body, ["审计时间", "Tested at", "Date"]),
            "audit_mode": md_field(body, ["审计模式", "Audit mode"]),
            "token_inflation_pct": md_field(
                body, ["Token 膨胀率", "Token 差异率", "Token inflation"]
            ),
            "avg_latency_ms": md_field(
                body,
                [
                    "平均延迟 (ms)",
                    "平均延迟",
                    "Average latency",
                    "Average latency (ms)",
                ],
            ),
        }

    def num(key: str) -> float | None:
        # Submissions write things like "78/100", "55.7", "1571ms" or
        # "-17.2%". Accept those exact shapes only: "about 78", "abc 42 def"
        # and template hints like "[0-100, e.g. 55.7]" must not produce a
        # number, or a half-filled form becomes a real 0 on the board.
        raw = clean_value(str(fm.get(key, "")))  # type: ignore[union-attr]
        if not raw or raw.upper() == "N/A" or is_placeholder(raw):
            return None
        m = re.fullmatch(
            r"\s*(-?[0-9]+(?:\.[0-9]+)?)(?:\s*/\s*100)?\s*(?:ms|%)?\s*", raw, re.I
        )
        return float(m.group(1)) if m else None

    score = num("overall_score")
    if score is None or not 0.0 <= score <= 100.0:
        # Fail closed: a submission without a usable 0-100 score must not
        # appear on the board as a real "0" — that would look like a verdict
        # we never made.
        return None

    labels = [str(l.get("name", "")).lower() for l in issue.get("labels") or []]
    return {
        "relay": str(fm.get("relay") or "unknown"),
        "base_url": str(fm.get("base_url") or ""),
        "model": str(fm.get("model") or "unknown"),
        "overall_score": score,
        "trust_level": str(fm.get("trust_level") or "unknown").lower(),
        "audit_mode": str(fm.get("audit_mode") or "").strip().lower() or "unknown",
        "token_inflation_pct": num("token_inflation_pct"),
        "avg_latency_ms": num("avg_latency_ms"),
        "contributor": str(fm.get("contributor") or ""),
        "submitter": str((issue.get("user") or {}).get("login") or ""),
        "tested_at": str(fm.get("tested_at") or issue.get("created_at") or ""),
        "verified": "verified" in labels,
        "issue_url": issue.get("html_url", ""),
        "issue_number": issue.get("number", 0),
        "evidence": parse_evidence(body),
    }


def is_audit_issue(issue: dict) -> bool:
    title = str(issue.get("title") or "").strip().lower()
    labels = [str(l.get("name", "")).lower() for l in issue.get("labels") or []]
    return LABEL in labels or title.startswith(TITLE_PREFIXES)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN")
    try:
        issues = fetch_issues(token)
    except urllib.error.HTTPError as exc:
        print(f"::error::GitHub API returned {exc.code}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"::error::network error: {exc}", file=sys.stderr)
        return 1

    entries: list[dict] = []
    for issue in issues:
        if issue.get("pull_request") or not is_audit_issue(issue):
            continue
        entry = parse_issue(issue)
        if entry is None:
            # Never drop a submission silently: a maintainer reading the run
            # log must see that this issue exists but could not be parsed.
            print(
                f"::warning::issue #{issue.get('number')} looks like an audit "
                "but has no usable relay name or 0-100 score; skipped",
                file=sys.stderr,
            )
            continue
        entries.append(entry)
    entries.sort(key=lambda e: str(e["tested_at"]), reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO,
        "count": len(entries),
        "entries": entries,
    }

    # `generated_at` used to change on every run, which made the workflow's
    # "Commit if changed" check dead code: every scheduled run produced a
    # timestamp-only commit. Keep the old file when the data itself is
    # unchanged, so `generated_at` means "when the data last changed" and
    # git history stays readable.
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = {}
        if (
            isinstance(previous, dict)
            and previous.get("entries") == entries
            and previous.get("count") == len(entries)
            and previous.get("repo") == REPO
        ):
            print(f"no change: {OUT} already has {len(entries)} entries")
            return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
