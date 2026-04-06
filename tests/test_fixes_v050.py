"""Tests for v0.5.0 fixes — trust formula, paths, fence stripping, validation, slugify."""

from pathlib import Path
from unittest.mock import patch

from kb.compile.compiler import _canonical_rel_path
from kb.config import (
    MAX_PAGES_FOR_TERM,
    MIN_PAGES_FOR_TERM,
    MIN_SHARED_TERMS,
    SEARCH_CONTENT_WEIGHT,
    SEARCH_TITLE_WEIGHT,
    STALENESS_MAX_DAYS,
)
from kb.feedback.store import add_feedback_entry, load_feedback
from kb.utils.paths import make_source_ref
from kb.utils.text import slugify, yaml_escape

# ── C2: Canonical path computation ──────────────────────────────


def test_canonical_rel_path(tmp_path):
    """_canonical_rel_path produces forward-slash relative paths."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "test.md"
    source.write_text("content")

    result = _canonical_rel_path(source, raw_dir)
    assert result == "raw/articles/test.md"
    assert "\\" not in result


def test_canonical_rel_path_outside_raw(tmp_path):
    """_canonical_rel_path falls back for files outside raw/."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    source = tmp_path / "other" / "file.md"
    source.parent.mkdir(parents=True)
    source.write_text("content")

    result = _canonical_rel_path(source, raw_dir)
    assert "\\" not in result


# ── C3: Bayesian trust formula with weighted wrong ──────────────


def test_trust_wrong_penalized_more_than_incomplete(tmp_path):
    """'wrong' feedback lowers trust more than 'incomplete'."""
    path_wrong = tmp_path / "fb_wrong.json"
    path_incomplete = tmp_path / "fb_incomplete.json"

    add_feedback_entry("Q1", "wrong", ["p1"], path=path_wrong)
    add_feedback_entry("Q1", "incomplete", ["p1"], path=path_incomplete)

    wrong_trust = load_feedback(path_wrong)["page_scores"]["p1"]["trust"]
    incomplete_trust = load_feedback(path_incomplete)["page_scores"]["p1"]["trust"]

    # wrong should produce lower trust than incomplete
    assert wrong_trust < incomplete_trust


def test_trust_useful_only(tmp_path):
    """Pure useful feedback gives trust > 0.5."""
    path = tmp_path / "fb.json"
    add_feedback_entry("Q1", "useful", ["p1"], path=path)
    trust = load_feedback(path)["page_scores"]["p1"]["trust"]
    assert trust > 0.5


def test_trust_mixed_feedback(tmp_path):
    """Mixed feedback with more useful than wrong gives trust near 0.5."""
    path = tmp_path / "fb.json"
    add_feedback_entry("Q1", "useful", ["p1"], path=path)
    add_feedback_entry("Q2", "useful", ["p1"], path=path)
    add_feedback_entry("Q3", "wrong", ["p1"], path=path)
    trust = load_feedback(path)["page_scores"]["p1"]["trust"]
    # (2+1)/(2+2*1+2) = 3/6 = 0.5
    assert abs(trust - 0.5) < 0.001


# ── C5: YAML escape ────────────────────────────────────────────


def testyaml_escape_quotes():
    """yaml_escape escapes double quotes."""
    assert yaml_escape('He said "hello"') == 'He said \\"hello\\"'


def testyaml_escape_backslash():
    """yaml_escape escapes backslashes."""
    assert yaml_escape("path\\to\\file") == "path\\\\to\\\\file"


def testyaml_escape_clean():
    """yaml_escape leaves clean strings unchanged."""
    assert yaml_escape("normal title") == "normal title"


# ── H1: make_source_ref utility ─────────────────────────────────


