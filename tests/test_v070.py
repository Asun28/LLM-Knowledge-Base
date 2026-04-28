"""Tests for v0.7.0 improvements — graph pagerank, case-insensitive wikilinks,
trust threshold fix, template hash detection, lint verdicts, entity enrichment,
new MCP tools, and MCP package split."""

import asyncio
from unittest.mock import patch

import networkx as nx
import pytest

# ── 1. Graph: PageRank and Centrality ────────────────────────────


def test_graph_stats_includes_pagerank(tmp_wiki, create_wiki_page):
    """graph_stats returns pagerank key."""
    create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]]")
    create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="See [[concepts/c]]")
    create_wiki_page("concepts/c", wiki_dir=tmp_wiki, content="See [[concepts/a]]")
    from kb.graph.builder import build_graph, graph_stats

    g = build_graph(tmp_wiki)
    stats = graph_stats(g)
    assert "pagerank" in stats
    assert len(stats["pagerank"]) > 0


def test_graph_stats_includes_bridge_nodes(tmp_wiki, create_wiki_page):
    """graph_stats returns bridge_nodes key."""
    create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="See [[concepts/b]]")
    create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="See [[concepts/c]]")
    create_wiki_page("concepts/c", wiki_dir=tmp_wiki, content="")
    from kb.graph.builder import build_graph, graph_stats

    g = build_graph(tmp_wiki)
    stats = graph_stats(g)
    assert "bridge_nodes" in stats


def test_graph_stats_bridge_nodes_filters_zero(tmp_wiki, create_wiki_page):
    """Bridge nodes with 0 centrality are filtered out."""
    # Two isolated pages -- no edges -- all centrality 0
    create_wiki_page("concepts/a", wiki_dir=tmp_wiki, content="No links")
    create_wiki_page("concepts/b", wiki_dir=tmp_wiki, content="No links")
    from kb.graph.builder import build_graph, graph_stats

    g = build_graph(tmp_wiki)
    stats = graph_stats(g)
    assert stats["bridge_nodes"] == []


def test_graph_stats_empty_graph():
    """graph_stats handles empty graph."""
    from kb.graph.builder import graph_stats

    g = nx.DiGraph()
    stats = graph_stats(g)
    assert stats["pagerank"] == []
    assert stats["bridge_nodes"] == []


# ── 2. Case-Insensitive Wikilinks ───────────────────────────────


def test_wikilinks_lowercase():
    """Wikilinks are normalized to lowercase."""
    from kb.utils.markdown import extract_wikilinks

    links = extract_wikilinks("See [[Concepts/RAG]] and [[ENTITIES/OpenAI]]")
    assert links == ["concepts/rag", "entities/openai"]


def test_wikilinks_with_label_lowercase():
    """Wikilinks with labels normalize the target to lowercase."""
    from kb.utils.markdown import extract_wikilinks

    links = extract_wikilinks("[[Concepts/RAG|Retrieval Augmented Gen]]")
    assert links == ["concepts/rag"]


def test_wikilinks_already_lowercase():
    """Lowercase wikilinks pass through unchanged."""
    from kb.utils.markdown import extract_wikilinks

    links = extract_wikilinks("[[concepts/rag]]")
    assert links == ["concepts/rag"]


# ── 3. Trust Threshold Boundary ──────────────────────────────────


def test_trust_at_threshold_is_flagged(tmp_path):
    """Pages with trust exactly at threshold (0.4) are flagged."""
    from kb.feedback.reliability import get_flagged_pages
    from kb.feedback.store import save_feedback

    data = {
        "entries": [],
        "page_scores": {"concepts/test": {"useful": 1, "wrong": 1, "incomplete": 0, "trust": 0.4}},
    }
    path = tmp_path / "feedback.json"
    save_feedback(data, path)
    flagged = get_flagged_pages(path, threshold=0.4)
    assert "concepts/test" in flagged


def test_trust_above_threshold_not_flagged(tmp_path):
    """Pages with trust above threshold are not flagged."""
    from kb.feedback.reliability import get_flagged_pages
    from kb.feedback.store import save_feedback

    data = {
        "entries": [],
        "page_scores": {"concepts/good": {"useful": 3, "wrong": 0, "incomplete": 0, "trust": 0.8}},
    }
    path = tmp_path / "feedback.json"
    save_feedback(data, path)
    flagged = get_flagged_pages(path, threshold=0.4)
    assert flagged == []


