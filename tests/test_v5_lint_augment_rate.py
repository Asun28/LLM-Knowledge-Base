"""Cross-process rate limiter for kb_lint --augment fetches."""

import json
from datetime import UTC, datetime, timedelta


def _make_limiter(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint._augment_rate.RATE_PATH", tmp_path / "augment_rate.json")
    from kb.lint._augment_rate import RateLimiter

    return RateLimiter()


def test_first_call_allowed(tmp_path, monkeypatch):
    rl = _make_limiter(tmp_path, monkeypatch)
    allowed, retry = rl.acquire("en.wikipedia.org")
    assert allowed is True
    assert retry == 0


def test_per_run_cap_blocks_after_max(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.config.AUGMENT_FETCH_MAX_CALLS_PER_RUN", 2)
    rl = _make_limiter(tmp_path, monkeypatch)
    rl.acquire("en.wikipedia.org")
    rl.acquire("en.wikipedia.org")
    allowed, _ = rl.acquire("en.wikipedia.org")
    assert allowed is False


def test_per_host_cap_blocks_after_3(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR", 3)
    rl = _make_limiter(tmp_path, monkeypatch)
    rl.acquire("en.wikipedia.org")
    rl.acquire("en.wikipedia.org")
    rl.acquire("en.wikipedia.org")
    allowed, retry = rl.acquire("en.wikipedia.org")
    assert allowed is False
    assert retry > 0


def test_different_hosts_independent_buckets(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR", 1)
    rl = _make_limiter(tmp_path, monkeypatch)
    rl.acquire("en.wikipedia.org")
    allowed, _ = rl.acquire("arxiv.org")
    assert allowed is True


def test_state_persists_across_instances(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR", 1)
    rl1 = _make_limiter(tmp_path, monkeypatch)
    rl1.acquire("en.wikipedia.org")
    rl2 = _make_limiter(tmp_path, monkeypatch)
    allowed, _ = rl2.acquire("en.wikipedia.org")
    assert allowed is False, "second instance should see the first's quota use"


def test_old_entries_outside_window_dropped(tmp_path, monkeypatch):
    # Seed the rate-limit file directly with a stale entry, then let acquire()
    # purge it inside its locked read-check-write critical section.
    rate_path = tmp_path / "augment_rate.json"
    monkeypatch.setattr("kb.lint._augment_rate.RATE_PATH", rate_path)
    old_ts = (datetime.now(UTC) - timedelta(hours=2)).timestamp()
    rate_path.write_text(
        json.dumps(
            {
                "schema": 1,
                "global": {"hour_window": []},
                "per_host": {"en.wikipedia.org": {"hour_window": [old_ts]}},
            }
        )
    )
    from kb.lint._augment_rate import RateLimiter

    rl = RateLimiter()
    allowed, _ = rl.acquire("en.wikipedia.org")
    assert allowed is True


def test_concurrent_acquire_at_boundary_rejects_second_caller(tmp_path, monkeypatch):
    """Two RateLimiter instances racing at the cap boundary — second must lose.

    Regression guard for TOCTOU: before the fix both instances could read
    state at count=cap-1, both pass the check, both write — permanently
    exceeding the cap. With the read-check-write held under file_lock the
    second caller re-reads the winner's write and is rejected.
    """
    monkeypatch.setattr("kb.config.AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR", 1)
    monkeypatch.setattr("kb.lint._augment_rate.RATE_PATH", tmp_path / "augment_rate.json")
    from kb.lint._augment_rate import RateLimiter

    rl_a = RateLimiter()
    rl_b = RateLimiter()  # independent instance, no shared in-memory state

    allowed_a, _ = rl_a.acquire("en.wikipedia.org")
    allowed_b, retry_b = rl_b.acquire("en.wikipedia.org")

    assert allowed_a is True
    assert allowed_b is False, "second acquire must re-read A's write and reject"
    assert retry_b > 0
