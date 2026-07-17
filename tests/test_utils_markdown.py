"""Regression tests for kb.utils.markdown — wikilink extraction."""


def test_extract_wikilinks_rejects_whitespace_only_targets():
    """Regression: Phase 4.5 CRITICAL item 12 ([[   ]] produced phantom empty-target nodes)."""
    from kb.utils.markdown import extract_wikilinks

    assert extract_wikilinks("See [[   ]] for details.") == []
    assert extract_wikilinks("See [[\t]] for details.") == []
    assert extract_wikilinks("Normal [[concepts/a]] link.") == ["concepts/a"]


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task02.py
# (utils/markdown.py parts). No deviations.
# ═══════════════════════════════════════════════════════════════════════


class TestWikilinkPatternEmbedExclusion:
    """WIKILINK_PATTERN must not match ![[image.png]] embeds."""

    def test_embed_not_extracted(self):
        from kb.utils.markdown import extract_wikilinks

        text = "See ![[raw/assets/image.png]] for the diagram."
        links = extract_wikilinks(text)
        assert not links

    def test_normal_wikilink_still_works(self):
        from kb.utils.markdown import extract_wikilinks

        text = "See [[concepts/rag]] for details."
        links = extract_wikilinks(text)
        assert links == ["concepts/rag"]


class TestRawRefPatternCaseInsensitive:
    """_RAW_REF_PATTERN must match uppercase extensions."""

    def test_uppercase_pdf(self):
        from kb.utils.markdown import extract_raw_refs

        text = "See raw/papers/report.PDF for details."
        refs = extract_raw_refs(text)
        assert "raw/papers/report.PDF" in refs

    def test_mixed_case_csv(self):
        from kb.utils.markdown import extract_raw_refs

        text = "Data at raw/datasets/data.Csv is here."
        refs = extract_raw_refs(text)
        assert "raw/datasets/data.Csv" in refs


class TestExtractRawRefsHyphenLookbehind:
    """extract_raw_refs must not match raw/ preceded by hyphen."""

    def test_hyphen_before_raw_rejected(self):
        from kb.utils.markdown import extract_raw_refs

        text = "The slug is see-raw/articles/foo.md in compound."
        refs = extract_raw_refs(text)
        assert refs == []
