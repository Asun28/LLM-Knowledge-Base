# Cycle 17 — Requirements & Acceptance Criteria

**Date:** 2026-04-20
**Cycle:** 17 (backlog-by-file)
**Branch:** `feat/backlog-by-file-cycle17`

## Problem

Phase 4.5 HIGH / MEDIUM backlog has ~40 open items after cycle 16. Architectural HIGH items (11-stage ingest atomicity, per-page locking across stages, compile two-phase refactor, sync→async MCP) are too large for a batch-by-file cycle and remain deferred. Cycle 17 targets tractable HIGH / MEDIUM items grouped by file (per user preference `feedback_batch_by_file`) plus the one open Phase 5 capture CRITICAL item (two-pass slug reservation).

## Non-goals

- **NOT** refactoring `compile_wiki` into a true two-phase pipeline (HIGH, architectural — dedicated cycle).
- **NOT** introducing per-page file locks across the 11-stage ingest pipeline (HIGH, architectural).
- **NOT** implementing `refine_page` two-phase audit write (HIGH Deferred per BACKLOG).
- **NOT** vector-index lifecycle overhaul (HIGH Deferred bundle).
- **NOT** making MCP tools `async def` (HIGH, architectural — dedicated cycle).
- **NOT** splitting `config.py` into `config/*.py` subpackage (MEDIUM but large-blast-radius — dedicated cycle).
- **NOT** adding `kb search` CLI subcommand (new Phase 5 feature, not a bugfix).
- **NOT** introducing `syrupy` / `pytest-snapshot` golden tests (MEDIUM — requires dep + fixture conversion; dedicated cycle).

## Acceptance criteria (21 ACs across 14 files)

### Theme A — `compile/compiler.py` manifest consistency (3 ACs)

- **AC1** (HIGH, BACKLOG §HIGH "compile_wiki:367-380"): Full-mode prune base uses `raw_dir.resolve().parent` to match `_canonical_rel_path`'s base. Current code at line 431 (`not (raw_dir.parent / k).exists()`) breaks when `raw_dir` is passed as a relative path, producing false-positive prunes of all manifest entries.
  - Pass/fail: `test_cycle17_compile_prune_base.py` passes relative `raw_dir`, confirms manifest survives full-mode compile without spurious pruning.

- **AC2** (HIGH regression pin, BACKLOG §HIGH "compile_wiki:343-347"): Add regression test asserting `make_source_ref(src, raw_dir)` == `_canonical_rel_path(src, raw_dir)` for default + relative + absolute `raw_dir`. BACKLOG item reports a historical double-write divergence; success-path double-write has since been removed, but the normalization-contract invariant is not pinned. Test closes the drift door.
  - Pass/fail: new test fails if the two functions ever emit different strings for the same input.

- **AC3** (HIGH atomicity, BACKLOG §HIGH "compile_wiki:367-380"): Wrap the full-mode tail "reload + prune + save" block in `file_lock(manifest_path)` to match the per-source reload-save convention used elsewhere in the codebase. A concurrent `kb_ingest` during compile-finalize can currently have its manifest entry deleted by the prune pass.
  - Pass/fail: unit test with `threading.Thread` performing manifest write during compile-finalize asserts both writes survive.

### Theme B — MCP cold-boot lazy imports (4 ACs, 4 files)

- **AC4** (HIGH, BACKLOG §HIGH "mcp/__init__.py:4 + mcp_server.py:10"): `mcp/core.py` defers `from kb.query.engine import ...` and `from kb.ingest.pipeline import ...` into tool-body function-local imports. Module-level imports limited to `kb.config`, `kb.mcp.app`, `kb.utils.*`, stdlib. Pattern already used for `feedback` + `compile` — extend to remaining heavy imports.
  - Pass/fail: `tests/test_mcp_lazy_imports.py` asserts `import kb.mcp.core` does NOT bring `anthropic`, `kb.query.engine`, `kb.ingest.pipeline` into `sys.modules`.

- **AC5** (HIGH): `mcp/browse.py` — same defer-to-tool-body treatment for `kb.query.engine` + any heavy import touching `kb.ingest.pipeline` or `kb.graph.export`.
  - Pass/fail: same import-absence assertion as AC4 applied to `kb.mcp.browse`.

- **AC6** (HIGH): `mcp/health.py` — defer `kb.graph.export`, `kb.compile.compiler`, `kb.lint.runner`. Already partial; complete coverage.
  - Pass/fail: `networkx` NOT loaded by `import kb.mcp.health`.

- **AC7** (HIGH): `mcp/quality.py` — defer `kb.review.refiner`, `kb.lint.augment`, `kb.lint.checks` to tool-body imports.
  - Pass/fail: `trafilatura` (pulled transitively by `lint.augment`) NOT loaded by `import kb.mcp.quality`.

### Theme C — Dead code (1 AC)

