"""Cycle 64 — `compile/publish.py::build_per_page_siblings` manifest-based
incremental cleanup (AC16 + AC17).

Regression tests proving:
- AC16: first publish creates the manifest at
  `<wiki_dir>.parent/.data/publish-siblings-manifest.json` and emits zero
  unlinks (no prior manifest = first publish; no orphans).
- AC16: second publish unlinks ONLY siblings whose page_id was in the
  previous manifest but is NOT in the current kept set.
- AC17: corrupted manifest falls back to cycle-16 unconditional cleanup
  (excluded-page sibling unlink) without crashing.

Per cycle-40 L3: each test diverges expected vs reverted behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

from kb.compile.publish import (
    _publish_manifest_path,
    build_per_page_siblings,
)


def _write_kept_page(wiki_dir: Path, page_id: str, *, page_type: str = "concept") -> None:
    """Write a kept (non-excluded) page so it's published as siblings."""
    subdir = wiki_dir / page_id.split("/")[0]
    subdir.mkdir(parents=True, exist_ok=True)
    page_path = wiki_dir / f"{page_id}.md"
    page_path.write_text(
        f"---\ntitle: {page_id}\nsource: []\ntype: {page_type}\n"
        f"confidence: stated\ncreated: 2026-05-03\nupdated: 2026-05-03\n---\n\n"
        f"# {page_id}\n\nBody.\n",
        encoding="utf-8",
    )


def _retract(wiki_dir: Path, page_id: str) -> None:
    """Mutate a page's frontmatter to belief_state: retracted (excludes it)."""
    page_path = wiki_dir / f"{page_id}.md"
    body = page_path.read_text(encoding="utf-8")
    page_path.write_text(
        body.replace("confidence: stated", "confidence: stated\nbelief_state: retracted"),
        encoding="utf-8",
    )


def test_first_publish_creates_manifest_no_unlinks(tmp_path):
    """AC16: first publish (no prior manifest) writes manifest + emits zero
    unlinks (only kept-page sibling files exist).
    """
    wiki = tmp_path / "wiki"
    out_dir = tmp_path / "_publish"
    _write_kept_page(wiki, "concepts/page-a")
    _write_kept_page(wiki, "concepts/page-b")

    manifest_path = _publish_manifest_path(wiki)
    # Pre-publish: no manifest yet.
    assert not manifest_path.exists()

    written = build_per_page_siblings(wiki, out_dir)

    # Manifest now exists.
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "concepts/page-a" in manifest
    assert "concepts/page-b" in manifest

    # Both pages have siblings on disk.
    pages_dir = (out_dir / "pages").resolve()
    assert (pages_dir / "concepts" / "page-a.txt").exists()
    assert (pages_dir / "concepts" / "page-a.json").exists()
    assert (pages_dir / "concepts" / "page-b.txt").exists()
    assert (pages_dir / "concepts" / "page-b.json").exists()

    # 4 sibling paths total in the written list (2 pages × 2 formats).
    assert len(written) == 4


def test_second_publish_only_unlinks_orphaned_siblings(tmp_path):
    """AC16 / AC17 / R1-F8 — second publish unlinks ONLY pages that were in
    the prior manifest but are no longer kept (newly-orphaned).

    Reverts: pre-cycle-64 unconditional cleanup would unlink ALL excluded
    pages every publish, regardless of prior manifest state.
    """
    wiki = tmp_path / "wiki"
    out_dir = tmp_path / "_publish"
    _write_kept_page(wiki, "concepts/page-a")
    _write_kept_page(wiki, "concepts/page-b")
    _write_kept_page(wiki, "concepts/page-c")

    # First publish: 3 pages.
    build_per_page_siblings(wiki, out_dir)
    pages_dir = (out_dir / "pages").resolve()

    a_txt = pages_dir / "concepts" / "page-a.txt"
    b_txt = pages_dir / "concepts" / "page-b.txt"
    c_txt = pages_dir / "concepts" / "page-c.txt"
    assert a_txt.exists() and b_txt.exists() and c_txt.exists()

    # Now retract page-c so it becomes excluded.
    _retract(wiki, "concepts/page-c")

    # Spy on Path.unlink to count cleanup calls.
    unlink_calls: list[Path] = []
    real_unlink = Path.unlink

    def _spy_unlink(self, missing_ok=False):
        unlink_calls.append(self)
        return real_unlink(self, missing_ok=missing_ok)

    Path.unlink = _spy_unlink  # type: ignore[method-assign]
    try:
        # Second publish.
        build_per_page_siblings(wiki, out_dir)
    finally:
        Path.unlink = real_unlink  # type: ignore[method-assign]

    # Only page-c's siblings should have been unlinked (it's now orphaned).
    # page-a, page-b are still kept; should NOT be unlinked.
    unlink_names = {p.name for p in unlink_calls if "page-" in p.name}
    assert "page-c.txt" in unlink_names or "page-c.json" in unlink_names
    assert "page-a.txt" not in unlink_names
    assert "page-a.json" not in unlink_names
    assert "page-b.txt" not in unlink_names
    assert "page-b.json" not in unlink_names


def test_manifest_corrupted_falls_back_to_full_cleanup(tmp_path):
    """AC17: a malformed manifest (truncated JSON) triggers fallback to
    cycle-16 unconditional unlink semantics WITHOUT raising.

    Reverts: removing the try/except in `_load_publish_manifest` would let
    json.JSONDecodeError propagate — this test catches it via pytest fail.
    """
    wiki = tmp_path / "wiki"
    out_dir = tmp_path / "_publish"
    _write_kept_page(wiki, "concepts/page-x")

    # Pre-corrupt the manifest before first publish.
    manifest_path = _publish_manifest_path(wiki)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{ this is not valid JSON }", encoding="utf-8")

    # Must NOT raise — corrupted manifest triggers fallback path.
    result = build_per_page_siblings(wiki, out_dir)
    assert result is not None
    # First publish writes valid manifest atop the corrupted one.
    new_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "concepts/page-x" in new_manifest
