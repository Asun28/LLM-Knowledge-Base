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

    PR #39 R1 Sonnet MAJOR fix: capture the manifest state AT THE MOMENT
    `ingest_source` is called so we can assert the AC6 pre-marker was written
    BEFORE the exception fired. Pre-fix, this test was revert-tolerant: if
    AC6 was removed entirely, the `except` handler still wrote `failed:` and
    the final-state assertion passed. The snapshot-inside-stub assertion
    flips to failure under AC6 revert (manifest empty at call time).
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    src = _seed_raw_source(raw_dir)
    manifest_path = tmp_path / "hashes.json"
    _write_manifest(manifest_path, {})

    # Stub scan to return our seeded source.
    monkeypatch.setattr(compiler_mod, "scan_raw_sources", lambda _rd: [src])

    # Stub ingest_source that SNAPSHOTS the manifest at call time and then
    # raises. Under AC6, the manifest should already contain
    # `in_progress:{pre_hash}` when `ingest_source` is invoked.
    snapshot: dict = {}

    def _raise_and_snapshot(*args, **kwargs):
        snapshot.update(load_manifest(manifest_path))
        raise RuntimeError("simulated ingest failure")

    monkeypatch.setattr(compiler_mod, "ingest_source", _raise_and_snapshot)

    compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)

    # Pre-exception snapshot: AC6 pre-marker must be in place.
    source_key = next((k for k in snapshot if "articles/example.md" in k), None)
    assert source_key is not None, (
        f"AC6 revert detection: pre-marker manifest entry MISSING at "
        f"ingest_source call time. Snapshot: {snapshot}"
    )
    pre_value = str(snapshot[source_key])
    assert pre_value.startswith("in_progress:"), (
        f"AC6 revert detection: expected in_progress:{{pre_hash}} snapshot at "
        f"ingest_source call time; got {pre_value!r}. Revert of AC6 pre-marker "
        f"write would leave the manifest empty at call time."
    )

    # Final manifest: exception handler (existing cycle-17 code) must
    # overwrite the marker with `failed:{pre_hash}`.
    final_manifest = load_manifest(manifest_path)
    final_value = str(final_manifest[source_key])
    assert final_value.startswith("failed:"), (
        f"AC8: exception must overwrite in_progress with failed:{{hash}}; got {final_value!r}"
    )
    assert not final_value.startswith("in_progress:"), (
        "AC8: in_progress marker MUST NOT persist after a normal exception"
    )
    # Both hashes should be equal (same pre_hash used by both marker and failure).
    assert pre_value.split(":", 1)[1] == final_value.split(":", 1)[1], (
        "Pre-marker and failure marker must reference the same pre_hash"
    )


def test_incremental_prune_exempts_in_progress_markers(tmp_path):
    """CONDITION 13 (incremental path) — PR #39 R1 Codex BLOCKER: the full-mode
    prune exemption alone is insufficient because the default incremental
    `kb compile` path runs `find_changed_sources` which also prunes
    deleted-source entries. The exemption MUST apply there too or incremental
    compile silently deletes the markers AC7 says operators should see.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "articles").mkdir()
    manifest_path = tmp_path / "hashes.json"
    # Seed manifest with an in_progress marker whose raw file is MISSING.
    _write_manifest(
        manifest_path,
        {
            "articles/missing_src.md": "in_progress:xyz789",
            "articles/normal_missing.md": "hash_abc",  # should be pruned
        },
    )

    # No raw sources on disk → find_changed_sources will prune both unless
    # exempted. Run in incremental mode (default).
    compile_wiki(incremental=True, raw_dir=raw_dir, manifest_path=manifest_path)

    final = load_manifest(manifest_path)
    assert "articles/missing_src.md" in final, (
        "PR #39 R1 Codex BLOCKER: in_progress marker must NOT be pruned by "
        "find_changed_sources. Pre-fix would delete it silently on incremental compile."
    )
    assert str(final["articles/missing_src.md"]).startswith("in_progress:")
    # Sanity: normal missing-file entry IS pruned (existing behaviour unchanged).
    assert "articles/normal_missing.md" not in final


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