def test_make_source_ref(tmp_path):
    """make_source_ref produces canonical raw/ relative paths."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "my-article.md"
    source.write_text("content")

    ref = make_source_ref(source, raw_dir)
    assert ref == "raw/articles/my-article.md"


def test_make_source_ref_fallback(tmp_path):
    """make_source_ref falls back for files completely outside the project tree."""
    import tempfile

    raw_dir = tmp_path / "project" / "raw"
    raw_dir.mkdir(parents=True)

    # Create file in an unrelated temp dir (outside raw_dir.parent)
    with tempfile.TemporaryDirectory() as other_dir:
        source = Path(other_dir) / "doc.md"
        source.write_text("content")
        ref = make_source_ref(source, raw_dir)
        assert ref == "raw/doc.md"


# ── H3: Fence stripping edge cases ─────────────────────────────


def test_fence_stripping_no_newline():
    """Fence stripping handles ``` with no newline."""
    from kb.ingest.extractors import extract_from_source

    with patch("kb.ingest.extractors.call_llm") as mock_llm:
        mock_llm.return_value = '```{"title": "test"}```'
        result = extract_from_source("content", "article")
        assert result["title"] == "test"


def test_fence_stripping_normal():
    """Fence stripping handles normal ```json\\n...``` format."""
    from kb.ingest.extractors import extract_from_source

    with patch("kb.ingest.extractors.call_llm") as mock_llm:
        mock_llm.return_value = '```json\n{"title": "test"}\n```'
        result = extract_from_source("content", "article")
        assert result["title"] == "test"


def test_fence_stripping_no_fences():
    """Clean JSON without fences passes through."""
    from kb.ingest.extractors import extract_from_source

    with patch("kb.ingest.extractors.call_llm") as mock_llm:
        mock_llm.return_value = '{"title": "test"}'
        result = extract_from_source("content", "article")
        assert result["title"] == "test"


# ── H8: Frontmatter split edge case ────────────────────────────


def test_refine_page_with_dashes_in_content(tmp_path):
    """refine_page handles content containing --- correctly."""
    from kb.review.refiner import refine_page

    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    (wiki / "log.md").write_text("# Log\n\n")

    page = wiki / "concepts" / "test.md"
    page.write_text(
        '---\ntitle: "Test"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "Content with --- dashes in it.\n"
    )

    history_path = tmp_path / "history.json"
    result = refine_page(
        "concepts/test", "Updated content", "test fix", wiki_dir=wiki, history_path=history_path
    )
    assert result.get("error") is None
    assert result["updated"] is True

    # Verify frontmatter is intact
    text = page.read_text(encoding="utf-8")
    assert 'title: "Test"' in text
    assert "Updated content" in text


def test_refine_page_invalid_frontmatter(tmp_path):
    """refine_page returns error for file without frontmatter."""
    from kb.review.refiner import refine_page

    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True)
    page = wiki / "concepts" / "bad.md"
    page.write_text("No frontmatter here\nJust content\n")

    result = refine_page("concepts/bad", "new content", wiki_dir=wiki)
    assert "error" in result


# ── M1: Config constants exist ──────────────────────────────────


def test_config_constants_exist():
    """All config constants from magic numbers exist and have expected values."""
    assert STALENESS_MAX_DAYS == 90
    assert MIN_PAGES_FOR_TERM == 2
    assert MAX_PAGES_FOR_TERM == 5
    assert MIN_SHARED_TERMS == 3
    assert SEARCH_TITLE_WEIGHT == 3
    assert SEARCH_CONTENT_WEIGHT == 1


# ── M6: Empty slugify skipped ───────────────────────────────────


def test_slugify_empty_input():
    """slugify returns empty string for punctuation-only input."""
    assert slugify("...") == ""
    assert slugify("!!!") == ""
    assert slugify("") == ""


def test_slugify_normal():
    """slugify produces expected slug for normal input."""
    assert slugify("Hello World") == "hello-world"
    assert slugify("LLM Knowledge Base") == "llm-knowledge-base"


# ── H2: Graph builder edge invariant ───────────────────────────


def test_graph_no_dangling_edges(tmp_wiki):
    """Graph should not contain edges to nonexistent nodes."""
    from kb.graph.builder import build_graph

    # Create page with a link to a nonexistent page
    page = tmp_wiki / "concepts" / "rag.md"
    page.write_text(
        '---\ntitle: "RAG"\nsource:\n  - raw/test.md\n'
        "created: 2026-04-06\nupdated: 2026-04-06\n"
        "type: concept\nconfidence: stated\n---\n\n"
        "Links to [[concepts/nonexistent]] and [[entities/ghost]].\n"
    )

    graph = build_graph(tmp_wiki)
    # Only "concepts/rag" should be a node
    assert "concepts/rag" in graph.nodes()
    assert "concepts/nonexistent" not in graph.nodes()
    assert "entities/ghost" not in graph.nodes()
    # No edges should exist since targets don't exist as nodes
    assert graph.number_of_edges() == 0


# ── H4: Extraction JSON validation ─────────────────────────────


def test_extraction_validation_missing_title(tmp_path):
    """kb_ingest rejects extraction without title."""
    from kb.mcp_server import kb_ingest

    source = tmp_path / "raw" / "articles" / "test.md"
    source.parent.mkdir(parents=True)
    source.write_text("test content")

    with (
        patch("kb.mcp_server.PROJECT_ROOT", tmp_path),
        patch("kb.mcp_server.RAW_DIR", tmp_path / "raw"),
        patch("kb.mcp_server.WIKI_DIR", tmp_path / "wiki"),
    ):
        result = kb_ingest(str(source), "article", '{"entities_mentioned": []}')
    assert "Error" in result
    assert "title" in result.lower()


def test_extraction_validation_non_dict(tmp_path):
    """kb_ingest rejects non-dict extraction JSON."""
    from kb.mcp_server import kb_ingest

    source = tmp_path / "raw" / "articles" / "test.md"
    source.parent.mkdir(parents=True)
    source.write_text("test content")

    with (
        patch("kb.mcp_server.PROJECT_ROOT", tmp_path),
        patch("kb.mcp_server.RAW_DIR", tmp_path / "raw"),
        patch("kb.mcp_server.WIKI_DIR", tmp_path / "wiki"),
    ):
        result = kb_ingest(str(source), "article", '["not", "a", "dict"]')
    assert "Error" in result
    assert "object" in result.lower()
