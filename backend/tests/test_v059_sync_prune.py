"""v0.5.9 P3-2 regression: sync_reference_data.py prunes stale mirrored JSON.

Commit f74575c added the stale-file prune so a removed/renamed catalog entry
never keeps shipping inside the wheel. Before this test, deleting the prune
loop in ``sync_reference_data.py:45-48`` left every existing test green, so
the behavior had no regression guard. This test seeds a stale JSON in the
destination mirror, asserts it is pruned and the current file copied, then
runs a second pass that must be a no-op (idempotent, nothing pruned).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_sync_module():
    spec = importlib.util.spec_from_file_location(
        "sync_reference_data", REPO_ROOT / "sync_reference_data.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prunes_stale_json_and_copies_current(tmp_path, capsys):
    sync = _load_sync_module()
    src = tmp_path / "src_baselines"
    dst = tmp_path / "dst_baselines"
    src.mkdir()
    dst.mkdir()

    current = src / "gpt-4o-mini.json"
    current.write_text('{"model": "gpt-4o-mini"}', encoding="utf-8")
    # Stale entry present in the mirror but absent from the source manifest.
    stale = dst / "STALE-OLD-RETIRED.json"
    stale.write_text('{"retired": true}', encoding="utf-8")
    # A current file already present in the mirror (must be refreshed, kept).
    (dst / "gpt-4o-mini.json").write_text("{}", encoding="utf-8")

    sync.REPO = tmp_path
    sync.JOBS = [(src, dst)]
    sync.main()

    out = capsys.readouterr().out
    # Stale file was pruned; current file survived and was copied.
    assert not stale.exists(), "stale mirrored JSON must be pruned"
    assert (dst / "gpt-4o-mini.json").exists()
    assert "pruned stale" in out
    assert "copied" in out


def test_second_pass_is_idempotent_no_prune(tmp_path, capsys):
    sync = _load_sync_module()
    src = tmp_path / "src_baselines"
    dst = tmp_path / "dst_baselines"
    src.mkdir()
    dst.mkdir()
    (src / "gpt-4o-mini.json").write_text('{"model": "gpt-4o-mini"}', encoding="utf-8")
    (dst / "gpt-4o-mini.json").write_text('{"model": "gpt-4o-mini"}', encoding="utf-8")

    sync.REPO = tmp_path
    sync.JOBS = [(src, dst)]
    sync.main()
    capsys.readouterr()  # discard first-pass output

    # Second pass: manifest matches the mirror exactly -> no prune, no change.
    sync.main()
    out = capsys.readouterr().out
    assert "pruned stale" not in out, "second pass must prune nothing"
    assert (dst / "gpt-4o-mini.json").exists()
