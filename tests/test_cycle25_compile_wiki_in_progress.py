"""Cycle 25 AC6/AC7/AC8 — `compile_wiki` in_progress marker lifecycle.

Regression tests for:
- AC6: pre-marker write before each ingest_source call.
- AC7: stale-marker entry scan logs a warning per stale source.
- CONDITION 13: full-mode prune EXEMPTS `in_progress:` markers so AC7's
  "operator decides" contract holds.
- AC8 contract: normal exceptions overwrite marker with `failed:{pre_hash}`;
  marker only survives hard-kill (simulated by direct manifest seed).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from kb.compile import compiler as compiler_mod
from kb.compile.compiler import compile_wiki, load_manifest


def _seed_raw_source(raw_dir: Path, rel: str = "articles/example.md") -> Path:
    """Create a minimal raw source file and return its path."""
    src = raw_dir / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# Example\n\nContent.\n", encoding="utf-8")
    return src


def _write_manifest(manifest_path: Path, data: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data), encoding="utf-8")


def test_stale_marker_warning_on_entry(tmp_path, monkeypatch, caplog):
    """AC7 — compile_wiki logs a warning for each stale in_progress marker.

    Simulates hard-kill by pre-seeding the manifest with an in_progress entry.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    manifest_path = tmp_path / "hashes.json"
    # Seed manifest with a stale in_progress marker.
    _write_manifest(
        manifest_path,
        {
            "raw/articles/stale1.md": "in_progress:abc123",
            "raw/articles/stale2.md": "in_progress:def456",
        },
    )

    # Stub out ingest_source so we don't actually extract anything.
    monkeypatch.setattr(
        compiler_mod,
        "scan_raw_sources",
        lambda _rd: [],  # empty — just test the entry scan
    )

    with caplog.at_level(logging.WARNING, logger="kb.compile.compiler"):
        compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    warning_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    stale_warnings = [m for m in warning_msgs if "stale in_progress" in m]
    assert stale_warnings, f"Expected stale-marker warning; got {warning_msgs!r}"
    msg = stale_warnings[0]
    assert "2 stale in_progress marker" in msg
    assert "raw/articles/stale1.md" in msg, "Each stale source must be named"
    assert "raw/articles/stale2.md" in msg, "Each stale source must be named"


def test_no_warning_when_no_stale_markers(tmp_path, monkeypatch, caplog):
    """AC7 — clean manifest triggers NO stale-marker warning."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    manifest_path = tmp_path / "hashes.json"
    _write_manifest(manifest_path, {"raw/articles/ok.md": "hash123"})

    monkeypatch.setattr(compiler_mod, "scan_raw_sources", lambda _rd: [])

    with caplog.at_level(logging.WARNING, logger="kb.compile.compiler"):
        compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    warning_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    stale_warnings = [m for m in warning_msgs if "stale in_progress" in m]
    assert not stale_warnings, f"Clean manifest must not emit stale warning; got {stale_warnings!r}"


def test_exception_during_ingest_overwrites_marker_with_failed(tmp_path, monkeypatch):
    """AC8 — normal Python exception in `ingest_source` overwrites the
    in_progress marker with `failed:{pre_hash}`; the marker MUST NOT persist.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src = _seed_raw_source(raw_dir)
    manifest_path = tmp_path / "hashes.json"
    _write_manifest(manifest_path, {})

    # Stub scan to return our seeded source; stub ingest_source to raise.
    monkeypatch.setattr(compiler_mod, "scan_raw_sources", lambda _rd: [src])

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated ingest failure")

    monkeypatch.setattr(compiler_mod, "ingest_source", _raise)

    compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    # After compile_wiki, load the FINAL manifest and inspect the entry.
    final_manifest = load_manifest(manifest_path)
    # Source key format: _canonical_rel_path (e.g., "raw/articles/example.md")
    source_key = next((k for k in final_manifest if "articles/example.md" in k), None)
    assert source_key is not None, f"Source key not found in manifest: {final_manifest}"
    final_value = str(final_manifest[source_key])
    assert final_value.startswith("failed:"), (
        f"AC8: exception must overwrite in_progress with failed:{{hash}}; got {final_value!r}"
    )
    assert not final_value.startswith("in_progress:"), (
        "AC8: in_progress marker MUST NOT persist after a normal exception"
    )


def test_full_mode_prune_exempts_in_progress_markers(tmp_path, monkeypatch, caplog):
    """CONDITION 13 — full-mode prune at compile_wiki tail MUST NOT delete
    `in_progress:` markers even when the raw file is absent.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    manifest_path = tmp_path / "hashes.json"
    # Seed manifest with an in_progress marker whose raw file is MISSING.
    _write_manifest(
        manifest_path,
        {
            "articles/missing_src.md": "in_progress:xyz789",
            "articles/normal_missing.md": "hash_abc",  # this one SHOULD be pruned
        },
    )

    monkeypatch.setattr(compiler_mod, "scan_raw_sources", lambda _rd: [])

    with caplog.at_level(logging.WARNING, logger="kb.compile.compiler"):
        compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    final = load_manifest(manifest_path)
    # CONDITION 13: in_progress marker survives the prune.
    assert "articles/missing_src.md" in final, (
        "CONDITION 13: in_progress marker for missing source must NOT be pruned"
    )
    assert str(final["articles/missing_src.md"]).startswith("in_progress:")
    # Sanity: normal missing-file entry IS pruned (existing behaviour unchanged).
    assert "articles/normal_missing.md" not in final, (
        "Existing prune behaviour for non-in_progress entries still fires"
    )
