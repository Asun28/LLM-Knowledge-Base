# Cycle 31 — Step 16 Self-Review

**Date:** 2026-04-25
**Merge commit:** `e02a8d3`
**PR:** #45
**Commits:** 10 on feature branch (8 implementation + 1 R1 fix + 1 post-merge doc is TBD).

---

## Step scorecard (1-15)

| Step | Executed? | First-try? | Surprise / note |
|------|-----------|------------|-----------------|
| 1 | yes | yes | — |
| 2 | yes | yes | Opus threat model returned in ~5 min with 10 threats. |
| 3 | yes | yes | 3 approaches generated; A recommended; 10 open questions. |
| 4 | yes | yes | Parallel R1 Opus + R2 Codex. R2 surfaced pre-existing silent-failure bug → scope expansion to AC8 via Step-5 Q4 Option A. |
| 5 | yes | yes | Opus gate APPROVE; 10 questions resolved; 14 CONDITIONS + 32-test target set. |
| 6 | skipped | N/A | Internal-only cycle — justified skip. **But see L1 below.** |
| 7 | yes | yes | Primary-session draft per cycle-14 L1. |
| 8 | yes | **no** | Codex plan-gate REJECT with 5 gaps; all 5 resolved inline per cycle-21 L1. |
| 9 | yes | yes | 5 TASKs landed in 5 commits. Minor: Click 8.3 `mix_stderr` removal caught at TASK 4 TDD-red→green (see L1). |
| 10 | yes | yes | GREEN (2872 passed + 10 skipped, ruff + format clean). |
| 11 | yes | yes | 10/10 threats IMPLEMENTED via primary-session mechanical verify; no Codex dispatch (cycle-13 L2 scope sized for primary). |
| 11.5 | skipped | N/A | No-op — both open CVEs have no upstream fix. |
| 12 | yes | yes | All 3 CLAUDE.md test-count narrative sites synced per cycle-26 L2. |
| 13 | yes | yes | PR #45 opened with structured review-trail body. |
| 14 | yes | **no** | R1 Sonnet APPROVE-WITH-NITS (2 MAJORs). Fix commit `ba7caca` addressed both. R1 Codex APPROVE no findings. R2 Codex APPROVE all 5 axes. R3 skipped per Q10. |
| 15 | yes | yes | Merged as `e02a8d3`; branch deleted; no late-arrival CVEs. |

**Summary:** 2 non-first-try steps (8, 14) — both resolved inline via documented patterns (cycle-21 L1 plan-gate inline; standard R1-fix commit cycle). Zero blocking surprises. Scope expanded once (Step-5 Q4 Option A → AC8) and once more mid-review (R1 Sonnet MAJOR 2 → 5 wrapper homogenization).

---

## What worked

1. **Parallel R1+R2 design eval.** R2 Codex caught the AC8 bug that R1 Opus missed — parallel dispatch is load-bearing, not redundant.
2. **Cycle-21 L1 inline plan-gate resolution.** All 5 REJECT gaps were documentation clarifications; no re-dispatch needed. Saved ~10 min.
3. **Revert-divergent test discipline (cycle-24 L4).** The 3 non-colon boundary tests + 3 AC8 retrofit tests all flip under a simple one-line revert — caught the discriminator's real contract.
4. **`+TBD` commit-count placeholder (cycle-30 L1).** No recursion drift in CHANGELOG. Post-merge backfill deferred cleanly.
5. **Step-5 Q4 scope expansion.** Turning a "nice-to-have future cycle" into an AC8 scope item closed a real silent-exit-0 bug same-day.

## What hurt

1. **Click 8.3 `mix_stderr` removal (L1 below).** Design doc Q3 prescribed `CliRunner(mix_stderr=False)`; caught only at TDD-red→green in TASK 4. ~5 min lost, zero shipping impact but avoidable.
2. **R1 Sonnet MAJOR 2 scope inconsistency (L2 below).** The initial AC8 scope deliberately limited the retrofit to 3 "known-broken" wrappers; R1 Sonnet correctly flagged the remaining 5 "safe-today" peers as a consistency gap. Fix was trivial (5 one-liners) but could have been anticipated at Step 5.
3. **Stream-assertion weakness in one boundary test (L3 below).** One test asserted on merged `result.output` instead of explicit `result.stderr`. The weaker form still caught the documented revert scenario via the exit-code guard, but failed the stream-awareness discipline the rest of the file follows.

---

## Skill patches (L1-L3)

Three lessons for `~/.claude/skills/feature-dev/SKILL.md`:

### L1 — Step 6 Context7 should NOT skip when design specifies library-API kwargs

Current skill says "Skip when pure stdlib/internal code." Cycle 31 skipped Step 6 on "internal-only CLI wrappers + click stdlib-equivalent." But the design doc Q3 prescribed `CliRunner(mix_stderr=False)` — a library-version-sensitive API. Click 8.2 removed the `mix_stderr` kwarg; my installed Click is 8.3.2; the kwarg check failed at TASK 4 TDD-red→green.

