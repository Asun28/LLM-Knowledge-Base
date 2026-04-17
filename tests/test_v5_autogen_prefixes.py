"""Regression: AUTOGEN_PREFIXES centralized; skip applied to orphan/isolated/stub checks."""


def test_autogen_prefixes_is_in_config():
    from kb.config import AUTOGEN_PREFIXES

    assert AUTOGEN_PREFIXES == ("summaries/", "comparisons/", "synthesis/")


def test_check_stub_pages_skips_comparisons_and_synthesis(tmp_wiki, create_wiki_page):
    from kb.lint.checks import check_stub_pages

    # comparisons/ and synthesis/ MUST be skipped (currently checks.py:446 only skips summaries/)
    create_wiki_page(
        page_id="comparisons/short",
        title="Short comparison",
        content="Brief.",  # <100 chars
        wiki_dir=tmp_wiki,
        page_type="comparison",
    )
    create_wiki_page(
        page_id="synthesis/short",
        title="Short synthesis",
        content="Brief.",
        wiki_dir=tmp_wiki,
        page_type="synthesis",
    )
    create_wiki_page(
        page_id="summaries/short",
        title="Short summary",
        content="Brief.",
        wiki_dir=tmp_wiki,
        page_type="summary",
    )
    issues = check_stub_pages(wiki_dir=tmp_wiki)
    flagged = {i["page"] for i in issues}
    assert "comparisons/short" not in flagged
    assert "synthesis/short" not in flagged
    assert "summaries/short" not in flagged


def test_check_stub_pages_still_flags_entity_stub(tmp_wiki, create_wiki_page):
    from kb.lint.checks import check_stub_pages

    create_wiki_page(
        page_id="entities/foo",
        title="Foo",
        content="Brief.",
        wiki_dir=tmp_wiki,
        page_type="entity",
    )
    issues = check_stub_pages(wiki_dir=tmp_wiki)
    flagged = {i["page"] for i in issues}
    assert "entities/foo" in flagged
