"""Static guard for the root Pages facade (index.html).

Runs without Node or a browser: it parses the static page and fails when a
removed DOM element leaves an orphan listener/getElementById, when
``runVerifyDemo`` is not exposed on ``window``, or when a dead direct-connect
``chat/completions`` fetch / real-key form comes back. If a future edit deletes
an element but leaves a reference, this test fails instead of crashing the page
at runtime (the v0.5.2 regression that crashed the whole module).
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "index.html"


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_all_referenced_element_ids_exist(page_text: str) -> None:
    """Every getElementById('x') must target an id that exists in the document."""
    import re

    defined = set(re.findall(r'id="([^"]+)"', page_text))
    referenced = set(re.findall(r"getElementById\(['\"]([^'\"]+)['\"]\)", page_text))
    missing = sorted(referenced - defined)
    assert not missing, f"getElementById targets missing elements: {missing}"


def test_run_verify_demo_exposed_on_window(page_text: str) -> None:
    assert "window.runVerifyDemo = runVerifyDemo;" in page_text
    assert "window.runDemo = runDemo;" in page_text


def test_no_direct_connect_chat_completions_fetch(page_text: str) -> None:
    # The static page must never POST a Bearer key straight to a relay.
    assert "chat/completions" not in page_text
    assert "/models" not in page_text


def test_no_real_key_form(page_text: str) -> None:
    # No real-key input / auto-detect / loadModels plumbing on the offline page.
    assert "api-key" not in page_text
    assert "loadModels" not in page_text
    assert "auto-detect-result" not in page_text


def test_demo_buttons_present(page_text: str) -> None:
    assert "runDemo()" in page_text
    assert "runVerifyDemo()" in page_text
