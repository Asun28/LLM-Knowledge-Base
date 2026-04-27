"""Tests for MCP browse and health tools (kb.mcp.browse, kb.mcp.health)."""

import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import kb.config
import kb.mcp.app
import kb.mcp.browse
import kb.utils.pages
from kb.config import PROJECT_ROOT
from kb.lint._safe_call import _safe_call
from kb.lint.runner import run_all_checks
from kb.mcp import browse, health
from kb.mcp.app import _sanitize_error_str, _validate_wiki_dir
from kb.mcp.browse import (
    kb_list_pages,
    kb_list_sources,
    kb_read_page,
    kb_search,
    kb_stats,
)
from kb.mcp.health import (
    kb_detect_drift,
    kb_evolve,
    kb_graph_viz,
    kb_lint,
    kb_verdict_trends,
)

# ── Helpers ──────────────────────────────────────────────────────


def _setup_browse_dirs(tmp_project, monkeypatch):
    """Monkeypatch config and module-level paths for browse tools."""
    wiki_dir = tmp_project / "wiki"
    raw_dir = tmp_project / "raw"
    monkeypatch.setattr(kb.config, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.config, "RAW_DIR", raw_dir)
    # Patch module-level imports bound at import time
    monkeypatch.setattr(kb.mcp.browse, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.mcp.browse, "RAW_DIR", raw_dir)
    monkeypatch.setattr(kb.mcp.app, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.utils.pages, "WIKI_DIR", wiki_dir)
    return wiki_dir, raw_dir


# ── kb_search ────────────────────────────────────────────────────


def test_kb_search_returns_results(tmp_project, monkeypatch, create_wiki_page):
    """kb_search finds pages matching a keyword query."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/retrieval-augmented-generation",
        title="Retrieval Augmented Generation",
        content="RAG combines retrieval with generation for grounded answers.",
        wiki_dir=wiki_dir,
    )
    create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="OpenAI builds large language models.",
        wiki_dir=wiki_dir,
    )

    result = kb_search("retrieval augmented generation")
    assert "Found" in result
    assert "retrieval-augmented-generation" in result


def test_kb_search_no_results(tmp_project, monkeypatch, create_wiki_page):
    """kb_search returns a 'no matches' message for nonexistent terms."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Retrieval augmented generation.",
        wiki_dir=wiki_dir,
    )

    result = kb_search("xyzzyplugh")
    assert result == "No matching pages found."


def test_kb_search_max_results_clamped(tmp_project, monkeypatch, create_wiki_page):
    """kb_search clamps max_results > 100 to 100 (no crash)."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Retrieval augmented generation.",
        wiki_dir=wiki_dir,
    )

    # Should not error — internally clamped to 100
    result = kb_search("retrieval", max_results=999)
    assert isinstance(result, str)
    # Either finds results or returns no-match — no crash
    assert "Found" in result or "No matching" in result


# ── kb_read_page ─────────────────────────────────────────────────


def test_kb_read_page_exists(tmp_project, monkeypatch, create_wiki_page):
    """kb_read_page returns the full content of an existing page."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="RAG is retrieval augmented generation.",
        wiki_dir=wiki_dir,
    )

    result = kb_read_page("concepts/rag")
    assert "RAG" in result
    assert "retrieval augmented generation" in result
    # Should contain frontmatter
    assert "title:" in result


def test_kb_read_page_not_found(tmp_project, monkeypatch):
    """kb_read_page returns 'not found' error for a nonexistent page."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    result = kb_read_page("concepts/nonexistent")
    assert "not found" in result.lower() or "Page not found" in result


def test_kb_read_page_traversal_blocked(tmp_project, monkeypatch):
    """kb_read_page blocks path traversal attempts with '..'."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    result = kb_read_page("../../../etc/passwd")
    assert "Error" in result or "Invalid" in result


