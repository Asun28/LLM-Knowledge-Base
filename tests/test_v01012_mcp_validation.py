"""Tests for Phase 4 MCP validation fixes."""

from __future__ import annotations


def test_kb_query_feedback_rejects_long_question():
    from kb.config import MAX_QUESTION_LEN
    from kb.mcp.quality import kb_query_feedback

    result = kb_query_feedback("x" * (MAX_QUESTION_LEN + 1), rating="helpful", cited_pages="")
    assert isinstance(result, str) and result.startswith("Error:")


def test_kb_lint_consistency_caps_page_ids():
    from kb.mcp.quality import kb_lint_consistency

    ids = ",".join(f"concepts/p{i}" for i in range(60))
    result = kb_lint_consistency(ids)
    assert isinstance(result, str) and result.startswith("Error:") and "50" in result


def test_kb_graph_viz_zero_nodes_uses_default():
    from kb.mcp.health import kb_graph_viz

    result = kb_graph_viz(max_nodes=0)
    # Must not produce unbounded output — should work like max_nodes=30
    assert result is not None
    assert isinstance(result, str)


def test_kb_list_pages_rejects_invalid_type():
    from kb.mcp.browse import kb_list_pages

    result = kb_list_pages(page_type="bogus_type_that_doesnt_exist")
    assert isinstance(result, str) and result.startswith("Error:")


def test_kb_save_lint_verdict_caps_issues():
    # 200 issues — should be capped; pass as JSON array
    import json

    from kb.mcp.quality import kb_save_lint_verdict

    issues_list = [{"severity": "low", "description": f"issue{i}"} for i in range(200)]
    issues_str = json.dumps(issues_list)
    result = kb_save_lint_verdict(
        page_id="concepts/test",
        verdict_type="fidelity",
        verdict="pass",
        issues=issues_str,
    )
    assert isinstance(result, str) and result.startswith("Error:") and "100" in result


def test_kb_query_rejects_overlong_question():
    from kb.config import MAX_QUESTION_LEN
    from kb.mcp.core import kb_query

    result = kb_query("x" * (MAX_QUESTION_LEN + 1))
    assert isinstance(result, str) and result.startswith("Error:")


def test_kb_detect_drift_none_changed_sources(monkeypatch):
    """None changed_sources must not raise TypeError."""
    from kb.mcp import health as _h

    def fake_detect(*args, **kwargs):
        return {
            "summary": "1 source changed",
            "changed_sources": ["raw/articles/foo.md"],
            "affected_pages": [{"page_id": "concepts/p1", "changed_sources": None}],
        }

    monkeypatch.setattr(_h, "detect_source_drift", fake_detect, raising=False)
    result = _h.kb_detect_drift()
    assert result is not None
    assert not (isinstance(result, str) and "Traceback" in result)
    assert isinstance(result, str)
