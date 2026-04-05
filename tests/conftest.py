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
