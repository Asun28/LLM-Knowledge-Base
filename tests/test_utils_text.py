"""Regression tests for kb.utils.text — slugify and related helpers."""

from tests.fixtures.injection_payloads import (
    BENIGN_KEY_CLAIM_WITH_CODE,
    BENIGN_SUMMARY_WITH_DASHES,
    INJECTION_CONTROL_CHARS,
    INJECTION_EVIDENCE_ANCHOR,
    INJECTION_FRONTMATTER_FENCE,
    INJECTION_HEADER,
    INJECTION_HTML_COMMENT,
    INJECTION_MARKDOWN_LINK,
    INJECTION_MAX_LENGTH,
    INJECTION_WIKILINK_CLOSE,
    INJECTION_WIKILINK_PIPE,
)

# ---------------------------------------------------------------------------
# sanitize_extraction_field
# ---------------------------------------------------------------------------


def test_sanitize_strips_markdown_header_injection():
    """Regression: Phase 4.5 HIGH item 1 (## header injection into wiki body)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(INJECTION_HEADER)
    assert "## Review Checklist" not in result


def test_sanitize_strips_evidence_trail_anchor():
    """Regression: Phase 4.5 HIGH item 2 (## Evidence Trail forgery in body)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(INJECTION_EVIDENCE_ANCHOR)
    assert "## Evidence Trail" not in result
    # Legitimate content before the injected header should survive
    assert "legitimate" in result


def test_sanitize_strips_html_comments():
    """Regression: Phase 4.5 HIGH item 3 (HTML comment injection)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(INJECTION_HTML_COMMENT)
    assert "<!--" not in result
    assert "malicious instruction" not in result
    # The surrounding benign text should survive
    assert "content" in result


def test_sanitize_strips_control_chars():
    """Regression: Phase 4.5 HIGH item 4 (C0 control char embedding)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(INJECTION_CONTROL_CHARS)
    assert "\x00" not in result
    assert "\x01" not in result
    assert "\x02" not in result
    # After stripping the three control chars the remaining text joins directly
    assert "contentembedded" in result


def test_sanitize_strips_frontmatter_fence():
    """Regression: Phase 4.5 HIGH item 5 (frontmatter fence injection)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(INJECTION_FRONTMATTER_FENCE)
    # No standalone --- lines should remain
    for line in result.splitlines():
        assert not line.strip() == "---", f"Frontmatter fence survived: {line!r}"


def test_sanitize_caps_length():
    """Regression: Phase 4.5 HIGH item 6 (length cap with truncation marker)."""
    from kb.utils.text import sanitize_extraction_field

    max_len = 100
    result = sanitize_extraction_field(INJECTION_MAX_LENGTH, max_len=max_len)
    assert result.endswith("... [truncated]")
    # Total length is max_len chars of payload + truncation suffix
    assert len(result) == max_len + len("... [truncated]")


def test_sanitize_preserves_em_dash():
    """Regression: Phase 4.5 HIGH item 7 (em-dash must survive sanitization)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(BENIGN_SUMMARY_WITH_DASHES)
    assert result == BENIGN_SUMMARY_WITH_DASHES


def test_sanitize_preserves_inline_code():
    """Regression: Phase 4.5 HIGH item 8 (inline backtick code must survive)."""
    from kb.utils.text import sanitize_extraction_field

    result = sanitize_extraction_field(BENIGN_KEY_CLAIM_WITH_CODE)
    assert result == BENIGN_KEY_CLAIM_WITH_CODE


def test_sanitize_none_returns_empty_string():
    """Regression: Phase 4.5 HIGH item 9 (None input returns empty string)."""
    from kb.utils.text import sanitize_extraction_field

    assert sanitize_extraction_field(None) == ""
    assert sanitize_extraction_field("") == ""


# ---------------------------------------------------------------------------
# wikilink_display_escape
# ---------------------------------------------------------------------------


def test_wikilink_escape_strips_close_brackets():
    """Regression: Phase 4.5 HIGH item 10 (]] in title breaks wikilink syntax)."""
    from kb.utils.text import wikilink_display_escape

    result = wikilink_display_escape(INJECTION_WIKILINK_CLOSE)
    assert "]]" not in result
    assert "[[" not in result
    # The meaningful text content should still be readable
    assert "bad" in result


def test_wikilink_escape_escapes_pipes():
    """Regression: Phase 4.5 HIGH item 11 (| splits wikilink display text)."""
    from kb.utils.text import wikilink_display_escape

    result = wikilink_display_escape(INJECTION_WIKILINK_PIPE)
    assert r"\|" in result
    assert result.count(r"\|") == INJECTION_WIKILINK_PIPE.count("|")
    # Words survive after pipe escaping
    assert "Title" in result
    assert "with" in result
    assert "pipes" in result


def test_wikilink_escape_handles_markdown_link_injection():
    """Regression: Phase 4.5 HIGH item 12 (markdown link injection via ]] and [[)."""
    from kb.utils.text import wikilink_display_escape

    result = wikilink_display_escape(INJECTION_MARKDOWN_LINK)
    assert "]]" not in result
    assert "[[" not in result
    # The URL text should remain visible (not silently dropped)
    assert "http://evil.com" in result


def test_slugify_preserves_cjk():
    """Regression: Phase 4.5 CRITICAL item 11.

    re.ASCII stripped all non-ASCII, collapsing CJK to empty.
    """
    from kb.utils.text import slugify

    assert slugify("中文标题") != "", "CJK title collapsed to empty slug"
    assert slugify("日本語") != ""
    assert slugify("あ") != ""


def test_slugify_falls_back_on_pure_emoji():
    """Regression: Phase 4.5 CRITICAL item 11 (fallback when strip yields empty)."""
    from kb.utils.text import slugify

    result = slugify("😀")
    assert result != "", "pure-emoji title produced empty slug"
    assert result.startswith("untitled-") or len(result) > 0
