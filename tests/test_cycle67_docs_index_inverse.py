"""Cycle 67 AC14 — docs/reference/INDEX.md inverse-direction consistency.

Cycle 65 AC20 (`tests/test_docs_reference_index_complete.py`) already verifies
the FORWARD direction: every `docs/reference/*.md` file (except INDEX.md and
README.md) appears in INDEX.md AND in CLAUDE.md's Detailed Documentation
table. This is "no orphan files" coverage.

Cycle 67 AC14 adds the INVERSE direction: every `*.md` filename mentioned in
INDEX.md or CLAUDE.md's table MUST correspond to a real file. Closes the
typo class — e.g. `architecturee.md` in INDEX.md would silently pass
cycle-65 AC20 but fail this test.

Per R2-F19 / C-AC14-multilink: regex MUST handle multiple inline links per
line.
"""

from __future__ import annotations

import re
from pathlib import Path


_REF_DIR = Path("docs/reference")
_INDEX = _REF_DIR / "INDEX.md"
_CLAUDE = Path("CLAUDE.md")
_INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\(docs/reference/([^)]+\.md)\)")


def _real_files() -> set[str]:
    """Set of file basenames in docs/reference/, excluding meta files."""
    return {
        p.name
        for p in _REF_DIR.glob("*.md")
        if p.name not in {"INDEX.md", "README.md"}
    }


def _entries_in(path: Path) -> set[str]:
    """Extract all `docs/reference/<name>.md` references from a markdown file
    using inline-link regex. Returns the set of basenames."""
    content = path.read_text(encoding="utf-8")
    return set(_INLINE_LINK_RE.findall(content))


def test_t14a_index_entries_all_correspond_to_real_files() -> None:
    """T14-A: every `docs/reference/<name>.md` referenced inside INDEX.md
    MUST correspond to a real file. Catches typos / stale entries.
    """
    real = _real_files()
    referenced = _entries_in(_INDEX)
    orphan_entries = referenced - real
    assert not orphan_entries, (
        f"AC14 T14-A: INDEX.md inline-link entries that don't map to a real "
        f"file: {orphan_entries}"
    )


def test_t14b_claude_md_table_entries_all_correspond_to_real_files() -> None:
    """T14-B: every `docs/reference/<name>.md` referenced inside CLAUDE.md
    (table OR prose) MUST correspond to a real file.
    """
    real = _real_files() | {"INDEX.md", "README.md"}
    referenced = _entries_in(_CLAUDE)
    orphan_entries = referenced - real
    assert not orphan_entries, (
        f"AC14 T14-B: CLAUDE.md inline-link entries that don't map to a real "
        f"file: {orphan_entries}"
    )


def test_t14c_multilink_per_line_regex(tmp_path: Path) -> None:
    """T14-C / C-AC14-multilink: regex MUST detect multiple inline links per
    line. Per R2-F19 design gate condition.
    """
    fixture = tmp_path / "fixture.md"
    fixture.write_text(
        "See [architecture](docs/reference/architecture.md) and "
        "[testing](docs/reference/testing.md) on the same line.\n",
        encoding="utf-8",
    )
    matches = _INLINE_LINK_RE.findall(fixture.read_text(encoding="utf-8"))
    assert len(matches) == 2, (
        f"AC14 T14-C: regex MUST detect both links on one line. "
        f"Got {len(matches)}: {matches!r}"
    )
    assert "architecture.md" in matches
    assert "testing.md" in matches


def test_t14d_regex_ignores_reference_style_links(tmp_path: Path) -> None:
    """T14-D: per R2-F18 (REJECTED scope expansion), reference-style links
    (`[label][ref]` + `[ref]: docs/reference/foo.md`) are intentionally NOT
    detected. CLAUDE.md uses inline-link only by convention.

    This test pins the convention.
    """
    fixture = tmp_path / "ref_style.md"
    fixture.write_text(
        "See [architecture][arch].\n\n[arch]: docs/reference/architecture.md\n",
        encoding="utf-8",
    )
    matches = _INLINE_LINK_RE.findall(fixture.read_text(encoding="utf-8"))
    assert matches == [], (
        f"AC14 T14-D: reference-style link should NOT be detected by inline "
        f"regex. Got: {matches!r}"
    )


def test_t14e_negative_control_orphan_entry_detected(tmp_path: Path) -> None:
    """T14-E (divergent-fail): synthesize a fake INDEX.md with a typo entry
    (`architecturee.md` instead of `architecture.md`) and confirm the
    inverse-check would catch it.
    """
    fake_ref_dir = tmp_path / "docs" / "reference"
    fake_ref_dir.mkdir(parents=True)
    (fake_ref_dir / "architecture.md").write_text("real file", encoding="utf-8")

    fake_index = tmp_path / "INDEX.md"
    fake_index.write_text(
        "See [architecture](docs/reference/architecturee.md) — typo!\n",
        encoding="utf-8",
    )

    real = {p.name for p in fake_ref_dir.glob("*.md")}
    referenced = set(_INLINE_LINK_RE.findall(fake_index.read_text(encoding="utf-8")))
    orphans = referenced - real
    assert "architecturee.md" in orphans, (
        f"AC14 T14-E: inverse-check MUST catch typo'd filename. Got orphans: "
        f"{orphans!r}"
    )
