# Cycle 23 — Requirements + Acceptance Criteria

**Date:** 2026-04-23
**Branch target:** `feat/backlog-by-file-cycle23`
**Scope driver:** `/feature-dev` user prompt — "group work as many as backlog fix items (before Phase 5 items)". Interpreted as Phase 4.5 HIGH + MEDIUM items that are tractable in one cycle.

---

## Problem

Three Phase 4.5 concerns remain after cycle 22:

1. **MCP server boot latency** (Phase 4.5 HIGH, BACKLOG line 101-102). `kb mcp` startup measured at 1.83s / +89 MB / 2,433 modules; ~0.8s / ~35 MB is unnecessary for read-only tool sessions. Root cause: `kb.mcp.__init__` eagerly imports `core, browse, health, quality` which transitively pull `anthropic`, `networkx`, and `sentence-transformers`. Cycle-17 AC4 deferred `kb.capture` only; the "defer `kb.query.engine`, `kb.ingest.pipeline`, `kb.graph.export`" items remain open. **Constraint:** cycle-19 AC15 established that `kb.mcp.core.<module>` MUST remain reachable as an attribute for robust monkeypatching under `importlib.reload` chains (cycle-19 L2 reload-leak). Naive function-body deferral breaks `tests/test_cycle19_mcp_monkeypatch_migration.py:57` which does `monkeypatch.setattr(mcp_core.ingest_pipeline, "ingest_source", fake)`. The fix must preserve module-attribute reachability.

2. **`compile_wiki(incremental=False)` opacity** (Phase 4.5 HIGH, BACKLOG line 86-87). The `--full` flag rescans sources but the docstring does not document what is NOT invalidated: manifest deletion-prune (runs only in `detect_source_drift`), vector index (rebuilt per-ingest, not bulk), in-process LRU caches. No CLI affordance exists to wipe these for a clean rebuild.

3. **End-to-end and cross-process test coverage** (Phase 4.5 HIGH tests cluster + HIGH-Deferred multiprocessing). Current tests cover single-module behavior; no test chains `ingest_source` → `query_wiki` → `run_all_checks` against the same `tmp_project`. The `@pytest.mark.integration` multiprocessing file-lock test (Phase 4.5 HIGH-Deferred) was parked pending a dedicated cycle — Windows NTFS lock semantics are not exercised today (threading-only).

## Non-goals

- **Not** rewriting `kb.mcp.core` import structure beyond the PEP-562 lazy-shim (cycle-8 pattern). Test-contract preservation is load-bearing.
- **Not** solving the full state-store fan-out (Phase 4.5 HIGH lines 82-85 receipt file) — architectural, out of scope for one cycle.
- **Not** splitting `config.py` god-module or doing CLI↔MCP parity auto-generation.
- **Not** introducing pytest-snapshot/syrupy golden-file infrastructure.
- **Not** touching the Phase 5 pre-merge CRITICAL capture.py two-pass architecture (out of "before Phase 5" scope).
- **Not** changing the 28-MCP-tool surface area (no new tools, no renames).

## Acceptance Criteria (8 total)

### Group A — compile `--full` transparency (3 ACs)

- **AC1** `src/kb/compile/compiler.py::compile_wiki` docstring explicitly enumerates what `incremental=False` does NOT invalidate: (a) manifest deletion-prune (only runs via `detect_source_drift`), (b) vector index (rebuilt incrementally inside `ingest_source`, not bulk-wiped), (c) in-process LRU caches on `kb.ingest.extractors` / `kb.utils.pages`. Pointer to `rebuild_indexes()` helper. Blast radius: docstring only.
  - Test: `tests/test_cycle23_compile_full_docstring.py::test_compile_wiki_documents_full_scope` — asserts docstring contains `"manifest"`, `"vector"`, `"LRU"` sentinels + pointer to `rebuild_indexes`. This is **a string-grep test of documentation content (allowed because the assertion class is "docstring says X", not "code does X")**. Rationale: cycle-11 L1 bans source-scan string-grep for PRODUCTION BEHAVIOR claims; docstring-content is different because the docstring IS the artifact under test.

