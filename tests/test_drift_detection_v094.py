"""Tests for content drift detection — detect_source_drift() and kb_detect_drift MCP tool."""

import json
from contextlib import contextmanager
from unittest.mock import patch

from kb.utils.hashing import content_hash

# Shared helper to patch SOURCE_TYPE_DIRS and suppress template hash checks
# (find_changed_sources looks up SOURCE_TYPE_DIRS for template-change detection,
# so we must also neutralize _template_hashes to avoid KeyError on missing types).


@contextmanager
def _patch_source_dirs(articles_dir):
    """Patch SOURCE_TYPE_DIRS to only include the test articles dir,
    and neutralize _template_hashes so template-change detection doesn't
    try to look up missing source types."""
    with (
        patch("kb.compile.compiler.SOURCE_TYPE_DIRS", {"article": articles_dir}),
        patch("kb.compile.compiler._template_hashes", return_value={}),
    ):
        yield


# ── 1. No changes detected ─────────────────────────────────────


def test_detect_drift_no_changes(tmp_path):
    """When manifest matches all sources, no drift is detected."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "test.md"
    source.write_text("# Test\n\nContent.", encoding="utf-8")

    # Manifest has current hash
    manifest_path = tmp_path / "hashes.json"
    current_hash = content_hash(source)
    manifest_path.write_text(json.dumps({"raw/articles/test.md": current_hash}), encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    for d in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / d).mkdir(parents=True)

    from kb.compile.compiler import detect_source_drift

    with _patch_source_dirs(articles):
        result = detect_source_drift(
            raw_dir=raw_dir, wiki_dir=wiki_dir, manifest_path=manifest_path
        )

    assert result["changed_sources"] == []
    assert result["affected_pages"] == []
    assert "up to date" in result["summary"]


# ── 2. New source detected ─────────────────────────────────────


def test_detect_drift_new_source(tmp_path):
    """A source not in the manifest is detected as new."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "new-article.md"
    source.write_text("# New Article\n\nFresh content.", encoding="utf-8")

    # Empty manifest
    manifest_path = tmp_path / "hashes.json"
    manifest_path.write_text("{}", encoding="utf-8")

    wiki_dir = tmp_path / "wiki"
    for d in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / d).mkdir(parents=True)

    from kb.compile.compiler import detect_source_drift

    with _patch_source_dirs(articles):
        result = detect_source_drift(
            raw_dir=raw_dir, wiki_dir=wiki_dir, manifest_path=manifest_path
        )

    assert len(result["changed_sources"]) == 1
    assert "raw/articles/new-article.md" in result["changed_sources"]
    assert "1 new source(s)" in result["summary"]


# ── 3. Changed source detected ─────────────────────────────────


def test_detect_drift_changed_source(tmp_path):
    """A source whose hash differs from manifest is detected as changed."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "article.md"
    source.write_text("# Updated Content\n\nNew version.", encoding="utf-8")

    # Manifest has old hash
    manifest_path = tmp_path / "hashes.json"
    manifest_path.write_text(
        json.dumps({"raw/articles/article.md": "old_hash_that_doesnt_match"}),
        encoding="utf-8",
    )

    wiki_dir = tmp_path / "wiki"
    for d in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / d).mkdir(parents=True)

    from kb.compile.compiler import detect_source_drift

    with _patch_source_dirs(articles):
        result = detect_source_drift(
            raw_dir=raw_dir, wiki_dir=wiki_dir, manifest_path=manifest_path
        )

    assert len(result["changed_sources"]) == 1
    assert "raw/articles/article.md" in result["changed_sources"]
    assert "1 changed source(s)" in result["summary"]


# ── 4. Finds affected wiki pages ───────────────────────────────


def test_detect_drift_finds_affected_pages(tmp_path):
    """Wiki pages referencing changed sources appear in affected_pages."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "test.md"
    source.write_text("# Original Content\n\nSome text.", encoding="utf-8")

    # Manifest with old hash (simulating change)
    manifest_path = tmp_path / "hashes.json"
    manifest_path.write_text(
        json.dumps({"raw/articles/test.md": "old_hash_that_doesnt_match"}),
        encoding="utf-8",
    )

    # Wiki page referencing this source
    wiki_dir = tmp_path / "wiki"
    for d in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / d).mkdir(parents=True)
    summary = wiki_dir / "summaries" / "test-summary.md"
    summary.write_text(
        '---\ntitle: "Test Summary"\nsource:\n  - "raw/articles/test.md"\n'
        "created: 2026-01-01\nupdated: 2026-01-01\ntype: summary\nconfidence: stated\n---\n\n"
        "# Test Summary\n\nSummary of test article.\n",
        encoding="utf-8",
    )

    from kb.compile.compiler import detect_source_drift

    with _patch_source_dirs(articles):
        result = detect_source_drift(
            raw_dir=raw_dir, wiki_dir=wiki_dir, manifest_path=manifest_path
        )

    assert len(result["affected_pages"]) >= 1
    assert result["affected_pages"][0]["page_id"] == "summaries/test-summary"
    assert "raw/articles/test.md" in result["affected_pages"][0]["changed_sources"]
    assert "may need re-review" in result["summary"]


