"""Test that real baseline JSON files load correctly from the repo root."""
from app.core.statistical_analyzer import StatisticalAnalyzer


class TestRealBaselines:
    def test_load_real_baselines_finds_gpt4o_mini(self):
        an = StatisticalAnalyzer()
        an.load_real_baselines()
        # The loader adds an explicit "gpt-4o-mini" alias when the file name
        # contains "gpt-4o-mini".
        assert "gpt-4o-mini" in an.baseline_db, (
            f"Expected gpt-4o-mini baseline, got keys: {list(an.baseline_db.keys())}"
        )
        bl = an.baseline_db["gpt-4o-mini"]
        assert bl.sample_size > 0
        assert len(bl.behavioral_distributions) > 0

    def test_gpt4o_mini_resolves_to_its_own_baseline(self):
        an = StatisticalAnalyzer()
        an.load_real_baselines()
        bl = an._resolve_baseline("gpt-4o-mini")
        assert bl is not None
        assert bl.model_name == "gpt-4o-mini"

    def test_gpt4o_does_not_share_mini_baseline(self):
        an = StatisticalAnalyzer()
        an.load_real_baselines()
        mini = an._resolve_baseline("gpt-4o-mini")
        full = an._resolve_baseline("gpt-4o")
        assert mini is not None and full is not None
        assert mini.model_name != full.model_name or mini is not full
