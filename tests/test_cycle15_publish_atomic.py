"""Cycle 15 AC9/AC10/AC11/AC27 — publish builders use atomic_text_write.

Threat T4 — graph.jsonld temp file must be colocated with out_path so
os.replace stays atomic across Windows/OneDrive volume boundaries.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import kb.compile.publish as publish


def _seed_page(wiki_dir: Path, pid: str) -> None:
    path = wiki_dir / "concepts" / f"{pid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
title: {pid}
source:
  - raw/articles/{pid}.md
created: 2026-04-20
updated: 2026-04-20
type: concept
confidence: stated
---
Body of {pid}.
""",
        encoding="utf-8",
    )


class TestBuildersUseAtomicTextWrite:
    """AC27 — all three builders route through atomic_text_write."""

    def test_build_llms_txt_uses_atomic_write(self, tmp_path, monkeypatch):
        _seed_page(tmp_path, "alpha")
        calls: list[tuple[str, Path]] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append((content, path))
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        out = tmp_path / "out" / "llms.txt"
        publish.build_llms_txt(tmp_path, out)
        assert len(calls) == 1
        assert calls[0][1] == out
        assert out.exists()

    def test_build_llms_full_txt_uses_atomic_write(self, tmp_path, monkeypatch):
        _seed_page(tmp_path, "beta")
        calls: list[Path] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append(path)
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        out = tmp_path / "out" / "llms-full.txt"
        publish.build_llms_full_txt(tmp_path, out)
        assert len(calls) == 1
        assert out.exists()

    def test_build_graph_jsonld_uses_atomic_write(self, tmp_path, monkeypatch):
        """AC11 — JSON-LD must go through atomic_text_write (not json.dump direct)."""
        _seed_page(tmp_path, "gamma")
        calls: list[Path] = []
        real = publish.atomic_text_write

        def _spy(content: str, path: Path) -> None:
            calls.append(path)
            real(content, path)

        monkeypatch.setattr(publish, "atomic_text_write", _spy)
        out = tmp_path / "out" / "graph.jsonld"
        publish.build_graph_jsonld(tmp_path, out)
        assert len(calls) == 1
        # Content must still be valid JSON.
        import json

        parsed = json.loads(out.read_text(encoding="utf-8"))
        assert "@context" in parsed
        assert "@graph" in parsed


class TestJsonldNoTmpResidueT4:
    """AC11/T4 — on atomic_text_write failure, no orphan .tmp sibling remains."""

    def test_no_tmp_residue_on_write_failure(self, tmp_path, monkeypatch):
        """AC27 T4 — simulate failure mid-write; parent dir stays clean."""
        _seed_page(tmp_path, "delta")
        out = tmp_path / "out" / "graph.jsonld"
        out.parent.mkdir(parents=True, exist_ok=True)

        def _boom(content: str, path: Path) -> None:
            raise OSError("simulated disk full")

        monkeypatch.setattr(publish, "atomic_text_write", _boom)
        with pytest.raises(OSError, match="simulated disk full"):
            publish.build_graph_jsonld(tmp_path, out)
        # No residue — the helper is expected to clean up internally; we
        # only assert the parent dir has no orphan `.tmp` / `.jsonld.tmp`
        # siblings.
        residue = [p.name for p in out.parent.iterdir() if p.name != out.name]
        tmp_residue = [n for n in residue if ".tmp" in n]
        assert tmp_residue == [], (
            f"atomic_text_write must clean up on failure; got residue {tmp_residue}"
        )
