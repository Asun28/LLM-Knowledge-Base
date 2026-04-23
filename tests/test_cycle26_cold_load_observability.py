"""Cycle 26 AC1-AC5 — vector-model cold-load observability.

Pins the new `maybe_warm_load_vector_model` helper, cold-load latency
instrumentation, `_vector_model_cold_loads_seen` counter, and the AC2b
boot-lean invariant that bare `import kb.mcp` does not pull the
embeddings module into `sys.modules`.

Seven named tests per cycle-26 CONDITION 2:
1. test_maybe_warm_load_returns_none_when_vec_path_missing
2. test_maybe_warm_load_returns_thread_when_vec_path_exists
3. test_maybe_warm_load_idempotent_when_model_already_loaded
4. test_cold_load_logs_latency_info_and_warning (CONDITION 4)
5. test_cold_load_counter_increments_per_load
6. test_bare_import_kb_mcp_does_not_load_embeddings_module (Q10a, AC2b)
7. test_warm_load_thread_swallows_exception_and_logs (Q10b, T6)

Per cycle-26 T3 mitigation: every test combining `maybe_warm_load_vector_model`
with `_reset_model` MUST call `thread.join(timeout=5)` between them so the
reset does not block on a still-held `_model_lock`.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from kb.query import embeddings as embeddings_mod

_REPO_SRC = Path(__file__).resolve().parent.parent / "src"


def _seed_vector_db(wiki_dir: Path) -> Path:
    """Create an empty sentinel vec_db file; helper only checks `.exists()`."""
    data_dir = wiki_dir.parent / ".data"
    data_dir.mkdir(parents=True, exist_ok=True)
    vec_path = data_dir / "vector_index.db"
    vec_path.write_bytes(b"")  # empty sentinel — helper only stats .exists()
    return vec_path


def _make_wiki_dir(tmp_path: Path) -> Path:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    return wiki_dir


def test_maybe_warm_load_returns_none_when_vec_path_missing(tmp_path, monkeypatch):
    """AC1 — no vec_db on disk → helper returns None, no thread spawned.

    R1 Sonnet N3 fix — explicitly force `_hybrid_available=True` so the assertion
    exercises the VEC_PATH branch, not the hybrid-unavailable short-circuit.
    Without this monkeypatch the test could pass vacuously on environments
    where `model2vec`/`sqlite-vec` are not installed.
    """
    wiki_dir = _make_wiki_dir(tmp_path)
    monkeypatch.setattr(embeddings_mod, "_hybrid_available", True)
    monkeypatch.setattr(embeddings_mod, "_model", None)

    thread = embeddings_mod.maybe_warm_load_vector_model(wiki_dir)

    assert thread is None, "Expected None when vec_path does not exist"


def test_maybe_warm_load_returns_thread_when_vec_path_exists(tmp_path, monkeypatch):
    """AC1 — vec_db present + `_model is None` + hybrid available → Thread returned."""
    wiki_dir = _make_wiki_dir(tmp_path)
    _seed_vector_db(wiki_dir)

    # Reset singleton + stub StaticModel.from_pretrained with a near-instant
    # return so the thread terminates quickly.
    monkeypatch.setattr(embeddings_mod, "_model", None)

    class _FakeModel:
        def encode(self, texts):
            return []

    class _FakeStaticModel:
        @staticmethod
        def from_pretrained(name, force_download=False):
            return _FakeModel()

    # Patch the module2vec StaticModel symbol resolved inside _get_model.
    import model2vec

    monkeypatch.setattr(model2vec, "StaticModel", _FakeStaticModel)

    thread = embeddings_mod.maybe_warm_load_vector_model(wiki_dir)

    assert thread is not None, "Expected a Thread when vec_path exists + model unset"
    thread.join(timeout=5)
    assert not thread.is_alive(), "Warm-load thread failed to terminate within 5s"
    # The stub installed a fake model singleton.
    assert embeddings_mod._model is not None


def test_maybe_warm_load_idempotent_when_model_already_loaded(tmp_path, monkeypatch):
    """AC1 — `_model` already set → helper returns None even with vec_path present."""
    wiki_dir = _make_wiki_dir(tmp_path)
    _seed_vector_db(wiki_dir)

    sentinel = object()
    monkeypatch.setattr(embeddings_mod, "_model", sentinel)

    thread = embeddings_mod.maybe_warm_load_vector_model(wiki_dir)

    assert thread is None, "Expected None when _model is already set (idempotent no-op)"
    assert embeddings_mod._model is sentinel, "Helper must not replace an existing model"


def test_cold_load_logs_latency_info_and_warning(tmp_path, monkeypatch, caplog):
    """AC3 + CONDITION 3 + CONDITION 4 — cold-load emits INFO + WARNING on 0.5s load.

    Pins the post-success ordering contract via the "logs ONLY after success"
    shape: the monkeypatched stub sleeps 0.5s then returns, so both records
    must appear. If the implementation placed them in `finally:`, an
    exception path would also fire the INFO (separately tested in Test 7
    via exception-swallow).
    """
    monkeypatch.setattr(embeddings_mod, "_model", None)

    def _slow_stub(name, force_download=False):
        import time

        time.sleep(0.5)

        class _M:
            def encode(self, texts):
                return []

        return _M()

    import model2vec

    monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", staticmethod(_slow_stub))

    caplog.set_level(logging.INFO, logger="kb.query.embeddings")
    embeddings_mod._get_model()

    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "cold-loaded in" in r.getMessage()
    ]
    warning_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and "exceeded" in r.getMessage()
        and "threshold" in r.getMessage()
    ]
    all_msgs = [r.getMessage() for r in caplog.records]
    assert info_records, f"Expected INFO 'Vector model cold-loaded in' record; got {all_msgs!r}"
    assert warning_records, (
        f"Expected WARNING 'exceeded ... threshold' record for 0.5s > 0.3s; got {all_msgs!r}"
    )


def test_cold_load_counter_increments_per_load(tmp_path, monkeypatch):
    """AC4 — counter increments once per successful cold-load."""

    def _fast_stub(name, force_download=False):
        class _M:
            def encode(self, texts):
                return []

        return _M()

    import model2vec

    monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", staticmethod(_fast_stub))

    baseline = embeddings_mod.get_vector_model_cold_load_count()

    # Reset + load #1
    monkeypatch.setattr(embeddings_mod, "_model", None)
    embeddings_mod._get_model()
    assert embeddings_mod.get_vector_model_cold_load_count() - baseline == 1

    # Reset + load #2
    monkeypatch.setattr(embeddings_mod, "_model", None)
    embeddings_mod._get_model()
    assert embeddings_mod.get_vector_model_cold_load_count() - baseline == 2


def test_bare_import_kb_mcp_does_not_load_embeddings_module():
    """AC2b / CONDITION 1 (sys.modules probe) — Q10a companion to cycle-23 boot-lean.

    Subprocess isolation so pytest collection state cannot contaminate the probe.
    """
    code = (
        "import json, sys\n"
        "import kb.mcp  # noqa: F401 — bare import\n"
        "print(json.dumps({'loaded': 'kb.query.embeddings' in sys.modules}))\n"
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(_REPO_SRC), os.environ.get("PYTHONPATH", "")]).rstrip(
            os.pathsep
        ),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"Probe failed: {proc.stderr}"
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    result = json.loads(lines[-1])
    assert result["loaded"] is False, (
        "Cycle 26 AC2b contract broken — bare `import kb.mcp` pulled "
        "kb.query.embeddings into sys.modules"
    )


def test_cold_load_exception_suppresses_info_log_and_counter(tmp_path, monkeypatch, caplog):
    """R1 Sonnet M1 fix — CONDITION 3 post-success ordering divergent-fail.

    Test 4 exercises the success path (0.5s stub returns); Test 7 monkeypatches
    `_get_model` at the top level so the body is never entered — neither catches
    a future `finally:` regression that would fire INFO/counter on exceptions.

    This test patches `StaticModel.from_pretrained` (not `_get_model`) to RAISE
    a known exception; the body of `_get_model` IS entered; a `finally:` block
    around the log + increment would fire. Under the correct post-success
    ordering, no INFO record appears and the counter does not advance.
    Revert to `finally:` flips both assertions.
    """
    monkeypatch.setattr(embeddings_mod, "_model", None)

    def _raising_stub(name, force_download=False):
        raise RuntimeError("simulated HF-Hub failure in from_pretrained")

    import model2vec

    monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", staticmethod(_raising_stub))

    caplog.set_level(logging.INFO, logger="kb.query.embeddings")
    baseline = embeddings_mod.get_vector_model_cold_load_count()

    import pytest

    with pytest.raises(RuntimeError, match="simulated HF-Hub failure"):
        embeddings_mod._get_model()

    # Post-success ordering contract: on exception, no INFO/WARNING log fires,
    # counter stays at baseline, `_model` remains None.
    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "cold-loaded in" in r.getMessage()
    ]
    assert not info_records, (
        "CONDITION 3 violated: INFO 'cold-loaded in' record fired on exception path. "
        f"Records: {[r.getMessage() for r in caplog.records]!r}"
    )
    delta = embeddings_mod.get_vector_model_cold_load_count() - baseline
    assert delta == 0, (
        f"CONDITION 3 violated: counter advanced by {delta} on exception path; expected 0"
    )
    assert embeddings_mod._model is None, (
        "Post-exception invariant: _model must stay None so next query re-attempts"
    )


def test_warm_load_thread_swallows_exception_and_logs(tmp_path, monkeypatch, caplog):
    """AC1 / Q2 / CONDITION 10 / T6 — daemon thread catches + logs on failure."""
    wiki_dir = _make_wiki_dir(tmp_path)
    _seed_vector_db(wiki_dir)

    monkeypatch.setattr(embeddings_mod, "_model", None)

    def _raising_get_model():
        raise RuntimeError("simulated HF-Hub failure")

    monkeypatch.setattr(embeddings_mod, "_get_model", _raising_get_model)

    # `logger.exception` is ERROR-level by default; caplog WARNING threshold
    # captures it, but set ERROR explicitly so the test is independent of the
    # default root threshold.
    caplog.set_level(logging.ERROR, logger="kb.query.embeddings")

    thread = embeddings_mod.maybe_warm_load_vector_model(wiki_dir)
    assert thread is not None, "Expected a Thread to be spawned"
    thread.join(timeout=5)
    assert not thread.is_alive(), "Warm-load thread must terminate even on exception"

    error_records = [
        r
        for r in caplog.records
        if r.levelno == logging.ERROR and "Warm-load thread failed" in r.getMessage()
    ]
    all_msgs = [r.getMessage() for r in caplog.records]
    assert error_records, f"Expected ERROR record naming Warm-load failure; got {all_msgs!r}"
    # The exception info should include the RuntimeError message.
    assert any("simulated HF-Hub failure" in str(r.exc_info) for r in error_records), (
        "Expected RuntimeError details in the logger.exception record"
    )
