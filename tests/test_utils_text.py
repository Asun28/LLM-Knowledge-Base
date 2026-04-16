"""Regression tests for kb.utils.text — slugify and related helpers."""


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
