"""Cycle 83 — `ingest_source` crash-atomicity via `in_progress:` manifest markers.

Phase 4.5 HIGH (R2): `_check_and_reserve_manifest` wrote the bare content hash
BEFORE any wiki page existed. A crash anywhere between that reservation and the
end of `_run_ingest_body` left `.data/hashes.json` asserting the source was
ingested while the wiki held zero or partial pages — and `find_changed_sources`
then skipped that source permanently on every later compile.

Fix: reserve as `in_progress:{hash}` (the same producer string `compile_wiki`
has used since cycle 25), promote to the bare hash at the Phase-2 confirmation,
and downgrade to `failed:{hash}` on the handled-exception path.

Test strategy: behavioural assertions against the on-disk manifest via the
default `HASH_MANIFEST` path patched by `tmp_kb_env`. No `manifest_path=`
overrides anywhere in this file — the Phase-2 confirmation hardcodes
`HASH_MANIFEST`, so a `manifest_path=` test would observe only `compile_wiki`'s
cycle-25 marker and pass under revert (design doc CONDITION 7).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from kb.compile import compiler as compiler_mod
from kb.errors import IngestError
from kb.ingest import pipeline as pipeline_mod
from kb.utils.hashing import hash_bytes

_SHARED_BODY = "# Shared\n\nIdentical content across two distinct source files.\n"


def _stub_extraction() -> dict:
    return {
        "title": "Cycle 83 Crash Atomicity Source",
        "summary": "Small test source used by cycle 83 manifest-marker tests.",
        "entities_mentioned": [],
        "concepts_mentioned": [],
        "key_points": ["Trigger the ingest path."],
    }


def _seed_raw(tmp_kb_env: Path, slug: str, body: str | None = None) -> Path:
    raw = tmp_kb_env / "raw" / "articles" / f"{slug}.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(body if body is not None else f"# {slug}\n\nBody.\n", encoding="utf-8")
    return raw


def _ingest(tmp_kb_env: Path, raw: Path) -> dict:
    return pipeline_mod.ingest_source(
        raw,
        source_type="article",
        extraction=_stub_extraction(),
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
        # Nothing here exercises hybrid search, and the tail `rebuild_vector_index`
        # is heavy sqlite I/O. Left enabled, twelve full rebuilds added enough load
        # to the suite to intermittently tip the pre-existing timing-sensitive
        # contradiction-concurrency tests past their `file_lock` timeout — the
        # production change was innocent (the suite is green with this file
        # excluded), the cost was purely this fixture's.
        _skip_vector_rebuild=True,
    )


def _manifest() -> dict:
    """Read the manifest through the compiler module so the tmp_kb_env patch applies."""
    return compiler_mod.load_manifest()


def _entry_for(manifest: dict, slug: str) -> tuple[str, str]:
    key = next((k for k in manifest if slug in k), None)
    assert key is not None, f"No manifest entry for {slug!r}; manifest={manifest!r}"
    return key, str(manifest[key])


def _raise_in_body(monkeypatch, message: str = "simulated ingest failure") -> None:
    monkeypatch.setattr(
        pipeline_mod,
        "_run_ingest_body",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError(message)),
    )


def _restore_body(monkeypatch) -> None:
    """Undo ONLY the `_run_ingest_body` stub.

    Deliberately not a blanket `monkeypatch` undo — `tmp_kb_env` receives the same
    `monkeypatch` instance, so a blanket undo also tears down the path sandbox
    and lets the rest of the test write into the real `wiki/` and `.data/`.
    """
    monkeypatch.setattr(pipeline_mod, "_run_ingest_body", _ORIGINAL_RUN_INGEST_BODY)


_ORIGINAL_RUN_INGEST_BODY = pipeline_mod._run_ingest_body


# --------------------------------------------------------------------------
# The core contract: a crash mid-body leaves a marker, not a bare hash.
# --------------------------------------------------------------------------


def test_crash_mid_ingest_leaves_in_progress_marker_not_bare_hash(tmp_kb_env, monkeypatch):
    """At `_run_ingest_body` call time the manifest holds `in_progress:{hash}`.

    This is the revert detector. Pre-cycle-83, `_check_and_reserve_manifest`
    wrote the BARE hash at that moment, so the snapshot value would be 32 hex
    chars and the `startswith("in_progress:")` assertion fails.

    Snapshotting INSIDE the stub rather than asserting on final state is what
    makes this non-vacuous: the failure path also writes a `failed:` value, so a
    final-state-only assertion would pass even with the reservation reverted.
    """
    raw = _seed_raw(tmp_kb_env, "crash-mid-body")
    expected_hash = hash_bytes(raw.read_bytes())

    snapshot: dict = {}

    def _snapshot_then_raise(**kwargs):
        snapshot.update(compiler_mod.load_manifest())
        raise RuntimeError("simulated hard failure inside ingest body")

    monkeypatch.setattr(pipeline_mod, "_run_ingest_body", _snapshot_then_raise)

    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)

    _key, value = _entry_for(snapshot, "crash-mid-body")
    assert value.startswith("in_progress:"), (
        f"Cycle-83 revert detected: expected an in_progress marker in the manifest "
        f"at _run_ingest_body call time, got {value!r}. A bare hash here means a "
        f"crash would make find_changed_sources skip this source permanently."
    )
    assert value == f"in_progress:{expected_hash}", (
        f"Marker payload must be the reserved content hash; got {value!r}"
    )


def test_marker_payload_is_a_bare_hash(tmp_kb_env, monkeypatch):
    """Ingest's marker string matches `compile_wiki`'s producer shape.

    Design D2: do not invent a second prefix. `compile_wiki` writes
    `in_progress:{pre_hash}` and `content_hash`/`hash_bytes` are the same
    function, so both producers emit the same string for the same file.
    """
    raw = _seed_raw(tmp_kb_env, "prefix-parity")
    snapshot: dict = {}

    def _snapshot_then_raise(**kwargs):
        snapshot.update(compiler_mod.load_manifest())
        raise RuntimeError("stop after reservation")

    monkeypatch.setattr(pipeline_mod, "_run_ingest_body", _snapshot_then_raise)
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)

    _key, value = _entry_for(snapshot, "prefix-parity")
    prefix, _, payload = value.partition(":")
    assert prefix == "in_progress"
    assert len(payload) == 32 and all(c in "0123456789abcdef" for c in payload), (
        f"Marker payload must be a bare 32-hex content hash so the manifest value "
        f"namespace stays a tagged union of disjoint strings; got {payload!r}"
    )


# --------------------------------------------------------------------------
# Terminal states: failure downgrades, success promotes.
# --------------------------------------------------------------------------


def test_handled_exception_downgrades_marker_to_failed(tmp_kb_env, monkeypatch):
    """After a handled exception the value is `failed:`, never `in_progress:`.

    Design D3 (load-bearing): without the downgrade, every ordinary ingest error
    leaves an in_progress marker and the cycle-25 stale-marker warning becomes
    noise operators learn to ignore. `in_progress:` must mean "suspected hard
    kill", `failed:` must mean "handled exception".
    """
    raw = _seed_raw(tmp_kb_env, "downgrade-to-failed")
    expected_hash = hash_bytes(raw.read_bytes())

    _raise_in_body(monkeypatch, "handled ingest failure")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)

    _key, value = _entry_for(_manifest(), "downgrade-to-failed")
    assert value == f"failed:{expected_hash}", (
        f"Handled exception must downgrade the marker to failed:{{hash}}; got {value!r}"
    )
    assert not value.startswith("in_progress:"), (
        "in_progress must not survive a handled exception — it is reserved for hard kills"
    )


def test_downgrade_does_not_mask_the_original_exception(tmp_kb_env, monkeypatch):
    """A failing downgrade must never replace the caller's exception.

    Design D3: the downgrade is wrapped in its own try/except. If `save_manifest`
    itself blows up during rollback, the caller still sees the real ingest error.
    """
    raw = _seed_raw(tmp_kb_env, "rollback-blows-up")

    def _explode(*args, **kwargs):
        raise OSError("manifest save failed during rollback")

    _raise_in_body(monkeypatch, "the original failure the caller must see")
    monkeypatch.setattr(compiler_mod, "save_manifest", _explode)

    with pytest.raises(IngestError, match="the original failure the caller must see"):
        _ingest(tmp_kb_env, raw)


def test_successful_ingest_promotes_marker_to_bare_hash(tmp_kb_env):
    """A completed ingest leaves the bare hash, with no marker residue.

    Phase-2 confirmation must overwrite the reservation. If it did not, every
    successful ingest would leave a permanent in_progress entry and re-ingest
    forever (threat T14: absence of a marker means "assume complete").
    """
    raw = _seed_raw(tmp_kb_env, "promote-on-success")
    expected_hash = hash_bytes(raw.read_bytes())

    result = _ingest(tmp_kb_env, raw)
    assert not result.get("duplicate"), "fixture sanity: first ingest is not a duplicate"

    _key, value = _entry_for(_manifest(), "promote-on-success")
    assert value == expected_hash, (
        f"Successful ingest must promote the marker to the bare hash; got {value!r}"
    )


# --------------------------------------------------------------------------
# `_claims_content` — the three-way manifest vocabulary. Both halves of the
# split are load-bearing and each is pinned here.
# --------------------------------------------------------------------------


def test_failed_marker_does_not_suppress_a_different_source(tmp_kb_env, monkeypatch):
    """`failed:` MUST NOT claim content — the load-bearing negative contract.

    A failed attempt wrote no pages. If it were treated as a duplicate, a
    genuinely different source with identical content would be skipped and that
    content would exist in NO page at all — the same silent data-loss class this
    cycle closes.

    Fails against an implementation that strips every prefix indiscriminately.
    """
    raw_a = _seed_raw(tmp_kb_env, "failed-source-a", body=_SHARED_BODY)

    _raise_in_body(monkeypatch, "A fails")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw_a)
    _restore_body(monkeypatch)

    _key_a, value_a = _entry_for(_manifest(), "failed-source-a")
    assert value_a.startswith("failed:"), f"fixture sanity: expected failed:, got {value_a!r}"

    raw_b = _seed_raw(tmp_kb_env, "recovering-source-b", body=_SHARED_BODY)
    result_b = _ingest(tmp_kb_env, raw_b)

    assert not result_b.get("duplicate"), (
        "A `failed:` entry must NOT make a different file with identical content "
        "look like a duplicate — the failed attempt wrote no pages, so suppressing "
        "B would leave the content unrepresented entirely."
    )
    assert result_b.get("pages_created"), (
        f"Source B must produce pages; got pages_created={result_b.get('pages_created')!r}"
    )


def test_live_in_progress_marker_still_claims_content(tmp_kb_env):
    """`in_progress:` MUST claim content — preserves the Phase 4.5 Q_A guarantee.

    Cycle 83 changed the reservation from a bare hash to a marker. If markers did
    not claim, two threads ingesting distinct files with identical content would
    both pass the duplicate check and both write pages, reopening the RMW race
    that `tests/test_ingest.py::test_duplicate_content_concurrent_ingest` pins.

    Asserted at the helper level because the race itself is exercised by that
    existing threaded test; this pins the predicate the fix depends on.
    """
    content_hash = "a" * 32
    assert pipeline_mod._claims_content(f"in_progress:{content_hash}", content_hash) is True
    assert pipeline_mod._claims_content(content_hash, content_hash) is True
    assert pipeline_mod._claims_content(f"failed:{content_hash}", content_hash) is False
    # A marker for DIFFERENT content must not claim.
    assert pipeline_mod._claims_content(f"in_progress:{'b' * 32}", content_hash) is False
    # Threat T4 — a corrupt non-string manifest value must never claim, and must
    # not raise (pre-fix, `stored.startswith` on an int killed the whole scan).
    assert pipeline_mod._claims_content(12345, content_hash) is False
    assert pipeline_mod._claims_content(None, content_hash) is False


def test_stale_marker_does_not_block_reingest_of_same_key(tmp_kb_env, monkeypatch):
    """The recovery path: re-ingesting the crashed source itself works.

    The `ref != source_ref` guard protects this, and it is the case that matters
    most for recovery, so it gets an explicit pin.
    """
    raw = _seed_raw(tmp_kb_env, "retry-after-crash")

    _raise_in_body(monkeypatch, "first attempt dies")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)
    _restore_body(monkeypatch)

    result = _ingest(tmp_kb_env, raw)
    assert not result.get("duplicate"), "Re-ingest of a crashed source must not be skipped"
    _key, value = _entry_for(_manifest(), "retry-after-crash")
    assert value == hash_bytes(raw.read_bytes()), (
        f"Successful retry must leave the bare hash; got {value!r}"
    )


def test_completed_ingest_still_deduplicates_identical_content(tmp_kb_env):
    """The dedup guarantee is preserved for COMPLETED ingests."""
    raw_a = _seed_raw(tmp_kb_env, "dedup-original", body=_SHARED_BODY)
    _ingest(tmp_kb_env, raw_a)

    raw_b = _seed_raw(tmp_kb_env, "dedup-copy", body=_SHARED_BODY)
    result_b = _ingest(tmp_kb_env, raw_b)

    assert result_b.get("duplicate") is True, (
        "A completed ingest must still deduplicate identical content from another path"
    )


# --------------------------------------------------------------------------
# The marker drives recovery through the existing compile machinery.
# --------------------------------------------------------------------------


def test_marker_valued_entry_is_reselected_as_changed(tmp_kb_env):
    """`find_changed_sources` re-selects a marker-valued source.

    This is why the marker approach needs no new recovery pass: the change diff
    already treats any value != current hash as changed, so a crashed source
    becomes eligible for re-ingest automatically. It is also what makes the
    stale-`in_progress:` residual self-healing.
    """
    raw = _seed_raw(tmp_kb_env, "reselect-me")
    real_hash = hash_bytes(raw.read_bytes())

    compiler_mod.save_manifest({"raw/articles/reselect-me.md": f"in_progress:{real_hash}"})

    _new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=tmp_kb_env / "raw")
    changed_names = {Path(c).name for c in changed_sources}
    assert "reselect-me.md" in changed_names, (
        f"A source whose manifest value is an in_progress marker must be re-selected "
        f"for ingest; changed={changed_names!r}"
    )


def test_find_changed_sources_default_manifest_path_does_not_crash(tmp_kb_env):
    """`find_changed_sources(save_hashes=True)` works with the default path.

    Separate live bug found while writing the reselect test above.
    `find_changed_sources` resolved the manifest default for `load_manifest` and
    `save_manifest` but passed the raw `manifest_path` straight to `file_lock`,
    so a `None` raised `AttributeError: 'NoneType' object has no attribute
    'with_suffix'` and killed the scan.

    Reachable in production from the `kb_compile_scan` MCP tool, which sets
    `manifest_path = ... if wiki_path else None` — i.e. any call that omits the
    optional `wiki_dir` argument. `compile_wiki` was unaffected because it
    resolves the default earlier, which is why no existing test caught this.
    """
    _seed_raw(tmp_kb_env, "default-path-scan")

    # save_hashes defaults to True — this is the branch that took the lock.
    new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=tmp_kb_env / "raw")

    names = {Path(p).name for p in (*new_sources, *changed_sources)}
    assert "default-path-scan.md" in names, (
        f"Scan with the default manifest path must succeed and see the source; got {names!r}"
    )


def test_reservation_failure_is_logged_at_warning(tmp_kb_env, monkeypatch, caplog):
    """Threat T2: a swallowed reservation failure must be visible.

    Pre-cycle-83 this was `logger.debug`, so a manifest that silently stopped
    recording reservations produced no operator signal at default log level.
    """
    raw = _seed_raw(tmp_kb_env, "reservation-blows-up")

    def _explode(*args, **kwargs):
        raise OSError("simulated manifest write failure")

    monkeypatch.setattr(compiler_mod, "save_manifest", _explode)

    with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
        pipeline_mod._check_and_reserve_manifest(
            hash_bytes(raw.read_bytes()), "raw/articles/reservation-blows-up.md"
        )

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, (
        "A failed manifest reservation must surface at WARNING; it was previously "
        "swallowed at DEBUG and therefore invisible in normal operation."
    )
