"""F1 static regression guard for the serve UI (webapp/index.html).

CI has no Node runtime, so the enforceable guard lives in Python: it asserts the
UI defines ``esc()`` + a verdict whitelist, and that every server-provided value
interpolated inside ``renderReport`` (and the fetch catch) is wrapped in
``esc()``. Deleting ``esc`` or wiring a raw server field to ``innerHTML`` makes
this test fail. A zero-dependency Node unit test for ``esc()`` itself ships under
``scripts/webapp_esc.test.mjs`` for local runs.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "webapp" / "index.html"

# Server-side fields that reach the DOM and MUST be escaped.
_SERVER_REFS = ["rep.", "stats.", "tc.", "f.reason", "(beh", "k}"]


def _render_report_body(html: str) -> str:
    start = html.index("function renderReport(rep) {")
    end = html.index("el.innerHTML = html;", start)
    return html[start:end]


def test_esc_helper_and_whitelist_defined():
    html = PAGE.read_text(encoding="utf-8")
    assert "function esc(" in html, "esc() must be defined"
    assert "VERDICT_CLASSES" in html, "verdict whitelist must exist"
    assert "function verdictClass(" in html
    # Whitelist only admits the four verdicts + error.
    m = re.search(r"VERDICT_CLASSES\s*=\s*new Set\(\[([^\]]+)\]\)", html)
    assert m, "VERDICT_CLASSES literal not found"
    for allowed in ('"pass"', '"suspicious"', '"insufficient_evidence"', '"error"'):
        assert allowed in m.group(1)


def test_all_server_interpolations_are_escaped():
    html = PAGE.read_text(encoding="utf-8")
    body = _render_report_body(html)
    # Every ${...} that mentions a server field must carry esc( inside it.
    for interp in re.findall(r"\$\{([^}]*)\}", body):
        if any(ref in interp for ref in _SERVER_REFS):
            assert (
                "esc(" in interp
            ), f"server field interpolated without esc(): ${{{interp}}}"


def test_no_raw_verdict_class_interpolation():
    """verdict is mapped through the whitelist, never string-concatenated into a
    class attribute."""
    html = PAGE.read_text(encoding="utf-8")
    body = _render_report_body(html)
    # The class slot must use verdictClass(), not raw ${v} / ${rep.verdict}.
    assert "verdictClass(rep)" in body
    assert "${cls}" in body
    assert 'class="verdict ${v}"' not in body
    assert "${rep.verdict}" not in body.split("verdictClass(rep)")[0]


def test_fetch_catch_escapes_error_message():
    html = PAGE.read_text(encoding="utf-8")
    catch = html[html.index("} catch (err)") :]
    catch = catch[: catch.index("} finally")]
    assert "esc(err.message)" in catch, "network error message must be escaped"


def test_no_inline_injection_sink_patterns():
    """The page must not build an <img onerror> / <script> / javascript: node from
    server data (heuristic: no onerror= or javascript: literal in report HTML)."""
    html = PAGE.read_text(encoding="utf-8")
    body = _render_report_body(html)
    assert "onerror=" not in body.lower()
    assert "<script" not in body.lower()
    assert "javascript:" not in body.lower()


def test_bundled_copy_matches_root_and_is_esc_safe():
    """The installed fallback (app.verify/webapp/index.html) must stay byte-identical
    to the root webapp copy and carry the same esc()/whitelist guard."""
    import hashlib

    bundled = REPO / "backend" / "app" / "verify" / "webapp" / "index.html"
    assert bundled.is_file(), "bundled webapp/index.html missing"
    root_bytes = PAGE.read_bytes()
    bundled_bytes = bundled.read_bytes()
    assert (
        hashlib.sha256(root_bytes).hexdigest()
        == hashlib.sha256(bundled_bytes).hexdigest()
    ), "root and bundled webapp/index.html differ"
    bhtml = bundled.read_text(encoding="utf-8")
    assert "function esc(" in bhtml
    assert "VERDICT_CLASSES" in bhtml
    bbody = bhtml[
        bhtml.index("function renderReport(rep) {") : bhtml.index(
            "el.innerHTML = html;"
        )
    ]
    for interp in re.findall(r"\$\{([^}]*)\}", bbody):
        if any(ref in interp for ref in _SERVER_REFS):
            assert "esc(" in interp, f"bundled: server field not escaped: ${{{interp}}}"


# ─── P2-3: ESC_MAP table itself is pinned (Python CI guard) ────────────────
# The Node script scripts/webapp_esc.test.mjs exercises esc() at runtime, but
# it was never wired into CI. These static assertions parse ESC_MAP and the
# esc() character class so deleting the `<`/`>` (or any) mapping turns the
# Python suite red too — previously the mutation survived (M3 in the review).

# Every character esc() must neutralize -> its expected entity in ESC_MAP.
_REQUIRED_ESC_PAIRS = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
    "`": "&#96;",
    "$": "&#36;",
}


def _parse_esc_map(html: str) -> dict[str, str]:
    """Parse the ``const ESC_MAP = { ... }`` literal into a {char: entity} dict."""
    start = html.index("const ESC_MAP = {")
    end = html.index("\n};", start)
    block = html[start:end]
    mapping: dict[str, str] = {}
    for m in re.finditer(r"""['"](.)['"]\s*:\s*["']([^"']+)["']""", block):
        mapping[m.group(1)] = m.group(2)
    return mapping


def _esc_class(html: str) -> str:
    """Extract the character class inside esc()'s replace(/.../g) call."""
    esc_start = html.index("function esc(v) {")
    esc_end = html.index("\n}", esc_start)
    esc_src = html[esc_start:esc_end]
    m = re.search(r"replace\(/\[([^\]]+)\]/g", esc_src)
    assert m, "esc() replace character class not found"
    return m.group(1)


def _assert_esc_table(html: str, label: str) -> None:
    mapping = _parse_esc_map(html)
    for char, entity in _REQUIRED_ESC_PAIRS.items():
        assert (
            mapping.get(char) == entity
        ), f"{label}: ESC_MAP missing {char!r} -> {entity!r} (got {mapping.get(char)!r})"
    # Every required char must also be listed in the replace() character class,
    # otherwise the map entry is dead and the char survives unscathed.
    char_class = _esc_class(html)
    for char in _REQUIRED_ESC_PAIRS:
        assert (
            char in char_class
        ), f"{label}: {char!r} not in esc() replace class [{char_class}]"
    # Functional check: applying the table neutralizes raw injection samples.
    samples = [
        ("<img src=x onerror=alert(1)>", "&lt;img"),
        ("<script>alert(1)</script>", "&lt;script"),
        ['"quoted"', "&quot;"],
        ["'single'", "&#39;"],
        ["`template ${7*7}`", "&#96;"],
        ["dollar$ign", "&#36;"],
        ["&lt;entity&gt;", "&amp;lt;"],
    ]
    for raw, expect in samples:
        out = raw
        for char, entity in mapping.items():
            out = out.replace(char, entity)
        assert expect in out, f"{label}: esc({raw!r}) = {out!r}; expected {expect!r}"
        assert not re.search(
            r"[<>]", out
        ), f"{label}: raw tag delimiter survived: {out!r}"


def test_esc_map_table_and_class_are_complete():
    html = PAGE.read_text(encoding="utf-8")
    _assert_esc_table(html, "root webapp/index.html")


def test_bundled_copy_esc_map_table_is_complete():
    bundled = REPO / "backend" / "app" / "verify" / "webapp" / "index.html"
    bhtml = bundled.read_text(encoding="utf-8")
    _assert_esc_table(bhtml, "bundled webapp/index.html")
