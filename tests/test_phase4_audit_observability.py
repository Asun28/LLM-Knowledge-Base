"""Tests for observability fixes — Phase 4 audit."""

import logging
from unittest.mock import MagicMock, patch

import anthropic
import pytest


def test_llm_last_retry_logs_giving_up(caplog):
    """On final attempt, log must say 'giving up', not 'retrying'."""
    from kb.utils import llm as llm_mod
    from kb.utils.llm import _make_api_call

    mock_resp = MagicMock(status_code=429, headers={})

    with patch.object(llm_mod, "get_client") as mock_client:
        mock_client.return_value.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited", response=mock_resp, body={}
        )
        with caplog.at_level(logging.WARNING, logger="kb.utils.llm"):
            with pytest.raises(Exception):
                _make_api_call({"model": "test", "messages": [], "max_tokens": 1}, "test-model")

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_messages, "No warnings were logged"
    last_warning = warning_messages[-1]
    assert "retrying" not in last_warning.lower(), (
        f"Last warning still says 'retrying': {last_warning!r}"
    )
    assert "giving up" in last_warning.lower(), (
        f"Last warning does not say 'giving up': {last_warning!r}"
    )


def test_llm_intermediate_retry_logs_retrying(caplog):
    """Before the final attempt, log must say 'retrying'."""
    from kb.utils import llm as llm_mod
    from kb.utils.llm import MAX_RETRIES, _make_api_call

    if MAX_RETRIES < 1:
        pytest.skip("Need at least 1 retry to test intermediate logs")

    call_count = [0]
    mock_resp = MagicMock(status_code=429, headers={})

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        raise anthropic.RateLimitError(message="rate limited", response=mock_resp, body={})

    with patch.object(llm_mod, "get_client") as mock_client:
        with patch.object(llm_mod, "time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_client.return_value.messages.create.side_effect = side_effect
            with caplog.at_level(logging.WARNING, logger="kb.utils.llm"):
                with pytest.raises(Exception):
                    _make_api_call({"model": "test", "messages": [], "max_tokens": 1}, "test-model")

    warning_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_messages) >= 2, "Expected at least 2 warnings (intermediate + final)"
    # First warning (not final attempt) must say retrying
    assert "retrying" in warning_messages[0].lower()


def test_pagerank_failure_logs_warning(caplog):
    """PageRank convergence failure must emit a warning with the graph size."""
    import networkx as nx

    from kb.graph.builder import graph_stats

    g = nx.DiGraph()
    g.add_edges_from([("a", "b"), ("b", "a"), ("c", "a")])

    with patch("networkx.pagerank", side_effect=nx.PowerIterationFailedConvergence(100)):
        with caplog.at_level(logging.WARNING, logger="kb.graph.builder"):
            stats = graph_stats(g)

    assert stats["pagerank"] == []
    warning_texts = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert (
        "pagerank" in warning_texts.lower()
        or "converge" in warning_texts.lower()
        or "failed" in warning_texts.lower()
    )


def test_vector_search_failure_logs_warning(caplog, tmp_path):
    """sqlite_vec load failure must emit a WARNING, not silently return []."""

    from kb.query.embeddings import VectorIndex

    idx = VectorIndex(tmp_path / "test.db")

    # Simulate a populated index (so the code reaches the extension-load step)
    with patch.object(idx, "db_path") as mock_path:
        mock_path.exists.return_value = True
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.enable_load_extension = MagicMock()
            mock_connect.return_value = mock_conn

            import builtins

            real_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name == "sqlite_vec":
                    raise ImportError("sqlite_vec not found")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=fake_import):
                with caplog.at_level(logging.WARNING, logger="kb.query.embeddings"):
                    results = idx.query([0.1] * 256, limit=5)

    assert results == []
    warning_texts = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING)
    assert (
        "sqlite_vec" in warning_texts.lower()
        or "vector" in warning_texts.lower()
        or "extension" in warning_texts.lower()
    )
