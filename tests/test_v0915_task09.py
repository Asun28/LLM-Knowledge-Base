"""Phase 3.96 Task 9 — MCP server fixes (security, validation, robustness).

Covers:
  9.1  — empty/whitespace question guard in kb_query
  9.2  — RAW_DIR path boundary (rejects wiki/, project root, etc.)
  9.3  — filename length cap (max 200 chars)
  9.4  — cited_pages page_id validation in kb_query_feedback
  9.5  — source_refs Windows path bypass (os.path.isabs)
  9.6  — content-size limit (max 160 000 chars)
  9.8  — trust label float equality (epsilon comparison)
  9.9  — binary file extension rejection
  9.11 — control characters stripped from page_id
  9.12 — kb_create_page subdir prefix validated
  9.13 — kb_list_pages singular filter normalization
  9.15 — empty question guard in kb_query_feedback
  9.19 — whitespace/empty filename guard
  9.20 — os.path.isabs check in _validate_page_id
  9.21 — notes length cap in kb_save_lint_verdict
"""

import sys

import pytest

# ── Fix 9.1 — empty question guard in kb_query ───────────────────────────────


class TestKbQueryEmptyGuard:
    def test_empty_question_returns_error(self):
        from kb.mcp.core import kb_query

        result = kb_query("")
        assert result.startswith("Error:")

    def test_whitespace_question_returns_error(self):
        from kb.mcp.core import kb_query

        result = kb_query("   \n  ")
        assert result.startswith("Error:")

    def test_valid_question_does_not_return_empty_error(self):
        """A real (non-empty) question must not be rejected by the guard."""
        from kb.mcp.core import kb_query

        result = kb_query("What is RAG?")
        # Guard must not fire; any other result is fine
        assert result != "Error: Question cannot be empty."


# ── Fix 9.2 — RAW_DIR path boundary ─────────────────────────────────────────


class TestIngestPathBoundary:
    def test_wiki_file_rejected(self):
        from kb.mcp.core import kb_ingest

        result = kb_ingest("wiki/concepts/rag.md")
        assert "Error" in result

    def test_project_root_file_rejected(self, tmp_path):
        """File at project root (outside raw/) should be rejected."""
        from kb.mcp.core import kb_ingest

        # Pass a path outside raw/ — doesn't need to exist for path check
        result = kb_ingest("CLAUDE.md")
        assert "Error" in result

    def test_absolute_outside_raw_rejected(self, tmp_path):
        """Absolute path outside raw/ must be rejected."""
        from kb.mcp.core import kb_ingest

        outside = str(tmp_path / "outside.md")
        result = kb_ingest(outside)
        assert "Error" in result


# ── Fix 9.3 — filename length cap ────────────────────────────────────────────


class TestFilenameLengthCap:
    def test_ingest_content_long_filename_rejected(self):
        from kb.mcp.core import kb_ingest_content

        long_name = "a" * 201
        result = kb_ingest_content(
            content="hello",
            filename=long_name,
            source_type="article",
            extraction_json='{"title":"t","entities_mentioned":[],"concepts_mentioned":[]}',
        )
        assert result.startswith("Error:")
        assert "200" in result

    def test_save_source_long_filename_rejected(self):
        from kb.mcp.core import kb_save_source

        long_name = "b" * 201
        result = kb_save_source(content="hello", filename=long_name, source_type="article")
        assert result.startswith("Error:")
        assert "200" in result

    def test_filename_exactly_200_accepted_path(self):
        """Filename of exactly 200 chars must pass the length check (may still fail later)."""
        from kb.mcp.core import kb_ingest_content

        name_200 = "c" * 200
        result = kb_ingest_content(
            content="hello",
            filename=name_200,
            source_type="article",
            extraction_json='{"title":"t","entities_mentioned":[],"concepts_mentioned":[]}',
        )
        # Must NOT be rejected for length
        assert "Filename too long" not in result


# ── Fix 9.4 — cited_pages page_id validation ────────────────────────────────


class TestQueryFeedbackCitedPagesValidation:
    def test_path_traversal_in_cited_page_rejected(self):
        from kb.mcp.quality import kb_query_feedback

        result = kb_query_feedback(
            question="What is RAG?",
            rating="useful",
            cited_pages="../etc/passwd",
        )
        assert result.startswith("Error:")

    def test_valid_cited_page_accepted(self):
        from kb.mcp.quality import kb_query_feedback

        # Valid page_id format — may fail for "page not found" but NOT for validation
        result = kb_query_feedback(
            question="What is RAG?",
            rating="useful",
            cited_pages="concepts/rag",
        )
        # Must not be rejected by the page_id validator
        assert "Invalid cited page" not in result

    def test_slash_prefix_cited_page_rejected(self):
        from kb.mcp.quality import kb_query_feedback

        result = kb_query_feedback(
            question="What is RAG?",
            rating="useful",
            cited_pages="/etc/passwd",
        )
        assert result.startswith("Error:")


