"""Cycle 8 contradiction persistence idempotency coverage."""

from __future__ import annotations

import contextlib
import logging
import threading
from datetime import date

import pytest

from kb.ingest.pipeline import _persist_contradictions

# Cycle 84 — generous budgets for the two threaded tests below.
#
# These tests assert a real invariant (concurrent RMW under `file_lock` loses no
# write). They were flaky under full-suite load, and the cause was NOT a missing
# barrier — it was three independent 5-second budgets that a loaded machine can
# each blow through: the rendezvous barrier, the thread join, and `file_lock`'s
# own `LOCK_TIMEOUT_SECONDS` (5.0). Any one exceeded produces a spurious failure
# (BrokenBarrierError / still-alive thread / TimeoutError) that looks like a lock
# bug but is scheduler starvation.
#
# Raising the budgets does NOT weaken the assertions: a genuinely broken lock
# still loses a write and still fails the content assertions. The timeouts only
# exist so the test cannot hang forever, so they should sit far above any
# plausible scheduling delay rather than near it.
_THREAD_BUDGET_SECONDS = 60.0
_LOCK_BUDGET_SECONDS = 30.0


@pytest.fixture
def generous_lock_timeout(monkeypatch):
    """Widen `file_lock`'s acquisition deadline for load-sensitive threaded tests.

    `file_lock` reads `LOCK_TIMEOUT_SECONDS` at call time, so patching the module
    attribute takes effect for acquisitions made inside the test.
    """
    import kb.utils.io as io_mod

    monkeypatch.setattr(io_mod, "LOCK_TIMEOUT_SECONDS", _LOCK_BUDGET_SECONDS)
    return _LOCK_BUDGET_SECONDS


def test_same_day_reingest_skips_identical_contradiction_block(tmp_path, caplog):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    contradictions = [{"claim": "Alpha contradicts beta."}]

    _persist_contradictions(contradictions, "raw/articles/source.md", wiki_dir)
    with caplog.at_level(logging.DEBUG, logger="kb.ingest.pipeline"):
        _persist_contradictions(contradictions, "raw/articles/source.md", wiki_dir)

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    header = f"## raw/articles/source.md — {date.today().isoformat()}\n"
    assert content.count(header) == 1
    assert content.count("- Alpha contradicts beta.\n") == 1
    assert any("Skipping duplicate contradiction block" in r.getMessage() for r in caplog.records)
    assert all("Alpha contradicts beta" not in r.getMessage() for r in caplog.records)


def test_same_day_same_source_with_different_claims_appends_distinct_block(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    _persist_contradictions([{"claim": "First claim."}], "raw/articles/source.md", wiki_dir)
    _persist_contradictions([{"claim": "Second claim."}], "raw/articles/source.md", wiki_dir)

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    header = f"## raw/articles/source.md — {date.today().isoformat()}\n"
    assert content.count(header) == 2
    assert "- First claim.\n" in content
    assert "- Second claim.\n" in content


def test_source_ref_header_injection_is_stripped_before_persist(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()

    _persist_contradictions(
        [{"claim": "Injected source ref should not create a second header."}],
        "## raw/articles/source.md\n## injected",
        wiki_dir,
    )

    content = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    header = f"## raw/articles/source.md — {date.today().isoformat()}\n"
    assert header in content
    assert "## injected" not in content


def test_concurrent_same_day_same_source_distinct_claims_both_persist(
    tmp_wiki, generous_lock_timeout
):
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(claim: str) -> None:
        try:
            barrier.wait(timeout=_THREAD_BUDGET_SECONDS)
            _persist_contradictions([{"claim": claim}], "raw/a.md", tmp_wiki)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("claim-alpha",)),
        threading.Thread(target=worker, args=("claim-beta",)),
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_THREAD_BUDGET_SECONDS)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    content = (tmp_wiki / "contradictions.md").read_text(encoding="utf-8")
    assert content.count("claim-alpha") == 1
    assert content.count("claim-beta") == 1


def test_concurrent_identical_claim_block_dedups_once(tmp_wiki, generous_lock_timeout):
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=_THREAD_BUDGET_SECONDS)
            _persist_contradictions([{"claim": "claim-alpha"}], "raw/a.md", tmp_wiki)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=_THREAD_BUDGET_SECONDS)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    content = (tmp_wiki / "contradictions.md").read_text(encoding="utf-8")
    assert content.count("claim-alpha") == 1


