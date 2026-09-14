"""Tests for randomized probe generation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.randomized_probes import (
    ProbeRandomizer,
    generate_randomized_probes,
    RandomizedProbe,
)
from app.core.probes import TOKENIZER_PROBES, BEHAVIORAL_PROBES, CAPABILITY_PROBES


class TestProbeRandomizer:
    """Test probe randomization."""

    def test_generate_with_seed(self):
        probes, seed = generate_randomized_probes(seed=42)
        assert seed == 42
        assert len(probes) == len(TOKENIZER_PROBES) + len(BEHAVIORAL_PROBES) + len(CAPABILITY_PROBES)

    def test_generate_without_seed(self):
        probes, seed = generate_randomized_probes()
        assert isinstance(seed, int)
        assert seed > 0
        assert len(probes) > 0

    def test_same_seed_produces_same_probes(self):
        probes1, _ = generate_randomized_probes(seed=42)
        probes2, _ = generate_randomized_probes(seed=42)
        for p1, p2 in zip(probes1, probes2):
            assert p1.prompt == p2.prompt

    def test_different_seeds_produce_different_probes(self):
        probes1, _ = generate_randomized_probes(seed=42)
        probes2, _ = generate_randomized_probes(seed=123)
        # At least some probes should be different
        differences = sum(1 for p1, p2 in zip(probes1, probes2) if p1.prompt != p2.prompt)
        assert differences > 0, "Different seeds should produce different probes"

    def test_randomized_probes_preserve_category(self):
        probes, _ = generate_randomized_probes(seed=42)
        tokenizer_count = sum(1 for p in probes if p.category == "tokenizer")
        behavioral_count = sum(1 for p in probes if p.category == "behavioral")
        capability_count = sum(1 for p in probes if p.category == "capability")
        assert tokenizer_count == len(TOKENIZER_PROBES)
        assert behavioral_count == len(BEHAVIORAL_PROBES)
        assert capability_count == len(CAPABILITY_PROBES)

    def test_randomized_probes_have_original_id(self):
        probes, _ = generate_randomized_probes(seed=42)
        for probe in probes:
            assert isinstance(probe, RandomizedProbe)
            assert probe.original_id, "Must track original probe ID"
            assert probe.random_seed == 42

    def test_tokenizer_probes_preserve_character_type(self):
        """Tokenizer probes should preserve their characteristic content type."""
        randomizer = ProbeRandomizer(seed=42)
        probe = next(p for p in TOKENIZER_PROBES if p.id == "tok-digits")
        randomized = randomizer._randomize_tokenizer_probe("tok-digits")
        # Should contain mostly digits
        digit_part = randomized.split("exactly: ")[-1]
        digit_count = sum(1 for c in digit_part if c.isdigit())
        assert digit_count > len(digit_part) * 0.8, "Digit probe should contain mostly digits"

    def test_behavioral_probes_preserve_question_type(self):
        """Behavioral probes should preserve the type of question."""
        randomizer = ProbeRandomizer(seed=42)
        prompt = randomizer._randomize_behavioral_probe("beh-random-100")
        assert "100" in prompt or "one hundred" in prompt.lower()
        assert "number" in prompt.lower()

    def test_capability_probes_randomize_numbers(self):
        """Capability math probes should randomize the numbers."""
        randomizer = ProbeRandomizer(seed=42)
        prompt1, expected1 = randomizer._randomize_capability_probe("cap-simple-math")
        prompt2, expected2 = randomizer._randomize_capability_probe("cap-simple-math")
        # Different randomization should produce different numbers
        assert prompt1 != prompt2 or expected1 != expected2
