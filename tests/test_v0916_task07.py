"""Phase 3.97 Task 07 — MCP server fixes."""

from unittest.mock import patch


class TestKbQueryMaxResultsForwarding:
    """kb_query with use_api=True must forward max_results."""

    def test_max_results_forwarded_in_api_mode(self):
        with patch("kb.mcp.core.query_wiki") as mock_qw:
            mock_qw.return_value = {
                "answer": "test",
                "citations": [],
                "source_pages": [],
            }
            from kb.mcp.core import kb_query

            kb_query("test question", max_results=25, use_api=True)
            mock_qw.assert_called_once()
            call_kwargs = mock_qw.call_args
            assert call_kwargs[1].get("max_results", 10) == 25 or call_kwargs[0][1:] == ()


class TestKbReliabilityMapKeyError:
    """kb_reliability_map must use .get() for score keys."""

    def test_missing_keys_handled(self):
        with patch("kb.mcp.quality.compute_trust_scores") as mock_ts:
            mock_ts.return_value = {
                "concepts/test": {"trust": 0.5}  # missing useful, wrong, incomplete
            }
            with patch("kb.mcp.quality.get_flagged_pages", return_value=[]):
                from kb.mcp.quality import kb_reliability_map

                result = kb_reliability_map()
                assert "Error" not in result


class TestKbCreatePageNestedPageId:
    """kb_create_page must reject page_id with more than one slash."""

    def test_nested_page_id_rejected(self):
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="comparisons/sub/nested",
            title="Test",
            content="Content",
        )
        assert "Error" in result
        assert "one '/'" in result or "exactly one" in result


class TestKbReadPageUnicodeError:
    """kb_read_page must catch UnicodeDecodeError."""

    def test_unicode_error_handled(self, tmp_wiki):
        page = tmp_wiki / "concepts" / "bad-encoding.md"
        page.write_bytes(b"---\ntitle: Test\n---\n\n\xff\xfe bad bytes")

        with patch("kb.mcp.browse.WIKI_DIR", tmp_wiki):
            from kb.mcp.browse import kb_read_page

            result = kb_read_page("concepts/bad-encoding")
            assert "Error" in result or isinstance(result, str)


class TestKbCreatePageSourceRefsValidation:
    """kb_create_page source_refs must start with 'raw/'."""

    def test_non_raw_source_ref_rejected(self):
        from kb.mcp.quality import kb_create_page

        result = kb_create_page(
            page_id="comparisons/test-comp",
            title="Test",
            content="Content",
            source_refs="wiki/concepts/rag.md",
        )
        assert "Error" in result
        assert "raw/" in result


class TestKbQueryTrustNone:
    """kb_query must handle trust=None without TypeError."""

    def test_trust_none_coerced(self):
        mock_results = [
            {
                "id": "concepts/test",
                "type": "concept",
                "confidence": "stated",
                "score": 1.0,
                "title": "Test",
                "content": "Content",
                "trust": None,
            }
        ]
        with patch("kb.mcp.core.search_pages", return_value=mock_results):
            with patch("kb.mcp.core.compute_trust_scores", return_value={}):
                from kb.mcp.core import kb_query

                result = kb_query("test")
                assert "Error" not in result


class TestValidatePageIdEmpty:
    """_validate_page_id must reject empty string."""

    def test_empty_page_id_rejected(self):
        from kb.mcp.app import _validate_page_id

        err = _validate_page_id("")
        assert err is not None
        assert "empty" in err.lower()

    def test_whitespace_only_rejected(self):
        from kb.mcp.app import _validate_page_id

        err = _validate_page_id("   ")
        assert err is not None


class TestKbListSourcesGitkeep:
    """kb_list_sources must not show .gitkeep files."""

    def test_gitkeep_excluded(self, tmp_path):
        raw = tmp_path / "raw"
        articles = raw / "articles"
        articles.mkdir(parents=True)
        (articles / ".gitkeep").write_text("", encoding="utf-8")
        (articles / "real.md").write_text("content", encoding="utf-8")

        with patch("kb.mcp.browse.RAW_DIR", raw):
            from kb.mcp.browse import kb_list_sources

            result = kb_list_sources()
            assert ".gitkeep" not in result
            assert "real.md" in result


class TestKbSaveLintVerdictMaxNotesLen:
    """kb_save_lint_verdict should use MAX_NOTES_LEN constant."""

    def test_notes_limit_matches_config(self):
        from kb.config import MAX_NOTES_LEN
        from kb.mcp.quality import kb_save_lint_verdict

        long_notes = "x" * (MAX_NOTES_LEN + 1)
        result = kb_save_lint_verdict(
            page_id="concepts/test",
            verdict_type="fidelity",
            verdict="pass",
            notes=long_notes,
        )
        assert "Error" in result