- **AC2** `src/kb/compile/compiler.py` exports `rebuild_indexes(wiki_dir=None, *, hash_manifest=None, vector_db=None) -> dict` helper that: (a) unlinks `HASH_MANIFEST` if present, (b) unlinks `vector_index.db` under `wiki_dir` parent `.data` dir if present, (c) clears `kb.ingest.extractors._build_schema_cached.cache_clear()` (and any other LRU caches that pre-exist), (d) returns `{"manifest_cleared": bool, "vector_cleared": bool, "caches_cleared": list[str]}`. Failure-mode: all file unlinks wrapped in `try/except OSError` so a stale lock on one file does not prevent clearing others; returns per-path status. Uses `atomic_text_write` semantics only via deletion (no rewrite). Blast radius: `kb.compile.compiler` — new public helper.

- **AC3** `src/kb/cli.py` — `kb rebuild-indexes [--wiki-dir PATH]` subcommand. Invokes `rebuild_indexes()`, prints per-result summary line, exit code 0 on success (even if nothing to clear). Blast radius: new CLI command; no existing command touched.
  - Test: `tests/test_cycle23_compile_full_docstring.py::test_rebuild_indexes_cli` — CliRunner invocation + assertion on manifest/vector DB file removal + LRU-cache cleared counter.

### Group B — MCP boot latency (2 ACs)

- **AC4** `src/kb/mcp/core.py` — migrate `kb.query.engine`, `kb.ingest.pipeline`, `kb.feedback.reliability` from module-level `from ... import ... as X` to **PEP 562 module-level `__getattr__` lazy-shim** (cycle-8 pattern). After migration:
  - Bare `import kb.mcp` does NOT trigger import of `anthropic`, `networkx`, `sentence_transformers`.
  - First attribute access to `kb.mcp.core.ingest_pipeline` / `.query_engine` / `.reliability` triggers `importlib.import_module(...)`, caches in `globals()`, returns the module.
  - Subsequent accesses return the cached reference (no repeat load).
  - Tests that do `monkeypatch.setattr(mcp_core.ingest_pipeline, "ingest_source", fake)` continue to work because `.ingest_pipeline` access resolves to the module object.
  - Inside tool bodies, references like `ingest_pipeline.ingest_source(...)` work unchanged (they go through module `__getattr__` the first time).
  - Blast radius: `kb.mcp.core` only. No tool signatures change. No test monkeypatch migration needed (cycle-19 AC15 already routes everything through owner modules).

- **AC5** Regression test `tests/test_cycle23_mcp_boot_lean.py` — spawns a subprocess with `python -c "import kb.mcp; ..."` (subprocess to get a fresh module graph, not the pytest one polluted by prior imports), asserts:
  - Post-`import kb.mcp`, `sys.modules` does NOT contain `anthropic`, `networkx`, `sentence_transformers`, `kb.query.engine`, `kb.ingest.pipeline`, `kb.feedback.reliability`.
  - Post-`from kb.mcp.core import ingest_pipeline; ingest_pipeline.ingest_source`, `sys.modules` DOES contain `kb.ingest.pipeline`.
  - Cycle-19 AC15 contract still holds: `kb.mcp.core.ingest_pipeline is kb.ingest.pipeline`.
  - Test uses `sys.executable` + `env={**os.environ, "PYTHONPATH": <repo>/src}` per cycle-7 subprocess `sys.path` footgun.

### Group C — End-to-end + cross-process coverage (2 ACs)

- **AC6** `tests/test_cycle23_workflow_e2e.py` — hermetic end-to-end workflow test with the synthesis LLM stubbed:
  - Seeds `tmp_project` with two raw articles under `raw/articles/`.
  - Calls `ingest_source` with `extraction={...}` (skip LLM extraction) for both.
  - Asserts `pages_created` / `pages_updated` / `wikilinks_injected` shape per ingest.
  - Calls `query_wiki` with `conversation_context=None` and `call_llm` stubbed at `kb.query.engine.call_llm` to return a canned answer referencing `[source: raw/articles/foo.md]`.
  - Asserts returned `citations` list shape + `source_pages` includes both entity pages.
  - Calls `run_all_checks` on the same `tmp_wiki`; asserts `lint_report["summary"]["error"] == 0`.
  - Runs in < 3 seconds; no real LLM calls; no real HTTP.
  - Blast radius: new test file, no production code changes.

