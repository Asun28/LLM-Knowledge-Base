from __future__ import annotations

import importlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def test_augment_package_structure_cycle44() -> None:
    pkg = ROOT / "src" / "kb" / "lint" / "augment"
    assert pkg.is_dir()
    for module in (
        "collector",
        "proposer",
        "fetcher",
        "persister",
        "quality",
        "manifest",
        "rate",
        "orchestrator",
        "__init__",
    ):
        assert (pkg / f"{module}.py").is_file(), f"M2: {module}.py missing"
    assert not (ROOT / "src" / "kb" / "lint" / "augment.py").exists()
    # Cycle 46 — Phase 4.6 LOW closeout: legacy `_augment_*.py` compat shims deleted
    # (deferred from cycle 44 → 45 → 46). Both file presence AND importability are
    # pinned per CONDITION 2 / `feedback_test_behavior_over_signature` / C40-L3 —
    # `is_file()` covers disk state; `pytest.raises(ModuleNotFoundError)` is the
    # behavioural contract. Either failure flags a partial cycle-46 revert.
    assert not (ROOT / "src" / "kb" / "lint" / "_augment_manifest.py").is_file()
    assert not (ROOT / "src" / "kb" / "lint" / "_augment_rate.py").is_file()
    with pytest.raises(ModuleNotFoundError):
        import kb.lint._augment_manifest  # noqa: F401
    with pytest.raises(ModuleNotFoundError):
        import kb.lint._augment_rate  # noqa: F401


def test_augment_package_reexports_match_former_flat_symbols_cycle44() -> None:
    import kb.lint.augment
    from kb.lint.augment import (
        _build_proposer_prompt,
        _format_proposals_md,
        _parse_proposals_md,
        _post_ingest_quality,
        _propose_urls,
        _record_verdict_gap_callout,
        _relevance_score,
        _resolve_raw_dir,
        run_augment,
    )

    assert run_augment is kb.lint.augment.orchestrator.run_augment
    assert _build_proposer_prompt is kb.lint.augment.proposer._build_proposer_prompt
    assert _relevance_score is kb.lint.augment.proposer._relevance_score
    assert _propose_urls is kb.lint.augment.proposer._propose_urls
    assert _format_proposals_md is kb.lint.augment.persister._format_proposals_md
    assert _parse_proposals_md is kb.lint.augment.persister._parse_proposals_md
    assert _post_ingest_quality is kb.lint.augment.quality._post_ingest_quality
    assert _resolve_raw_dir is kb.lint.augment.quality._resolve_raw_dir
    assert _record_verdict_gap_callout is kb.lint.augment.quality._record_verdict_gap_callout


