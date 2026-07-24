"""Cycle 83 (Design C) — `ingest_source` crash-atomicity via completion-only commit.

Phase 4.5 HIGH (R2): the manifest hash used to be reserved BEFORE any wiki page
was written, and a bare hash is indistinguishable from a completed ingest. A
crash mid-body left `.data/hashes.json` asserting the source was ingested while
the wiki held zero or partial pages, and `find_changed_sources` then skipped
that source permanently.

Design C closes it by writing the manifest hash exactly ONCE, as the last
durable step of a successful ingest (`_commit_ingest_manifest`, called from
`ingest_source` after `_run_ingest_body` returns). A crash anywhere before that
leaves no manifest entry, so the source is re-selected and retried. There are no
`in_progress:`/`failed:` marker values in the ingest path any more.

Same-process concurrent ingest of identical content is serialized by an
in-process per-content-hash lock (`_content_ingest_lock`), so exactly one thread
writes pages and the other sees a completed duplicate. Cross-process concurrent
ingest of identical-content-different-files is deliberately NOT serialized; it
degrades to the existing summary-collision merge (see the module docstring in
`pipeline.py`).

Coverage is at the SUITE level, not per-test. The load-bearing invariants —
no manifest entry after a first-ingest crash, no stale-but-equal entry after a
RE-INGEST crash, re-selection of a crashed source, a crash not suppressing a
different identical-content file, and commit-is-last ordering — each have a test
that fails a revert to the pre-cycle-83 reserve-before-body behaviour. The
remaining tests pin dedup, the in-process content lock, and the `file_lock(None)`
fix, and are not all individually revert-sensitive.

Manifest access goes through the default `HASH_MANIFEST` path patched by
`tmp_kb_env`; no test passes `manifest_path=` (the Phase-2 confirmation that
hardcoded HASH_MANIFEST is gone, but keeping the discipline avoids re-introducing
the vacuity trap).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from kb.compile import compiler as compiler_mod
from kb.errors import IngestError
from kb.ingest import pipeline as pipeline_mod
from kb.utils.hashing import hash_bytes

_SHARED_BODY = "# Shared\n\nIdentical content across two distinct source files.\n"

_ORIGINAL_RUN_INGEST_BODY = pipeline_mod._run_ingest_body


def _stub_extraction() -> dict:
    return {
        "title": "Cycle 83 Crash Atomicity Source",
        "summary": "Small test source used by cycle 83 crash-atomicity tests.",
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
        # Nothing here exercises hybrid search; skip the heavy vector rebuild so
        # this file adds no measurable load to timing-sensitive concurrency tests
        # elsewhere in the suite.
        _skip_vector_rebuild=True,
    )


def _manifest() -> dict:
    return compiler_mod.load_manifest()


def _raise_in_body(monkeypatch, message: str = "simulated ingest failure") -> None:
    monkeypatch.setattr(
        pipeline_mod,
        "_run_ingest_body",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError(message)),
    )


def _restore_body(monkeypatch) -> None:
    """Undo ONLY the `_run_ingest_body` stub.

    Deliberately not a blanket `monkeypatch` undo — `tmp_kb_env` receives the same
    `monkeypatch` instance, so undoing everything tears down the path sandbox and
    lets the rest of the test write into the real `wiki/` and `.data/`.
    """
    monkeypatch.setattr(pipeline_mod, "_run_ingest_body", _ORIGINAL_RUN_INGEST_BODY)


# --------------------------------------------------------------------------
# Core contract: the manifest hash appears ONLY after the body succeeds.
# --------------------------------------------------------------------------


def test_crash_mid_body_leaves_no_manifest_entry(tmp_kb_env, monkeypatch):
    """A crash inside `_run_ingest_body` must leave the source unrecorded.

    Revert detector. Pre-cycle-83 the bare hash was reserved BEFORE the body, so
    after a crash the manifest held `manifest[ref] == source_hash` and this
    assertion fails. Under Design C the commit is post-body, so a crash leaves no
    entry.
    """
    raw = _seed_raw(tmp_kb_env, "crash-mid-body")

    _raise_in_body(monkeypatch, "hard failure inside ingest body")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)

    manifest = _manifest()
    key = next((k for k in manifest if "crash-mid-body" in k), None)
    assert key is None, (
        f"Cycle-83 revert detected: a crashed ingest left a manifest entry "
        f"({key!r} -> {manifest.get(key)!r}). The hash must be written only on "
        f"success, or a crash makes find_changed_sources skip the source forever."
    )


def test_crashed_source_is_reselected_by_find_changed_sources(tmp_kb_env, monkeypatch):
    """After a crash, `find_changed_sources` must re-select the source.

    This is the end-to-end recovery guarantee, and it is what the pre-cycle-83
    bug broke: a reserved bare hash equalled the current hash, so the crashed
    source was classified up-to-date and skipped.
    """
    raw = _seed_raw(tmp_kb_env, "reselect-after-crash")

    _raise_in_body(monkeypatch, "crash before commit")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)
    _restore_body(monkeypatch)

    new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=tmp_kb_env / "raw")
    names = {Path(p).name for p in (*new_sources, *changed_sources)}
    assert "reselect-after-crash.md" in names, (
        f"A source that crashed mid-ingest must be re-selected for ingest; "
        f"got new+changed={names!r}"
    )


def test_reingest_crash_does_not_leave_stale_complete_entry(tmp_kb_env, monkeypatch):
    """A crashed RE-INGEST of an already-recorded source must not leave `H` behind.

    R2 Codex MAJOR: Design C's completion-only commit closed the first-ingest
    window, but re-ingesting a source whose manifest entry already equals the
    current hash (forced re-ingest, or a same-content update that still rewrites
    the page body + evidence trail) had a residual — a crash mid-body left the
    pre-existing bare hash, so `find_changed_sources` saw `H == current_hash`,
    skipped the source, and masked its half-rewritten pages.

    The fix clears the entry before the body, so after a crashed re-ingest the
    source is absent from the manifest and re-selected. This test fails if the
    pre-body clear is removed.
    """
    raw = _seed_raw(tmp_kb_env, "reingest-crash")
    # First ingest succeeds and records the bare hash.
    _ingest(tmp_kb_env, raw)
    committed_hash = hash_bytes(raw.read_bytes())
    manifest = _manifest()
    key = next((k for k in manifest if "reingest-crash" in k), None)
    assert key is not None and manifest[key] == committed_hash, "fixture sanity"

    # Re-ingest the SAME (unchanged) content, but crash mid-body.
    _raise_in_body(monkeypatch, "crash during re-ingest")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)
    _restore_body(monkeypatch)

    manifest = _manifest()
    key = next((k for k in manifest if "reingest-crash" in k), None)
    assert key is None, (
        f"a crashed re-ingest must not leave a stale-but-equal manifest entry "
        f"({key!r} -> {manifest.get(key)!r}); it would mask half-rewritten pages"
    )

    # And the crashed re-ingest source must be re-selected for retry.
    new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=tmp_kb_env / "raw")
    names = {Path(p).name for p in (*new_sources, *changed_sources)}
    assert "reingest-crash.md" in names, f"a crashed re-ingest must be re-selected; got {names!r}"


def test_duplicate_is_not_recorded_and_is_never_a_dedup_target(tmp_kb_env):
    """A duplicate owns no pages, so it must own no manifest entry and never be a
    dedup target — closing the R3 self-propagating false-target regression.

    R3 Codex MAJOR (against the R2 attempt): committing the duplicate's bare hash
    made its entry indistinguishable from the page-owning source's. Under a later
    re-selection of both, each would treat the OTHER as a valid duplicate target
    and neither would regenerate pages — self-propagating data loss. The fix is to
    DELETE the duplicate's entry instead, so the invariant "a bare hash means this
    source owns pages" holds. This test pins that the page-owning source can still
    be re-ingested and regenerates pages even though an identical-content
    duplicate exists — i.e. the duplicate is not accepted as A's dedup target.
    """
    raw_a = _seed_raw(tmp_kb_env, "dup-target", body=_SHARED_BODY)
    _ingest(tmp_kb_env, raw_a)

    raw_b = _seed_raw(tmp_kb_env, "dup-source", body=_SHARED_BODY)
    result_b = _ingest(tmp_kb_env, raw_b)
    assert result_b.get("duplicate") is True, "fixture sanity: B is a duplicate"

    # B (the duplicate) must NOT be recorded — it owns no pages.
    manifest = _manifest()
    assert not any("dup-source" in k for k in manifest), (
        f"a duplicate must not hold a manifest entry (it would become a false "
        f"dedup target); manifest={manifest!r}"
    )

    # Now re-ingest the page-OWNER A. With B unrecorded, A has no other bare-hash
    # entry to be a duplicate of, so A regenerates its pages instead of being
    # wrongly skipped as a duplicate of B. Under the R2 attempt (B recorded at H),
    # A would have seen B=H and returned duplicate here.
    result_a2 = _ingest(tmp_kb_env, raw_a)
    assert not result_a2.get("duplicate"), (
        "re-ingesting the page-owner must not be treated as a duplicate of an "
        "identical-content source that owns no pages (R3 false-target regression)"
    )


def test_successful_ingest_writes_the_bare_hash(tmp_kb_env):
    """A completed ingest records exactly the bare content hash — no marker."""
    raw = _seed_raw(tmp_kb_env, "commit-on-success")
    expected_hash = hash_bytes(raw.read_bytes())

    result = _ingest(tmp_kb_env, raw)
    assert not result.get("duplicate"), "fixture sanity: first ingest is not a duplicate"

    manifest = _manifest()
    key = next((k for k in manifest if "commit-on-success" in k), None)
    assert key is not None, "successful ingest must record the source in the manifest"
    assert manifest[key] == expected_hash, (
        f"completed ingest must store the bare content hash, not a marker; got {manifest[key]!r}"
    )


def test_no_marker_vocabulary_in_ingest_path(tmp_kb_env, monkeypatch):
    """Neither success nor failure writes an `in_progress:`/`failed:` value.

    Design C retired the marker state-machine entirely from the ingest path. A
    revert to the marker approach writes one of these prefixes and fails here.
    """
    ok_raw = _seed_raw(tmp_kb_env, "no-marker-ok")
    _ingest(tmp_kb_env, ok_raw)

    bad_raw = _seed_raw(tmp_kb_env, "no-marker-fail")
    _raise_in_body(monkeypatch, "fail after nothing committed")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, bad_raw)
    _restore_body(monkeypatch)

    for key, value in _manifest().items():
        assert not str(value).startswith(("in_progress:", "failed:")), (
            f"ingest path must not write marker values; found {key!r} -> {value!r}"
        )


def test_commit_is_the_last_durable_step(tmp_kb_env, monkeypatch):
    """The manifest entry is absent while the body runs and present only after.

    Snapshots the manifest from INSIDE the body (the body has not returned yet,
    so the commit has not run). Pre-cycle-83, the reservation had already written
    the hash by this point, so the snapshot would be non-empty.
    """
    raw = _seed_raw(tmp_kb_env, "commit-ordering")

    seen_during_body: dict = {}
    real_body = pipeline_mod._run_ingest_body

    def _snapshot_then_run(**kwargs):
        seen_during_body.update(compiler_mod.load_manifest())
        return real_body(**kwargs)

    monkeypatch.setattr(pipeline_mod, "_run_ingest_body", _snapshot_then_run)
    _ingest(tmp_kb_env, raw)

    assert not any("commit-ordering" in k for k in seen_during_body), (
        f"the manifest must NOT contain this source while its body is still "
        f"running; a pre-body reservation is the reverted bug. Saw: {seen_during_body!r}"
    )
    assert any("commit-ordering" in k for k in _manifest()), (
        "after a successful ingest the source must be committed to the manifest"
    )


# --------------------------------------------------------------------------
# Duplicate detection (bare-hash, cycle-17 semantics restored).
# --------------------------------------------------------------------------


def test_completed_ingest_deduplicates_identical_content(tmp_kb_env):
    """A completed ingest still dedups an identical-content source at another path."""
    raw_a = _seed_raw(tmp_kb_env, "dedup-original", body=_SHARED_BODY)
    _ingest(tmp_kb_env, raw_a)

    raw_b = _seed_raw(tmp_kb_env, "dedup-copy", body=_SHARED_BODY)
    result_b = _ingest(tmp_kb_env, raw_b)

    assert result_b.get("duplicate") is True, (
        "a completed ingest must dedup identical content ingested from another path"
    )


def test_crashed_source_does_not_suppress_a_different_file(tmp_kb_env, monkeypatch):
    """A crashed source must NOT make a different identical-content file a dup.

    This is the failure mode the marker approach reintroduced (Codex BLOCKER): a
    stale claim suppressing a genuinely different source, yielding zero pages for
    that content. Under Design C the crashed source left no manifest entry, so B
    is not a duplicate and gets ingested normally.
    """
    raw_a = _seed_raw(tmp_kb_env, "crashed-a", body=_SHARED_BODY)
    _raise_in_body(monkeypatch, "A crashes")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw_a)
    _restore_body(monkeypatch)

    raw_b = _seed_raw(tmp_kb_env, "healthy-b", body=_SHARED_BODY)
    result_b = _ingest(tmp_kb_env, raw_b)

    assert not result_b.get("duplicate"), (
        "a crashed source (no pages, no manifest entry) must not suppress a "
        "different file with identical content"
    )
    assert result_b.get("pages_created"), (
        f"source B must produce pages; got {result_b.get('pages_created')!r}"
    )


def test_reingest_of_crashed_source_succeeds(tmp_kb_env, monkeypatch):
    """Re-ingesting the crashed source itself works and records the bare hash."""
    raw = _seed_raw(tmp_kb_env, "retry-me")

    _raise_in_body(monkeypatch, "first attempt dies")
    with pytest.raises(IngestError):
        _ingest(tmp_kb_env, raw)
    _restore_body(monkeypatch)

    result = _ingest(tmp_kb_env, raw)
    assert not result.get("duplicate"), "re-ingest of a crashed source must not be skipped"
    manifest = _manifest()
    key = next((k for k in manifest if "retry-me" in k), None)
    assert key is not None and manifest[key] == hash_bytes(raw.read_bytes()), (
        f"successful retry must record the bare hash; got {manifest.get(key)!r}"
    )


# --------------------------------------------------------------------------
# In-process serialization of identical content (same-process concurrency).
# --------------------------------------------------------------------------


def test_content_lock_serializes_identical_content_same_process(tmp_kb_env):
    """Two threads ingesting different files with identical content: exactly one
    creates pages, the other sees a duplicate — deterministically.

    This is the same-process guarantee `_content_ingest_lock` provides. It does
    not depend on timing: the second thread cannot run its duplicate check until
    the first has committed.
    """
    raw_a = _seed_raw(tmp_kb_env, "concurrent-a", body=_SHARED_BODY)
    raw_b = _seed_raw(tmp_kb_env, "concurrent-b", body=_SHARED_BODY)

    results: dict[str, dict] = {}
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def _run(name: str, raw: Path) -> None:
        try:
            barrier.wait()
            results[name] = _ingest(tmp_kb_env, raw)
        except BaseException as exc:  # noqa: BLE001 — surfaced via assertion below
            errors.append(exc)

    t1 = threading.Thread(target=_run, args=("a", raw_a))
    t2 = threading.Thread(target=_run, args=("b", raw_b))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"unexpected exceptions: {errors!r}"
    dups = [r for r in results.values() if r.get("duplicate")]
    non_dups = [r for r in results.values() if not r.get("duplicate")]
    assert len(non_dups) == 1, f"exactly one thread must create pages; got {results!r}"
    assert len(dups) == 1, f"exactly one thread must see a duplicate; got {results!r}"


def test_content_lock_does_not_serialize_distinct_content(tmp_kb_env):
    """Distinct content uses distinct locks — no false serialization or dedup."""
    raw_a = _seed_raw(tmp_kb_env, "distinct-a", body="# A\n\nUnique content A.\n")
    raw_b = _seed_raw(tmp_kb_env, "distinct-b", body="# B\n\nUnique content B.\n")

    result_a = _ingest(tmp_kb_env, raw_a)
    result_b = _ingest(tmp_kb_env, raw_b)

    assert not result_a.get("duplicate")
    assert not result_b.get("duplicate"), "distinct content must never dedup against each other"


# --------------------------------------------------------------------------
# The `file_lock(None)` crash fix (independent of the marker redesign).
# --------------------------------------------------------------------------


def test_find_changed_sources_default_manifest_path_does_not_crash(tmp_kb_env):
    """`find_changed_sources(save_hashes=True)` works with the default path.

    `find_changed_sources` resolved the manifest default for `load_manifest` and
    `save_manifest` but passed the raw `manifest_path` to `file_lock`, so a `None`
    raised `AttributeError: 'NoneType' object has no attribute 'with_suffix'` and
    killed the scan. Reachable from `kb_compile_scan` (MCP) on any call omitting
    `wiki_dir`. `compile_wiki` was unaffected because it resolves the default
    earlier, which is why no existing test caught it.
    """
    _seed_raw(tmp_kb_env, "default-path-scan")

    new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=tmp_kb_env / "raw")

    names = {Path(p).name for p in (*new_sources, *changed_sources)}
    assert "default-path-scan.md" in names, (
        f"scan with the default manifest path must succeed and see the source; got {names!r}"
    )


def test_corrupt_non_string_manifest_value_does_not_kill_the_scan(tmp_kb_env):
    """Cycle 84 (threat T4) — a non-string manifest value must not abort the scan.

    `find_changed_sources` called `stored.startswith("failed:")` on whatever
    `json.loads` produced. A hand-edited or corrupted `.data/hashes.json` holding
    an int / list / null raised `AttributeError` and killed the ENTIRE compile
    scan, so one bad row took down every source. The bad row is now treated as
    changed, so the source is re-ingested and the entry self-heals.
    """
    raw_good = _seed_raw(tmp_kb_env, "healthy-source")
    raw_bad = _seed_raw(tmp_kb_env, "corrupt-entry-source")

    compiler_mod.save_manifest(
        {
            "raw/articles/corrupt-entry-source.md": 12345,  # non-string, the poison row
            "raw/articles/healthy-source.md": hash_bytes(raw_good.read_bytes()),
        }
    )

    # Must not raise AttributeError.
    new_sources, changed_sources = compiler_mod.find_changed_sources(raw_dir=tmp_kb_env / "raw")

    names = {Path(p).name for p in (*new_sources, *changed_sources)}
    assert raw_bad.name in names, (
        f"a source whose manifest value is corrupt must be re-selected so the row "
        f"self-heals; got {names!r}"
    )
