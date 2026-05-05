"""Tests for v0.7.0 improvements — graph pagerank, case-insensitive wikilinks,
trust threshold fix, template hash detection, lint verdicts, entity enrichment,
new MCP tools, and MCP package split."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import networkx as nx
import pytest

from kb.mcp.app import _validate_run_id

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


# ── 9. tmp_kb_env fixture coverage (cycle 51 fold from test_cycle12_conftest.py) ─


def _is_under(path: Path, base: Path) -> bool:
    return path.resolve().is_relative_to(base.resolve())


def test_tmp_kb_env_rebinds_preimported_config_consumers(request):
    import kb.capture as capture
    import kb.config as config
    import kb.mcp.browse as browse
    import kb.mcp.core as core

    original_source_keys = tuple(config.SOURCE_TYPE_DIRS)

    project = request.getfixturevalue("tmp_kb_env")
    raw = project / "raw"

    for module in (config, core, browse, capture):
        assert _is_under(module.PROJECT_ROOT, project)

    for module in (config, core, browse):
        assert _is_under(module.RAW_DIR, project)

    for module in (config, browse):
        assert _is_under(module.WIKI_DIR, project)

    assert _is_under(config.CAPTURES_DIR, project)
    assert _is_under(capture.CAPTURES_DIR, project)

    assert tuple(config.SOURCE_TYPE_DIRS) == original_source_keys
    assert tuple(core.SOURCE_TYPE_DIRS) == original_source_keys
    for source_dir in config.SOURCE_TYPE_DIRS.values():
        assert _is_under(source_dir, raw)
    for source_dir in core.SOURCE_TYPE_DIRS.values():
        assert _is_under(source_dir, raw)

    assert _is_under(capture._CAPTURES_DIR_RESOLVED, project)
    assert _is_under(capture._captures_resolved, project)
    assert _is_under(capture._project_resolved, project)


# Cycle 64 AC1/AC3: `test_tmp_kb_env_is_not_autouse` deleted — its contract
# (tmp_kb_env path patches must NOT apply unless explicitly requested) was
# deliberately reversed by cycle 64. The autouse `_autouse_kb_path_sandbox`
# fixture now redirects `kb.config.WIKI_*` / `RAW_*` / `PROJECT_ROOT` for
# every test by default. Replacement coverage lives in
# `tests/test_cycle64_conftest_leak.py::test_default_isolation_redirects_wiki_constants_to_tmp`
# (asserts the FORWARD contract: config.PROJECT_ROOT != real_project_root
# under default pytest invocation). Per cycle-15 L2 / cycle-44 L4 DROP-with-
# test-anchor, the deletion is safe because replacement coverage is in
# place.


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


class TestMcpAppInstructions:
    """Folded from tests/test_cycle9_mcp_app.py (cycle 49 — Phase 4.5 HIGH #4)."""

    @staticmethod
    def _instruction_tool_groups(instructions: str) -> dict[str, list[str]]:
        import re

        groups: dict[str, list[str]] = {}
        current_group: str | None = None

        for line in instructions.splitlines():
            if match := re.fullmatch(r"### (?P<group>.+)", line):
                current_group = match.group("group")
                groups[current_group] = []
                continue

            if current_group and (match := re.fullmatch(r"- `(?P<name>kb_[^`]+)` — .+", line)):
                groups[current_group].append(match.group("name"))

        return groups

    def test_instructions_tool_names_sorted_within_groups(self):
        from kb.mcp import mcp

        groups = self._instruction_tool_groups(mcp.instructions or "")

        assert groups
        for group_name, tool_names in groups.items():
            assert tool_names, f"{group_name} has no documented tools"
            assert sorted(tool_names) == tool_names

        rendered_tool_names = {name for tool_names in groups.values() for name in tool_names}
        registered_tools = asyncio.run(mcp.list_tools(run_middleware=False))
        registered_tool_names = {tool.name for tool in registered_tools}

        assert rendered_tool_names == registered_tool_names


class TestValidateRunId:
    """T1 (cycle 17) — shared validator contract.

    Folded from tests/test_cycle17_validators.py (cycle 51 — Phase 4.5 HIGH #4).
    """

    def test_empty_string_is_sentinel_for_no_resume(self) -> None:
        assert _validate_run_id("") is None

    def test_valid_8_hex_chars(self) -> None:
        assert _validate_run_id("abc12345") is None
        assert _validate_run_id("00000000") is None
        assert _validate_run_id("ffffffff") is None
        assert _validate_run_id("deadbeef") is None

    @pytest.mark.parametrize(
        "bad_input",
        [
            "../etc",
            "../../secret",
            "abc",
            "abc1234",
            "abcdef012",
            "abcdef0123",
            "ABCD1234",
            "abcdefgh",
            "abc1234*",
            "abc1234?",
            "abc12[34",
            "abc/1234",
            "abc\\1234",
            "abc 1234",
            "abc-1234",
            "abc.1234",
            "  abc12345  ",
            "abc12345\n",
            "\x00abc12345",
        ],
    )
    def test_rejects_invalid(self, bad_input: str) -> None:
        result = _validate_run_id(bad_input)
        assert result is not None, f"Expected rejection for {bad_input!r}"
        assert "Invalid resume id" in result

    def test_rejection_message_quotes_input(self) -> None:
        """Error message should include the offending value for operator visibility."""
        result = _validate_run_id("../etc")
        assert result is not None
        assert "'../etc'" in result or '"../etc"' in result or "../etc" in result

    def test_rejection_message_hints_format(self) -> None:
        """Error message should state the expected format."""
        result = _validate_run_id("bad")
        assert result is not None
        assert "8 hex" in result or "0-9a-f" in result


# ── 10. Package export curation (cycle 51 fold from test_cycle8_package_exports.py) ─


def _run_export_import_probe(code: str):
    """Helper: run an `import` probe in a fresh subprocess against repo src/.

    Renamed from `_run_import_probe` per cycle-51 design Q2 (helper-name uniqueness
    in receiver). The 6 callers below use this helper.
    """
    import os
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src_dir) if not existing else f"{src_dir}{os.pathsep}{existing}"
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_kb_top_level_exports_importable_in_fresh_subprocess():
    result = _run_export_import_probe(
        "from kb import ("
        "ingest_source, compile_wiki, query_wiki, build_graph, "
        "WikiPage, RawSource, LLMError, __version__"
        ")"
    )

    assert result.returncode == 0, result.stderr


