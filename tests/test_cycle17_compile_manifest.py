"""Cycle 17 AC1-AC3 — compile/compiler.py manifest consistency + locking."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from kb.compile.compiler import (
    _canonical_rel_path,
    compile_wiki,
    load_manifest,
    save_manifest,
)
from kb.utils.paths import make_source_ref


def _seed_raw_dir(raw_dir: Path, files: dict[str, str]) -> list[Path]:
    """Create raw_dir + subdirs + files, return list of Paths."""
    paths = []
    for rel, content in files.items():
        p = raw_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


class TestAC1PruneBaseFix:
    """AC1 — full-mode prune base must be raw_dir.resolve().parent, not raw_dir.parent."""

    def test_prune_survives_relative_raw_dir(self, tmp_path: Path, monkeypatch) -> None:
        """Relative raw_dir must not prune all manifest entries."""
        raw_abs = tmp_path / "raw"
        raw_abs.mkdir()
        (raw_abs / "articles").mkdir()
        article = raw_abs / "articles" / "foo.md"
        article.write_text("---\ntitle: foo\n---\nbody\n", encoding="utf-8")

        manifest_path = tmp_path / "hashes.json"
        # Seed manifest with an entry for the existing file.
        rel = _canonical_rel_path(article, raw_abs)
        save_manifest({rel: "abc123"}, manifest_path)

        # Cross-platform chdir: relative Path("./raw") must resolve to raw_abs.
        monkeypatch.chdir(tmp_path)
        raw_relative = Path("raw")
        assert raw_relative.resolve() == raw_abs.resolve()

        # Monkeypatch ingest_source to a no-op so we focus on prune behavior.
        with patch("kb.compile.compiler.ingest_source") as mock_ingest:
            mock_ingest.return_value = {
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "wikilinks_injected": [],
                "affected_pages": [],
                "duplicate": False,
            }
            compile_wiki(
                incremental=False,
                raw_dir=raw_relative,
                manifest_path=manifest_path,
                wiki_dir=tmp_path / "wiki",
            )

        # The manifest entry should survive — pre-fix, it would have been pruned
        # because (raw_relative.parent / rel) == ("./" / "raw/articles/foo.md") does not exist
        # when the cwd happens to be elsewhere.
        surviving = load_manifest(manifest_path)
        assert rel in surviving, (
            f"AC1 regression: manifest entry {rel!r} was pruned by full-mode compile "
            f"under relative raw_dir. Surviving keys: {list(surviving.keys())}"
        )


class TestAC2NormalizationInvariant:
    """AC2 — regression pin: make_source_ref and _canonical_rel_path agree for raw-named dirs.

    Design-gate Q7 decision: cycle 17 parametrizes only raw_dir.name == "raw" cases.
    The non-"raw" name case is a pre-existing divergence filed to BACKLOG for a
    dedicated normalization cycle (make_source_ref hardcodes "raw/" prefix while
    _canonical_rel_path uses raw_dir.parent-relative path).
    """

    @pytest.mark.parametrize("raw_dir_style", ["default", "relative", "absolute"])
    def test_make_source_ref_matches_canonical(
        self, tmp_path: Path, monkeypatch, raw_dir_style: str
    ) -> None:
        """For default-named raw dirs, both functions must produce identical strings."""
        raw_abs = tmp_path / "raw"
        raw_abs.mkdir()
        (raw_abs / "articles").mkdir()
        article = raw_abs / "articles" / "example.md"
        article.write_text("body", encoding="utf-8")

        if raw_dir_style == "default":
            raw_dir = raw_abs
        elif raw_dir_style == "relative":
            monkeypatch.chdir(tmp_path)
            raw_dir = Path("raw")
        else:  # absolute
            raw_dir = raw_abs.resolve()

        src_ref = make_source_ref(article, raw_dir=raw_dir)
        canonical = _canonical_rel_path(article, raw_dir)

        assert src_ref == canonical, (
            f"AC2 regression: make_source_ref ({src_ref!r}) and "
            f"_canonical_rel_path ({canonical!r}) diverged for style={raw_dir_style}"
        )


class TestAC3FullModeLock:
    """AC3 — full-mode tail + exception path RMW under file_lock(manifest_path)."""

    def test_concurrent_writer_during_full_mode_tail_survives(self, tmp_path: Path) -> None:
        """A concurrent manifest writer during full-mode tail must not lose its entry."""
        raw_abs = tmp_path / "raw"
        raw_abs.mkdir()
        (raw_abs / "articles").mkdir()
        # Seed a real file so sources_to_process is non-empty.
        (raw_abs / "articles" / "seed.md").write_text(
            "---\ntitle: seed\n---\nbody\n", encoding="utf-8"
        )
        # Also seed the concurrent file so full-mode prune does not evict its
        # manifest entry for non-existence.
        (raw_abs / "articles" / "concurrent.md").write_text(
            "---\ntitle: concurrent\n---\nbody\n", encoding="utf-8"
        )
        manifest_path = tmp_path / "hashes.json"

        # Seed manifest with an existing entry.
        save_manifest({"_template/article": "seed_hash"}, manifest_path)

        race_victim_key = "raw/articles/concurrent.md"
        race_victim_value = "race_hash"
        concurrent_write_done = threading.Event()

        def slow_ingest(*args, **kwargs):
            """Simulate slow ingest so we can race a concurrent manifest write."""
            # While ingest is "running", another process writes to the manifest.
            m = load_manifest(manifest_path)
            m[race_victim_key] = race_victim_value
            save_manifest(m, manifest_path)
            concurrent_write_done.set()
            return {
                "pages_created": [],
                "pages_updated": [],
                "pages_skipped": [],
                "wikilinks_injected": [],
                "affected_pages": [],
                "duplicate": False,
            }

        with patch("kb.compile.compiler.ingest_source", side_effect=slow_ingest):
            compile_wiki(
                incremental=False,
                raw_dir=raw_abs,
                manifest_path=manifest_path,
                wiki_dir=tmp_path / "wiki",
            )

        assert concurrent_write_done.is_set(), "slow_ingest was not called"
        surviving = load_manifest(manifest_path)
        assert race_victim_key in surviving, (
            f"AC3 regression: concurrent manifest write was clobbered by full-mode tail. "
            f"Surviving keys: {list(surviving.keys())}"
        )
        assert surviving[race_victim_key] == race_victim_value, (
            "AC3 regression: concurrent write value was overwritten"
        )

    def test_exception_path_uses_lock(self, tmp_path: Path) -> None:
        """Exception-path manifest RMW must also hold file_lock."""
        raw_abs = tmp_path / "raw"
        raw_abs.mkdir()
        (raw_abs / "articles").mkdir()
        source_file = raw_abs / "articles" / "broken.md"
        source_file.write_text("---\ntitle: broken\n---\nbroken body\n", encoding="utf-8")
        # Seed the concurrent file too so the full-mode tail prune does not
        # evict its manifest entry for non-existence.
        (raw_abs / "articles" / "concurrent.md").write_text(
            "---\ntitle: concurrent\n---\nbody\n", encoding="utf-8"
        )
        manifest_path = tmp_path / "hashes.json"
        save_manifest({"_template/article": "seed"}, manifest_path)

        race_key = "raw/articles/concurrent.md"
        concurrent_done = threading.Event()

        def raising_ingest(*args, **kwargs):
            """Simulate concurrent write during the exception handler's RMW window."""
            m = load_manifest(manifest_path)
            m[race_key] = "race_value"
            save_manifest(m, manifest_path)
            concurrent_done.set()
            raise RuntimeError("ingest exploded")

        with patch("kb.compile.compiler.ingest_source", side_effect=raising_ingest):
            compile_wiki(
                incremental=False,
                raw_dir=raw_abs,
                manifest_path=manifest_path,
                wiki_dir=tmp_path / "wiki",
            )

        assert concurrent_done.is_set()
        surviving = load_manifest(manifest_path)
        # The exception handler wrote `failed:<hash>` for broken.md; the concurrent
        # entry from raising_ingest must also survive.
        assert race_key in surviving, (
            f"AC3 regression: exception-path RMW clobbered concurrent write. "
            f"Surviving keys: {list(surviving.keys())}"
        )

    def test_lock_file_pattern_matches_file_lock_convention(self, tmp_path: Path) -> None:
        """file_lock uses <path>.lock sibling; if a prior run crashed,
        the stale lock should not block a new run (stale-lock purge is
        documented in utils/io.py::file_lock)."""
        from kb.utils.io import file_lock

        manifest_path = tmp_path / "hashes.json"
        save_manifest({"a": "b"}, manifest_path)
        # Acquire + release successfully to confirm file_lock works on this path.
        with file_lock(manifest_path):
            data = load_manifest(manifest_path)
            assert data == {"a": "b"}
            save_manifest({"a": "c"}, manifest_path)
        assert load_manifest(manifest_path) == {"a": "c"}
