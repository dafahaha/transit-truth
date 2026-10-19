# Publishing transit-truth to PyPI

> ⚠️ **已被取代 / 以 README 为准（v0.5.2）**：本文件是早期发布流程草稿；当前模型身份核验（测中转站真假）需本地/自托管 `transit-truth serve`，浏览器直连受 CORS 限制；测试数与口径以 README.md 为准，勿以本文件旧计数对外表述。

> **Status: build-ready, NOT published.** Everything below has been verified up
> to the upload step. The actual upload requires your own PyPI account and 2FA —
> this is the part only you can do. Do it in order; do not skip TestPyPI.

## 0. Preflight (already done — re-run before every release)

```powershell
# from the repo root
python sync_reference_data.py          # mirrors data/ into the package
python -m build                        # requires: pip install build
python -m twine check dist/*           # requires: pip install twine
```

Both artifacts must say `PASSED`:

```
Checking dist\transit_truth-0.4.7-py3-none-any.whl: PASSED
Checking dist\transit_truth-0.4.7.tar.gz: PASSED
```

**Versioning rule.** The shipped version lives in four places and a test
(`backend/tests/test_v045_version_tokenizer.py`) asserts they agree:

1. `pyproject.toml` (root) `[project] version`
2. `backend/pyproject.toml` `[project] version`
3. `backend/app/config.py` `APP_VERSION`
4. `backend/app/__init__.py` `__version__`

Cut a release only after moving the CHANGELOG `[Unreleased]` entry to a dated
version header, bumping all four sources, and running the test suite
(`352 passed / 7 skipped` and counting).

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
   - Workflow name: `release.yml` (create this workflow — see step 4)
   - Environment name: leave blank unless you set one.

   This removes secrets entirely: GitHub's OIDC token does the upload. If you
   would rather use a token instead: PyPI → API tokens → Add token, scope it
   to the `transit-truth` project (not "entire account"), and save it to a
   GitHub Actions secret named `PYPI_API_TOKEN`.

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

Once step 1 works manually, add `.github/workflows/release.yml`: on a
`v*` tag push, set up Python, run `python -m build`, and upload with
`pypa/gh-action-pypi-publish@release/v1` (OIDC trusted publisher, no secret to
manage). Trigger by pushing the tag that matches the CHANGELOG version.

## 5. Post-publish checklist

- [ ] Confirm <https://pypi.org/project/transit-truth/> renders the README
      (long_description = README.en.md).
- [ ] Edit `README.en.md` / `README.md`: both files contain explicit
      `PYPI-FLIP` HTML comments. In `README.en.md`, replace the Quickstart
      install block (currently source install) with `pip install transit-truth`
      and `pip install "transit-truth[reference]"`, and rename the
      "Installing from source" section per its `PYPI-FLIP` comment. In
      `README.md`, replace the "PyPI 上**尚未发布**" block with the pip
      command. The build's `long_description` is README.en.md, so the English
      side must be flipped first.
- [ ] Search both READMEs for `PYPI-FLIP` and resolve every marker.
- [ ] Create a GitHub Release with the CHANGELOG notes and the same tag.
- [ ] Announce via `docs/launch_kit.md`.