def test_kb_top_level_all_is_curated():
    import kb

    # Cycle 20 AC3 — kb.errors taxonomy exports added: KBError + 5 subclasses.
    assert kb.__all__ == [
        "ingest_source",
        "compile_wiki",
        "query_wiki",
        "build_graph",
        "WikiPage",
        "RawSource",
        "LLMError",
        "KBError",
        "IngestError",
        "CompileError",
        "QueryError",
        "ValidationError",
        "StorageError",
        "__version__",
    ]


def test_utils_exports_importable_in_fresh_subprocess():
    result = _run_export_import_probe(
        "from kb.utils import ("
        "slugify, yaml_escape, yaml_sanitize, STOPWORDS, atomic_json_write, "
        "atomic_text_write, file_lock, content_hash, extract_wikilinks, "
        "extract_raw_refs, FRONTMATTER_RE, append_wiki_log, load_all_pages, "
        "normalize_sources, make_source_ref"
        ")"
    )

    assert result.returncode == 0, result.stderr


def test_utils_all_is_curated():
    import kb.utils as utils

    assert utils.__all__ == [
        "slugify",
        "yaml_escape",
        "yaml_sanitize",
        "STOPWORDS",
        "atomic_json_write",
        "atomic_text_write",
        "file_lock",
        "content_hash",
        "extract_wikilinks",
        "extract_raw_refs",
        "FRONTMATTER_RE",
        "append_wiki_log",
        "load_all_pages",
        "normalize_sources",
        "make_source_ref",
    ]


def test_models_exports_importable_in_fresh_subprocess():
    result = _run_export_import_probe("from kb.models import WikiPage, RawSource")

    assert result.returncode == 0, result.stderr


def test_models_all_is_curated():
    import kb.models as models

    assert models.__all__ == ["WikiPage", "RawSource"]


# ── 11. Phase 3.97 task 09 — CLI fixes + version bump (cycle 56 fold from test_v0916_task09) ─


