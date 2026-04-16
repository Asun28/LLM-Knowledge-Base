"""Regression tests for kb.utils.markdown — wikilink extraction."""


def test_extract_wikilinks_rejects_whitespace_only_targets():
    """Regression: Phase 4.5 CRITICAL item 12 ([[   ]] produced phantom empty-target nodes)."""
    from kb.utils.markdown import extract_wikilinks

    assert extract_wikilinks("See [[   ]] for details.") == []
    assert extract_wikilinks("See [[\t]] for details.") == []
    assert extract_wikilinks("Normal [[concepts/a]] link.") == ["concepts/a"]
