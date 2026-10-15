#!/usr/bin/env python3
"""Mirror the shipped reference catalog into the installable Python package.

``transit-truth verify`` reads reference fingerprints from ``data/baselines``
and ``data/fingerprints`` in a repo checkout. When the package is built into a
wheel, the repo checkout is not available on the user's machine, so a copy of
the catalog ships inside ``backend/app/verify/data/``.

Run this script (from the repo root) whenever ``data/baselines`` or
``data/fingerprints`` changes, *before* building the sdist/wheel:

    python sync_reference_data.py

Only the shipped catalog files are copied (``dev_samples/`` and any ``*.json``
whose name contains "test" are intentionally excluded, matching
``load_reference_analyzer``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent

# (source dir, destination dir)
JOBS = [
    (
        REPO / "data" / "baselines",
        REPO / "backend" / "app" / "verify" / "data" / "baselines",
    ),
    (
        REPO / "data" / "fingerprints",
        REPO / "backend" / "app" / "verify" / "data" / "fingerprints",
    ),
]


def main() -> None:
    for src, dst in JOBS:
        dst.mkdir(parents=True, exist_ok=True)
        for jf in sorted(src.glob("*.json")):
            if "test" in jf.name.lower():
                continue
            shutil.copy2(jf, dst / jf.name)
            print(f"copied {jf.relative_to(REPO)} -> {dst.relative_to(REPO)}/{jf.name}")


if __name__ == "__main__":
    main()
