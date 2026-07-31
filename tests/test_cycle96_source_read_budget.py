"""Cycle 96 — per-call total read-BYTE budget for the page↔source pairing.

Closes the Phase 4.5 MEDIUM entry recorded as the cycle-95 R1 P1 residual:
``kb_review_page`` (``build_review_context``) and ``kb_lint_deep``
(``build_fidelity_context``) both build LLM context by reading EVERY raw
source referenced by their one page. Both bound their OUTPUT — but neither
bounded the READ. ``pair_page_with_sources`` called ``read_text()`` on each
listed source with no per-file and no total cap, so a page citing a handful
of very large raw files pulled tens of MB into memory before any truncation
applied.

Acceptance criteria under test:

- **AC01** — ``kb.config.PAIRED_SOURCE_READ_MAX_BYTES`` exists as the
  per-call total read budget.
- **AC02** — ``pair_page_with_sources`` spends that budget across sources in
  frontmatter order: never reads more than the budget in total, marks a
  partially-read source ``truncated``, and marks a source reached with an
  exhausted budget ``skipped``. Partial reads are UTF-8 boundary-safe and
  still surface genuinely-invalid UTF-8 as an error (no silent ``ignore``).
- **AC03** — ``build_review_context`` gains the output budget it never had
  (``QUERY_CONTEXT_MAX_CHARS - _FENCE_OVERHEAD``) and renders an explicit
  notice for truncated/skipped sources instead of degrading silently.
- **AC04** — ``_cap_page_content`` / ``_CAP_TRUNCATION_MARKER`` move to the
  leaf module ``kb.utils.text`` and stay re-exported from
  ``kb.lint.semantic`` so the cycle-72 monkeypatch surface is unchanged.
"""

import pytest

from kb.config import QUERY_CONTEXT_MAX_CHARS
from kb.utils.text import _FENCE_OVERHEAD

PAGE_FRONTMATTER = (
    '---\ntitle: "Test"\nsource:\n{sources}'
    "created: 2026-01-01\nupdated: 2026-01-01\ntype: concept\n"
    "confidence: stated\n---\n\n# Test\n\nPage body.\n"
)


def _make_wiki(tmp_path, source_sizes, *, page_body="Page body."):
    """Build a wiki page citing N raw sources of the given byte sizes.

    Returns ``(wiki_dir, raw_dir, [source_paths])``. Each source is filled
    with a distinct repeating ASCII marker so a test can tell which source a
    slice of assembled output came from.
    """
    wiki_dir = tmp_path / "wiki"
    raw_dir = tmp_path / "raw"
    (wiki_dir / "concepts").mkdir(parents=True)
    (raw_dir / "articles").mkdir(parents=True)

    refs = []
    paths = []
    for i, size in enumerate(source_sizes):
        name = f"src{i}.md"
        marker = chr(ord("A") + i)
        path = raw_dir / "articles" / name
        path.write_text(marker * size, encoding="utf-8")
        refs.append(f'  - "raw/articles/{name}"\n')
        paths.append(path)

    page = wiki_dir / "concepts" / "test.md"
    page.write_text(
        PAGE_FRONTMATTER.format(sources="".join(refs)).replace("Page body.", page_body),
        encoding="utf-8",
    )
    return wiki_dir, raw_dir, paths


# ── AC01 — the budget constant exists ────────────────────────────────


class TestAC01_BudgetConstant:
    def test_constant_exists_and_is_a_positive_int(self):
        import kb.config as config

        assert hasattr(config, "PAIRED_SOURCE_READ_MAX_BYTES"), (
            "AC01: kb.config.PAIRED_SOURCE_READ_MAX_BYTES missing — the "
            "per-call total read budget has no single source of truth"
        )
        value = config.PAIRED_SOURCE_READ_MAX_BYTES
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value > 0

    def test_budget_is_resolved_at_call_time(self, tmp_path, monkeypatch):
        """Cycle-18 L1 / cycle-19 L2: a monkeypatched module binding MUST take
        effect. A default argument captured at ``def`` time would defeat this
        and silently pin the shipped default in every test below."""
        from kb.review import context as context_mod

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [5000])
        monkeypatch.setattr(context_mod, "PAIRED_SOURCE_READ_MAX_BYTES", 100)

        paired = context_mod.pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir
        )
        content = paired["source_contents"][0]["content"]
        assert len(content) <= 100, (
            "AC01: monkeypatched PAIRED_SOURCE_READ_MAX_BYTES had no effect — "
            "budget is bound at import time, not call time"
        )


# ── AC02 — bounded, in-order read spend ──────────────────────────────


