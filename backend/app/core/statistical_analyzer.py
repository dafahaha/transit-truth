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
import re
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
    # Sample sizes (for uncertainty quantification)
    baseline_sample_size: int = 0
    observed_sample_size: int = 0
    # Sample adequacy warning
    sample_adequacy: str = "unknown"  # "sufficient", "moderate", "insufficient"
    sample_warning: Optional[str] = None
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

    def load_real_baselines(self, data_dir: str | None = None):
        """Load real baseline data from JSON files collected from actual APIs.

        Replaces synthetic baselines with empirically collected data.
        Each JSON file follows the format produced by collect_baseline.py.

        Args:
            data_dir: Directory containing baseline JSON files
        """
        import json
        from pathlib import Path

        if data_dir is None:
            # Resolve relative to the repo root (this file lives at
            # backend/app/core/statistical_analyzer.py -> 4 parents up = repo root).
            repo_root = Path(__file__).resolve().parents[3]
            candidates = [
                Path("data/baselines"),
                repo_root / "data" / "baselines",
                Path("../data/baselines"),
            ]
            baseline_path = next((p for p in candidates if p.exists()), candidates[1])
        else:
            baseline_path = Path(data_dir)
        if not baseline_path.exists():
            print(f"Warning: baseline directory {baseline_path} not found, keeping synthetic baselines")
            return

        loaded = 0
        # Remember which keys came from synthetic defaults (if any). After a
        # successful real load we will drop synthetic placeholders that are
        # NOT backed by a real file, so a claim like "gpt-4" can never silently
        # fall back to the n=10 synthetic distribution.
        synthetic_keys = set(self.baseline_db.keys())
        real_keys: set[str] = set()
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
                real_keys.add(model_name)
                # Also add common aliases
                if "gpt-4o-mini" in model_name:
                    self.baseline_db["gpt-4o-mini"] = baseline
                    real_keys.add("gpt-4o-mini")
                loaded += 1
                n_tok = len(tokenizer_dist)
                n_beh = len(behavioral_dist)
                print(f"  Loaded real baseline: {model_name} (n={baseline.sample_size}, {n_tok} tokenizer, {n_beh} behavioral probes)")

            except Exception as e:
                print(f"  Error loading {json_file.name}: {e}")

        if loaded > 0:
            # Drop synthetic-only placeholders that no real file overwrote
            # (e.g. the synthetic "gpt-4" alias of the old demo gpt4). A real
            # audit must compare against real data or be honestly inconclusive,
            # never against a tiny fabricated distribution.
            for k in list(synthetic_keys):
                if k not in real_keys:
                    self.baseline_db.pop(k, None)
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
        # Normalize each probe to z-scores using the probe's own baseline
        # mean/std, then run a *two-sample* KS between observed z-scores and
        # the empirical z-score distribution of the baseline samples. This
        # avoids misspecifying the reference as a standard normal when the
        # baseline itself is small (where the true reference is the empirical
        # baseline CDF, not N(0,1)).
        observed_z: list[float] = []
        baseline_z: list[float] = []

        for probe_id, observed_count in observed.items():
            if probe_id not in baseline.tokenizer_distributions:
                continue
            baseline_vals = baseline.tokenizer_distributions[probe_id]
            if len(baseline_vals) < 2:
                continue
            mean = statistics.mean(baseline_vals)
            std = statistics.stdev(baseline_vals)
            if std == 0:
                # Zero-variance baseline: cannot normalize; skip rather than
                # silently dividing by 1.0 and masking the anomaly.
                continue
            observed_z.append((observed_count - mean) / std)
            for v in baseline_vals:
                baseline_z.append((v - mean) / std)

        if len(observed_z) < 2 or len(baseline_z) < 2:
            return 0.0, 1.0  # insufficient data

        # Two-sample KS against the empirical baseline CDF.
        ks_stat, p_value = stats.ks_2samp(observed_z, baseline_z)
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
        total_df = 0

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

            # Include BOTH directions in the test and in df:
            #   - baseline-only categories (observed count = 0): kept.
            #   - observed-only categories (baseline count = 0): a response the
            #     baseline NEVER produced is strong mismatch evidence and must
            #     NOT be silently dropped. We keep the plain empirical expected
            #     for categories the baseline actually observed (so an exact
            #     resubstitution still yields chi2 ~ 0), and only apply a small
            #     Jeffreys-style floor expected for never-seen categories so the
            #     cell contributes without dividing by zero.
            alpha = 0.5
            k_cats = len(all_categories)
            probe_chi2 = 0.0
            probe_cells = 0
            for cat in all_categories:
                bc = baseline_counts.get(cat, 0)
                actual = observed_counts.get(cat, 0)
                if bc > 0:
                    expected = (bc / n_baseline) * n_observed
                else:
                    # baseline count == 0 -> novel response; floor expected.
                    expected = (alpha / (n_baseline + alpha * k_cats)) * n_observed
                probe_chi2 += (actual - expected) ** 2 / expected
                probe_cells += 1

            # Per-probe goodness-of-fit df = (number of union categories) - 1.
            # Pool across probes by summing (k_i - 1), not (sum k_i - 1)
            # (the latter over-counts df by n_probes - 1).
            if probe_cells >= 2:
                chi2_sum += probe_chi2
                total_df += probe_cells - 1

            total_observed += n_observed
            total_expected += n_baseline

        if total_df < 1:
            return 0.0, 1.0

        # p-value from chi-square distribution
        p_value = float(1 - stats.chi2.cdf(chi2_sum, total_df))
        return float(chi2_sum), p_value

    @staticmethod
    def _normalize_model_name(name: str) -> str:
        """Lower-case and strip version/date suffixes for exact baseline lookup."""
        n = name.strip().lower()
        # Strip OpenAI-style date suffixes: -2024-08-06 or -20240806
        n = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", n)
        n = re.sub(r"-\d{8}$", "", n)
        return n.strip()

    def bayesian_update(self, prior: float, likelihood_ratio: float,
                        observed_size: int = 0, baseline_size: int = 0
                        ) -> tuple[float, float, float]:
        """Bayesian update for model verification.

        Args:
            prior: P(honest) before evidence
            likelihood_ratio: P(evidence|honest) / P(evidence|dishonest).
                Non-positive LR is treated as strong evidence against honest.
            observed_size: number of observed samples (drives CI width)
            baseline_size: number of baseline samples (drives CI width)

        Returns:
            (posterior, ci_lower, ci_upper) - 95% credible interval
        """
        # Clamp prior into (0, 1) to avoid log(0).
        prior = min(max(prior, 1e-6), 1 - 1e-6)

        # Work in log-odds space to avoid overflow when LR is huge.
        log_prior_odds = math.log(prior / (1 - prior))

        if not math.isfinite(likelihood_ratio) or likelihood_ratio <= 0:
            # LR=0 / negative / NaN / inf: evidence that the model is NOT as
            # claimed. Map -inf log-odds -> posterior 0; +inf -> posterior 1.
            if math.isnan(likelihood_ratio):
                log_lr = 0.0  # undefined evidence: no update
            elif likelihood_ratio <= 0:
                log_lr = -math.log(1e6)  # strong against, but finite
            else:
                log_lr = math.log(1e6)  # +inf: strong for, but finite
        else:
            log_lr = math.log(likelihood_ratio)

        log_post_odds = log_prior_odds + log_lr
        # Sigmoid, guarded against overflow.
        if log_post_odds >= 0:
            posterior = 1.0 / (1.0 + math.exp(-log_post_odds))
        else:
            exp_v = math.exp(log_post_odds)
            posterior = exp_v / (1.0 + exp_v)
        posterior = min(max(posterior, 0.0), 1.0)

        # Credible interval width scales with the *effective* sample size, so
        # that a 5-sample audit gets a wide interval and a 500-sample audit
        # gets a narrow one. Use a Beta(posterior * N, (1-posterior) * N)
        # where N = observed_size + baseline_size.
        n_eff = max(int(observed_size) + int(baseline_size), 1)
        alpha = posterior * n_eff
        beta_param = (1 - posterior) * n_eff

        if alpha > 1e-6 and beta_param > 1e-6:
            ci_lower = float(stats.beta.ppf(0.025, alpha, beta_param))
            ci_upper = float(stats.beta.ppf(0.975, alpha, beta_param))
        else:
            # Extreme posterior with very few samples: still leave a wide CI.
            ci_lower = 0.0
            ci_upper = 1.0

        return posterior, ci_lower, ci_upper

    def calculate_likelihood_ratio(self, ks_pvalue: float,
                                     chi2_pvalue: float,
                                     capability_failure_rate: float) -> float:
        """Calculate likelihood ratio from test results.

        P(evidence|honest) / P(evidence|dishonest)

        Semantics (asymmetric on purpose):
        - Tokenizer/KS is a *cross-family* signal only. For two same-family
          endpoints (e.g. gpt-4o vs gpt-4o-mini) the tokenizer is identical
          by design, so a *high* KS p-value (tokenizer consistent) is the
          EXPECTED, NEUTRAL situation -> factor = 1.0, NEVER > 1. Only a LOW
          KS p-value (tokenizer that does not match the claimed baseline at
          all) counts as reverse evidence of a different family (factor < 1).
          This prevents a same-family downgrade from being washed out by a
          spurious "tokenizer looks fine -> honest x2".
        - Behavioral chi-square is the PRIMARY same-family fingerprint signal
          and may go both ways: low p = mismatch (<1), high p = match (>1).
        - High capability failure rate suggests downgrade (<1).
        """
        lr = 1.0

        # --- Tokenizer / KS: asymmetric, factor in (0, 1] only ---
        # Consistency = neutral (same-family tokenizer is expected).
        # Inconsistency = evidence of a different (cheaper) family.
        if ks_pvalue < 0.01:
            lr *= 0.2  # tokenizer strongly off-family -> against honest
        elif ks_pvalue < 0.05:
            lr *= 0.5
        elif ks_pvalue < 0.1:
            lr *= 0.8
        # else: consistent -> factor 1.0 (NEUTRAL, never rewards)

        # --- Behavioral chi-square: PRIMARY same-family fingerprint ---
        if chi2_pvalue < 0.01:
            lr *= 0.05  # distribution strongly off baseline -> downgrade
        elif chi2_pvalue < 0.05:
            lr *= 0.3
        elif chi2_pvalue < 0.1:
            lr *= 0.7
        elif chi2_pvalue > 0.5:
            lr *= 3.0   # strong behavioral fingerprint match -> honest
        elif chi2_pvalue > 0.2:
            lr *= 1.3

        # --- Capability failure rate ---
        if capability_failure_rate > 0.7:
            lr *= 0.1  # almost certainly downgraded
        elif capability_failure_rate > 0.5:
            lr *= 0.3
        elif capability_failure_rate > 0.3:
            lr *= 0.6
        elif capability_failure_rate < 0.1:
            lr *= 1.5

        return lr

    def _resolve_baseline(self, claimed_model: str):
        """Return the BaselineDistribution for the claimed model, or None.

        Matching rules (in order):
          1. Exact normalized id match (case-insensitive, date-suffix stripped).
          2. Exact match after stripping OpenAI date suffixes (-YYYY-MM-DD).
        No substring / fuzzy containment: a mini variant must never be
        compared against a non-mini baseline.
        """
        norm = self._normalize_model_name(claimed_model)
        # Build normalized lookup once.
        norm_db = {self._normalize_model_name(k): v for k, v in self.baseline_db.items()}
        return norm_db.get(norm)

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
        # Find matching baseline by exact normalized model id. We deliberately
        # do NOT use substring containment: "gpt-4o-mini" must never match the
        # "gpt-4o" baseline just because "gpt-4o" is a substring.
        baseline = self._resolve_baseline(claimed_model)

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
        observed_size = sum(len(responses) for responses in observed_behavioral.values())
        posterior, ci_lower, ci_upper = self.bayesian_update(
            self.prior_honest, lr,
            observed_size=observed_size,
            baseline_size=baseline.sample_size,
        )

        # Assess sample adequacy
        sample_adequacy, sample_warning = assess_sample_adequacy(
            baseline_size=baseline.sample_size,
            observed_size=observed_size,
        )

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

        # If sample is insufficient, downgrade confidence
        if sample_adequacy == "insufficient" and confidence_level == "high":
            confidence_level = "medium"
        elif sample_adequacy == "insufficient" and confidence_level == "medium":
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
            baseline_sample_size=baseline.sample_size,
            observed_sample_size=observed_size,
            sample_adequacy=sample_adequacy,
            sample_warning=sample_warning,
            conclusion=conclusion,
            confidence_level=confidence_level,
            details={
                "baseline_model": baseline.model_name,
                "baseline_sample_size": baseline.sample_size,
                "observed_sample_size": observed_size,
                "sample_adequacy": sample_adequacy,
                "sample_warning": sample_warning,
                "likelihood_ratio": lr,
                "prior_honest": self.prior_honest,
                "ks_interpretation": self._interpret_pvalue(ks_pvalue),
                "chi2_interpretation": self._interpret_pvalue(chi2_pvalue),
                "posterior_95ci": [round(ci_lower, 3), round(ci_upper, 3)],
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

    def estimate_false_positive_rate(self, alpha: float = 0.05,
                                       n_tests: int = 2) -> float:
        """Estimate false positive rate for the test battery.

        Probability of flagging an honest relay as suspicious,
        assuming independent tests with significance level alpha.

        FPR = 1 - (1 - alpha)^n_tests (at least one false positive).
        The battery has n_tests=2 independent significance tests (KS + chi2).
        (The previous `n_probes` parameter was ignored/misleading and removed;
        the probe count does not change the number of hypothesis tests.)
        """
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


# ─── Wilson Score Interval (比例置信区间) ───────────────────────────
def wilson_score_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """
    Wilson Score Interval - 计算比例的置信区间

    比正态近似更准确，特别适合小样本或极端比例（接近0或1）。

    参数：
    - successes: 成功次数
    - n: 总样本数
    - confidence: 置信水平（默认0.95）

    返回：
    - (lower, upper): 置信区间下界和上界

    参考：https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval
    """
    import math

    if n == 0:
        return (0.0, 1.0)

    # z-score for confidence level
    z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_scores.get(confidence, 1.96)

    p_hat = successes / n
    denominator = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denominator

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return (lower, upper)


def assess_sample_adequacy(
    baseline_size: int,
    observed_size: int,
    min_baseline: int = 100,
    min_observed: int = 10,
) -> tuple[str, Optional[str]]:
    """
    评估样本量是否足够

    参数：
    - baseline_size: 基准数据样本量
    - observed_size: 观测数据样本量
    - min_baseline: 基准数据最小样本量（默认100）
    - min_observed: 观测数据最小样本量（默认10）

    返回：
    - (adequacy, warning): 样本充足程度和警告信息
      adequacy: "sufficient" | "moderate" | "insufficient"
    """
    warnings = []

    # 评估基准样本量
    if baseline_size >= 200:
        baseline_status = "good"
    elif baseline_size >= 100:
        baseline_status = "moderate"
        warnings.append(f"基准样本量({baseline_size})偏少，建议增加到200+以提高统计准确性")
    elif baseline_size >= 50:
        baseline_status = "low"
        warnings.append(f"基准样本量({baseline_size})不足，95%置信区间约±14%，结论可能不稳定")
    else:
        baseline_status = "insufficient"
        warnings.append(f"基准样本量({baseline_size})严重不足，结论不可靠，建议至少50样本")

    # 评估观测样本量
    if observed_size >= 20:
        observed_status = "good"
    elif observed_size >= 10:
        observed_status = "moderate"
        warnings.append(f"观测样本量({observed_size})偏少，建议增加到20+")
    else:
        observed_status = "low"
        warnings.append(f"观测样本量({observed_size})不足，建议至少10样本")

    # 综合评估
    if baseline_status == "good" and observed_status == "good":
        adequacy = "sufficient"
    elif baseline_status in ("good", "moderate") and observed_status in ("good", "moderate"):
        adequacy = "moderate"
    else:
        adequacy = "insufficient"

    warning = "；".join(warnings) if warnings else None

    return (adequacy, warning)
