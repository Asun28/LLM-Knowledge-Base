"""Tests for kb.review.refiner — Phase 4.5 CRITICAL regression coverage."""

from contextlib import contextmanager

from kb.review.refiner import refine_page


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


# Cycle 80 freeze-and-fold — moved verbatim from tests/test_v0915_task07.py
# (Phase 3.96 Task 7 — Review module fixes).
class TestRefinerFrontmatterGuard:
    """Fix 7.1: refine_page must reject empty frontmatter blocks."""

    def test_frontmatter_block_with_keys_rejected(self, tmp_wiki, create_wiki_page):
        """Phase 4.5 HIGH D1: guard requires key:value between fences.

        Empty fences (---\\n---) are allowed (horizontal rules). Only blocks
        containing YAML key: value lines are rejected.
        """
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test",
            "---\ntitle: Injected\ntype: entity\n---\nReal body",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" in result

    def test_normal_horizontal_rule_accepted(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test2", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test2",
            "Updated content.\n\n---\n\nMore content.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result


class TestRefinerEmptyContent:
    """Fix 7.2: refine_page must reject empty or whitespace-only content."""

    def test_empty_content_rejected(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test",
            "",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" in result

    def test_whitespace_only_rejected(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/test2", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/test2",
            "   \n  \n  ",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" in result


class TestRefinerAtomicWrite:
    """Fix 7.3: refine_page uses atomic write for page content."""

    def test_successful_write_produces_correct_content(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/atomic", wiki_dir=tmp_wiki, content="Original content.")
        result = refine_page(
            "concepts/atomic",
            "Updated content.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result
        page_path = tmp_wiki / "concepts/atomic.md"
        written = page_path.read_text(encoding="utf-8")
        assert "Updated content." in written

    def test_history_entry_created_after_successful_write(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import load_review_history, refine_page

        history_path = tmp_wiki / "history.json"
        create_wiki_page("concepts/atomic2", wiki_dir=tmp_wiki, content="Original.")
        refine_page(
            "concepts/atomic2",
            "New content.",
            revision_notes="test note",
            wiki_dir=tmp_wiki,
            history_path=history_path,
        )
        history = load_review_history(history_path)
        assert len(history) == 1
        assert history[0]["page_id"] == "concepts/atomic2"
        assert history[0]["revision_notes"] == "test note"


class TestPairPageWithSourcesYAMLError:
    """Fix 7.4: pair_page_with_sources handles malformed YAML gracefully."""

    def test_malformed_yaml_returns_error(self, tmp_wiki):
        from kb.review.context import pair_page_with_sources

        page_dir = tmp_wiki / "concepts"
        page_dir.mkdir(parents=True, exist_ok=True)
        bad_page = page_dir / "broken.md"
        # Write a file with malformed YAML frontmatter
        bad_page.write_text(
            "---\ntitle: [unclosed\nsource: raw/x.md\n---\nBody.\n", encoding="utf-8"
        )
        result = pair_page_with_sources("concepts/broken", wiki_dir=tmp_wiki)
        assert "error" in result
        assert result.get("page_id") == "concepts/broken"


class TestVerdictVocabulary:
    """Fix 7.5: build_review_checklist uses pass|warning|fail vocabulary."""

    def test_checklist_uses_correct_verdict_vocabulary(self):
        from kb.review.context import build_review_checklist

        checklist = build_review_checklist()
        # Should use the verdict vocabulary that matches add_verdict() accepted values
        assert "pass | warning | fail" in checklist
        # Should NOT use the old vocabulary
        assert "approve | revise | reject" not in checklist


class TestRefinerCRLF:
    """Fix 7.6: refiner handles CRLF line endings in stored pages."""

    def test_crlf_frontmatter_parsed_correctly(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        # Create page then manually overwrite with CRLF line endings
        create_wiki_page("concepts/crlf", wiki_dir=tmp_wiki, content="Original.")
        page_path = tmp_wiki / "concepts/crlf.md"
        lf_text = page_path.read_text(encoding="utf-8")
        crlf_text = lf_text.replace("\n", "\r\n")
        page_path.write_bytes(crlf_text.encode("utf-8"))

        result = refine_page(
            "concepts/crlf",
            "Updated body.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result, f"Got error: {result.get('error')}"
        written = page_path.read_text(encoding="utf-8")
        assert "Updated body." in written


class TestRefinerLeadingWhitespaceStripped:
    """Fix 7.7: leading whitespace stripped from updated_content before reconstruction."""

    def test_leading_newlines_stripped_from_body(self, tmp_wiki, create_wiki_page):
        from kb.review.refiner import refine_page

        create_wiki_page("concepts/strip", wiki_dir=tmp_wiki, content="Original.")
        result = refine_page(
            "concepts/strip",
            "\n\nBody with leading newlines.",
            wiki_dir=tmp_wiki,
            history_path=tmp_wiki / "history.json",
        )
        assert "error" not in result
        page_path = tmp_wiki / "concepts/strip.md"
        written = page_path.read_text(encoding="utf-8")
        # After the closing --- of frontmatter there should be exactly one blank line
        # then the body (no multiple leading blank lines from updated_content)
        assert "---\n\nBody with leading newlines." in written


# -- Cycle 93 fold from test_v0911_phase392.py (review history cap subset) --
# ── Task 2: Review history 10k cap ──────────────────────────────


class TestReviewHistoryCap:
    """review/refiner.py must cap review history at MAX_REVIEW_HISTORY_ENTRIES."""

    def test_review_history_capped_at_limit(self, tmp_path):
        """refine_page caps history at MAX_REVIEW_HISTORY_ENTRIES entries."""
        from kb.config import MAX_REVIEW_HISTORY_ENTRIES
        from kb.review.refiner import load_review_history, save_review_history

        history_path = tmp_path / "review_history.json"

        # Pre-populate with MAX entries
        entries = [
            {"timestamp": f"2026-01-01T00:00:{i % 60:02d}", "page_id": f"p{i}", "status": "applied"}
            for i in range(MAX_REVIEW_HISTORY_ENTRIES)
        ]
        save_review_history(entries, history_path)

        # Create a wiki page to refine
        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True)
        page = wiki_dir / "concepts" / "test.md"
        page.write_text(
            "---\ntitle: Test\nsource:\n  - raw/articles/a.md\n"
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nBody.",
            encoding="utf-8",
        )

        from kb.review.refiner import refine_page

        refine_page(
            "concepts/test",
            "Updated body.",
            revision_notes="test cap",
            wiki_dir=wiki_dir,
            history_path=history_path,
        )

        history = load_review_history(history_path)
        assert len(history) == MAX_REVIEW_HISTORY_ENTRIES, (
            f"Expected {MAX_REVIEW_HISTORY_ENTRIES} entries, got {len(history)}"
        )


# -- Cycle 93 fold from test_phase4_audit_security.py (refine_page subset) --


def test_kb_refine_page_accepts_valid_content(tmp_wiki, create_wiki_page):
    """Regression: Phase 4.5 CRITICAL item 3 (verify body actually written)."""
    page_id = "concepts/test-item-3"
    create_wiki_page(
        page_id=page_id,
        title="Test",
        content="Original body.\n",
        wiki_dir=tmp_wiki,
    )
    new_body = "Updated body with more detail.\n\nSecond paragraph.\n"
    result = refine_page(
        page_id=page_id,
        updated_content=new_body,
        revision_notes="tighten",
        wiki_dir=tmp_wiki,
    )
    assert isinstance(result, dict)
    assert result.get("updated") is True, f"refine_page did not report success: {result}"
    page_text = (tmp_wiki / f"{page_id}.md").read_text(encoding="utf-8")
    assert "Updated body with more detail." in page_text
    assert "Second paragraph." in page_text


# -- Cycle 93 fold from test_v0913_phase394.py (refine_page) --


class TestRefinePageHorizontalRule:
    """review/refiner.py refine_page: content starting with '---' (hr) is allowed."""

    def test_horizontal_rule_content_not_rejected(self, tmp_wiki, create_wiki_page):
        """Content starting with '---\\n' (horizontal rule) must not return error."""
        from kb.review.refiner import refine_page

        create_wiki_page(
            page_id="concepts/hr-test",
            title="HR Test",
            content="Some content.",
            wiki_dir=tmp_wiki,
        )
        result = refine_page(
            "concepts/hr-test",
            updated_content="---\n\nBelow the rule.\n",
            wiki_dir=tmp_wiki,
        )
        assert "error" not in result, f"Horizontal rule incorrectly rejected: {result}"

    def test_frontmatter_block_content_still_rejected(self, tmp_wiki, create_wiki_page):
        """Content that is a full frontmatter block (---\\nkey: val\\n---) must be rejected."""
        from kb.review.refiner import refine_page

        create_wiki_page(
            page_id="concepts/fm-test",
            title="FM Test",
            content="Some content.",
            wiki_dir=tmp_wiki,
        )
        result = refine_page(
            "concepts/fm-test",
            updated_content="---\ntitle: Injected\n---\nContent\n",
            wiki_dir=tmp_wiki,
        )
        assert "error" in result, "Frontmatter block content must be rejected"


# -- Cycle 93 fold from test_v0914_phase395.py (refine_page) --


class TestRefinePageWriteOrdering:
    """refine_page must write the page file BEFORE recording 'applied' in history."""

    def test_failed_page_write_no_history(self, tmp_wiki, monkeypatch, tmp_path):
        from kb.review.refiner import refine_page

        # Create a page to refine
        page_path = tmp_wiki / "concepts" / "test.md"
        page_path.write_text(
            '---\ntitle: "Test"\nsource:\n  - "raw/articles/test.md"\n'
            "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
            "confidence: stated\n---\n\nOriginal content.\n",
            encoding="utf-8",
        )

        history_path = tmp_path / "review_history.json"

        # Make page write fail — patch atomic_text_write since refiner now uses it
        def failing_atomic_write(content, path):
            if "test.md" in str(path) and "wiki" in str(path):
                raise OSError("disk full")
            from kb.utils.io import atomic_text_write as _real

            _real(content, path)

        monkeypatch.setattr("kb.review.refiner.atomic_text_write", failing_atomic_write)

        result = refine_page(
            "concepts/test",
            "Updated content.",
            revision_notes="Test revision",
            wiki_dir=tmp_wiki,
            history_path=history_path,
        )

        # The result should indicate an error
        assert "error" in str(result).lower() or not result.get("updated", False)

        # History should NOT contain "applied" for a failed write
        if history_path.exists():
            import json

            history = json.loads(history_path.read_text(encoding="utf-8"))
            applied = [h for h in history if h.get("status") == "applied"]
            assert len(applied) == 0, "History recorded 'applied' for a failed page write"
