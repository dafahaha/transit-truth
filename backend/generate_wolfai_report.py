"""Generate comprehensive audit comparison report for wolfai.top."""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from app.models import (
    AuditResult, AuditStatus, CheckResult, CheckType,
    TokenComparison, FingerprintResult,
)
from app.utils.report_generator import generate_html_report

# Audit results from real testing
results = [
    {
        "audit_id": "wolfai-default-gpt4omini",
        "model": "gpt-4o-mini",
        "group": "default",
        "key_name": "transit-truth-test",
        "overall_score": 55.7,
        "trust_level": "critical",
        "duration_s": 58.1,
        "token": {
            "prompt_reported": 81,
            "prompt_expected": 46,
            "completion_reported": 440,
            "total_reported": 521,
            "inflation_pct": 76.09,
            "suspicious": True,
            "score": 0,
        },
        "fingerprint": {
            "claimed": "gpt-4o-mini",
            "detected_family": "openai-gpt4",
            "family_match": True,
            "confidence": 0.6,
            "suspicious": True,
            "score": 70,
        },
        "latency": {
            "avg_ms": 1856.1,
            "p50_ms": 1718.7,
            "p95_ms": 2113.6,
            "error_rate": 0.0,
            "score": 81.4,
        },
        "protocol": {
            "checks_passed": 5,
            "checks_total": 7,
            "score": 71.4,
        },
    },
    {
        "audit_id": "wolfai-user-gpt4o",
        "model": "gpt-4o",
        "group": "user",
        "key_name": "cd",
        "overall_score": 57.5,
        "trust_level": "critical",
        "duration_s": 47.6,
        "token": {
            "prompt_reported": 81,
            "prompt_expected": 46,
            "completion_reported": 463,
            "total_reported": 544,
            "inflation_pct": 76.09,
            "suspicious": True,
            "score": 0,
        },
        "fingerprint": {
            "claimed": "gpt-4o",
            "detected_family": "openai-gpt4",
            "family_match": True,
            "confidence": 0.6,
            "suspicious": True,
            "score": 70,
        },
        "latency": {
            "avg_ms": 1161.4,
            "p50_ms": 1210.6,
            "p95_ms": 1219.9,
            "error_rate": 0.0,
            "score": 88.4,
        },
        "protocol": {
            "checks_passed": 5,
            "checks_total": 7,
            "score": 71.4,
        },
    },
]

# Models not supported
unsupported = [
    {"group": "Codex", "model": "gpt-4o-mini", "error": "503 model_not_found"},
    {"group": "Codex", "model": "gpt-4o", "error": "503 model_not_found"},
    {"group": "user", "model": "gpt-4o-mini", "error": "503 model_not_found"},
    {"group": "Mini", "model": "gpt-4o-mini", "error": "503 model_not_found"},
    {"group": "Mini", "model": "gpt-4o", "error": "503 model_not_found"},
    {"group": "Mini", "model": "gpt-3.5-turbo", "error": "503 model_not_found"},
]

# Print comparison table
print("=" * 90)
print("WolfAI.top 中转站审计对比报告")
print("=" * 90)
print(f"{'分组':<10} {'模型':<15} {'总分':<8} {'信任等级':<10} {'Token膨胀':<12} {'平均延迟':<12} {'协议合规':<10}")
print("-" * 90)
for r in results:
    print(f"{r['group']:<10} {r['model']:<15} {r['overall_score']:<8.1f} {r['trust_level']:<10} +{r['token']['inflation_pct']:<10.1f}% {r['latency']['avg_ms']:<10.1f}ms {r['protocol']['checks_passed']}/{r['protocol']['checks_total']:<7}")
print("-" * 90)

print("\n关键发现：")
print("1. 两个成功审计的Token膨胀率完全相同：+76.09%")
print("   - 预期prompt tokens: 46, 中转站报告: 81")
print("   - 差异: 35 tokens (可能来自chat template或系统提示词)")
print("2. 模型指纹检测：两个分组都检测到openai-gpt4家族，与声称模型匹配")
print("3. 延迟：user分组(gpt-4o)比default分组(gpt-4o-mini)更快（1161ms vs 1856ms）")
print("4. 协议合规：都是5/7检查通过（error_format检查失败）")
print("5. Codex和Mini分组不支持常见模型，需要使用特定模型")

