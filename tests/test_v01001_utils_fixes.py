"""Tests for Phase 4 MEDIUM/LOW fixes in utils/."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from kb.utils.io import atomic_json_write
from kb.utils.markdown import extract_wikilinks
from kb.utils.pages import load_all_pages
from kb.utils.text import slugify
from kb.utils.wiki_log import append_wiki_log


def _write_page(dirpath: Path, name: str, body: str) -> None:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / f"{name}.md").write_text(body, encoding="utf-8")


def test_load_all_pages_extracts_date_from_datetime(tmp_wiki):
    """Page with a full datetime in `updated:` must yield an ISO-8601 date string."""
    body = (
        "---\n"
        'title: "Foo"\n'
        "type: concept\n"
        "confidence: stated\n"
        "source:\n  - raw/articles/foo.md\n"
        "updated: 2024-01-01 12:00:00\n"
        "---\n"
        "body\n"
    )
    _write_page(tmp_wiki / "concepts", "foo", body)
    pages = load_all_pages(tmp_wiki)
    assert len(pages) == 1
    # Must be parseable by date.fromisoformat — no time portion.
    _dt.date.fromisoformat(pages[0]["updated"])
    assert pages[0]["updated"] == "2024-01-01"


def test_slugify_preserves_version_numbers():
    """`v1.0` and `v10` must NOT collide."""
    assert slugify("v1.0") != slugify("v10")
    assert slugify("python 3.12") == "python-3-12"
    assert slugify("v1.0") == "v1-0"


def test_atomic_json_write_cleanup_no_ebadf(tmp_path, monkeypatch):
    """When json.dump raises, cleanup must not double-close the fd."""
    import json as _json

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(_json, "dump", _boom)
    with pytest.raises(RuntimeError):
        atomic_json_write({"a": 1}, tmp_path / "out.json")
    # Temp file must be cleaned up.
    assert not any(p.suffix == ".tmp" for p in tmp_path.iterdir())


def test_extract_wikilinks_strips_embedded_newlines():
    """Wikilink targets containing newlines must not produce broken page IDs."""
    text = "See [[foo\nbar]] and [[baz]]."
    links = extract_wikilinks(text)
    for link in links:
        assert "\n" not in link
        assert "\r" not in link


def test_append_wiki_log_strips_tabs(tmp_path):
    """Tab characters in log message must be replaced with spaces."""
    log_path = tmp_path / "log.md"
    log_path.write_text("# Log\n", encoding="utf-8")
    append_wiki_log("ingest", "added\ttabbed\tentry", log_path=log_path)
    content = log_path.read_text(encoding="utf-8")
    # The final line (the log entry) must not contain a literal tab character.
    assert "\t" not in content.splitlines()[-1]
