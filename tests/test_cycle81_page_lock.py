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


class TestInterruptSafety:
    """R2 Codex MAJOR — an async exception must not strand a depth entry.

    The reported window: if a KeyboardInterrupt lands between the depth
    mutation and the `try` that guards it, the `finally` never runs and the key
    stays positive after `file_lock` has released. A pooled thread reused later
    then treats a fresh acquisition as a re-entry and mutates the page holding
    NO lock. The fix moves the mutation INSIDE the `try` and restores the exact
    prior depth.

    HONEST SCOPE (revert-checked per cycle-11 L1): the first two tests below
    pass with OR without that fix, because an exception raised inside the
    `with` body always reaches the `finally`. The vulnerable window is a
    between-two-adjacent-statements gap that pure Python cannot deterministically
    hit without bytecode/trace injection, which is too brittle to pin here.
    They are therefore general interrupt-unwinding coverage, NOT a gate on the
    fix. `test_restore_depth_is_absolute_not_decrement` IS the real gate: it
    pins the absolute-restore contract that makes the window safe, and fails if
    anyone reimplements `_restore_depth` as a decrement.
    """

    def test_interrupt_during_outer_acquire_leaves_no_depth(self, page: Path) -> None:
        from kb.utils import page_lock as pl

        with pytest.raises(KeyboardInterrupt):
            with page_lock(page, timeout=0.25):
                raise KeyboardInterrupt

        assert pl._depths().get(_page_key(page), 0) == 0, "depth stranded after interrupt"
        assert not _lock_sidecar(page).exists()
        # The decisive part: the NEXT acquisition must really acquire.
        with page_lock(page, timeout=0.25):
            assert _lock_sidecar(page).exists()

    def test_interrupt_during_nested_acquire_restores_outer_depth(self, page: Path) -> None:
        from kb.utils import page_lock as pl

        key = _page_key(page)
        with page_lock(page, timeout=0.25):
            assert pl._depths()[key] == 1
            with pytest.raises(KeyboardInterrupt):
                with page_lock(page, timeout=0.25):
                    raise KeyboardInterrupt
            # Depth must be back to exactly 1 — not 2 (stranded) and not 0
            # (over-decremented, which would drop the outer lock's bookkeeping).
            assert pl._depths()[key] == 1
            assert _lock_sidecar(page).exists()

        assert pl._depths().get(key, 0) == 0
        assert not _lock_sidecar(page).exists()

    def test_restore_depth_is_absolute_not_decrement(self) -> None:
        """A decrement is only correct if the increment definitely happened."""
        from kb.utils.page_lock import _restore_depth

        depths: dict[str, int] = {}
        # Simulate the interrupted case: prior was 0, the increment never ran.
        _restore_depth(depths, "k", 0)
        assert "k" not in depths

        # Simulate an interrupted nested acquire: prior 2, increment never ran.
        depths["k"] = 2
        _restore_depth(depths, "k", 2)
        assert depths["k"] == 2


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

    def test_dotdot_path_shares_a_key_with_its_normalised_form(self, tmp_path: Path) -> None:
        """`wiki/../wiki/a.md` and `wiki/a.md` are the same file, so they must
        share a depth key."""
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        direct = wiki / "a.md"
        indirect = wiki / ".." / "wiki" / "a.md"
        assert _page_key(direct) == _page_key(indirect)

    def test_dotdot_and_direct_paths_mutually_exclude(self, tmp_path: Path) -> None:
        """Pins the OS-resolution property `page_lock` relies on.

        The key normalises `..` away while the sidecar path does not, so a
        reviewer will reasonably ask whether one page can end up guarded by two
        sidecars. It cannot: the OS resolves `..` at open time, making
        `wiki/../wiki/a.md.lock` and `wiki/a.md.lock` the same inode. This test
        pins that. It passes with or without normalising the path handed to
        `file_lock` — which is precisely why that normalisation was NOT added.
        """
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        direct = wiki / "a.md"
        direct.write_text("a", encoding="utf-8")
        indirect = wiki / ".." / "wiki" / "a.md"

        refused: list[TimeoutError] = []
        held = threading.Event()
        attempt_done = threading.Event()

        def contender() -> None:
            try:
                held.wait(timeout=10.0)
                try:
                    with page_lock(indirect, timeout=0.1):
                        pass
                except TimeoutError as exc:
                    refused.append(exc)
            finally:
                attempt_done.set()

        t = threading.Thread(target=contender)
        t.start()
        try:
            with page_lock(direct, timeout=0.25):
                held.set()
                assert attempt_done.wait(timeout=10.0), "contender never finished"
        finally:
            t.join(timeout=10.0)

        assert not t.is_alive(), "contender thread did not terminate"
        assert len(refused) == 1, "the `..` spelling bypassed the lock on the same page"


class TestCrossThreadExclusionPreserved:
    """AC01 — reentrancy is thread-local; a second thread still blocks."""

    def test_other_thread_cannot_enter_while_held(self, page: Path) -> None:
        """R2 Codex MINOR — event-driven, not sleep-driven.

        The lock is held until the contender signals it has FINISHED its
        attempt, so a descheduled contender cannot produce a false pass. Only
        `TimeoutError` is accepted: also catching `OSError` would let an
        unrelated permission or lock-parse failure satisfy the exclusion
        assertion without proving contention.
        """
        held = threading.Event()
        attempt_done = threading.Event()
        second_acquired = threading.Event()
        refused: list[TimeoutError] = []

        def contender() -> None:
            try:
                held.wait(timeout=10.0)
                try:
                    with page_lock(page, timeout=0.1):
                        second_acquired.set()
                except TimeoutError as exc:  # expected — lock is held
                    refused.append(exc)
            finally:
                attempt_done.set()

        t = threading.Thread(target=contender)
        t.start()
        try:
            with page_lock(page, timeout=0.25):
                held.set()
                # Hold the lock until the contender's attempt has fully
                # resolved — no fixed sleep, so machine load cannot skew this.
                assert attempt_done.wait(timeout=10.0), "contender never finished"
                assert not second_acquired.is_set()
        finally:
            t.join(timeout=10.0)

        assert not t.is_alive(), "contender thread did not terminate"
        assert len(refused) == 1, "second thread must be excluded with TimeoutError"

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

    def test_evidence_append_runs_under_the_outer_lock(self, page: Path, monkeypatch) -> None:
        """AC04 — the deterministic witness.

        At the exact moment `_update_existing_page` invokes
        `append_evidence_trail`, the page sidecar must ALREADY exist, proving
        the outer `page_lock` is still held. Pre-cycle-81 the body-write lock
        was released before this call, so the sidecar would be absent here —
        which makes this a precise discriminator rather than a timing race.

        Deliberately not a polling watcher: a sampler can miss a critical
        section shorter than its interval and then pass vacuously.
        """
        import kb.ingest.pipeline as pipeline_mod

        real_append = pipeline_mod.append_evidence_trail
        observed: dict[str, bool] = {}

        def probe(page_path: Path, *args, **kwargs):
            observed["sidecar_held"] = _lock_sidecar(page_path).exists()
            return real_append(page_path, *args, **kwargs)

        monkeypatch.setattr(pipeline_mod, "append_evidence_trail", probe)

        _update_existing_page(page, "raw/articles/second.md", name="Alpha", verb="Mentioned")

        assert observed.get("sidecar_held") is True, (
            "evidence append ran with the page lock released — the AC04 window is still open"
        )
        # Non-vacuity: the probe must actually have fired.
        assert "sidecar_held" in observed
        assert not _lock_sidecar(page).exists(), "lock leaked past the outer with-block"


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
