"""Cycle 15 AC12/AC28 — _publish_skip_if_unchanged + incremental builder kwarg.

Covers:
  - incremental=True short-circuits when wiki unchanged.
  - incremental=False regenerates even when nothing changed.
  - mtime-freshening any wiki page re-triggers write.
  - Index-file (log.md etc.) mutations do NOT re-trigger (scan_wiki_pages excludes).
  - T10c: retracted-page freshening regenerates AND filters the page.
  - Docstring single-writer note (threat T3).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import kb.compile.publish as publish


def _seed_page(wiki_dir: Path, pid: str, belief_state: str | None = None) -> Path:
    path = wiki_dir / "concepts" / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    bs_line = f"belief_state: {belief_state}\n" if belief_state else ""
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-04-20
updated: 2026-04-20
type: concept
confidence: stated
{bs_line}---
Body of {pid}.
""",
        encoding="utf-8",
    )
    return path


class TestIncrementalSkip:
    """AC28 — incremental=True short-circuits; incremental=False regenerates."""

    def test_incremental_true_skips_when_unchanged(self, tmp_path, monkeypatch):
        _seed_page(tmp_path, "one")
        out = tmp_path / "out" / "llms.txt"
        publish.build_llms_txt(tmp_path, out)
        first_content = out.read_text(encoding="utf-8")
        first_mtime_ns = out.stat().st_mtime_ns

        # Ensure the output mtime is strictly greater than any wiki page
        # mtime so the skip path fires (fixture files may share mtime with
        # the fresh write on fast filesystems).
        os.utime(
            out,
            ns=(first_mtime_ns + 1_000_000_000, first_mtime_ns + 1_000_000_000),
        )

        calls: list[Path] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append(path)
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        result = publish.build_llms_txt(tmp_path, out, incremental=True)
        assert result == out
        assert calls == [], "incremental=True must skip atomic_text_write when unchanged"
        # Content unchanged.
        assert out.read_text(encoding="utf-8") == first_content

    def test_incremental_false_regenerates(self, tmp_path, monkeypatch):
        _seed_page(tmp_path, "two")
        out = tmp_path / "out" / "llms.txt"
        publish.build_llms_txt(tmp_path, out)
        first_mtime_ns = out.stat().st_mtime_ns
        os.utime(
            out,
            ns=(first_mtime_ns + 1_000_000_000, first_mtime_ns + 1_000_000_000),
        )

        calls: list[Path] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append(path)
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        # Default incremental=False should regenerate.
        publish.build_llms_txt(tmp_path, out)
        assert len(calls) == 1

    def test_mtime_freshen_retriggers(self, tmp_path, monkeypatch):
        page_path = _seed_page(tmp_path, "three")
        out = tmp_path / "out" / "llms.txt"
        publish.build_llms_txt(tmp_path, out)

        # R1 MINOR 3 — freshen by +5s to ensure mtime strictly exceeds the
        # output mtime regardless of write-time clock granularity (NTFS 100ns,
        # FAT32 2s, SMB coarser). A smaller offset risks flaky failures on
        # low-resolution filesystems.
        now_ns = time.time_ns() + 5_000_000_000
        os.utime(page_path, ns=(now_ns, now_ns))

        calls: list[Path] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append(path)
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        publish.build_llms_txt(tmp_path, out, incremental=True)
        assert len(calls) == 1, "mtime-freshening a wiki page must re-trigger publish"


class TestIndexFileMutationsIgnored:
    """AC28 — mutations to root-level index files do NOT re-trigger publish."""

    def test_log_md_mutation_does_not_retrigger(self, tmp_path, monkeypatch):
        _seed_page(tmp_path, "four")
        out = tmp_path / "out" / "llms.txt"
        publish.build_llms_txt(tmp_path, out)
        first_mtime_ns = out.stat().st_mtime_ns
        # Make sure output is strictly newer than wiki pages.
        os.utime(
            out,
            ns=(first_mtime_ns + 2_000_000_000, first_mtime_ns + 2_000_000_000),
        )

        # Touch log.md at an even later mtime.
        log = tmp_path / "log.md"
        log.write_text("fake log\n", encoding="utf-8")
        later_ns = first_mtime_ns + 5_000_000_000
        os.utime(log, ns=(later_ns, later_ns))

        calls: list[Path] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append(path)
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        publish.build_llms_txt(tmp_path, out, incremental=True)
        assert calls == [], "log.md is not in scan_wiki_pages; mutation must not re-trigger publish"


class TestT10cEpistemicFilterOrdering:
    """AC28/T10c — retracted page freshening regens AND filters output."""

    def test_retracted_freshening_retriggers_and_filters(self, tmp_path, monkeypatch):
        page_path = _seed_page(tmp_path, "retracted-page")
        out = tmp_path / "out" / "llms.txt"
        publish.build_llms_txt(tmp_path, out)
        # First write — page is visible in output.
        assert "retracted-page" in out.read_text(encoding="utf-8")

        # Rewrite page with belief_state: retracted AND freshen mtime.
        page_path.write_text(
            """---
title: retracted-page
source:
  - raw/articles/retracted-page.md
created: 2026-04-20
updated: 2026-04-20
type: concept
confidence: stated
belief_state: retracted
---
Body.
""",
            encoding="utf-8",
        )
        now_ns = time.time_ns() + 5_000_000_000
        os.utime(page_path, ns=(now_ns, now_ns))

        # With incremental=True, mtime-advanced page must still regen AND
        # the retracted filter must hide it from output.
        publish.build_llms_txt(tmp_path, out, incremental=True)
        content = out.read_text(encoding="utf-8")
        assert "retracted-page" not in content, "retracted page must be filtered from output (T2)"
        assert "[!excluded]" in content, "excluded-count footer must surface"


class TestDocstringSingleWriter:
    """AC12 T3 — helper docstring documents single-writer assumption."""

    def test_skip_helper_docstring_mentions_single_writer(self):
        doc = publish._publish_skip_if_unchanged.__doc__ or ""
        assert "single-writer" in doc.lower() or "single writer" in doc.lower(), (
            "AC12/T3 — _publish_skip_if_unchanged docstring must note single-writer assumption"
        )
