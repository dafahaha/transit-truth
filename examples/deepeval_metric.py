"""DeepEval-style custom metric example (OPTIONAL dependency).

This shows how to wrap the verifier as a DeepEval-style metric. It does NOT
require deepeval to be installed: the metric logic uses only the plain report
dict, and the DeepEval base classes are imported defensively.

Install deepeval to actually register it::

    pip install deepeval

Otherwise this file just documents the integration shape.
"""

from __future__ import annotations

from app.verify import verify_endpoint_sync


class TransitTruthIdentityMetric:
    """A minimal DeepEval-style metric over a relay endpoint.

    Usage with DeepEval (optional)::

        from deepeval.metrics import BaseMetric
        class Metric(TransitTruthIdentityMetric, BaseMetric): ...
    """

    def __init__(self, base_url: str, claimed_model: str, threshold: float = 0.5):
        self.base_url = base_url
        self.claimed_model = claimed_model
        self.threshold = threshold

    def measure(self, *args, **kwargs) -> dict:
        report = verify_endpoint_sync(
            base_url=self.base_url, claimed_model=self.claimed_model
        )
        # Map the three-state verdict to a 0..1 score a metric suite can threshold.
        score_map = {"pass": 1.0, "insufficient_evidence": 0.5, "suspicious": 0.0}
        self.score = score_map.get(report["verdict"], 0.0)
        self.success = self.score >= self.threshold
        self.reason = report["evidence_reason"]
        return report


if __name__ == "__main__":
    print(
        "TransitTruthIdentityMetric is ready. Wire it into DeepEval by subclassing "
        "deepeval.metrics.BaseMetric and calling self.measure(endpoint, model)."
    )