- **AC8** (MEDIUM, BACKLOG §MEDIUM "models/page.py dataclasses are dead"): `WikiPage` / `RawSource` dataclasses have zero production-code readers; tests/cycle8 pinned their signatures. Decision gate picks (a) delete + remove from `kb.models.__all__` + migrate `test_cycle8_models_validation.py` to assert "deleted as dead code" OR (b) document as contract types with `# dataclass: Phase-5 migration target — production still uses dicts` module-level comment. Leaning (b) — tests already pin, removing risks test-breakage cascade.
  - Pass/fail: production code audit grep confirms 0 non-test callers; documented decision lives in module docstring.

### Theme D — Capture refinements (2 ACs)

- **AC9** (MEDIUM, BACKLOG §MEDIUM Phase-5-pre-merge "capture.py:209-238"): `capture.py::_PROMPT_TEMPLATE` — move from module-level string to `templates/capture_prompt.txt` loaded via `Path.read_text()` at module init; document that `.txt` is distinct from YAML JSON-schema templates in `templates/*.yaml`.
  - Pass/fail: `_PROMPT_TEMPLATE` constant replaced by a loader; test asserts equivalent rendering.

- **AC10** (CRITICAL, BACKLOG §CRITICAL "capture.py:341-372, 428-460"): `capture.py::_write_item_files` two-pass architecture — Pass 1: `O_EXCL`-reserve all N slugs with Phase-C retry; Pass 2: compute `alongside_for` from finalized slugs, write all files. Current code freezes `alongside_for` from Phase-A slugs and never recomputes after Phase-C reassignment, leaving cross-process-collision writers with `captured_alongside` entries pointing at non-existent slugs.
  - Pass/fail: two concurrent capture runs under a fake-collision monkeypatch produce valid `captured_alongside` lists matching finalized slugs.

### Theme E — Lint augment resume wiring (3 ACs, 3 files)

- **AC11** (MEDIUM, BACKLOG §MEDIUM Phase-5-pre-merge "lint/augment.py run_augment resume"): `lint/augment.py::run_augment` — re-add `resume: str | None = None` kwarg; at entry, call `Manifest.resume(run_id_prefix=resume)` when non-None; skip Phase A and restart iteration from `manifest.incomplete_gaps()`.
  - Pass/fail: test writes a partial manifest, then invokes `run_augment(resume=<run_id_prefix>)` and asserts Phase A was skipped (no new proposals written) and only incomplete gaps ran.

- **AC12** (MEDIUM): `cli.py lint` — new `--resume <id>` Click option forwarding to `run_augment(resume=id)`. Validates `<id>` matches the expected run-ID regex (alnum + hyphens, bounded length) to prevent path-traversal into `.data/augment/<id>/`.
  - Pass/fail: CLI help output includes `--resume`; invalid IDs rejected with user-visible error string.

- **AC13** (MEDIUM): `mcp/health.py::kb_lint(resume: str = "")` — new MCP parameter forwarded to `run_augment`. Empty-string sentinel = no resume (matches MCP stringiness). Same run-ID validation as AC12.
  - Pass/fail: MCP call with `resume="<valid-id>"` forwards; `resume="../etc"` returns `"Error: ..."` string.

### Theme F — Test infrastructure (5 ACs)

- **AC14** (HIGH, BACKLOG §HIGH "tests/test_v0p5_purpose.py purpose-threading"): Add integration test that creates `wiki/purpose.md` under `tmp_wiki`, calls `query_wiki(question, wiki_dir=tmp)`, monkeypatches `call_llm`, asserts purpose text threads into synthesis prompt. Cycle-6 added rewriter-side test; this closes the query-side gap.
  - Pass/fail: spy `call_llm` captures prompt; assertion `"<kb_purpose>" in prompt` AND `<purpose.md content>` substring present.

- **AC15** (HIGH, BACKLOG §HIGH "tests/ no end-to-end workflow"): `tests/test_workflow_e2e.py` (NEW) — 3-scenario multi-step test: (a) ingest article → `query_wiki` returns the created entity page; (b) ingest → `refine_page` → re-query returns refined content; (c) ingest 2 articles with shared entity → backlinks merged, `source:` list contains both refs. `call_llm` / `call_llm_json` mocked at the boundary; uses `tmp_project` fixture; marked `@pytest.mark.integration`.
  - Pass/fail: 3 test functions pass end-to-end without real API calls.

- **AC16** (HIGH, BACKLOG §HIGH "tests/conftest.py leak surface"): `tests/conftest.py` — add OPT-IN `_kb_sandbox` fixture that monkeypatches `kb.config.{WIKI_DIR, WIKI_CONTRADICTIONS, WIKI_LOG, RAW_DIR, HASH_MANIFEST, PROJECT_ROOT}` to `tmp_path` subdirs. Documented with usage notes in module docstring. **Opt-in**, not autouse, because flipping the default would cascade-break ~2000 existing tests; phase-in migration begins with opt-in + one demo usage in `test_workflow_e2e.py`.
  - Pass/fail: fixture callable; test using it can assert `kb.config.WIKI_DIR` == `tmp_path / "wiki"`; non-using tests unaffected.

