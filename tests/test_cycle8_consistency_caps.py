"""Cycle 8 consistency caps and notes validation coverage."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from kb.config import MAX_CONSISTENCY_GROUPS, MAX_CONSISTENCY_PAGE_CONTENT_CHARS, MAX_NOTES_LEN
from kb.lint.semantic import build_consistency_context
from kb.mcp.app import _validate_notes
from kb.mcp.quality import kb_lint_consistency


def _write_page(wiki_dir: Path, page_id: str, source_ref: str, body: str) -> None:
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        "\n".join(
            [
                "---",
                f'title: "{page_id}"',
                "source:",
                f'  - "{source_ref}"',
                "created: 2026-04-01",
                "updated: 2026-04-02",
                "type: concept",
                "confidence: stated",
                "---",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def test_config_consistency_cap_constants_are_exact():
    assert MAX_CONSISTENCY_GROUPS == 20
    assert MAX_CONSISTENCY_PAGE_CONTENT_CHARS == 4096


def test_kb_lint_consistency_docstring_documents_auto_caps():
    doc = inspect.getdoc(kb_lint_consistency)

    assert doc is not None
    assert "caps total emitted groups" in doc
    assert "truncates each inlined page body" in doc
    assert "not truncated" in doc


def test_auto_mode_caps_emitted_groups_after_chunking(tmp_wiki):
    for idx in range(MAX_CONSISTENCY_GROUPS + 5):
        source_ref = f"raw/articles/shared-{idx}.md"
        _write_page(tmp_wiki, f"concepts/topic-{idx}-a", source_ref, f"unique body {idx} alpha")
        _write_page(tmp_wiki, f"concepts/topic-{idx}-b", source_ref, f"unique body {idx} beta")

    context = build_consistency_context(wiki_dir=tmp_wiki)

    group_headers = re.findall(r"^## Group \d+", context, flags=re.MULTILINE)
    assert len(group_headers) == MAX_CONSISTENCY_GROUPS


def test_auto_mode_strips_frontmatter_before_body_truncation(tmp_wiki):
    marker = (
        f"[Truncated at {MAX_CONSISTENCY_PAGE_CONTENT_CHARS} chars "
        "— run kb_lint_deep for full body]"
    )
    long_body = "body-start\n" + ("x" * (MAX_CONSISTENCY_PAGE_CONTENT_CHARS + 50))
    _write_page(tmp_wiki, "concepts/long-a", "raw/articles/long.md", long_body)
    _write_page(tmp_wiki, "concepts/long-b", "raw/articles/long.md", "short body")

    context = build_consistency_context(wiki_dir=tmp_wiki)

    assert marker in context
    assert "body-start" in context
    assert 'title: "concepts/long-a"' not in context


def test_explicit_mode_does_not_truncate_page_body(tmp_wiki):
    long_body = "explicit-body\n" + ("y" * (MAX_CONSISTENCY_PAGE_CONTENT_CHARS + 50))
    _write_page(tmp_wiki, "concepts/explicit-a", "raw/articles/explicit.md", long_body)
    _write_page(tmp_wiki, "concepts/explicit-b", "raw/articles/explicit.md", "short body")

    context = build_consistency_context(
        page_ids=["concepts/explicit-a", "concepts/explicit-b"],
        wiki_dir=tmp_wiki,
    )

    assert f"[Truncated at {MAX_CONSISTENCY_PAGE_CONTENT_CHARS} chars" not in context
    assert long_body in context


def test_validate_notes_accepts_valid_and_reports_sanitized_length():
    assert _validate_notes("short note", "notes") is None
    assert _validate_notes("\x00\u202eshort note\u2069", "notes") is None

    error = _validate_notes(("x" * MAX_NOTES_LEN) + "\x00\u202ey", "revision_notes")

    assert error == (
        f"Error: revision_notes too long ({MAX_NOTES_LEN + 1} chars; max {MAX_NOTES_LEN})."
    )


def test_validate_notes_strips_control_chars_before_length_check():
    raw = ("x" * MAX_NOTES_LEN) + "\x00"

    assert _validate_notes(raw, "notes") is None
