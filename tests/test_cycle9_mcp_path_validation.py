"""Cycle 9 MCP wiki_dir boundary validation regressions."""

from __future__ import annotations

from pathlib import Path

from kb.mcp.core import kb_compile_scan
from kb.mcp.health import kb_evolve, kb_lint


def _missing_abs_path(tmp_path: Path) -> str:
    path = tmp_path / "does-not-exist" / "wiki"
    assert path.is_absolute()
    assert not path.exists()
    return str(path)


def test_kb_compile_scan_rejects_nonexistent_wiki_dir(tmp_path):
    result = kb_compile_scan(wiki_dir=_missing_abs_path(tmp_path))

    assert "wiki_dir does not exist" in result


def test_kb_compile_scan_rejects_relative_wiki_dir():
    result = kb_compile_scan(wiki_dir="wiki")

    assert "wiki_dir must be an absolute path" in result


def test_kb_compile_scan_rejects_file_instead_of_dir(tmp_path):
    wiki_file = tmp_path / "wiki-file"
    wiki_file.write_text("not a directory", encoding="utf-8")

    result = kb_compile_scan(wiki_dir=str(wiki_file))

    assert "wiki_dir is not a directory" in result


def test_kb_lint_rejects_nonexistent_wiki_dir(tmp_path):
    result = kb_lint(wiki_dir=_missing_abs_path(tmp_path))

    assert "wiki_dir does not exist" in result


def test_kb_lint_rejects_relative_wiki_dir():
    result = kb_lint(wiki_dir="wiki")

    assert "wiki_dir must be an absolute path" in result


def test_kb_lint_rejects_file_instead_of_dir(tmp_path):
    wiki_file = tmp_path / "wiki-file"
    wiki_file.write_text("not a directory", encoding="utf-8")

    result = kb_lint(wiki_dir=str(wiki_file))

    assert "wiki_dir is not a directory" in result


def test_kb_evolve_rejects_nonexistent_wiki_dir(tmp_path):
    result = kb_evolve(wiki_dir=_missing_abs_path(tmp_path))

    assert "wiki_dir does not exist" in result


def test_kb_evolve_rejects_relative_wiki_dir():
    result = kb_evolve(wiki_dir="wiki")

    assert "wiki_dir must be an absolute path" in result


def test_kb_evolve_rejects_file_instead_of_dir(tmp_path):
    wiki_file = tmp_path / "wiki-file"
    wiki_file.write_text("not a directory", encoding="utf-8")

    result = kb_evolve(wiki_dir=str(wiki_file))

    assert "wiki_dir is not a directory" in result
