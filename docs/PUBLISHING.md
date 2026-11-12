# Publishing transit-truth to PyPI

> **Status: GitHub Release v0.5.9 published; PyPI not published yet — the package
> and the publish pipeline are ready (verified 2026-11-07, re-verified 2026-11-11).**
> `README.md` / `README.en.md` already advertise `pip install transit-truth`
> (source install kept as a fallback), the committed `dist/` artifacts were
> rebuilt from the current `main` source, and `.github/workflows/publish.yml`
> publishes via Trusted Publishing (OIDC) when a GitHub Release is published.
> Test count re-run on 2026-11-11 in a clean venv: **400 passed, 7 skipped**.
> The release path below was run end to end on 0.5.9: `twine check` PASSED on both
> artifacts, and the resulting wheel installed cleanly into a fresh venv where
> `transit-truth --help` and `transit-truth verify --help` both work.
> The GitHub Release (<https://github.com/dafahaha/transit-truth/releases/tag/v0.5.9>)
> carries the originally-tagged build. The artifacts below were rebuilt on
> 2026-11-11 from current `main`, with the README flipped to `pip install
> transit-truth`; these are the ones meant for the PyPI upload.
> Canonical artifacts (reproducible, `SOURCE_DATE_EPOCH=1792368000`):
>
> | file | bytes | sha256 |
> |---|---|---|
> | `transit_truth-0.5.9-py3-none-any.whl` | 193219 | `563f21d4def1707be45acbefc13a734e17e9ffd5599f7e10be5d8a9ccfb8b569` |
> | `transit_truth-0.5.9.tar.gz` | 227941 | `37674ba60464eb57e64468ce15d3439451168dce7409c8d1363af376e75efd73` |
>
> The only remaining step is the PyPI upload, which requires your own PyPI account
> and 2FA token — this is the part only you can do. Do it in order; do not skip
> TestPyPI.

## 0. Preflight (already done — re-run before every release)

> 🔒 **Use the release script, not bare `python -m build`.** Bare builds are
> non-reproducible on Windows: the wheel honors `SOURCE_DATE_EPOCH`, but the
> sdist tar.gz stamps every tar member (and the gzip header) with the actual
> wall-clock build time, so the SHA256 of a rebuilt tarball drifts even with
> byte-identical content. `scripts/build_release.ps1` pins
> `SOURCE_DATE_EPOCH=1792368000` (0.5.9 release date, 2026-10-19 00:00 UTC),
> builds both artifacts, then rewrites the sdist with fixed member mtimes,
> stripped PAX headers, and gzip `mtime=0` — two consecutive clean runs then
> produce byte-identical sdist+wheel (verified). Always upload those artifacts
> and record their hashes; if you rebuild by hand, the hashes will NOT match
> what is archived.

```powershell
# from the repo root — the ONLY supported release-build path:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_release.ps1
# it runs: clean -> python -m build -> sdist normalize -> twine check
```

**Interpreter preflight (built into the script):** the build needs a Python
with `build` and `twine` installed (e.g. `pip install build twine`). The
script resolves the interpreter as `$env:PYTHON` if set, otherwise `python`
from PATH; it then verifies `import build, twine` succeeds and auto-installs
them if missing (or fails with an actionable message). If your PATH mixes
anaconda base (which may lack build/twine) with another Python, point the
script at the right one explicitly:

```powershell
$env:PYTHON = "C:\path\to\python.exe"   # optional override
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_release.ps1
```

Equivalent manual steps (only if debugging):

```powershell
$env:SOURCE_DATE_EPOCH = "1792368000"
python sync_reference_data.py          # mirrors data/ into the package
python -m build                        # requires: pip install build
python scripts\_normalize_sdist.py dist\transit_truth-0.5.9.tar.gz
python -m twine check dist/*           # requires: pip install twine
```

Both artifacts must say `PASSED`:

```
Checking dist\transit_truth-0.5.9-py3-none-any.whl: PASSED
Checking dist\transit_truth-0.5.9.tar.gz: PASSED
```

**Versioning rule.** The shipped version lives in four places and a test
(`backend/tests/test_v045_version_tokenizer.py`) asserts they agree:

1. `pyproject.toml` (root) `[project] version`
2. `backend/pyproject.toml` `[project] version`
3. `backend/app/config.py` `APP_VERSION`
4. `backend/app/__init__.py` `__version__`

Cut a release only after moving the CHANGELOG `[Unreleased]` entry to a dated
version header, bumping all four sources, and running the test suite
(`400 passed / 7 skipped` and counting).

Package name: `transit-truth` was checked available on PyPI
(`https://pypi.org/pypi/transit-truth/json` returned 404 at readiness time).
If PyPI ever rejects the name on upload, candidates are `transit-truth-cli`,
`tt-audit`, or `model-truth-cli` — you will then need to update the root
`pyproject.toml` `[project] name` and re-sync this doc.

## 1. PyPI account & 2FA (one-time)

1. Register at <https://pypi.org/account/register/> with your email.
2. **Enable 2FA** (Security → Two-factor authentication). PyPI no longer
   accepts long-lived password auth for uploads; you need either a trusted
   publisher or an API token.
3. Recommended: add PyPI as a **trusted publisher** for this GitHub repo
   (PyPI → Publishing → Add a new publisher):
   - PyPI project name: `transit-truth`
   - Owner: `dafahaha`
   - Repository name: `transit-truth`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`

   This removes secrets entirely: GitHub's OIDC token does the upload. If the
   automated run fails, fall back to a local upload with a project-scoped API
   token (see the alternative below) — do not create a repository secret, because
   `publish.yml` reads none.

## 2. Smoke test on TestPyPI first

```powershell
python -m twine upload --repository testpypi dist/*
```

Then install from TestPyPI into a throwaway venv and verify:

```powershell
python -m venv .venv-testpypi
.venv-testpypi\Scripts\pip install --index-url https://test.pypi.org/simple/ `
    --extra-index-url https://pypi.org/simple/ transit-truth
.venv-testpypi\Scripts\transit-truth --help
```

Expected: help text prints, no `ModuleNotFoundError`. Also run the local
self-check from the README (`reference-server` + `verify --allow-local`) — it
confirms the bundled reference catalog made it into the wheel.

## 3. Upload to real PyPI

```powershell
python -m twine upload dist/*
```

## 4. (Recommended) Automate with GitHub Actions

`.github/workflows/publish.yml` is already in the repo: it builds, runs
`twine check`, and publishes with `pypa/gh-action-pypi-publish@release/v1`
(OIDC trusted publisher, no secret to manage). Trigger it from
Actions → Publish → Run workflow, or publish a GitHub Release whose tag matches
the package version.

## 5. Post-publish checklist

- [ ] Confirm <https://pypi.org/project/transit-truth/> renders the README
      (long_description = README.en.md). Both READMEs already advertise
      `pip install transit-truth` and carry no `PYPI-FLIP` markers, so nothing
      needs editing after publish.
- [ ] Confirm the published metadata carries no "not yet published" wording.
- [ ] Create a GitHub Release with the CHANGELOG notes and the same tag (if not
      already published).
- [ ] Announce via `docs/launch_kit.md`.