def test_augment_package_imports_with_nonexistent_wiki_dir_cycle44(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("kb.config.WIKI_DIR", tmp_path / "nonexistent" / "wiki")
    import kb.lint.augment.manifest
    import kb.lint.augment.rate

    importlib.reload(kb.lint.augment.manifest)
    importlib.reload(kb.lint.augment.rate)

    assert hasattr(kb.lint.augment.manifest, "Manifest")
    assert hasattr(kb.lint.augment.rate, "RateLimiter")


def test_run_augment_docstring_survives_cycle46_import_flip() -> None:
    """CONDITION 3 forward-protection — `run_augment.__doc__` must keep the
    `"Three-gate"` marker even after the AC3 import flip. Catches any future
    edit that orphans the docstring per cycle-23 L1 (function-local imports
    placed BEFORE the closing triple-quote)."""
    from kb.lint.augment.orchestrator import run_augment

    assert run_augment.__doc__ is not None
    assert "Three-gate" in run_augment.__doc__


# -- Cycle 90 fold from test_v5_lint_augment_manifest.py --
# Manifest state machine per-gap: pending → proposed → fetched → saved → ingested → done.


def _make_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint.augment.manifest.MANIFEST_DIR", tmp_path)
    from kb.lint.augment.manifest import Manifest

    run_id = str(uuid.uuid4())
    stubs = [
        {"page_id": "concepts/foo", "title": "Foo"},
        {"page_id": "entities/bar", "title": "Bar"},
    ]
    return Manifest.start(run_id=run_id, mode="propose", max_gaps=5, stubs=stubs), run_id


def test_start_writes_initial_manifest(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    files = list(tmp_path.glob("augment-run-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["run_id"] == run_id
    assert data["schema"] == 1
    assert data["ended_at"] is None
    assert len(data["gaps"]) == 2
    for gap in data["gaps"]:
        assert gap["state"] == "pending"
        assert gap["transitions"] == [{"state": "pending", "ts": gap["transitions"][0]["ts"]}]


def test_advance_appends_transition(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.advance("concepts/foo", "proposed", payload={"urls": ["https://wikipedia.org/wiki/Foo"]})
    data = json.loads((tmp_path / f"augment-run-{run_id[:8]}.json").read_text())
    foo_gap = next(g for g in data["gaps"] if g["page_id"] == "concepts/foo")
    assert foo_gap["state"] == "proposed"
    assert len(foo_gap["transitions"]) == 2
    assert foo_gap["transitions"][1]["state"] == "proposed"
    assert foo_gap["transitions"][1]["payload"]["urls"] == ["https://wikipedia.org/wiki/Foo"]


def test_advance_to_terminal_state(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.advance("entities/bar", "abstained", payload={"reason": "out of scope"})
    data = json.loads((tmp_path / f"augment-run-{run_id[:8]}.json").read_text())
    bar_gap = next(g for g in data["gaps"] if g["page_id"] == "entities/bar")
    assert bar_gap["state"] == "abstained"


def test_close_writes_ended_at(tmp_path, monkeypatch):
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.close()
    data = json.loads((tmp_path / f"augment-run-{run_id[:8]}.json").read_text())
    assert data["ended_at"] is not None
    # ISO 8601 with Z or +00:00
    assert "T" in data["ended_at"]


def test_resume_finds_incomplete_run(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint.augment.manifest.MANIFEST_DIR", tmp_path)
    from kb.lint.augment.manifest import Manifest

    run_id = "abcd1234-5678-90ab-cdef-1234567890ab"
    initial = {
        "schema": 1,
        "run_id": run_id,
        "started_at": "2026-04-15T14:00:00Z",
        "ended_at": None,
        "mode": "auto_ingest",
        "max_gaps": 5,
        "gaps": [
            {"page_id": "concepts/x", "state": "ingested", "transitions": []},
            {"page_id": "concepts/y", "state": "fetched", "transitions": []},
        ],
    }
    (tmp_path / f"augment-run-{run_id[:8]}.json").write_text(json.dumps(initial))
    m = Manifest.resume(run_id="abcd1234")
    assert m is not None
    assert m.run_id == run_id
    incomplete = m.incomplete_gaps()
    assert {g["page_id"] for g in incomplete} == {"concepts/y"}


def test_resume_returns_none_for_unknown_run(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint.augment.manifest.MANIFEST_DIR", tmp_path)
    from kb.lint.augment.manifest import Manifest

    assert Manifest.resume(run_id="zzzzzzzz") is None


def test_runs_index_is_appended_on_close(tmp_path, monkeypatch):
    # With RUNS_INDEX_PATH derived at call time from MANIFEST_DIR, a single
    # monkeypatch on MANIFEST_DIR is now sufficient — no separate constant
    # to remember. (_make_manifest already patches MANIFEST_DIR.)
    m, run_id = _make_manifest(tmp_path, monkeypatch)
    m.advance("concepts/foo", "done")
    m.advance("entities/bar", "abstained", payload={"reason": "x"})
    m.close()
    lines = (tmp_path / "augment_runs.jsonl").read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["run_id"] == run_id
    assert entry["gaps_succeeded"] == 1  # done
    assert entry["gaps_abstained"] == 1
    assert entry["gaps_failed"] == 0


# -- Cycle 90 fold from test_v5_lint_augment_rate.py --
# Cross-process rate limiter for kb_lint --augment fetches.


def _make_limiter(tmp_path, monkeypatch):
    monkeypatch.setattr("kb.lint.augment.rate.RATE_PATH", tmp_path / "augment_rate.json")
    from kb.lint.augment.rate import RateLimiter

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
    monkeypatch.setattr("kb.lint.augment.rate.RATE_PATH", rate_path)
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
    from kb.lint.augment.rate import RateLimiter

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
    monkeypatch.setattr("kb.lint.augment.rate.RATE_PATH", tmp_path / "augment_rate.json")
    from kb.lint.augment.rate import RateLimiter

    rl_a = RateLimiter()
    rl_b = RateLimiter()  # independent instance, no shared in-memory state

    allowed_a, _ = rl_a.acquire("en.wikipedia.org")
    allowed_b, retry_b = rl_b.acquire("en.wikipedia.org")

    assert allowed_a is True
    assert allowed_b is False, "second acquire must re-read A's write and reject"
    assert retry_b > 0
