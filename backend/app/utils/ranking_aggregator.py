"""Ranking data validation and aggregation.

Processes audit results from GitHub Issues, calculates medians,
detects anomalies, and determines verified/preliminary status.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuditEntry:
    """A single audit result."""
    relay: str
    model: str
    base_url: str
    overall_score: float
    trust_level: str
    token_inflation_pct: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    contributor: str = ""
    tested_at: str = ""
    issue_number: int = 0
    issue_url: str = ""


@dataclass
class AggregatedEntry:
    """Aggregated result for a relay+model combination."""
    relay: str
    model: str
    base_url: str
    audit_count: int = 0
    median_score: float = 0
    median_token_inflation: Optional[float] = None
    median_latency: Optional[float] = None
    verified: bool = False
    contributors: list[str] = field(default_factory=list)
    last_audited: str = ""
    entries: list[AuditEntry] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


def parse_frontmatter(body: str) -> dict:
    """Parse YAML frontmatter from issue body."""
    match = body.split("---")
    if len(match) < 3:
        return {}
    fm = {}
    for line in match[1].strip().split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip()
    return fm


def parse_audit_entry(issue: dict) -> Optional[AuditEntry]:
    """Parse a GitHub issue into an AuditEntry."""
    body = issue.get("body", "")
    fm = parse_frontmatter(body)

    if not fm.get("relay") or not fm.get("model"):
        return None

    try:
        score = float(fm.get("overall_score", 0))
    except (ValueError, TypeError):
        score = 0

    token_inflation = None
    if fm.get("token_inflation_pct") and fm["token_inflation_pct"] != "N/A":
        try:
            token_inflation = float(fm["token_inflation_pct"])
        except (ValueError, TypeError):
            pass

    avg_latency = None
    if fm.get("avg_latency_ms") and fm["avg_latency_ms"] != "N/A":
        try:
            avg_latency = float(fm["avg_latency_ms"])
        except (ValueError, TypeError):
            pass

    return AuditEntry(
        relay=fm.get("relay", "unknown"),
        model=fm.get("model", "unknown"),
        base_url=fm.get("base_url", ""),
        overall_score=score,
        trust_level=fm.get("trust_level", "unknown"),
        token_inflation_pct=token_inflation,
        avg_latency_ms=avg_latency,
        contributor=fm.get("contributor", ""),
        tested_at=fm.get("tested_at", ""),
        issue_number=issue.get("number", 0),
        issue_url=issue.get("html_url", ""),
    )


def detect_anomalies(entries: list[AuditEntry]) -> list[str]:
    """Detect anomalous audit results.

    Anomaly detection rules:
    1. Score deviation > 30 points from median
    2. Token inflation > 200% or < 0%
    3. Latency > 30000ms (30 seconds) or < 50ms (suspiciously fast, maybe cached)
    4. Same exact score across multiple audits (possible cached/fake data)
    5. Score = 0 or 100 exactly (suspicious)
    """
    anomalies = []

    if len(entries) < 2:
        return anomalies

    scores = [e.overall_score for e in entries]
    median_score = statistics.median(scores)

    # Check for exact duplicate scores (possible cached data)
    score_counts = Counter(scores)
    duplicate_scores = [s for s, c in score_counts.items() if c >= 3]
    if duplicate_scores:
        anomalies.append(
            f"Suspicious: {len(duplicate_scores)} score(s) appear 3+ times "
            f"(possible cached/fake data): {duplicate_scores}"
        )

    for e in entries:
        # Score deviation > 30 points from median
        if abs(e.overall_score - median_score) > 30:
            anomalies.append(
                f"Issue #{e.issue_number}: score {e.overall_score} deviates "
                f"{abs(e.overall_score - median_score):.1f} from median {median_score:.1f}"
            )

        # Score = 0 or 100 exactly (suspicious)
        if e.overall_score == 0 or e.overall_score == 100:
            anomalies.append(
                f"Issue #{e.issue_number}: suspicious exact score {e.overall_score}"
            )

        # Token inflation > 200% or < 0%
        if e.token_inflation_pct is not None:
            if e.token_inflation_pct > 200:
                anomalies.append(
                    f"Issue #{e.issue_number}: token inflation {e.token_inflation_pct:.1f}% > 200%"
                )
            elif e.token_inflation_pct < 0:
                anomalies.append(
                    f"Issue #{e.issue_number}: negative token inflation {e.token_inflation_pct:.1f}%"
                )

        # Latency > 30000ms or < 50ms
        if e.avg_latency_ms is not None:
            if e.avg_latency_ms > 30000:
                anomalies.append(
                    f"Issue #{e.issue_number}: very high latency {e.avg_latency_ms:.0f}ms > 30s"
                )
            elif e.avg_latency_ms < 50:
                anomalies.append(
                    f"Issue #{e.issue_number}: suspiciously low latency {e.avg_latency_ms:.0f}ms < 50ms (possible cached response)"
                )

    return anomalies


def aggregate_audits(entries: list[AuditEntry]) -> list[AggregatedEntry]:
    """Aggregate audit results by relay+model."""
    groups: dict[tuple[str, str], list[AuditEntry]] = {}

    for entry in entries:
        key = (entry.relay, entry.model)
        if key not in groups:
            groups[key] = []
        groups[key].append(entry)

    aggregated = []
    for (relay, model), group_entries in groups.items():
        scores = [e.overall_score for e in group_entries]
        token_inflations = [e.token_inflation_pct for e in group_entries if e.token_inflation_pct is not None]
        latencies = [e.avg_latency_ms for e in group_entries if e.avg_latency_ms is not None]
        contributors = list(set(e.contributor for e in group_entries if e.contributor))
        last_audited = max(e.tested_at for e in group_entries if e.tested_at) if any(e.tested_at for e in group_entries) else ""

        agg = AggregatedEntry(
            relay=relay,
            model=model,
            base_url=group_entries[0].base_url,
            audit_count=len(group_entries),
            median_score=statistics.median(scores),
            median_token_inflation=statistics.median(token_inflations) if token_inflations else None,
            median_latency=statistics.median(latencies) if latencies else None,
            verified=len(group_entries) >= 3,
            contributors=contributors,
            last_audited=last_audited,
            entries=group_entries,
            anomalies=detect_anomalies(group_entries),
        )
        aggregated.append(agg)

    # Sort by median score descending
    aggregated.sort(key=lambda x: x.median_score, reverse=True)
    return aggregated


def generate_ranking_json(aggregated: list[AggregatedEntry]) -> dict:
    """Generate ranking data in JSON format."""
    return {
        "generated_at": "",
        "total_audits": sum(a.audit_count for a in aggregated),
        "total_relays": len(set(a.relay for a in aggregated)),
        "verified_count": sum(1 for a in aggregated if a.verified),
        "rankings": [
            {
                "relay": a.relay,
                "model": a.model,
                "base_url": a.base_url,
                "audit_count": a.audit_count,
                "median_score": round(a.median_score, 1),
                "median_token_inflation": round(a.median_token_inflation, 1) if a.median_token_inflation is not None else None,
                "median_latency_ms": round(a.median_latency, 1) if a.median_latency is not None else None,
                "verified": a.verified,
                "contributors": a.contributors,
                "last_audited": a.last_audited,
                "anomalies": a.anomalies,
            }
            for a in aggregated
        ],
    }


def get_top_contributors(entries: list[AuditEntry], top_n: int = 10) -> list[dict]:
    """Get top contributors by audit count and reputation."""
    contributor_data: dict[str, dict] = {}

    for e in entries:
        if not e.contributor or e.contributor == "匿名":
            continue
        if e.contributor not in contributor_data:
            contributor_data[e.contributor] = {
                "audit_count": 0,
                "verified_count": 0,
                "relays": set(),
                "anomalies": 0,
            }
        contributor_data[e.contributor]["audit_count"] += 1
        if e.contributor and e.contributor.startswith("@"):
            contributor_data[e.contributor]["verified_count"] += 1
        if e.relay:
            contributor_data[e.contributor]["relays"].add(e.relay)

    # Calculate reputation score
    contributors = []
    for name, data in contributor_data.items():
        reputation = calculate_reputation(
            audit_count=data["audit_count"],
            verified_count=data["verified_count"],
            unique_relays=len(data["relays"]),
        )
        contributors.append({
            "contributor": name,
            "audit_count": data["audit_count"],
            "verified_count": data["verified_count"],
            "unique_relays": len(data["relays"]),
            "reputation_score": reputation,
            "reputation_level": get_reputation_level(reputation),
        })

    # Sort by reputation score (then by audit count)
    contributors.sort(key=lambda x: (x["reputation_score"], x["audit_count"]), reverse=True)

    return [
        {"rank": i + 1, **c}
        for i, c in enumerate(contributors[:top_n])
    ]


def calculate_reputation(audit_count: int, verified_count: int = 0,
                         unique_relays: int = 0, anomaly_count: int = 0) -> float:
    """Calculate contributor reputation score (0-100).

    Reputation factors:
    - Audit count: 40% (more audits = higher reputation)
    - Verified count: 20% (audits that became verified = higher quality)
    - Unique relays: 20% (auditing different relays = more diverse)
    - Anomaly penalty: -20% (anomalous submissions reduce reputation)
    """
    # Audit count score (capped at 20 audits for full marks)
    count_score = min(audit_count / 20, 1.0) * 40

    # Verified count score (capped at 10 verified for full marks)
    verified_score = min(verified_count / 10, 1.0) * 20

    # Unique relays score (capped at 5 relays for full marks)
    relay_score = min(unique_relays / 5, 1.0) * 20

    # Anomaly penalty
    anomaly_penalty = min(anomaly_count * 5, 20)

    reputation = count_score + verified_score + relay_score - anomaly_penalty
    return max(0, min(100, round(reputation, 1)))


def get_reputation_level(reputation: float) -> str:
    """Get reputation level label."""
    if reputation >= 80:
        return "Trusted"
    elif reputation >= 60:
        return "Established"
    elif reputation >= 40:
        return "Regular"
    elif reputation >= 20:
        return "New"
    else:
        return "Unknown"


def aggregate_with_reputation(entries: list[AuditEntry],
                               contributor_reputations: dict[str, float] | None = None) -> list[AggregatedEntry]:
    """Aggregate audits with contributor reputation weighting.

    Entries from higher-reputation contributors get higher weight
    in the median calculation. This helps mitigate low-quality or
    malicious submissions.
    """
    if contributor_reputations is None:
        # Calculate reputations from entries
        top = get_top_contributors(entries, top_n=100)
        contributor_reputations = {c["contributor"]: c["reputation_score"] for c in top}

    # Weight entries by reputation (normalized to 0.5-1.5 range)
    weighted_entries = []
    for e in entries:
        reputation = contributor_reputations.get(e.contributor, 50.0)
        weight = 0.5 + (reputation / 100)  # 0.5 (new) to 1.5 (trusted)
        # Repeat entry by weight factor (integer part) for median calculation
        repeat_count = max(1, int(round(weight)))
        for _ in range(repeat_count):
            weighted_entries.append(e)

    return aggregate_audits(weighted_entries)


if __name__ == "__main__":
    # Example usage with mock data
    mock_entries = [
        AuditEntry(relay="wolfai.top", model="gpt-4o-mini", base_url="https://wolfai.top/v1",
                   overall_score=55.7, trust_level="critical", token_inflation_pct=76.1,
                   avg_latency_ms=1856, contributor="@dafahaha", tested_at="2026-09-14"),
        AuditEntry(relay="wolfai.top", model="gpt-4o", base_url="https://wolfai.top/v1",
                   overall_score=57.5, trust_level="critical", token_inflation_pct=76.1,
                   avg_latency_ms=1161, contributor="@dafahaha", tested_at="2026-09-14"),
    ]

    aggregated = aggregate_audits(mock_entries)
    ranking = generate_ranking_json(aggregated)
    contributors = get_top_contributors(mock_entries)

    print("=== Ranking ===")
    print(json.dumps(ranking, indent=2, ensure_ascii=False))
    print("\n=== Top Contributors ===")
    print(json.dumps(contributors, indent=2, ensure_ascii=False))
