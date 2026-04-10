"""Phase 3.96 Task 4 — Query, BM25, and Citation fixes."""


class TestExtractCitationsNoDeadCode:
    def test_wikilink_in_citation_not_normalized(self):
        from kb.query.citations import extract_citations

        # The dead re.sub used to normalize [[wikilinks]] inside citation text.
        # After removal, wikilinks in surrounding text don't affect extraction.
        text = "According to [[concepts/rag]], this is true. [source: concepts/rag]"
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "concepts/rag"

    def test_plain_citation_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: entities/gpt-4] for details."
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "entities/gpt-4"
        assert result[0]["type"] == "wiki"

    def test_ref_citation_extracted(self):
        from kb.query.citations import extract_citations

        text = "Documented in [ref: raw/papers/paper.md]."
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "raw/papers/paper.md"
        assert result[0]["type"] == "raw"


class TestCitationPathTraversal:
    def test_dot_slash_prefix_rejected(self):
        from kb.query.citations import extract_citations

        text = "[source: ./config]"
        result = extract_citations(text)
        assert result == []

    def test_dot_dot_rejected(self):
        from kb.query.citations import extract_citations

        text = "[source: ../secret]"
        result = extract_citations(text)
        assert result == []

    def test_leading_slash_rejected(self):
        from kb.query.citations import extract_citations

        text = "[source: /etc/passwd]"
        result = extract_citations(text)
        assert result == []

    def test_normal_path_accepted(self):
        from kb.query.citations import extract_citations

        text = "[source: concepts/rag]"
        result = extract_citations(text)
        assert len(result) == 1
        assert result[0]["path"] == "concepts/rag"


class TestBM25TokenizeConsecutiveHyphens:
    def test_consecutive_hyphens_normalized(self):
        from kb.query.bm25 import tokenize

        # "--" should be treated as a single hyphen separator
        result = tokenize("pre--compiled model")
        assert "pre-compiled" in result or ("pre" in result and "compiled" in result)

    def test_triple_hyphen_normalized(self):
        from kb.query.bm25 import tokenize

        result = tokenize("fine---tuning")
        # Should not produce "fine---tuning" — consecutive hyphens normalized
        assert "fine---tuning" not in result

    def test_normal_hyphen_preserved(self):
        from kb.query.bm25 import tokenize

        result = tokenize("fine-tuning is important")
        assert "fine-tuning" in result


class TestBM25TokenizeRegex:
    def test_two_char_token_included(self):
        from kb.query.bm25 import tokenize

        result = tokenize("go is fast")
        assert "go" in result

    def test_single_char_excluded(self):
        from kb.query.bm25 import tokenize

        result = tokenize("a b c hello")
        assert "a" not in result
        assert "b" not in result
        assert "c" not in result
        assert "hello" in result

    def test_hyphenated_word_kept(self):
        from kb.query.bm25 import tokenize

        result = tokenize("state-of-the-art systems")
        assert "state-of-the-art" in result


class TestQueryMaxTokensConfig:
    def test_query_max_tokens_defined(self):
        from kb.config import QUERY_MAX_TOKENS

        assert QUERY_MAX_TOKENS == 2048

    def test_query_max_tokens_is_int(self):
        from kb.config import QUERY_MAX_TOKENS

        assert isinstance(QUERY_MAX_TOKENS, int)


class TestBuildQueryContextOversize:
    """Test that the top-ranked page is truncated rather than skipped when oversized."""

    def _make_page(self, page_id: str, content: str) -> dict:
        return {
            "id": page_id,
            "title": "Test Page",
            "type": "concept",
            "confidence": "stated",
            "content": content,
            "content_lower": content.lower(),
        }

    def test_top_page_truncated_not_skipped(self):
        from kb.query.engine import _build_query_context

        # Create a page with content that exceeds the budget
        large_content = "x" * 500
        page = self._make_page("concepts/big", large_content)
        result = _build_query_context([page], max_chars=200)
        # Should include the page (truncated), not return empty
        assert result["context_pages"] == ["concepts/big"]
        assert len(result["context"]) <= 200

    def test_top_page_context_within_budget(self):
        from kb.query.engine import _build_query_context

        large_content = "x" * 500
        page = self._make_page("concepts/big", large_content)
        result = _build_query_context([page], max_chars=200)
        assert len(result["context"]) <= 200

    def test_small_page_fits_normally(self):
        from kb.query.engine import _build_query_context

        page = self._make_page("concepts/small", "short content")
        result = _build_query_context([page], max_chars=10_000)
        assert result["context_pages"] == ["concepts/small"]
        assert "short content" in result["context"]

    def test_extremely_tiny_budget_returns_fallback(self):
        from kb.query.engine import _build_query_context

        # Budget smaller than even the page header — should return empty
        page = self._make_page("concepts/big", "x" * 500)
        result = _build_query_context([page], max_chars=5)
        # With a 5-char budget the header (~60 chars) won't fit — empty fallback
        assert result["context_pages"] == []
