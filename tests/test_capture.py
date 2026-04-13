"""Tests for kb.capture — see docs/superpowers/specs/2026-04-13-kb-capture-design.md.

Test matrix coverage maps to spec §9 — Class A (input reject + secret scan + rate limit),
Class B (LLM failure), Class C (quality filter), Class D (write errors), happy path
(frontmatter, slug, MCP wrapper), round-trip integration.

Pytest imports are added in subsequent tasks alongside the first tests that use them.
"""

import pytest

from kb.utils.text import yaml_escape


class TestYamlEscapeBidiMarks:
    """Spec §8 — strip Unicode bidi override marks to defend audit-log confusion."""

    @pytest.mark.parametrize("codepoint,name", [
        ("\u202a", "LEFT-TO-RIGHT EMBEDDING"),
        ("\u202b", "RIGHT-TO-LEFT EMBEDDING"),
        ("\u202c", "POP DIRECTIONAL FORMATTING"),
        ("\u202d", "LEFT-TO-RIGHT OVERRIDE"),
        ("\u202e", "RIGHT-TO-LEFT OVERRIDE"),
        ("\u2066", "LEFT-TO-RIGHT ISOLATE"),
        ("\u2067", "RIGHT-TO-LEFT ISOLATE"),
        ("\u2068", "FIRST STRONG ISOLATE"),
        ("\u2069", "POP DIRECTIONAL ISOLATE"),
    ])
    def test_strips_bidi_codepoint(self, codepoint, name):
        result = yaml_escape(f"pay{codepoint}usalert")
        assert codepoint not in result, f"{name} ({codepoint!r}) should be stripped"
        # The visible chars should survive
        assert "pay" in result
        assert "usalert" in result

    def test_preserves_normal_unicode(self):
        # CJK, accented Latin, Cyrillic — all should survive unchanged
        for s in ["決定", "café", "Привет", "résumé"]:
            result = yaml_escape(s)
            assert s in result or result == s, f"normal unicode {s!r} altered: {result!r}"

    def test_bidi_and_control_both_stripped(self):
        # Bidi range (U+202A-2069) and control range (\x01-\x1f) are disjoint,
        # so order of stripping does not matter for output. This test verifies
        # both classes are removed in a single yaml_escape call without
        # interference, not the ordering itself.
        result = yaml_escape("a\u202eb\x01c")
        assert "\u202e" not in result
        assert "\x01" not in result
        # The visible chars survive
        assert "a" in result and "b" in result and "c" in result
