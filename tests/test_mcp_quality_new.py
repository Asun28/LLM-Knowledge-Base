"""Tests for untested MCP quality tools: kb_affected_pages, kb_save_lint_verdict, kb_create_page."""

import json
from pathlib import Path
from unittest.mock import patch

import kb.config
import kb.lint.verdicts
import kb.mcp.quality
import kb.utils.wiki_log
from kb.mcp.quality import kb_affected_pages, kb_create_page, kb_save_lint_verdict

# ── Helpers ──────────────────────────────────────────────────────


def _setup_quality_paths(tmp_path, monkeypatch):
    """Monkeypatch config and module-level paths for quality tool tests."""
    wiki_dir = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / subdir).mkdir(parents=True)
    (wiki_dir / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")

    data_dir = tmp_path / ".data"
    data_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(kb.config, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.mcp.quality, "WIKI_DIR", wiki_dir)
    monkeypatch.setattr(kb.utils.wiki_log, "WIKI_LOG", wiki_dir / "log.md")
    monkeypatch.setattr(kb.lint.verdicts, "VERDICTS_PATH", data_dir / "lint_verdicts.json")

    return wiki_dir, data_dir


# ── kb_affected_pages ────────────────────────────────────────────


def test_kb_affected_pages_with_backlinks(monkeypatch):
    """Pages with backlinks and shared sources are identified as affected."""
    mock_backlinks = {"concepts/rag": ["concepts/llm", "entities/openai"]}
    mock_pages = [
        {
            "id": "concepts/rag",
            "sources": ["raw/articles/rag.md"],
            "title": "RAG",
            "path": Path("wiki/concepts/rag.md"),
            "type": "concept",
            "confidence": "stated",
            "created": "2026-04-06",
            "updated": "2026-04-06",
            "content": "RAG content.",
            "raw_content": "---\ntitle: RAG\n---\nRAG content.",
        },
        {
            "id": "concepts/llm",
            "sources": ["raw/articles/llm.md"],
            "title": "LLM",
            "path": Path("wiki/concepts/llm.md"),
            "type": "concept",
            "confidence": "stated",
            "created": "2026-04-06",
            "updated": "2026-04-06",
            "content": "LLM content.",
            "raw_content": "---\ntitle: LLM\n---\nLLM content.",
        },
        {
            "id": "entities/openai",
            "sources": ["raw/articles/rag.md"],  # shared source with concepts/rag
            "title": "OpenAI",
            "path": Path("wiki/entities/openai.md"),
            "type": "entity",
            "confidence": "stated",
            "created": "2026-04-06",
            "updated": "2026-04-06",
            "content": "OpenAI content.",
            "raw_content": "---\ntitle: OpenAI\n---\nOpenAI content.",
        },
    ]

    with (
        patch("kb.compile.linker.build_backlinks", return_value=mock_backlinks),
        patch("kb.mcp.quality.load_all_pages", return_value=mock_pages),
    ):
        result = kb_affected_pages("concepts/rag")

    assert "Pages Affected" in result
    # Backlinks
    assert "concepts/llm" in result
    assert "entities/openai" in result
    # Shared sources section
    assert "Shared Sources" in result


def test_kb_affected_pages_no_affected(monkeypatch):
    """Page with no backlinks or shared sources returns 'No pages' message."""
    mock_backlinks: dict[str, list[str]] = {}
    mock_pages = [
        {
            "id": "concepts/isolated",
            "sources": ["raw/articles/unique.md"],
            "title": "Isolated",
            "path": Path("wiki/concepts/isolated.md"),
            "type": "concept",
            "confidence": "stated",
            "created": "2026-04-06",
            "updated": "2026-04-06",
            "content": "Isolated content.",
            "raw_content": "---\ntitle: Isolated\n---\nIsolated content.",
        },
    ]

    with (
        patch("kb.compile.linker.build_backlinks", return_value=mock_backlinks),
        patch("kb.mcp.quality.load_all_pages", return_value=mock_pages),
    ):
        result = kb_affected_pages("concepts/isolated")

    assert "No pages" in result
    assert "concepts/isolated" in result


# ── kb_save_lint_verdict ─────────────────────────────────────────


def test_kb_save_lint_verdict_success(tmp_path, monkeypatch):
    """Valid verdict is saved and success message returned."""
    _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_save_lint_verdict(
        page_id="concepts/rag",
        verdict_type="fidelity",
        verdict="pass",
        notes="All claims verified.",
    )

    assert "Verdict recorded" in result
    assert "concepts/rag" in result
    assert "fidelity" in result
    assert "pass" in result
    assert "All claims verified." in result

    # Verify persistence
    verdicts_path = tmp_path / ".data" / "lint_verdicts.json"
    assert verdicts_path.exists()
    stored = json.loads(verdicts_path.read_text(encoding="utf-8"))
    assert len(stored) == 1
    assert stored[0]["page_id"] == "concepts/rag"
    assert stored[0]["verdict"] == "pass"


def test_kb_save_lint_verdict_invalid_verdict(tmp_path, monkeypatch):
    """Invalid verdict value returns error."""
    _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_save_lint_verdict(
        page_id="concepts/rag",
        verdict_type="fidelity",
        verdict="bad",
    )

    assert "Error" in result
    assert "bad" in result


def test_kb_save_lint_verdict_invalid_type(tmp_path, monkeypatch):
    """Invalid verdict_type returns error."""
    _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_save_lint_verdict(
        page_id="concepts/rag",
        verdict_type="bad",
        verdict="pass",
    )

    assert "Error" in result
    assert "bad" in result


def test_kb_save_lint_verdict_with_issues_json(tmp_path, monkeypatch):
    """JSON issues array is parsed and stored with verdict."""
    _setup_quality_paths(tmp_path, monkeypatch)

    issues = json.dumps([
        {"severity": "error", "description": "Missing citation for claim X"},
        {"severity": "info", "description": "Minor formatting issue"},
    ])

    result = kb_save_lint_verdict(
        page_id="concepts/rag",
        verdict_type="fidelity",
        verdict="fail",
        issues=issues,
        notes="Found citation gaps.",
    )

    assert "Verdict recorded" in result
    assert "Issues: 2" in result

    # Verify stored issues
    verdicts_path = tmp_path / ".data" / "lint_verdicts.json"
    stored = json.loads(verdicts_path.read_text(encoding="utf-8"))
    assert len(stored[0]["issues"]) == 2
    assert stored[0]["issues"][0]["severity"] == "error"


# ── kb_create_page ───────────────────────────────────────────────


def test_kb_create_page_success(tmp_path, monkeypatch):
    """New page is created with proper frontmatter and content."""
    wiki_dir, _ = _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_create_page(
        page_id="comparisons/rag-vs-finetuning",
        title="RAG vs Fine-Tuning",
        content="A comparison of RAG and fine-tuning approaches.",
        page_type="comparison",
        confidence="inferred",
        source_refs="raw/articles/rag.md,raw/articles/finetuning.md",
    )

    assert "Created: comparisons/rag-vs-finetuning" in result
    assert "comparison" in result
    assert "inferred" in result
    assert "Sources: 2" in result

    # Verify file contents
    page_path = wiki_dir / "comparisons" / "rag-vs-finetuning.md"
    assert page_path.exists()
    text = page_path.read_text(encoding="utf-8")
    assert 'title: "RAG vs Fine-Tuning"' in text
    assert "type: comparison" in text
    assert "confidence: inferred" in text
    assert "raw/articles/rag.md" in text
    assert "raw/articles/finetuning.md" in text
    assert "A comparison of RAG and fine-tuning approaches." in text


def test_kb_create_page_already_exists(tmp_path, monkeypatch):
    """Attempting to create a page that already exists returns error."""
    wiki_dir, _ = _setup_quality_paths(tmp_path, monkeypatch)

    # Pre-create the page
    page_path = wiki_dir / "concepts" / "rag.md"
    page_path.write_text("---\ntitle: RAG\n---\nExisting.", encoding="utf-8")

    result = kb_create_page(
        page_id="concepts/rag",
        title="RAG",
        content="New content.",
    )

    assert "Error" in result
    assert "already exists" in result


def test_kb_create_page_auto_detect_type(tmp_path, monkeypatch):
    """Page type is auto-detected from the subdirectory in page_id."""
    wiki_dir, _ = _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_create_page(
        page_id="comparisons/x-vs-y",
        title="X vs Y",
        content="Comparing X and Y.",
    )

    assert "Created: comparisons/x-vs-y" in result
    assert "comparison" in result

    page_path = wiki_dir / "comparisons" / "x-vs-y.md"
    text = page_path.read_text(encoding="utf-8")
    assert "type: comparison" in text


def test_kb_create_page_invalid_type(tmp_path, monkeypatch):
    """Invalid page_type returns error listing valid types."""
    _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_create_page(
        page_id="concepts/test",
        title="Test",
        content="Content.",
        page_type="invalid_type",
    )

    assert "Error" in result
    assert "invalid_type" in result
    assert "entity" in result  # valid types listed in error


def test_kb_create_page_invalid_confidence(tmp_path, monkeypatch):
    """Invalid confidence level returns error listing valid levels."""
    _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_create_page(
        page_id="concepts/test",
        title="Test",
        content="Content.",
        confidence="certain",
    )

    assert "Error" in result
    assert "certain" in result
    assert "stated" in result  # valid levels listed in error


def test_kb_create_page_traversal_blocked(tmp_path, monkeypatch):
    """Page ID with '..' path traversal is rejected."""
    _setup_quality_paths(tmp_path, monkeypatch)

    result = kb_create_page(
        page_id="../etc/passwd",
        title="Evil",
        content="Malicious.",
    )

    assert "Error" in result
    assert ".." in result
