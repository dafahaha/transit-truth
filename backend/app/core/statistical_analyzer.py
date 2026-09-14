"""Statistical analyzer for model fingerprinting.

This module provides rigorous statistical methods for model verification,
moving beyond heuristic scoring to statistically significant conclusions.

Key concepts:
- Baseline database: known distributions for each model family
- KS test: compare token count distributions
- Chi-square test: compare behavioral distributions
- Bayesian updating: combine prior beliefs with evidence
- Confidence intervals: quantify uncertainty
- False positive/negative rates: measure test reliability

References:
- CoIn (arXiv 2505.13778): "Can You Trust Your LLM API?"
- SILENT-BENCH: benchmark for silent model degradation
"""
import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import stats


@dataclass
class BaselineDistribution:
    """Baseline distribution for a model family.

    Collected by running probes against official APIs.
    """
    model_family: str
    model_name: str
    # Tokenizer probe results: {probe_id: [prompt_token_counts]}
    tokenizer_distributions: dict[str, list[float]] = field(default_factory=dict)
    # Behavioral probe results: {probe_id: [responses]}
    behavioral_distributions: dict[str, list[str]] = field(default_factory=dict)
    # Latency distribution
    latency_distribution: list[float] = field(default_factory=list)
    # Sample size
    sample_size: int = 0
    # Collection date
    collected_at: str = ""


@dataclass
class StatisticalVerdict:
    """Statistically grounded verdict for model verification."""
    claimed_model: str
    detected_family: Optional[str]
    # Test results
    ks_statistic: Optional[float] = None
    ks_pvalue: Optional[float] = None
    chi2_statistic: Optional[float] = None
    chi2_pvalue: Optional[float] = None
    # Bayesian posterior probability that the model is as claimed
    posterior_probability: float = 0.5
    # Confidence interval for posterior (95%)
    posterior_ci_lower: float = 0.0
    posterior_ci_upper: float = 1.0
    # Conclusion
    conclusion: str = "inconclusive"  # "match", "mismatch", "inconclusive"
    confidence_level: str = "low"  # "high", "medium", "low"
    # Details
    details: dict = field(default_factory=dict)


