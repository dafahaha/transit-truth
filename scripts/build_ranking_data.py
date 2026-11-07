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


def fetch_issues(token: str | None, pages: int = 3) -> list[dict]:
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


def md_field(body: str, names: list[str]) -> str:
    for name in names:
        m = re.search(rf"\*\*\s*{re.escape(name)}\s*\*\*\s*[:：]\s*(.+)", body)
        if m:
            return m.group(1).strip()
    return ""


def parse_issue(issue: dict) -> dict | None:
    body = issue.get("body") or ""
    fm = front_matter(body)
    if fm is None:
        relay = md_field(body, ["中转站名称", "中转站", "Relay"])
        if not relay:
            return None
        score_raw = md_field(body, ["信任分", "总分", "Trust score"])
        fm = {
            "relay": relay,
            "base_url": md_field(body, ["Base URL"]),
            "model": md_field(body, ["模型名称", "模型", "Model"]) or "unknown",
            "overall_score": score_raw,
            "trust_level": md_field(body, ["信任等级", "Trust level"]) or "unknown",
            "contributor": md_field(body, ["GitHub 用户名", "贡献者", "Contributor"]),
            "tested_at": md_field(body, ["审计时间", "Tested at"]),
            "audit_mode": md_field(body, ["审计模式", "Audit mode"]),
        }

    def num(key: str) -> float | None:
        # Submissions write things like "78/100" or "55.7"; take the leading
        # number rather than feeding the whole string to float().
        raw = str(fm.get(key, "")).strip()  # type: ignore[union-attr]
        if not raw or raw.upper() == "N/A":
            return None
        m = re.search(r"-?\d+(?:\.\d+)?", raw)
        return float(m.group(0)) if m else None

    labels = [str(l.get("name", "")).lower() for l in issue.get("labels") or []]
    return {
        "relay": str(fm.get("relay") or "unknown"),
        "base_url": str(fm.get("base_url") or ""),
        "model": str(fm.get("model") or "unknown"),
        "overall_score": num("overall_score") or 0.0,
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

    entries = [
        e
        for e in (
            parse_issue(i)
            for i in issues
            if is_audit_issue(i) and not i.get("pull_request")
        )
        if e
    ]
    entries.sort(key=lambda e: str(e["tested_at"]), reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": REPO,
        "count": len(entries),
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
