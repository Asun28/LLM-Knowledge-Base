"""Cycle 89 — make the durability barrier able to report what it did.

Cycle 88's review produced the same finding twice, from two model families
approaching from opposite ends: R1 DeepSeek said the Windows rollback claims a
durability it does not have, R2 Codex said the POSIX tolerated-errno path does
the same. Both proposed having callers REPORT a missing barrier, and neither
noticed that `_fsync_parent_dir` returned `None` in every case — so the
information needed to report it did not exist. Both remedies were rejected in
cycle 88 for consistency, and the shared root cause filed instead.

* **AC01** `_fsync_parent_dir` returns a `BarrierResult` tri-state. A genuine
  storage failure still RAISES (the cycle-86 contract is unchanged).
* **AC02** `capture._finish_rollback` consumes it, and the tri-state earns its
  third value here: `UNSUPPORTED` is worth telling the operator, while
  `SKIPPED_PLATFORM` is constant on Windows and would be pure noise. A bool
  could not express that difference.

The note is deliberately a SEPARATE token from `rollback_incomplete`. They make
different claims — "the state is unknown, go look" versus "the state is known
but not yet durable" — and merging them would undo the cycle-88 decision.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

import kb.capture as capture_mod
import kb.utils.io as io_mod
from kb.utils.io import BarrierResult, _fsync_parent_dir

# ==========================================================================
# AC01 — the tri-state itself
# ==========================================================================


def _force_posix_branch(monkeypatch) -> None:
    """Drive the fsync-capable branch regardless of the host platform.

    C86-L3: a `skipif`-guarded platform branch is untested on whichever platform
    the developer is not using, which is how the Windows durability gap survived
    cycle 86. `_dir_fsync_supported` exists as a seam precisely so these tests
    run everywhere. Monkeypatching `os.name` instead would break every
    `Path(...)` in the call stack (pathlib picks its flavour from it).
    """
    monkeypatch.setattr(io_mod, "_dir_fsync_supported", lambda: True)


def test_a_real_flush_reports_flushed(tmp_path, monkeypatch):
    """The ordinary case on a local filesystem.

    `os.open` on a directory is a PermissionError on Windows, so the descriptor
    is faked to keep the branch reachable from either platform. What is under
    test is the VERDICT, not the syscall.
    """
    _force_posix_branch(monkeypatch)
    monkeypatch.setattr(io_mod.os, "open", lambda *a, **kw: 4242)
    monkeypatch.setattr(io_mod.os, "fsync", lambda fd: None)
    monkeypatch.setattr(io_mod.os, "close", lambda fd: None)

    assert _fsync_parent_dir(tmp_path) is BarrierResult.FLUSHED


def test_the_platform_no_op_reports_skipped_rather_than_success(tmp_path, monkeypatch):
    """The no-op must be distinguishable from a flush.

    This is the exact confusion that let cycle 88 ship a docstring claiming
    Windows rollback deletions were durable: the helper returned the same thing
    either way, so nothing could tell them apart.
    """
    monkeypatch.setattr(io_mod, "_dir_fsync_supported", lambda: False)

    assert _fsync_parent_dir(tmp_path) is BarrierResult.SKIPPED_PLATFORM


@pytest.mark.parametrize("code", sorted(io_mod._FSYNC_UNSUPPORTED_ERRNOS))
def test_a_tolerated_errno_reports_unsupported(tmp_path, monkeypatch, code):
    """Every errno the helper tolerates must report as UNSUPPORTED, not success.

    Parametrised over the real frozenset rather than a hand-picked sample, so
    adding an errno to `_FSYNC_UNSUPPORTED_ERRNOS` cannot quietly introduce one
    that reports FLUSHED.
    """
    _force_posix_branch(monkeypatch)
    monkeypatch.setattr(io_mod.os, "open", lambda *a, **kw: 4242)
    monkeypatch.setattr(io_mod.os, "close", lambda fd: None)

    def _refuse(fd):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(io_mod.os, "fsync", _refuse)

    assert _fsync_parent_dir(tmp_path) is BarrierResult.UNSUPPORTED


def test_an_unopenable_directory_reports_unsupported(tmp_path, monkeypatch):
    """No handle means no flush, so it is not success either.

    R2 Codex reached this branch specifically: it patched `os.open` to fail and
    showed `_finish_rollback` returned an empty string, i.e. reported nothing
    wrong at all.
    """
    _force_posix_branch(monkeypatch)

    def _refuse(path, flags, *a, **kw):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(io_mod.os, "open", _refuse)

    assert _fsync_parent_dir(tmp_path) is BarrierResult.UNSUPPORTED


@pytest.mark.parametrize("code", [errno.EIO, errno.ENOSPC])
def test_a_failing_open_raises_instead_of_claiming_unsupported(tmp_path, monkeypatch, code):
    """R1 DeepSeek HIGH. The open branch swallowed every errno alike since cycle
    86, which was defensible while it returned `None` — that claimed nothing.

    Naming the value UNSUPPORTED is what made the swallow wrong: it asserts WHY
    there was no flush, so an `EIO` from failing storage would reach the caller
    as a benign platform limitation. This cycle introduced that mislabelling, so
    this cycle fixes it — the open branch now classifies errnos with the same set
    the fsync branch uses.
    """
    _force_posix_branch(monkeypatch)

    def _fail(path, flags, *a, **kw):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(io_mod.os, "open", _fail)

    with pytest.raises(OSError):
        _fsync_parent_dir(tmp_path)


@pytest.mark.parametrize("code", [errno.EIO, errno.ENOSPC])
def test_a_genuine_storage_failure_still_raises(tmp_path, monkeypatch, code):
    """The cycle-86 contract is unchanged: a real fault is an exception, NOT a
    fourth enum value. Returning it would let `durable_replace` report a
    committed write whose rename a power loss can still revert."""
    _force_posix_branch(monkeypatch)
    monkeypatch.setattr(io_mod.os, "open", lambda *a, **kw: 4242)
    monkeypatch.setattr(io_mod.os, "close", lambda fd: None)

    def _fail(fd):
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(io_mod.os, "fsync", _fail)

    with pytest.raises(OSError):
        _fsync_parent_dir(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="needs a real directory fd")
def test_the_unfaked_posix_path_really_flushes(tmp_path):
    """One un-mocked end-to-end run, so the faked tests above cannot all agree
    on a wrong syscall shape. Skipped on Windows because there is no real
    directory descriptor to take there — that platform's verdict is
    SKIPPED_PLATFORM, pinned separately."""
    assert _fsync_parent_dir(tmp_path) is BarrierResult.FLUSHED


def test_the_promote_helpers_are_behaviourally_unchanged(tmp_path, monkeypatch):
    """AC01 is additive. `durable_replace` ignores the new return value, and a
    tolerated barrier must still be a successful promote — not a raise."""
    monkeypatch.setattr(io_mod, "_fsync_parent_dir", lambda d: BarrierResult.UNSUPPORTED)
    monkeypatch.setattr(io_mod, "_use_windows_write_through", lambda: False)

    src = tmp_path / "tmp.txt"
    src.write_text("payload", encoding="utf-8")
    dest = tmp_path / "final.txt"

    io_mod.durable_replace(src, dest)

    assert dest.read_text(encoding="utf-8") == "payload"
    assert not src.exists()


# ==========================================================================
# AC02 — capture reports UNSUPPORTED but stays quiet about SKIPPED_PLATFORM
# ==========================================================================


def _make_item(title: str) -> dict:
    return {
        "title": title,
        "kind": "decision",
        "body": "body content",
        "one_line_summary": "summary",
        "confidence": "stated",
    }


def _write_two_failing_on_the_last(captures_dir: Path, monkeypatch):
    """Promote items 0 and 1, then fail item 2 so a rollback runs."""
    calls = {"n": 0}

    def _promote(src, dst):
        if calls["n"] == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        calls["n"] += 1
        return os.replace(src, dst)

    monkeypatch.setattr(capture_mod, "durable_replace", _promote)
    return capture_mod._write_item_files(
        [_make_item("alpha"), _make_item("beta"), _make_item("gamma")],
        "prov",
        "2026-04-13T00:00:00Z",
        captures_dir=captures_dir,
    )


def test_an_unsupported_barrier_is_reported_to_the_caller(tmp_path, monkeypatch):
    """The gap R2 Codex found: on a filesystem that refuses directory fsync the
    deletions are not durable, and pre-cycle-89 the caller was told nothing."""
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.UNSUPPORTED)

    written, err = _write_two_failing_on_the_last(tmp_path / "captures", monkeypatch)

    assert written == []
    assert capture_mod.BARRIER_UNSUPPORTED_MARKER in err
    assert "not on stable storage" in err


def test_an_unsupported_barrier_does_not_claim_the_state_is_unknown(tmp_path, monkeypatch):
    """The load-bearing distinction. The rollback COMPLETED — every unlink
    succeeded — so the batch state is known-empty and `rollback_incomplete` must
    NOT fire. Merging the two tokens would undo the cycle-88 decision that
    rejected reporting a merely-unavailable barrier as indeterminate."""
    captures_dir = tmp_path / "captures"
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.UNSUPPORTED)

    _written, err = _write_two_failing_on_the_last(captures_dir, monkeypatch)

    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER not in err
    assert list(captures_dir.glob("*.md")) == [], "precondition: the rollback really completed"


def test_the_windows_no_op_is_deliberately_not_reported(tmp_path, monkeypatch):
    """SKIPPED_PLATFORM is constant on Windows, so a note would ride along on
    every capture failure and train the reader to ignore it. This is why the
    helper returns a tri-state rather than a bool: UNSUPPORTED and
    SKIPPED_PLATFORM both mean "no flush" yet warrant opposite handling."""
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.SKIPPED_PLATFORM)

    _written, err = _write_two_failing_on_the_last(tmp_path / "captures", monkeypatch)

    assert capture_mod.BARRIER_UNSUPPORTED_MARKER not in err
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER not in err


def test_a_flushed_barrier_adds_no_note(tmp_path, monkeypatch):
    """The happy path stays silent."""
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.FLUSHED)

    _written, err = _write_two_failing_on_the_last(tmp_path / "captures", monkeypatch)

    assert capture_mod.BARRIER_UNSUPPORTED_MARKER not in err
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER not in err


def test_both_markers_can_appear_together(tmp_path, monkeypatch):
    """They are orthogonal claims: a rollback can both fail to finish AND run on
    a filesystem that refuses the barrier. Reporting only one would drop half
    the caller's picture."""
    captures_dir = tmp_path / "captures"
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.UNSUPPORTED)
    real_unlink = Path.unlink

    def _unlink(self, *args, **kwargs):
        if self.name == "decision-alpha.md":
            raise OSError(errno.EACCES, "Permission denied")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)

    _written, err = _write_two_failing_on_the_last(captures_dir, monkeypatch)

    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in err
    assert capture_mod.BARRIER_UNSUPPORTED_MARKER in err
    assert "decision-alpha.md" in err


