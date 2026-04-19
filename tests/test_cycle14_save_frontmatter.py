"""Cycle 14 TASK 3 — save_page_frontmatter wrapper.

Covers AC16/AC17. Threat T4: atomic-write + sort_keys=False contract.
"""

from __future__ import annotations

import frontmatter

from kb.utils.pages import save_page_frontmatter


class TestInsertionOrderPreserved:
    """AC17(a) — 4+ non-alphabetical keys round-trip in insertion order."""

    def test_six_required_fields_order_preserved(self, tmp_path):
        target = tmp_path / "page.md"
        post = frontmatter.Post(content="body content\n")
        # Insertion order: title → source → created → updated → type → confidence
        post.metadata["title"] = "Hello"
        post.metadata["source"] = "raw/articles/hi.md"
        post.metadata["created"] = "2026-04-20"
        post.metadata["updated"] = "2026-04-20"
        post.metadata["type"] = "entity"
        post.metadata["confidence"] = "stated"

        save_page_frontmatter(target, post)

        text = target.read_text(encoding="utf-8")
        lines = text.splitlines()
        # Lines 1-6 inside frontmatter are keys in INSERTION order.
        assert lines[0] == "---"
        key_lines = [line.split(":", 1)[0] for line in lines[1:7]]
        assert key_lines == ["title", "source", "created", "updated", "type", "confidence"]

    def test_nonalphabetical_insertion_order(self, tmp_path):
        target = tmp_path / "weird.md"
        post = frontmatter.Post(content="weird\n")
        # Deliberately non-alphabetical insertion
        for key, value in [
            ("zebra", 1),
            ("apple", 2),
            ("mango", 3),
            ("banana", 4),
        ]:
            post.metadata[key] = value
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        keys_in_order = []
        in_fm = False
        for line in text.splitlines():
            if line == "---":
                if in_fm:
                    break
                in_fm = True
                continue
            if in_fm and ":" in line:
                keys_in_order.append(line.split(":", 1)[0])
        assert keys_in_order == ["zebra", "apple", "mango", "banana"]


class TestBodyVerbatim:
    """AC17(b) — body content verbatim including trailing newline."""

    def test_body_content_with_trailing_newline(self, tmp_path):
        target = tmp_path / "body.md"
        post = frontmatter.Post(content="Line 1\nLine 2\n\nLine 4\n")
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        # The body follows the second `---` delimiter.
        assert "Line 1" in text
        assert "Line 4" in text

    def test_body_preserved_with_special_chars(self, tmp_path):
        target = tmp_path / "special.md"
        body = "body with > quote and `code` and [[wikilink]]\n"
        post = frontmatter.Post(content=body)
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        assert "[[wikilink]]" in text
        assert "`code`" in text
        assert "> quote" in text


class TestListValuedMetadataOrder:
    """AC17(c) — list-valued metadata order preserved."""

    def test_source_list_order(self, tmp_path):
        target = tmp_path / "list.md"
        post = frontmatter.Post(content="x\n")
        post.metadata["title"] = "T"
        post.metadata["source"] = ["z.md", "a.md", "m.md"]
        save_page_frontmatter(target, post)
        loaded = frontmatter.load(str(target))
        assert loaded.metadata["source"] == ["z.md", "a.md", "m.md"]


class TestExtraKeysPreserved:
    """AC17(d) — custom metadata keys preserved."""

    def test_custom_keys_survive_roundtrip(self, tmp_path):
        target = tmp_path / "custom.md"
        post = frontmatter.Post(content="body\n")
        post.metadata["title"] = "T"
        post.metadata["type"] = "entity"
        post.metadata["last_augment_attempted"] = "2026-04-20T12:34:56Z"
        post.metadata["wikilinks"] = ["a", "b"]
        save_page_frontmatter(target, post)
        loaded = frontmatter.load(str(target))
        assert loaded.metadata["last_augment_attempted"] == "2026-04-20T12:34:56Z"
        assert loaded.metadata["wikilinks"] == ["a", "b"]


class TestAtomicWriteProof:
    """AC17(e) — writes atomically; no partial .tmp sibling on success."""

    def test_no_tmp_sibling_left_after_success(self, tmp_path):
        target = tmp_path / "atomic.md"
        post = frontmatter.Post(content="body\n")
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)

        # atomic_text_write creates a .tmp file then renames it to target.
        # Post-success, no .tmp sibling should remain.
        siblings = list(tmp_path.glob(f"{target.name}.tmp*"))
        assert siblings == []
        assert target.exists()

    def test_write_overwrites_existing(self, tmp_path):
        target = tmp_path / "overwrite.md"
        target.write_text("old content", encoding="utf-8")
        post = frontmatter.Post(content="new body\n")
        post.metadata["title"] = "T"
        save_page_frontmatter(target, post)
        text = target.read_text(encoding="utf-8")
        assert "new body" in text
        assert "old content" not in text
