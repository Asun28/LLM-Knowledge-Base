# Cycle 30 — Plan Gate (Step 8)

**Date:** 2026-04-24
**Role:** Primary-session plan-gate review (R2 Codex earlier silently stalled past cycle-20 L4 threshold; same fallback path invoked here — plan is well-scoped, no unfamiliar code to explore).
**Per cycle-21 L1:** when plan-gate gaps are doc/design in nature (not code-exploration), resolve inline.

## Coverage matrix

| AC | Threat | CONDITIONS | TASK | Test file | Covered? |
|---|---|---|---|---|---|
| AC1 | T1 (non-issue), T5 | C1, C2, C3, C4 | TASK 1 | `test_cycle30_audit_token_cap.py` | ✅ |
| AC2 | T2, T4, T6-T8 | C5, C7-C11 | TASK 2 | `test_cycle30_cli_parity.py::TestGraphVizCli` | ✅ |
| AC3 | T2, T6-T8 | C7-C11 | TASK 2 | `test_cycle30_cli_parity.py::TestVerdictTrendsCli` | ✅ |
| AC4 | T2, T6-T8 | C7-C11 | TASK 3 | `test_cycle30_cli_parity.py::TestDetectDriftCli` | ✅ |
| AC5 | T6-T8 | C10-C11 | TASK 3 | `test_cycle30_cli_parity.py::TestReliabilityMapCli` | ✅ |
| AC6 | T3, T6-T8 | C6, C7-C11 | TASK 4 | `test_cycle30_cli_parity.py::TestLintConsistencyCli` | ✅ |
| AC7 | — | C13 | TASK 5 | N/A (pure text) | ✅ |
| Doc | — | C14 | TASK 6 | N/A | ✅ |

## CONDITION verification (each maps to a concrete test / grep)

- **C1** (AC1 both-branch cap): TASK 1 tests `test_audit_token_caps_long_warn_error` + `test_audit_token_caps_long_fallback_error`; grep `truncate(str(block` → ≥2.
- **C2** (function-local import): TASK 1 code change; grep `^    from kb.utils.text import truncate` in `_audit_token` body.
- **C3** (unit + e2e tests): TASK 1 both tests spelled out.
- **C4** (existing audit-grep tests green): TASK 1 post-commit full-suite run catches drift.
- **C5** (AC2 help-text literal): TASK 2 test `test_graph_viz_help_exits_zero` asserts `"1-500; 0 rejected"` in output.
- **C6** (AC6 raw passthrough): TASK 4 test `test_lint_consistency_body_executes_with_ids` asserts `called["page_ids"] == "concepts/a,concepts/b"` (not split).
- **C7** (no `--wiki-dir` on AC6): TASK 4 test `test_lint_consistency_help_exits_zero` asserts `"--wiki-dir" not in result.output`.
- **C8** (docstring-import order): TASK 2/3/4 pattern follows cycle-27 lines 584-595 (imports AFTER docstring).
- **C9** (no `Path(wiki_dir)`): none of the TASK code wraps `wiki_dir` — forwarded raw.
- **C10** (`_error_exit(exc)` wrap): present in every TASK 2/3/4 CLI body.
- **C11** (test file naming + class-per-command): TASK 2-4 all use `test_cycle30_cli_parity.py` with one class per subcommand.
- **C12** (6 commits): TASK 1-6 mapping is 1-to-1 with Q6 commit plan.
- **C13** (BACKLOG confined): TASK 5 explicit diff targets.
- **C14** (test/commit counts): TASK 6 bullet lists the verification commands per cycle-25 L3 + cycle-26 L1.
- **C15** (R3 SKIP note in PR): Step-13 task will include the one-line note in PR body.

## Dependency check (cycle-11 L3 split-verdict guard)

No PLAN-AMENDS-DESIGN conflicts. Task ordering is:
- TASK 1 (compiler.py) — independent.
- TASK 2, 3, 4 (cli.py) — each appends at EOF; no cross-task dependency.
- TASK 5 (BACKLOG.md) — independent.
- TASK 6 (docs) — depends on TASK 1-5 completion for accurate counts.

The plan orders TASK 1 before TASK 2-4 (compiler before CLI), which doesn't need to hold — both are independent. But keeping the order matches "simplest change first" heuristic (AC1 is 3 lines + 5 tests vs AC2-AC5 which are 5 × ~20-line blocks).

## Test expectations pinned per AC

Each TASK lists:
- Revert-tolerance check: test assertion flips under production revert (per Q3 / cycle-24 L4 / cycle-28 L2).
- Body-execution test per cycle-27 L2 (not just `--help` smoke).
- Spy-on-MCP-module pattern (monkeypatch `quality_mod` / `health_mod`) matching cycle-27 precedent.

## Plan-gate verdict

**APPROVE.** Every AC maps to a TASK with a concrete test assertion and CONDITION references. No PLAN-AMENDS-DESIGN signals. No code-exploration gaps (all target functions grep-verified at Step 4). Step 9 clear to proceed.

Note: cycle-21 L1 alternative (inline Codex plan-gate re-dispatch) not invoked because the plan's verification table above is already complete + tractable. Step 9 commencement path authoritative.