def test_kb_read_page_case_insensitive_fallback(tmp_project, monkeypatch, create_wiki_page):
    """kb_read_page falls back to case-insensitive match when exact path missing."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="About OpenAI.",
        page_type="entity",
        wiki_dir=wiki_dir,
    )

    # Request with different case — should still find entities/openai.md
    result = kb_read_page("entities/OpenAI")
    assert "OpenAI" in result
    assert "Error" not in result


# ── Cycle 10 AC21: kb_read_page ambiguous case-insensitive page_id (cycle 43 fold) ─


def test_kb_read_page_rejects_case_insensitive_ambiguity_regression_pin(
    tmp_path, tmp_wiki, monkeypatch
):
    """Cycle 10 AC21 fold: two wiki files differing only in case (foo-bar.md vs
    Foo-Bar.md) must surface an ambiguity error from kb_read_page rather than
    silently picking one. Skipped on case-insensitive filesystems via a
    capability probe so the assertion only runs where the precondition holds.
    """
    probe_dir = tmp_path / "case_probe"
    probe_dir.mkdir()
    upper_probe = probe_dir / "Foo.md"
    lower_probe = probe_dir / "foo.md"
    upper_probe.write_text("upper", encoding="utf-8")
    lower_probe.write_text("lower", encoding="utf-8")
    if upper_probe.read_text(encoding="utf-8") == lower_probe.read_text(encoding="utf-8"):
        pytest.skip("case-insensitive FS detected via capability probe")

    concepts_dir = tmp_wiki / "concepts"
    (concepts_dir / "foo-bar.md").write_text("lower content", encoding="utf-8")
    (concepts_dir / "Foo-Bar.md").write_text("upper content", encoding="utf-8")
    monkeypatch.setattr(kb.config, "WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(kb.mcp.app, "WIKI_DIR", tmp_wiki)
    monkeypatch.setattr(browse, "WIKI_DIR", tmp_wiki)

    result = browse.kb_read_page("concepts/FOO-BAR")

    assert result.startswith("Error: ambiguous page_id")
    assert "foo-bar" in result
    assert "Foo-Bar" in result


# ── kb_list_pages ────────────────────────────────────────────────


def test_kb_list_pages_all(tmp_project, monkeypatch, create_wiki_page):
    """kb_list_pages lists all wiki pages with correct count."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page("concepts/rag", title="RAG", content="About RAG.", wiki_dir=wiki_dir)
    create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="About OpenAI.",
        page_type="entity",
        wiki_dir=wiki_dir,
    )
    create_wiki_page(
        "summaries/test-article",
        title="Test Article",
        content="Summary.",
        page_type="summary",
        wiki_dir=wiki_dir,
    )

    result = kb_list_pages()
    assert "Total: 3 page(s)" in result
    assert "concepts/rag" in result
    assert "entities/openai" in result
    assert "summaries/test-article" in result


def test_kb_list_pages_filtered(tmp_project, monkeypatch, create_wiki_page):
    """kb_list_pages filters by page type prefix."""
    wiki_dir, _ = _setup_browse_dirs(tmp_project, monkeypatch)
    create_wiki_page("concepts/rag", title="RAG", content="About RAG.", wiki_dir=wiki_dir)
    create_wiki_page("concepts/llm", title="LLM", content="About LLM.", wiki_dir=wiki_dir)
    create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="About OpenAI.",
        page_type="entity",
        wiki_dir=wiki_dir,
    )

    result = kb_list_pages(page_type="concepts")
    assert "Total: 2 page(s)" in result
    assert "concepts/rag" in result
    assert "concepts/llm" in result
    assert "entities/openai" not in result


# ── kb_list_sources ──────────────────────────────────────────────


def test_kb_list_sources_empty(tmp_project, monkeypatch):
    """kb_list_sources returns zero count when raw dir has no files."""
    _, raw_dir = _setup_browse_dirs(tmp_project, monkeypatch)
    # raw subdirectories exist but are empty (created by tmp_project fixture)

    result = kb_list_sources()
    assert "Total:" in result
    assert "0 source file(s)" in result


# ── kb_stats ─────────────────────────────────────────────────────


