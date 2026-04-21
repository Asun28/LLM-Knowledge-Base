"""Cycle 19 AC15/AC16 — MCP monkeypatch migration vacuity tests.

AC15: kb.mcp.core was refactored from `from owner import name` to
`from owner import module` + `module.name(...)` so tests patching the OWNER
module (`kb.ingest.pipeline.ingest_source`, `kb.query.engine.query_wiki`,
`kb.query.engine.search_pages`, `kb.feedback.reliability.compute_trust_scores`)
intercept the MCP tool's call site at call time.

AC16: Constants imported via `from kb.config import X` retain the snapshot-
binding semantic — patching `kb.config.X` does NOT propagate to
`kb.mcp.core.X`. Tests for constants MUST use `monkeypatch.setattr(
"kb.mcp.core.X", ...)` directly.

These tests are the cycle-11 L1 vacuous-gate revert checks for AC15: if a
maintainer reverts `kb.mcp.core` to the legacy `from … import name` style,
each `_owner_module_patch_intercepts_*` test fails because the patch on the
owner module no longer affects the MCP call site.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ────────────────────────────────────────────────────────────────────────────
# AC15 — vacuity tests for the 4 migrated callables
# ────────────────────────────────────────────────────────────────────────────


def test_owner_module_patch_intercepts_ingest_source(tmp_kb_env, monkeypatch) -> None:
    """T-15a — Patching kb.ingest.pipeline.ingest_source intercepts mcp.core.kb_ingest.

    Patches via mcp_core.ingest_pipeline (the module object actually reachable
    from kb.mcp.core) so an earlier importlib.reload(kb.config) in the suite
    cannot leave sys.modules['kb.ingest.pipeline'] pointing at a different
    object than what kb.mcp.core's `ingest_pipeline` reference holds.
    """
    from kb.mcp import core as mcp_core

    raw_path = tmp_kb_env / "raw" / "articles" / "smoke.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text("# Smoke\n", encoding="utf-8")

    sentinel = {
        "source_path": str(raw_path),
        "source_type": "article",
        "content_hash": "abc123",
        "pages_created": [],
        "pages_updated": [],
        "pages_skipped": [],
        "duplicate": False,
        "affected_pages": [],
        "wikilinks_injected": [],
        "contradictions": [],
    }

    fake = MagicMock(return_value=sentinel)
    monkeypatch.setattr(mcp_core.ingest_pipeline, "ingest_source", fake)
    # AC16 — RAW_DIR snapshot lives on kb.mcp.core; patch directly so kb_ingest's
    # path-containment check passes against the tmp_kb_env raw dir. (The earlier
    # importlib.reload(kb.config) by cycle-15 leaves the snapshot stale.)
    monkeypatch.setattr(mcp_core, "RAW_DIR", tmp_kb_env / "raw")
    monkeypatch.setattr(mcp_core, "PROJECT_ROOT", tmp_kb_env)
    mcp_core.kb_ingest(str(raw_path), source_type="article", use_api=True)

    assert fake.called, (
        "kb.mcp.core.kb_ingest must call ingest_source via the owner-module "
        "attribute path so this owner-module patch intercepts it. If it didn't, "
        "the cycle-19 AC15 import refactor was reverted."
    )


def test_owner_module_patch_intercepts_query_wiki(tmp_kb_env, monkeypatch) -> None:
    """T-15b — Patching kb.query.engine.query_wiki intercepts mcp.core.kb_query's API call."""
    from kb.mcp import core as mcp_core

    sentinel = {
        "answer": "smoke",
        "citations": [],
        "source_pages": [],
        "context_pages": [],
    }
    fake = MagicMock(return_value=sentinel)
    with patch("kb.query.engine.query_wiki", fake):
        # use_api=True triggers the path that calls query_engine.query_wiki(...)
        mcp_core.kb_query("test question", use_api=True)
    assert fake.called, "kb.mcp.core.kb_query (use_api) must call query_wiki via owner-module path."


