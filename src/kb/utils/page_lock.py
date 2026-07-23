"""Reentrant per-page write lock (cycle 81 AC01).

``kb.utils.io.file_lock`` is a cross-process sidecar lock and is deliberately
NOT reentrant: a thread that already holds ``file_lock(p)`` and tries to take
it again self-deadlocks until the timeout fires. That contract forced
``_update_existing_page`` to *release* its body-write lock before calling
``append_evidence_trail`` (which acquires its own lock), leaving a window in
which a concurrent writer could interleave between the body write and the
provenance append (Phase 4.5 HIGH R5).

``page_lock`` closes that window. It delegates to ``file_lock`` on the
outermost acquisition and degrades to a no-op on re-entry from the SAME thread
for the SAME page, so the whole read → modify → write → append-trail span can
run under one held lock::

    with page_lock(page_path):           # acquires file_lock(page_path)
        _update_existing_page_body(...)  # page_lock(...) → depth 2, no-op
        append_evidence_trail(...)       # page_lock(...) → depth 2, no-op

Reentrancy is tracked in **thread-local** state, so a different thread
contending for the same page still blocks on the real ``file_lock`` — the
cross-process and cross-thread guarantees are unchanged. Only the
same-thread-same-page nesting case is relaxed.

Lock ordering is unaffected: ``page_lock`` never introduces a second distinct
path, so the ``kb.utils.io`` lock-order convention (page_path < history_path <
contradictions_path < log_path < manifest_path) continues to apply to callers
that acquire several different locks.
"""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kb.utils.io import file_lock

# Per-thread map of {normalised page key: nesting depth}. Thread-local by
# construction — a second thread sees an empty map and therefore takes the real
# `file_lock`, preserving cross-thread mutual exclusion.
_held = threading.local()

__all__ = ["page_lock"]


def _page_key(path: Path | str) -> str:
    """Normalise a page path into a stable reentrancy key.

    Uses ``abspath`` rather than ``resolve`` to stay cheap and to avoid
    resolving symlinks — matching ``file_lock``, which derives its sidecar path
    from the path it is handed. ``normcase`` folds Windows drive-letter and
    separator casing so ``C:\\wiki\\a.md`` and ``c:/wiki/a.md`` share one depth
    counter.

    SYMLINK CAVEAT (inherited from ``file_lock``, not introduced here): two
    symlinked aliases of the same file normalise to two different keys AND two
    different sidecars, so they do NOT exclude each other. This predates
    ``page_lock`` — ``file_lock`` has always keyed on the supplied path — and
    is not a hazard for current callers, which build page paths from
    ``wiki_dir`` and pass them through ``_validate_page_id`` /
    ``_assert_under_project_root``. Do not introduce symlinked page aliases
    without switching both primitives to ``resolve()``.
    """
    return os.path.normcase(os.path.abspath(str(path)))


def _depths() -> dict[str, int]:
    """Return this thread's depth map, creating it on first use."""
    depths = getattr(_held, "depths", None)
    if depths is None:
        depths = {}
        _held.depths = depths
    return depths


def _restore_depth(depths: dict[str, int], key: str, prior: int) -> None:
    """Restore ``key`` to its EXACT pre-acquisition depth.

    Deliberately an absolute restore rather than a decrement. A decrement is
    only correct when the matching increment definitely happened; an absolute
    restore is correct either way, which is what makes the async-exception
    window safe (R2 Codex MAJOR — see ``page_lock``).
    """
    if prior > 0:
        depths[key] = prior
    else:
        depths.pop(key, None)


@contextmanager
def page_lock(path: Path | str, timeout: float | None = None) -> Iterator[None]:
    """Acquire a reentrant exclusive lock on a wiki page.

    On the outermost entry this is exactly ``file_lock(path, timeout)`` and can
    raise ``TimeoutError`` / ``OSError`` identically. On a nested entry from the
    same thread for the same page it yields immediately without touching the
    filesystem — ``timeout`` is ignored in that case because no acquisition
    happens.

    The depth counter is incremented only AFTER ``file_lock`` yields, so a
    failed acquisition leaves no phantom depth behind for the next call.

    Args:
        path: Wiki page to lock. Relative paths are resolved against the
            current working directory for keying purposes.
        timeout: Acquisition deadline in seconds, forwarded to ``file_lock``.
            ``None`` uses ``kb.utils.io.LOCK_TIMEOUT_SECONDS``.

    Yields:
        None. The lock is held for the duration of the ``with`` body.

    Raises:
        TimeoutError: If the outermost acquisition cannot take the lock before
            the deadline and the holder process is still alive.
        OSError: If the sidecar lock file is unreadable or unparseable.
    """
    key = _page_key(path)
    depths = _depths()
    prior = depths.get(key, 0)

    if prior > 0:
        # R2 Codex MAJOR — the depth mutation lives INSIDE the try. If it sat
        # outside, an async exception (KeyboardInterrupt, signal, injected
        # cancellation) landing between the increment and the `try` would skip
        # the `finally` and strand a positive depth. A pooled thread reused
        # later would then see depth > 0, treat a fresh acquisition as a
        # re-entry, and write the page holding NO lock at all.
        try:
            depths[key] = prior + 1
            yield
        finally:
            _restore_depth(depths, key, prior)
        # CRITICAL: this return skips the `file_lock` acquisition below. A
        # re-entry must NOT acquire — falling through would self-deadlock
        # against the lock this same thread already holds.
        return

    # The raw `path` is handed to `file_lock` deliberately. The key normalises
    # with `abspath` while the sidecar does not, but that divergence is not
    # observable: the OS resolves `..` and relative segments at open time, so
    # `wiki/../wiki/a.md.lock` and `wiki/a.md.lock` are the same inode.
    # Verified by revert-check (cycle-11 L1): normalising here changes no test
    # outcome, so it would be churn, not a fix.
    with file_lock(Path(path), timeout=timeout):
        # Same INSIDE-the-try discipline as the re-entry branch above, and the
        # restore is absolute (`prior`, which is 0 here) rather than a
        # decrement, so an interrupted acquisition cannot leave the key set.
        try:
            depths[key] = 1
            yield
        finally:
            _restore_depth(depths, key, prior)
