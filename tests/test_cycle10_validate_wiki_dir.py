"""Cycle 10 AC15 tests for wiki_dir validation hardening."""

import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT
from kb.mcp import browse, health
from kb.mcp.app import _validate_wiki_dir
from kb.mcp.health import kb_detect_drift, kb_graph_viz, kb_verdict_trends


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
