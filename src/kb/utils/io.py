"""Atomic file write utilities.

Lock-ordering convention (Cycle 7 AC17): any caller acquiring more than one
``file_lock()`` across the concurrency surface MUST acquire them in stable
alphabetical order by the authoritative path:

    VERDICTS_PATH → FEEDBACK_PATH → REVIEW_HISTORY_PATH

A single out-of-order acquisition can deadlock with any caller honouring the
convention. Verified by cycle-1/2/6 reviewers; deviating from this ordering is
a bug, not a style preference.
"""

import enum
import errno
import json
import logging
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 5.0  # default acquisition deadline
# Cycle 24 AC9 — exponential backoff cap. Read at call time inside `file_lock`
# so tests monkeypatching the module attribute (see
# `tests/test_backlog_by_file_cycle2.py:172,210`) continue to clamp all observed
# sleeps to the patched value. Also doubles as the default polling ceiling for
# the normal + stale-lock retry paths.
LOCK_POLL_INTERVAL = 0.05
# Cycle 24 AC9 — exponential-backoff floor. First retry sleeps for this
# duration; subsequent retries double until capped by ``LOCK_POLL_INTERVAL``.
# Read at call time inside `file_lock` (module attribute, not function-entry
# snapshot).
LOCK_INITIAL_POLL_INTERVAL = 0.01

_IS_WINDOWS = sys.platform == "win32"
_legacy_locks_purged = False
_legacy_locks_purge_lock = threading.Lock()

# Cycle 32 AC6 — fair-queue stagger mitigation (intra-process only,
# probabilistic). Module-level counter tracks how many threads are
# currently inside the ``file_lock`` retry loop so each entrant can
# stagger its first sleep by ``position * _FAIR_QUEUE_STAGGER_MS / 1000``
# (clamped to ``LOCK_POLL_INTERVAL``). Does NOT guarantee fair-queue
# acquisition across processes; only improves the intra-process
# thundering-herd case.
_LOCK_WAITERS: int = 0
_LOCK_WAITERS_LOCK: threading.Lock = threading.Lock()
_FAIR_QUEUE_STAGGER_MS: float = 2.0