def test_kb_stats_runs(tmp_project, monkeypatch):
    """kb_stats returns formatted statistics via mocked analyze_coverage and graph_stats."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    mock_coverage = {
        "total_pages": 42,
        "by_type": {"concept": 20, "entity": 15, "summary": 7},
        "under_covered_types": ["comparison"],
        "orphan_concepts": ["concepts/orphan-one"],
    }
    mock_stats = {
        "nodes": 42,
        "edges": 78,
        "components": 3,
        "most_linked": [("entities/openai", 10), ("concepts/rag", 8)],
        "pagerank": [("entities/openai", 0.085), ("concepts/rag", 0.072)],
        "bridge_nodes": [("concepts/llm", 0.15)],
    }

    # Lazy imports inside kb_stats — patch at the source module
    with (
        patch("kb.evolve.analyzer.analyze_coverage", return_value=mock_coverage) as mock_cov,
        patch("kb.graph.builder.build_graph", return_value="fake_graph") as mock_bg,
        patch("kb.graph.builder.graph_stats", return_value=mock_stats) as mock_gs,
    ):
        result = kb_stats()

    mock_cov.assert_called_once()
    mock_bg.assert_called_once()
    mock_gs.assert_called_once_with("fake_graph")

    assert "Wiki Statistics" in result
    assert "42" in result  # total pages
    assert "concept: 20" in result
    assert "entity: 15" in result
    assert "78 edges" in result
    assert "3 component(s)" in result
    assert "comparison" in result  # missing type
    assert "orphan-one" in result  # orphan concept
    assert "entities/openai" in result  # most linked + pagerank
    assert "concepts/llm" in result  # bridge node


def test_kb_stats_error_handling(tmp_project, monkeypatch):
    """kb_stats returns an error message when underlying functions fail."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy import — patch at source module
    with patch("kb.evolve.analyzer.analyze_coverage", side_effect=RuntimeError("boom")):
        result = kb_stats()

    assert "Error" in result
    assert "boom" in result


# ── kb_lint ──────────────────────────────────────────────────────


def test_kb_lint_runs(tmp_project, monkeypatch):
    """kb_lint returns a formatted lint report via mocked run_all_checks."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy imports inside kb_lint — patch at source module
    mock_report = {"errors": [], "warnings": []}
    mock_text = "# Lint Report\n\nAll checks passed."
    with (
        patch("kb.lint.runner.run_all_checks", return_value=mock_report) as mock_rac,
        patch("kb.lint.runner.format_report", return_value=mock_text) as mock_fr,
    ):
        result = kb_lint()

    mock_rac.assert_called_once()
    mock_fr.assert_called_once()
    assert "Lint Report" in result
    assert "All checks passed" in result


def test_kb_lint_error_handling(tmp_project, monkeypatch):
    """kb_lint returns an error message when run_all_checks raises."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy import — patch at source module
    with patch("kb.lint.runner.run_all_checks", side_effect=RuntimeError("lint crash")):
        result = kb_lint()

    assert "Error" in result
    assert "lint crash" in result


# ── kb_evolve ────────────────────────────────────────────────────


