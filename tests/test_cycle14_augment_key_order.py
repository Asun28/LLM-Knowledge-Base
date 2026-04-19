"""Cycle 14 TASK 4 — augment write-back migration key order preservation.

Covers AC18, AC19. Three write-back sites in lint/augment.py migrated to
save_page_frontmatter wrapper (sort_keys=False). Threat T10 verification.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import frontmatter

from kb.lint import augment


def _seed_page(path: Path, content: str, metadata: dict) -> None:
    """Write a page via frontmatter.dumps without sort_keys so we control
    the ON-DISK insertion order for the test."""
    post = frontmatter.Post(content=content)
    # Assign metadata IN the test-specified order.
    for k, v in metadata.items():
        post.metadata[k] = v
    path.write_text(frontmatter.dumps(post, sort_keys=False), encoding="utf-8")


def _disk_key_order(path: Path) -> list[str]:
    """Return ordered list of top-level frontmatter keys from file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    keys: list[str] = []
    in_fm = False
    for line in lines:
        if line == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if in_fm and ":" in line and not line.startswith(" ") and not line.startswith("-"):
            keys.append(line.split(":", 1)[0])
    return keys


class TestRecordVerdictGapCallout:
    """AC18 — _record_verdict_gap_callout preserves insertion order."""

    def test_preserves_non_alpha_key_order(self, tmp_path):
        page = tmp_path / "stub.md"
        _seed_page(
            page,
            content="body\n",
            metadata={
                "title": "Stub Page",
                "zebra": 1,
                "created": "2026-04-20",
                "apple": 2,
            },
        )
        order_before = _disk_key_order(page)
        augment._record_verdict_gap_callout(page, run_id="abcdef12", reason="low-signal")
        order_after = _disk_key_order(page)
        assert order_after == order_before, (
            f"key order regressed: before={order_before} after={order_after}"
        )

    def test_gap_callout_inserted_in_body(self, tmp_path):
        page = tmp_path / "stub.md"
        _seed_page(
            page,
            content="original body\n",
            metadata={"title": "Stub Page"},
        )
        augment._record_verdict_gap_callout(page, run_id="abcdef12", reason="low-signal")
        text = page.read_text(encoding="utf-8")
        assert "[!gap]" in text
        assert "abcdef12" in text
        assert "original body" in text

    def test_idempotent_on_preexisting_gap(self, tmp_path):
        page = tmp_path / "stub.md"
        _seed_page(
            page,
            content="> [!gap]\n> existing gap\n\nbody\n",
            metadata={"title": "Stub Page"},
        )
        augment._record_verdict_gap_callout(page, run_id="newid001", reason="retry")
        text = page.read_text(encoding="utf-8")
        # Should NOT have prepended a second gap callout.
        assert text.count("[!gap]") == 1
        # The new run_id should NOT have been added.
        assert "newid001" not in text


class TestMarkPageAugmented:
    """AC18 — _mark_page_augmented preserves wikilinks + order."""

    def test_preserves_wikilinks_list(self, tmp_path):
        page = tmp_path / "page.md"
        _seed_page(
            page,
            content="body\n",
            metadata={
                "title": "Page",
                "wikilinks": ["concepts/rag", "entities/karpathy"],
                "source": "raw/articles/x.md",
            },
        )
        augment._mark_page_augmented(page, source_url="https://example.org/x")
        loaded = frontmatter.load(str(page))
        assert loaded.metadata["wikilinks"] == ["concepts/rag", "entities/karpathy"]

    def test_forces_confidence_to_speculative(self, tmp_path):
        page = tmp_path / "page.md"
        _seed_page(
            page,
            content="body\n",
            metadata={
                "title": "Page",
                "confidence": "stated",
            },
        )
        augment._mark_page_augmented(page, source_url="https://example.org/x")
        loaded = frontmatter.load(str(page))
        assert loaded.metadata["confidence"] == "speculative"

    def test_preserves_non_alpha_custom_keys(self, tmp_path):
        page = tmp_path / "page.md"
        _seed_page(
            page,
            content="body\n",
            metadata={
                "title": "Page",
                "custom_priority": "high",
                "belief_state": "confirmed",
                "authored_by": "hybrid",
            },
        )
        order_before = _disk_key_order(page)
        augment._mark_page_augmented(page, source_url="https://example.org/x")
        order_after = _disk_key_order(page)
        # Order of PRE-EXISTING keys preserved; `confidence` may be added
        # IF not in original metadata, appended at end (dict insertion).
        # Original keys ordered: title, custom_priority, belief_state, authored_by
        # Then append: confidence (if new)
        # Filter to pre-existing keys and check their order.
        preexisting = [k for k in order_after if k in order_before]
        assert preexisting == order_before


class TestRecordAttempt:
    """AC18 — _record_attempt preserves order + stamps timestamp."""

    def test_stamps_last_augment_attempted(self, tmp_path):
        page = tmp_path / "stub.md"
        _seed_page(
            page,
            content="body\n",
            metadata={"title": "Stub"},
        )
        augment._record_attempt(page)
        loaded = frontmatter.load(str(page))
        assert "last_augment_attempted" in loaded.metadata
        timestamp = str(loaded.metadata["last_augment_attempted"])
        assert timestamp.endswith("Z")

    def test_preserves_custom_keys_order(self, tmp_path):
        page = tmp_path / "stub.md"
        _seed_page(
            page,
            content="body\n",
            metadata={
                "title": "Stub",
                "zzz_marker": "end",
                "aaa_marker": "start",
            },
        )
        order_before = _disk_key_order(page)
        augment._record_attempt(page)
        order_after = _disk_key_order(page)
        preexisting = [k for k in order_after if k in order_before]
        assert preexisting == order_before

    def test_error_swallowed_on_missing_file(self, tmp_path):
        """Docstring says failures are logged and swallowed."""
        missing = tmp_path / "does_not_exist.md"
        # Should not raise.
        augment._record_attempt(missing)


class TestMigrationCompleteness:
    """Threat T10 — verify no bare frontmatter.dumps remains in augment.py."""

    def test_no_bare_frontmatter_dumps_in_augment_module(self):
        """Module-level grep-equivalent: every frontmatter.dumps call must
        route through save_page_frontmatter. Uses importlib + source scan
        as a behavioural proxy — the wrapper is the sole enforcement point."""
        module = importlib.import_module("kb.lint.augment")
        module_path = Path(module.__file__)
        text = module_path.read_text(encoding="utf-8")
        # This test is deliberately a text scan: T10 explicitly checks
        # for migration completeness at source level. Per cycle-11 L1
        # note, source-scan tests are inspect.getsource in disguise —
        # but here it IS the contract under test (not the behaviour).
        # Complement with the behavioural tests above.
        assert "frontmatter.dumps(" not in text, (
            "Found bare frontmatter.dumps in augment.py — "
            "must route through save_page_frontmatter (AC18 / T10)."
        )

    def test_save_page_frontmatter_imported(self):
        """Complement: verify the wrapper is imported (reachable)."""
        from kb.lint.augment import save_page_frontmatter

        assert callable(save_page_frontmatter)