- **AC7** `tests/test_cycle23_file_lock_multiprocessing.py` — `@pytest.mark.integration` cross-process `file_lock` test:
  - Parent spawns a `multiprocessing.Process` that acquires `file_lock(<path>)`, writes its PID to a sentinel file, and sleeps holding the lock.
  - Parent polls the sentinel file to confirm child has the lock.
  - Parent attempts `file_lock(<path>, timeout=0.5)` → expects timeout / busy return or `LockError`.
  - Parent signals child to release, joins, then re-attempts lock → succeeds.
  - Skips on `sys.platform == "win32"` if `mp.get_start_method()` does not support "spawn" cleanly (PID file fallback).
  - Blast radius: new test file.

### Group D — Docs + backlog cleanup (1 AC)

- **AC8** Doc sync: `CLAUDE.md` update (test count + module map if shifted), `CHANGELOG.md` + `CHANGELOG-history.md` entries, `BACKLOG.md` delete the 4 items this cycle resolves (lines 101-109 MCP boot, line 86-87 `--full` opacity, tests E2E workflow, tests multiprocessing-Deferred), leave the 3 MCP-tools async-def item (line 107-108) — it requires a dedicated async-migration cycle. Plus README update if the `kb rebuild-indexes` subcommand is user-facing (it is — new CLI command).

## Blast radius

**Touched files:**
- `src/kb/compile/compiler.py` — docstring + new `rebuild_indexes()` helper (AC1, AC2)
- `src/kb/cli.py` — new subcommand (AC3)
- `src/kb/mcp/core.py` — PEP-562 lazy shim migration (AC4)
- `tests/test_cycle23_compile_full_docstring.py` — new (AC1, AC3)
- `tests/test_cycle23_mcp_boot_lean.py` — new (AC5)
- `tests/test_cycle23_workflow_e2e.py` — new (AC6)
- `tests/test_cycle23_file_lock_multiprocessing.py` — new (AC7)
- `CLAUDE.md`, `CHANGELOG.md`, `CHANGELOG-history.md`, `BACKLOG.md`, `README.md` — doc updates (AC8)

**Not touched:**
- `kb.ingest.*`, `kb.query.*` implementation — no behavior changes.
- MCP tool surface (28 tools) — no additions, no renames.
- Any test that monkeypatches `kb.ingest.pipeline.X` / `kb.query.engine.X` — PEP 562 preserves attribute reachability.

## Cycle-specific lessons applied

- **Cycle-17 L1** (monkeypatch-target enumeration): grepped reference-form + string-form sites. `rewrite_query` has 4 reference-form sites on `kb.mcp.core` → intentionally NOT deferred (keeps module-level import). `query_engine`, `ingest_pipeline`, `reliability`, `compute_trust_scores` are already migrated to owner-module patching by cycle-19 AC15 → safe to defer via PEP 562.
- **Cycle-19 L2** (reload-leak on module-top file reads): not applicable here — PEP 562 `__getattr__` loads on attribute access, which already bypasses the reload-stale-snapshot class.
- **Cycle-22 L1** (Windows pip-audit + bash /tmp): using `.data/cycle-23/` project-relative paths for baselines, and `pip-audit` against installed venv (no `-r requirements.txt`).
- **Cycle-22 L3** (full-suite vs isolation): Step 10 will run full `pytest` + `ruff check` + `ruff format --check` as the gate.
- **Cycle-22 L5** (design-gate CONDITIONS are load-bearing): any CONDITIONS emitted by Step 5 gate will map to explicit test assertions in Step 9.
- **Cycle-14 L1** (primary-session plan drafting): 8 ACs + operator holds full Step 1-5 context → plan will be drafted in primary.
- **Cycle-13 L2** (sizing heuristic): each AC is < 30 LOC code + < 100 LOC tests with stdlib-only APIs → primary-session TDD execution, not Codex dispatch for Step 9.
- **Cycle-8 L1** (`sys.argv --version` short-circuit): `rebuild_indexes` CLI subcommand must not affect the `kb --version` fast path — verify via subprocess test.
