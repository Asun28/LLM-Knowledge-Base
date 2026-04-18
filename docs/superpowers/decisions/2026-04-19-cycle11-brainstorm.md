# Cycle 11 — Brainstorm (Step 3)

**Date:** 2026-04-19
**Scope:** 14 ACs across 10 files. Test-coverage-heavy, refactor-light, zero new features.

## Shape of the cycle

Backlog-by-file pattern. The ACs are pre-clustered per file so brainstorming is about *sequencing* and *risk isolation*, not about WHAT to do.

## Three candidate sequencings

### Approach A — Refactor-first, tests-last (risk-heavy)

1. `src/kb/utils/pages.py` — absorb canonical `page_id` + `scan_wiki_pages`.
2. `src/kb/graph/builder.py` — convert to re-export shim.
3. 5-module caller cluster — switch imports.
4. `src/kb/ingest/pipeline.py` — `_coerce_str_field` migration + comparison/synthesis reject.
5. Existing test updates (`tests/test_ingest.py`, `tests/test_compile.py`).
6. New test files (5 new files).
7. Docs.

**Why consider it:** front-loads the refactor so subsequent commits have the canonical import location already available; any test-only commit afterward is trivial to rebase if blockers land.

**Risk:** if step 2 is wrong (re-export shim drops a signature nuance), every subsequent commit in the series must be rebased. The refactor touches 5 caller modules — single failure cascades.

### Approach B — Test-first, refactor-last (risk-minimising)

1. New test files for AC6 (`utils/pages`), AC7/AC8 (cli imports + --version), AC9–AC11 (`_flag_stale_results` edge cases) — these all pass against current `main` without source changes because the behaviours already exist.
2. `src/kb/ingest/pipeline.py` — AC1 migration + AC2 reject.
3. New test file for AC1/AC2/AC3 (`test_cycle11_ingest_coerce.py`).
4. `tests/test_ingest.py` — AC12 scaffolding cleanup.
5. `tests/test_compile.py` — AC13 behavioural assertion.
6. `src/kb/utils/pages.py` — absorb canonical helpers.
7. `src/kb/graph/builder.py` — re-export shim.
8. 5-module caller cluster — import swap.
9. Docs.

**Why consider it:** tests land first when they describe existing behaviour (AC6/AC9/AC10/AC11 all pin behaviour that's already true in the code). Production-code changes come last when the test safety net is already in place. If refactor blocks at step 8, the full test suite already captures the baseline.

**Risk:** the new `tests/test_cycle11_utils_pages.py` for AC6 would initially test the OLD (`kb.graph.builder`) location and need to be updated when the move happens — OR we write the tests against the NEW location from day 1 with a `skip-if-not-present` guard, which is awkward.

### Approach C — Bucket-by-risk (recommended)

Group by risk and ship in independent per-file commits:

**Phase 1 (atomic import cluster — must land together):**
- a. `src/kb/utils/pages.py` (absorb canonical)
- b. `src/kb/graph/builder.py` (re-export shim)
- c. 5-module caller cluster (`compile/linker`, `evolve/analyzer`, `lint/checks`, `lint/runner`, `lint/semantic`)
— These 7 files form ONE atomic change (documented as a cluster per cycle-4 RedFlag guidance). Either the entire import move lands together or nothing does; a half-migrated intermediate commit breaks imports.

**Phase 2 (independent per-file hardening):**
- `src/kb/ingest/pipeline.py` — AC1 + AC2 in one commit (same file, related hardening).
- `tests/test_ingest.py` — AC12 (scaffolding cleanup).
- `tests/test_compile.py` — AC13 (behavioural assertion).

**Phase 3 (new test files, all independent, can land parallel or serial):**
- `tests/test_cycle11_utils_pages.py` — AC6.
- `tests/test_cycle11_cli_imports.py` — AC7 + AC8.
- `tests/test_cycle11_stale_results.py` — AC9 + AC10 + AC11.
- `tests/test_cycle11_ingest_coerce.py` — AC1 + AC2 + AC3 regression tests.

**Phase 4:** CHANGELOG + BACKLOG doc sync.

**Why this wins:**
- The atomic cluster is called out explicitly as a cluster (per cycle-4 RedFlag: "Multi-file tasks break AC6 file-grouped-commit discipline" — the mitigation is to flag the cluster with rationale, not to contort the change).
- Test files for AC6 are written against the NEW canonical location AFTER Phase 1 lands, eliminating the "test the old location then migrate" awkwardness of Approach B.
- New test files (Phase 3) are fully independent and can be written in parallel.
- Phase 2 files are genuinely unrelated to the Phase 1 refactor, so they don't rebase-cascade on a Phase 1 retry.

## Decision

**Proceed with Approach C.** Phase 1 (atomic cluster) first, Phase 2 (independent per-file) next, Phase 3 (new tests) last, Phase 4 (docs) at the end. This matches the cycle-9 and cycle-10 pattern (backlog-by-file with explicit cluster rationale where multi-file change is load-bearing).

## Open questions (for Step 5 gate)

1. **`page_id` lowercase behaviour** — when we move `page_id` to `utils/pages`, do we preserve the existing `lower()` call? The backlog also flags this as a cross-platform issue (Windows dev + Linux CI diverge on case-sensitive filesystems). Decision: **preserve existing behaviour** in cycle 11. Fixing the cross-platform semantics is a separate, larger cycle (requires wiki-wide filename normalisation). Documented as out-of-scope in requirements "Non-goals".

2. **Back-compat re-export scope** — should `kb.graph.builder.page_id` be a true re-export (`from kb.utils.pages import page_id`) or a wrapper function? Decision: **true re-export** so `id(kb.graph.builder.page_id) == id(kb.utils.pages.page_id)` — simplest, least surface for drift.

3. **AC2 error signalling** — does `ingest_source(source_type="comparison")` raise `ValueError` or return an error dict? Decision: match the existing `detect_source_type(assets)` precedent which RAISES `ValueError`. Callers (CLI, MCP) already translate exceptions to user-facing error strings. See `ingest_source` line 867 onward for the existing try/except wrapping in `cli.py::ingest`.

4. **AC1 coverage bound** — should all 12+ `.get()` sites be migrated or only the primary-text sites? Decision: migrate only the sites that feed into string-consuming functions (title-merge, author, key_claims/key_points/key_arguments, entities_mentioned, concepts_mentioned). Sites that feed into list-consuming functions already tolerate list/None via `or []`; migrating them without a list-coerce helper is scope creep. Document the list-consumer sites as out-of-scope (same ticket, different fix).

5. **AC8 implementation** — subprocess test importing `kb.cli` vs monkeypatch-based in-process test? Decision: **subprocess test** via `python -c "import sys; kb.cli.cli([...])"` with assertion on `sys.modules` — in-process test won't exercise the short-circuit path because `kb.config` is already loaded by pytest's own import chain.
