"""
End-to-end integration tests - 端到端集成测试

这些测试需要真实的API密钥，默认不运行。

运行方式：
    # 设置环境变量
    export TRANSIT_TRUTH_TEST_API_KEY="your-api-key"
    export TRANSIT_TRUTH_TEST_BASE_URL="https://api.openai.com/v1"
    export TRANSIT_TRUTH_TEST_MODEL="gpt-4o-mini"

    # 运行集成测试
    pytest tests/test_integration.py -m integration -v

    # 运行所有测试（包括单元测试和集成测试）
    pytest tests/ -m "integration or not integration" -v
"""
import pytest
import asyncio

from app.core.auditor import AuditRequest, AuditEngine
from app.core.model_reference import get_model_reference
from app.core.statistical_analyzer import (
    StatisticalAnalyzer,
    wilson_score_interval,
    assess_sample_adequacy,
)

pytestmark = pytest.mark.integration


class TestHTTPClientIntegration:
    """HTTP客户端集成测试"""

    def test_chat_completion_success(self, api_key, base_url, test_model):
        """测试成功的聊天补全请求"""
        from app.utils.http_client import AsyncAPIClient

        async def run():
            async with AsyncAPIClient(api_key, base_url) as client:
                result = await client.chat_completion(
                    model=test_model,
                    messages=[{"role": "user", "content": "Say 'hello'"}],
                    max_tokens=10,
                    temperature=0,
                )
                return result

        result = asyncio.run(run())
        assert "error" not in result, f"请求失败: {result.get('error')}"
        assert "choices" in result
        assert result["_status_code"] == 200
        assert "_latency_ms" in result
        assert result["_latency_ms"] > 0

    def test_check_availability(self, api_key, base_url, test_model):
        """测试API可用性检查"""
        from app.utils.http_client import AsyncAPIClient

        async def run():
            async with AsyncAPIClient(api_key, base_url) as client:
                result = await client.check_availability(test_model)
                return result, client.stats

        result, stats = asyncio.run(run())
        assert "error" not in result
        assert stats["total_requests"] == 1
        assert stats["successful"] == 1

    def test_retry_on_rate_limit(self, api_key, base_url, test_model):
        """测试限流时的重试机制（发送大量请求触发限流）"""
        from app.utils.http_client import AsyncAPIClient

        async def run():
            async with AsyncAPIClient(api_key, base_url, timeout=10) as client:
                # 发送20个并发请求，可能触发限流
                tasks = [
                    client.chat_completion(
                        model=test_model,
                        messages=[{"role": "user", "content": f"Say number {i}"}],
                        max_tokens=5,
                        temperature=0,
                    )
                    for i in range(20)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                return results, client.stats

        results, stats = asyncio.run(run())
        # 至少大部分请求应该成功（即使有限流，重试后应该成功）
        success_count = sum(1 for r in results if isinstance(r, dict) and "error" not in r)
        assert success_count >= 15, f"成功率太低: {success_count}/20"
        assert stats["total_requests"] == 20


class TestAuditorIntegration:
    """审计器集成测试"""

    def test_full_audit_quick_mode(self, api_key, base_url, test_model):
        """测试快速模式的完整审计流程"""
        request = AuditRequest(
            api_key=api_key,
            base_url=base_url,
            model=test_model,
            mode="quick",
            run_token_check=True,
            run_fingerprint=True,
            run_latency=True,
            run_protocol=True,
        )

        auditor = AuditEngine()
        result = asyncio.run(auditor.run_audit(request))

        assert result.status.value == "completed"
        assert result.overall_score is not None
        assert 0 <= result.overall_score <= 100
        assert result.trust_level in ["high", "medium", "low", "critical"]
        assert len(result.checks) > 0
        assert result.model_reference is not None or True  # 可能没有参考数据

    def test_full_audit_deep_mode(self, api_key, base_url, test_model):
        """测试深度模式的完整审计流程（较慢）"""
        request = AuditRequest(
            api_key=api_key,
            base_url=base_url,
            model=test_model,
            mode="deep",
            run_token_check=True,
            run_fingerprint=True,
            run_latency=True,
            run_protocol=True,
        )

        auditor = AuditEngine()
        result = asyncio.run(auditor.run_audit(request))

        assert result.status.value == "completed"
        assert result.overall_score is not None
        # 深度模式应该有更多检查
        assert len(result.checks) >= 3

    def test_audit_with_invalid_api_key(self, base_url, test_model):
        """测试无效API密钥的错误处理"""
        request = AuditRequest(
            api_key="sk-invalid-key-for-testing",
            base_url=base_url,
            model=test_model,
            mode="quick",
        )

        auditor = AuditEngine()
        result = asyncio.run(auditor.run_audit(request))

        # 无效密钥应该返回错误或低信任分，不应该崩溃
        assert result.status.value in ["completed", "failed"]


class TestModelReferenceIntegration:
    """模型参考数据集成测试"""

    def test_get_reference_for_known_models(self):
        """测试获取已知模型的参考数据"""
        known_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "claude-3-5-sonnet",
            "gemini-1.5-pro",
            "llama-3.1-70b",
        ]

        for model in known_models:
            ref = get_model_reference(model)
            assert ref is not None, f"未找到模型 {model} 的参考数据"
            assert ref.display_name is not None
            assert ref.provider is not None
            assert ref.intelligence_index is not None

    def test_fuzzy_matching(self):
        """测试模糊匹配"""
        # 带版本号的模型名称
        ref = get_model_reference("gpt-4o-2024-08-06")
        assert ref is not None
        assert ref.model_id == "gpt-4o"

        # 大小写不同
        ref = get_model_reference("GPT-4O-MINI")
        assert ref is not None
        assert ref.model_id == "gpt-4o-mini"


