# Cycle 43 — Test fold continuation (Phase 4.5 HIGH #4)

**Date:** 2026-04-27
**Branch:** `cycle-43-test-folds`
**Parallel cycle:** cycle 42 (Phase 4.6 dedup) on `cycle-42-phase46-dedup` — DO NOT touch `src/kb/cli.py`, `src/kb/mcp/*.py`, or `tests/test_v01013_cli_error_truncation.py` (cycle-42 WIP stashed at `stash@{0}`).

## Problem

Phase 4.5 HIGH #4 — `tests/` coverage-visibility — has been worked piecemeal across cycles 38-41 (cycle 38 mock_scan_llm fold; cycle 39 cycle-tagged file fold; cycle 40 three folds — `test_cycle10_safe_call`, `test_cycle10_linker` SPLIT, `test_cycle11_stale_results`; cycle 41 four folds — `test_cycle10_validate_wiki_dir`, `test_cycle10_capture`, `test_cycle10_quality`, `test_cycle11_cli_imports`). **Test file count: 251**. **~200+ versioned `test_cycleNN_*.py` / `test_v0NNN_*.py` / `test_phase4_audit_*.py` files remain**, blocking per-module coverage discovery. Each fold reduces the grep surface and brings tests under canonical home discoverability.

## Non-goals

- **No production-code changes.** Cycle 43 is test-only relocation; new behavior tests do NOT belong here.
- **No vacuous-test upgrades.** Per C40-L3, fold KNOWN-WEAK tests (vacuous-grep, signature-only, isolation-stub, docstring-introspection) AS-IS into canonical home AND file BACKLOG.md upgrade-candidate entry; do NOT auto-upgrade. C41-L1 reinforces: docstring-vs-code sanity check first.
- **No conflict with cycle-42.** Skip folds whose canonical home is `test_mcp_*` if the source file imports `_sanitize_error_str` / `_truncate` / `_rel` (cycle-42 dedup territory). Verified: cycle-1[0-2]\_*.py source files do NOT import those symbols.
- **No new dependencies.** Pytest stdlib + existing project fixtures only.
- **No CI matrix expansion.** Single-OS strict gate per cycle-36 L1.

## Acceptance criteria

Target: 12 fold ACs + ≥3 BACKLOG entries for vacuous candidates ≈ ~30 backlog items per `feedback_batch_by_file`.

| AC | Source file | Canonical home | Fold rationale |
|----|-------------|----------------|----------------|
| AC1 | `tests/test_cycle10_browse.py` | `test_mcp_browse_health.py` | Browse-specific MCP tests; canonical home already hosts cycle-10 helpers from prior fold (cycle-40 AC1) |
| AC2 | `tests/test_cycle10_extraction_validation.py` | `test_ingest.py` | Extraction-validation gate exercises ingest pipeline pre-validate path |
| AC3 | `tests/test_cycle10_vector_min_sim.py` | `test_query.py` | Vector min-similarity threshold lives in `query/embeddings.py`; canonical home is `test_query.py` per cycle-40 `test_cycle11_stale_results` precedent |
| AC4 | `tests/test_cycle11_conftest_fixture.py` | `test_paths.py` OR `test_models.py` (decided at Step 5) | Conftest fixture validation — host depends on what is asserted |
| AC5 | `tests/test_cycle11_ingest_coerce.py` | `test_ingest.py` | Ingest type coercion |
| AC6 | `tests/test_cycle11_utils_pages.py` | `test_utils.py` (or new `test_utils_pages.py`) | Utils/pages helper tests; decided at Step 5 |
| AC7 | `tests/test_cycle12_config_project_root.py` | `test_paths.py` | Config PROJECT_ROOT walk-up; paths module owns root-resolution helpers |
| AC8 | `tests/test_cycle12_frontmatter_cache.py` | `test_models.py` | Frontmatter cache lives in `models/frontmatter.py` |
| AC9 | `tests/test_cycle12_io_sweep.py` | `test_utils_io.py` | sweep_orphan_tmp lives in `utils/io.py`; canonical home exists |
| AC10 | `tests/test_cycle12_sanitize_context.py` | `test_utils.py` (sanitize) — ONLY if no `_sanitize_error_str` re-export dependency | Verify no cycle-42 conflict before fold |
| AC11 | `tests/test_cycle13_augment_raw_dir.py` | `test_lint.py` | Augment lives in `lint/augment.py`; canonical home is `test_lint.py` |
| AC12 | `tests/test_cycle13_sweep_wiring.py` | `test_cli.py` | sweep_orphan_tmp wiring in CLI boot |
| AC13 | BACKLOG-document any fold candidates that turn out to be vacuous (per C40-L3) | — | At least one entry expected based on prior cycle base rate |
| AC14 | Test count + file count drift verified at Step 12 | CHANGELOG / docs/reference/testing.md / CLAUDE.md / README.md / docs/reference/implementation-status.md | Per C26-L2 + C39-L3 multi-site grep |

