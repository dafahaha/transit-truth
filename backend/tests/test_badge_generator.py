"""Tests for SVG badge generators (user-controlled field escaping).

The contributor name reaches the badge from the public /api/contribute
endpoint. It must be HTML/XML-escaped before being spliced into the SVG, so a
malicious name like ``<script>alert(1)</script>"&`` cannot inject a script tag
or break out of the text/attribute context.
"""

from app.utils.badge_generator import (
    generate_contributor_badge,
    generate_stat_badge,
)


class TestBadgeEscaping:
    def test_contributor_name_script_tag_is_escaped(self):
        evil = '<script>alert(1)</script>"&'
        svg = generate_contributor_badge(evil, 5, 2)
        # The raw payload must never appear verbatim.
        assert "<script>alert(1)</script>" not in svg
        # But its escaped form must be present.
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg
        assert "&quot;" in svg
        assert "&amp;" in svg

    def test_contributor_name_plain_still_works(self):
        svg = generate_contributor_badge("dafahaha", 5, 2)
        assert "@dafahaha" in svg

    def test_stat_badge_label_and_value_are_escaped(self):
        evil_label = '<script>x</script>"&'
        evil_value = 'v"<b>&'
        svg = generate_stat_badge(evil_label, evil_value, "#2563eb")
        assert "<script>x</script>" not in svg
        assert "&lt;script&gt;x&lt;/script&gt;" in svg
        assert "&quot;" in svg
        assert "&amp;" in svg

    def test_stat_badge_plain_still_works(self):
        svg = generate_stat_badge("Audits", "12", "#16a34a")
        assert ">Audits<" in svg or "Audits" in svg
        assert ">12<" in svg or ">12" in svg
