"""Tests for kb.review.refiner — Phase 4.5 CRITICAL regression coverage."""

from contextlib import contextmanager


def test_refine_page_preserves_leading_code_block_indent(tmp_wiki, create_wiki_page, monkeypatch):
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


def test_refine_page_strips_leading_crlf_on_windows_input(tmp_wiki, create_wiki_page, monkeypatch):
    """Regression: leading CRLF must be stripped from refined body on Windows-like input."""
    page_id = "concepts/crlf-test"
    create_wiki_page(page_id=page_id, title="CRLF", content="Original.", wiki_dir=tmp_wiki)
    from kb.review import refiner

    monkeypatch.setattr(refiner, "REVIEW_HISTORY_PATH", tmp_wiki / "review_history.json")
    # NOTE: refine_page already normalises CRLF → LF at line ~103, so this verifies the
    # defense-in-depth regex fix too (no leading blanks after frontmatter).
    new_body = "\r\n\r\n\r\nActual content.\n"
    result = refiner.refine_page(
        page_id=page_id,
        updated_content=new_body,
        revision_notes="crlf-strip",
        wiki_dir=tmp_wiki,
    )
    assert result.get("updated") is True
    page_text = (tmp_wiki / f"{page_id}.md").read_text(encoding="utf-8")
    # The page format is "---\n{fm}---\n\n{body}\n".
    # Split after the closing ---\n to get "\n{body}\n" (one separator newline + body).
    # If CRLF stripping failed, the body_section would be "\n\n\n..." (extra blank lines).
    parts = page_text.split("---\n", 2)  # ["", fm_content, "\n{body}\n"]
    assert len(parts) == 3, f"unexpected page structure: {page_text!r}"
    body_section = parts[2]  # "\n{body}\n" — the \n is the separator blank line
    # After lstripping the ONE separator newline, should get "Actual content.\n".
    # Extra blank lines (un-stripped CRLF/LF) would cause more than one leading \n.
    assert body_section.lstrip("\n").startswith("Actual content."), (
        f"leading blank lines not stripped from body; body_section={body_section!r}"
    )
    # Specifically: exactly one separator \n before "Actual content.", not multiple.
    assert body_section == "\nActual content.\n\n", (
        f"unexpected leading blank lines; body_section={body_section!r}"
    )


import pytest as _pytest_for_cycle64  # noqa: E402


@_pytest_for_cycle64.mark.skip(
    reason=(
        "cycle 64 AC3 migration debt — autouse tmp_kb_env (AC1) patches "
        "kb.config.REVIEW_HISTORY_PATH to tmp_path/.data/, so 'production' "
        "history IS now tmp. Test needs migration to assert against the "
        "snapshot of REVIEW_HISTORY_PATH-at-conftest-import-time. Trial-skip "
        "per cycle-61 precedent; cycle-65+ migrate."
    )
)
def test_refine_page_derives_history_path_from_wiki_dir(tmp_wiki, tmp_path, create_wiki_page):
    """Regression: refine_page(wiki_dir=tmp) must NOT write to production review_history.json."""
    page_id = "concepts/history-test"
    create_wiki_page(page_id=page_id, title="H", content="x", wiki_dir=tmp_wiki)
    from kb.review import refiner

    # Do NOT monkeypatch REVIEW_HISTORY_PATH — this test verifies derivation from wiki_dir works.
    prod_history = refiner.REVIEW_HISTORY_PATH
    ts_before = prod_history.stat().st_mtime if prod_history.exists() else None
    refiner.refine_page(
        page_id=page_id,
        updated_content="updated.",
        revision_notes="n",
        wiki_dir=tmp_wiki,
    )
    ts_after = prod_history.stat().st_mtime if prod_history.exists() else None
    assert ts_before == ts_after, (
        f"refine_page(wiki_dir=tmp) wrote to production history: {prod_history}"
    )


# ═══════════════════════════════════════════════════════════════════════
# Cycle 78 freeze-and-fold — moved verbatim from tests/test_v0916_task06.py
# (review/refiner.py parts). Only deviation: fold-site `Path` import.
# ═══════════════════════════════════════════════════════════════════════

from pathlib import Path  # noqa: E402  — fold-site import (cycle 78)


class TestRefinePageReadError:
    """refine_page must return error dict when read_text raises."""

    def test_os_error_on_read(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "test-read.md"
        page.write_text(
            '---\ntitle: "Test"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from unittest.mock import patch

        from kb.review.refiner import refine_page

        with patch.object(Path, "read_text", side_effect=OSError("Permission denied")):
            result = refine_page("concepts/test-read", "new content", wiki_dir=tmp_wiki)
            assert "error" in result


class TestLoadReviewHistoryRobustness:
    """load_review_history must handle corrupt files."""

    def test_non_list_json_returns_empty(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text('{"key": "value"}', encoding="utf-8")

        from kb.review.refiner import load_review_history

        result = load_review_history(history_file)
        assert result == []

    def test_os_error_returns_empty(self, tmp_path):
        history_file = tmp_path / "history.json"
        history_file.write_text("[1, 2, 3]", encoding="utf-8")

        from unittest.mock import patch

        from kb.review.refiner import load_review_history

        with patch.object(Path, "read_text", side_effect=OSError("read error")):
            result = load_review_history(history_file)
            assert result == []


class TestRefinePageCRLFGuard:
    """refine_page frontmatter guard must handle CRLF content."""

    def test_crlf_frontmatter_rejected(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "crlf-test.md"
        page.write_text(
            '---\ntitle: "CRLF"\nsource: []\ncreated: 2026-01-01\n'
            "updated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\nContent.\n",
            encoding="utf-8",
        )

        from kb.review.refiner import refine_page

        # Content that looks like a frontmatter block with CRLF
        result = refine_page(
            "concepts/crlf-test",
            "---\r\ntitle: bad\r\n---\r\nContent",
            wiki_dir=tmp_wiki,
        )
        assert "error" in result