# ── 5. No affected pages when none reference changed source ────


def test_detect_drift_no_affected_pages(tmp_path):
    """When no wiki pages reference the changed source, affected_pages is empty."""
    raw_dir = tmp_path / "raw"
    articles = raw_dir / "articles"
    articles.mkdir(parents=True)
    source = articles / "orphan.md"
    source.write_text("# Orphan\n\nNo wiki page references this.", encoding="utf-8")

    # Manifest with old hash
    manifest_path = tmp_path / "hashes.json"
    manifest_path.write_text(
        json.dumps({"raw/articles/orphan.md": "stale_hash"}),
        encoding="utf-8",
    )

    # Wiki page referencing a DIFFERENT source
    wiki_dir = tmp_path / "wiki"
    for d in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / d).mkdir(parents=True)
    page = wiki_dir / "concepts" / "unrelated.md"
    page.write_text(
        '---\ntitle: "Unrelated"\nsource:\n  - "raw/articles/other.md"\n'
        "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\nconfidence: stated\n---\n\n"
        "# Unrelated\n\nThis references a different source.\n",
        encoding="utf-8",
    )

    from kb.compile.compiler import detect_source_drift

    with _patch_source_dirs(articles):
        result = detect_source_drift(
            raw_dir=raw_dir, wiki_dir=wiki_dir, manifest_path=manifest_path
        )

    assert len(result["changed_sources"]) == 1
    assert result["affected_pages"] == []
    assert "No existing wiki pages reference" in result["summary"]


# ── 6. MCP tool exists and is importable ───────────────────────


def test_kb_detect_drift_tool_exists():
    """The kb_detect_drift function is importable from kb.mcp.health."""
    from kb.mcp.health import kb_detect_drift

    assert callable(kb_detect_drift)


# ── 7. MCP tool formats output correctly ──────────────────────


def test_kb_detect_drift_returns_formatted_output():
    """kb_detect_drift formats the drift result into readable markdown."""
    mock_result = {
        "changed_sources": ["raw/articles/foo.md", "raw/papers/bar.md"],
        "affected_pages": [
            {
                "page_id": "summaries/foo-summary",
                "changed_sources": ["raw/articles/foo.md"],
            },
            {
                "page_id": "entities/bar-entity",
                "changed_sources": ["raw/papers/bar.md"],
            },
        ],
        "summary": "1 new source(s), 1 changed source(s). 2 wiki page(s) may need re-review.",
    }

    with patch("kb.mcp.health.detect_source_drift", create=True) as mock_fn:
        mock_fn.return_value = mock_result
        with patch.dict(
            "sys.modules",
            {"kb.compile.compiler": type("mod", (), {"detect_source_drift": mock_fn})()},
        ):
            from kb.mcp.health import kb_detect_drift

            output = kb_detect_drift()

    assert "# Source Drift Detection" in output
    assert "Changed Sources (2)" in output
    assert "- raw/articles/foo.md" in output
    assert "- raw/papers/bar.md" in output
    assert "Affected Wiki Pages (2)" in output
    assert "**summaries/foo-summary**" in output
    assert "**entities/bar-entity**" in output
    assert "kb_review_page" in output
