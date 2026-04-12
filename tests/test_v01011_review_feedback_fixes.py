"""Tests for Phase 4 review/feedback/config fixes."""
from __future__ import annotations


def test_refine_page_rejects_multiline_frontmatter_body(tmp_wiki):
    """Content that looks like a multi-line frontmatter block must be rejected."""
    from kb.review.refiner import refine_page

    page = tmp_wiki / "concepts" / "foo.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: foo\ntype: concept\nconfidence: stated\n---\nBody\n",
        encoding="utf-8",
    )
    # Multi-line frontmatter-looking content
    malicious = "---\ntitle: evil\ntype: concept\nconfidence: stated\n---\n"
    result = refine_page("concepts/foo", malicious, revision_notes="update", wiki_dir=tmp_wiki)
    assert "error" in result, "Expected error for frontmatter-block content"


def test_refine_page_updated_regex_anchored(tmp_wiki):
    """'last_updated: 2023-01-01' in the body must NOT be rewritten by the date update."""
    from kb.review.refiner import refine_page

    page = tmp_wiki / "concepts" / "bar.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        "---\ntitle: bar\ntype: concept\nconfidence: stated\n"
        "updated: 2023-01-01\n---\n"
        "Some body text with last_updated: 2022-12-31 in it.\n",
        encoding="utf-8",
    )
    refine_page(
        "concepts/bar",
        "New body with last_updated: 2022-12-31 inside.",
        revision_notes="x",
        wiki_dir=tmp_wiki,
    )
    final = page.read_text(encoding="utf-8")
    # The body's 'last_updated: 2022-12-31' must survive untouched
    assert "last_updated: 2022-12-31" in final


def test_embedding_dim_resolved():
    """EMBEDDING_DIM must be either deleted from config or validated in VectorIndex."""
    from kb import config

    if not hasattr(config, "EMBEDDING_DIM"):
        return  # Deleted — PASS

    # If it still exists, it must be used somewhere (VectorIndex.build)
    import inspect

    try:
        from kb.query.embeddings import VectorIndex

        src = inspect.getsource(VectorIndex)
        assert "EMBEDDING_DIM" in src, (
            "EMBEDDING_DIM defined in config but not validated in VectorIndex"
        )
    except ImportError:
        pass
