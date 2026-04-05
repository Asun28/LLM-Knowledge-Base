"""Tests for data models and frontmatter validation."""

from kb.utils.markdown import extract_wikilinks, extract_raw_refs
from kb.utils.hashing import content_hash


def test_extract_wikilinks():
    text = "See [[concepts/rag]] and [[entities/karpathy|Karpathy]] for details."
    links = extract_wikilinks(text)
    assert links == ["concepts/rag", "entities/karpathy"]


def test_extract_wikilinks_empty():
    assert extract_wikilinks("No links here.") == []


def test_extract_raw_refs():
    text = "Source: raw/articles/example.md and raw/papers/paper.pdf"
    refs = extract_raw_refs(text)
    assert "raw/articles/example.md" in refs
    assert "raw/papers/paper.pdf" in refs


def test_content_hash(tmp_path):
    f = tmp_path / "test.md"
    f.write_text("hello world")
    h = content_hash(f)
    assert isinstance(h, str)
    assert len(h) == 16
    # Same content → same hash
    assert content_hash(f) == h
