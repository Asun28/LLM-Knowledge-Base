# Cycle 30 — Step 16 Self-Review (mandatory)

**Date:** 2026-04-25
**Merged:** commit `6ad3175` (PR #44)
**Branch:** cleaned up post-merge
**Final test count:** 2850 (2826 → 2850, +24)
**Commit count (post-merge):** 12 on feature branch

## Scorecard

| Step | Executed? | First-try? | Surprised? |
|------|-----------|------------|------------|
| 1 — Requirements + AC | yes | yes | — |
| 2 — Threat model + CVE baseline | yes | yes (Opus Agent + pip-audit parallel) | — |
| 3 — Brainstorming | yes | yes | — |
| 4 — Design eval (R1+R2) | yes | **no** (R2 Codex stalled ~14min, primary-session R2 fallback per cycle-20 L4; R2 returned later with 3 substantive findings applied as DESIGN-AMEND) | R2 Codex subagent stall + late return raised 2 valid amendments (R2-A2 AC1 truthiness guard, R2-A3 AC7 arithmetic `14→12`) that would have been caught without fallback |
| 5 — Design decision gate | yes | yes (primary Opus Agent, 13 Qs resolved, 15 CONDITIONS) | — |
| 6 — Context7 | skipped per skill rule (stdlib + internal wrappers) | — | — |
| 7 — Implementation plan | yes, primary-session per cycle-14 L1 | yes | — |
| 8 — Plan gate | yes, primary-session per cycle-21 L1 | yes | — |
| 9 — Implementation (TDD) | yes, 6 commits per plan | yes — all 7 ACs landed in a single TDD cycle | — |
| 10 — CI hard gate | yes | yes (2836 passed + 10 skipped, ruff clean) | — |
| 11 — Security verify + PR-CVE diff | yes, primary-session per cycle-20 L4 pattern | yes (all T1-T8 IMPLEMENTED, CVE diff empty) | — |
| 11.5 — Existing-CVE patch | skipped (ragas alert no upstream fix, identical to cycle-25-29 baseline) | — | — |
| 12 — Doc update | yes | **no** — commit-count recursion trap (cycle-26 L1) — 3 convergence attempts (6→7→8→9) + 2 post-R1/R2 fix updates (10→12) | See L1 patch below |
| 13 — Branch finalise + PR | yes, PR #44 opened | yes | — |
| 14 — PR review (2 rounds) | yes (R1 Codex APPROVE, R1 Sonnet 2 MAJOR fix commit, R2 Codex PARTIAL follow-up fix commit) | no — R1 Sonnet caught valid test-coverage gaps that the Step-9 implementation missed | Unicode / `--max-nodes 0` boundary tests — see L2 patch below |
| 15 — Merge + cleanup | yes, merged via `gh pr merge`, branch deleted, main up-to-date | yes | Late-arrival CVE check: alert 12 (ragas, pre-existing) — no new advisories |
| 16 — Self-review + skill patch | in progress | — | — |

## What worked

- **Primary-session R2 fallback at Step 4** (cycle-20 L4 / cycle-27 L3) — saved ~14 min wall time vs waiting for the hung agent. When R2 Codex returned late, its findings merged cleanly as DESIGN-AMEND without re-running Step 5 (cycle-21 L1 pattern for doc/clarification gaps).
- **Primary-session plan draft at Step 7** (cycle-14 L1) — thresholds were below subagent-dispatch justification; plan wrote in ~5 min with full context retention. Plan-gate at Step 8 APPROVED.
- **Test-file split** (`test_cycle30_audit_token_cap.py` vs `test_cycle30_cli_parity.py`) kept the AC1 compiler concern cleanly separated from AC2-AC6 CLI concerns — matches cycle-27 precedent + cycle-19 L2 reload-leak isolation.
- **R2 late-arrival DESIGN-AMEND** applied R2-A2 + R2-A3 inline without re-running Step 5; R2-A4 dismissed appropriately (plan was correct, only requirements prose was wrong — cycle-22 L5 rule).
- **Cycle-27 cookie-cutter pattern** replayed cleanly for AC2-AC6. Zero decorator-theft regressions (cycle-27 L1), zero docstring-orphan bugs (cycle-23 L1), zero `Path(wiki_dir)` coercion (cycle-23 I1).

## What hurt

1. **Commit-count recursion at Step 12** (cycle-26 L1 trap applied literally). The `+1 self-referential` rule combined with my naive "fix the drift, then fix the fix" approach produced 4 convergence commits (`ef63cc9`, `4f4fa00`, `d09ad79`, then R1/R2 fix commits bumping further). The cycle-25 L3 `+TBD` placeholder alternative would have avoided the entire loop — file as new skill patch.
2. **R1 Sonnet test-coverage MAJORs** — both valid gaps (Unicode + `--max-nodes 0` boundary). My Step-9 test design pinned happy paths but not established MCP-tool boundaries. File as new skill patch.
3. **R2 Codex PARTIAL on CJK** — my CJK test called `.encode().decode()` for side-effect only without asserting equality, while the emoji test DID have the equality check. An internal copy-paste drift between two parallel test cases. The fix was trivial but the asymmetry was avoidable.
4. **R2 Codex Step-4 silent stall** — the stall was due to a read-only sandbox mode mismatch (per memory context), NOT a true agent hang. Diagnosing this requires checking the agent's task output file via ls, not assuming hang after 10min. Cycle-20 L4 fallback was still correct behavior but the root-cause attribution was wrong.

## Skill patches

### L1 — Commit-count `+TBD` placeholder is MANDATORY at Step 12 (generalises cycle-25 L3, obsoletes cycle-26 L1 inline-fix pattern)

Cycle 30 demonstrated that the cycle-26 L1 "self-referential +1 at commit-write time" rule creates an infinite recursion when the operator discovers post-commit drift and tries to "fix it" with another commit. Each fix-commit adds +1 to the count, requiring another fix, ad infinitum. Cycle 30 shipped 4 convergence commits before accepting defeat.

**New rule:** Step 12 CHANGELOG + CHANGELOG-history Quick Reference MUST use `+TBD` placeholder for the `commits: <K>` field. Backfill the final value in Step 15 (post-merge) as a separate `docs(cycle N): backfill post-merge counts` commit on main — this commit lands AFTER the feature branch is merged + deleted, so its `+1` is irrelevant to any self-referential math.

Alternatively, if the operator insists on landing the final number in the feature branch: pre-compute the anticipated count as `(pre-step-12 count) + 1 (step-12 itself) + anticipated R1/R2 fix commits` BEFORE writing Step 12. If the operator cannot predict R1/R2 fix commits (the normal case), default to `+TBD`.

Rule: `cycle-26 L1` is now `cycle-30 L1` — the inline-fix pattern is deprecated. The `+TBD` discipline removes the recursion surface entirely.

Test counts (cycle-15 L4) continue to use the inline-fix pattern because `pytest --collect-only | tail -1` gives a deterministic value at each commit write time — there's no self-reference problem for test counts.

### L2 — CLI wrappers over MCP tools with enforced boundaries MUST have a test per boundary (refines cycle-27 L2)

Cycle 27 L2 mandated body-execution tests (spy + non-`--help`) per CLI subcommand. Cycle 30 AC2 shipped with only the happy-path (`--max-nodes 50`) + an `Error:`-prefix path. R1 Sonnet correctly flagged missing tests for:
- `--max-nodes 0` — MCP tool explicitly rejects with error string.
- `--max-nodes -1` — MCP tool silently clamps to 1.

Both edges are documented in the MCP tool's body + docstring, and the CLI passthrough contract says "CLI forwards raw; MCP is authoritative". Without tests, the contract is unverified.

**Rule:** For every CLI wrapper over an MCP tool with a `click.IntRange`-shaped parameter OR an enforced-range validator, the test suite must include:
1. A rejection-boundary test (e.g., `--max-nodes 0` → exit non-zero + `Error:`-prefix) using the REAL MCP tool (NO monkeypatch — exercise the integration).
2. A clamp-or-silent-transform test (e.g., `--max-nodes -1`) using a spy to confirm the CLI forwards the value RAW (not clamped at CLI level). Divergent-fail: if the CLI added its own clamp, the spy would see the clamped value and the test would flip.

Self-check at Step 9: for each `click.option(type=int)` / `click.option(type=click.Path)` / `click.option(type=str)` with a documented MCP-tool range or validator, verify the paired test file has ≥1 rejection-boundary test + ≥1 raw-forwarding test. If either is missing, add before commit.

### L3 — Parallel test cases must share assertion shape (new cycle-30 lesson)

My AC1 Unicode tests shipped with an asymmetric shape: the CJK test (`test_audit_token_caps_unicode_cjk_error`) had only a side-effect `.encode().decode()` line without equality assertion; the emoji test (`test_audit_token_caps_mixed_emoji_error`) had a full `assert result == encoded.decode("utf-8")`. R2 Codex caught the asymmetry as PARTIAL.

Root cause: manual copy-paste drift during test authoring. The stronger assertion pattern wasn't propagated to the first-authored test.

**Rule:** When two or more test cases in the same test class exercise parallel invariants on different inputs (CJK + emoji + latin + mixed; int=0 + int=-1 + int=MAX; empty-list + single-item + many-items), they MUST share identical assertion shape. Concrete discipline:
1. Write the assertion skeleton ONCE.
2. Use it as a mental template when copy-pasting the test body for the next input variant.
3. Run a diff-style mental check: "do these two tests assert the same property in the same way on their respective inputs?" If not, fix before committing.
4. At PR-review time: when reviewing parallel test cases, grep for matching assertion patterns. If one case has an extra line of verification that the other lacks, flag as PARTIAL.

Generalises cycle-24 L1 (`Edit(replace_all=true)` silent-miss risk) to test-authoring: copy-paste between parallel cases is a drift risk class regardless of the mechanism.

## Cycle metrics

- **Wall time:** ~3h (Step 0 inventory through Step 15 merge).
- **Commits merged:** 12.
- **Tests added:** +24.
- **Doc files created:** 10 decision docs + 1 self-review = 11 total under `docs/superpowers/decisions/`.
- **Reviewer fix rate:** 2 MAJOR + 1 PARTIAL across R1 Codex + R1 Sonnet + R2 Codex; all closed in-cycle via 2 fix commits.
- **CVE state:** unchanged — diskcache + ragas still no upstream fix. Zero PR-introduced CVEs.
