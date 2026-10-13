"""Deterministic tests for the budgeted epsilon-dilution sequential analysis."""

from __future__ import annotations

import math

from app.verify.sequential import (
    budgeted_sequential_analysis,
    detection_power,
    required_samples,
)


def test_full_dilution_always_detected():
    # epsilon=1 (every request is fake) -> power 1.
    assert detection_power(1.0, 1) == 1.0
    assert detection_power(1.0, 100) == 1.0


def test_zero_dilution_never_detected():
    assert detection_power(0.0, 10000) == 0.0
    assert required_samples(0.0, 0.95) is None


def test_half_dilution_needs_five_for_95pct():
    # 1 - (1-0.5)^n >= 0.95  -> (0.5)^n <= 0.05 -> n >= ceil(log2(20)) = 5
    assert required_samples(0.5, 0.95) == 5
    assert detection_power(0.5, 4) < 0.95
    assert detection_power(0.5, 5) >= 0.95


def test_one_percent_dilution_needs_many():
    # 1 - 0.99^n >= 0.95 -> n ~= ln(0.05)/ln(0.99) ~= 298.
    n = required_samples(0.01, 0.95)
    assert n == math.ceil(math.log(0.05) / math.log(0.99))
    assert detection_power(0.01, n - 1) < 0.95
    assert detection_power(0.01, n) >= 0.95


def test_detectability_scales_effective_rate():
    # Only half the fake requests are recognizable -> needs ~2x budget.
    full = required_samples(0.1, 0.95, detectability=1.0)
    half = required_samples(0.1, 0.95, detectability=0.5)
    assert half > full


def test_budget_report_shape():
    rep = budgeted_sequential_analysis(epsilon=0.1, budget=100, target_power=0.95)
    assert rep["epsilon"] == 0.1
    assert rep["budget"] == 100
    assert 0.0 <= rep["detection_power_in_budget"] <= 1.0
    assert rep["expected_fake_requests"] == 10.0
    assert "interpretation" in rep