class TestAC02_ReadBudgetSpend:
    def test_total_bytes_read_never_exceeds_budget(self, tmp_path):
        """The defect: 4 x 100 KB sources loaded 400 KB regardless of caps."""
        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [100_000] * 4)
        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=150_000
        )

        total = sum(len(s.get("content") or "") for s in paired["source_contents"])
        assert total <= 150_000, (
            f"AC02: read {total} bytes against a 150,000-byte budget — "
            "the per-call total read cap is not enforced"
        )

    def test_budget_is_spent_in_frontmatter_order(self, tmp_path):
        """Earlier sources get the budget first; later ones are cut off. The
        alternative (even split) would truncate a page's primary source to
        make room for a trailing footnote source."""
        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [1000, 1000, 1000])
        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=1500
        )
        first, second, third = paired["source_contents"]

        assert first["content"] == "A" * 1000, "first source must be read in full"
        assert second.get("content"), "second source must receive the remaining budget"
        assert set(second["content"]) == {"B"}
        assert len(second["content"]) == 500
        assert not third.get("content"), "third source must be skipped — budget exhausted"

    def test_partial_read_is_flagged_truncated_with_byte_counts(self, tmp_path):
        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [10_000])
        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=4_000
        )
        entry = paired["source_contents"][0]

        assert entry.get("truncated") is True, (
            "AC02: a partially-read source must be machine-readably flagged, "
            "or consumers cannot tell a short file from a cut-off one"
        )
        assert entry["bytes_read"] == 4_000
        assert entry["bytes_total"] == 10_000

    def test_untruncated_source_carries_no_truncation_flags(self, tmp_path):
        """Absence == no caveat, matching the cycle-88 ``durable``/``status``
        and cycle-73 ``get_prompt_version`` legacy-default convention."""
        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [100])
        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=10_000
        )
        entry = paired["source_contents"][0]

        assert entry["content"] == "A" * 100
        assert "truncated" not in entry
        assert "skipped" not in entry

    def test_skipped_source_is_flagged_and_reports_its_size(self, tmp_path):
        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [1000, 2000])
        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=1000
        )
        skipped = paired["source_contents"][1]

        assert skipped.get("skipped") is True
        assert skipped["content"] is None
        assert skipped["bytes_total"] == 2000
        assert "budget" in skipped["error"].lower()

    def test_partial_read_does_not_split_a_utf8_character(self, tmp_path):
        """A budget cut landing mid-sequence must not raise and must not emit
        a replacement char. Multi-byte content + a deliberately odd budget."""
        from kb.review.context import pair_page_with_sources

        wiki_dir = tmp_path / "wiki"
        raw_dir = tmp_path / "raw"
        (wiki_dir / "concepts").mkdir(parents=True)
        (raw_dir / "articles").mkdir(parents=True)
        # 3-byte-per-char CJK; a 100-byte cut lands inside char 34.
        (raw_dir / "articles" / "src0.md").write_text("识" * 200, encoding="utf-8")
        (wiki_dir / "concepts" / "test.md").write_text(
            PAGE_FRONTMATTER.format(sources='  - "raw/articles/src0.md"\n'),
            encoding="utf-8",
        )

        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=100
        )
        content = paired["source_contents"][0]["content"]

        assert content == "识" * 33, (
            f"AC02: partial read must stop at the last COMPLETE UTF-8 character; got {content!r}"
        )
        assert "�" not in content, "no replacement characters"

    def test_invalid_utf8_still_reported_as_an_error(self, tmp_path):
        """Boundary-safe decoding must not become ``errors='ignore'`` — that
        would silently swallow genuinely corrupt bytes that the pre-cycle-96
        full-read path surfaced as an error entry."""
        from kb.review.context import pair_page_with_sources

        wiki_dir = tmp_path / "wiki"
        raw_dir = tmp_path / "raw"
        (wiki_dir / "concepts").mkdir(parents=True)
        (raw_dir / "articles").mkdir(parents=True)
        # 0xFF is never valid UTF-8, and it sits mid-buffer, not at the cut.
        (raw_dir / "articles" / "src0.md").write_bytes(b"ok " + b"\xff" + b" more" * 100)
        (wiki_dir / "concepts" / "test.md").write_text(
            PAGE_FRONTMATTER.format(sources='  - "raw/articles/src0.md"\n'),
            encoding="utf-8",
        )

        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=50
        )
        entry = paired["source_contents"][0]

        assert entry["content"] is None
        assert entry.get("error"), "invalid UTF-8 must surface as an error entry"

    def test_oversized_file_is_never_fully_loaded(self, tmp_path, monkeypatch):
        """Guards the actual memory defect rather than only the returned
        value: a source far larger than the budget must not be handed to
        ``read_text()`` (which materialises the whole file first)."""
        from pathlib import Path

        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [500_000])

        def _explode(self, *a, **kw):
            raise AssertionError(
                "AC02: whole-file read_text() reached on a source that "
                "exceeds the read budget — the cap is applied AFTER loading"
            )

        monkeypatch.setattr(Path, "read_text", _explode)
        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=1000
        )
        assert len(paired["source_contents"][0]["content"]) == 1000

    def test_missing_and_unreadable_sources_still_report_as_before(self, tmp_path):
        """Negative control: cycle-96 must not change the existing not-found
        entry shape, and a not-found source must not consume budget."""
        from kb.review.context import pair_page_with_sources

        wiki_dir, raw_dir, paths = _make_wiki(tmp_path, [100, 100])
        paths[0].unlink()

        paired = pair_page_with_sources(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=150
        )
        missing, present = paired["source_contents"]

        assert missing["content"] is None
        assert "not found" in missing["error"].lower()
        assert present["content"] == "B" * 100, "a missing source must not consume read budget"


