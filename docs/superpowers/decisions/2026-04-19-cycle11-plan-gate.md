## Coverage check
- AC1: covered by TASK 5: Harden Ingest Coercion And Reject comparison/synthesis, Files: `src/kb/ingest/pipeline.py`; TASK 12: Add Ingest Coercion And Dead-path Regression Tests, Files: `tests/test_cycle11_ingest_coerce.py`
- AC2: covered by TASK 5: Harden Ingest Coercion And Reject comparison/synthesis, Files: `src/kb/ingest/pipeline.py`; TASK 6: Add MCP Ingest Special-case Guidance, Files: `src/kb/mcp/core.py`; TASK 12: Add Ingest Coercion And Dead-path Regression Tests, Files: `tests/test_cycle11_ingest_coerce.py`
- AC3: covered by TASK 5: Harden Ingest Coercion And Reject comparison/synthesis, Files: `src/kb/ingest/pipeline.py`; TASK 12: Add Ingest Coercion And Dead-path Regression Tests, Files: `tests/test_cycle11_ingest_coerce.py`
- AC4: covered by TASK 2: Move Canonical Page Helpers To utils.pages, Files: `src/kb/utils/pages.py`; TASK 3: Convert graph.builder Helpers To Re-export Shim, Files: `src/kb/graph/builder.py`
- AC5: covered by TASK 2: Move Canonical Page Helpers To utils.pages, Files: `src/kb/utils/pages.py`; TASK 3: Convert graph.builder Helpers To Re-export Shim, Files: `src/kb/graph/builder.py`; TASK 4: Switch Internal Graph Helper Imports Atomically, Files: `src/kb/compile/linker.py`, `src/kb/evolve/analyzer.py`, `src/kb/lint/checks.py`, `src/kb/lint/runner.py`, `src/kb/lint/semantic.py`, `src/kb/compile/compiler.py`
- AC6: covered by TASK 2: Move Canonical Page Helpers To utils.pages, Files: `src/kb/utils/pages.py`; TASK 9: Add Direct utils.pages Tests, Files: `tests/test_cycle11_utils_pages.py`
- AC7: covered by TASK 10: Add CLI Import And Version Short-circuit Tests, Files: `tests/test_cycle11_cli_imports.py`
- AC8: covered by TASK 10: Add CLI Import And Version Short-circuit Tests, Files: `tests/test_cycle11_cli_imports.py`
- AC9: covered by TASK 11: Add Stale Result Edge-case Tests, Files: `tests/test_cycle11_stale_results.py`
- AC10: covered by TASK 11: Add Stale Result Edge-case Tests, Files: `tests/test_cycle11_stale_results.py`
- AC11: covered by TASK 11: Add Stale Result Edge-case Tests, Files: `tests/test_cycle11_stale_results.py`
- AC12: covered by TASK 1: Enhance tmp_project Fixture, Files: `tests/conftest.py`; TASK 7: Simplify test_ingest Scaffolding, Files: `tests/test_ingest.py`
- AC13: covered by TASK 8: Add Manifest Content Stability Assertion, Files: `tests/test_compile.py`
- AC14: covered by TASK 13: Sync Changelog And Backlog, Files: `CHANGELOG.md`, `BACKLOG.md`
- T1: covered by TASK 5: Harden Ingest Coercion And Reject comparison/synthesis, Files: `src/kb/ingest/pipeline.py`; TASK 12: Add Ingest Coercion And Dead-path Regression Tests, Files: `tests/test_cycle11_ingest_coerce.py`
- T2: covered by TASK 5: Harden Ingest Coercion And Reject comparison/synthesis, Files: `src/kb/ingest/pipeline.py`; TASK 6: Add MCP Ingest Special-case Guidance, Files: `src/kb/mcp/core.py`; TASK 12: Add Ingest Coercion And Dead-path Regression Tests, Files: `tests/test_cycle11_ingest_coerce.py`
- T3: covered by TASK 2: Move Canonical Page Helpers To utils.pages, Files: `src/kb/utils/pages.py`; TASK 3: Convert graph.builder Helpers To Re-export Shim, Files: `src/kb/graph/builder.py`; TASK 4: Switch Internal Graph Helper Imports Atomically, Files: `src/kb/compile/linker.py`, `src/kb/evolve/analyzer.py`, `src/kb/lint/checks.py`, `src/kb/lint/runner.py`, `src/kb/lint/semantic.py`, `src/kb/compile/compiler.py`; TASK 9: Add Direct utils.pages Tests, Files: `tests/test_cycle11_utils_pages.py`
- T4: covered by TASK 1: Enhance tmp_project Fixture, Files: `tests/conftest.py`; TASK 7: Simplify test_ingest Scaffolding, Files: `tests/test_ingest.py`
- T5: covered by TASK 10: Add CLI Import And Version Short-circuit Tests, Files: `tests/test_cycle11_cli_imports.py`
- T6: covered by TASK 10: Add CLI Import And Version Short-circuit Tests, Files: `tests/test_cycle11_cli_imports.py`
- T7: covered by TASK 11: Add Stale Result Edge-case Tests, Files: `tests/test_cycle11_stale_results.py`
- T8: covered by TASK 3: Convert graph.builder Helpers To Re-export Shim, Files: `src/kb/graph/builder.py`; TASK 9: Add Direct utils.pages Tests, Files: `tests/test_cycle11_utils_pages.py`
- T9: covered by TASK 8: Add Manifest Content Stability Assertion, Files: `tests/test_compile.py`
- T10: covered by TASK 13: Sync Changelog And Backlog, Files: `CHANGELOG.md`, `BACKLOG.md`

## PLAN-AMENDS-DESIGN analysis
PLAN-AMENDS-DESIGN-DISMISSED: both orderings preserve all dependency constraints. The amended plan places `tests/conftest.py` in TASK 1 before `tests/test_ingest.py` in TASK 7, satisfying the AC12 consumer dependency. It places `src/kb/utils/pages.py` in TASK 2 before `src/kb/graph/builder.py` in TASK 3, satisfying the canonical absorb before re-export shim dependency. It places `src/kb/graph/builder.py` in TASK 3 before the six-caller atomic cluster in TASK 4, satisfying the shim before caller migration dependency. There is no dependency edge requiring `src/kb/utils/pages.py` to land before `tests/conftest.py`, or requiring `tests/conftest.py` to land after `src/kb/utils/pages.py`.

## VERDICT
APPROVE

## Gaps (if any)
- None.
