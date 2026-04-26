"""Cycle 10 AC1/AC1b quality degradation warning tests.

Cycle 36 AC5 — added `kb.config.WIKI_DIR` mirror to the existing 3-module
monkeypatch chain (cycle-19 L1 defensive pattern). Call-chain trace:

- `kb_refine_page` → `refine_page` (kb.review.refiner) reads `WIKI_DIR` from
  refiner module-top snapshot (test patches via `kb.review.refiner.WIKI_DIR`).
- `refine_page` → `build_backlinks` (kb.compile.linker) reads `WIKI_DIR` from
  linker module-top snapshot (test patches via `kb.compile.linker.WIKI_DIR`).
- `kb_affected_pages` reads `WIKI_DIR` via `quality` module-top snapshot
  (test patches via `quality.WIKI_DIR` alias).

The `kb.config.WIKI_DIR` source mirror is defensive: the current chain does
not read `kb.config.WIKI_DIR` directly, but adding the mirror prepares for
the cycle-36 ubuntu-latest matrix introduction (AC12) and any future
re-import that captures the source snapshot.
"""

from kb.mcp import quality
from kb.mcp.quality import kb_affected_pages, kb_refine_page


def test_kb_refine_page_surfaces_backlinks_error_on_failure(
    tmp_wiki, create_wiki_page, monkeypatch
):
    page_id = "concepts/rag"
    create_wiki_page(page_id, content="old content", wiki_dir=tmp_wiki)
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_wiki)
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
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_wiki)
    monkeypatch.setattr("kb.compile.linker.WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(quality, "WIKI_DIR", tmp_wiki)

    def fail_load_all_pages(*, wiki_dir):
        raise OSError("page load failed")

    monkeypatch.setattr("kb.mcp.quality.load_all_pages", fail_load_all_pages)

    response = kb_affected_pages(page_id)

    assert "[warn] shared_sources_error:" in response
    assert "page load failed" in response