def test_no_barrier_is_taken_when_the_rollback_deleted_nothing(tmp_path, monkeypatch):
    """The cycle-88 `targets` gate, re-pinned against the new note: a batch that
    never wrote must not acquire a durability caveat it cannot have."""
    calls: list[Path] = []
    monkeypatch.setattr(
        capture_mod,
        "_fsync_parent_dir",
        lambda d: (calls.append(d), BarrierResult.UNSUPPORTED)[1],
    )

    detail = capture_mod._finish_rollback(tmp_path, [], targets=[])

    assert detail == ""
    assert calls == []


def test_no_barrier_note_when_every_deletion_failed(tmp_path, monkeypatch):
    """R1 Codex P2. If every unlink failed, nothing was deleted — so there is no
    deletion for a durability caveat to be about.

    Pre-fix the same error said both "every file remains" and "the deletions may
    not stick", which cannot both be true. Reporting a caveat about work that
    never happened is the same false-claim class this cycle exists to remove.
    """
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.UNSUPPORTED)
    stuck = tmp_path / "decision-alpha.md"

    detail = capture_mod._finish_rollback(tmp_path, [stuck], targets=[stuck])

    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in detail
    assert "still present: decision-alpha.md" in detail
    assert capture_mod.BARRIER_UNSUPPORTED_MARKER not in detail


