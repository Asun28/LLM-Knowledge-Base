"""Cycle 87 — durability & containment completion.

Follow-ons to the cycle-86 Codex review, all in the same two fix families:

* **AC01** ``utils/io.py`` had no rename-durability barrier on Windows.
  ``_fsync_parent_dir`` returns immediately when ``os.name == "nt"``, and the
  docstring's claim that ``MoveFileEx`` covers the gap does not hold: CPython's
  ``os.replace`` passes only ``MOVEFILE_REPLACE_EXISTING``, never
  ``MOVEFILE_WRITE_THROUGH``, so it makes no power-loss promise. Windows is this
  project's primary development platform, so cycle-86 AC04 hardened only CI.
* **AC02** ``capture.py`` and ``query/embeddings.py`` call ``os.replace``
  directly, bypassing both atomic-write helpers, so they had no barrier at all.
* **AC03** ``lint/checks/evidence_resolvable.py`` decided containment against a
  resolved path and then ran a separate ``is_file()`` stat, so the two could
  refer to different inodes.

Platform branches are driven by *faked* platform tests rather than ``skipif``
(C86-L3): a ``skipif``-guarded branch holding a decision rule is untested on
whichever platform the developer is not using, which is precisely how the
Windows gap survived cycle 86.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import kb.capture as capture_mod
import kb.lint.checks.evidence_resolvable as evidence_mod
import kb.query.embeddings as embeddings_mod
import kb.utils.io as io_mod
from kb.lint.checks.evidence_resolvable import (
    _is_regular_file_no_follow,
    check_evidence_resolvable,
)

# ==========================================================================
# AC01 — rename-durability barrier, both platforms
# ==========================================================================


def test_write_through_flags_match_the_win32_constants():
    """Pins the two MoveFileExW flags. `MOVEFILE_COPY_ALLOWED` is deliberately
    absent: it would permit a cross-volume copy+delete, which is not an atomic
    replacement."""
    assert io_mod._MOVEFILE_REPLACE_EXISTING == 0x1
    assert io_mod._MOVEFILE_WRITE_THROUGH == 0x8


def test_durable_replace_on_posix_renames_then_fsyncs_the_parent_dir(tmp_path, monkeypatch):
    """POSIX keeps the cycle-86 AC04 behaviour: rename, then fsync the parent
    directory. Order matters — fsync-ing before the rename flushes the wrong
    state and buys no durability at all."""
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)

    order: list[str] = []
    real_replace = io_mod.os.replace

    def _spy_replace(src, dst):
        order.append("replace")
        return real_replace(src, dst)

    monkeypatch.setattr(io_mod.os, "replace", _spy_replace)
    seen: list[Path] = []

    def _spy_fsync(d):
        order.append("dir_fsync")
        seen.append(Path(d))

    monkeypatch.setattr(io_mod, "_fsync_parent_dir", _spy_fsync)

    tmp = tmp_path / "src.tmp"
    tmp.write_text("payload", encoding="utf-8")
    dest = tmp_path / "dest.md"

    io_mod.durable_replace(tmp, dest)

    assert order == ["replace", "dir_fsync"]
    assert seen == [dest.parent]
    assert dest.read_text(encoding="utf-8") == "payload"


def test_durable_replace_on_windows_uses_write_through_not_os_replace(tmp_path, monkeypatch):
    """The Windows branch must go through `MoveFileExW` with WRITE_THROUGH.

    Fails against the pre-cycle-87 code, which called `os.replace` (no
    write-through) and then a `_fsync_parent_dir` that returns immediately on
    `nt` — i.e. no barrier whatsoever.
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: True)

    calls: list[tuple] = []
    monkeypatch.setattr(
        io_mod,
        "_resolve_move_file_ex_w",
        lambda: lambda src, dst, flags: (calls.append((src, dst, flags)), 1)[1],
    )

    replace_spy = MagicMock()
    monkeypatch.setattr(io_mod.os, "replace", replace_spy)
    fsync_spy = MagicMock()
    monkeypatch.setattr(io_mod, "_fsync_parent_dir", fsync_spy)

    tmp = tmp_path / "src.tmp"
    dest = tmp_path / "dest.md"

    io_mod.durable_replace(tmp, dest)

    assert calls == [(os.fspath(tmp), os.fspath(dest), 0x1 | 0x8)]
    assert replace_spy.call_count == 0, "the nt branch must not use os.replace"
    assert fsync_spy.call_count == 0, "_fsync_parent_dir is a documented no-op on nt"