def test_trust_below_threshold_flagged(tmp_path):
    """Pages below threshold are flagged."""
    from kb.feedback.reliability import get_flagged_pages
    from kb.feedback.store import save_feedback

    data = {
        "entries": [],
        "page_scores": {"concepts/bad": {"useful": 0, "wrong": 2, "incomplete": 0, "trust": 0.2}},
    }
    path = tmp_path / "feedback.json"
    save_feedback(data, path)
    flagged = get_flagged_pages(path, threshold=0.4)
    assert "concepts/bad" in flagged


# ── 4. Template Hash Detection ───────────────────────────────────


def test_template_hashes_computed():
    """_template_hashes returns hash for each yaml template."""
    from kb.compile.compiler import _template_hashes

    hashes = _template_hashes()
    assert len(hashes) >= 8  # 8 original + 2 new (comparison, synthesis)
    for key in hashes:
        assert key.startswith("_template/")


def test_template_change_flags_sources(tmp_path):
    """Changed template causes sources of that type to be flagged."""
    from kb.compile.compiler import find_changed_sources, save_manifest
    from kb.config import TEMPLATES_DIR
    from kb.utils.hashing import content_hash

    # Set up raw dir with one article
    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True)
    source = raw_dir / "articles" / "test.md"
    source.write_text("test content")

    # Create manifest with current source hash but OLD template hash
    manifest_path = tmp_path / "hashes.json"
    manifest = {"raw/articles/test.md": content_hash(source)}
    # Add template hash with wrong value to simulate change
    tpl = TEMPLATES_DIR / "article.yaml"
    if tpl.exists():
        manifest["_template/article"] = "old_hash_that_doesnt_match"
    save_manifest(manifest, manifest_path)

    new, changed = find_changed_sources(raw_dir, manifest_path)
    # The source should appear as changed due to template change
    assert len(changed) >= 1 or len(new) >= 1


def test_compile_saves_template_hashes(tmp_path):
    """compile_wiki stores template hashes in the manifest."""
    from kb.compile.compiler import compile_wiki, load_manifest

    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True)
    manifest_path = tmp_path / "hashes.json"
    wiki_log = tmp_path / "wiki" / "log.md"
    wiki_log.parent.mkdir(parents=True)
    wiki_log.write_text("# Log\n\n")

    wiki_dir = wiki_log.parent
    compile_wiki(incremental=True, raw_dir=raw_dir, manifest_path=manifest_path, wiki_dir=wiki_dir)

    manifest = load_manifest(manifest_path)
    template_keys = [k for k in manifest if k.startswith("_template/")]
    assert len(template_keys) >= 8


# ── 5. Lint Verdicts ─────────────────────────────────────────────


def test_add_verdict(tmp_path):
    """add_verdict creates and stores a verdict."""
    from kb.lint.verdicts import add_verdict, load_verdicts

    path = tmp_path / "verdicts.json"
    entry = add_verdict("concepts/rag", "fidelity", "pass", path=path)
    assert entry["page_id"] == "concepts/rag"
    assert entry["verdict"] == "pass"
    stored = load_verdicts(path)
    assert len(stored) == 1


def test_add_verdict_invalid_verdict(tmp_path):
    """add_verdict rejects invalid verdict values."""
    from kb.lint.verdicts import add_verdict

    path = tmp_path / "verdicts.json"
    with pytest.raises(ValueError, match="Invalid verdict"):
        add_verdict("concepts/rag", "fidelity", "maybe", path=path)


def test_add_verdict_invalid_type(tmp_path):
    """add_verdict rejects invalid verdict_type values."""
    from kb.lint.verdicts import add_verdict

    path = tmp_path / "verdicts.json"
    with pytest.raises(ValueError, match="Invalid verdict_type"):
        add_verdict("concepts/rag", "grammar", "pass", path=path)


def test_get_page_verdicts(tmp_path):
    """get_page_verdicts returns filtered, reverse-chronological verdicts."""
    import time

    from kb.lint.verdicts import add_verdict, get_page_verdicts

    path = tmp_path / "verdicts.json"
    add_verdict("concepts/a", "fidelity", "pass", path=path)
    add_verdict("concepts/b", "fidelity", "fail", path=path)
    time.sleep(1.1)  # ensure distinct timestamps for ordering
    add_verdict("concepts/a", "review", "warning", path=path)
    results = get_page_verdicts("concepts/a", path)
    assert len(results) == 2
    assert results[0]["verdict_type"] == "review"  # most recent first


