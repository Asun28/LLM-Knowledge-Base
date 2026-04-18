"""Cycle 8 MCP wiki_dir plumbing coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from kb.mcp.browse import kb_stats
from kb.mcp.health import kb_verdict_trends


def _write_page(wiki_dir: Path, page_id: str, title: str, body: str = "") -> None:
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        "\n".join(
            [
                "---",
                f'title: "{title}"',
                "source:",
                '  - "raw/articles/test.md"',
                "created: 2026-04-01",
                "updated: 2026-04-02",
                "type: concept",
                "confidence: stated",
                "---",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def test_kb_stats_scopes_to_supplied_wiki_dir(tmp_path, monkeypatch):
    import kb.mcp.browse as browse

    monkeypatch.setattr(browse, "PROJECT_ROOT", tmp_path)
    wiki_dir = tmp_path / "project" / "wiki"
    _write_page(wiki_dir, "concepts/alpha", "Alpha")
    _write_page(wiki_dir, "concepts/beta", "Beta", "[[concepts/alpha]]")

    result = kb_stats(wiki_dir=str(wiki_dir))

    assert "**Total pages:** 2" in result
    assert "**Graph:** 2 nodes, 1 edges" in result


def test_kb_stats_rejects_traversal_wiki_dir(tmp_path, monkeypatch):
    import kb.mcp.browse as browse

    monkeypatch.setattr(browse, "PROJECT_ROOT", tmp_path / "project")

    assert kb_stats(wiki_dir="../..").startswith("Error: wiki_dir")
    assert kb_stats(wiki_dir=str(tmp_path.parent)).startswith("Error: wiki_dir")


def test_kb_verdict_trends_reads_data_next_to_supplied_wiki_dir(tmp_path, monkeypatch):
    import kb.mcp.health as health

    monkeypatch.setattr(health, "PROJECT_ROOT", tmp_path)
    wiki_dir = tmp_path / "project" / "wiki"
    wiki_dir.mkdir(parents=True)
    data_dir = wiki_dir.parent / ".data"
    data_dir.mkdir()
    verdicts = [
        {
            "timestamp": datetime(2026, 4, 6, tzinfo=UTC).isoformat(),
            "page_id": "concepts/alpha",
            "verdict_type": "fidelity",
            "verdict": "pass",
        },
        {
            "timestamp": datetime(2026, 4, 7, tzinfo=UTC).isoformat(),
            "page_id": "concepts/beta",
            "verdict_type": "fidelity",
            "verdict": "fail",
        },
    ]
    (data_dir / "verdicts.json").write_text(json.dumps(verdicts), encoding="utf-8")

    result = kb_verdict_trends(wiki_dir=str(wiki_dir))

    assert "**Total verdicts:** 2" in result
    assert "Pass: 1 | Fail: 1 | Warning: 0" in result


def test_kb_verdict_trends_rejects_traversal_wiki_dir(tmp_path, monkeypatch):
    import kb.mcp.health as health

    monkeypatch.setattr(health, "PROJECT_ROOT", tmp_path / "project")

    assert kb_verdict_trends(wiki_dir="../..").startswith("Error: wiki_dir")
    assert kb_verdict_trends(wiki_dir=str(tmp_path.parent)).startswith("Error: wiki_dir")