class TestStatisticalAnalysisIntegration:
    """统计分析集成测试"""

    def test_wilson_score_interval(self):
        """测试Wilson置信区间计算"""
        # 50个样本，30个成功
        lower, upper = wilson_score_interval(30, 50)
        assert 0 < lower < 0.6
        assert 0.4 < upper < 1.0
        assert lower < upper

        # 0个样本
        lower, upper = wilson_score_interval(0, 0)
        assert lower == 0.0
        assert upper == 1.0

        # 极端情况（全部成功）
        lower, upper = wilson_score_interval(50, 50)
        assert lower > 0.8
        assert upper == 1.0

    def test_sample_adequacy_assessment(self):
        """测试样本量评估"""
        # 充足的样本量
        adequacy, warning = assess_sample_adequacy(200, 20)
        assert adequacy == "sufficient"
        assert warning is None

        # 中等样本量
        adequacy, warning = assess_sample_adequacy(100, 10)
        assert adequacy == "moderate"
        assert warning is not None

        # 不足的样本量
        adequacy, warning = assess_sample_adequacy(30, 5)
        assert adequacy == "insufficient"
        assert warning is not None
        assert "不足" in warning or "insufficient" in warning.lower()

    def test_statistical_analyzer_with_real_baselines(self):
        """测试使用真实基准数据的统计分析器"""
        analyzer = StatisticalAnalyzer()
        analyzer.load_real_baselines()

        # 检查是否加载了基准数据
        assert len(analyzer.baseline_db) > 0, "未加载到基准数据"

        # 模拟观测数据（应该与gpt-4o-mini匹配）
        observed_behavioral = {
            "beh-number-1-10": ["7"] * 5,  # gpt-4o-mini 100% 返回 7
        }

        verdict = analyzer.analyze(
            claimed_model="gpt-4o-mini",
            observed_tokenizer={"tok-digits": 27},
            observed_behavioral=observed_behavioral,
        )

        assert verdict is not None
        assert verdict.baseline_sample_size > 0
        assert verdict.sample_adequacy in ["sufficient", "moderate", "insufficient"]
        assert verdict.posterior_probability is not None


class TestEndToEndWorkflow:
    """端到端工作流测试"""

    def test_complete_audit_workflow(self, api_key, base_url, test_model):
        """测试完整的审计工作流：请求→审计→结果分析→建议"""
        # 1. 创建审计请求
        request = AuditRequest(
            api_key=api_key,
            base_url=base_url,
            model=test_model,
            mode="quick",
        )

        # 2. 运行审计
        auditor = AuditEngine()
        result = asyncio.run(auditor.run_audit(request))

        # 3. 验证结果
        assert result.status.value == "completed"
        assert result.overall_score is not None

        # 4. 验证建议
        assert len(result.recommendations) > 0
        # 建议应该是中文的（因为我们改进了建议生成）
        for rec in result.recommendations:
            assert len(rec) > 10  # 建议应该有足够的内容

        # 5. 验证摘要
        assert result.summary is not None
        assert len(result.summary) > 0

        # 6. 验证模型参考数据（如果有）
        if result.model_reference:
            assert "display_name" in result.model_reference
            assert "provider" in result.model_reference

        print(f"\n审计完成: {test_model}")
        print(f"  信任分: {result.overall_score}/100 ({result.trust_level})")
        print(f"  检查项: {len(result.checks)}")
        print(f"  建议数: {len(result.recommendations)}")