def test_durable_replace_on_windows_raises_and_never_falls_back(tmp_path, monkeypatch):
    """A failed write-through move must surface, not silently degrade.

    Falling back to `os.replace` would turn a durability failure into a
    successful-looking write with no barrier — the exact shape cycle-86's
    `_fsync_parent_dir` error-classification fix rejected for the POSIX path.
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: True)
    monkeypatch.setattr(io_mod, "_resolve_move_file_ex_w", lambda: lambda src, dst, flags: 0)

    def _boom():
        raise OSError(5, "Access is denied")

    monkeypatch.setattr(io_mod, "_raise_last_windows_error", _boom)

    replace_spy = MagicMock()
    monkeypatch.setattr(io_mod.os, "replace", replace_spy)

    with pytest.raises(OSError):
        io_mod.durable_replace(tmp_path / "src.tmp", tmp_path / "dest.md")

    assert replace_spy.call_count == 0, "a failed MoveFileExW must not fall back to os.replace"


def test_atomic_json_write_routes_through_durable_replace(tmp_path, monkeypatch):
    """The barrier must live on the shared promote path, not be re-implemented
    per call site — that is how this class kept reappearing."""
    spy = MagicMock(wraps=io_mod.durable_replace)
    monkeypatch.setattr(io_mod, "durable_replace", spy)

    target = tmp_path / "nested" / "manifest.json"
    io_mod.atomic_json_write({"k": "v"}, target)

    assert spy.call_count == 1
    assert Path(spy.call_args[0][1]) == target


def test_atomic_text_write_routes_through_durable_replace(tmp_path, monkeypatch):
    """Same-class peer, and the higher-traffic surface: every wiki page and
    evidence-trail append lands here."""
    spy = MagicMock(wraps=io_mod.durable_replace)
    monkeypatch.setattr(io_mod, "durable_replace", spy)

    target = tmp_path / "nested" / "page.md"
    io_mod.atomic_text_write("body\n", target)

    assert spy.call_count == 1
    assert Path(spy.call_args[0][1]) == target


def test_barrier_failure_after_a_completed_rename_raises_the_distinct_type(tmp_path, monkeypatch):
    """R1 MAJOR-1. `os.replace` was atomic in the sense callers relied on: it
    either renamed or raised, never both. The POSIX parent-dir fsync runs AFTER
    the rename and cycle-86 made it raise on genuine storage failure, so a bare
    re-raise tells the caller the promote did not happen while the destination
    sits there. The distinct type is what lets an all-or-nothing caller undo it.
    """
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)

    def _boom(_directory):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(io_mod, "_fsync_parent_dir", _boom)

    tmp = tmp_path / "src.tmp"
    tmp.write_text("payload", encoding="utf-8")
    dest = tmp_path / "dest.md"

    with pytest.raises(io_mod.RenameCompletedBarrierError) as excinfo:
        io_mod.durable_replace(tmp, dest)

    assert excinfo.value.errno == 5
    assert isinstance(excinfo.value, OSError), "legacy except OSError sites must still catch"
    assert dest.read_text(encoding="utf-8") == "payload", "the rename DID complete"
    assert not tmp.exists()


# ==========================================================================
# AC01 supplement — the real Win32 boundary (R1 MINOR-4)
# ==========================================================================


@pytest.mark.skipif(os.name != "nt", reason="exercises the real kernel32 binding")
def test_move_file_ex_w_abi_is_declared():
    """R1 MINOR-4: the faked-platform tests stub `_resolve_move_file_ex_w`, so a
    wrong argtypes/restype or a dropped `use_last_error` leaves them all green.
    This asserts the real declaration. `ctypes.wintypes` cannot even be imported
    on POSIX, so this cannot be a faked-platform test.
    """
    import ctypes
    import ctypes.wintypes

    fn = io_mod._resolve_move_file_ex_w()

    assert fn.argtypes == (
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.DWORD,
    )
    assert fn.restype is ctypes.wintypes.BOOL


@pytest.mark.skipif(os.name != "nt", reason="exercises the real kernel32 binding")
def test_real_write_through_promote_creates_overwrites_and_reports_failure(tmp_path):
    """R1 MINOR-4: end-to-end proof the native path works, which no faked test
    can give. CI is ubuntu-only, so without this the Windows branch would ship
    having never actually executed.
    """
    dest = tmp_path / "dest.md"

    first = tmp_path / "a.tmp"
    first.write_text("payload-A", encoding="utf-8")
    io_mod.durable_replace(first, dest)
    assert dest.read_text(encoding="utf-8") == "payload-A"
    assert not first.exists()

    # MOVEFILE_REPLACE_EXISTING must actually overwrite an existing destination.
    second = tmp_path / "b.tmp"
    second.write_text("payload-B", encoding="utf-8")
    io_mod.durable_replace(second, dest)
    assert dest.read_text(encoding="utf-8") == "payload-B"

    # A failed move must raise rather than silently report success. WinError maps
    # onto an OSError subclass, which is what every caller's except OSError relies on.
    with pytest.raises(OSError) as excinfo:
        io_mod.durable_replace(tmp_path / "absent.tmp", tmp_path / "other.md")
    assert excinfo.value.winerror == 2


# ==========================================================================
# AC02 — the two bare os.replace peers
# ==========================================================================


def _make_item(kind: str = "decision", body: str = "foo") -> dict:
    return {
        "title": f"Item {body}",
        "kind": kind,
        "body": body,
        "one_line_summary": "summary",
        "confidence": "stated",
    }


def test_capture_promotes_through_durable_replace(tmp_path, monkeypatch):
    """`capture.py` bypassed both atomic-write helpers, so a captured note had
    no rename barrier: power loss could leave a reported capture missing."""
    spy = MagicMock(wraps=capture_mod.durable_replace)
    monkeypatch.setattr(capture_mod, "durable_replace", spy)

    captures_dir = tmp_path / "captures"
    written, err = _write_capture(captures_dir)

    assert err is None
    assert len(written) == 1
    assert spy.call_count == 1
    assert Path(spy.call_args[0][1]) == written[0].path
    assert written[0].path.read_text(encoding="utf-8")


def test_capture_fsyncs_content_before_promoting(tmp_path, monkeypatch):
    """`write_text` alone leaves the body in the page cache, so the promote can
    win the race and expose an empty or partial capture after power loss."""
    order: list[str] = []
    real_fsync = os.fsync

    def _spy_fsync(fd):
        order.append("content_fsync")
        return real_fsync(fd)

    monkeypatch.setattr(capture_mod.os, "fsync", _spy_fsync)
    monkeypatch.setattr(
        capture_mod,
        "durable_replace",
        lambda src, dst: (order.append("promote"), os.replace(src, dst))[1],
    )

    _write_capture(tmp_path / "captures")

    assert order.index("content_fsync") < order.index("promote")


def _write_capture(captures_dir: Path):
    return capture_mod._write_item_files(
        [_make_item()],
        "prov",
        "2026-04-13T00:00:00Z",
        captures_dir=captures_dir,
    )


def test_capture_removes_the_final_when_the_barrier_fails_after_the_rename(tmp_path, monkeypatch):
    """R1 MAJOR-1. Capture promises all-or-nothing. When the rename completes and
    only the barrier fails, `written` never records the item and its temp is
    already gone, so neither rollback touches the final — an orphan `<slug>.md`
    would survive a capture reported as `([], error)`.

    Fails against a revert of the RenameCompletedBarrierError handling: the
    orphan remains and the captures dir is not empty.
    """
    captures_dir = tmp_path / "captures"

    def _rename_then_fail(src, dst):
        os.replace(src, dst)  # the promote genuinely completes
        raise io_mod.RenameCompletedBarrierError(5, "Input/output error")

    monkeypatch.setattr(capture_mod, "durable_replace", _rename_then_fail)

    written, err = _write_capture(captures_dir)

    assert written == []
    assert err is not None and "write failed" in err
    assert list(captures_dir.glob("*.md")) == [], "all-or-nothing leaked an orphan capture"


def test_proposal_consumption_promotes_through_durable_replace(tmp_path, monkeypatch):
    """R1 MAJOR-2. Scoped out originally as idempotent re-consumption, which
    understated it: a reverted rename makes the next run reparse the proposals
    and `persister.py` write ANOTHER raw article under a fresh run id.
    """
    import kb.lint.augment.orchestrator as orch_mod

    assert orch_mod.durable_rename is io_mod.durable_rename
    src = tmp_path / "_augment_proposals.md"
    src.write_text("proposals", encoding="utf-8")
    dest = tmp_path / "_augment_proposals.md.consumed-abcd1234"

    orch_mod.durable_rename(src, dest)

    assert dest.read_text(encoding="utf-8") == "proposals"
    assert not src.exists()


def test_log_rotation_promotes_through_durable_replace(tmp_path, monkeypatch):
    """R1 MINOR-3. Same-class rename peer: power loss could otherwise revert the
    archive-name transition after rotation was reported.
    """
    import kb.utils.wiki_log as wiki_log_mod

    spy = MagicMock(wraps=wiki_log_mod.durable_rename)
    monkeypatch.setattr(wiki_log_mod, "durable_rename", spy)

    log_path = tmp_path / "log.md"
    log_path.write_text("x" * 64, encoding="utf-8")

    wiki_log_mod.rotate_if_oversized(log_path, max_bytes=8, archive_stem_prefix="log")

    assert spy.call_count == 1
    assert not log_path.exists()
    assert len(list(tmp_path.glob("log.*.md"))) == 1


def test_vector_rebuild_promotes_through_durable_replace(tmp_path, monkeypatch):
    """`query/embeddings.py` swaps a freshly built sqlite DB into place with a
    bare `os.replace`; power loss there silently restores the previous index
    while the caller reports a successful rebuild."""
    import numpy as np

    wiki_dir = tmp_path / "wiki"
    page = wiki_dir / "entities" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text(
        "---\ntitle: Foo\nsource:\n  - raw/articles/source.md\n"
        "created: 2026-01-01\nupdated: 2026-01-01\ntype: entity\n"
        "confidence: stated\n---\n\n# Foo\n\nSome content.\n",
        encoding="utf-8",
    )
    (tmp_path / ".data").mkdir()

    class _StubModel:
        def encode(self, texts):
            return np.array([[1.0] for _ in texts], dtype=np.float32)

    monkeypatch.setattr(embeddings_mod, "_hybrid_available", True)
    monkeypatch.setattr(embeddings_mod, "_get_model", lambda: _StubModel())
    monkeypatch.setattr(embeddings_mod, "_model", None)
    embeddings_mod._index_cache.clear()

    spy = MagicMock(wraps=embeddings_mod.durable_replace)
    monkeypatch.setattr(embeddings_mod, "durable_replace", spy)

    assert embeddings_mod.rebuild_vector_index(wiki_dir, force=True) is True
    assert spy.call_count == 1
    assert Path(spy.call_args[0][1]) == embeddings_mod._vec_db_path(wiki_dir)


# ==========================================================================
# AC03 — evidence_resolvable containment TOCTOU
# ==========================================================================


def _write_page(wiki_dir: Path, ref: str) -> Path:
    """Write a wiki page whose only source ref is `ref`."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    page = wiki_dir / "page.md"
    page.write_text(
        f'---\ntitle: "P"\nsource:\n  - "{ref}"\n---\n\nBody.\n',
        encoding="utf-8",
    )
    return page


