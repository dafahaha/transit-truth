"""Tests for data models."""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import (
    AuditRequest,
    AuditResult,
    AuditStatus,
    AuditMode,
    CheckResult,
    CheckType,
    TokenComparison,
    FingerprintResult,
    RankingEntry,
)


class TestAuditRequest:
    def test_valid_request(self):
        req = AuditRequest(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
        )
        assert req.api_key == "sk-test"
        assert req.mode == AuditMode.DEEP  # default mode
        assert req.probe_count is None  # determined by mode at runtime
        assert req.run_token_check is True
        assert req.run_fingerprint is True

    def test_quick_mode(self):
        req = AuditRequest(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
            mode="quick",
        )
        assert req.mode == AuditMode.QUICK

    def test_explicit_probe_count(self):
        req = AuditRequest(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
            probe_count=5,
        )
        assert req.probe_count == 5

    def test_invalid_probe_count(self):
        import pytest
        with pytest.raises(Exception):
            AuditRequest(
                api_key="sk-test",
                base_url="https://api.example.com/v1",
                model="gpt-4o",
                probe_count=0,
            )

    def test_optional_official_key(self):
        req = AuditRequest(
            api_key="sk-test",
            base_url="https://api.example.com/v1",
            model="gpt-4o",
            official_api_key=None,
        )
        assert req.official_api_key is None


class TestAuditResult:
    def test_default_values(self):
        result = AuditResult(
            audit_id="test123",
            status=AuditStatus.PENDING,
            model="gpt-4o",
            base_url="https://api.example.com/v1",
            started_at=datetime.now(),
        )
        assert result.overall_score == 0
        assert result.trust_level == "unknown"
        assert result.checks == []
        assert result.recommendations == []

    def test_score_bounds(self):
        import pytest
        with pytest.raises(Exception):
            AuditResult(
                audit_id="test",
                status=AuditStatus.COMPLETED,
                model="gpt-4o",
                base_url="https://example.com",
                started_at=datetime.now(),
                overall_score=150,  # invalid
            )


class TestCheckResult:
    def test_valid_check(self):
        check = CheckResult(
            check_type=CheckType.TOKEN_COUNT,
            name="Test Check",
            passed=True,
            score=95.5,
            details="All good",
        )
        assert check.passed is True
        assert 0 <= check.score <= 100

    def test_check_types(self):
        assert CheckType.TOKEN_COUNT.value == "token_count"
        assert CheckType.MODEL_FINGERPRINT.value == "model_fingerprint"
        assert CheckType.RESPONSE_LATENCY.value == "response_latency"
        assert CheckType.PROTOCOL_COMPLIANCE.value == "protocol_compliance"


class TestTokenComparison:
    def test_suspicious_detection(self):
        tc = TokenComparison(
            prompt_tokens_reported=1500,
            prompt_tokens_expected=1000,
            completion_tokens_reported=500,
            completion_tokens_expected=500,
            total_tokens_reported=2000,
            prompt_inflation_pct=50.0,
            suspicious=True,
        )
        assert tc.suspicious is True
        assert tc.prompt_inflation_pct == 50.0


class TestFingerprintResult:
    def test_family_match(self):
        fp = FingerprintResult(
            claimed_model="gpt-4o",
            detected_family="openai-gpt4o",
            family_match=True,
            confidence=0.9,
            suspicious=False,
        )
        assert fp.family_match is True
        assert fp.confidence == 0.9