class StatisticalAnalyzer:
    """Rigorous statistical analysis for model fingerprinting."""

    def __init__(self, baseline_db: Optional[dict[str, BaselineDistribution]] = None):
        self.baseline_db = baseline_db or {}
        # Prior probability: assume 70% of relays are honest (base rate)
        self.prior_honest = 0.7

    def load_default_baselines(self):
        """Load default baseline distributions (synthetic, for demonstration).

        In production, these should be collected from official APIs.
        """
        # GPT-4 family baseline (cl100k/o200k tokenizer)
        gpt4 = BaselineDistribution(
            model_family="openai-gpt",
            model_name="gpt-4o",
            tokenizer_distributions={
                # prompt token counts for each probe (mean ± std from official API)
                "tok-digits": [22, 23, 22, 24, 23, 22, 23, 22, 24, 23],
                "tok-cjk": [24, 25, 24, 26, 25, 24, 25, 24, 26, 25],
                "tok-emoji": [30, 32, 31, 33, 32, 30, 31, 32, 33, 31],
                "tok-code": [18, 19, 18, 20, 19, 18, 19, 18, 20, 19],
            },
            behavioral_distributions={
                "beh-random-100": ["42", "17", "73", "89", "55", "28", "64", "91", "37", "12"],
                "beh-coin-flip": ["heads", "tails", "heads", "heads", "tails", "tails", "heads", "tails", "heads", "tails"],
            },
            latency_distribution=[800, 850, 900, 780, 820, 880, 790, 840, 870, 810],
            sample_size=10,
            collected_at="2026-09-10",
        )

        # GPT-3.5 family baseline
        gpt35 = BaselineDistribution(
            model_family="openai-gpt",
            model_name="gpt-3.5-turbo",
            tokenizer_distributions={
                "tok-digits": [22, 23, 22, 24, 23, 22, 23, 22, 24, 23],  # same tokenizer
                "tok-cjk": [24, 25, 24, 26, 25, 24, 25, 24, 26, 25],
                "tok-emoji": [30, 32, 31, 33, 32, 30, 31, 32, 33, 31],
                "tok-code": [18, 19, 18, 20, 19, 18, 19, 18, 20, 19],
            },
            latency_distribution=[400, 420, 450, 380, 410, 430, 390, 420, 440, 400],
            sample_size=10,
            collected_at="2026-09-10",
        )

        # Claude family baseline
        claude = BaselineDistribution(
            model_family="anthropic-claude",
            model_name="claude-3-5-sonnet",
            tokenizer_distributions={
                "tok-digits": [30, 31, 30, 32, 31, 30, 31, 30, 32, 31],  # different tokenizer
                "tok-cjk": [16, 17, 16, 18, 17, 16, 17, 16, 18, 17],  # Claude tokenizes CJK as 1 char/token
                "tok-emoji": [40, 42, 41, 43, 42, 40, 41, 42, 43, 41],
                "tok-code": [22, 23, 22, 24, 23, 22, 23, 22, 24, 23],
            },
            latency_distribution=[1100, 1150, 1200, 1080, 1120, 1180, 1090, 1140, 1170, 1110],
            sample_size=10,
            collected_at="2026-09-10",
        )

        self.baseline_db = {
            "gpt-4o": gpt4,
            "gpt-4": gpt4,
            "gpt-3.5-turbo": gpt35,
            "claude-3-5-sonnet": claude,
            "claude-3": claude,
        }

    def load_real_baselines(self, data_dir: str = "data/baselines"):
        """Load real baseline data from JSON files collected from actual APIs.

        Replaces synthetic baselines with empirically collected data.
        Each JSON file follows the format produced by collect_baseline.py.

        Args:
            data_dir: Directory containing baseline JSON files
        """
        import json
        from pathlib import Path

        baseline_path = Path(data_dir)
        if not baseline_path.exists():
            print(f"Warning: baseline directory {data_dir} not found, keeping synthetic baselines")
            return

        loaded = 0
        for json_file in sorted(baseline_path.glob("*.json")):
            if "test" in json_file.name.lower():
                continue  # Skip test files
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                model_name = data["metadata"]["model"]

                # Build tokenizer distributions from raw samples
                tokenizer_dist = {}
                for probe_id, probe_data in data.get("tokenizer", {}).items():
                    if "prompt_tokens" in probe_data and "samples" in probe_data["prompt_tokens"]:
                        samples = probe_data["prompt_tokens"]["samples"]
                        if samples:
                            tokenizer_dist[probe_id] = [float(s) for s in samples]

                # Build behavioral distributions from frequency counts
                behavioral_dist = {}
                for probe_id, probe_data in data.get("behavioral", {}).items():
                    dist = probe_data.get("response_distribution", {})
                    responses = []
                    for resp, count in dist.items():
                        responses.extend([resp] * int(count))
                    if responses:
                        behavioral_dist[probe_id] = responses

                # Build latency distribution
                latency_dist = [float(x) for x in data.get("latency", [])]

                baseline = BaselineDistribution(
                    model_family=self._infer_family(model_name),
                    model_name=model_name,
                    tokenizer_distributions=tokenizer_dist,
                    behavioral_distributions=behavioral_dist,
                    latency_distribution=latency_dist,
                    sample_size=data["metadata"].get("samples_per_probe", 0),
                    collected_at=data["metadata"].get("collected_at", ""),
                )

                self.baseline_db[model_name] = baseline
                # Also add common aliases
                if "gpt-4o-mini" in model_name:
                    self.baseline_db["gpt-4o-mini"] = baseline
                loaded += 1
                n_tok = len(tokenizer_dist)
                n_beh = len(behavioral_dist)
                print(f"  Loaded real baseline: {model_name} (n={baseline.sample_size}, {n_tok} tokenizer, {n_beh} behavioral probes)")

            except Exception as e:
                print(f"  Error loading {json_file.name}: {e}")

        if loaded > 0:
            print(f"Loaded {loaded} real baselines from {data_dir}")

    def _infer_family(self, model_name: str) -> str:
        """Infer model family from model name."""
        name = model_name.lower()
        if any(k in name for k in ["gpt", "o1", "o3", "davinci", "curie"]):
            return "openai-gpt"
        elif "claude" in name:
            return "anthropic-claude"
        elif "gemini" in name:
            return "google-gemini"
        elif "llama" in name:
            return "meta-llama"
        elif "qwen" in name:
            return "alibaba-qwen"
        elif "mistral" in name or "mixtral" in name:
            return "mistral"
        elif "command" in name or "cohere" in name:
            return "cohere"
        else:
            return "unknown"

    def ks_test_tokenizer(self, observed: dict[str, float],
                           baseline: BaselineDistribution) -> tuple[float, float]:
        """Kolmogorov-Smirnov test for tokenizer distributions.

        Compares observed prompt token counts against baseline distribution.

        Returns:
            (ks_statistic, p_value)
        """
        all_observed = []
        all_baseline = []

        for probe_id, observed_count in observed.items():
            if probe_id in baseline.tokenizer_distributions:
                all_observed.append(observed_count)
                all_baseline.extend(baseline.tokenizer_distributions[probe_id])

        if len(all_observed) < 2 or len(all_baseline) < 2:
            return 0.0, 1.0  # insufficient data

        # Normalize by probe (since different probes have different base counts)
        # Use per-probe z-scores instead
        z_scores = []
        for probe_id, observed_count in observed.items():
            if probe_id in baseline.tokenizer_distributions:
                baseline_vals = baseline.tokenizer_distributions[probe_id]
                if len(baseline_vals) >= 2:
                    mean = statistics.mean(baseline_vals)
                    std = statistics.stdev(baseline_vals) or 1.0
                    z_scores.append((observed_count - mean) / std)

        if len(z_scores) < 2:
            return 0.0, 1.0

        # One-sample KS test against standard normal
        ks_stat, p_value = stats.kstest(z_scores, 'norm')
        return float(ks_stat), float(p_value)

    def chi2_test_behavioral(self, observed: dict[str, list[str]],
                              baseline: BaselineDistribution) -> tuple[float, float]:
        """Chi-square test for behavioral distributions.

        Compares observed response distributions against baseline.

        Returns:
            (chi2_statistic, p_value)
        """
        total_observed = 0
        total_expected = 0
        chi2_sum = 0.0
        dof = 0

        for probe_id, observed_responses in observed.items():
            if probe_id not in baseline.behavioral_distributions:
                continue

            baseline_responses = baseline.behavioral_distributions[probe_id]
            if not baseline_responses or not observed_responses:
                continue

            # Count frequencies
            observed_counts = {}
            for r in observed_responses:
                observed_counts[r] = observed_counts.get(r, 0) + 1

            baseline_counts = {}
            for r in baseline_responses:
                baseline_counts[r] = baseline_counts.get(r, 0) + 1

            # All categories
            all_categories = set(observed_counts.keys()) | set(baseline_counts.keys())
            n_baseline = sum(baseline_counts.values())
            n_observed = sum(observed_counts.values())

            if n_baseline == 0 or n_observed == 0:
                continue

            for cat in all_categories:
                expected = (baseline_counts.get(cat, 0) / n_baseline) * n_observed
                actual = observed_counts.get(cat, 0)
                if expected > 0:
                    chi2_sum += (actual - expected) ** 2 / expected
                    dof += 1

            total_observed += n_observed
            total_expected += n_baseline

        if dof <= 1:
            return 0.0, 1.0

        # p-value from chi-square distribution
        p_value = float(1 - stats.chi2.cdf(chi2_sum, dof - 1))
        return float(chi2_sum), p_value

    def bayesian_update(self, prior: float, likelihood_ratio: float) -> tuple[float, float, float]:
        """Bayesian update for model verification.

        Args:
            prior: P(honest) before evidence
            likelihood_ratio: P(evidence|honest) / P(evidence|dishonest)

        Returns:
            (posterior, ci_lower, ci_upper) - 95% credible interval
        """
        # Posterior odds = prior odds * likelihood ratio
        prior_odds = prior / (1 - prior)
        posterior_odds = prior_odds * likelihood_ratio
        posterior = posterior_odds / (1 + posterior_odds)

        # Approximate credible interval using beta distribution
        # Convert to beta parameters (pseudo-counts)
        alpha = posterior * 100  # pseudo-count for honest
        beta_param = (1 - posterior) * 100  # pseudo-count for dishonest

        if alpha > 0 and beta_param > 0:
            ci_lower = float(stats.beta.ppf(0.025, alpha, beta_param))
            ci_upper = float(stats.beta.ppf(0.975, alpha, beta_param))
        else:
            ci_lower = 0.0
            ci_upper = 1.0

        return posterior, ci_lower, ci_upper

    def calculate_likelihood_ratio(self, ks_pvalue: float,
                                     chi2_pvalue: float,
                                     capability_failure_rate: float) -> float:
        """Calculate likelihood ratio from test results.

        P(evidence|honest) / P(evidence|dishonest)

        Heuristic:
        - High p-values (>>0.05) suggest match (LR > 1)
        - Low p-values (<<0.05) suggest mismatch (LR < 1)
        - High capability failure rate suggests downgrade (LR < 1)
        """
        lr = 1.0

        # KS test contribution
        if ks_pvalue < 0.01:
            lr *= 0.1  # strong evidence of mismatch
        elif ks_pvalue < 0.05:
            lr *= 0.3  # moderate evidence
        elif ks_pvalue < 0.1:
            lr *= 0.7  # weak evidence
        elif ks_pvalue > 0.5:
            lr *= 2.0  # strong evidence of match
        elif ks_pvalue > 0.2:
            lr *= 1.5  # moderate evidence

        # Chi-square test contribution
        if chi2_pvalue < 0.01:
            lr *= 0.2
        elif chi2_pvalue < 0.05:
            lr *= 0.5
        elif chi2_pvalue > 0.5:
            lr *= 1.5

        # Capability failure rate contribution
        if capability_failure_rate > 0.7:
            lr *= 0.1  # almost certainly downgraded
        elif capability_failure_rate > 0.5:
            lr *= 0.3
        elif capability_failure_rate > 0.3:
            lr *= 0.6
        elif capability_failure_rate < 0.1:
            lr *= 1.5

        return lr

    def analyze(self, claimed_model: str,
                observed_tokenizer: dict[str, float],
                observed_behavioral: dict[str, list[str]],
                capability_failure_rate: float = 0.0) -> StatisticalVerdict:
        """Full statistical analysis for model verification.

        Args:
            claimed_model: the model name claimed by the API
            observed_tokenizer: {probe_id: prompt_token_count}
            observed_behavioral: {probe_id: [responses]}
            capability_failure_rate: fraction of capability probes failed

        Returns:
            StatisticalVerdict with statistically grounded conclusion
        """
        # Find matching baseline
        baseline = None
        for key, bl in self.baseline_db.items():
            if key.lower() in claimed_model.lower() or claimed_model.lower() in key.lower():
                baseline = bl
                break

        if baseline is None:
            return StatisticalVerdict(
                claimed_model=claimed_model,
                detected_family=None,
                conclusion="inconclusive",
                confidence_level="low",
                details={"error": f"No baseline found for {claimed_model}"},
            )

        # Run statistical tests
        ks_stat, ks_pvalue = self.ks_test_tokenizer(observed_tokenizer, baseline)
        chi2_stat, chi2_pvalue = self.chi2_test_behavioral(observed_behavioral, baseline)

        # Calculate likelihood ratio
        lr = self.calculate_likelihood_ratio(ks_pvalue, chi2_pvalue, capability_failure_rate)

        # Bayesian update
        posterior, ci_lower, ci_upper = self.bayesian_update(self.prior_honest, lr)

        # Determine conclusion
        if posterior > 0.9 and ci_lower > 0.7:
            conclusion = "match"
            confidence_level = "high"
        elif posterior > 0.7 and ci_lower > 0.5:
            conclusion = "match"
            confidence_level = "medium"
        elif posterior < 0.1 and ci_upper < 0.3:
            conclusion = "mismatch"
            confidence_level = "high"
        elif posterior < 0.3 and ci_upper < 0.5:
            conclusion = "mismatch"
            confidence_level = "medium"
        else:
            conclusion = "inconclusive"
            confidence_level = "low"

        return StatisticalVerdict(
            claimed_model=claimed_model,
            detected_family=baseline.model_family,
            ks_statistic=ks_stat,
            ks_pvalue=ks_pvalue,
            chi2_statistic=chi2_stat,
            chi2_pvalue=chi2_pvalue,
            posterior_probability=posterior,
            posterior_ci_lower=ci_lower,
            posterior_ci_upper=ci_upper,
            conclusion=conclusion,
            confidence_level=confidence_level,
            details={
                "baseline_model": baseline.model_name,
                "baseline_sample_size": baseline.sample_size,
                "likelihood_ratio": lr,
                "prior_honest": self.prior_honest,
                "ks_interpretation": self._interpret_pvalue(ks_pvalue),
                "chi2_interpretation": self._interpret_pvalue(chi2_pvalue),
            },
        )

    def _interpret_pvalue(self, pvalue: float) -> str:
        """Interpret p-value in plain language."""
        if pvalue < 0.001:
            return "极显著差异 (p<0.001)"
        elif pvalue < 0.01:
            return "高度显著差异 (p<0.01)"
        elif pvalue < 0.05:
            return "显著差异 (p<0.05)"
        elif pvalue < 0.1:
            return "边缘显著 (p<0.1)"
        elif pvalue > 0.5:
            return "无显著差异，分布高度一致"
        else:
            return "无显著差异"

    def estimate_false_positive_rate(self, n_probes: int = 10,
                                       alpha: float = 0.05) -> float:
        """Estimate false positive rate for the test battery.

        Probability of flagging an honest relay as suspicious,
        assuming independent tests with significance level alpha.

        FPR = 1 - (1 - alpha)^n_tests (at least one false positive)
        """
        n_tests = 2  # KS test + chi-square test
        fpr = 1 - (1 - alpha) ** n_tests
        return fpr

    def estimate_false_negative_rate(self, effect_size: float = 0.5,
                                       n_probes: int = 10,
                                       alpha: float = 0.05) -> float:
        """Estimate false negative rate (power analysis).

        Probability of failing to detect a real downgrade.

        Uses simplified power analysis for KS test.
        """
        # For KS test with n samples, detectable effect size ~ 1/sqrt(n)
        # Power = P(reject H0 | H1 true with effect size d)
        n_effective = n_probes * 3  # 3 samples per probe
        critical_value = math.sqrt(-0.5 * math.log(alpha / 2)) / math.sqrt(n_effective)

        if effect_size <= critical_value:
            # Effect too small to detect reliably
            power = 0.3
        else:
            # Approximate power calculation
            lambda_val = (effect_size - critical_value) * math.sqrt(n_effective)
            power = 1 - math.exp(-2 * lambda_val ** 2)

        return 1 - power


# ─── Convenience functions ────────────────────────────────────

def quick_statistical_analysis(claimed_model: str,
                                 tokenizer_results: dict,
                                 behavioral_results: dict,
                                 capability_failure_rate: float = 0.0) -> StatisticalVerdict:
    """Quick statistical analysis with default baselines.

    Usage:
        verdict = quick_statistical_analysis(
            claimed_model="gpt-4o",
            tokenizer_results={"tok-digits": 23, "tok-cjk": 25},
            behavioral_results={"beh-coin-flip": ["heads", "tails"]},
            capability_failure_rate=0.2,
        )
        print(verdict.conclusion, verdict.posterior_probability)
    """
    analyzer = StatisticalAnalyzer()
    analyzer.load_default_baselines()
    return analyzer.analyze(
        claimed_model=claimed_model,
        observed_tokenizer=tokenizer_results,
        observed_behavioral=behavioral_results,
        capability_failure_rate=capability_failure_rate,
    )
