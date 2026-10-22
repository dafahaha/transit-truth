"""Offline static guard for the pure-static online check (docs/online/).

Runs without a browser or network. Fails when the browser tool regresses on its
security contract: CSP tightened, no inline/external script, no DOM injection
sink for user/relay data, no key persistence, and the private-network block
patterns stay present. Runtime behavior is additionally exercised by the
headless-Chrome self-documentation in docs/audit_round1_1022.md.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ONLINE = REPO_ROOT / "docs" / "online"
PAGE = ONLINE / "index.html"
JS = ONLINE / "app.js"
CSS = ONLINE / "styles.css"


@pytest.fixture(scope="module")
def page_text() -> str:
    return PAGE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_text() -> str:
    return JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_code() -> str:
    """JS source with /* */ and // comments stripped, so comments that merely
    *describe* a forbidden sink do not trip the guard."""
    src = JS.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def test_files_present(page_text, js_text):
    assert PAGE.exists() and JS.exists() and CSS.exists()
    assert "verdict" in page_text.lower()


def test_csp_meta_tight_and_no_unsafe_inline_script(page_text):
    m = re.search(r'Content-Security-Policy" content="([^"]+)"', page_text)
    assert m, "CSP meta missing"
    csp = m.group(1)
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_no_remote_or_inline_script(page_text):
    assert not re.search(r"<script[^>]+src\s*=\s*[\"']?https?://", page_text, re.I)
    assert not re.search(r"<script[^>]+src\s*=\s*[\"']?//", page_text, re.I)
    # Only the external self-hosted app.js is allowed; no inline script block.
    inline = re.findall(
        r"<script(?![^>]*src=)[^>]*>(.*?)</script>", page_text, re.S | re.I
    )
    inline = [b.strip() for b in inline if b.strip()]
    assert not inline, f"inline script blocks found: {inline}"


def test_no_dom_injection_sinks(js_code):
    for sink in ("innerHTML", "outerHTML", "document.write", "insertAdjacentHTML"):
        assert sink not in js_code, f"dangerous DOM sink {sink} present"


def test_no_storage_persistence_of_key(js_code):
    for sink in ("localStorage", "sessionStorage", "setItem", "document.cookie"):
        assert sink not in js_code, f"key persistence sink {sink} present"


def test_evidence_object_never_contains_key(js_code):
    # The key (runKey) must never be copied into the evidence payload;
    # 'missing_api_key' appears only as a verdict state code.
    assert not re.search(r"api_key\s*:\s*runKey", js_code)
    assert "evidence.chat" in js_code
    assert "runKey" in js_code  # in-memory variable still exists


def test_only_http_https_scheme_allowed(js_text):
    assert "url.protocol !== 'http:'" in js_text
    assert "url.protocol !== 'https:'" in js_text
    # file:/data:/ftp:/ws: etc. fall into the rejection branch.
    assert "拒绝" in js_text


def test_private_network_block_patterns(js_text):
    for token in ("127", "192", "168", "169", "254", "100", "64", "::1", "fe80", "172"):
        assert token in js_text, f"private-block token {token} missing"


def test_user_strings_rendered_via_textcontent(js_text):
    assert "textContent" in js_text
    # el() helper must set textContent, never HTML.
    assert "node.textContent = String(text)" in js_text


def test_three_state_verdict_labels_present(js_text, page_text):
    for label in ("pass", "suspicious", "insufficient_evidence"):
        assert label in js_text or label in page_text
    for state in ("transport_error", "missing_api_key", "cors"):
        assert state in js_text


def test_bilingual_disclosure_present(page_text):
    assert "Probabilistic auxiliary evidence" in page_text
    assert "概率性辅助证据" in page_text
