"""Main audit engine - orchestrates all checks."""
import asyncio
import uuid
from datetime import datetime
from typing import Optional

from ..config import DEFAULT_PROBE_COUNT
from ..models import (
    AuditRequest,
    AuditResult,
    AuditStatus,
    CheckResult,
    CheckType,
)
from ..utils.http_client import AsyncAPIClient
from .fingerprint import ModelFingerprinter
from .latency_protocol import LatencyChecker, ProtocolChecker
from .token_check import TokenVerifier
from .randomized_probes import generate_randomized_probes


class AuditEngine:
    """Orchestrates the full audit pipeline."""

    def __init__(self):
        self.audits: dict[str, AuditResult] = {}

    async def run_audit(self, request: AuditRequest) -> AuditResult:
        """Run a complete audit."""
        # Determine probe count based on mode if not explicitly set
        if request.probe_count is None:
            if request.mode == "quick":
                request.probe_count = 3
            else:
                request.probe_count = 10

        audit_id = str(uuid.uuid4())[:8]
        result = AuditResult(
            audit_id=audit_id,
            status=AuditStatus.RUNNING,
            model=request.model,
            base_url=request.base_url,
            started_at=datetime.now(),
        )
        self.audits[audit_id] = result

        try:
            async with AsyncAPIClient(request.api_key, request.base_url) as client:
                # Check availability first
                avail = await client.check_availability(request.model)
                if "error" in avail:
                    result.status = AuditStatus.FAILED
                    result.error = f"API unavailable: {avail.get('error', {})}"
                    result.completed_at = datetime.now()
                    return result

                # Official API client for comparison (if provided)
                official_client = None
                if request.official_api_key:
                    # Determine official base URL from model
                    official_base = self._get_official_base(request.model)
                    if official_base:
                        official_client = AsyncAPIClient(request.official_api_key, official_base)

                checks = []

                # 1. Token count check
                if request.run_token_check:
                    token_check = CheckResult(
                        check_type=CheckType.TOKEN_COUNT,
                        name="Token Count Verification",
                        passed=False,
                        score=0,
                        details="Running...",
                    )
                    checks.append(token_check)

                    verifier = TokenVerifier(client, request.model)
                    token_result = await verifier.verify(official_client=official_client)
                    result.token_comparison = token_result

                    token_check.passed = not token_result.suspicious
                    token_check.score = 100 if not token_result.suspicious else max(0, 100 - abs(token_result.prompt_inflation_pct or 0) * 2)
                    token_check.details = self._token_summary(token_result)
                    token_check.evidence = token_result.model_dump()

                # 2. Model fingerprint check
                if request.run_fingerprint:
                    fp_check = CheckResult(
                        check_type=CheckType.MODEL_FINGERPRINT,
                        name="Model Fingerprint Verification",
                        passed=False,
                        score=0,
                        details="Running...",
                    )
                    checks.append(fp_check)

                    # Generate randomized probes to prevent relay defense
                    randomized_probes, probe_seed = generate_randomized_probes()
                    fingerprinter = ModelFingerprinter(client, request.model, custom_probes=randomized_probes)
                    await fingerprinter.run_tokenizer_probes(count=min(8, request.probe_count))
                    # Behavioral probes need more samples to detect fingerprints
                    # (e.g., gpt-4o-mini returns "7" 100% for 1-10 selection)
                    behavioral_samples = 10 if request.mode == "deep" else 5
                    await fingerprinter.run_behavioral_probes(
                        count=min(6, request.probe_count),
                        samples=behavioral_samples
                    )
                    await fingerprinter.run_capability_probes(count=min(6, request.probe_count))
                    fp_result = fingerprinter.analyze()
                    result.fingerprint = fp_result

                    fp_check.passed = not fp_result.suspicious
                    fp_check.score = 100 if not fp_result.suspicious else max(0, 100 - fp_result.confidence * 50)
                    fp_check.details = self._fingerprint_summary(fp_result)
                    fp_check.evidence = {
                        "claimed_model": fp_result.claimed_model,
                        "detected_family": fp_result.detected_family,
                        "family_match": fp_result.family_match,
                        "confidence": fp_result.confidence,
                        "suspicious": fp_result.suspicious,
                        "capability_tier": fp_result.tokenizer_signature.get("capability_tier", "unknown") if hasattr(fp_result, 'tokenizer_signature') else "unknown",
                    }

                # 3. Latency check
                if request.run_latency:
                    lat_check = CheckResult(
                        check_type=CheckType.RESPONSE_LATENCY,
                        name="Response Latency & Availability",
                        passed=False,
                        score=0,
                        details="Running...",
                    )
                    checks.append(lat_check)

                    latency_checker = LatencyChecker(client, request.model)
                    lat_result = await latency_checker.measure(samples=5)

                    # Score: lower latency and lower error rate = better
                    error_penalty = lat_result["error_rate"] * 50
                    latency_penalty = min(lat_result["avg_latency_ms"] / 100, 30)  # Cap at 30
                    lat_score = max(0, 100 - error_penalty - latency_penalty)

                    lat_check.passed = lat_result["error_rate"] < 0.2 and lat_result["avg_latency_ms"] < 10000
                    lat_check.score = round(lat_score, 1)
                    lat_check.details = (
                        f"Avg: {lat_result['avg_latency_ms']}ms, "
                        f"P50: {lat_result['p50_latency_ms']}ms, "
                        f"P95: {lat_result['p95_latency_ms']}ms, "
                        f"Error rate: {lat_result['error_rate']*100:.0f}%"
                    )
                    lat_check.evidence = lat_result

                # 4. Protocol compliance check
                if request.run_protocol:
                    proto_check = CheckResult(
                        check_type=CheckType.PROTOCOL_COMPLIANCE,
                        name="API Protocol Compliance",
                        passed=False,
                        score=0,
                        details="Running...",
                    )
                    checks.append(proto_check)

                    protocol_checker = ProtocolChecker(client, request.model)
                    proto_result = await protocol_checker.check()
                    summary = proto_result.get("_summary", {})

                    proto_check.passed = summary.get("score", 0) >= 70
                    proto_check.score = summary.get("score", 0)
                    proto_check.details = f"{summary.get('passed', 0)}/{summary.get('total', 0)} checks passed"
                    proto_check.evidence = {k: v for k, v in proto_result.items() if k != "_summary"}

                # Close official client if opened
                if official_client:
                    await official_client.__aexit__(None, None, None)

                # Calculate overall score
                result.checks = checks
                if checks:
                    result.overall_score = round(sum(c.score for c in checks) / len(checks), 1)
                result.trust_level = self._trust_level(result.overall_score, checks)
                result.summary = self._generate_summary(result)
                result.recommendations = self._generate_recommendations(result)

                # Add model reference data (公开权威数据对比)
                try:
                    from app.core.model_reference import get_model_reference
                    ref = get_model_reference(result.model)
                    if ref:
                        result.model_reference = {
                            "display_name": ref.display_name,
                            "provider": ref.provider,
                            "tier": ref.tier,
                            "official_price": {
                                "input": ref.input_price,
                                "output": ref.output_price,
                            },
                            "intelligence_index": ref.intelligence_index,
                            "arena_elo": ref.arena_elo,
                            "arena_rank": ref.arena_rank,
                            "ttft_seconds": ref.ttft_seconds,
                            "output_tokens_per_second": ref.output_tokens_per_second,
                            "context_window": ref.context_window,
                            "release_date": ref.release_date,
                        }
                except Exception:
                    pass  # Reference data is optional

                result.status = AuditStatus.COMPLETED
                result.completed_at = datetime.now()

        except Exception as e:
            result.status = AuditStatus.FAILED
            result.error = str(e)
            result.completed_at = datetime.now()

        return result

    def _get_official_base(self, model: str) -> Optional[str]:
        """Get official API base URL for a model."""
        model_lower = model.lower()
        if any(k in model_lower for k in ["gpt", "o1", "o3", "dall"]):
            return "https://api.openai.com/v1"
        if "claude" in model_lower:
            return "https://api.anthropic.com/v1"
        if "gemini" in model_lower:
            return "https://generativelanguage.googleapis.com/v1beta"
        return None

    def _token_summary(self, token_result) -> str:
        parts = [f"Reported: {token_result.total_tokens_reported} tokens"]
        if token_result.prompt_inflation_pct is not None:
            parts.append(f"Prompt discrepancy: {token_result.prompt_inflation_pct:+.1f}%")
        if token_result.completion_inflation_pct is not None:
            parts.append(f"Completion discrepancy: {token_result.completion_inflation_pct:+.1f}%")
        if token_result.chat_template_overhead > 0:
            parts.append(f"Chat template est.: {token_result.chat_template_overhead} tokens")
        if token_result.suspicious:
            parts.append("⚠ SUSPICIOUS (adjusted for chat template)")
        return " | ".join(parts)

    def _fingerprint_summary(self, fp_result) -> str:
        parts = [f"Claimed: {fp_result.claimed_model}"]
        if fp_result.detected_family:
            parts.append(f"Detected family: {fp_result.detected_family}")
        parts.append(f"Family match: {'✓' if fp_result.family_match else '✗'}")
        parts.append(f"Confidence: {fp_result.confidence:.0%}")
        if fp_result.suspicious:
            parts.append("⚠ SUSPICIOUS")
        return " | ".join(parts)

    def _trust_level(self, score: float, checks: list[CheckResult]) -> str:
        """Determine trust level from score and checks."""
        has_critical_failure = any(
            c.check_type in (CheckType.TOKEN_COUNT, CheckType.MODEL_FINGERPRINT)
            and not c.passed
            for c in checks
        )
        if has_critical_failure:
            return "critical"
        if score >= 80:
            return "high"
        if score >= 60:
            return "medium"
        if score >= 40:
            return "low"
        return "critical"

    def _generate_summary(self, result: AuditResult) -> str:
        """Generate human-readable summary."""
        parts = [f"Audit of {result.model} at {result.base_url}"]
        parts.append(f"Overall score: {result.overall_score}/100 ({result.trust_level} trust)")

        for check in result.checks:
            status = "✓" if check.passed else "✗"
            parts.append(f"  {status} {check.name}: {check.score}/100 - {check.details}")

        if result.token_comparison and result.token_comparison.suspicious:
            parts.append("⚠ Token count inflation detected!")
        if result.fingerprint and result.fingerprint.suspicious:
            parts.append("⚠ Model identity mismatch detected!")

        return "\n".join(parts)

    def _generate_recommendations(self, result: AuditResult) -> list[str]:
        """Generate actionable recommendations based on audit findings."""
        recs = []

        # Token inflation - specific actionable steps
        if result.token_comparison and result.token_comparison.suspicious:
            inflation = result.token_comparison.prompt_inflation_pct or 0
            recs.append(
                f"⚠ Token 差异率 {inflation:+.1f}% - 中转站可能多计 token。"
                f"建议：1) 用官方 API 跑同样请求对比 token 数；"
                f"2) 计算实际成本差异（每 1M tokens 多花 ${inflation/100*2.5:.2f}）；"
                f"3) 如确认多计，联系中转站客服或更换服务商。"
            )

        # Model fingerprint mismatch - specific verification steps
        if result.fingerprint and result.fingerprint.suspicious:
            confidence = result.fingerprint.confidence or 0
            detected = result.fingerprint.detected_family or "未知"
            recs.append(
                f"⚠ 模型身份不匹配（置信度 {confidence*100:.0f}%）- 检测到家族：{detected}。"
                f"建议：1) 切换到深度模式（10个探针）重新审计；"
                f"2) 用行为探针手动验证（如'选1-10数字'，gpt-4o-mini 100% 返回 7）；"
                f"3) 询问中转站客服确认实际使用的模型；"
                f"4) 如确认降级，保留证据并考虑投诉或更换。"
            )

        # High latency - specific thresholds
        latency_checks = [c for c in result.checks if c.check_type == CheckType.RESPONSE_LATENCY]
        if latency_checks and not latency_checks[0].passed:
            recs.append(
                "⚠ 延迟过高或错误率高 - 不适合生产环境。"
                "建议：1) 检查网络连接（换节点/代理）；"
                "2) 对比官方 API 延迟（gpt-4o 官方 TTFT ~0.65s）；"
                "3) 如中转站持续高延迟，考虑更换或使用官方 API。"
            )

        # Protocol non-compliance
        proto_checks = [c for c in result.checks if c.check_type == CheckType.PROTOCOL_COMPLIANCE]
        if proto_checks and proto_checks[0].score < 70:
            recs.append(
                "⚠ API 协议不兼容 - 可能缺少 usage 字段或 model 回显。"
                "建议：1) 检查客户端库是否依赖这些字段；"
                "2) 如字段缺失，可能导致 token 计数、模型识别等功能异常；"
                "3) 联系中转站修复或更换兼容的服务商。"
            )

        # Capability test failure
        cap_checks = [c for c in result.checks if c.check_type == CheckType.CAPABILITY_TEST]
        if cap_checks and cap_checks[0].score < 60:
            recs.append(
                "⚠ 能力测试失败率高 - 模型可能被降级。"
                "建议：1) 用官方 API 跑同样的能力测试对比；"
                "2) 简单数学题（17*23=391）和逻辑题应该所有模型都能答对；"
                "3) 如频繁答错，模型很可能被降级到更低档次。"
            )

        # Positive recommendations
        if result.trust_level == "high":
            recs.append(
                "✓ 该中转站通过所有检查，看起来可信。"
                "建议：1) 定期（每周）重新审计监控变化；"
                "2) 关注余额变化，防止突然涨价；"
                "3) 可考虑贡献审计结果到社区排行榜帮助他人。"
            )
        elif result.trust_level == "medium":
            recs.append(
                "⚡ 该中转站有一些小问题，但基本可用。"
                "建议：1) 不用于关键生产环境；"
                "2) 定期监控问题是否恶化；"
                "3) 准备备选中转站以防问题加重。"
            )
        elif result.trust_level == "low":
            recs.append(
                "⚠ 该中转站问题较多，谨慎使用。"
                "建议：1) 仅用于非关键测试；"
                "2) 不要充值过多余额；"
                "3) 尽快寻找替代方案。"
            )
        elif result.trust_level == "critical":
            recs.append(
                "🚨 严重警告：该中转站有严重问题，建议立即停止使用！"
                "建议：1) 不要继续充值；"
                "2) 如有余额，尽快用完或申请退款；"
                "3) 切换到官方 API 或可信中转站；"
                "4) 保留审计证据，必要时在社区曝光。"
            )

        return recs