def test_the_barrier_note_still_fires_when_some_deletion_succeeded(tmp_path, monkeypatch):
    """The guard must not over-correct: a partially-successful rollback DOES have
    deletions whose durability is in question."""
    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", lambda d: BarrierResult.UNSUPPORTED)
    stuck = tmp_path / "decision-alpha.md"
    gone = tmp_path / "decision-beta.md"

    detail = capture_mod._finish_rollback(tmp_path, [stuck], targets=[stuck, gone])

    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in detail
    assert capture_mod.BARRIER_UNSUPPORTED_MARKER in detail


def test_a_missing_directory_is_tolerated_on_the_posix_branch(tmp_path, monkeypatch):
    """R2 Codex P1, and the sharpest C86-L3 illustration in the codebase.

    `tests/test_cycle86_validation_ordering.py` already pins that a nonexistent
    directory must NOT raise (the T7 contract: the barrier must never convert a
    working write into a hard failure). On Windows that test passes VACUOUSLY —
    the platform check returns before the open is attempted — so an R1 fix that
    made `ENOENT` raise was green locally and would have failed Ubuntu CI.

    This test forces the POSIX branch, so the T7 contract is now pinned on both
    platforms instead of only the one CI happens to run.
    """
    _force_posix_branch(monkeypatch)

    assert _fsync_parent_dir(tmp_path / "no-such-dir") is BarrierResult.UNSUPPORTED


def test_only_genuine_storage_faults_raise_from_the_open_branch(tmp_path, monkeypatch):
    """The open branch classifies with an ALLOW-LIST, not the inverse of the
    tolerated set: `fsync` on a valid descriptor cannot return `ENOENT` but
    `open` routinely can, so the two branches face different error populations
    and deriving one rule from the other is what caused the P1."""
    _force_posix_branch(monkeypatch)

    for benign in (errno.ENOENT, errno.ENOTDIR, errno.EACCES):
        monkeypatch.setattr(
            io_mod.os,
            "open",
            lambda *a, _c=benign, **kw: (_ for _ in ()).throw(OSError(_c, os.strerror(_c))),
        )
        assert _fsync_parent_dir(tmp_path) is BarrierResult.UNSUPPORTED, benign

    for fault in (errno.EIO, errno.ENOSPC):
        monkeypatch.setattr(
            io_mod.os,
            "open",
            lambda *a, _c=fault, **kw: (_ for _ in ()).throw(OSError(_c, os.strerror(_c))),
        )
        with pytest.raises(OSError):
            _fsync_parent_dir(tmp_path)
