"""Cycle 12 TASK 3 tests for project-root resolution."""

import importlib
import logging
from pathlib import Path


def _reload_config():
    import kb.config as config

    return importlib.reload(config)


def _heuristic_root(config) -> Path:
    return Path(config.__file__).resolve().parents[2]


def test_valid_env_var_path_used(monkeypatch, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("KB_PROJECT_ROOT", str(project))

    config = _reload_config()

    assert config.PROJECT_ROOT == project.resolve()
    assert config.RAW_DIR == project.resolve() / "raw"
    assert config.WIKI_DIR == project.resolve() / "wiki"


def test_env_set_but_nonexistent_path_warns_and_falls_back(monkeypatch, tmp_path, caplog):
    missing = tmp_path / "base" / "missing"
    monkeypatch.setenv("KB_PROJECT_ROOT", str(missing))

    with caplog.at_level(logging.WARNING, logger="kb.config"):
        config = _reload_config()

    assert config.PROJECT_ROOT == _heuristic_root(config)
    assert "KB_PROJECT_ROOT" in caplog.text
    assert str(missing) in caplog.text
    assert "not a directory" in caplog.text


def test_env_set_but_regular_file_warns_and_falls_back(monkeypatch, tmp_path, caplog):
    project = tmp_path / "project"
    project.mkdir()
    file_path = project / "not-a-dir.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("KB_PROJECT_ROOT", str(file_path))

    with caplog.at_level(logging.WARNING, logger="kb.config"):
        config = _reload_config()

    assert config.PROJECT_ROOT == _heuristic_root(config)
    assert "KB_PROJECT_ROOT" in caplog.text
    assert str(file_path) in caplog.text
    assert "not a directory" in caplog.text


def test_env_unset_walk_up_finds_pyproject_within_five_levels(monkeypatch, tmp_path, caplog):
    import kb.config as config

    heuristic_pyproject = Path(config.__file__).resolve().parents[2] / "pyproject.toml"
    original_exists = Path.exists

    def exists_with_heuristic_pyproject_hidden(path):
        if Path(path) == heuristic_pyproject:
            return False
        return original_exists(path)

    project = tmp_path / "detected"
    cwd = project / "one" / "two" / "three" / "four" / "five"
    wiki = project / "wiki"
    cwd.mkdir(parents=True)
    wiki.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname = 'detected'\n", encoding="utf-8")
    monkeypatch.delenv("KB_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(Path, "exists", exists_with_heuristic_pyproject_hidden)

    with caplog.at_level(logging.INFO, logger="kb.config"):
        config = _reload_config()

    assert config.PROJECT_ROOT == project.resolve()
    assert "KB_PROJECT_ROOT" not in caplog.text
    assert "pyproject.toml" in caplog.text
    assert str(project.resolve()) in caplog.text
    assert "wiki_exists=True" in caplog.text


def test_env_unset_no_match_within_five_levels_falls_back_without_raise(monkeypatch, tmp_path):
    cwd = tmp_path / "one" / "two" / "three" / "four" / "five" / "six"
    cwd.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'too-far'\n", encoding="utf-8")
    monkeypatch.delenv("KB_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(cwd)

    config = _reload_config()

    assert config.PROJECT_ROOT == _heuristic_root(config)