def test_kb_evolve_runs(tmp_project, monkeypatch):
    """kb_evolve returns a formatted evolution report via mocked functions."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy imports inside kb_evolve — patch at source module
    with (
        patch(
            "kb.evolve.analyzer.generate_evolution_report",
            return_value={"coverage": {}, "suggestions": []},
        ) as mock_ger,
        patch(
            "kb.evolve.analyzer.format_evolution_report",
            return_value="# Wiki Evolution Report\n\nNo gaps found.",
        ) as mock_fer,
    ):
        result = kb_evolve()

    mock_ger.assert_called_once()
    mock_fer.assert_called_once()
    assert "Evolution Report" in result
    assert "No gaps found" in result


def test_kb_evolve_error_handling(tmp_project, monkeypatch):
    """kb_evolve returns an error message when analysis raises."""
    _setup_browse_dirs(tmp_project, monkeypatch)

    # Lazy import — patch at source module
    with patch(
        "kb.evolve.analyzer.generate_evolution_report",
        side_effect=RuntimeError("evolve crash"),
    ):
        result = kb_evolve()

    assert "Error" in result
    assert "evolve crash" in result


# ── _sanitize_error_str at MCP boundary ────────────────────────


class TestSanitizeErrorStrAtMCPBoundary:
    """MCP-boundary path-sanitization regression suite.

    Folded from ``tests/test_cycle10_safe_call.py`` cycle 40 (originally cycle 10).
    Covers ``_safe_call`` direct unit, ``kb_lint`` MCP surface, ``run_all_checks``
    runner surface, and ``_sanitize_error_str`` unit — all four invocation
    sites of the path-sanitization contract at the MCP boundary.
    """

    def test_safe_call_sanitises_absolute_path_in_exception_message(self, tmp_path, monkeypatch):
        secret_path = str(tmp_path / "secret.json")

        def boom():
            raise OSError(f"disk full at {secret_path}")

        monkeypatch.setattr(boom, "__name__", "boom")

        result, err = _safe_call(boom, fallback=[], label="verdict_history")

        assert result == []
        assert err is not None
        assert "disk full" in err
        assert "verdict_history_error:" in err
        assert str(tmp_path) not in err

    def test_safe_call_sanitises_absolute_path_in_feedback_exception_message(
        self, tmp_path, monkeypatch
    ):
        secret_path = str(tmp_path / "secret.json")

        def boom():
            raise OSError(f"disk full at {secret_path}")

        monkeypatch.setattr(boom, "__name__", "boom")

        result, err = _safe_call(boom, fallback=[], label="feedback")

        assert result == []
        assert err is not None
        assert "disk full" in err
        assert "feedback_error:" in err
        assert str(tmp_path) not in err

    def test_kb_lint_surfaces_sanitised_feedback_error_from_caller(
        self, tmp_project, tmp_path, monkeypatch
    ):
        def boom(*args, **kwargs):
            raise OSError(f"disk read error at {tmp_path}/feedback.json")

        monkeypatch.setattr(health, "PROJECT_ROOT", tmp_project)
        monkeypatch.setattr("kb.feedback.reliability.get_flagged_pages", boom)

        response = kb_lint(wiki_dir=str(tmp_project / "wiki"))

        assert "feedback_flagged_pages_error:" in response
        assert str(tmp_path) not in response

    def test_lint_runner_surfaces_sanitised_verdict_history_error(
        self, tmp_project, tmp_path, monkeypatch
    ):
        def boom(*args, **kwargs):
            raise OSError(f"cannot read {tmp_path}/verdicts.json")

        monkeypatch.setattr("kb.lint.runner.get_verdict_summary", boom)

        report = run_all_checks(wiki_dir=tmp_project / "wiki", raw_dir=tmp_project / "raw")

        assert "verdict_history_error" in report
        assert str(tmp_path) not in report["verdict_history_error"]

    def test_sanitize_error_str_rewrites_explicit_path_before_regex_sweep(self):
        secret_path = health.PROJECT_ROOT / "raw" / "secret.json"
        exc = OSError(f"disk full at {secret_path}")

        result = _sanitize_error_str(exc, secret_path)

        assert "raw/secret.json" in result
        assert str(secret_path) not in result
        assert "<path>" not in result


# ── Cycle 10 AC15 — wiki_dir validation hardening (folded from test_cycle10_validate_wiki_dir.py) ─


def test_validate_wiki_dir_rejects_absolute_outside_project_root(tmp_path):
    outside = tmp_path / "outside_project_root_cycle10"
    outside.mkdir()
    assert not outside.resolve().is_relative_to(PROJECT_ROOT.resolve())

    path, err = _validate_wiki_dir(str(outside))

    assert path is None
    assert err is not None
    assert err.startswith("wiki_dir must be inside project root")


def test_validate_wiki_dir_accepts_project_wiki_subdir(tmp_project, monkeypatch):
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    wiki = tmp_project / "wiki"

    path, err = _validate_wiki_dir(str(wiki), project_root=tmp_project)

    assert err is None
    assert path == wiki.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="symlink semantics differ")
def test_validate_wiki_dir_symlink_to_outside_rejected(tmp_project, tmp_path_factory, monkeypatch):
    # Cycle 36 AC11 fix — pre-cycle-36 used `tmp_path` which is the SAME
    # pytest dir as `tmp_project` (conftest.py `tmp_project` returns
    # tmp_path), so `outside = tmp_path / "..."` was actually INSIDE
    # tmp_project and the is_relative_to check passed. Use tmp_path_factory
    # to get a sibling tmp dir guaranteed outside tmp_project.
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    outside_root = tmp_path_factory.mktemp("outside_cycle10")
    outside = outside_root / "target"
    outside.mkdir()
    link = tmp_project / "wiki_link"
    link.symlink_to(outside, target_is_directory=True)

    path, err = _validate_wiki_dir(str(link), project_root=tmp_project)

    assert path is None
    assert err is not None
    assert err.startswith("wiki_dir must be inside project root")


def test_kb_stats_respects_wiki_dir_override_and_rejects_traversal(
    tmp_project, create_wiki_page, monkeypatch
):
    wiki = tmp_project / "wiki"
    create_wiki_page(
        "entities/openai",
        title="OpenAI",
        content="Entity body.",
        page_type="entity",
        wiki_dir=wiki,
    )
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Concept body.",
        page_type="concept",
        wiki_dir=wiki,
    )
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(browse, "PROJECT_ROOT", tmp_project)

    result = browse.kb_stats(wiki_dir=str(wiki))

    assert not result.startswith("Error:")
    assert "2" in result

    traversal = browse.kb_stats(wiki_dir="../../evil")

    assert traversal.startswith("Error: wiki_dir ")


def _allow_tmp_project_wiki_dir(tmp_project, monkeypatch) -> Path:
    wiki = tmp_project / "wiki"
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(health, "PROJECT_ROOT", tmp_project)
    return wiki


def test_validate_wiki_dir_is_threadsafe_with_explicit_project_root(tmp_path):
    results: list[tuple[int, Path | None, str | None]] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        wiki = tmp_path / f"t{i}" / "wiki"
        wiki.mkdir(parents=True)
        path, err = _validate_wiki_dir(str(wiki), project_root=wiki.parent)
        with lock:
            results.append((i, path, err))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 20
    for i, path, err in results:
        expected = (tmp_path / f"t{i}" / "wiki").resolve()
        assert err is None
        assert path == expected

    outside = tmp_path / "outside" / "wiki"
    outside.mkdir(parents=True)
    path, err = _validate_wiki_dir(str(outside), project_root=tmp_path / "inside")
    assert path is None
    assert err is not None
    assert err.startswith("wiki_dir must be inside project root")


def test_kb_graph_viz_respects_wiki_dir_override_and_rejects_traversal(
    tmp_project, create_wiki_page, monkeypatch
):
    wiki = _allow_tmp_project_wiki_dir(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Concept body.",
        page_type="concept",
        wiki_dir=wiki,
    )

    result = kb_graph_viz(wiki_dir=str(wiki))

    assert not result.startswith("Error:")
    assert "graph LR" in result

    traversal = kb_graph_viz(wiki_dir="../../evil")

    assert traversal.startswith("Error: wiki_dir ")


def test_kb_verdict_trends_respects_wiki_dir_override_and_rejects_traversal(
    tmp_project, create_wiki_page, monkeypatch
):
    wiki = _allow_tmp_project_wiki_dir(tmp_project, monkeypatch)
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Concept body.",
        page_type="concept",
        wiki_dir=wiki,
    )
    data_dir = tmp_project / ".data"
    data_dir.mkdir(exist_ok=True)
    verdicts = [
        {
            "timestamp": datetime(2026, 4, 6, tzinfo=UTC).isoformat(),
            "page_id": "concepts/rag",
            "verdict_type": "fidelity",
            "verdict": "pass",
        }
    ]
    (data_dir / "verdicts.json").write_text(json.dumps(verdicts), encoding="utf-8")

    result = kb_verdict_trends(wiki_dir=str(wiki))

    assert not result.startswith("Error:")
    assert "**Total verdicts:** 1" in result

    traversal = kb_verdict_trends(wiki_dir="../../evil")

    assert traversal.startswith("Error: wiki_dir ")


def test_kb_detect_drift_respects_wiki_dir_override_and_rejects_traversal(
    tmp_project, create_wiki_page, monkeypatch
):
    from kb.compile import compiler

    wiki = _allow_tmp_project_wiki_dir(tmp_project, monkeypatch)
    raw_dir = tmp_project / "raw"
    create_wiki_page(
        "concepts/rag",
        title="RAG",
        content="Concept body.",
        source_ref="raw/articles/test.md",
        page_type="concept",
        wiki_dir=wiki,
    )
    (raw_dir / "articles" / "test.md").write_text("# Test\n", encoding="utf-8")
    data_dir = tmp_project / ".data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(compiler, "RAW_DIR", raw_dir)
    monkeypatch.setattr(compiler, "HASH_MANIFEST", data_dir / "hashes.json")

    result = kb_detect_drift(wiki_dir=str(wiki))

    assert not result.startswith("Error:")
    assert "# Source Drift Detection" in result

    traversal = kb_detect_drift(wiki_dir="../../evil")

    assert traversal.startswith("Error: wiki_dir ")


@pytest.mark.parametrize(
    "tool",
    [browse.kb_stats, kb_graph_viz, kb_verdict_trends, kb_detect_drift],
)
def test_all_four_tools_return_consistent_error_shape(tmp_project, monkeypatch, tool):
    _allow_tmp_project_wiki_dir(tmp_project, monkeypatch)

    result = tool(wiki_dir="../../evil")

    assert result.startswith("Error: wiki_dir ")
