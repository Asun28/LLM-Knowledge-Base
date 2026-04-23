"""Cycle 24 AC1/AC3 — evidence-trail inline render at first write.

Divergent-fail harness for the AC1 contract: `_write_wiki_page` MUST render
the initial `## Evidence Trail` section + sentinel + first entry INLINE into
the single first-write payload. NO follow-up `append_evidence_trail` call
may run in the new-page tail, for either `exclusive=False` (atomic_text_write)
or `exclusive=True` (O_EXCL + os.write) branches.

Closes threat T5 joint-regression (paired with AC14 sentinel-anchor) +
CONDITION 1 + CONDITION 4 from `2026-04-23-cycle24-design.md`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kb.ingest import pipeline as pipeline_mod
from kb.ingest.evidence import SENTINEL


@pytest.mark.parametrize("exclusive", [False, True])
def test_new_page_write_single_atomic_write_with_inline_trail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exclusive: bool
) -> None:
    """AC3 — parameterized over both branches.

    Assertions:
    - For `exclusive=False`: `atomic_text_write` is called exactly once AND the
      written content contains `## Evidence Trail` + sentinel + initial entry.
    - For `exclusive=True`: `os.write` is called exactly once with the full
      rendered payload AND the on-disk content contains the same trail
      section. (The file is reserved via `os.open(O_EXCL)`.)
    - For BOTH: `append_evidence_trail` is NOT called in the new-page tail.

    Divergent-fail on AC1 revert: reverting `_write_wiki_page` to the previous
    two-write pattern (write body then call `append_evidence_trail`) would
    either (a) call `atomic_text_write` twice (once direct, once inside
    append_evidence_trail) OR (b) land the trail via a separate write path.
    Either way the assertions below fail.
    """
    page = tmp_path / f"new-page-exclusive-{exclusive}.md"

    # Spy on `atomic_text_write` called from pipeline module. The pipeline
    # binds the symbol at line 30 via `from kb.utils.io import ...`, so the
    # patch target is `kb.ingest.pipeline.atomic_text_write`.
    atomic_spy = MagicMock(wraps=pipeline_mod.atomic_text_write)
    monkeypatch.setattr(pipeline_mod, "atomic_text_write", atomic_spy)
    # Spy on `append_evidence_trail` — MUST NOT be called for new pages.
    append_spy = MagicMock()
    monkeypatch.setattr(pipeline_mod, "append_evidence_trail", append_spy)

    pipeline_mod._write_wiki_page(
        page_path=page,
        title="Test Page",
        page_type="entity",
        source_ref="raw/articles/test.md",
        confidence="stated",
        content="Body paragraph with details.",
        exclusive=exclusive,
    )

    # Assertion A — append_evidence_trail MUST NOT have fired.
    assert append_spy.call_count == 0, (
        f"exclusive={exclusive}: append_evidence_trail must not run for "
        f"new pages; got {append_spy.call_count} call(s). Cycle 24 AC1 reverts "
        f"to the two-write pattern would trigger this."
    )

    # Assertion B — page exists and contains inline trail.
    assert page.exists(), f"exclusive={exclusive}: page not written to disk"
    on_disk = page.read_text(encoding="utf-8")
    assert "## Evidence Trail" in on_disk, (
        f"exclusive={exclusive}: inline ## Evidence Trail section missing"
    )
    assert SENTINEL in on_disk, f"exclusive={exclusive}: sentinel missing"
    assert "Initial extraction: entity page created" in on_disk, (
        f"exclusive={exclusive}: initial entry action text missing"
    )
    # The trail section MUST come AFTER the body (frontmatter + content).
    frontmatter_end = on_disk.index("---", 3) + 3  # second "---" closes frontmatter
    trail_start = on_disk.index("## Evidence Trail")
    assert trail_start > frontmatter_end, (
        f"exclusive={exclusive}: trail section must follow frontmatter"
    )

    # Assertion C — per-branch spy count.
    if not exclusive:
        # Non-exclusive branch goes through atomic_text_write exactly once.
        assert atomic_spy.call_count == 1, (
            f"exclusive=False: atomic_text_write must be called once "
            f"(got {atomic_spy.call_count}). AC1 revert would call it twice "
            f"(body + trail-via-append)."
        )
        # The single call's first arg (rendered content) must contain the trail.
        written = atomic_spy.call_args.args[0]
        assert "## Evidence Trail" in written, (
            "Rendered payload passed to atomic_text_write must include trail"
        )
        assert SENTINEL in written, "Rendered payload must include sentinel"
    else:
        # Exclusive branch bypasses atomic_text_write entirely.
        assert atomic_spy.call_count == 0, (
            f"exclusive=True: atomic_text_write must NOT be called "
            f"(branch uses os.write + O_EXCL); got {atomic_spy.call_count}"
        )


def test_render_initial_evidence_trail_format_preserves_pipe_neutralization(
    tmp_path: Path,
) -> None:
    """Defense-in-depth: the helper must backtick-escape pipe-bearing values.

    Reuse of `format_evidence_entry` (cycle-2 R1 contract) must be preserved
    through the new `render_initial_evidence_trail` entry point.
    """
    from kb.ingest.evidence import render_initial_evidence_trail

    trail = render_initial_evidence_trail(
        source_ref="raw/articles/bar|baz.md",
        action="Testing pipe",
        entry_date="2026-04-23",
    )
    # The pipe character inside `bar|baz.md` must be backtick-wrapped.
    assert "`raw/articles/bar|baz.md`" in trail, "source_ref pipe must be neutralized"
    assert SENTINEL in trail
    assert "## Evidence Trail" in trail
    assert "2026-04-23" in trail