def test_no_follow_helper_accepts_a_regular_file(tmp_path):
    """Baseline contract: a plain regular file is reported as one."""
    target = tmp_path / "real.md"
    target.write_text("x", encoding="utf-8")

    assert _is_regular_file_no_follow(target) is True


def test_no_follow_helper_rejects_a_directory_and_a_missing_path(tmp_path):
    """Only regular files count — a directory is not evidence, nor is nothing."""
    a_dir = tmp_path / "subdir"
    a_dir.mkdir()

    assert _is_regular_file_no_follow(a_dir) is False
    assert _is_regular_file_no_follow(tmp_path / "absent.md") is False


def test_existence_verdict_is_driven_by_the_no_follow_helper(tmp_path, monkeypatch):
    """The production loop must decide existence via the no-follow helper.

    Platform-independent counterpart to the symlink test below (which can only
    run where unprivileged symlink creation works). The raw file genuinely
    exists, so `Path.is_file()` returns True and emits no issue; forcing the
    no-follow helper to False must flip the verdict. Against a revert to
    `.is_file()` the helper's return value is ignored, no issue is emitted, and
    this fails.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "evidence.md").write_text("real evidence", encoding="utf-8")
    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")

    monkeypatch.setattr(evidence_mod, "_is_regular_file_no_follow", lambda p: False)

    issues = check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page])

    assert [i["check"] for i in issues] == ["evidence_unresolvable"]
    assert issues[0]["severity"] == "warning"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink test")
def test_stat_does_not_follow_a_symlink_swapped_in_after_the_containment_check(
    tmp_path, monkeypatch
):
    """The existence stat must not follow a link out of `raw/` (threat T1).

    Models the TOCTOU window directly. `_resolve_evidence_ref` is stubbed to
    return the contained path because that is what it does in the real race: it
    calls `.resolve()` and decides containment BEFORE the swap lands, so it
    returns a path it correctly judged to be inside `raw/`. Only afterwards does
    that path become a symlink pointing outside. Letting the real resolver run
    against an already-planted symlink would test the wrong thing entirely —
    `.resolve()` follows the link, containment then rejects it, and the stat
    under test is never reached.

    Pre-fix, `resolved.is_file()` followed the link and reported True — a stat
    of a path outside `raw/` whose result reached lint output, which is exactly
    the filesystem-existence oracle the cycle-86 T1 boundary exists to prevent.
    So pre-fix this emits NO issue at all; post-fix the link is refused and the
    ref is reported unresolvable.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.md"
    secret.write_text("host secret", encoding="utf-8")

    swapped = raw_dir / "evidence.md"
    swapped.symlink_to(secret)
    assert swapped.is_file(), "precondition: the pre-fix stat would have followed this link"

    monkeypatch.setattr(evidence_mod, "_resolve_evidence_ref", lambda ref, raw: swapped)

    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")

    issues = check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page])

    assert [i["check"] for i in issues] == ["evidence_unresolvable"]
    assert "does not resolve to a file" in issues[0]["message"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink test")
def test_a_symlink_resolving_inside_raw_is_still_accepted(tmp_path):
    """R1 raised that the no-follow stat might reject legitimate symlinks in
    `raw/`. It does not, and this pins that rather than arguing it.

    `_resolve_evidence_ref` returns the RESOLVED path, so an ordinary symlink is
    already followed and containment-checked before the stat ever runs. A link
    pointing INSIDE `raw/` therefore arrives at the stat as its regular-file
    target and passes. (A link pointing OUTSIDE `raw/` was already an `error`
    before this cycle, via the containment check — not the silent pass the
    review assumed.) Only a link appearing at the resolved path itself, i.e. one
    swapped in after resolution, is refused.
    """
    raw_dir = tmp_path / "raw"
    (raw_dir / "shared").mkdir(parents=True)
    real = raw_dir / "shared" / "real.md"
    real.write_text("shared evidence", encoding="utf-8")

    link = raw_dir / "evidence.md"
    link.symlink_to(real)

    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")

    assert check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page]) == []


