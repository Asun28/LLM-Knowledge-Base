"""Data models for wiki pages and raw sources."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from kb.config import CONFIDENCE_LEVELS, PAGE_TYPES, VALID_SOURCE_TYPES
from kb.utils.pages import normalize_sources

_TITLE_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _strip_control_chars(value: object) -> str:
    """Strip control and bidi formatting characters from page titles."""
    return _TITLE_UNSAFE_RE.sub("", str(value))


def _parse_date(value: object, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO date") from exc
    raise ValueError(f"{field_name} must be a date, datetime, ISO date string, or None")


def _safe_sources(sources: str | list | None) -> list[str]:
    result = []
    for source in normalize_sources(sources):
        normalized = source.replace("\\", "/")
        if (
            normalized.startswith("/")
            or ".." in normalized.split("/")
            or _WINDOWS_DRIVE_RE.match(source)
            or Path(source).is_absolute()
        ):
            continue
        result.append(normalized)
    return result


@dataclass
class RawSource:
    """A raw source document in the raw/ directory."""

    path: Path
    source_type: str  # article, paper, repo, video, podcast, book, dataset, conversation
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if self.source_type not in VALID_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")


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

    def __post_init__(self) -> None:
        self.title = _strip_control_chars(self.title)
        if self.page_type not in PAGE_TYPES:
            raise ValueError(f"page_type must be one of {PAGE_TYPES}")
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {CONFIDENCE_LEVELS}")

    def to_dict(self) -> dict:
        """Return the JSON wire format for a wiki page."""
        return {
            "path": str(self.path),
            "title": self.title,
            "type": self.page_type,
            "sources": list(self.sources),
            "confidence": self.confidence,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
            "wikilinks": list(self.wikilinks),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_post(cls, post: object, path: str | Path) -> "WikiPage":
        """Build a validated wiki page from a frontmatter.Post-shaped object."""
        metadata = getattr(post, "metadata", None)
        if not isinstance(metadata, dict):
            raise ValueError("post.metadata must be a dict")

        missing = [
            key
            for key in ("title", "type", "confidence")
            if metadata.get(key) is None or str(metadata.get(key)).strip() == ""
        ]
        if missing:
            raise ValueError(f"missing required metadata: {', '.join(missing)}")

        return cls(
            path=Path(path),
            title=_strip_control_chars(metadata["title"]).strip(),
            page_type=str(metadata["type"]),
            sources=_safe_sources(metadata.get("source")),
            confidence=str(metadata["confidence"]),
            created=_parse_date(metadata.get("created"), "created"),
            updated=_parse_date(metadata.get("updated"), "updated"),
            wikilinks=[str(link) for link in metadata.get("wikilinks", []) or []],
            content_hash=(
                str(metadata["content_hash"]) if metadata.get("content_hash") is not None else None
            ),
        )
