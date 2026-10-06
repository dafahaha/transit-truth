"""Tests for detect, ranking aggregation, and badge generation.

Converted from the old print-script `backend/test_new_features.py` into
real pytest cases so they are collected and run in CI.
"""
from app.core.detect import detect_base_url, suggest_relays, KNOWN_RELAYS
from app.utils.ranking_aggregator import (
    AuditEntry,
    aggregate_audits,
    detect_anomalies,
    generate_ranking_json,
    get_top_contributors,
)
from app.utils.badge_generator import (
    generate_contributor_badge,
    generate_stat_badge,
    generate_profile_readme_section,
)


class TestDetect:
    def test_known_relays_nonempty(self):
        assert len(KNOWN_RELAYS) > 5

    def test_detect_base_url_returns_string(self):
        result = detect_base_url("sk-test123")
        assert result is None or isinstance(result, str)

    def test_suggest_relays_returns_list(self):
        suggestions = suggest_relays("sk-test123")
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        for s in suggestions:
            assert "name" in s and "base_url" in s and "confidence" in s


class TestRankingAggregator:
    def test_aggregate_and_ranking_json(self):
        entries = [
            AuditEntry(relay="r1", model="gpt-4o-mini", base_url="https://r1/v1",
                       overall_score=55.7, trust_level="critical",
                       token_inflation_pct=76.1, contributor="alice"),
            AuditEntry(relay="r1", model="gpt-4o", base_url="https://r1/v1",
                       overall_score=57.5, trust_level="critical",
                       token_inflation_pct=76.1, contributor="alice"),
        ]
        aggregated = aggregate_audits(entries)
        ranking = generate_ranking_json(aggregated)
        assert ranking["total_audits"] == 2
        assert ranking["total_relays"] >= 1

    def test_top_contributors(self):
        entries = [
            AuditEntry(relay="r1", model="m1", base_url="https://r1/v1",
                       overall_score=80.0, trust_level="high",
                       token_inflation_pct=0.0, contributor="alice"),
            AuditEntry(relay="r2", model="m1", base_url="https://r2/v1",
                       overall_score=70.0, trust_level="medium",
                       token_inflation_pct=5.0, contributor="bob"),
        ]
        top = get_top_contributors(entries)
        assert len(top) >= 1
        assert "contributor" in top[0]

    def test_detect_anomalies_group_of_two_no_nameerror(self):
        # Regression: Counter was used at ranking_aggregator.py:121 but never
        # imported, so any group with >=2 entries crashed with NameError.
        entries = [
            AuditEntry(relay="r1", model="m1", base_url="https://r1/v1",
                       overall_score=50.0, trust_level="medium"),
            AuditEntry(relay="r1", model="m1", base_url="https://r1/v1",
                       overall_score=55.0, trust_level="medium"),
        ]
        anomalies = detect_anomalies(entries)
        assert isinstance(anomalies, list)
        # aggregate_audits also calls detect_anomalies internally per group.
        aggregated = aggregate_audits(entries)
        assert aggregated[0].audit_count == 2


class TestBadgeGenerator:
    def test_contributor_badge_nonempty(self):
        badge = generate_contributor_badge("alice", 5, 2)
        assert len(badge) > 0

    def test_stat_badge_nonempty(self):
        stat = generate_stat_badge("Audits", "12", "#16a34a")
        assert len(stat) > 0

    def test_profile_readme_section_nonempty(self):
        section = generate_profile_readme_section("alice", 5, 2, 1, 56.6)
        assert len(section) > 0
