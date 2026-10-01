"""Regression tests for statistical correctness (post Round-1 review fixes)."""
import math
import pytest

from app.core.statistical_analyzer import (
    StatisticalAnalyzer,
    BaselineDistribution,
    wilson_score_interval,
)


class TestBaselineResolution:
    def test_mini_does_not_match_4o(self):
        an = StatisticalAnalyzer()
        an.load_default_baselines()
        # gpt-4o-mini is NOT in the default synthetic db; must not silently
        # resolve to the gpt-4o baseline just because "gpt-4o" is a substring.
        assert an._resolve_baseline("gpt-4o-mini") is None

    def test_gpt4o_with_date_suffix_matches_4o(self):
        an = StatisticalAnalyzer()
        an.load_default_baselines()
        bl = an._resolve_baseline("gpt-4o-2024-08-06")
        assert bl is not None
        assert bl.model_name == "gpt-4o"

    def test_exact_match(self):
        an = StatisticalAnalyzer()
        an.load_default_baselines()
        assert an._resolve_baseline("gpt-3.5-turbo").model_name == "gpt-3.5-turbo"
        assert an._resolve_baseline("CLAUDE-3-5-SONNET").model_name == "claude-3-5-sonnet"


class TestBayesBoundaries:
    def setup_method(self):
        self.an = StatisticalAnalyzer()

    def test_inf_lr_gives_posterior_one(self):
        p, lo, hi = self.an.bayesian_update(0.7, float("inf"), 5, 10)
        assert p == pytest.approx(1.0, abs=1e-6)
        assert 0 <= lo <= 1 and 0 <= hi <= 1

    def test_zero_lr_gives_posterior_zero(self):
        p, lo, hi = self.an.bayesian_update(0.7, 0.0, 5, 10)
        assert p < 1e-3
        assert 0 <= lo <= 1 and 0 <= hi <= 1

    def test_negative_lr_clamped(self):
        p, lo, hi = self.an.bayesian_update(0.7, -1.0, 5, 10)
        assert 0.0 <= p <= 1.0
        assert not math.isnan(p)

    def test_nan_lr_no_update(self):
        p, _, _ = self.an.bayesian_update(0.7, float("nan"), 5, 10)
        assert p == pytest.approx(0.7, abs=1e-6)

    def test_posterior_always_in_unit_interval(self):
        for lr in [1.0, 0.0, -5.0, float("inf"), 1e9, 1e-9]:
            p, lo, hi = self.an.bayesian_update(0.5, lr, 3, 7)
            assert 0.0 <= p <= 1.0
            assert 0.0 <= lo <= 1.0
            assert 0.0 <= hi <= 1.0

    def test_ci_width_shrinks_with_sample_size(self):
        _, lo_small, hi_small = self.an.bayesian_update(0.7, 10.0, 2, 10)
        _, lo_large, hi_large = self.an.bayesian_update(0.7, 10.0, 200, 200)
        width_small = hi_small - lo_small
        width_large = hi_large - lo_large
        assert width_large < width_small


class TestChi2Dof:
    def setup_method(self):
        self.an = StatisticalAnalyzer()
        self.bl = BaselineDistribution(
            model_family="x", model_name="x",
            behavioral_distributions={
                "beh-a": ["heads"] * 6 + ["tails"] * 4,
                "beh-b": ["up"] * 8 + ["down"] * 2,
            },
        )

    def test_matching_distribution_p_near_one(self):
        s, p = self.an.chi2_test_behavioral(
            {"beh-a": ["heads"] * 6 + ["tails"] * 4,
             "beh-b": ["up"] * 8 + ["down"] * 2},
            self.bl,
        )
        assert s == pytest.approx(0.0, abs=1e-9)
        assert p > 0.99

    def test_divergent_distribution_significant(self):
        s, p = self.an.chi2_test_behavioral(
            {"beh-a": ["heads"] * 10, "beh-b": ["down"] * 10},
            self.bl,
        )
        assert p < 0.01

    def test_single_probe_matches_chi2_reference(self):
        # One probe, 2 categories -> df = 1. Statistic should match chi2 cdf.
        bl = BaselineDistribution(model_family="x", model_name="x",
            behavioral_distributions={"beh-a": ["heads"] * 5 + ["tails"] * 5})
        s, p = self.an.chi2_test_behavioral(
            {"beh-a": ["heads"] * 9 + ["tails"] * 1}, bl)
        # Expected: heads=5, tails=5; observed 9/10 vs 1/10 -> chi2=6.4, df=1
        assert s == pytest.approx(6.4, abs=0.01)


class TestEntropy:
    def test_entropy_is_shannon(self):
        # Import via fingerprint to check the formula is now -sum p ln p.
        from app.core.fingerprint import ModelFingerprinter
        from app.core.statistical_analyzer import StatisticalAnalyzer
        fp = ModelFingerprinter.__new__(ModelFingerprinter)
        fp.behavioral_results = {"beh-x": ["a", "a", "a", "a", "b"]}
        fp.stat_analyzer = StatisticalAnalyzer()
        fp.model = "unknown-model"
        sig = fp._analyze_behavioral()
        # 4/5 a, 1/5 b -> entropy = -(0.8 ln0.8 + 0.2 ln0.2) ~= 0.5004 nats
        assert sig["signatures"]["beh-x"]["entropy_nats"] == pytest.approx(0.5004, abs=0.01)


