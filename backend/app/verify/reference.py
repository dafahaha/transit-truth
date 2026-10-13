"""Reference fingerprint loading for the stateless verifier.

The verifier compares an endpoint's observed fingerprint against a reference
distribution. Reference data is the *same* on-disk format the existing audit
pipeline already collects (``data/baselines/*.json``), extended in v2 by the
open-source fingerprint catalog (``data/fingerprints/*.json``).

We deliberately reuse :class:`app.core.statistical_analyzer.StatisticalAnalyzer`
rather than re-implementing the KS / chi-square / Bayesian machinery: the
verifier is a thin, stateless shell around the already-audited statistics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.statistical_analyzer import BaselineDistribution, StatisticalAnalyzer

# Repo root: backend/app/verify/reference.py -> 4 parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_REFERENCE_DIRS = [
    _REPO_ROOT / "data" / "baselines",
    _REPO_ROOT / "data" / "fingerprints",
]


def _inject_fingerprint(analyzer: StatisticalAnalyzer, path: Path) -> None:
    """Inject one fingerprint JSON into ``baseline_db`` WITHOUT dropping others.

    ``load_real_baselines`` drops any pre-existing baseline it did not load in the
    same call (to purge synthetic placeholders). When we have several reference
    directories we must not run that purge per-directory or later loads would
    wipe earlier ones, so the open-source catalog is injected directly.
    """
    import json

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    model_name = data["metadata"]["model"]

    tokenizer_dist: dict[str, list[float]] = {}
    for probe_id, probe_data in data.get("tokenizer", {}).items():
        samples = probe_data.get("prompt_tokens", {}).get("samples")
        if samples:
            tokenizer_dist[probe_id] = [float(s) for s in samples]

    behavioral_dist: dict[str, list[str]] = {}
    for probe_id, probe_data in data.get("behavioral", {}).items():
        dist = probe_data.get("response_distribution", {})
        rows: list[str] = []
        for resp, count in dist.items():
            rows.extend([resp] * int(count))
        if rows:
            behavioral_dist[probe_id] = rows

    analyzer.baseline_db[model_name] = BaselineDistribution(
        model_family=analyzer._infer_family(model_name),
        model_name=model_name,
        tokenizer_distributions=tokenizer_dist,
        behavioral_distributions=behavioral_dist,
        latency_distribution=[float(x) for x in data.get("latency", [])],
        sample_size=data["metadata"].get("samples_per_probe", 0),
        collected_at=data["metadata"].get("collected_at", ""),
    )


def load_reference_analyzer(
    extra_dirs: Optional[list[str]] = None,
) -> StatisticalAnalyzer:
    """Build a :class:`StatisticalAnalyzer` populated with reference fingerprints.

    Real baselines from ``data/baselines`` are loaded via the audited
    ``load_real_baselines`` (which purges synthetic placeholders). The
    open-source catalog ``data/fingerprints`` (and any extra dirs) is then
    injected directly so it does not wipe the baselines.
    """
    analyzer = StatisticalAnalyzer()
    analyzer.load_default_baselines()

    # Purge synthetic placeholders once, using the audited baselines dir.
    baselines_dir = _REPO_ROOT / "data" / "baselines"
    if baselines_dir.exists():
        analyzer.load_real_baselines(str(baselines_dir))

    extra: list[Path] = [_REPO_ROOT / "data" / "fingerprints"]
    if extra_dirs:
        extra.extend(Path(d) for d in extra_dirs)
    for d in extra:
        if d.exists():
            for jf in sorted(d.glob("*.json")):
                if "test" in jf.name.lower():
                    continue
                try:
                    _inject_fingerprint(analyzer, jf)
                except Exception as exc:  # noqa: BLE001
                    print(f"  Warning: could not load fingerprint {jf.name}: {exc}")

    return analyzer


def resolve_reference(
    analyzer: StatisticalAnalyzer, claimed_model: str
) -> Optional[BaselineDistribution]:
    """Return the reference fingerprint for *claimed_model*, or ``None``."""
    return analyzer._resolve_baseline(claimed_model)


def tokenizer_consistency(
    observed: dict[str, float],
    baseline: Optional[BaselineDistribution],
    tolerance: int = 1,
) -> dict:
    """Direct, deterministic tokenizer-count consistency.

    A model's tokenizer produces a *fixed* token count for a given prompt. Two
    endpoints served by the same tokenizer must agree (within rounding) on that
    count; a different tokenizer (e.g. Qwen vs GLM vs o200k) diverges. This is a
    cross-family signal that does not depend on chi-square power and works on the
    small real tokenizer fingerprints.
    """
    if baseline is None:
        return {"overlap": 0, "consistent": 0, "score": None, "verdict": "no_baseline"}

    import statistics

    overlap = 0
    consistent = 0
    details: dict[str, dict] = {}
    for probe_id, obs_count in observed.items():
        ref_samples = baseline.tokenizer_distributions.get(probe_id)
        if not ref_samples:
            continue
        overlap += 1
        ref_mean = statistics.mean(ref_samples)
        ok = abs(obs_count - ref_mean) <= tolerance
        consistent += 1 if ok else 0
        details[probe_id] = {
            "observed": obs_count,
            "reference": round(ref_mean, 1),
            "consistent": ok,
        }

    if overlap == 0:
        return {
            "overlap": 0,
            "consistent": 0,
            "score": None,
            "verdict": "no_overlap",
            "details": details,
        }
    score = consistent / overlap
    # Symmetric minimum-overlap rule: we need at least 3 overlapping probes before
    # declaring EITHER a family mismatch OR a family match. Two overlapping probes
    # agreeing is not enough to certify the same tokenizer family.
    if overlap < 3:
        verdict = "insufficient_overlap"
    elif score < 0.5:
        verdict = "mismatch"
    elif score >= 0.8:
        verdict = "match"
    else:
        verdict = "ambiguous"
    return {
        "overlap": overlap,
        "consistent": consistent,
        "score": round(score, 2),
        "verdict": verdict,
        "details": details,
    }