class TestCompileExitCode:
    """kb compile must exit 1 when errors occur."""

    def test_compile_errors_exit_code_1(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        mock_result = {
            "mode": "incremental",
            "sources_processed": 1,
            "pages_created": [],
            "pages_updated": [],
            "pages_skipped": [],
            "wikilinks_injected": [],
            "affected_pages": [],
            "duplicates": 0,
            "errors": [{"source": "raw/articles/bad.md", "error": "parse failed"}],
        }
        with patch("kb.compile.compiler.compile_wiki", return_value=mock_result):
            result = runner.invoke(cli, ["compile"])
            assert result.exit_code == 1


class TestCliSourceTypeList:
    """CLI ingest --type choices must match SOURCE_TYPE_DIRS."""

    def test_all_source_types_available(self):
        from kb.cli import cli

        # Get the ingest command's --type parameter choices
        ingest_cmd = cli.commands["ingest"]
        type_param = next(p for p in ingest_cmd.params if p.name == "source_type")
        choices = type_param.type.choices

        from kb.config import SOURCE_TYPE_DIRS

        for key in SOURCE_TYPE_DIRS:
            assert key in choices, f"Source type '{key}' missing from CLI choices"


class TestVersionBump:
    """Version must be bumped to current minor (cycle 65: 0.12.0)."""

    def test_version_is_0_9_16(self):
        # Test name preserves historical context (originally validated 0.9.16);
        # cycle 34 bumped to 0.11.0; cycle 65 bumped to 0.12.0. The cycle-34
        # regression test_pyproject_version_is_0_12_0 +
        # test_kb_init_version_matches_pyproject provide the cross-file
        # lockstep guard.
        from kb import __version__

        assert __version__ == "0.12.0"


# ── Cycle 17 AC4-AC7 — MCP cold-boot lazy imports (cycle 57 fold) ───────────
#
# Folded from tests/test_cycle17_lazy_imports.py per cycle-49+50+51 test_v070.py
# receiver precedent.
#
# Helpers and module constants renamed with `_cycle17_` / `_CYCLE17_` prefixes
# per cycle-52 L4 helper-name uniqueness.
#
# AC4 narrowed deferrals to `anthropic`, `frontmatter`, `kb.utils.llm.LLMError`,
# `kb.utils.pages.save_page_frontmatter`, `kb.capture.*` inside their consuming tool
# bodies. AC6 removed `kb.graph.export` from mcp/health.py module scope.
# AC5 / AC7 are AST regression pins on mcp/browse.py and mcp/quality.py.
# AST inspection used (not sys.modules) because cold-boot is order-dependent
# under pytest's shared-process model — once any sibling test loads kb.mcp,
# FastMCP @mcp.tool() decorators register + cache.

import ast as _cycle17_ast  # noqa: E402 — appended fold section per cycle-49+50+51 host-shape
import sys as _cycle17_sys  # noqa: E402
from pathlib import Path as _Cycle17Path  # noqa: E402

_CYCLE17_REPO_ROOT = _Cycle17Path(__file__).resolve().parent.parent
_CYCLE17_SRC_KB_MCP = _CYCLE17_REPO_ROOT / "src" / "kb" / "mcp"


def _cycle17_module_level_imports(py_file: _Cycle17Path) -> set[str]:
    """Return set of fully-qualified names imported at MODULE level via `ast`.

    Ignores function-body and class-body imports (those are lazy by definition).
    Returns top-level Import + ImportFrom targets only.
    """
    try:
        tree = _cycle17_ast.parse(py_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in tree.body:  # tree.body = top-level statements only
        if isinstance(node, _cycle17_ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, _cycle17_ast.ImportFrom):
            if node.module:
                # Normalise `from X.Y import Z, W` → add both `X.Y` and `X.Y.Z`
                # style entries so tests can match at either granularity.
                names.add(node.module)
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
        elif isinstance(node, _cycle17_ast.If):
            # Handle TYPE_CHECKING guarded blocks — their imports are NOT
            # runtime-level. Skip them.
            continue
    return names


class TestAC4ModuleLevelImportsNarrowed:
    """AC4 — `mcp/core.py` must defer the tool-body-lazy imports at source level."""

    def test_anthropic_not_at_module_level(self) -> None:
        imports = _cycle17_module_level_imports(_CYCLE17_SRC_KB_MCP / "core.py")
        assert "anthropic" not in imports, (
            "AC4 regression: `import anthropic` at module level of mcp/core.py. "
            "Move it inside the `if use_api:` branch of kb_query."
        )

    def test_frontmatter_not_at_module_level(self) -> None:
        imports = _cycle17_module_level_imports(_CYCLE17_SRC_KB_MCP / "core.py")
        assert "frontmatter" not in imports, (
            "AC4 regression: `import frontmatter` at module level of mcp/core.py. "
            "Move it inside `_save_synthesis`."
        )

    def test_kb_capture_module_level_note(self) -> None:
        """Cycle 17 parked — kb.capture stays module-level; header explains why."""
        src = (_CYCLE17_SRC_KB_MCP / "core.py").read_text(encoding="utf-8")
        assert "kb.capture" in src and "security check" in src.lower(), (
            "AC4 documentation: cycle 17 header note about parked kb.capture "
            "deferral missing from mcp/core.py"
        )


class TestAC6HealthGraphExportDeferred:
    """AC6 — `mcp/health.py` must not import `kb.graph.export` at module level."""

    def test_graph_export_not_at_module_level(self) -> None:
        imports = _cycle17_module_level_imports(_CYCLE17_SRC_KB_MCP / "health.py")
        assert (
            "kb.graph.export" not in imports and "kb.graph.export.export_mermaid" not in imports
        ), (
            "AC6 regression: `from kb.graph.export import export_mermaid` at "
            "module level of mcp/health.py. Move it inside `kb_graph_viz`."
        )

    def test_graph_export_not_loaded_at_mcp_package_import(self) -> None:
        """Positive runtime pin — networkx must not load on `import kb.mcp.core`."""
        # If kb.graph.export was already imported by some prior test, this
        # check is informational only; the AST check above is the hard guarantee.
        if "kb.graph.export" in _cycle17_sys.modules:
            # Pre-loaded by an earlier test (e.g. one that invoked kb_graph_viz).
            # Don't fail — the AST check already enforces the source contract.
            return
        import importlib

        importlib.import_module("kb.mcp.core")
        assert "kb.graph.export" not in _cycle17_sys.modules, (
            "AC6 regression: importing kb.mcp.core (which triggers kb.mcp "
            "package init → health.py) loaded kb.graph.export."
        )


class TestAC5BrowseRegressionPin:
    """AC5 — `mcp/browse.py` MUST NOT gain module-level heavy imports."""

    def test_no_heavy_imports_at_module_level(self) -> None:
        imports = _cycle17_module_level_imports(_CYCLE17_SRC_KB_MCP / "browse.py")
        forbidden = {
            "kb.evolve.analyzer",
            "kb.graph.builder",
            "kb.graph.export",
        }
        violations = imports & forbidden
        assert not violations, (
            f"AC5 regression: mcp/browse.py imports {violations} at module level. "
            "These must stay in tool bodies."
        )


class TestAC7QualityRegressionPin:
    """AC7 — `mcp/quality.py` MUST NOT gain module-level heavy imports."""

    def test_no_heavy_imports_at_module_level(self) -> None:
        imports = _cycle17_module_level_imports(_CYCLE17_SRC_KB_MCP / "quality.py")
        forbidden = {
            "kb.review.refiner",
            "kb.review.context",
            "kb.lint.semantic",
        }
        violations = imports & forbidden
        assert not violations, (
            f"AC7 regression: mcp/quality.py imports {violations} at module level. "
            "These must stay in tool bodies."
        )


class TestDocumentedScope:
    """Meta — the module docstring explains what cycle 17 did / didn't fix."""

    def test_docstring_declares_parked_deferrals(self) -> None:
        """Future cycles planning deeper deferrals should see the precedent."""
        core_source = (_CYCLE17_SRC_KB_MCP / "core.py").read_text(encoding="utf-8")
        assert "Cycle 17 AC4" in core_source, (
            "cycle 17 AC4 context note missing from mcp/core.py header"
        )
        health_source = (_CYCLE17_SRC_KB_MCP / "health.py").read_text(encoding="utf-8")
        assert "Cycle 17 AC6" in health_source, (
            "cycle 17 AC6 context note missing from mcp/health.py header"
        )
