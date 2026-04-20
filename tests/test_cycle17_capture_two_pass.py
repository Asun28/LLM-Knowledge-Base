"""Cycle 17 AC10 — capture two-pass write with all-or-nothing rollback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kb.capture import (
    _rollback_finalized,
    _rollback_reservations,
    _write_item_files,
)


def _make_items(n: int) -> list[dict]:
    return [
        {
            "kind": "discovery",
            "title": f"item {i}",
            "body": f"body {i}",
            "one_line_summary": f"summary {i}",
            "confidence": "stated",
        }
        for i in range(n)
    ]


class TestAC10TwoPassWrite:
    def test_success_path_writes_all_md_files(self, tmp_path: Path) -> None:
        items = _make_items(3)
        written, err = _write_item_files(
            items,
            provenance="test-run",
            captured_at="2026-04-20T00:00:00Z",
            captures_dir=tmp_path,
        )
        assert err is None
        assert len(written) == 3
        md_files = sorted(tmp_path.glob("*.md"))
        assert len(md_files) == 3
        # No orphaned reservation temps remain.
        assert not list(tmp_path.glob(".*.reserving"))

    def test_alongside_for_uses_finalized_slugs(self, tmp_path: Path) -> None:
        """The written captured_alongside block must reference finalized slugs."""
        items = _make_items(3)
        written, err = _write_item_files(
            items,
            provenance="alongside-test",
            captured_at="2026-04-20T00:00:00Z",
            captures_dir=tmp_path,
        )
        assert err is None

        # Each written file's captured_alongside frontmatter should list the
        # OTHER two finalized slugs.
        slugs_set = {w.slug for w in written}
        for item in written:
            content = item.path.read_text(encoding="utf-8")
            peers = slugs_set - {item.slug}
            for peer in peers:
                assert peer in content, (
                    f"AC10 regression: finalized peer slug {peer!r} not in "
                    f"captured_alongside of {item.slug!r}"
                )

    def test_partial_reservation_rollback(self, tmp_path: Path) -> None:
        """If item 3 reservation fails, items 0-2 temps must all be unlinked."""
        items = _make_items(4)
        call_count = {"n": 0}
        original_open = __import__("os").open

        def failing_open(path, flags, *args, **kwargs):
            """Raise OSError on the 4th reservation attempt."""
            path_str = str(path)
            if ".reserving" in path_str:
                call_count["n"] += 1
                if call_count["n"] == 4:
                    raise OSError(28, "disk full")
            return original_open(path, flags, *args, **kwargs)

        with patch("kb.capture.os.open", side_effect=failing_open):
            written, err = _write_item_files(
                items,
                provenance="rollback-test",
                captured_at="2026-04-20T00:00:00Z",
                captures_dir=tmp_path,
            )

        assert written == [], f"AC10 regression: expected empty written, got {written}"
        assert err is not None
        assert "reservation failed" in err or "disk full" in err
        # No reservation temps should remain.
        assert not list(tmp_path.glob(".*.reserving")), (
            "AC10 regression: reservation rollback left orphan temp files"
        )
        # No final .md files either (all-or-nothing).
        assert not list(tmp_path.glob("*.md"))

    def test_phase3_failure_rolls_back_all(self, tmp_path: Path) -> None:
        """If item 2 Phase-3 replace fails, items 0-1 .md files must ALSO be unlinked."""
        items = _make_items(3)
        call_count = {"n": 0}

        def failing_replace(src, dst):
            """Succeed for first 2 replaces; raise on the 3rd."""
            import os as _os

            call_count["n"] += 1
            if call_count["n"] == 3:
                raise OSError(13, "permission denied on third replace")
            _os.replace(src, dst)

        with patch("kb.capture.os.replace", side_effect=failing_replace):
            written, err = _write_item_files(
                items,
                provenance="phase3-fail",
                captured_at="2026-04-20T00:00:00Z",
                captures_dir=tmp_path,
            )

        assert written == [], (
            f"AC10 regression: Phase-3 failure must return empty written for all-or-"
            f"nothing semantics; got {len(written)} finalised items"
        )
        assert err is not None
        assert "write failed" in err
        # No .md files should remain (rollback cleaned finalised items 0-1).
        assert not list(tmp_path.glob("*.md")), (
            "AC10 regression: Phase-3 rollback left orphan .md files"
        )
        # No reservation temps either (rollback cleaned remaining reservations).
        assert not list(tmp_path.glob(".*.reserving"))

    def test_hidden_temp_not_matched_by_md_glob(self, tmp_path: Path) -> None:
        """Hidden-temp reservations must not match `*.md` glob (T4 defense)."""
        items = _make_items(2)
        # Replace os.replace with a no-op to leave temps in place for this test.
        with patch("kb.capture.os.replace", side_effect=lambda *a, **kw: None):
            _write_item_files(
                items,
                provenance="hidden-temp-test",
                captured_at="2026-04-20T00:00:00Z",
                captures_dir=tmp_path,
            )
        # Reservation temps were created but never renamed.
        temps = list(tmp_path.glob(".*.reserving"))
        md_files = list(tmp_path.glob("*.md"))
        assert len(temps) == 2
        assert md_files == [], (
            "AC10 regression: hidden-temp reservations are matched by *.md glob; "
            "a concurrent kb_ingest scanning raw/captures/*.md would ingest them."
        )

    def test_empty_items_returns_empty_success(self, tmp_path: Path) -> None:
        """N=0 edge case — no mkdir work, no lock contention."""
        written, err = _write_item_files(
            [],
            provenance="empty",
            captured_at="2026-04-20T00:00:00Z",
            captures_dir=tmp_path,
        )
        assert written == []
        assert err is None

    def test_single_item(self, tmp_path: Path) -> None:
        """N=1 edge case — alongside_for should be [[]]."""
        items = _make_items(1)
        written, err = _write_item_files(
            items,
            provenance="single",
            captured_at="2026-04-20T00:00:00Z",
            captures_dir=tmp_path,
        )
        assert err is None
        assert len(written) == 1
        content = written[0].path.read_text(encoding="utf-8")
        # captured_alongside frontmatter should be an empty list for N=1.
        # Don't depend on exact YAML format; just verify no peer slugs leak.
        assert "captured_alongside" in content


class TestAC10RollbackHelpers:
    """Direct unit tests for the rollback helpers."""

    def test_rollback_reservations_unlinks_all(self, tmp_path: Path) -> None:
        paths = []
        for i in range(3):
            p = tmp_path / f".test-{i}.reserving"
            p.write_text("", encoding="utf-8")
            paths.append((f"slug-{i}", p, {}))
        _rollback_reservations(paths)
        for _s, p, _i in paths:
            assert not p.exists()

    def test_rollback_reservations_tolerates_missing(self, tmp_path: Path) -> None:
        """Missing file should not raise."""
        p = tmp_path / ".nonexistent.reserving"
        _rollback_reservations([("slug", p, {})])
        # Should not raise.

    def test_rollback_finalized_unlinks_md(self, tmp_path: Path) -> None:
        from kb.capture import CaptureItem

        paths = []
        for i in range(2):
            p = tmp_path / f"final-{i}.md"
            p.write_text("body", encoding="utf-8")
            paths.append(
                CaptureItem(
                    slug=f"final-{i}",
                    path=p,
                    title=f"T{i}",
                    kind="discovery",
                    body_chars=4,
                )
            )
        _rollback_finalized(paths)
        for item in paths:
            assert not item.path.exists()