def test_get_verdict_summary(tmp_path):
    """get_verdict_summary aggregates stats correctly."""
    from kb.lint.verdicts import add_verdict, get_verdict_summary

    path = tmp_path / "verdicts.json"
    add_verdict("concepts/a", "fidelity", "pass", path=path)
    add_verdict("concepts/b", "fidelity", "fail", path=path)
    add_verdict("concepts/a", "review", "warning", path=path)
    summary = get_verdict_summary(path)
    assert summary["total"] == 3
    assert summary["by_verdict"]["pass"] == 1
    assert summary["by_verdict"]["fail"] == 1
    assert summary["by_verdict"]["warning"] == 1
    assert summary["pages_with_failures"] == ["concepts/b"]


def test_load_verdicts_missing_file(tmp_path):
    """load_verdicts returns empty list when file doesn't exist."""
    from kb.lint.verdicts import load_verdicts

    path = tmp_path / "nonexistent.json"
    assert load_verdicts(path) == []


# ── 6. Entity Enrichment ─────────────────────────────────────────


def test_update_existing_page_enriches_content(tmp_wiki, create_wiki_page):
    """Updating an existing page with extraction data adds context."""
    from kb.ingest.pipeline import _update_existing_page

    page = create_wiki_page(
        "entities/openai",
        wiki_dir=tmp_wiki,
        page_type="entity",
        content="# OpenAI\n\n## References\n\n- Mentioned in raw/articles/old.md\n",
    )
    extraction = {
        "title": "New Article",
        "key_claims": ["OpenAI released GPT-4", "OpenAI leads AI research"],
        "entities_mentioned": ["OpenAI"],
    }
    _update_existing_page(page, "raw/articles/new.md", name="OpenAI", extraction=extraction)
    content = page.read_text(encoding="utf-8")
    assert "raw/articles/new.md" in content
    assert "GPT-4" in content or "Context" in content


def test_update_existing_page_no_duplicate_context(tmp_wiki, create_wiki_page):
    """Context is not added if already present in the page."""
    from kb.ingest.pipeline import _update_existing_page

    page = create_wiki_page(
        "entities/openai",
        wiki_dir=tmp_wiki,
        page_type="entity",
        content=(
            "# OpenAI\n\n## Context\n\n- OpenAI released GPT-4\n\n"
            "## References\n\n- Mentioned in raw/articles/old.md\n"
        ),
    )
    extraction = {
        "title": "Same Article",
        "key_claims": ["OpenAI released GPT-4"],
        "entities_mentioned": ["OpenAI"],
    }
    _update_existing_page(page, "raw/articles/new.md", name="OpenAI", extraction=extraction)
    content = page.read_text(encoding="utf-8")
    # Should not have duplicate context
    assert content.count("## Context") == 1


def test_update_existing_page_without_extraction(tmp_wiki, create_wiki_page):
    """Updating without extraction still works (backward compatible)."""
    from kb.ingest.pipeline import _update_existing_page

    page = create_wiki_page(
        "entities/test",
        wiki_dir=tmp_wiki,
        page_type="entity",
        content="# Test\n\n## References\n\n- Mentioned in raw/articles/old.md\n",
    )
    _update_existing_page(page, "raw/articles/new.md")
    content = page.read_text(encoding="utf-8")
    assert "raw/articles/new.md" in content


# ── 7. New MCP Tools ─────────────────────────────────────────────


def test_kb_create_page(tmp_path):
    """kb_create_page creates a new wiki page."""
    from kb.mcp.quality import kb_create_page

    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "comparisons").mkdir(parents=True)
    log_path = wiki_dir / "log.md"
    log_path.write_text("# Log\n\n")

    with (
        patch("kb.mcp.quality.WIKI_DIR", wiki_dir),
    ):
        result = kb_create_page(
            "comparisons/rag-vs-finetuning",
            "RAG vs Fine-tuning",
            "# RAG vs Fine-tuning\n\nComparison content.",
            "comparison",
            "inferred",
        )

    assert "Created" in result
    assert "comparison" in result
    page = wiki_dir / "comparisons" / "rag-vs-finetuning.md"
    assert page.exists()
    content = page.read_text(encoding="utf-8")
    assert "RAG vs Fine-tuning" in content
    assert "type: comparison" in content


