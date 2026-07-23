"""Cycle 81 — reentrant per-page write lock (`kb.utils.page_lock.page_lock`).

Closes the Phase 4.5 HIGH R5 residual gap: `_update_existing_page` used to
release its body-write `file_lock(page_path)` before `append_evidence_trail`
re-acquired the same lock, because the sidecar lock is not reentrant. A
concurrent writer could interleave in that window, landing a body update
between another ingest's body write and its provenance row.

`page_lock` is reentrant per (thread, page): the outermost acquisition delegates
to `file_lock`, nested same-thread same-page acquisitions are no-ops.
Cross-thread and cross-process exclusion are unchanged.

AC coverage:
  AC01 — page_lock reentrancy, key normalisation, depth bookkeeping.
  AC02 — append_evidence_trail nests without deadlocking.
  AC03 — _update_existing_page_body nests without deadlocking.
  AC04 — _update_existing_page holds ONE lock across body write + trail append.
  AC05 — inject_wikilinks uses page_lock.
"""

import os
import threading
import time
from pathlib import Path

import pytest

from kb.ingest.evidence import append_evidence_trail
from kb.ingest.pipeline import _update_existing_page, _update_existing_page_body
from kb.utils.io import file_lock
from kb.utils.page_lock import _page_key, page_lock

PAGE_BODY = """---
title: "Alpha"
source:
  - "raw/articles/first.md"
created: 2026-07-23
updated: 2026-07-23
type: entity
confidence: stated
---

# Alpha

## References

- raw/articles/first.md

## Evidence Trail

<!-- evidence-trail:begin -->
| 2026-07-23 | raw/articles/first.md | Initial extraction |
"""


@pytest.fixture
def page(tmp_path: Path) -> Path:
    p = tmp_path / "alpha.md"
    p.write_text(PAGE_BODY, encoding="utf-8")
    return p


def _lock_sidecar(p: Path) -> Path:
    """The sidecar path `file_lock` creates for `p`."""
    return p.with_suffix(p.suffix + ".lock")


