"""Regression test for the top-level analyze_baseline.py script.

The report appendix points to analyze_baseline.py as the script that reproduces
the flagship gpt-4o-mini result (posterior ~= 0.913, CrI ~= [0.885, 0.937],
LR = 4.5, confidence = medium). A previous version only loaded the small
synthetic baselines (which do not contain gpt-4o-mini), silently produced an
"inconclusive" 0.500 posterior, and then crashed formatting a None KS
statistic. This test runs the script as a subprocess and locks the correct
behavior so it cannot silently rot again. It reads only local JSON files and
never touches the network.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# backend/tests/test_analyze_baseline_script.py -> parents[2] = repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "analyze_baseline.py"

EXPECTED_POSTERIOR = 0.913
TOLERANCE = 0.01


@pytest.fixture(scope="module")
def script_run():
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=env,
    )
    return proc


def test_script_runs_without_error(script_run):
    assert script_run.returncode == 0, (
        f"analyze_baseline.py exited {script_run.returncode}\n"
        f"-- stdout --\n{script_run.stdout}\n"
        f"-- stderr --\n{script_run.stderr}"
    )


def test_script_does_not_crash_on_none_stats(script_run):
    # The old failure mode: formatting a None KS statistic raised TypeError.
    assert "TypeError" not in script_run.stderr
    assert "Traceback" not in script_run.stderr
    # And it must actually have loaded the real baseline, not fallen back to
    # the inconclusive default.
    assert "inconclusive" not in script_run.stdout
    assert "match" in script_run.stdout


def test_script_reproduces_flagship_posterior(script_run):
    match = re.search(r"后验概率:\s*([0-9.]+)", script_run.stdout)
    assert match, f"posterior line not found in output:\n{script_run.stdout}"
    posterior = float(match.group(1))
    assert (
        abs(posterior - EXPECTED_POSTERIOR) < TOLERANCE
    ), f"posterior {posterior} not within {TOLERANCE} of {EXPECTED_POSTERIOR}"
    # The exact reference value must appear verbatim so the report appendix
    # stays truthful.
    assert "0.913" in script_run.stdout


def test_script_reproduces_cri_and_lr(script_run):
    assert "[0.885, 0.937]" in script_run.stdout
    assert "似然比: 4.5" in script_run.stdout
    assert "置信度: medium" in script_run.stdout