def test_kb_create_page_already_exists(tmp_path):
    """kb_create_page rejects if page already exists."""
    from kb.mcp.quality import kb_create_page

    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "comparisons").mkdir(parents=True)
    (wiki_dir / "comparisons" / "test.md").write_text("existing")

    with patch("kb.mcp.quality.WIKI_DIR", wiki_dir):
        result = kb_create_page("comparisons/test", "Test", "content")
    assert "Error" in result
    assert "already exists" in result


def test_kb_save_lint_verdict(tmp_path):
    """kb_save_lint_verdict stores a verdict."""
    from kb.mcp.quality import kb_save_lint_verdict

    with patch("kb.lint.verdicts.VERDICTS_PATH", tmp_path / "v.json"):
        result = kb_save_lint_verdict("concepts/rag", "fidelity", "pass", notes="All good")
    assert "Verdict recorded" in result
    assert "fidelity" in result


def test_kb_save_lint_verdict_invalid(tmp_path):
    """kb_save_lint_verdict returns error for invalid verdict."""
    from kb.mcp.quality import kb_save_lint_verdict

    with patch("kb.lint.verdicts.VERDICTS_PATH", tmp_path / "v.json"):
        result = kb_save_lint_verdict("concepts/rag", "fidelity", "maybe")
    assert "Error" in result


# ── 8. MCP Split Verification ────────────────────────────────────


def test_mcp_server_backward_compat():
    """mcp_server.py still exports mcp for backward compatibility."""
    from kb.mcp_server import mcp

    assert mcp is not None


def test_mcp_all_tools_registered():
    """All 21 tools are registered in the MCP server."""
    from kb.mcp import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = {t.name for t in tools}
    expected = {
        "kb_query",
        "kb_ingest",
        "kb_ingest_content",
        "kb_save_source",
        "kb_compile_scan",
        "kb_search",
        "kb_read_page",
        "kb_list_pages",
        "kb_list_sources",
        "kb_stats",
        "kb_lint",
        "kb_evolve",
        "kb_review_page",
        "kb_refine_page",
        "kb_lint_deep",
        "kb_lint_consistency",
        "kb_query_feedback",
        "kb_reliability_map",
        "kb_affected_pages",
        "kb_save_lint_verdict",
        "kb_create_page",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


def test_ingest_source_export_lazy_loads_pipeline():
    """Folded from tests/test_cycle9_package_exports.py (cycle 49 — Phase 4.5 HIGH #4).

    Subprocess child verifies lazy-import contract: kb.ingest.pipeline must
    NOT be in sys.modules until kb.ingest.ingest_source attribute is accessed
    (cycle-9 PEP-562 lazy-shim).
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    repo_src = repo_root / "src"
    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath = (
        str(repo_src) if not existing_pythonpath else f"{repo_src}{os.pathsep}{existing_pythonpath}"
    )
    probe = """
import sys

import kb.ingest

assert "kb.ingest.pipeline" not in sys.modules
kb.ingest.ingest_source
assert "kb.ingest.pipeline" in sys.modules
"""

    result = subprocess.run(
        [sys.executable, "-c", probe],
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


class TestKbMcpConsoleScript:
    """Folded from tests/test_cycle12_mcp_console_script.py (cycle 49 — Phase 4.5 HIGH #4)."""

    def test_kb_mcp_package_exposes_main(self):
        from kb.mcp import main

        assert callable(main)

    def test_kb_mcp_server_reexports_main_and_mcp(self):
        from kb.mcp import main as pkg_main
        from kb.mcp import mcp as pkg_mcp
        from kb.mcp_server import main as shim_main
        from kb.mcp_server import mcp as shim_mcp

        assert shim_main is pkg_main
        assert shim_mcp is pkg_mcp

    def test_pyproject_has_kb_mcp_script_entry(self):
        import tomllib

        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        scripts = data.get("project", {}).get("scripts", {})
        assert scripts.get("kb-mcp") == "kb.mcp:main"
        assert scripts.get("kb") == "kb.cli:cli"