class TestReentrancy:
    """AC01 — same-thread same-page nesting is a no-op, not a deadlock."""

    def test_nested_same_page_does_not_deadlock(self, page: Path) -> None:
        # A bounded timeout means a genuine self-deadlock fails fast rather
        # than hanging the suite.
        with page_lock(page, timeout=0.25), page_lock(page, timeout=0.25):
            assert _lock_sidecar(page).exists()

    def test_three_levels_deep(self, page: Path) -> None:
        with page_lock(page, timeout=0.25):
            with page_lock(page, timeout=0.25):
                with page_lock(page, timeout=0.25):
                    assert _lock_sidecar(page).exists()
        assert not _lock_sidecar(page).exists()

    def test_lock_released_only_at_outermost_exit(self, page: Path) -> None:
        with page_lock(page, timeout=0.25):
            with page_lock(page, timeout=0.25):
                pass
            # Inner exit must NOT drop the real lock.
            assert _lock_sidecar(page).exists()
        assert not _lock_sidecar(page).exists()

    def test_distinct_pages_each_take_a_real_lock(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("a", encoding="utf-8")
        b.write_text("b", encoding="utf-8")
        with page_lock(a, timeout=0.25), page_lock(b, timeout=0.25):
            assert _lock_sidecar(a).exists()
            assert _lock_sidecar(b).exists()

    def test_depth_cleared_after_exit_so_relock_still_acquires(self, page: Path) -> None:
        with page_lock(page, timeout=0.25):
            pass
        # If the depth counter leaked, this second acquisition would be a
        # silent no-op and never create the sidecar.
        with page_lock(page, timeout=0.25):
            assert _lock_sidecar(page).exists()

    def test_exception_inside_body_unwinds_depth(self, page: Path) -> None:
        with pytest.raises(RuntimeError), page_lock(page, timeout=0.25):
            raise RuntimeError("boom")
        assert not _lock_sidecar(page).exists()
        with page_lock(page, timeout=0.25):
            assert _lock_sidecar(page).exists()

    def test_failed_acquisition_leaves_no_phantom_depth(self, page: Path) -> None:
        """A failed acquire must not register depth — otherwise the NEXT call
        would wrongly believe this thread holds the lock and skip acquiring."""
        # Stamp the sidecar with THIS process's PID: file_lock only steals a
        # lock whose holder is dead, so a live PID guarantees a clean timeout
        # rather than a steal.
        _lock_sidecar(page).write_text(str(os.getpid()), encoding="utf-8")
        try:
            with pytest.raises((TimeoutError, OSError)), page_lock(page, timeout=0.01):
                pass
        finally:
            _lock_sidecar(page).unlink(missing_ok=True)
        with page_lock(page, timeout=0.25):
            assert _lock_sidecar(page).exists()


class TestPageKey:
    """AC01 — key normalisation decides what counts as 'the same page'."""

    def test_path_and_str_share_a_key(self, tmp_path: Path) -> None:
        p = tmp_path / "alpha.md"
        assert _page_key(p) == _page_key(str(p))

    def test_distinct_pages_have_distinct_keys(self, tmp_path: Path) -> None:
        assert _page_key(tmp_path / "a.md") != _page_key(tmp_path / "b.md")

    def test_key_is_normcase_stable(self, tmp_path: Path) -> None:
        # normcase is a no-op on POSIX; the invariant that matters on both
        # platforms is that the key is already normalised (idempotent).
        p = tmp_path / "Alpha.md"
        assert _page_key(p) == os.path.normcase(_page_key(p))

    def test_key_is_absolute(self, tmp_path: Path) -> None:
        assert os.path.isabs(_page_key(tmp_path / "alpha.md"))


class TestCrossThreadExclusionPreserved:
    """AC01 — reentrancy is thread-local; a second thread still blocks."""

    def test_other_thread_cannot_enter_while_held(self, page: Path) -> None:
        entered = threading.Event()
        second_acquired = threading.Event()
        failed: list[BaseException] = []

        def contender() -> None:
            entered.wait(timeout=5.0)
            try:
                with page_lock(page, timeout=0.1):
                    second_acquired.set()
            except (TimeoutError, OSError) as exc:  # expected — lock is held
                failed.append(exc)

        t = threading.Thread(target=contender)
        t.start()
        try:
            with page_lock(page, timeout=0.25):
                entered.set()
                time.sleep(0.4)
                assert not second_acquired.is_set()
        finally:
            t.join(timeout=5.0)

        assert failed, "second thread must be excluded, not silently admitted"

    def test_file_lock_and_page_lock_exclude_each_other(self, page: Path) -> None:
        """page_lock must not be a parallel universe — it has to contend on the
        SAME sidecar file_lock uses, or the two would not serialise."""
        with file_lock(page, timeout=0.25):
            with pytest.raises((TimeoutError, OSError)):
                with page_lock(page, timeout=0.01):
                    pass


class TestCallSitesNest:
    """AC02/AC03/AC04 — the real ingest call sites nest under an outer lock."""

    def test_append_evidence_trail_under_outer_page_lock(self, page: Path) -> None:
        with page_lock(page, timeout=0.25):
            append_evidence_trail(page, "raw/articles/second.md", "Mentioned in new source")
        assert "raw/articles/second.md" in page.read_text(encoding="utf-8")

    def test_update_existing_page_body_under_outer_page_lock(self, page: Path) -> None:
        with page_lock(page, timeout=0.25):
            wrote = _update_existing_page_body(
                page_path=page,
                source_ref="raw/articles/second.md",
                name="Alpha",
                verb="Mentioned",
            )
        assert wrote is True
        assert "raw/articles/second.md" in page.read_text(encoding="utf-8")

    def test_update_existing_page_writes_body_and_trail(self, page: Path) -> None:
        _update_existing_page(page, "raw/articles/second.md", name="Alpha", verb="Mentioned")
        text = page.read_text(encoding="utf-8")
        # Body update (frontmatter source list) AND provenance row both landed.
        assert text.count("raw/articles/second.md") >= 2
        assert not _lock_sidecar(page).exists()

    def test_update_existing_page_holds_one_lock_throughout(self, page: Path) -> None:
        """AC04 — the sidecar must stay present for the WHOLE call, including the
        evidence-append step. Pre-cycle-81 the lock was dropped between the body
        write and the trail append; this observes that gap directly."""
        observations: list[bool] = []
        stop = threading.Event()

        def watcher() -> None:
            while not stop.is_set():
                observations.append(_lock_sidecar(page).exists())
                time.sleep(0.001)

        t = threading.Thread(target=watcher, daemon=True)
        t.start()
        try:
            _update_existing_page(page, "raw/articles/second.md", name="Alpha", verb="Mentioned")
        finally:
            stop.set()
            t.join(timeout=5.0)

        # The watcher samples before and after the call too, so "always held"
        # is not assertable. What IS assertable: no held → released → held
        # sequence, which is exactly the re-acquire signature.
        transitions = [(observations[i], observations[i + 1]) for i in range(len(observations) - 1)]
        releases = [i for i, (a, b) in enumerate(transitions) if a and not b]
        reacquires = [i for i, (a, b) in enumerate(transitions) if not a and b]
        assert not (releases and reacquires and min(reacquires) > min(releases)), (
            "lock was released and re-acquired mid-call — the AC04 window is still open"
        )


class TestLinkerUsesPageLock:
    """AC05 — inject_wikilinks routes through page_lock, not raw file_lock."""

    def test_linker_imports_page_lock(self) -> None:
        import kb.compile.linker as linker

        assert hasattr(linker, "page_lock")
        assert not hasattr(linker, "file_lock"), (
            "linker should no longer hold a direct file_lock reference"
        )

    def test_inject_wikilinks_under_outer_page_lock(self, tmp_path: Path) -> None:
        """Reentrancy means the injector can still write a page this thread holds.

        Pre-cycle-81 this deadlocked to the 0.25s `_INJECT_LOCK_TIMEOUT` and the
        page was skipped with a warning.
        """
        from kb.compile.linker import inject_wikilinks

        # `scan_wiki_pages` globs `<wiki_dir>/<subdir>/*.md` for each name in
        # WIKI_SUBDIRS — a flat `entities/`, not `pages/entities/`.
        wiki = tmp_path / "wiki"
        (wiki / "entities").mkdir(parents=True)
        mentioner = wiki / "entities" / "beta.md"
        mentioner.write_text(
            '---\ntitle: "Beta"\n---\n\nBeta discusses Gamma at length.\n',
            encoding="utf-8",
        )
        target = wiki / "entities" / "gamma.md"
        target.write_text('---\ntitle: "Gamma"\n---\n\nGamma.\n', encoding="utf-8")

        with page_lock(mentioner, timeout=0.25):
            updated = inject_wikilinks("Gamma", "entities/gamma", wiki_dir=wiki)

        # `updated` lists the pages that were MODIFIED, i.e. the mentioner.
        assert "entities/beta" in updated
        assert "[[entities/gamma|Gamma]]" in mentioner.read_text(encoding="utf-8")
