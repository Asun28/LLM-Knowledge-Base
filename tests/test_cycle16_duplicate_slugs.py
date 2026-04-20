"""Cycle 16 AC10 + AC13 + T6 + T14 — check_duplicate_slugs behavioural tests.

Direct import + tmp_wiki fixture. No source-scan assertions.
"""

from pathlib import Path

import pytest

from kb.lint.checks import (
    _bounded_edit_distance,
    _slug_for_duplicate,
    check_duplicate_slugs,
)


def _write_page(wiki_dir: Path, page_id: str) -> Path:
    """Create a minimal page at `<wiki>/<page_id>.md` with valid frontmatter."""
    path = wiki_dir / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f'title: "{page_id}"\n'
        'source: ["raw/articles/x.md"]\n'
        "created: 2026-04-01\n"
        "updated: 2026-04-01\n"
        "type: concept\n"
        "confidence: stated\n"
        "---\n\nbody.\n",
        encoding="utf-8",
    )
    return path


class TestBoundedEditDistance:
    def test_identical_strings_zero(self) -> None:
        assert _bounded_edit_distance("abc", "abc", 3) == 0

    def test_single_substitution_one(self) -> None:
        assert _bounded_edit_distance("cat", "cot", 3) == 1

    def test_transposition_two(self) -> None:
        # "attention" vs "attnetion" — swap of 'e' and 'n' = 2 operations.
        assert _bounded_edit_distance("attention", "attnetion", 3) == 2

    def test_length_diff_gt_threshold_short_circuits(self) -> None:
        """Levenshtein lower bound: |len(a)-len(b)| > threshold → > threshold."""
        assert _bounded_edit_distance("abc", "abcdefgh", 3) == 4

    def test_early_exit_above_threshold(self) -> None:
        """Distance above threshold returns threshold+1 (caller distinguishes)."""
        d = _bounded_edit_distance("abcdef", "zzzzzz", 2)
        assert d == 3  # threshold + 1 marker


class TestCheckDuplicateSlugs:
    def test_attention_attnetion_flagged_distance_2(self, tmp_wiki) -> None:
        """AC13 — classic typo pair flagged at distance 2."""
        _write_page(tmp_wiki, "concepts/attention")
        _write_page(tmp_wiki, "concepts/attnetion")
        issues = check_duplicate_slugs(tmp_wiki)
        assert len(issues) == 1
        assert issues[0]["distance"] == 2

    def test_attention_mechanism_not_flagged(self, tmp_wiki) -> None:
        """AC13 — length diff 10 is > threshold → not flagged."""
        _write_page(tmp_wiki, "concepts/attention")
        _write_page(tmp_wiki, "concepts/attention-mechanism")
        issues = check_duplicate_slugs(tmp_wiki)
        assert issues == []

    def test_length_diff_3_flagged(self, tmp_wiki) -> None:
        """Q10/C6 — distance-3 pair with length diff 3 MUST be flagged."""
        _write_page(tmp_wiki, "concepts/foo")
        _write_page(tmp_wiki, "concepts/foobar")
        issues = check_duplicate_slugs(tmp_wiki)
        # "concepts/foo" vs "concepts/foobar" — distance 3, flagged.
        assert any(
            i.get("distance") == 3
            and {i.get("slug_a"), i.get("slug_b")} == {"concepts/foo", "concepts/foobar"}
            for i in issues
        )

    def test_distance_0_excluded_and_subdir_retained(self, tmp_wiki) -> None:
        """AC10 + T14 — distance-0 pairs excluded; subdir retention keeps
        parallel-stem pages apart so they aren't false-matched.

        `concepts/topic` vs `entities/topic` share a stem but the full lowered
        `page_id` differs by 7+ characters ("concepts" -> "entities"), far
        above the threshold (3). Correctly NOT flagged — demonstrates subdir
        retention prevents false-merging of parallel-subdir pages.
        """
        _write_page(tmp_wiki, "concepts/topic")
        _write_page(tmp_wiki, "entities/topic")
        issues = check_duplicate_slugs(tmp_wiki)
        assert issues == []

    def test_distance_0_with_alias_excluded(self, tmp_wiki) -> None:
        """AC10 — true distance-0 (same full page_id) cannot occur on a
        real filesystem (one file), but the algorithm still documents the
        exclusion: same slug → skipped even if the pair reaches comparison.
        """
        # Construct synthetic page list with duplicate slugs (same id reached
        # twice through a symlink-ish scenario).
        fake = [
            Path(tmp_wiki / "concepts/x.md"),
            Path(tmp_wiki / "concepts/x.md"),  # duplicate reference
        ]
        _write_page(tmp_wiki, "concepts/x")
        issues = check_duplicate_slugs(tmp_wiki, pages=fake)
        assert issues == []

    def test_slug_form_is_full_lowered_page_id(self, tmp_wiki) -> None:
        """AC10 + T14 — slug form is full lowered page_id with subdir retained."""
        # Create one page to verify _slug_for_duplicate output shape.
        p = _write_page(tmp_wiki, "concepts/Attention")
        slug = _slug_for_duplicate(p, tmp_wiki)
        assert slug == "concepts/attention"  # lowercased, subdir retained
        assert "/" in slug  # subdir NOT stripped
        # Underscores normalized to hyphens.
        p2 = _write_page(tmp_wiki, "concepts/foo_bar")
        slug2 = _slug_for_duplicate(p2, tmp_wiki)
        assert slug2 == "concepts/foo-bar"

    def test_empty_wiki_returns_empty_list(self, tmp_wiki) -> None:
        assert check_duplicate_slugs(tmp_wiki) == []

    def test_single_page_returns_empty_list(self, tmp_wiki) -> None:
        _write_page(tmp_wiki, "concepts/only")
        assert check_duplicate_slugs(tmp_wiki) == []

    def test_large_wiki_returns_skip_record(self, tmp_wiki) -> None:
        """T6 — wiki > 10k pages returns a single skip record (no O(N²) scan)."""
        fake_pages = [Path(f"{tmp_wiki}/concepts/page{i}.md") for i in range(10_001)]
        issues = check_duplicate_slugs(tmp_wiki, pages=fake_pages)
        assert len(issues) == 1
        assert issues[0]["skipped_reason"].startswith("wiki too large")
        assert issues[0]["distance"] == -1

    def test_symmetric_deduplication(self, tmp_wiki) -> None:
        """A pair flagged once, not twice (A<->B and B<->A dedup)."""
        _write_page(tmp_wiki, "concepts/one")
        _write_page(tmp_wiki, "concepts/ono")  # distance 2
        issues = check_duplicate_slugs(tmp_wiki)
        assert len(issues) == 1


class TestPagesKwargThreading:
    def test_preloaded_pages_not_rescanned(self, tmp_wiki) -> None:
        """When pages kwarg provided, no extra disk walk (contract)."""
        _write_page(tmp_wiki, "concepts/a")
        _write_page(tmp_wiki, "concepts/b")
        from kb.utils.pages import scan_wiki_pages

        pages = scan_wiki_pages(tmp_wiki)
        issues = check_duplicate_slugs(tmp_wiki, pages=pages)
        # "concepts/a" vs "concepts/b" — distance 1, flagged.
        assert len(issues) == 1


# Sanity — `pytest` fixture export guard (keeps ruff happy if the fixture
# moves).
assert pytest is not None  # noqa: S101