**Per-fold contract:**
1. Read source file + canonical home — compare class/function organization
2. Identify vacuity class (vacuous-grep / signature-only / isolation-stub / docstring-introspection per C40-L3); apply C41-L1 docstring-vs-code sanity check before any upgrade — if vacuous, fold AS-IS + file BACKLOG entry; do NOT auto-upgrade
3. Move tests preserving structure (class-based hosts → wrap in class; bare-function hosts → bare functions per cycle-40 host-shape precedent + C40-L5 structural grep)
4. Delete source file
5. Run `python -m pytest tests/<canonical>.py -q` — must pass
6. Commit per-AC: `test(cycle 43 ACN): fold test_<source> into <canonical>` (one commit per fold per `feedback_batch_by_file`)

**Per-cycle contract:**
- Test count: unchanged (folds preserve count) — verify via `python -m pytest --collect-only | tail -1` after Step 9 and AGAIN after each Step 14 fix commit (cycle-15 L4)
- File count: 251 → 251 - N_folds (one delete per fold)
- BACKLOG.md: Phase 4.5 HIGH #4 progress note updated with new fold count + per-fold delta
- `docs/reference/testing.md` test-count narrative updated (per C26-L2)
- `README.md` tree-block + Phase X stats prose updated (per C39-L3)
- CLAUDE.md Quick Reference test-count block updated
- CHANGELOG-history.md per-cycle detail
- CHANGELOG.md compact entry

## Blast radius

- `tests/` directory only (no `src/kb/` changes)
- Doc files: CHANGELOG.md, CHANGELOG-history.md, BACKLOG.md, CLAUDE.md, docs/reference/testing.md, docs/reference/implementation-status.md, README.md
- New decisions docs: `docs/superpowers/decisions/2026-04-27-cycle-43-{requirements,threat-model,design,plan,self-review}.md`

**Cycle-42 collision surface (verified):** Cycle-42 stash modifies `src/kb/cli.py`, `src/kb/mcp/{app,browse,core,health,quality}.py`, `tests/test_v01013_cli_error_truncation.py`. Cycle-43 fold candidates (test_cycle1[0-2]\_*) do NOT import `_sanitize_error_str` / `_truncate` / `kb.mcp.app._rel` (grep verified at Step 1). Folds going INTO `test_mcp_browse_health.py` (AC1) carry the lowest collision risk because they relocate tests that already exist in `test_cycle10_browse.py` source — the fold doesn't ADD new imports of cycle-42 symbols, it just relocates existing test bodies. Confirm at Step 4 design eval.

## Threat model preview (Step 2 will formalize)

- **T1 — Fold introduces test ordering hazard.** New canonical home test runs in different position vs source; reload-leak (cycle-22 L3 + cycle-19 L2) may surface. Mitigation: full-suite run at Step 10.
- **T2 — Vacuous-test fold misses upgrade.** A signature-only test gets folded without a BACKLOG entry; future maintainer treats it as a behavior pin. Mitigation: C40-L3 + C41-L1 self-check at every fold.
- **T3 — Test-count drift across docs.** CHANGELOG says N tests, README says M, CLAUDE.md says K. Mitigation: C26-L2 + C39-L3 multi-site grep at Step 12 + re-verify after every R1/R2 fix commit (cycle-15 L4).
- **T4 — Cycle-42 merge conflict.** Cycle-42 lands AFTER cycle-43, BACKLOG.md sections collide. Mitigation: cycle-43 BACKLOG edits scoped to Phase 4.5 HIGH #4 progress line; cycle-42 edits Phase 4.6. Different sections; rebase-clean.
- **T5 — Reload-leak via host-file conftest behaviour.** Folding tests into a canonical home that already mutates module state (importlib.reload, monkeypatch.setenv("KB_PROJECT_ROOT")) may break sibling tests in the same file. Mitigation: prefer canonical homes that DO NOT reload kb.config; if reload is unavoidable, fold to a sub-class with isolated setup (cycle-19 L2 + cycle-20 L1 test-isolation patterns).

## Step 6 (Context7) skip rationale

Test-only refactor uses pytest stdlib + project test fixtures (`tmp_wiki`, `tmp_project`, `tmp_kb_env`). No third-party library API verification needed.

## Step 9.5 (`/simplify`) skip rationale

`/simplify` scope is `src/` only per skill. Cycle 43 is test-only.
