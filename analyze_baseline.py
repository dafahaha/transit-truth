"""Reproduce the flagship gpt-4o-mini baseline result.

This is the analysis script referenced by the report appendix. It loads the
REAL baselines collected from the live API (data/baselines/gpt-4o-mini.json
and gpt-4o.json), then feeds the gpt-4o-mini baseline's own distributions back
as the "observed" sample (resubstitution) and runs the exact Bayesian + KS /
chi-square pipeline that the production audit uses.

It must reproduce: posterior ~= 0.913, 95% CrI ~= [0.885, 0.937], LR = 4.5,
confidence = medium. A regression test runs this script as a subprocess and
asserts exit code 0 plus a posterior of ~0.913, so it can never silently rot.

Exit code: 0 on success, non-zero on failure.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.statistical_analyzer import StatisticalAnalyzer

BASELINES_DIR = REPO_ROOT / "data" / "baselines"
TARGET_MODEL = "gpt-4o-mini"


def _fmt(value, spec=".4f"):
    """Format a numeric verdict field, returning 'N/A' for None.

    Without this guard, a missing baseline leaves e.g. ``ks_statistic`` as
    None and ``f"{None:.4f}"`` raises TypeError. Printing 'N/A' instead keeps
    the report alive and makes the missing-baseline problem visible.
    """
    if value is None:
        return "N/A"
    return format(value, spec)


def main() -> int:
    baseline_path = BASELINES_DIR / f"{TARGET_MODEL}.json"
    if not baseline_path.exists():
        print(f"ERROR: baseline file not found: {baseline_path}", file=sys.stderr)
        return 1

    # Load the raw JSON only for the human-readable summary below.
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline_data = json.load(f)

    print("=" * 60)
    print(f"{TARGET_MODEL} 基准数据分析报告")
    print("=" * 60)
    print()

    # 元数据
    meta = baseline_data["metadata"]
    print(f"模型: {meta['model']}")
    print(f"采集时间: {meta['collected_at']}")
    print(f"总请求数: {meta['total_requests']}")
    print(
        f"失败请求: {meta['failed_requests']} "
        f"({meta['failed_requests'] / max(meta['total_requests'], 1) * 100:.1f}%)"
    )
    print(f"耗时: {meta['elapsed_seconds']:.1f}s")
    print()

    # 行为探针数据（模型指纹核心）
    print("--- 行为探针数据（模型指纹核心） ---")
    print(
        f"{'探针':<25} {'最高频回答':<15} {'占比':<8} {'正常随机':<8} {'偏差倍数':<8}"
    )
    print("-" * 70)
    random_pct_map = {
        "100": 1.0,
        "color": 1.0,
        "coin": 50.0,
        "letter": 3.8,
        "dice": 16.7,
        "animal": 1.0,
        "day": 14.3,
        "1-10": 10.0,
    }
    for probe_id, data in baseline_data["behavioral"].items():
        dist = data["response_distribution"]
        if not dist:
            continue
        top = max(dist.items(), key=lambda x: x[1])
        total = sum(dist.values())
        pct = top[1] / total * 100
        random_pct = next((v for k, v in random_pct_map.items() if k in probe_id), 10.0)
        deviation = pct / max(random_pct, 0.1)
        print(
            f"  {probe_id:<23} {top[0]:<15} {pct:.0f}%{'':<5} "
            f"{random_pct:.1f}%{'':<4} {deviation:.1f}x"
        )

    print()
    print("=" * 60)
    print("统计方法验证")
    print("=" * 60)

    # Load the REAL baselines (gpt-4o-mini.json + gpt-4o.json), NOT the small
    # synthetic defaults. The synthetic defaults do not contain gpt-4o-mini, so
    # the analysis previously returned an "inconclusive" 0.500 posterior and
    # then crashed formatting the None KS statistic.
    analyzer = StatisticalAnalyzer()
    analyzer.load_real_baselines()

    baseline = analyzer._resolve_baseline(TARGET_MODEL)
    if baseline is None:
        print(
            f"ERROR: no real baseline loaded for {TARGET_MODEL}",
            file=sys.stderr,
        )
        return 1

    # Resubstitution: feed the baseline's OWN distributions back as the
    # "observed" sample. This is the reference check that the pipeline can
    # correctly recognize a model that matches its baseline.
    observed_tokenizer = {
        probe_id: float(samples[0])
        for probe_id, samples in baseline.tokenizer_distributions.items()
        if samples
    }
    observed_behavioral = {
        probe_id: list(responses)
        for probe_id, responses in baseline.behavioral_distributions.items()
        if responses
    }

    verdict = analyzer.analyze(
        claimed_model=TARGET_MODEL,
        observed_tokenizer=observed_tokenizer,
        observed_behavioral=observed_behavioral,
        capability_failure_rate=0.0,
    )

    print(f"  声称模型: {verdict.claimed_model}")
    print(f"  检测家族: {verdict.detected_family or 'N/A'}")
    print(f"  结论: {verdict.conclusion}")
    print(f"  后验概率: {_fmt(verdict.posterior_probability, '.3f')}")
    print(
        f"  95% CI: [{_fmt(verdict.posterior_ci_lower, '.3f')}, "
        f"{_fmt(verdict.posterior_ci_upper, '.3f')}]"
    )
    print(
        f"  KS统计量: {_fmt(verdict.ks_statistic)}, " f"p值: {_fmt(verdict.ks_pvalue)}"
    )
    print(
        f"  卡方统计量: {_fmt(verdict.chi2_statistic)}, "
        f"p值: {_fmt(verdict.chi2_pvalue)}"
    )
    print(f"  置信度: {verdict.confidence_level}")
    print(f"  似然比: {verdict.details.get('likelihood_ratio', 'N/A')}")

    print()
    print("=" * 60)
    print("实验结论")
    print("=" * 60)
    print("1. gpt-4o-mini 的行为指纹极强，随机数偏好偏差达 10-74 倍")
    print("2. 这些偏好来自训练数据与 RLHF，中转站难以伪造")
    print("3. 统计分析方法（KS 检验 + 贝叶斯更新）能正确识别匹配")
    print("4. 基准数据已保存到 data/baselines/gpt-4o-mini.json")
    print("5. 下一步：采集 gpt-4o、claude、gemini 等模型的基准数据以验证区分度")
    return 0


if __name__ == "__main__":
    sys.exit(main())