def test_a_real_contained_file_still_passes(tmp_path):
    """Guard against over-rejection: the happy path must stay silent."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "evidence.md").write_text("real evidence", encoding="utf-8")
    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")

    assert check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page]) == []


def test_durable_rename_refuses_to_clobber_an_existing_destination(tmp_path):
    """R2 MINOR-4/MINOR-5. The R1 fixes gained a barrier by routing two callers
    onto `durable_replace`, which silently also swapped their semantics from
    no-clobber to overwrite. Both depend on the refusal: wiki_log picks its
    archive name with an ordinal loop precisely so it does not destroy an
    existing archive, and the consumed-proposal name is unique only to 8 run-id
    characters. Adding durability must not change who wins a collision.
    """
    src = tmp_path / "src.md"
    src.write_text("new", encoding="utf-8")
    dest = tmp_path / "dest.md"
    dest.write_text("PRECIOUS EXISTING ARCHIVE", encoding="utf-8")

    with pytest.raises(OSError):
        io_mod.durable_rename(src, dest)

    assert dest.read_text(encoding="utf-8") == "PRECIOUS EXISTING ARCHIVE"
    assert src.exists(), "a refused rename must leave the source in place"

    # durable_replace is the overwrite variant and must stay that way, since
    # tmp->final promotes rely on it.
    io_mod.durable_replace(src, dest)
    assert dest.read_text(encoding="utf-8") == "new"


def test_durable_rename_succeeds_onto_a_free_destination(tmp_path):
    """The no-clobber guard must not break the ordinary path."""
    src = tmp_path / "log.md"
    src.write_text("body", encoding="utf-8")
    dest = tmp_path / "log.2026-07.md"

    io_mod.durable_rename(src, dest)

    assert dest.read_text(encoding="utf-8") == "body"
    assert not src.exists()


def test_log_rotation_does_not_destroy_an_existing_archive(tmp_path):
    """R2 MINOR-5 end-to-end: the ordinal loop picks the next free name, and the
    promote must not overwrite the archive it just stepped around."""
    import kb.utils.wiki_log as wiki_log_mod

    log_path = tmp_path / "log.md"
    log_path.write_text("x" * 64, encoding="utf-8")
    existing = list(tmp_path.glob("log.*.md"))
    assert existing == []

    wiki_log_mod.rotate_if_oversized(log_path, max_bytes=8, archive_stem_prefix="log")
    first = list(tmp_path.glob("log.*.md"))
    assert len(first) == 1
    first[0].write_text("FIRST ARCHIVE", encoding="utf-8")

    log_path.write_text("y" * 64, encoding="utf-8")
    wiki_log_mod.rotate_if_oversized(log_path, max_bytes=8, archive_stem_prefix="log")

    assert first[0].read_text(encoding="utf-8") == "FIRST ARCHIVE", "clobbered the prior archive"
    assert len(list(tmp_path.glob("log.*.md"))) == 2
