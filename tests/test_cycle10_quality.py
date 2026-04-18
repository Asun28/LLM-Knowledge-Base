"""Cycle 10 AC1/AC1b quality degradation warning tests."""

from kb.mcp import quality
from kb.mcp.quality import kb_affected_pages, kb_refine_page


def test_kb_refine_page_surfaces_backlinks_error_on_failure(
    tmp_wiki, create_wiki_page, monkeypatch
):
    page_id = "concepts/rag"
    create_wiki_page(page_id, content="old content", wiki_dir=tmp_wiki)
    monkeypatch.setattr("kb.review.refiner.WIKI_DIR", tmp_wiki)
    monkeypatch.setattr("kb.compile.linker.WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(quality, "WIKI_DIR", tmp_wiki)

    def fail_backlinks():
        raise OSError("corrupt manifest cache")

    monkeypatch.setattr("kb.compile.linker.build_backlinks", fail_backlinks)

    response = kb_refine_page(page_id, "updated content", "test notes")

    assert response.startswith("Refined:")
    assert "[warn] backlinks_error:" in response
    assert "corrupt manifest cache" in response


def test_kb_affected_pages_surfaces_shared_sources_error_on_failure(
    tmp_wiki, create_wiki_page, monkeypatch
):
    page_id = "concepts/rag"
    create_wiki_page(
        page_id,
        content="content",
        source_ref="raw/articles/x.md",
        wiki_dir=tmp_wiki,
    )
    monkeypatch.setattr("kb.compile.linker.WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(quality, "WIKI_DIR", tmp_wiki)

    def fail_load_all_pages(*, wiki_dir):
        raise OSError("page load failed")

    monkeypatch.setattr("kb.mcp.quality.load_all_pages", fail_load_all_pages)

    response = kb_affected_pages(page_id)

    assert "[warn] shared_sources_error:" in response
    assert "page load failed" in response
