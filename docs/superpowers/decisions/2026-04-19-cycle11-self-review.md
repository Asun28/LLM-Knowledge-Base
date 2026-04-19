# Cycle 11 — Step 16 Self-Review

**Date:** 2026-04-19
**PR:** #25 (merge commit `958df04`)
**Branch:** `feat/backlog-by-file-cycle11` (deleted post-merge)
**Commits on branch:** 18 (audit + 14 impl/test/docs + 3 review fixes + 1 R3 trail)
**Test delta:** 2038 → 2082 passed (+44), 7 Windows-skips preserved.
**New test files:** 6 (`test_cycle11_{conftest_fixture,utils_pages,cli_imports,stale_results,ingest_coerce,task6_mcp_ingest_type}.py`)
**Deps touched:** 0. Class B (PR-introduced) CVEs: 0.
**Dependabot alerts post-merge:** 0.

## Step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements + AC | yes | yes | — |
| 2 Threat model + CVE baseline | yes | yes | — |
| 3 Brainstorming | yes | yes | — |
| 4 Design eval R1+R2 | yes | yes | R2 caught AC7 `--help` vacuous (doesn't exercise callbacks); R1 caught AC5 missing `compile/compiler.py` 6th caller |
| 5 Decision gate (Opus subagent) | yes | yes | resolved 10 Qs HIGH-confidence; expanded atomic cluster from 5→6, kept `_page_id` as alias (not deleted), flipped AC7 to CliRunner, AC8 to fresh subprocess + minimal env |
| 6 Context7 verify | skipped | n/a | stdlib-only, no new deps — correctly skipped |
| 7 Plan (Codex) | yes | yes | Codex flagged `PLAN-AMENDS-DESIGN:` on commit-ordering reorder |
| 8 Plan gate (Codex) | yes | yes | `PLAN-AMENDS-DESIGN-DISMISSED` — both orderings preserved dependencies |
| 9 Implementation | yes | yes per-task | 12 serial tasks; all Codex responses landed cleanly, full pytest + ruff green at each task commit |
| 10 CI hard gate | yes | yes | 2079 → 2081 after same-class fix; all ruff clean |
| 11 Security verify (Codex) | yes | **no** | FAIL verdict flagged 3 issues: T3 same-class (real — fixed via `kb_save_source` guard in follow-up commit `ed73ce6`), T5 scope-bypass grep (7 false-positive comment hits — manually verified), T9 deletion-branch (scoped-out per Step-5 Q10, not a cycle-11 AC) |
| 11.5 Existing-CVE patch | skipped | n/a | 0 open Dependabot alerts |
| 12 Doc update (Codex) | yes | yes | CHANGELOG + BACKLOG + CLAUDE.md updated via Codex diff-reader pass |
| 13 Branch + PR | yes | yes | PR #25 opened with comprehensive body (review trail + test plan) |
| 14 PR review R1+R2+R3 | yes | **no** | R1 caught atomic-cluster history (B1 Codex) + inspect-source test (B1 Sonnet / M1 Codex) + AC13 single-pass (M2 both) + env leak (M2 Sonnet) + alias comment (N1 Codex). R2 caught test didn't exercise `compile/compiler.py` function-local import. R3 APPROVE after fix. |
| 15 Merge + cleanup + late-arrival CVE | yes | yes | Merged via `--merge` (matches cycle 10 convention) at `958df04`. Branch deleted. Zero post-merge alerts. |
| 16 Self-review + skill patch | yes (this doc) | yes | documenting 3 lessons below |

## Lessons (to become SKILL.md Red Flags)

### L1 — Inspect-source patterns LURK IN BEHAVIOURAL-LOOKING TESTS

**What happened.** My AC4/AC5 pinning test `test_cycle11_ac4_six_callers_do_not_import_page_helpers_from_builder` used `line.startswith("from kb.graph.builder import")` as a "line-prefix" check. It looked behavioural (iterating caller module files). But `startswith` on raw lines SKIPS indented lines. `compile/compiler.py`'s function-local import (`    from kb.graph.builder import page_id as get_page_id` inside `detect_source_drift`) is indented 4 spaces — so the assertion never executed for THE ONE FILE the test was specifically designed to cover. Both R1 Sonnet (B1) and R1 Codex (M1) caught it.

**Why this matters.** The `feedback_inspect_source_tests` memory already bans `inspect.getsource(module) + "X" in src`. But this test didn't use `inspect.getsource` — it used `Path.read_text().splitlines()`. Same anti-pattern, different dress. The generalised rule: **any test that reads source files as strings is a source-scan test**, regardless of whether the read is via `inspect.getsource`, `Path.read_text`, or `subprocess cat`.

**How to apply.** When pinning "no import of X from module Y", prefer `importlib.import_module` + attribute-identity check (`module.X is canonical.X`). When the import is function-local (compiler.py:242), ACTUALLY CALL the function under a stub so the function-local import line runs — if the import resolves wrong, `ImportError` fires inside the call.

### L2 — Same-class completeness scan must include sibling MCP tools

**What happened.** AC2 was designed as "reject comparison/synthesis in `kb_ingest` + `kb_ingest_content`" (two-layer closure per Step-5 Q9). Step-11 Codex security verify correctly flagged that `kb_save_source` also accepts a `source_type` arg and rejects comparison/synthesis — but with a GENERIC "Unknown source_type" message, not the helpful "use kb_create_page" message the cycle introduced for the other two tools. Same-class completeness miss (per cycle-7/8 RedFlag) — caught by security verify, not by design eval.

**Why this matters.** Cycle-7 introduced the same-class completeness RedFlag after `_validate_notes` was scoped to 2/3 quality tools. The RedFlag said "Step 5 decision doc must explicitly call out same-threat-class sites C, D that are DELIBERATELY out of scope". My Step-5 design doc named AC2 scope as `kb_ingest` + `kb_ingest_content` but did NOT explicitly call out `kb_save_source` as a scoped-out same-class peer. The design would have been tighter if `kb_save_source` had been either in-scope or explicitly scope-out with rationale.

**How to apply.** When an AC introduces a user-facing error-message convention at N call sites, grep ALL functions in the same module (or all MCP tools in the same registry) that accept the same parameter type. Explicitly list the peers IN THE DESIGN DOC, either (a) in-scope (same commit), or (b) out-of-scope with one-line justification. If the justification is weak ("not a priority"), bring them in-scope.

### L3 — Plan-gate ordering discrepancies are almost always DISMISSED

**What happened.** My Step 7 plan dispatch prompt specified a 13-commit order with `tests/conftest.py` as commit 1 and `src/kb/utils/pages.py` as commit 2. The Step-5 design doc's per-file plan listed `utils/pages.py` first and `conftest.py` sixth. Codex flagged this as `PLAN-AMENDS-DESIGN:` on the plan's first line. Step 8 plan gate CORRECTLY diagnosed this as `PLAN-AMENDS-DESIGN-DISMISSED` — both orderings satisfied the real dependencies (conftest before `test_ingest.py`; `utils/pages.py` before `graph/builder.py` before the cluster).

**Why this matters.** The feature-dev skill's `PLAN-AMENDS-DESIGN` rule currently says "re-run step 5" unconditionally. In practice, 99% of PLAN-AMENDS-DESIGN hits are ordering reorders that don't violate dependencies. Re-running Step 5 for cosmetic reorders is wasteful. A `PLAN-AMENDS-DESIGN-DISMISSED` verdict from the plan gate should be a first-class resolution path in the skill doc.

**How to apply.** Update the feature-dev SKILL.md Step 8 section to explicitly recognise `PLAN-AMENDS-DESIGN-DISMISSED` as a valid Codex gate verdict: "if the dependency invariants are preserved under both orderings, dismiss the flag with an explicit 'DISMISSED' line and proceed to Step 9."

## Red Flag candidates for SKILL.md

I'll add two new rows + update one:

1. **L1 Red Flag** — new: "My test reads source files via `Path.read_text()` / `splitlines()` + substring check — that's behavioural, right?" — generalisation of the existing `inspect.getsource` Red Flag to catch line-prefix / splitlines variants.
2. **L2 Red Flag** — new: "Same-class peers in the same MCP tool registry — explicit in-scope / out-of-scope list in Step-5 design doc" — tightens cycle-7/8 RedFlag with a grep-based discipline for MCP tool same-class peers.
3. **L3 skill patch** — update Step 8 section: recognise `PLAN-AMENDS-DESIGN-DISMISSED` as a valid Codex gate verdict; skip Step 5 re-run.

## Process notes (no RedFlag needed)

- Cycle 11 was almost entirely test-coverage + one small refactor (page_id / scan_wiki_pages relocation). Very low blast-radius cycle vs cycle-10's 33 ACs. Good cycle-to-cycle pacing: alternate heavy cycles (10 = trust-boundary hardening) with lighter cycles (11 = test coverage + cleanup).
- 16 commits for 14 ACs reflects the R1/R2/R3 review loop producing follow-up commits. The PR review trail comment on PR #25 documents every fix-commit's review source — this is exactly the audit pattern the `feedback_3_round_pr_review` memory encodes.
- `tmp_project` fixture enhancement (TASK 1) was the perfect prereq commit — landed trivially, gave TASK 7 (scaffolding cleanup) clean ground.