Rule: if the design decision gate (Step 5) references a specific library API pattern (named kwarg, version-specific method, deprecation-sensitive form), **Step 6 Context7 MUST run** regardless of the "internal-only" disposition. The check is cheap (one `mcp__context7__query-docs` call); the cost of catching at Step 9 is a mid-task detour + plan-doc amendment.

Concrete rule: any Step-5 decision (Q or C or AC) that cites a kwarg, constructor arg, or method call against a third-party library (`click.CliRunner`, `requests.Session`, `pathlib.Path` platform-specifics, `frontmatter.Post`, `pydantic.ConfigDict`) triggers a mandatory Step-6 library-version lookup for that specific API.

Self-check at end of Step 5: grep the design doc for `\w+\([a-z]+=[^)]+\)` (named-kwarg form) in any non-project-code context. If hits > 0, Step 6 is mandatory.

### L2 — Same-class peer homogenization during AC-scope expansion

Cycle 31 Step 5 Q4 Option A expanded scope to retrofit 3 "known-broken" wrappers to the new helper. 5 other peers (same cycle 27/30 vintage, same `kb_*` MCP-tool shape, same single-line discriminator pattern) were NOT retrofitted because their wrapped MCP tools emit only colon-form errors today (no current bug). R1 Sonnet flagged the scope split as MAJOR 2 "safe today but inconsistent." The 5-line migration cost was trivial; migration risk was zero (behaviour unchanged under colon-form); consistency benefit was concrete (future non-colon emitter additions are pre-defended; single-discriminator grep target; reduced cognitive load for readers).

Rule: when AC-scope expansion at Step 5 introduces a shared helper retrofitting N "known-broken" sites, and there are M "currently-safe-but-same-class" sites, the decision gate MUST evaluate both "defer M" AND "include M" explicitly. Default: INCLUDE M if (a) migration cost is one-liner per site, (b) existing tests cover the happy path without modification, (c) the helper is the cycle's central contract. Only DEFER M if (a) migration would require new tests, (b) the peers have different input/output contracts that might diverge under homogenization, or (c) the cycle's AC count would cross the R3-required threshold (≥25 ACs, cycle-17 L4).

Cycle 31 evidence: including M=5 would have added 0 new tests (colon-form behaviour unchanged) and 5 LOC (one line each) — net effect on PR-review burden < 5% of the cycle's total diff. Deferring M=5 created a ~30-minute R1-fix detour. INCLUDE M should have been the default at Step 5 Q4.

Self-check at Step 5 Q-resolution: for any "expand to N / defer to BACKLOG the M" question, compute the "include M" LOC + test delta. If LOC_m < 50 and no_new_tests → default INCLUDE. Cycle-31's M=5 would have scored LOC=5, no_new_tests=True, so default INCLUDE.

### L3 — Stream-aware test assertions uniformly in Click 8.3+ test files

Cycle 31's `test_cycle31_cli_parity.py` has 32 tests. 6 parity tests (`TestParityCliMcp`) correctly use `result.stdout == mcp_output + "\n"` + `result.stderr == ""` (success) / `result.stderr == mcp_output + "\n"` + `result.stdout == ""` (error). But one boundary test (`test_read_page_missing_exits_non_zero_with_page_not_found`) asserted `"Page not found:" in result.output` — `result.output` is the MERGED stdout+stderr in Click 8.3+. Under the documented revert scenario, the exit-code guard catches regression; under a hypothetical future stream-routing bug (exit 1 but error text on stdout), the merged-output assertion would PASS incorrectly. R1 Sonnet caught this MAJOR 1.

Rule: in any test file that includes Click error-path tests, **every error-path assertion must use `result.stderr` explicitly** (not `result.output`), and SHOULD additionally assert `result.stdout == ""` for clean separation. Exception: `--help` smoke tests (parser-only, no body-run) can use `result.output` because the help text is stdout-only.

Self-check at PR-review time (or during initial Step-9 TDD): grep the new test file for `result.output.*Error|result.output.*Page not found|result.output.*"Error"`. Any hit that's NOT inside a `--help` test body is a candidate MAJOR. Rewrite to `result.stderr.contains(X)` + `result.stdout == ""` pattern.

Generalises cycle-27 L2 (body-execution tests) + cycle-30 L2 (integration-boundary tests) + cycle-30 L3 (parallel assertion shape) — all three about test-assertion discipline for CLI wrappers. L3 here adds: assertion-STREAM discipline (not just shape or site).

---

## Final counts

- Tests: 2850 → 2882 (+32; all 32 pass)
- CLI commands: 19 → 22
- MCP tool count: 28 (unchanged — no new tools)
- BACKLOG parity-entry count: "~12 remaining" → "~9 remaining"
- CVE baseline: 2 open (diskcache + ragas, both no-upstream-fix — unchanged from cycle 30)
- Dependabot alerts: 1 open (ragas, sev=low, no upstream fix — unchanged)
- Commit count on feature branch pre-merge: 10 (8 implementation + 1 R1 fix + 1 post-merge doc placeholder)

**Cycle 31 complete.** PR #45 merged as `e02a8d3`. Self-review at `2026-04-25-cycle31-self-review.md`. Three skill patches (L1-L3) to land in `~/.claude/skills/feature-dev/SKILL.md`.
