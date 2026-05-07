"""Cycle 67 AC06 — `KB_DISABLE_VECTORS=1` runtime kill-switch for hybrid search.

Phase 4.5 MEDIUM: hybrid search is opt-in via the `[hybrid]` extra (cycle 34
AC19), but there is no runtime env toggle to disable it without uninstalling
the extra. Operators wanting to A/B-test BM25-only vs hybrid mid-process,
or to disable vectors after a sqlite-vec extension load failure, had no
ergonomic switch.

Cycle 67 AC06 adds `KB_DISABLE_VECTORS` (call-time read per cycle-19 L2):
- env unset / falsy → vector branch invoked (default; back-compat)
- env in {1, true, yes} → vector branch skipped, BM25-only fallback

Truthiness convention symmetric with AC04 `KB_STRICT_PUBLISH` per design
FW-3 / R1-C3 / C-AC04-truthy / C-AC06-truthy.
"""

from __future__ import annotations

import pytest

from kb.query.hybrid import _vectors_disabled_at_runtime, hybrid_search


def _make_bm25_stub(results: list[dict]):
    """Return a callable matching `bm25_fn` signature."""
    calls = {"count": 0}

    def _stub(query, limit):
        calls["count"] += 1
        return results[:limit]

    _stub.calls = calls  # type: ignore[attr-defined]
    return _stub


def _make_vector_stub(results: list[dict]):
    """Return a callable matching `vector_fn` signature with call counter."""
    calls = {"count": 0}

    def _stub(query, limit):
        calls["count"] += 1
        return results[:limit]

    _stub.calls = calls  # type: ignore[attr-defined]
    return _stub


def test_t06a_default_invokes_vector_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T06-A: env unset → vector_fn IS invoked alongside bm25_fn."""
    monkeypatch.delenv("KB_DISABLE_VECTORS", raising=False)
    bm25_stub = _make_bm25_stub([{"id": "p1", "score": 0.9}])
    vector_stub = _make_vector_stub([{"id": "p2", "score": 0.8}])
    results = hybrid_search(
        "test query",
        bm25_fn=bm25_stub,
        vector_fn=vector_stub,
        limit=5,
    )
    assert bm25_stub.calls["count"] == 1, "bm25_fn should be called once"
    assert vector_stub.calls["count"] == 1, (
        "vector_fn MUST be called when KB_DISABLE_VECTORS is unset (default)"
    )
    assert results, "hybrid search should return fused results"


def test_t06b_kill_switch_skips_vector_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T06-B: env=`"1"` → vector_fn is NOT called; results contain only
    BM25 hits."""
    monkeypatch.setenv("KB_DISABLE_VECTORS", "1")
    bm25_stub = _make_bm25_stub([{"id": "p1", "score": 0.9}])
    vector_stub = _make_vector_stub([{"id": "p2", "score": 0.8}])
    results = hybrid_search(
        "test query",
        bm25_fn=bm25_stub,
        vector_fn=vector_stub,
        limit=5,
    )
    assert bm25_stub.calls["count"] == 1
    assert vector_stub.calls["count"] == 0, (
        "AC06 T06-B: vector_fn MUST NOT be called when KB_DISABLE_VECTORS=1. "
        f"Got {vector_stub.calls['count']} call(s)."
    )
    result_ids = {r["id"] for r in results}
    assert "p1" in result_ids
    assert "p2" not in result_ids, "p2 came from vector branch which should be skipped"


def test_t06c_call_time_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """T06-C: env var read at CALL time. Setting it after the first call
    mutates behavior on the second call WITHOUT process restart.
    """
    bm25_stub = _make_bm25_stub([{"id": "p1", "score": 0.9}])
    vector_stub = _make_vector_stub([{"id": "p2", "score": 0.8}])

    monkeypatch.delenv("KB_DISABLE_VECTORS", raising=False)
    hybrid_search("first", bm25_fn=bm25_stub, vector_fn=vector_stub, limit=5)
    first_vec_count = vector_stub.calls["count"]
    assert first_vec_count >= 1

    monkeypatch.setenv("KB_DISABLE_VECTORS", "1")
    hybrid_search("second", bm25_fn=bm25_stub, vector_fn=vector_stub, limit=5)
    second_vec_count = vector_stub.calls["count"]
    assert second_vec_count == first_vec_count, (
        "AC06 T06-C: vector_fn call count MUST NOT increase after env=1 is set "
        f"mid-process. before={first_vec_count}, after={second_vec_count}"
    )


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "TRUE", "Yes", "  yes  "])
def test_t06d_truthy_variants_disable_vectors(
    truthy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T06-D: truthiness convention symmetric with AC04. Each of {1, true,
    yes} (case-insensitive, whitespace-tolerant) disables vectors.
    """
    monkeypatch.setenv("KB_DISABLE_VECTORS", truthy)
    assert _vectors_disabled_at_runtime() is True, (
        f"AC06 T06-D: env={truthy!r} should be recognized as truthy"
    )


@pytest.mark.parametrize("falsy", ["0", "false", "no", "", "anything-else"])
def test_t06d_falsy_variants_enable_vectors(
    falsy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T06-D inverse: falsy / unrecognized values keep default behavior."""
    monkeypatch.setenv("KB_DISABLE_VECTORS", falsy)
    assert _vectors_disabled_at_runtime() is False, (
        f"AC06 T06-D: env={falsy!r} should NOT be recognized as truthy"
    )


def test_t06e_divergent_fail_revert_breaks_killswitch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Divergent-fail: pin the production code path. If a future maintainer
    reverts AC06, vector_fn would still be called even with env=1. We
    explicitly assert the call-count contract.
    """
    monkeypatch.setenv("KB_DISABLE_VECTORS", "yes")
    bm25_stub = _make_bm25_stub([])
    vector_stub = _make_vector_stub([{"id": "v1", "score": 1.0}])
    hybrid_search("q", bm25_fn=bm25_stub, vector_fn=vector_stub, limit=5)
    assert vector_stub.calls["count"] == 0, (
        "AC06 divergent-fail: vector_fn was called despite KB_DISABLE_VECTORS=yes. "
        "Production AC06 has been reverted or the kill-switch wiring is broken."
    )
