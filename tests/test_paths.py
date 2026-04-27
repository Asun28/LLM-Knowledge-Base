"""Tests for kb.utils.paths — canonical source reference computation."""

import importlib
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.utils.paths import make_source_ref

# ── Basic usage ──────────────────────────────────────────────────


def test_make_source_ref_normal(tmp_path):
    """File inside raw/articles/ produces 'raw/articles/<name>.md'."""
    raw_dir = tmp_path / "raw"
    (raw_dir / "articles").mkdir(parents=True)
    source = raw_dir / "articles" / "test.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=raw_dir)

    assert result == "raw/articles/test.md"


def test_make_source_ref_nested(tmp_path):
    """Deeply nested path inside raw/ produces correct forward-slash ref."""
    raw_dir = tmp_path / "raw"
    nested = raw_dir / "papers" / "2026" / "april" / "deep-paper.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("content", encoding="utf-8")

    result = make_source_ref(nested, raw_dir=raw_dir)

    assert result == "raw/papers/2026/april/deep-paper.md"


# ── Fallback behavior ───────────────────────────────────────────


def test_make_source_ref_outside_raw_dir(tmp_path):
    """Path outside raw dir raises ValueError."""
    import pytest

    raw_dir = tmp_path / "project" / "raw"
    raw_dir.mkdir(parents=True)

    # Create source in a completely separate directory tree
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    source = other_dir / "stray-file.md"
    source.write_text("content", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        make_source_ref(source, raw_dir=raw_dir)


# ── Forward slashes (Windows safety) ────────────────────────────


def test_make_source_ref_forward_slashes(tmp_path):
    """Result always uses forward slashes, even on Windows."""
    raw_dir = tmp_path / "raw"
    (raw_dir / "repos").mkdir(parents=True)
    source = raw_dir / "repos" / "my-repo.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=raw_dir)

    assert "\\" not in result
    assert result == "raw/repos/my-repo.md"


# ── Explicit vs. default raw_dir ────────────────────────────────


def test_make_source_ref_with_explicit_raw_dir(tmp_path):
    """Passing raw_dir explicitly always produces a 'raw/...' prefix."""
    custom_raw = tmp_path / "custom_raw"
    (custom_raw / "videos").mkdir(parents=True)
    source = custom_raw / "videos" / "talk.md"
    source.write_text("content", encoding="utf-8")

    result = make_source_ref(source, raw_dir=custom_raw)

    assert result == "raw/videos/talk.md"


def test_make_source_ref_default_raw_dir(tmp_path):
    """When raw_dir is None, make_source_ref uses config.RAW_DIR."""
    # Mock RAW_DIR to point at a temporary raw directory
    mock_raw = tmp_path / "raw"
    (mock_raw / "articles").mkdir(parents=True)
    source = mock_raw / "articles" / "default-test.md"
    source.write_text("content", encoding="utf-8")

    with patch("kb.utils.paths.RAW_DIR", mock_raw):
        result = make_source_ref(source)

    assert result == "raw/articles/default-test.md"


# ── tmp_project fixture-contract pins (cycle 43 AC4 fold) ───────


class TestTmpProjectFixtureContract:
    """Pin the conftest-defined ``tmp_project`` fixture's canonical wiki files.

    The fixture must create wiki/index.md, wiki/_sources.md, and wiki/log.md
    with specific frontmatter+body shapes. A future change that accidentally
    mutates these defaults would silently break every consuming test; this
    single-purpose pin catches the drift early.
    """

    EXPECTED_INDEX = (
        "---\n"
        "title: Wiki Index\n"
        "source: []\n"
        "type: index\n"
        "---\n\n"
        "# Knowledge Base Index\n\n"
        "## Pages\n\n"
        "*No pages yet.*\n\n"
        "## Entities\n\n"
        "*No pages yet.*\n\n"
        "## Concepts\n\n"
        "*No pages yet.*\n\n"
        "## Comparisons\n\n"
        "*No pages yet.*\n\n"
        "## Summaries\n\n"
        "*No pages yet.*\n\n"
        "## Synthesis\n\n"
        "*No pages yet.*\n"
    )

    EXPECTED_SOURCES = (
        "---\ntitle: Source Mapping\nsource: []\ntype: index\n---\n\n# Source Mapping\n"
    )

    def test_tmp_project_creates_canonical_index_sources_and_log(self, tmp_project):
        wiki = tmp_project / "wiki"

        assert (wiki / "index.md").read_text(encoding="utf-8") == self.EXPECTED_INDEX
        assert (wiki / "_sources.md").read_text(encoding="utf-8") == self.EXPECTED_SOURCES
        assert (wiki / "log.md").read_text(encoding="utf-8") == "# Wiki Log\n\n"


# ── PROJECT_ROOT resolution pins (cycle 43 AC7 fold; reload-isolated per c-19/20 L1/L2) ─


class TestProjectRootResolution:
    """Cycle 12 TASK 3 tests for kb.config.PROJECT_ROOT resolution.

    Each test mutates env vars and reloads kb.config; the autouse fixture
    restores the canonical config snapshot after every test so sibling
    tests in test_paths.py don't see leaked PROJECT_ROOT/RAW_DIR/WIKI_DIR
    state.
    """

    @staticmethod
    def _reload_config():
        import kb.config as config

        return importlib.reload(config)

    @staticmethod
    def _heuristic_root(config) -> Path:
        return Path(config.__file__).resolve().parents[2]

    @pytest.fixture(autouse=True)
    def _restore_config_after_test(self, monkeypatch):
        """Restore kb.config to canonical snapshot after every test in this class.

        Cycle-19 L2 / cycle-20 L1 reload-isolation: this class reloads
        kb.config N times; without an autouse teardown, sibling tests in
        test_paths.py see whatever the LAST test in this class left behind.
        """
        yield
        monkeypatch.delenv("KB_PROJECT_ROOT", raising=False)
        # Force reload back to canonical heuristic-root state.
        import kb.config as config

        importlib.reload(config)

    def test_valid_env_var_path_used(self, monkeypatch, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("KB_PROJECT_ROOT", str(project))

        config = self._reload_config()

        assert config.PROJECT_ROOT == project.resolve()
        assert config.RAW_DIR == project.resolve() / "raw"
        assert config.WIKI_DIR == project.resolve() / "wiki"

    def test_env_set_but_nonexistent_path_warns_and_falls_back(self, monkeypatch, tmp_path, caplog):
        missing = tmp_path / "base" / "missing"
        monkeypatch.setenv("KB_PROJECT_ROOT", str(missing))

        with caplog.at_level(logging.WARNING, logger="kb.config"):
            config = self._reload_config()

        assert config.PROJECT_ROOT == self._heuristic_root(config)
        assert "KB_PROJECT_ROOT" in caplog.text
        assert str(missing) in caplog.text
        assert "not a directory" in caplog.text

    def test_env_set_but_regular_file_warns_and_falls_back(self, monkeypatch, tmp_path, caplog):
        project = tmp_path / "project"
        project.mkdir()
        file_path = project / "not-a-dir.txt"
        file_path.write_text("not a directory", encoding="utf-8")
        monkeypatch.setenv("KB_PROJECT_ROOT", str(file_path))

        with caplog.at_level(logging.WARNING, logger="kb.config"):
            config = self._reload_config()

        assert config.PROJECT_ROOT == self._heuristic_root(config)
        assert "KB_PROJECT_ROOT" in caplog.text
        assert str(file_path) in caplog.text
        assert "not a directory" in caplog.text

    def test_env_unset_walk_up_finds_pyproject_within_five_levels(
        self, monkeypatch, tmp_path, caplog
    ):
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
            config = self._reload_config()

        assert config.PROJECT_ROOT == project.resolve()
        assert "KB_PROJECT_ROOT" not in caplog.text
        assert "pyproject.toml" in caplog.text
        assert str(project.resolve()) in caplog.text
        assert "wiki_exists=True" in caplog.text

    def test_env_unset_no_match_within_five_levels_falls_back_without_raise(
        self, monkeypatch, tmp_path
    ):
        cwd = tmp_path / "one" / "two" / "three" / "four" / "five" / "six"
        cwd.mkdir(parents=True)
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'too-far'\n", encoding="utf-8")
        monkeypatch.delenv("KB_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(cwd)

        config = self._reload_config()

        assert config.PROJECT_ROOT == self._heuristic_root(config)