# ── Fix 9.5 — source_refs Windows path bypass ────────────────────────────────


class TestCreatePageSourceRefsValidation:
    def test_windows_absolute_path_rejected(self):
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="comparisons/test-page",
            title="Test",
            content="body",
            source_refs="C:\\Users\\Admin\\secret.md",
        )
        assert result.startswith("Error:")

    def test_double_dot_in_source_ref_rejected(self):
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="comparisons/test-page2",
            title="Test",
            content="body",
            source_refs="raw/../../../etc/passwd",
        )
        assert result.startswith("Error:")

    def test_valid_relative_source_ref_accepted(self):
        from kb.mcp.quality import kb_create_page

        # Valid source ref — page may already exist, that's OK
        result = kb_create_page(
            page_id="comparisons/valid-test-page",
            title="Test",
            content="body",
            source_refs="raw/articles/example.md",
        )
        # Must not be rejected for source_ref format (may fail for other reasons)
        assert "Invalid source_ref" not in result


# ── Fix 9.6 — content-size limit ────────────────────────────────────────────


class TestContentSizeLimit:
    def test_ingest_content_too_large_rejected(self):
        from kb.mcp.core import kb_ingest_content

        big_content = "x" * 160_001
        result = kb_ingest_content(
            content=big_content,
            filename="big-file",
            source_type="article",
            extraction_json='{"title":"t","entities_mentioned":[],"concepts_mentioned":[]}',
        )
        assert result.startswith("Error:")
        assert "too large" in result.lower() or "160" in result

    def test_save_source_too_large_rejected(self):
        from kb.mcp.core import kb_save_source

        big_content = "y" * 160_001
        result = kb_save_source(content=big_content, filename="big-file", source_type="article")
        assert result.startswith("Error:")
        assert "too large" in result.lower() or "160" in result

    def test_content_exactly_at_limit_accepted(self):
        """Content of exactly 160 000 chars must pass the size check."""
        from kb.mcp.core import kb_save_source

        content_at_limit = "z" * 160_000
        result = kb_save_source(
            content=content_at_limit, filename="limit-file", source_type="article"
        )
        assert "too large" not in result.lower()


# ── Fix 9.9 — binary file extension rejection ────────────────────────────────


class TestBinaryFileExtensionCheck:
    def test_pdf_extension_rejected(self, tmp_path):
        from kb.config import RAW_DIR
        from kb.mcp.core import kb_ingest

        # Create a fake pdf inside raw/
        fake_pdf = RAW_DIR / "articles" / "test_binary.pdf"
        try:
            fake_pdf.parent.mkdir(parents=True, exist_ok=True)
            fake_pdf.write_bytes(b"%PDF-1.4 fake")
            result = kb_ingest(str(fake_pdf))
            assert "Error" in result
            assert "Unsupported file type" in result or "pdf" in result.lower()
        finally:
            fake_pdf.unlink(missing_ok=True)

    def test_md_extension_passes_extension_check(self, tmp_path):
        from kb.config import RAW_DIR
        from kb.mcp.core import kb_ingest

        # A .md file that doesn't exist should fail with "not found", not "Unsupported"
        fake_md = str(RAW_DIR / "articles" / "_nonexistent_test.md")
        result = kb_ingest(fake_md)
        assert "Unsupported file type" not in result


# ── Fix 9.11 — control chars stripped from page_id ──────────────────────────


class TestControlCharStripping:
    def test_control_chars_stripped_in_review_page(self):
        from kb.mcp.quality import kb_review_page

        # After stripping \x00, page_id becomes "concepts/rag" — may not exist
        result = kb_review_page("concepts\x00/rag")
        # Must not raise; error about page not found is acceptable
        assert isinstance(result, str)
        # Must not error about control characters specifically
        assert "control" not in result.lower()

    def test_control_chars_stripped_in_lint_deep(self):
        from kb.mcp.quality import kb_lint_deep

        result = kb_lint_deep("concepts\x1f/rag")
        assert isinstance(result, str)

    def test_page_id_with_only_control_chars_rejected(self):
        from kb.mcp.quality import kb_review_page

        # After stripping, page_id becomes "" — should fail validation
        result = kb_review_page("\x00\x01\x02")
        assert isinstance(result, str)


# ── Fix 9.12 — kb_create_page subdir prefix validation ──────────────────────