- **AC17** (MEDIUM, BACKLOG §MEDIUM "tests/ thin MCP tool coverage"): `tests/test_mcp_tool_coverage.py` (NEW) — per-tool minimum coverage for 5 thin-coverage MCP tools (`kb_stats`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`, `kb_compile_scan`): happy path + validation error + missing-file branch. Autogenerable skeleton; ~15 test functions total.
  - Pass/fail: 15 tests (5 tools × 3 scenarios) pass.

- **AC18** (HIGH): `tests/test_v0p5_purpose.py` — regression test pinning `load_purpose(wiki_dir=tmp)` returning content from `tmp/purpose.md`, independent of `KB_PROJECT_ROOT` env var. Closes the legacy bug class where `load_purpose` would read the real `PROJECT_ROOT/wiki/purpose.md` instead of the sandbox path.
  - Pass/fail: test with `monkeypatch.setenv("KB_PROJECT_ROOT", "/elsewhere")` asserts `load_purpose(tmp)` reads only `tmp/purpose.md`.

### Theme G — Ingest observability + helper (2 ACs, 1 file)

- **AC19** (MEDIUM, BACKLOG §MEDIUM "ingest/pipeline.py observability"): `ingest_source` emits `request_id = uuid.uuid4().hex[:16]` at entry; threads through `wiki/log.md` message prefix (`[req=<id>] <existing>`) and a new structured line per call in `.data/ingest_log.jsonl` with the full result dict. Logger warnings tagged `[req=<id>]`. Correlation ID is ADDITIVE — no callers break.
  - Pass/fail: test monkeypatches `uuid.uuid4`, ingests a source, asserts `.data/ingest_log.jsonl` contains one line with the expected `request_id` + all result dict keys.

- **AC20** (MEDIUM, BACKLOG §MEDIUM "ingest/pipeline.py index-file write order"): Consolidate `index.md` + `_sources.md` writes into `_write_index_files(wiki_dir, index_entry, sources_entry)` helper with documented ordering (`index.md` first, then `_sources.md`) + top-of-module comment about recovery semantics. Minimal refactor: extract existing two writes into one function, no behavior change.
  - Pass/fail: helper has its own unit test; existing `test_ingest.py` full-pipeline test continues to pass.

### Theme H — Linker batch scan (1 AC)

- **AC21** (MEDIUM, BACKLOG §MEDIUM "ingest/pipeline.py:712-721 inject_wikilinks per-page loop"): `compile/linker.py::inject_wikilinks_batch(new_titles_and_ids, pages)` — batch scanner reading each page once with single compiled alternation regex; `ingest/pipeline.py:712-721` switches to batch call. Preserves per-page atomic_text_write semantics; no locking regression. Measured target: 100 new titles × N pages = N disk reads (not 100·N).
  - Pass/fail: regression test asserts a single `inject_wikilinks_batch` call over 100 titles reads each target page exactly once (via `unittest.mock.patch.object(Path, 'read_text')` counter).

## Blast radius (by `src/kb/` module)

| Module | ACs | Reversibility |
|---|---|---|
| `compile/compiler.py` | AC1, AC2, AC3 | reversible (internal logic + test) |
| `compile/linker.py` | AC21 | reversible (new function + callsite switch) |
| `mcp/{core,browse,health,quality}.py` | AC4-AC7 | reversible (import order change) |
| `models/page.py` | AC8 | reversible (docstring OR delete — decision gate) |
| `capture.py` | AC9, AC10 | AC10 has state-machine risk; AC9 trivial |
| `lint/augment.py` | AC11 | reversible (new kwarg) |
| `cli.py` | AC12 | reversible (new Click option) |
| `mcp/health.py` | AC13 (overlaps AC6) | reversible (new MCP param) |
| `ingest/pipeline.py` | AC19, AC20 | AC19 adds new file; AC20 is refactor-only |
| `tests/conftest.py` | AC16 | opt-in fixture, zero existing-test impact |
| `tests/test_v0p5_purpose.py` | AC14, AC18 | net-add tests |
| `tests/test_workflow_e2e.py` (NEW) | AC15 | net-add file |
| `tests/test_mcp_tool_coverage.py` (NEW) | AC17 | net-add file |

Total: 14 source + test files; 2 new test files.

## Dependencies / threat-model inputs

- No new third-party packages.
- New filesystem writes: `.data/ingest_log.jsonl` (append-only, per-ingest line). Path-traversal attack surface = none (compile-time constant under `.data/`).
- New user-controllable string: `--resume <id>` / `kb_lint(resume=...)` — **input validation required** to prevent path traversal into `.data/augment/<id>/`.
- New UUID generation path for `request_id` — collision risk nil at hex[:16] over per-process lifetime; not security-relevant.

## Cycle sizing

21 ACs → triggers R3 PR review per cycle-16 L4 (new filesystem-write surface `.data/ingest_log.jsonl` + new MCP param `kb_lint(resume=...)` with validation). R3 scheduled.
