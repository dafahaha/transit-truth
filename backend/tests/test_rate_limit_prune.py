"""P3-2 regression: stale per-IP rate-limit buckets are pruned instead of
accumulating for the life of the process.

Fixed-window semantics (boundary ~2x burst) are documented in
``app/utils/rate_limit.py``; these tests pin the stale-key sweep /
``prune_expired`` hygiene so a long-running process cannot grow ``_windows``
without bound.
"""

from __future__ import annotations

import time

from app.utils import rate_limit


def test_prune_expired_removes_stale_buckets_and_keeps_active():
    # Tiny window so buckets expire almost immediately.
    rate_limit.configure(5, 0.05)
    try:
        assert rate_limit._check("10.0.0.1")
        assert rate_limit._check("10.0.0.2")
        assert len(rate_limit._windows) == 2

        # Let both windows fully elapse.
        time.sleep(0.1)
        # A brand-new bucket created after the elapse must survive pruning.
        assert rate_limit._check("10.0.0.3")

        removed = rate_limit.prune_expired()
        assert removed == 2, f"expected 2 stale buckets removed, got {removed}"
        assert "10.0.0.1" not in rate_limit._windows
        assert "10.0.0.2" not in rate_limit._windows
        assert "10.0.0.3" in rate_limit._windows
    finally:
        rate_limit.reset()


def test_prune_expired_on_empty_state_returns_zero():
    rate_limit.configure(5, 60)
    try:
        assert rate_limit.prune_expired() == 0
    finally:
        rate_limit.reset()
