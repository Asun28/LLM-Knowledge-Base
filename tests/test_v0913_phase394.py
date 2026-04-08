"""Tests for Phase 3.94 backlog fixes (v0.9.13)."""


# ── Task 1: BM25 & Query Engine ─────────────────────────────────────────────


class TestBM25DuplicateTokens:
    def test_duplicate_tokens_do_not_inflate_score(self):
        from kb.query.bm25 import BM25Index

        docs = [["neural", "network", "training"], ["python", "code"]]
        index = BM25Index(docs)
        score_single = index.score(["neural"])[0]
        score_double = index.score(["neural", "neural"])[0]
        assert score_single == score_double, (
            f"Duplicate tokens inflated score: single={score_single}, double={score_double}"
        )

    def test_unique_tokens_still_sum_correctly(self):
        from kb.query.bm25 import BM25Index

        docs = [["neural", "network"], ["python", "code"]]
        index = BM25Index(docs)
        score_two = index.score(["neural", "network"])[0]
        score_one = index.score(["neural"])[0]
        assert score_two > score_one


class TestQueryEngineMaxResults:
    def test_max_results_clamped_at_library_level(self, tmp_wiki, create_wiki_page):
        from kb.config import MAX_SEARCH_RESULTS
        from kb.query.engine import search_pages

        for i in range(5):
            create_wiki_page(
                page_id=f"concepts/test-concept-{i}",
                title=f"Test Concept {i}",
                content=f"alpha beta gamma test content {i}",
                wiki_dir=tmp_wiki,
            )
        results = search_pages("alpha beta gamma test", wiki_dir=tmp_wiki, max_results=9999)
        assert len(results) <= MAX_SEARCH_RESULTS


class TestQueryContextTopPageWarning:
    def test_warns_when_top_page_excluded_by_limit(self, caplog):
        import logging

        from kb.query.engine import _build_query_context

        big_page = {
            "id": "concepts/big",
            "type": "concept",
            "confidence": "stated",
            "title": "Big Page",
            "content": "x" * 1000,
        }
        small_page = {
            "id": "concepts/small",
            "type": "concept",
            "confidence": "stated",
            "title": "Small Page",
            "content": "y" * 10,
        }
        with caplog.at_level(logging.WARNING, logger="kb.query.engine"):
            _build_query_context([big_page, small_page], max_chars=100)
        assert any("big" in r.message.lower() for r in caplog.records), (
            "Expected WARNING mentioning excluded top-page 'big'"
        )


class TestCitationsWikilinkNormalization:
    def test_wikilink_wrapped_path_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: [[concepts/rag]]] for details."
        citations = extract_citations(text)
        paths = [c["path"] for c in citations]
        assert "concepts/rag" in paths, f"Expected 'concepts/rag' in {paths}"

    def test_plain_path_still_extracted(self):
        from kb.query.citations import extract_citations

        text = "See [source: concepts/rag] for details."
        citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0]["path"] == "concepts/rag"