def test_removing_the_lock_loses_a_write(tmp_wiki, monkeypatch):
    """Meta-test: with `file_lock` neutered, a concurrent write IS lost.

    Cycle 85 (review MINOR). The tests above assert that the locked
    read-modify-write loses no write — but they only fail against a REMOVED lock
    if the two threads' RMW windows happen to overlap, which a barrier aligning
    thread *starts* does not guarantee. So "they pass" was weak evidence that the
    lock is load-bearing.

    This test supplies the missing half: it removes the lock and FORCES the
    overlap deterministically, then asserts a write really is lost. If this ever
    starts passing without losing a write, the sibling tests above have stopped
    being able to detect a broken lock and need rethinking.

    Determinism: alpha is held at its write until beta has completed a full
    read+write, so alpha's in-memory `existing` (read before beta wrote) is
    stale and its write clobbers beta's block. That interleaving is exactly what
    `file_lock` exists to prevent, and is impossible while the lock is real.
    """
    from contextlib import contextmanager

    import kb.ingest.pipeline as pipeline_mod

    @contextmanager
    def _no_lock(_path, timeout=None):
        yield

    monkeypatch.setattr(pipeline_mod, "file_lock", _no_lock)

    alpha_may_write = threading.Event()
    beta_written = threading.Event()
    real_write = pipeline_mod.atomic_text_write

    def _gated_write(content: str, path):
        if "claim-alpha" in content:
            # Hold alpha until beta has fully committed its own block.
            alpha_may_write.set()
            # Cycle 85 (review MINOR) — the wait result is asserted, not ignored.
            # If beta's write failed and was swallowed, alpha would resume on the
            # timeout and the "beta absent" assertion below would pass for the
            # WRONG reason (beta never wrote at all, rather than being clobbered).
            assert beta_written.wait(timeout=_THREAD_BUDGET_SECONDS), (
                "beta never completed its write, so this test cannot prove alpha clobbered it"
            )
        result = real_write(content, path)
        if "claim-beta" in content:
            beta_written.set()
        return result

    monkeypatch.setattr(pipeline_mod, "atomic_text_write", _gated_write)

    errors: list[BaseException] = []

    def worker(claim: str) -> None:
        try:
            _persist_contradictions([{"claim": claim}], "raw/a.md", tmp_wiki)
        except BaseException as exc:  # noqa: BLE001 — surfaced below
            errors.append(exc)

    t_alpha = threading.Thread(target=worker, args=("claim-alpha",))
    t_alpha.start()
    # Only start beta once alpha has read and is parked at its write.
    assert alpha_may_write.wait(timeout=_THREAD_BUDGET_SECONDS), "alpha never reached its write"

    t_beta = threading.Thread(target=worker, args=("claim-beta",))
    t_beta.start()

    for thread in (t_alpha, t_beta):
        thread.join(timeout=_THREAD_BUDGET_SECONDS)

    assert not any(t.is_alive() for t in (t_alpha, t_beta))
    assert errors == []

    content = (tmp_wiki / "contradictions.md").read_text(encoding="utf-8")
    assert "claim-alpha" in content, "alpha wrote last, so its block must survive"
    assert "claim-beta" not in content, (
        "beta's block should have been CLOBBERED by alpha's stale read. If it "
        "survived, this harness can no longer detect a removed lock, which means "
        "the sibling no-lost-write tests are not actually falsifiable."
    )


def test_lock_timeout_retries_once_then_reports_the_drop(tmp_wiki, monkeypatch, caplog):
    """A lock timeout is retried exactly once, then the loss is named.

    Cycle 85 (review MINOR) — the retry loop and both DROPPED-warning paths had no
    coverage. This pins: exactly two acquisition attempts, the second using the
    longer deadline, and a final WARNING that names the source and the claim count
    so an operator can tell what was discarded and re-ingest it.
    """
    import kb.ingest.pipeline as pipeline_mod

    attempts: list[float | None] = []

    @contextlib.contextmanager
    def _always_timeout(_path, timeout=None):
        attempts.append(timeout)
        raise TimeoutError("simulated lock contention")
        yield  # pragma: no cover — unreachable, keeps this a generator

    monkeypatch.setattr(pipeline_mod, "file_lock", _always_timeout)

    with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
        pipeline_mod._persist_contradictions(
            [{"claim": "alpha"}, {"claim": "beta"}], "raw/articles/src.md", tmp_wiki
        )

    assert len(attempts) == 2, f"expected exactly one retry; got attempts={attempts!r}"
    assert attempts[0] is None, "first attempt must use file_lock's default deadline"
    assert attempts[1] == pipeline_mod._CONTRADICTION_RETRY_LOCK_TIMEOUT, (
        f"retry must use the longer deadline; got {attempts[1]!r}"
    )

    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    dropped = [m for m in messages if "DROPPED" in m]
    assert dropped, f"the give-up path must name the loss; got {messages!r}"
    assert "2 contradiction(s)" in dropped[-1], f"claim count missing from {dropped[-1]!r}"
    assert "raw/articles/src.md" in dropped[-1], f"source ref missing from {dropped[-1]!r}"


def test_write_failure_inside_the_lock_is_not_retried(tmp_wiki, monkeypatch, caplog):
    """A failure INSIDE the locked span is reported once, never retried.

    Cycle 85 (review MINOR) — `atomic_text_write` can itself raise TimeoutError.
    Without an inner handler the outer `except TimeoutError` would treat that as
    lock contention and retry a write that failed for an unrelated reason. This
    pins that the lock is acquired exactly once and the drop is reported.
    """
    import kb.ingest.pipeline as pipeline_mod

    acquisitions: list[float | None] = []
    real_lock = pipeline_mod.file_lock

    @contextlib.contextmanager
    def _counting_lock(path, timeout=None):
        acquisitions.append(timeout)
        with real_lock(path, timeout=timeout):
            yield

    def _explode(_content, _path):
        raise TimeoutError("write-side timeout, NOT lock contention")

    monkeypatch.setattr(pipeline_mod, "file_lock", _counting_lock)
    monkeypatch.setattr(pipeline_mod, "atomic_text_write", _explode)

    with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
        pipeline_mod._persist_contradictions([{"claim": "alpha"}], "raw/articles/src.md", tmp_wiki)

    assert len(acquisitions) == 1, (
        f"a write-side failure must NOT be retried as lock contention; "
        f"lock was acquired {len(acquisitions)} times"
    )
    dropped = [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and "DROPPED" in r.getMessage()
    ]
    assert dropped, "a write-side failure must still report the drop"
    assert "1 contradiction(s)" in dropped[-1]
