"""Tests for layered context assembly (Phase 4)."""

from kb.query.engine import _build_query_context


def _page(pid, content, ptype="concept"):
    return {
        "id": pid,
        "title": pid.split("/")[-1].replace("-", " ").title(),
        "type": ptype,
        "confidence": "stated",
        "content": content,
    }


class TestLayeredContextAssembly:
    def test_short_content_fits_entirely(self):
        pages = [_page("concepts/a", "Short content.")]
        ctx = _build_query_context(pages, max_chars=10000)
        assert "concepts/a" in ctx["context"]
        assert "Short content." in ctx["context"]

    def test_summaries_prioritized_in_tier1(self):
        pages = [
            _page("concepts/big", "x" * 5000, "concept"),
            _page("summaries/small", "summary text", "summary"),
        ]
        ctx = _build_query_context(pages, max_chars=6000)
        # Both should fit within 6000 chars
        assert "summaries/small" in ctx["context_pages"]

    def test_budget_respected(self):
        pages = [_page(f"concepts/p{i}", "x" * 2000) for i in range(20)]
        ctx = _build_query_context(pages, max_chars=5000)
        assert len(ctx["context"]) <= 5500  # Allow small header overhead

    def test_empty_pages(self):
        ctx = _build_query_context([], max_chars=10000)
        assert ctx["context_pages"] == []

    def test_returns_context_pages_list(self):
        pages = [_page("concepts/a", "Content A"), _page("concepts/b", "Content B")]
        ctx = _build_query_context(pages, max_chars=10000)
        assert "concepts/a" in ctx["context_pages"]
        assert "concepts/b" in ctx["context_pages"]