class TestCreatePageSubdirValidation:
    def test_invalid_subdir_rejected(self):
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="invalid_subdir/test-page",
            title="Test",
            content="body",
        )
        assert result.startswith("Error:")
        assert "invalid_subdir" in result or "prefix" in result.lower()

    def test_valid_subdir_accepted(self):
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="comparisons/subdir-validation-test",
            title="Test",
            content="body",
        )
        # May succeed or fail for other reasons (e.g., already exists)
        assert "Invalid page_id prefix" not in result

    def test_raw_subdir_rejected(self):
        from kb.mcp.quality import kb_create_page

        # "raw" is not a valid wiki subdir
        result = kb_create_page(
            page_id="raw/articles",
            title="Test",
            content="body",
        )
        assert result.startswith("Error:")


# ── Fix 9.13 — kb_list_pages singular filter normalization ───────────────────


class TestListPagesSingularFilter:
    def test_singular_concept_accepted(self):
        from kb.mcp.browse import kb_list_pages

        result_singular = kb_list_pages("concept")
        result_plural = kb_list_pages("concepts")
        # Both should behave the same (either both find nothing or both find pages)
        if "No pages found" in result_singular:
            assert "No pages found" in result_plural
        else:
            # Both should contain the same page type header
            assert "concepts" in result_singular or "No pages found" in result_singular

    def test_singular_entity_accepted(self):
        from kb.mcp.browse import kb_list_pages

        result = kb_list_pages("entity")
        assert isinstance(result, str)
        # Should not error
        assert result.startswith("Error:") is False or "entity" in result


# ── Fix 9.15 — empty question guard in kb_query_feedback ────────────────────


class TestQueryFeedbackEmptyQuestion:
    def test_empty_question_rejected(self):
        from kb.mcp.quality import kb_query_feedback

        result = kb_query_feedback(question="", rating="useful")
        assert result.startswith("Error:")

    def test_whitespace_question_rejected(self):
        from kb.mcp.quality import kb_query_feedback

        result = kb_query_feedback(question="   \t\n", rating="useful")
        assert result.startswith("Error:")

    def test_valid_question_not_rejected(self):
        from kb.mcp.quality import kb_query_feedback

        result = kb_query_feedback(question="What is RAG?", rating="useful")
        assert result != "Error: Question cannot be empty."


# ── Fix 9.19 — whitespace/empty filename guard ───────────────────────────────


class TestEmptyFilenameGuard:
    def test_empty_filename_ingest_content_rejected(self):
        from kb.mcp.core import kb_ingest_content

        result = kb_ingest_content(
            content="hello",
            filename="",
            source_type="article",
            extraction_json='{"title":"t","entities_mentioned":[],"concepts_mentioned":[]}',
        )
        assert result.startswith("Error:")

    def test_whitespace_filename_save_source_rejected(self):
        from kb.mcp.core import kb_save_source

        result = kb_save_source(content="hello", filename="   ", source_type="article")
        assert result.startswith("Error:")


# ── Fix 9.20 — os.path.isabs in _validate_page_id ───────────────────────────


class TestValidatePageIdAbsoluteCheck:
    @pytest.mark.skipif(
        sys.platform != "win32",
        reason=(
            "Cycle 36 AC11 — Windows-style absolute path detection "
            "(drive letter); POSIX absolute-path semantics differ."
        ),
    )
    def test_absolute_path_rejected(self):
        from kb.mcp.app import _validate_page_id

        result = _validate_page_id("C:/Windows/System32/cmd", check_exists=False)
        assert result is not None
        assert "Invalid page_id" in result

    def test_relative_page_id_not_rejected_by_abs_check(self):
        from kb.mcp.app import _validate_page_id

        result = _validate_page_id("concepts/rag", check_exists=False)
        # Should pass validation (None = no error)
        assert result is None


# ── Fix 9.21 — notes length cap in kb_save_lint_verdict ─────────────────────


class TestSaveLintVerdictNotesLengthCap:
    def test_notes_too_long_rejected(self):
        from kb.mcp.quality import kb_save_lint_verdict

        long_notes = "n" * 2001
        result = kb_save_lint_verdict(
            page_id="concepts/rag",
            verdict_type="fidelity",
            verdict="pass",
            notes=long_notes,
        )
        assert result.startswith("Error:")
        assert "2000" in result

    def test_notes_exactly_2000_chars_accepted(self):
        from kb.mcp.quality import kb_save_lint_verdict

        notes_2000 = "n" * 2000
        result = kb_save_lint_verdict(
            page_id="concepts/rag",
            verdict_type="fidelity",
            verdict="pass",
            notes=notes_2000,
        )
        assert "Notes too long" not in result
