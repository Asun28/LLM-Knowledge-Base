"""Tests for kb.review.refiner — Phase 4.5 CRITICAL regression coverage."""

from contextlib import contextmanager


def test_refine_page_preserves_leading_code_block_indent(
    tmp_wiki, create_wiki_page, monkeypatch
):
    """Regression: Phase 4.5 CRITICAL item 10 (lstrip() stripped 4-space code-block indent)."""
    page_id = "concepts/code-sample"
    create_wiki_page(
        page_id=page_id,
        title="Code sample",
        content="Original.",
        wiki_dir=tmp_wiki,
    )
    new_body = "    def foo():\n        return 42\n\nMore text.\n"
    from kb.review import refiner

    monkeypatch.setattr(refiner, "REVIEW_HISTORY_PATH", tmp_wiki / "review_history.json")

    result = refiner.refine_page(
        page_id=page_id,
        updated_content=new_body,
        revision_notes="preserve indent",
        wiki_dir=tmp_wiki,
    )
    assert result.get("updated") is True
    page_text = (tmp_wiki / f"{page_id}.md").read_text(encoding="utf-8")
    assert "    def foo():" in page_text, f"4-space indent lost; body: {page_text!r}"


def test_refine_page_audit_uses_cross_process_lock(tmp_wiki, create_wiki_page, monkeypatch):
    """Regression: Phase 4.5 CRITICAL item 13.

    threading-only lock permits cross-process audit history loss.
    """
    page_id = "concepts/r13"
    create_wiki_page(page_id=page_id, title="R13", content="body", wiki_dir=tmp_wiki)
    from kb.review import refiner
    from kb.utils import io as io_mod

    lock_paths_acquired = []
    real_file_lock = io_mod.file_lock

    @contextmanager
    def spy_file_lock(path, timeout=5.0):
        lock_paths_acquired.append(path)
        with real_file_lock(path, timeout=timeout):
            yield

    monkeypatch.setattr(refiner, "REVIEW_HISTORY_PATH", tmp_wiki / "review_history.json")
    monkeypatch.setattr(refiner, "file_lock", spy_file_lock)
    refiner.refine_page(
        page_id=page_id,
        updated_content="updated.",
        revision_notes="n",
        wiki_dir=tmp_wiki,
    )
    assert lock_paths_acquired, "refine_page did not use file_lock for audit RMW"
    assert any("review_history" in str(p) for p in lock_paths_acquired), (
        f"expected review_history.json locked; got {lock_paths_acquired}"
    )
