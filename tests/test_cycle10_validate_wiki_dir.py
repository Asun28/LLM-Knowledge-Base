"""Cycle 10 AC15 tests for wiki_dir validation hardening."""

import sys
from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT
from kb.mcp import app as mcp_app
from kb.mcp import browse
from kb.mcp.app import _validate_wiki_dir


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
    monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_project)
    wiki = tmp_project / "wiki"

    path, err = _validate_wiki_dir(str(wiki))

    assert err is None
    assert path == wiki.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="symlink semantics differ")
def test_validate_wiki_dir_symlink_to_outside_rejected(tmp_project, tmp_path, monkeypatch):
    monkeypatch.setattr("kb.config.PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_project)
    outside = tmp_path / "outside_project_root_cycle10"
    outside.mkdir()
    link = tmp_project / "wiki_link"
    link.symlink_to(outside, target_is_directory=True)

    path, err = _validate_wiki_dir(str(link))

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
    monkeypatch.setattr(mcp_app, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(browse, "PROJECT_ROOT", tmp_project)

    result = browse.kb_stats(wiki_dir=str(wiki))

    assert not result.startswith("Error:")
    assert "2" in result

    traversal = browse.kb_stats(wiki_dir="../../evil")

    assert traversal.startswith("Error: wiki_dir ")
