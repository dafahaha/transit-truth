"""Regression guard: detect_base_url must never fall back to a commercial relay.

A prior regression re-injected an "unknown sk- key defaults to a commercial
relay (wolfai)" fallback at the top of detect_base_url; the existing tests
all passed because they only checked "returns None or a string". These
tests pin two properties:

1. Behavioural: empty/unknown keys resolve to None (or an official
   first-party endpoint) and never to a commercial relay name/URL.
2. Source-level: detect.py must not contain any commercial-relay domain
   string, and detect_base_url must not carry a hardcoded commercial
   fallback. A re-injected commercial default fails this suite instead of
   silently shipping.
"""

import inspect
from pathlib import Path

from app.core.detect import detect_base_url, suggest_relays

# Commercial relay names/domains that must never appear as a default guess.
_COMMERCIAL_BLOCKLIST = (
    "wolfai",
    "api2d",
    "ohmygpt",
    "aihubmix",
    "closeai",
    "betterapi",
    "geekapi",
    "anyai",
    "aiproxy",
    "aigc369",
    "chatanywhere",
    "fakeopen",
    "openai-sb",
    "aidp.cloud",
)

_CORE_DIR = Path(inspect.getfile(inspect.getmodule(detect_base_url))).parent


class TestDetectNoCommercialDefault:
    def test_empty_key_returns_none(self):
        assert detect_base_url("") is None
        assert detect_base_url(None) is None

    def test_unknown_sk_key_never_returns_commercial_relay(self):
        result = detect_base_url("sk-unknown-anonymous-12345")
        # May be None or an official first-party endpoint; never a commercial relay.
        if result is not None:
            lowered = result.lower()
            for bad in _COMMERCIAL_BLOCKLIST:
                assert (
                    bad not in lowered
                ), f"detect_base_url returned commercial relay '{bad}' for unknown key"

    def test_official_prefix_still_resolves(self):
        # Guard against over-removal: a unique official first-party prefix still maps.
        result = detect_base_url("gsk_abc123")
        assert result is not None
        assert "groq" in result.lower()

    def test_suggest_relays_exclude_commercial(self):
        for s in suggest_relays("sk-unknown-anonymous-12345"):
            lowered = s["base_url"].lower()
            for bad in _COMMERCIAL_BLOCKLIST:
                assert (
                    bad not in lowered
                ), f"suggest_relays leaks commercial relay '{bad}'"

    # Source-level injection guard.
    def test_detect_source_has_no_commercial_domain(self):
        src = (_CORE_DIR / "detect.py").read_text(encoding="utf-8").lower()
        for bad in _COMMERCIAL_BLOCKLIST:
            assert bad not in src, f"detect.py re-introduced commercial relay '{bad}'"

    def test_detect_base_url_has_no_hardcoded_fallback(self):
        body = inspect.getsource(detect_base_url)
        # A hardcoded commercial fallback would look like `return "https://...wolfai..."`.
        for bad in _COMMERCIAL_BLOCKLIST:
            assert (
                bad not in body.lower()
            ), f"detect_base_url carries commercial fallback '{bad}'"
        # After the KNOWN_RELAYS loop the function must end in a neutral return None.
        assert "return None" in body