class TestKsTwoSample:
    def test_matching_observations_not_significant(self):
        an = StatisticalAnalyzer()
        bl = BaselineDistribution(model_family="x", model_name="x",
            tokenizer_distributions={"a": [22, 23, 22, 24, 23],
                                     "b": [50, 51, 50, 52, 51]})
        s, p = an.ks_test_tokenizer({"a": 23, "b": 51}, bl)
        assert p > 0.2

    def test_far_observations_significant(self):
        an = StatisticalAnalyzer()
        bl = BaselineDistribution(model_family="x", model_name="x",
            tokenizer_distributions={"a": [22, 23, 22, 24, 23],
                                     "b": [50, 51, 50, 52, 51]})
        s, p = an.ks_test_tokenizer({"a": 100, "b": 200}, bl)
        assert p < 0.05


# ─── Round-2 fix regressions ──────────────────────────────────────────
class TestFusionAsymmetry:
    """P1-1: tokenizer-consistent is NEUTRAL (factor 1, never >1); behavioral
    chi2 is the primary signal. A same-family downgrade must alarm, a true
    same-model resubstitution must not false-alarm."""

    def _obs(self, bl):
        import statistics
        beh = {pid: list(v) for pid, v in bl.behavioral_distributions.items()}
        tok = {pid: statistics.mean(v) for pid, v in bl.tokenizer_distributions.items()}
        return tok, beh

    def test_mini_observed_claiming_4o_alarms(self):
        an = StatisticalAnalyzer()
        an.load_real_baselines()
        mini = an._resolve_baseline("gpt-4o-mini")
        tok, beh = self._obs(mini)
        v = an.analyze("gpt-4o", tok, beh, 0.0)
        # tokenizer is identical across the family -> ks_p high, but it must
        # NOT push posterior up. Behavioral chi2 strongly rejects -> mismatch.
        assert v.conclusion == "mismatch", f"got {v.conclusion}, posterior={v.posterior_probability}"
        assert v.posterior_probability < 0.3
        assert v.posterior_ci_upper < 0.5

    def test_true_4o_resubstitution_no_false_alarm(self):
        an = StatisticalAnalyzer()
        an.load_real_baselines()
        full = an._resolve_baseline("gpt-4o")
        tok, beh = self._obs(full)
        v = an.analyze("gpt-4o", tok, beh, 0.0)
        assert v.conclusion == "match", f"got {v.conclusion}, posterior={v.posterior_probability}"
        assert v.posterior_probability > 0.8

    def test_tokenizer_consistent_factor_never_rewards(self):
        # Direct unit check: ks_pvalue high (tokenizer consistent) must leave
        # the LR unchanged relative to a neutral baseline; only chi2 moves it.
        an = StatisticalAnalyzer()
        # neutral chi2 p=0.2 (no behavioral evidence), capability=0
        lr_consistent = an.calculate_likelihood_ratio(ks_pvalue=0.9, chi2_pvalue=0.2,
                                                      capability_failure_rate=0.0)
        # tokenizer consistent contributes factor 1.0; capability<0.1 -> 1.5
        assert lr_consistent == pytest.approx(1.5, abs=1e-9)
        # tokenizer INCONSISTENT (off-family) pulls LR below 1
        lr_off = an.calculate_likelihood_ratio(ks_pvalue=0.001, chi2_pvalue=0.2,
                                               capability_failure_rate=0.0)
        assert lr_off < 1.0


class TestSyntheticPurge:
    """P2-2: after loading real baselines, the n=10 synthetic 'gpt-4' alias
    must not survive to be matched against a real audit."""

    def test_gpt4_alias_not_synthetic_after_real_load(self):
        an = StatisticalAnalyzer()
        an.load_default_baselines()      # creates synthetic "gpt-4" (n=10)
        an.load_real_baselines()         # loads real gpt-4o / gpt-4o-mini
        g4 = an._resolve_baseline("gpt-4")
        # Either gone, or backed by a real (n>10) distribution -- never the n=10 placeholder.
        assert g4 is None or g4.sample_size > 10, f"gpt-4 still resolves to n={g4.sample_size} synthetic"


class TestChi2NovelCategory:
    """P2-3: observed-only categories (baseline count 0) must contribute."""

    def test_novel_response_category_counted(self):
        an = StatisticalAnalyzer()
        bl = BaselineDistribution(model_family="x", model_name="x",
            behavioral_distributions={"beh-a": ["heads"] * 8 + ["tails"] * 2})
        # observed emits a category the baseline never produced
        s, p = an.chi2_test_behavioral({"beh-a": ["okapi"] * 10}, bl)
        assert s > 0.0, "novel category was dropped (expected>0 check)"
        assert p < 0.05
