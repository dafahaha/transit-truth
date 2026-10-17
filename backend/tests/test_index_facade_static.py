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


def test_no_top_level_external_static_import(page_text: str) -> None:
    # A top-level static `import ... from 'https://...'` rejects the whole module
    # graph when the CDN is unreachable; external deps must use dynamic import()
    # wrapped in try/catch (or be removed). A bare side-effect
    # `import 'https://...'` is rejected the same way.
    import re

    external_static = re.findall(
        r"^\s*import\s+[^\n]*from\s+['\"]https?://",
        page_text,
        re.MULTILINE | re.IGNORECASE,
    )
    external_side_effect = re.findall(
        r"^\s*import\s+['\"]https?://",
        page_text,
        re.MULTILINE | re.IGNORECASE,
    )
    assert (
        not external_static
    ), f"top-level external static import found: {external_static}"
    assert (
        not external_side_effect
    ), f"bare side-effect external import found: {external_side_effect}"


def test_no_external_script_src(page_text: str) -> None:
    # No remote <script src>; the facade must be self-contained. Catch:
    #  * http(s) any scheme casing (HTTPS://, https://)
    #  * single/double quotes, unquoted
    #  * optional whitespace around `=` (`src = //x`)
    #  * protocol-relative (//...) URLs
    import re

    remote_scripts = re.findall(
        r'<script[^>]+src\s*=\s*["\']?https?://[^"\'>\s]+',
        page_text,
        re.IGNORECASE,
    )
    protocol_relative = re.findall(
        r'<script[^>]+src\s*=\s*["\']?//[^"\'>\s]+',
        page_text,
        re.IGNORECASE,
    )
    assert not remote_scripts, f"external remote script src found: {remote_scripts}"
    assert (
        not protocol_relative
    ), f"protocol-relative external script src found: {protocol_relative}"


def test_all_inline_handlers_defined_and_exported(page_text: str) -> None:
    # Every inline handler (onclick/onchange/oninput/onsubmit/...) must call a
    # function that is BOTH defined in the script AND exported on window. A
    # call to an undefined function, or a defined-but-unexported function, fails.
    import re

    # Capture inline handlers in BOTH quote styles: onclick="fn()" and
    # onclick='fn()'. A single-quote handler was previously invisible to this
    # guard and could call an undefined/unexported function unchecked.
    handlers = re.findall(r'\son\w+=(?:"([^"]+)"|\'([^\']+)\')', page_text)
    called = set()
    for double_q, single_q in handlers:
        attr = double_q or single_q
        called.update(re.findall(r"([A-Za-z_$][\w$]*)\s*\(", attr))
    defined = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", page_text))
    # Safe DOM methods / built-ins called inline need not be exported on window.
    builtins = {
        "getElementById",
        "querySelector",
        "querySelectorAll",
        "scrollIntoView",
        "addEventListener",
        "preventDefault",
        "focus",
        "blur",
        "click",
        "open",
        "close",
        "alert",
        "confirm",
        "parseInt",
        "parseFloat",
        "String",
        "Number",
        "Array",
        "Object",
        "JSON",
        "Math",
        "console",
        "fetch",
        "setTimeout",
        "setInterval",
        "encodeURIComponent",
        "decodeURIComponent",
    }
    undefined = sorted(fn for fn in called if fn not in defined and fn not in builtins)
    unexported = sorted(
        fn for fn in called if fn in defined and f"window.{fn} = {fn};" not in page_text
    )
    assert not undefined, f"inline handlers call undefined functions: {undefined}"
    assert not unexported, f"inline handlers not exported on window: {unexported}"
