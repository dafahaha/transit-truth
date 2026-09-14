"""Tests for HTML report generator."""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import (
    AuditResult,
    AuditStatus,
    CheckResult,
    CheckType,
    TokenComparison,
    FingerprintResult,
)
from app.utils.report_generator import generate_html_report, _trust_color, _trust_label


class TestReportGenerator:
    def _make_sample_result(self) -> AuditResult:
        return AuditResult(
            audit_id="test123",
            status=AuditStatus.COMPLETED,
            model="gpt-4o",
            base_url="https://api.example.com/v1",
            started_at=datetime(2026, 9, 14, 12, 0, 0),
            completed_at=datetime(2026, 9, 14, 12, 0, 30),
            overall_score=85.5,
            trust_level="high",
            checks=[
                CheckResult(
                    check_type=CheckType.TOKEN_COUNT,
                    name="Token Count Verification",
                    passed=True,
                    score=90.0,
                    details="No significant inflation detected",
                    evidence={"prompt_tokens": 1000, "completion_tokens": 500},
                    duration_ms=1500.0,
                ),
                CheckResult(
                    check_type=CheckType.MODEL_FINGERPRINT,
                    name="Model Fingerprint Verification",
                    passed=False,
                    score=60.0,
                    details="Minor anomalies detected in tokenizer signature",
                    evidence={"anomaly_score": 0.3},
                    duration_ms=5000.0,
                ),
            ],
            token_comparison=TokenComparison(
                prompt_tokens_reported=1050,
                prompt_tokens_expected=1000,
                completion_tokens_reported=500,
                completion_tokens_expected=500,
                total_tokens_reported=1550,
                prompt_inflation_pct=5.0,
                completion_inflation_pct=0.0,
                suspicious=False,
            ),
            fingerprint=FingerprintResult(
                claimed_model="gpt-4o",
                detected_family="openai-gpt4o",
                family_match=True,
                confidence=0.85,
                suspicious=False,
            ),
            summary="Test audit summary",
            recommendations=["Recommendation 1", "Recommendation 2"],
        )

    def test_generate_html_returns_string(self):
        result = self._make_sample_result()
        html = generate_html_report(result)
        assert isinstance(html, str)
        assert len(html) > 1000

    def test_html_contains_key_elements(self):
        result = self._make_sample_result()
        html = generate_html_report(result)
        assert "<!DOCTYPE html>" in html
        assert "TransitTruth" in html
        assert "gpt-4o" in html
        assert "85.5" in html or "86" in html  # score
        assert "高信任度" in html  # trust level label

    def test_html_contains_check_details(self):
        result = self._make_sample_result()
        html = generate_html_report(result)
        assert "Token Count Verification" in html
        assert "Model Fingerprint Verification" in html

    def test_html_contains_recommendations(self):
        result = self._make_sample_result()
        html = generate_html_report(result)
        assert "Recommendation 1" in html
        assert "Recommendation 2" in html

    def test_html_contains_token_comparison(self):
        result = self._make_sample_result()
        html = generate_html_report(result)
        assert "1050" in html  # reported prompt tokens
        assert "5.0%" in html or "5.0" in html  # inflation

    def test_trust_color_mapping(self):
        assert _trust_color("high") == "#16a34a"
        assert _trust_color("medium") == "#d97706"
        assert _trust_color("low") == "#dc2626"
        assert _trust_color("critical") == "#991b1b"
        assert _trust_color("unknown") == "#64748b"

    def test_trust_label_mapping(self):
        assert _trust_label("high") == "高信任度"
        assert _trust_label("medium") == "中等信任"
        assert _trust_label("low") == "低信任度"
        assert _trust_label("critical") == "危险"

    def test_empty_checks(self):
        result = self._make_sample_result()
        result.checks = []
        html = generate_html_report(result)
        assert isinstance(html, str)
        assert "检测项目详情" in html

    def test_no_token_comparison(self):
        result = self._make_sample_result()
        result.token_comparison = None
        html = generate_html_report(result)
        assert isinstance(html, str)
        assert "Token 计数对比" not in html
