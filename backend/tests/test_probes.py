"""Tests for probe definitions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.probes import (
    TOKENIZER_PROBES,
    BEHAVIORAL_PROBES,
    CAPABILITY_PROBES,
    get_all_probes,
    get_probes_by_category,
    Probe,
)


class TestProbeDefinitions:
    """Test that probe sets are properly defined."""

    def test_tokenizer_probes_not_empty(self):
        assert len(TOKENIZER_PROBES) > 0

    def test_behavioral_probes_not_empty(self):
        assert len(BEHAVIORAL_PROBES) > 0

    def test_capability_probes_not_empty(self):
        assert len(CAPABILITY_PROBES) > 0

    def test_all_probes_have_required_fields(self):
        for probe in get_all_probes():
            assert isinstance(probe, Probe)
            assert probe.id, "Probe must have an id"
            assert probe.category in ("tokenizer", "behavioral", "capability")
            assert probe.prompt, "Probe must have a prompt"
            assert probe.max_tokens > 0
            assert 0 <= probe.temperature <= 2

    def test_tokenizer_probes_have_expected_range(self):
        for probe in TOKENIZER_PROBES:
            assert probe.expected_tokens_range is not None
            lo, hi = probe.expected_tokens_range
            assert lo > 0 and hi > lo

    def test_behavioral_probes_high_temperature(self):
        for probe in BEHAVIORAL_PROBES:
            assert probe.temperature >= 0.5, "Behavioral probes should use high temperature for randomness"

    def test_capability_probes_low_temperature(self):
        for probe in CAPABILITY_PROBES:
            assert probe.temperature <= 0.1, "Capability probes should use low temperature for determinism"

    def test_get_all_probes_count(self):
        all_probes = get_all_probes()
        assert len(all_probes) == len(TOKENIZER_PROBES) + len(BEHAVIORAL_PROBES) + len(CAPABILITY_PROBES)

    def test_get_probes_by_category(self):
        assert len(get_probes_by_category("tokenizer")) == len(TOKENIZER_PROBES)
        assert len(get_probes_by_category("behavioral")) == len(BEHAVIORAL_PROBES)
        assert len(get_probes_by_category("capability")) == len(CAPABILITY_PROBES)
        assert get_probes_by_category("nonexistent") == []

    def test_probe_ids_unique(self):
        all_ids = [p.id for p in get_all_probes()]
        assert len(all_ids) == len(set(all_ids)), "Probe IDs must be unique"