def _pid_exists(pid: int) -> bool:
    """Return whether ``pid`` appears to identify a live process.

    POSIX supports ``os.kill(pid, 0)`` as a non-destructive liveness probe.
    Windows does not provide the same contract for ``os.kill``, so use the
    process-query API there instead.
    """
    if pid <= 0:
        return False
    if _IS_WINDOWS:
        return _windows_pid_exists(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        # EPERM and similar errors mean the process exists but cannot be
        # signalled by this user. Treat it as live; do not steal the lock.
        return True
    return True


def _windows_pid_exists(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    # PROCESS_QUERY_LIMITED_INFORMATION is enough for GetExitCodeProcess on
    # Vista+; SYNCHRONIZE keeps compatibility with older process handle rules.
    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    still_active = 259
    error_invalid_parameter = 87
    error_access_denied = 5

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        process_query_limited_information | synchronize,
        False,
        pid,
    )
    if not handle:
        error = ctypes.get_last_error()
        if error == error_invalid_parameter:
            return False
        if error == error_access_denied:
            return True
        # Unknown query failure is not proof of death; avoid lock stealing.
        return True

    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _take_waiter_slot() -> int:
    """Increment ``_LOCK_WAITERS`` and return 0-based position BEFORE increment.

    Caller MUST pair with ``_release_waiter_slot`` in a ``finally`` clause
    (cycle-32 C3 counter-symmetry contract). Position snapshot BEFORE the
    increment means first waiter sees 0 (zero stagger), second sees 1, etc.
    """
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        position = _LOCK_WAITERS
        _LOCK_WAITERS += 1
        return position


def _release_waiter_slot() -> None:
    """Decrement ``_LOCK_WAITERS``; warn on underflow.

    Cycle-32 C14 (R1 Opus R2 residual): silent clamp-to-zero hides
    paired-release bugs. On underflow, emit ``logger.warning`` so counter
    drift surfaces to operators instead of silently inflating stagger for
    all subsequent waiters.
    """
    global _LOCK_WAITERS
    with _LOCK_WAITERS_LOCK:
        if _LOCK_WAITERS > 0:
            _LOCK_WAITERS -= 1
        else:
            logger.warning("_LOCK_WAITERS underflow — paired _take_waiter_slot release missing")


def _cleanup_tmp(tmp_path: str) -> None:
    """Best-effort cleanup of an atomic-write temp file.

    Item 4 (cycle 2): swallow-on-cleanup-failure was silent; now logs WARNING
    so accumulated `.tmp` orphans on AV-locked/OneDrive-synced directories are
    visible. Never masks the caller's original exception (caller re-raises).
    """
    try:
        Path(tmp_path).unlink(missing_ok=True)
    except OSError as cleanup_err:  # pragma: no cover — rare Windows / AV race
        logger.warning("Failed to clean up tempfile %s: %s", tmp_path, cleanup_err)


def _flush_and_fsync(fd: int) -> None:
    """Item 3 (cycle 2): ensure bytes are on stable storage BEFORE atomic rename.
    Without fsync a crash between buffered-write and rename can leave the
    destination atomically replaced with a half-written file; on next
    `load_manifest`/`load_verdicts` the parse fails, silently wiping all
    existing entries. Must RAISE on OSError (threat model: data durability) —
    do not swallow.
    """
    os.fsync(fd)


# Errnos that mean "this filesystem/platform does not support fsync on a
# directory handle" rather than "the storage layer failed". Only these are
# tolerated; anything else (EIO, ENOSPC, …) is a real durability failure and
# propagates. Cycle 86, Codex review MAJOR.
_FSYNC_UNSUPPORTED_ERRNOS = frozenset(
    e
    for e in (
        getattr(errno, name, None)
        for name in ("EINVAL", "ENOTSUP", "EOPNOTSUPP", "EPERM", "EACCES", "ENOSYS", "EBADF")
    )
    if e is not None
)


def _dir_fsync_supported() -> bool:
    """Whether this platform can fsync a directory handle at all.

    A named predicate rather than an inline ``os.name == "nt"``, for the reason
    C86-L3 records: a ``skipif``-guarded platform branch is untested on whichever
    platform the developer is not using, and that is precisely how the Windows
    durability gap survived cycle 86. With the check behind a seam both branches
    are reachable from either platform.

    Monkeypatching ``os.name`` instead is not viable — ``pathlib.Path`` selects
    its concrete flavour from it at instantiation, so faking it makes every
    ``Path(...)`` in the call stack raise ``UnsupportedOperation``. Same hazard
    ``_use_windows_write_through`` exists to avoid; kept separate from it because
    they answer different questions and could diverge (a future platform might
    support one and not the other).
    """
    return os.name != "nt"


class BarrierResult(enum.Enum):
    """Which of three things ``_fsync_parent_dir`` actually did.

    Cycle 89 AC01 (cycle-88 R1 DeepSeek + R2 Codex, same root cause reached from
    two directions). The helper used to return ``None`` in all three cases, so no
    caller could tell a real flush from no flush at all — and both reviewers
    independently proposed making callers report a missing barrier without
    noticing that the information needed to do so did not exist.

    The three values exist because they warrant three DIFFERENT decisions, which
    is what makes this a tri-state rather than a bool:

      * ``FLUSHED`` — the directory entry is on stable storage. Say nothing.
      * ``UNSUPPORTED`` — the filesystem refused (``EINVAL`` / ``ENOTSUP`` /
        ``EPERM`` …, or the directory could not be opened at all). Unusual and
        filesystem-specific, so an operator generally wants to know.
      * ``SKIPPED_PLATFORM`` — Windows, where this is a documented permanent
        no-op. Constant, therefore not worth repeating to a human on every call:
        surfacing it would be the crying-wolf failure cycle 88 rejected twice.

    A genuine storage failure (``EIO`` / ``ENOSPC``) is NOT a value here — it
    still RAISES, exactly as cycle 86 established.
    """

    FLUSHED = "flushed"
    UNSUPPORTED = "unsupported"
    SKIPPED_PLATFORM = "skipped_platform"


def _fsync_parent_dir(directory: Path) -> BarrierResult:
    """Cycle 86 AC04 (Phase 4.5 MEDIUM / cycle-83 threat T12): flush the
    parent directory entry so the ``os.replace`` itself is durable.

    ``_flush_and_fsync`` above guarantees the temp file's CONTENTS reach
    stable storage before the rename. It does not guarantee the RENAME
    does. On ext4 (``data=writeback``), XFS, and several network
    filesystems the directory entry lives in a separate metadata stream,
    so a power loss immediately after ``os.replace`` can leave the
    directory still pointing at the pre-rename inode — the write silently
    reverts. fsync-ing the directory closes that window.

    Failure handling splits on WHY the fsync failed (cycle 86, Codex review
    MAJOR — the first version swallowed every ``OSError`` alike):

      * **Unsupported** (``EINVAL`` / ``ENOTSUP`` / ``EPERM`` / … — see
        ``_FSYNC_UNSUPPORTED_ERRNOS``): tolerated with a WARNING. Some SMB
        and NFS mounts reject ``fsync`` on a directory handle outright, and
        macOS wants ``F_FULLFSYNC`` instead. Treating those as fatal would
        convert writes that work today into hard failures.
      * **Genuine storage failure** (``EIO``, ``ENOSPC``, anything else):
        RAISES. Swallowing these is worse than never calling fsync, because
        the caller reads silence as durability — ``_commit_ingest_manifest``
        would report a committed ingest whose manifest entry a power loss
        can still revert, with success telemetry already on disk saying
        otherwise.

    Note the asymmetry with ``_flush_and_fsync`` above, which raises on
    everything: a content-fsync failure risks promoting a half-written file
    over a good one, which is corruption. A directory-fsync failure risks
    losing a rename, whose recovery is a re-ingest — worth reporting, but
    only when it reflects a real fault rather than an unsupported call.

    A failure to CLOSE the descriptor is logged and swallowed regardless:
    the fsync above has already decided durability, and a close error must
    not overwrite that verdict.

    No-op on Windows: NTFS has no ``O_DIRECTORY``, and ``os.open`` on a
    directory raises ``PermissionError`` there. Windows rename durability is
    obtained a different way — see ``durable_replace``, which routes ``nt``
    around this helper entirely rather than pretending it did something.
    """
    if not _dir_fsync_supported():
        return BarrierResult.SKIPPED_PLATFORM
    try:
        # O_DIRECTORY is POSIX-only and absent on some platforms; fall back
        # to a plain O_RDONLY open, which is valid for directories there.
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as e:
        # Cycle 89 R1 (DeepSeek HIGH). This branch swallowed every errno alike
        # since cycle 86, which was defensible while it returned ``None`` — that
        # claimed nothing. Returning UNSUPPORTED is a positive claim about WHY
        # there was no flush, so an ``EIO`` from failing storage would be
        # mislabelled "this filesystem does not support it" and the caller would
        # read a dying disk as a benign platform limitation. Naming the value is
        # what made the old swallow wrong, so this classification has to match
        # the one the fsync branch below already uses.
        if e.errno not in _FSYNC_UNSUPPORTED_ERRNOS:
            logger.error(
                "Parent-dir open FAILED for %s (errno=%s): %s — rename durability "
                "is not guaranteed for this write",
                directory,
                e.errno,
                e,
            )
            raise
        logger.warning("Could not open parent dir %s for fsync: %s", directory, e)
        # No handle means no flush. Same answer as a refused fsync from the
        # caller's side, so it reports as UNSUPPORTED rather than as success.
        return BarrierResult.UNSUPPORTED
    result = BarrierResult.FLUSHED
    try:
        os.fsync(fd)
    except OSError as e:
        # Cycle 86 (Codex review MAJOR) — distinguish "this filesystem does not
        # support the operation" from "the storage layer failed". The first is
        # the case this helper exists to tolerate; the second is a real
        # durability failure, and swallowing it would let `_commit_ingest_manifest`
        # report a committed ingest whose manifest a power loss can still revert.
        if e.errno in _FSYNC_UNSUPPORTED_ERRNOS:
            logger.warning(
                "Parent-dir fsync unsupported for %s (errno=%s): %s", directory, e.errno, e
            )
            result = BarrierResult.UNSUPPORTED
        else:
            logger.error(
                "Parent-dir fsync FAILED for %s (errno=%s): %s — rename durability "
                "is not guaranteed for this write",
                directory,
                e.errno,
                e,
            )
            raise
    finally:
        # A failure to close leaves descriptor state uncertain but the fsync
        # above already decided durability, so it must not mask that verdict.
        try:
            os.close(fd)
        except OSError as close_err:
            logger.warning("Failed to close parent-dir fd for %s: %s", directory, close_err)
    return result


# Win32 ``MoveFileExW`` flags. ``MOVEFILE_COPY_ALLOWED`` is deliberately absent:
# it lets the move degrade into a cross-volume copy+delete, which is not an
# atomic replacement and would reintroduce the torn-write window this helper
# exists to close.
_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_WRITE_THROUGH = 0x8


def _resolve_move_file_ex_w():  # pragma: no cover - exercised via a faked platform
    """Return a fully-typed ``MoveFileExW`` callable. Windows only.

    Split into its own function for two reasons. It keeps the ``ctypes`` ABI
    declaration in one auditable place — cycle 65 lost a day to an under-declared
    ``CreateFileW`` whose wrong ``restype`` broke real-file unlinks — and it gives
    the faked-platform tests a seam, since ``ctypes.WinDLL`` does not exist on the
    POSIX CI runner at all.

    ``use_last_error=True`` is load-bearing: it makes ctypes capture the thread's
    Win32 error code immediately after the call, so ``ctypes.get_last_error()``
    cannot be clobbered by an intervening call the way a bare
    ``GetLastError()`` lookup can be.
    """
    import ctypes
    import ctypes.wintypes

    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    move_file_ex_w = kernel32.MoveFileExW
    move_file_ex_w.argtypes = (
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.DWORD,
    )
    move_file_ex_w.restype = ctypes.wintypes.BOOL
    return move_file_ex_w


def _raise_last_windows_error() -> None:  # pragma: no cover - faked platform
    """Raise an ``OSError`` carrying the last Win32 error. Windows only."""
    import ctypes

    raise ctypes.WinError(ctypes.get_last_error())


class RenameCompletedBarrierError(OSError):
    """The rename COMPLETED, and only the durability barrier afterwards failed.

    Cycle 87 R1 (Codex MAJOR-1). ``os.replace`` was atomic in the sense callers
    relied on: it either renamed or raised, never both. ``durable_replace`` broke
    that, because the POSIX parent-directory fsync runs AFTER the rename and
    cycle-86 made it raise on genuine storage failure (``EIO`` / ``ENOSPC``).

    A caller that treats any exception as "the promote did not happen" will then
    leave the destination in place while reporting failure. For
    ``capture._write_item_files`` that silently breaks an explicit all-or-nothing
    contract: the orphan ``<slug>.md`` survives a capture reported as `([], err)`.

    Subclasses ``OSError`` so every existing ``except OSError`` still catches it;
    callers that must distinguish check for this type explicitly.

    **Only all-or-nothing callers need to handle it.** ``atomic_json_write`` and
    ``_atomic_text_write_replace`` deliberately do NOT: their destination now
    holds the new content, which is the outcome the caller asked for, and the
    exception means "that write is not durability-guaranteed", not "it did not
    happen". Rolling it back would DESTROY a completed write over a failed
    fsync. Their ``_cleanup_tmp`` is a no-op here because the temp was renamed
    away, which is correct. ``capture._write_item_files`` is different only
    because it promises all-or-nothing across a BATCH, so one item's completed
    promote has to be undone when a later step fails.
    """


def _use_windows_write_through() -> bool:
    """Whether ``durable_replace`` should take the Win32 write-through path.

    A named predicate rather than an inline ``os.name == "nt"`` so the tests can
    drive BOTH branches on a single platform. Monkeypatching ``os.name`` itself
    is not viable: ``pathlib.Path`` selects its concrete flavour from it at
    instantiation, so faking it makes every ``Path(...)`` in the call stack raise
    ``UnsupportedOperation``.
    """
    return os.name == "nt"


def durable_replace(tmp: Path | str, dest: Path | str) -> None:
    """Atomically replace ``dest`` with ``tmp``, making the RENAME durable.

    Cycle 87 AC01 (Phase 4.5 MEDIUM, cycle-86 Codex review MAJOR). Cycle 86 added
    a rename barrier but only a POSIX one, so the platform this project is
    actually developed on kept no durability guarantee at all. This helper is the
    single promote path for every caller that needs one, which is the other half
    of the fix: the same gap kept reappearing because each site rolled its own
    ``os.replace``.

    **POSIX** — rename, then fsync the parent directory, because the directory
    entry lives in a separate metadata stream on ext4 ``data=writeback``, XFS and
    several network filesystems.

    **Windows** — ``MoveFileExW`` with ``MOVEFILE_WRITE_THROUGH``, which MSDN
    defines as not returning until the move has been flushed to disk. This does
    NOT go through ``os.replace``: CPython passes only
    ``MOVEFILE_REPLACE_EXISTING``, so the ``os.replace``-is-durable-on-NTFS claim
    the previous docstring made was never true.

    Two shapes were rejected during design (both reviewers independently agreed).
    Re-opening ``dest`` after the rename and fsync-ing that handle is durability
    theatre: ``FlushFileBuffers`` flushes the file's own data and MFT record, not
    the parent directory index that carries the name, and it would additionally
    race any concurrent unlink of ``dest``. Falling back to ``os.replace`` when
    the write-through move fails is worse than the original bug, because it
    converts a durability failure into a successful-looking write.
    """
    if _use_windows_write_through():
        move_file_ex_w = _resolve_move_file_ex_w()
        if not move_file_ex_w(
            os.fspath(tmp),
            os.fspath(dest),
            _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH,
        ):
            _raise_last_windows_error()
        return
    # Arguments are passed through unchanged rather than coerced to Path: callers
    # that hand in strings have their exact call shape preserved for spies.
    os.replace(tmp, dest)
    try:
        _fsync_parent_dir(Path(dest).parent)
    except OSError as exc:
        # Cycle 87 R1 (Codex MAJOR-1) — past this line the rename has ALREADY
        # happened, so a bare re-raise would tell the caller "the promote did not
        # occur" while the destination sits there. Re-raise as a distinct type so
        # callers with an all-or-nothing contract can undo it. See
        # RenameCompletedBarrierError.
        raise RenameCompletedBarrierError(exc.errno, str(exc)) from exc


def durable_rename(src: Path | str, dest: Path | str) -> None:
    """Rename ``src`` to ``dest`` durably, REFUSING to clobber an existing dest.

    Cycle 87 R2 (Codex MINOR-4 + MINOR-5). The R1 fixes routed two callers onto
    ``durable_replace`` to gain a barrier, which silently also swapped their
    semantics: ``Path.rename`` refuses an existing destination, while
    ``os.replace`` and ``MOVEFILE_REPLACE_EXISTING`` overwrite it. Both callers
    depend on the refusal — ``wiki_log.rotate_if_oversized`` picks its archive
    name with an ordinal loop whose whole point is not to destroy an existing
    archive, and the augment consumed-proposal name is unique only to 8 run-id
    characters. Adding durability should not have changed who wins a collision.

    So the barrier and the clobber policy are separated: this is the no-clobber
    variant; ``durable_replace`` is the overwrite variant, used for tmp→final
    promotes where overwriting IS the contract.

    Raises ``FileExistsError`` if ``dest`` exists, and
    ``RenameCompletedBarrierError`` if the rename completed but the barrier then
    failed (same contract as ``durable_replace`` — see that type's docstring).
    """
    if _use_windows_write_through():
        move_file_ex_w = _resolve_move_file_ex_w()
        # No MOVEFILE_REPLACE_EXISTING: the move fails rather than destroying an
        # existing dest, which is the semantic being preserved here.
        if not move_file_ex_w(os.fspath(src), os.fspath(dest), _MOVEFILE_WRITE_THROUGH):
            _raise_last_windows_error()
        return

    # NOT `os.rename`: on POSIX that is `rename(2)`, which REPLACES an existing
    # destination silently — the no-clobber behaviour callers see from
    # `Path.rename` is Windows-only. Using it here would have left the exact
    # archive-destroying bug this function exists to prevent, on the CI platform
    # (caught by CI, not locally, because the local platform is the one where
    # `os.rename` does refuse).
    #
    # `link(2)` is the portable atomic no-clobber primitive: it fails with EEXIST
    # if the destination exists, with no window between the check and the create.
    # Both call sites move within one directory, so the cross-filesystem and
    # no-hardlink-support limitations of `os.link` do not apply.
    os.link(src, dest)
    os.unlink(src)
    try:
        _fsync_parent_dir(Path(dest).parent)
    except OSError as exc:
        raise RenameCompletedBarrierError(exc.errno, str(exc)) from exc


def atomic_json_write(data: object, path: Path) -> None:
    """Write data as JSON to path atomically (temp file + rename).

    Creates parent directories if needed. On failure, cleans up the
    temp file and re-raises the exception.

    Caveat: cloud-synced or network-backed directories such as OneDrive or SMB
    shares can transiently lock the temp file or destination and make the final
    replace time out or fail. Failed writes attempt immediate cleanup, but a
    locked sibling `.tmp` can remain; callers that write in those directories
    should periodically call `sweep_orphan_tmp(path.parent)` to remove old
    orphan temp files.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    fd_transferred = False
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            fd_transferred = True
            json.dump(data, f, indent=2, allow_nan=False)
            f.flush()
            _flush_and_fsync(f.fileno())
        # Cycle 87 AC01 — the rename is only durable once the directory entry
        # (POSIX) or the move itself (Windows) is flushed. See durable_replace.
        durable_replace(tmp_path, path)
    except BaseException:
        # fd_transferred=True means os.fdopen took ownership; the with-block already
        # closed it. Only close manually if os.fdopen never ran (rare failure).
        if not fd_transferred:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        _cleanup_tmp(tmp_path)
        raise


def _atomic_text_write_replace(content: str, path: Path) -> None:
    """Tempfile + os.replace crash-atomic write. Internal — used by both the
    default ``atomic_text_write`` path and the ``exclusive=True`` branch (after
    O_EXCL reserves the destination).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    fd_transferred = False
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            fd_transferred = True
            f.write(content)
            f.flush()
            _flush_and_fsync(f.fileno())
        # Cycle 87 AC01 — same-class peer of atomic_json_write's barrier
        # (cycle-86 design Q4). This is the higher-traffic surface of the two:
        # every wiki page, evidence-trail append, and log.md write lands here.
        durable_replace(tmp_path, path)
    except BaseException:
        if not fd_transferred:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        _cleanup_tmp(tmp_path)
        raise


def atomic_text_write(content: str, path: Path | str, *, exclusive: bool = False) -> None:
    """Write text to path atomically (temp file + rename).

    Creates parent directories if needed. On failure, cleans up the
    temp file and re-raises the exception.

    ``exclusive=False`` (default) — replace-or-create semantics via
    tempfile + ``os.replace``. Existing files are atomically overwritten.

    ``exclusive=True`` — create-or-fail semantics via
    ``os.open(O_CREAT | O_EXCL | O_WRONLY)`` for race-safe slug reservation,
    followed by the same tempfile + rename for crash-safety. Raises
    ``FileExistsError`` if ``path`` already exists. Cleans up the empty
    reservation on any failure of the inner write, including ``BaseException``
    (KeyboardInterrupt, SystemExit). Cycle 44 unifies ``capture._exclusive_atomic_write``
    into this helper per Phase 4.6 M4.

    Caveat: cloud-synced or network-backed directories such as OneDrive or SMB
    shares can transiently lock the temp file or destination and make the final
    replace time out or fail. Failed writes attempt immediate cleanup, but a
    locked sibling `.tmp` can remain; callers that write in those directories
    should periodically call `sweep_orphan_tmp(path.parent)` to remove old
    orphan temp files.
    """
    path = Path(path)
    if not exclusive:
        _atomic_text_write_replace(content, path)
        return
    # Cycle 44 M4: O_EXCL race-safe reservation + tempfile crash-safety
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(fd)
    try:
        _atomic_text_write_replace(content, path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _purge_legacy_locks(base: Path | None = None) -> int:
    """Item 2 (cycle 2): one-time migration that removes lock files whose
    content is not ASCII-decodable pure int. Legacy runs may have written PID
    files with UTF-8/BOM/CRLF; the cycle-2 `file_lock` path RAISES on such
    content rather than stealing — without this purge the first acquisition
    after upgrade would fail. Idempotent: files already clean are skipped.
    """
    from kb.config import PROJECT_ROOT

    scan_base = base if base is not None else PROJECT_ROOT / ".data"
    if not scan_base.exists():
        return 0
    purged = 0
    for lock_file in scan_base.rglob("*.lock"):
        try:
            text = lock_file.read_text(encoding="ascii")
            int(text.strip())
        except (OSError, UnicodeDecodeError, ValueError):
            try:
                lock_file.unlink(missing_ok=True)
                purged += 1
            except OSError as exc:  # pragma: no cover
                logger.warning("Failed to purge legacy lock %s: %s", lock_file, exc)
    if purged:
        logger.info("Purged %d legacy lock file(s) under %s", purged, scan_base)
    return purged


def sweep_orphan_tmp(directory: Path, *, max_age_seconds: float = 3600.0) -> int:
    """Remove old top-level atomic-write `.tmp` siblings from a directory.

    The input is resolved before scanning, then only files matching
    `directory.glob("*.tmp")` are considered. The scan is intentionally
    non-recursive so callers can sweep a directory of atomic-write siblings
    without deleting unrelated temp files in nested application data.

    A temp file is removed only when `time.time() - path.stat().st_mtime` is
    greater than `max_age_seconds`; fresh files are left in place because they
    may belong to an active writer. `OSError` from `stat()` or `unlink()` is
    logged at WARNING with the path and error detail, then swallowed so one
    locked, missing, or permission-denied temp file does not block the rest of
    the sweep.

    Returns the number of files successfully removed. Never raises past the
    boundary — a missing, non-directory, or permission-denied `directory` logs
    WARNING and returns 0 so callers (CLI boot, ingest tail, cleanup scripts)
    can invoke the sweep unconditionally without defensive pre-checks.
    """
    directory = Path(directory).resolve()
    if not directory.exists():
        logger.warning("sweep_orphan_tmp: directory does not exist: %s", directory)
        return 0
    if not directory.is_dir():
        logger.warning("sweep_orphan_tmp: path is not a directory: %s", directory)
        return 0

    removed = 0
    try:
        candidates = list(directory.glob("*.tmp"))
    except OSError as exc:
        logger.warning("Failed to scan tmp files in %s: %s", directory, exc)
        return removed

    for path in candidates:
        try:
            age_seconds = time.time() - path.stat().st_mtime
        except OSError as exc:
            logger.warning("Failed to stat tmp file %s: %s", path, exc)
            continue
        if age_seconds <= max_age_seconds:
            continue
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove tmp file %s: %s", path, exc)
            continue
        removed += 1
    return removed


def _ensure_legacy_locks_purged() -> None:
    """Cycle 2 PR review R1: run `_purge_legacy_locks` lazily on first
    `file_lock` acquisition rather than at module import. Avoids touching
    the real PROJECT_ROOT/.data/ directory during test collection or any
    other import-time path that doesn't actually acquire a lock.
    """
    global _legacy_locks_purged
    if _legacy_locks_purged:
        return
    with _legacy_locks_purge_lock:
        if _legacy_locks_purged:
            return
        try:
            _purge_legacy_locks()
        except Exception as exc:  # pragma: no cover — purge must not block acquire
            logger.warning("_purge_legacy_locks failed on first use: %s", exc)
        _legacy_locks_purged = True


def _backoff_sleep_interval(attempt_count: int) -> float:
    """Cycle 24 AC9 — compute the retry-sleep duration for ``file_lock``.

    Reads ``LOCK_INITIAL_POLL_INTERVAL`` and ``LOCK_POLL_INTERVAL`` from the
    module at CALL TIME (attribute lookup) so test monkeypatches on either
    constant take effect. Bounds the exponent at 30 to avoid ``OverflowError``
    under degenerate conditions (e.g., when ``LOCK_POLL_INTERVAL`` is
    monkeypatched to 0 and the caller spins); the cap clamps the duration to
    the current ``LOCK_POLL_INTERVAL`` value regardless.
    """
    # `min(..., 30)` prevents `2**attempt_count` from exploding into a bignum.
    # Once `2**30 * INITIAL` exceeds any reasonable CAP, further doubling is
    # irrelevant — the outer `min` with CAP already clamps the result.
    shift = min(attempt_count, 30)
    return min(LOCK_INITIAL_POLL_INTERVAL * (2**shift), LOCK_POLL_INTERVAL)


@contextmanager
def file_lock(path: Path, timeout: float | None = None):
    """Acquire a cross-process exclusive lock via a PID-stamped lock file.

    Writes the holder's PID to the lock file so that a timed-out waiter can
    verify the lock is stale (holder process no longer running) before stealing.

    Item 2 (cycle 2): PID files are read as ASCII; on decode/int failure the
    waiter RAISES rather than silently stealing — corruption is not proof of
    death.  Legacy non-ASCII lock files are purged once at module load.
    Item 1 (cycle 2): `acquired=True` is set only AFTER `os.write` returns
    successfully; the cleanup still runs via `finally` on partial writes.

    Raises TimeoutError if the lock is held by a running process.  Raises
    OSError on unparseable lock content (item 2).

    Windows PID-recycling caveat: stale-lock detection depends on the PID in
    the lock file. Windows can recycle PIDs, so a timed-out waiter can see a
    different live process with the same PID and avoid stealing the lock even
    though the original holder is gone. Investigate and delete such lock files
    manually when the owning process is known to be dead.

    Lock-order convention (Phase 4.5 HIGH cycle 1):
      page_path < history_path < contradictions_path < log_path < manifest_path
      (refine_page is the only nested-lock path today: page_path then history_path.)
    """
    _ensure_legacy_locks_purged()
    deadline_timeout = LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    my_pid_bytes = str(os.getpid()).encode("ascii")
    deadline = time.monotonic() + deadline_timeout
    acquired = False
    # Cycle 24 AC9 — exponential-backoff counter shared across all three
    # polling sites (normal retry, POSIX stale-steal, Windows stale-steal) per
    # design CONDITION 7. Incremented at every `time.sleep` call. Sleep duration
    # is `min(LOCK_INITIAL_POLL_INTERVAL * (2 ** attempt), LOCK_POLL_INTERVAL)`;
    # both constants read at CALL TIME (module attribute lookup) so
    # monkeypatching either one in tests takes effect immediately.
    attempt_count = 0
    # Cycle 32 AC6 — fair-queue position snapshot (intra-process only mitigation).
    # Pair with ``_release_waiter_slot()`` in the finally clause (C3 symmetry).
    # Cycle 32 PR review R1 Codex MAJOR 1 — take the slot INSIDE the outer try
    # and guard release with ``slot_taken`` to close a narrow window where a
    # KeyboardInterrupt landing between ``_take_waiter_slot()`` returning and
    # the try-statement being entered would leak the counter increment.
    slot_taken = False
    try:
        position = _take_waiter_slot()
        slot_taken = True
        # Cycle 32 C11 — one-shot initial stagger BEFORE retry loop, clamped
        # to ``LOCK_POLL_INTERVAL`` to prevent double-compounding with
        # exponential backoff (T7). Position=0 → zero stagger → no latency
        # change for uncontended acquires.
        if position > 0:
            stagger_s = min(
                position * _FAIR_QUEUE_STAGGER_MS / 1000.0,
                LOCK_POLL_INTERVAL,
            )
            time.sleep(stagger_s)
        while not acquired:
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                write_ok = False
                try:
                    os.write(fd, my_pid_bytes)
                    write_ok = True
                    # Item 1 (cycle 2): mark acquired right after the WRITE
                    # succeeds so the outer `finally: if acquired: unlink`
                    # runs even if a later step (e.g. `os.close` interrupted
                    # by SIGINT) raises — preserves Phase 4.5 CRITICAL item 15
                    # "no orphan lock on SIGINT during acquire".
                    acquired = True
                finally:
                    os.close(fd)
                    # Cycle 2 PR review R3 MAJOR: if `os.write` raised, the lock
                    # file exists on disk with no PID content — unlink here so
                    # the next waiter doesn't see an empty file that the
                    # cycle-2 RAISE-on-unparseable policy (item 2) would
                    # permanently reject.
                    if not write_ok:
                        try:
                            lock_path.unlink(missing_ok=True)
                        except OSError:  # pragma: no cover — best effort
                            logger.warning(
                                "Failed to unlink orphan lock %s after write failure",
                                lock_path,
                            )
            except PermissionError as perm_exc:
                # Cycle 3 H2: a PermissionError from os.open(O_CREAT|O_EXCL) is
                # NOT evidence that the lock is held by another process — it
                # means the directory itself cannot be written (read-only mount,
                # AV-locked parent, EACCES from tightened ACLs). Retrying the
                # same create would spin the same permission error until the
                # deadline, then enter the stale-lock path that re-raises the
                # denied read as "PID dead → safe to steal" — silently
                # corrupting the verdict/feedback RMW chain. Raise immediately
                # so the operator sees the real bug.
                raise OSError(f"Cannot create lock at {lock_path}: {perm_exc}") from perm_exc
            except FileExistsError:
                if time.monotonic() > deadline:
                    # Item 2 (cycle 2): ASCII-only decode + int-parse. Any
                    # failure is a corruption signal, not proof of death —
                    # surface as OSError.
                    try:
                        content = lock_path.read_text(encoding="ascii")
                    except (OSError, UnicodeDecodeError) as exc:
                        raise OSError(
                            f"Lock {lock_path} has unparseable content: {exc!r}. "
                            "Corruption is not proof of death — investigate manually."
                        ) from exc
                    try:
                        stale_pid = int(content.strip())
                    except ValueError as exc:
                        raise OSError(
                            f"Lock {lock_path} content is not an integer PID: "
                            f"{content!r}. Investigate manually."
                        ) from exc
                    if not _pid_exists(stale_pid):
                        # Unambiguous: PID doesn't exist — safe to steal.
                        lock_path.unlink(missing_ok=True)
                        time.sleep(_backoff_sleep_interval(attempt_count))
                        attempt_count += 1
                        continue
                    raise TimeoutError(
                        f"Lock {lock_path} held by running PID {stale_pid}. "
                        "Stop that process or delete the lock file."
                    )
                time.sleep(_backoff_sleep_interval(attempt_count))
                attempt_count += 1
        yield
    finally:
        # Cycle 32 C3 — release waiter slot on every exit path (success,
        # TimeoutError, PermissionError, KeyboardInterrupt). Guarded by
        # ``slot_taken`` so an exception BEFORE the slot was taken does not
        # decrement a counter that was never incremented (R1 Codex MAJOR 1).
        if slot_taken:
            _release_waiter_slot()
        if acquired:
            # Cycle 82 (R2 Codex MAJOR): the release unlink MUST NOT raise.
            # This runs during exception unwinding, so an OSError here would
            # REPLACE the in-flight exception — e.g. the
            # StorageError("evidence_trail_append_failure") that
            # `_update_existing_page` raises while still holding the page lock,
            # destroying the caller's partial-write classification. Raising is
            # also wrong on the success path: the guarded writes already
            # committed, so failing to tidy up the sidecar is not a failure of
            # the operation. Log and move on — a leftover lock file is
            # self-healing via the PID-based stale-lock steal above.
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Failed to remove lock file %s on release; "
                    "it will be reclaimed by stale-lock detection",
                    lock_path,
                )
