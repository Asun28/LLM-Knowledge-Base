"""Cycle 8 WikiPage and RawSource validation coverage."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from kb.models import RawSource, WikiPage


def _page(**overrides) -> WikiPage:
    kwargs = {
        "path": Path("wiki/concepts/rag.md"),
        "title": "Retrieval Augmented Generation",
        "page_type": "concept",
        "sources": ["raw/articles/rag.md"],
        "confidence": "stated",
        "created": date(2026, 4, 1),
        "updated": date(2026, 4, 2),
        "wikilinks": ["concepts/llm"],
        "content_hash": "abc123",
    }
    kwargs.update(overrides)
    return WikiPage(**kwargs)


def test_wiki_page_rejects_invalid_page_type():
    with pytest.raises(ValueError, match="page_type"):
        _page(page_type="bogus")


def test_wiki_page_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        _page(confidence="certain")


def test_raw_source_rejects_invalid_source_type():
    with pytest.raises(ValueError, match="source_type"):
        RawSource(path=Path("raw/unknown/input.md"), source_type="unknown")


def test_wiki_page_to_dict_is_json_wire_shape():
    payload = _page().to_dict()

    assert payload == {
        "path": str(Path("wiki/concepts/rag.md")),
        "title": "Retrieval Augmented Generation",
        "type": "concept",
        "sources": ["raw/articles/rag.md"],
        "confidence": "stated",
        "created": "2026-04-01",
        "updated": "2026-04-02",
        "wikilinks": ["concepts/llm"],
        "content_hash": "abc123",
    }
    json.dumps(payload)


def test_from_post_roundtrips_known_frontmatter_fields():
    post = SimpleNamespace(
        metadata={
            "title": "RAG",
            "type": "concept",
            "source": ["raw/articles/rag.md"],
            "confidence": "inferred",
            "created": "2026-04-03",
            "updated": date(2026, 4, 4),
            "wikilinks": ["concepts/retrieval"],
            "content_hash": "def456",
            "ignored": "metadata",
        }
    )

    page = WikiPage.from_post(post, Path("wiki/concepts/rag.md"))

    assert page.to_dict() == {
        "path": str(Path("wiki/concepts/rag.md")),
        "title": "RAG",
        "type": "concept",
        "sources": ["raw/articles/rag.md"],
        "confidence": "inferred",
        "created": "2026-04-03",
        "updated": "2026-04-04",
        "wikilinks": ["concepts/retrieval"],
        "content_hash": "def456",
    }


def test_from_post_requires_core_metadata():
    post = SimpleNamespace(metadata={"title": "RAG", "type": "concept"})

    with pytest.raises(ValueError, match="missing required metadata"):
        WikiPage.from_post(post, Path("wiki/concepts/rag.md"))


def test_from_post_strips_title_controls_and_traversal_sources():
    post = SimpleNamespace(
        metadata={
            "title": "\u202eRAG\x00 Notes\u2069",
            "type": "concept",
            "source": ["../../../etc/passwd", "/tmp/secret.md", "raw/articles/rag.md"],
            "confidence": "stated",
        }
    )

    page = WikiPage.from_post(post, Path("wiki/concepts/rag.md"))

    assert page.title == "RAG Notes"
    assert page.sources == ["raw/articles/rag.md"]
