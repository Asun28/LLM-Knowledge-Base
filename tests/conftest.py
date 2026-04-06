"""Shared test fixtures."""

from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def raw_dir(project_root: Path) -> Path:
    return project_root / "raw"


@pytest.fixture
def wiki_dir(project_root: Path) -> Path:
    return project_root / "wiki"


@pytest.fixture
def tmp_wiki(tmp_path: Path) -> Path:
    """Create a temporary wiki directory for isolated tests."""
    wiki = tmp_path / "wiki"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / subdir).mkdir(parents=True)
    return wiki


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with wiki/, raw/, and log.md."""
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / subdir).mkdir(parents=True)
    for subdir in ("articles", "papers", "repos", "videos"):
        (raw / subdir).mkdir(parents=True)
    (wiki / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    return tmp_path
