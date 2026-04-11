"""Data models for wiki pages and raw sources."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class RawSource:
    """A raw source document in the raw/ directory."""

    path: Path
    source_type: str  # article, paper, repo, video, podcast, book, dataset, conversation
    content_hash: str | None = None


@dataclass
class WikiPage:
    """A compiled wiki page in the wiki/ directory."""

    path: Path
    title: str
    page_type: str  # entity, concept, comparison, synthesis, summary
    sources: list[str] = field(default_factory=list)
    confidence: str = "stated"  # stated, inferred, speculative
    created: date | None = None
    updated: date | None = None
    wikilinks: list[str] = field(default_factory=list)
    content_hash: str | None = None
