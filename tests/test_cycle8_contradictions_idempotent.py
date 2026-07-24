"""Cycle 8 contradiction persistence idempotency coverage."""

from __future__ import annotations

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
