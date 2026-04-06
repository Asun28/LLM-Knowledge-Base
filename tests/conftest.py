"""Shared test fixtures."""

from datetime import date
from pathlib import Path

import pytest

from kb.config import PROJECT_ROOT

WIKI_SUBDIRS = ("entities", "concepts", "comparisons", "summaries", "synthesis")
RAW_SUBDIRS = ("articles", "papers", "repos", "videos")


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
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True)
    return wiki


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory with wiki/, raw/, and log.md."""
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    for subdir in WIKI_SUBDIRS:
        (wiki / subdir).mkdir(parents=True)
    for subdir in RAW_SUBDIRS:
        (raw / subdir).mkdir(parents=True)
    (wiki / "log.md").write_text("# Wiki Log\n\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def create_wiki_page(tmp_path: Path):
    """Factory fixture: create a wiki page with proper frontmatter.

    Usage:
        page_path = create_wiki_page("concepts/rag", title="RAG", content="About RAG.")
        page_path = create_wiki_page("entities/openai", page_type="entity")
    """

    def _create(
        page_id: str,
        *,
        title: str | None = None,
        content: str = "",
        source_ref: str = "raw/articles/test.md",
        page_type: str = "concept",
        confidence: str = "stated",
        updated: str | None = None,
        wiki_dir: Path | None = None,
    ) -> Path:
        wiki_dir_actual = wiki_dir or (tmp_path / "wiki")
        page_path = wiki_dir_actual / f"{page_id}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        today = updated or date.today().isoformat()
        page_title = title or page_id.split("/")[-1].replace("-", " ").title()
        fm = (
            f'---\ntitle: "{page_title}"\nsource:\n  - "{source_ref}"\n'
            f"created: {today}\nupdated: {today}\ntype: {page_type}\n"
            f"confidence: {confidence}\n---\n\n"
        )
        page_path.write_text(fm + content, encoding="utf-8")
        return page_path

    return _create


@pytest.fixture
def create_raw_source(tmp_path: Path):
    """Factory fixture: create a raw source file.

    Usage:
        src_path = create_raw_source("raw/articles/test.md", "Source content here.")
    """

    def _create(
        source_ref: str,
        content: str = "Sample source content.",
        project_dir: Path | None = None,
    ) -> Path:
        base = project_dir or tmp_path
        source_path = base / source_ref
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(content, encoding="utf-8")
        return source_path

    return _create
