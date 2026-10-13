"""Budgeted sequential testing for epsilon-dilution deception.

A relay may not fully swap the model: it may route only a fraction ``epsilon`` of
requests to a cheaper ("fake") model, passing the rest through honestly
(``epsilon``-dilution, a.k.a. partial downgrade). A single one-shot probe can
easily miss this. This module gives a deterministic, budget-aware statement of
*what can be detected* within a request budget.

Model (deliberately simple and auditable):

- Each probe request is routed to the fake model independently with probability
  ``epsilon``.
- A routed-to-fake request reveals itself with per-request ``detectability``
  (1.0 for a perfectly discriminative fingerprint probe; <1 if the probe can
  miss a fake sample).
- Effective per-request anomaly probability ``p = epsilon * detectability``.
- With ``n`` requests, the probability of observing at least one revealing fake
  response is ``1 - (1 - p) ** n``.

These are closed-form binomial approximations, not a replacement for the
Bayesian comparison in :mod:`app.core.statistical_analyzer`; they answer the
operator's upfront question: "within my budget, can I even hope to detect an
epsilon-diluted relay?"
"""

from __future__ import annotations

import math
from typing import Optional


def detection_power(
    epsilon: float, n_requests: int, detectability: float = 1.0
) -> float:
    """Probability of seeing >=1 revealing fake response within ``n_requests``.

    Args:
        epsilon: fraction of requests routed to the fake model (0..1).
        n_requests: total probe budget.
        detectability: per fake request the probability the probe flags it.
    """
    epsilon = min(max(epsilon, 0.0), 1.0)
    p = epsilon * min(max(detectability, 0.0), 1.0)
    if n_requests <= 0:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return 1.0 - (1.0 - p) ** n_requests


def required_samples(
    epsilon: float, target_power: float = 0.95, detectability: float = 1.0
) -> Optional[int]:
    """Minimum request budget to achieve ``target_power`` of detection.

    Returns ``None`` when epsilon is 0 (impossible to detect by construction).
    """
    p = epsilon * min(max(detectability, 0.0), 1.0)
    if p <= 0.0:
        return None
    if p >= 1.0:
        return 1
    # Solve 1 - (1-p)^n >= target_power  ->  (1-p)^n <= 1-target_power
    n = math.log(1.0 - target_power) / math.log(1.0 - p)
    return max(1, math.ceil(n))


def budgeted_sequential_analysis(
    epsilon: float,
    budget: int,
    target_power: float = 0.95,
    detectability: float = 1.0,
) -> dict:
    """Full budgeted sequential report for a given dilution and budget."""
    power = detection_power(epsilon, budget, detectability)
    needed = required_samples(epsilon, target_power, detectability)
    return {
        "epsilon": epsilon,
        "budget": budget,
        "detectability": detectability,
        "expected_fake_requests": round(epsilon * budget, 3),
        "detection_power_in_budget": round(power, 4),
        "target_power": target_power,
        "required_samples_for_target_power": needed,
        "budget_adequate": power >= target_power,
        "interpretation": (
            f"Within {budget} requests, an epsilon={epsilon:.3f} diluted relay is "
            f"detected with ~{power:.1%} probability."
            + (
                f" This meets the {target_power:.0%} target."
                if power >= target_power
                else f" It does NOT meet the {target_power:.0%} target; "
                f"plan for ~{needed} requests."
            )
        ),
    }