def test_owner_module_patch_intercepts_search_pages(tmp_kb_env, monkeypatch) -> None:
    """T-15c — Patching kb.query.engine.search_pages intercepts the default kb_query path."""
    from kb.mcp import core as mcp_core

    fake = MagicMock(return_value=[])
    with patch("kb.query.engine.search_pages", fake):
        mcp_core.kb_query("test question")  # default path (no use_api)
    assert fake.called, (
        "kb.mcp.core.kb_query (default) must call search_pages via owner-module path."
    )


def test_owner_module_patch_intercepts_compute_trust_scores(tmp_kb_env, monkeypatch) -> None:
    """T-15d — Patching kb.feedback.reliability.compute_trust_scores intercepts kb_query."""
    from kb.mcp import core as mcp_core

    fake = MagicMock(return_value={})
    # Provide a deterministic search_pages result so the trust-score branch runs.
    fake_results = [
        {
            "id": "concepts/test",
            "type": "concept",
            "confidence": "stated",
            "score": 1.0,
            "title": "Test",
            "content": "Content",
            "trust": None,
        }
    ]
    with patch("kb.query.engine.search_pages", return_value=fake_results):
        with patch("kb.feedback.reliability.compute_trust_scores", fake):
            mcp_core.kb_query("test question")
    assert fake.called, "kb.mcp.core.kb_query must call compute_trust_scores via owner-module path."


# ────────────────────────────────────────────────────────────────────────────
# AC16 — snapshot-binding asymmetry for constants
# ────────────────────────────────────────────────────────────────────────────


def test_config_constant_patch_does_not_propagate_to_mcp_core(monkeypatch, tmp_path) -> None:
    """AC16 behavioural — patching kb.config.PROJECT_ROOT does NOT change kb.mcp.core.PROJECT_ROOT.

    Constants imported via `from kb.config import X` capture a snapshot at
    import time. Tests patching `kb.config.X` post-import do not propagate.
    This is the documented asymmetry — tests MUST patch `kb.mcp.core.X`
    directly for constants.
    """
    import kb.config
    from kb.mcp import core as mcp_core

    original_mcp_root = mcp_core.PROJECT_ROOT

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)

    assert mcp_core.PROJECT_ROOT == original_mcp_root, (
        f"kb.mcp.core.PROJECT_ROOT should NOT change when kb.config.PROJECT_ROOT is patched "
        f"(snapshot-binding asymmetry); got mcp_core.PROJECT_ROOT={mcp_core.PROJECT_ROOT!r}, "
        f"original was {original_mcp_root!r}"
    )


def test_mcp_core_constant_patch_does_propagate_to_self(monkeypatch, tmp_path) -> None:
    """AC16 behavioural — patching kb.mcp.core.PROJECT_ROOT DOES change the local binding.

    Confirms that the recommended pattern (patch the local snapshot) works as
    expected; this is the asymmetric counterpart to the test above.
    """
    from kb.mcp import core as mcp_core

    monkeypatch.setattr("kb.mcp.core.PROJECT_ROOT", tmp_path)
    assert mcp_core.PROJECT_ROOT == tmp_path, (
        f"Patching kb.mcp.core.PROJECT_ROOT directly should propagate; "
        f"got {mcp_core.PROJECT_ROOT!r}"
    )


def test_mcp_core_docstring_documents_snapshot_asymmetry() -> None:
    """AC16 docstring gate — module docstring explains the snapshot-binding asymmetry."""
    from kb.mcp import core as mcp_core

    docstring = mcp_core.__doc__ or ""
    assert "snapshot" in docstring.lower(), (
        "kb.mcp.core module docstring must document the snapshot-binding "
        "asymmetry between callables (patch owner module) and constants "
        "(patch local module). See cycle-19 AC16 rationale."
    )
    assert "AC15" in docstring or "owner" in docstring.lower(), (
        "Docstring should reference the AC15 owner-module migration."
    )