print("\n不支持的模型组合：")
for u in unsupported:
    print(f"  - {u['group']}分组 / {u['model']}: {u['error']}")

# Generate HTML report for the first result (default group)
print("\n生成HTML报告...")
r = results[0]
audit_result = AuditResult(
    audit_id=r["audit_id"],
    status=AuditStatus.COMPLETED,
    model=r["model"],
    base_url="https://wolfai.top/v1",
    started_at=datetime.now(),
    completed_at=datetime.now(),
    overall_score=r["overall_score"],
    trust_level=r["trust_level"],
    checks=[
        CheckResult(
            check_type=CheckType.TOKEN_COUNT,
            name="Token Count Verification",
            passed=not r["token"]["suspicious"],
            score=r["token"]["score"],
            details=f"Reported: {r['token']['total_reported']} tokens | Prompt inflation: +{r['token']['inflation_pct']}% | SUSPICIOUS",
            evidence=r["token"],
        ),
        CheckResult(
            check_type=CheckType.MODEL_FINGERPRINT,
            name="Model Fingerprint Verification",
            passed=not r["fingerprint"]["suspicious"],
            score=r["fingerprint"]["score"],
            details=f"Claimed: {r['fingerprint']['claimed']} | Detected: {r['fingerprint']['detected_family']} | Match: {r['fingerprint']['family_match']} | Confidence: {r['fingerprint']['confidence']*100}%",
            evidence=r["fingerprint"],
        ),
        CheckResult(
            check_type=CheckType.RESPONSE_LATENCY,
            name="Response Latency & Availability",
            passed=True,
            score=r["latency"]["score"],
            details=f"Avg: {r['latency']['avg_ms']}ms, P50: {r['latency']['p50_ms']}ms, P95: {r['latency']['p95_ms']}ms, Error rate: {r['latency']['error_rate']*100}%",
            evidence=r["latency"],
        ),
        CheckResult(
            check_type=CheckType.PROTOCOL_COMPLIANCE,
            name="API Protocol Compliance",
            passed=True,
            score=r["protocol"]["score"],
            details=f"{r['protocol']['checks_passed']}/{r['protocol']['checks_total']} checks passed",
            evidence=r["protocol"],
        ),
    ],
    token_comparison=TokenComparison(
        prompt_tokens_reported=r["token"]["prompt_reported"],
        prompt_tokens_expected=r["token"]["prompt_expected"],
        completion_tokens_reported=r["token"]["completion_reported"],
        completion_tokens_expected=0,
        total_tokens_reported=r["token"]["total_reported"],
        prompt_inflation_pct=r["token"]["inflation_pct"],
        completion_inflation_pct=0.0,
        suspicious=r["token"]["suspicious"],
    ),
    fingerprint=FingerprintResult(
        claimed_model=r["fingerprint"]["claimed"],
        detected_family=r["fingerprint"]["detected_family"],
        family_match=r["fingerprint"]["family_match"],
        confidence=r["fingerprint"]["confidence"],
        suspicious=r["fingerprint"]["suspicious"],
    ),
    summary=f"Audit of {r['model']} at https://wolfai.top/v1 (group: {r['group']})\nOverall: {r['overall_score']}/100 ({r['trust_level']})\nToken inflation: +{r['token']['inflation_pct']}%\nKey finding: Both tested groups show identical +76.09% token inflation, suggesting systematic overcounting.",
    recommendations=[
        "Token count inflation detected (+76.09%) - the relay reports 81 prompt tokens when tiktoken expects 46.",
        "Both default and user groups show identical inflation rate, suggesting systematic overcounting rather than random error.",
        "Consider verifying with official API for precise comparison, or switch to a different relay.",
        "CRITICAL: This relay has serious token counting issues. We recommend caution for cost-sensitive workloads.",
    ],
)

html = generate_html_report(audit_result)
report_path = Path(__file__).parent.parent / "docs" / "wolfai_audit_report.html"
report_path.write_text(html, encoding="utf-8")
print(f"HTML报告已保存: {report_path}")
print(f"文件大小: {report_path.stat().st_size / 1024:.1f} KB")
