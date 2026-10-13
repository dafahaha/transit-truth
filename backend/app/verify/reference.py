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


def load_reference_analyzer(
    extra_dirs: Optional[list[str]] = None,
) -> StatisticalAnalyzer:
    """Build a :class:`StatisticalAnalyzer` populated with reference fingerprints.

    Real reference files are loaded from every directory that exists. Missing
    directories are skipped silently (the v2 open-source catalog may not be
    populated yet). The analyzer starts from synthetic defaults, then loads
    real baselines; ``load_real_baselines`` itself drops synthetic-only
    placeholders so a claim can never silently compare against a fabricated
    distribution.
    """
    analyzer = StatisticalAnalyzer()
    analyzer.load_default_baselines()

    dirs: list[Path] = list(DEFAULT_REFERENCE_DIRS)
    if extra_dirs:
        dirs.extend(Path(d) for d in extra_dirs)

    for d in dirs:
        if d.exists():
            analyzer.load_real_baselines(str(d))

    return analyzer


def resolve_reference(
    analyzer: StatisticalAnalyzer, claimed_model: str
) -> Optional[BaselineDistribution]:
    """Return the reference fingerprint for *claimed_model*, or ``None``."""
    return analyzer._resolve_baseline(claimed_model)