# ── AC03 — build_review_context output budget + explicit notices ─────


class TestAC03_ReviewContextBudget:
    def test_assembled_output_respects_the_context_budget(self, tmp_path):
        """The pre-cycle-96 builder inlined every source verbatim with no cap
        at all — unlike ``build_fidelity_context``, which reserves
        ``_FENCE_OVERHEAD`` from ``QUERY_CONTEXT_MAX_CHARS``."""
        from kb.review.context import build_review_context

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [200_000] * 3)
        out = build_review_context("concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir)

        assert len(out) <= QUERY_CONTEXT_MAX_CHARS, (
            f"AC03: assembled review context is {len(out):,} chars, over the "
            f"{QUERY_CONTEXT_MAX_CHARS:,} budget"
        )

    def test_oversized_page_body_is_capped(self, tmp_path):
        from kb.review.context import build_review_context

        wiki_dir, raw_dir, _ = _make_wiki(
            tmp_path, [100], page_body="X" * (QUERY_CONTEXT_MAX_CHARS + 50_000)
        )
        out = build_review_context("concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir)

        assert len(out) <= QUERY_CONTEXT_MAX_CHARS
        assert "truncated" in out.lower()

    def test_truncated_source_gets_an_explicit_notice(self, tmp_path):
        from kb.review.context import build_review_context

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [50_000])
        # Force the READ budget low so the notice comes from AC02, not AC03.
        out = build_review_context(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=1_000
        )

        assert "truncated" in out.lower(), (
            "AC03: a source cut off by the read budget must be announced in "
            "the assembled context — silent degradation misleads the reviewer "
            "LLM into scoring fidelity against material it never saw"
        )

    def test_skipped_source_gets_an_explicit_notice(self, tmp_path):
        from kb.review.context import build_review_context

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [2_000, 2_000])
        out = build_review_context(
            "concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir, read_budget=2_000
        )

        assert "raw/articles/src1.md" in out, "skipped source must still be listed"
        assert "budget" in out.lower()

    def test_pinned_header_shape_is_unchanged(self, tmp_path):
        """Negative control for the cycle-72 / phase-4.5-H14 pins: the
        ``## Raw Source N:`` header text and the ``<wiki_context>`` fence
        must survive the budget rework."""
        from kb.review.context import build_review_context

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [100])
        out = build_review_context("concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir)

        assert "## Raw Source 1: raw/articles/src0.md" in out
        assert "<wiki_context>" in out and "</wiki_context>" in out
        assert "<wiki_page_body>" not in out and "<raw_source_1>" not in out

    def test_fence_overhead_is_reserved(self, tmp_path, monkeypatch):
        """The wrap adds a fixed assertion + tags; the budget must reserve it
        so the WRAPPED total, not the pre-wrap body, fits."""
        from kb.review import context as context_mod

        wiki_dir, raw_dir, _ = _make_wiki(tmp_path, [40_000])
        monkeypatch.setattr(context_mod, "QUERY_CONTEXT_MAX_CHARS", 20_000)
        out = context_mod.build_review_context("concepts/test", wiki_dir=wiki_dir, raw_dir=raw_dir)

        assert len(out) <= 20_000
        assert _FENCE_OVERHEAD > 0


# ── AC04 — shared cap helper moves to the leaf module ────────────────


class TestAC04_CapHelperExtraction:
    def test_helper_lives_in_utils_text(self):
        from kb.utils.text import _cap_page_content

        assert _cap_page_content("abcdef", 100) == "abcdef"
        capped = _cap_page_content("x" * 500, 100)
        assert len(capped) <= 100

    def test_semantic_re_export_is_the_same_object(self):
        """Cycle-74 ``tier_boundary`` precedent: the extraction must not move
        the monkeypatch surface that cycle-72 tests already target."""
        from kb.lint import semantic
        from kb.utils import text

        assert semantic._cap_page_content is text._cap_page_content
        assert semantic._CAP_TRUNCATION_MARKER == text._CAP_TRUNCATION_MARKER

    def test_review_context_uses_the_shared_helper_not_a_copy(self):
        """A second private copy in ``review/context.py`` would drift from the
        cycle-72 R2 Codex M-1 marker-reservation fix."""
        import inspect

        from kb.review import context as context_mod

        src = inspect.getsource(context_mod)
        assert "def _cap_page_content" not in src, (
            "AC04: review/context.py defines its own _cap_page_content — "
            "import the kb.utils.text one instead"
        )

    @pytest.mark.parametrize("max_chars", [50, 120, 4096])
    def test_capped_length_never_exceeds_max(self, max_chars):
        from kb.utils.text import _cap_page_content

        assert len(_cap_page_content("y" * 10_000, max_chars)) <= max_chars
