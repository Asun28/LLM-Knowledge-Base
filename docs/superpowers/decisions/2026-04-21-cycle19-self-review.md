# Cycle 19 — Step 16 Self-Review

**Date:** 2026-04-21
**Merged PR:** [#33](https://github.com/Asun28/llm-wiki-flywheel/pull/33) — 9 commits, 2592 → 2639 collected (+47 tests, 2631 passing).
**Scope:** 23 production ACs across 6 source files — `inject_wikilinks_batch` (closes cycle-17 AC21 / cycle-18 deferral), `manifest_key_for` + dual-write threading + traversal validation, `refine_page` two-phase write + `list_stale_pending`, MCP monkeypatch migration to owner modules (13+17=30 sites total / 12 test files), AC18 forward-looking lint guard, AC14-anchor regression test, `kb.capture` lazy-load fix (cycle-15 reload leak).

## Scorecard (Steps 1–15)

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | Clean 20 ACs from BACKLOG; cycle-19 candidates + 2 HIGH bundled. |
| 2 — Threat model + CVE baseline | yes | NO — minor pip-audit env friction | Threat-model Opus subagent surfaced 5 threats (1 HIGH, 3 MED, 1 LOW). pip-audit failed with `--disable-pip` (Windows venv-resolver conflict, same as cycle-18 L0); fell back to installed-venv scan. CVE baseline unchanged: 1 diskcache CVE, no upstream patch. |
| 3 — Brainstorming | yes | yes | 12 design decisions + 15 open questions enumerated in-session per autonomous mode. |
| 4 — Design eval R1 Opus + R2 Codex parallel | yes | yes | R1 Opus: 1 BLOCKER (AC10 lock-flip unjustified) + 9 MAJORs; R2 Codex: 0 BLOCKERs + 5 MAJORs (M1 dual-write, M2 pending recovery, M3 under-lock re-derive, M4 platform-neutral test, M5 per-title length cap) + 2 NITs. AC15 monkeypatch enumeration cleared (13 sites / 7 files, no spooky patterns). Symbol-verification gate caught AC14 already-shipped + AC17 file-count mismatch. |
| 5 — Design decision gate | yes | yes | 23 production ACs finalised: AC10 WITHDRAW (preserve cycle-1 H1 lock order), AC14 DROP with test-anchor retention (cycle-15 L2 rule), AC1b/AC4b/AC8b added per R2 findings, AC12 revised for dual-write + traversal hardening. |
| 6 — Context7 verification | SKIPPED | n/a | Pure stdlib + internal code — no new external library. |
| 7 — Plan (primary session) | yes | yes | 6 task clusters / 6 commits drafted in primary per cycle-14 L1 heuristic (≥15 ACs + full Steps 1-5 context). |
| 8 — Plan gate | yes | NO — 5 amendments | Codex plan-gate REJECT-WITH-AMENDMENTS: TASK 2 wrong `_check_and_reserve_manifest` call shape, T2 null-byte sanitizer missing, AC17 file-count was wrong (re-grep showed zero true intersections — DROP per cycle-17 L3 with AC18 lint retained), T3 docstring missing, conditions revert-checks not explicit. All 5 amendments applied inline before Step 9. |
| 9 — Implementation (TDD) | yes | NO — 4 mid-course corrections | (a) Cycle-15 `importlib.reload(kb.config)` snapshot leak through `kb.capture._PROMPT_TEMPLATE` import-time read; fixed by lazy `_get_prompt_template()` cached helper. (b) MCP migration string-grep found 13 sites; AST-style `monkeypatch.setattr(core_mod, "X", ...)` patterns added another 17 sites across 6 more test files. (c) cycle-19 vacuity test failed under full suite due to mcp_core.ingest_pipeline pointing at a different module object after cycle-15 reload — fixed by patching via `mcp_core.ingest_pipeline` reference directly + RAW_DIR/PROJECT_ROOT explicit patches. (d) `_run_ingest_body` signature needed `manifest_ref` kwarg added (caught by ruff F821 after splitting body refactor — same shape as cycle-18 L2 telemetry envelope rule applied to data threading). |
| 10 — CI hard gate | yes | yes | 2631 passed / 8 skipped / ruff clean / format clean. |
| 11 — Security verify | yes | yes | Codex APPROVE — all 5 threats IMPLEMENTED, same-class peer scan clean (linker.py new constants are immutable numerics; cycle-18 L1 doesn't apply). |
| 11.5 — Existing-CVE patch | SKIPPED | n/a | Only diskcache `CVE-2025-69872`; no patched upstream; in BACKLOG. |
| 12 — Doc update | yes | NO — CLAUDE.md edit needed re-attempt | Doc agent updated CHANGELOG + BACKLOG inline; CLAUDE.md edit failed once due to Read-before-Edit requirement after BACKLOG changed; second pass succeeded. |
| 13 — Branch finalise + PR | yes | yes | PR #33 opened with full review trail. |
| 14 — PR review rounds | yes | NO — 3 rounds (mandatory) | R1 Codex REQUEST-CHANGES (1 MAJOR: under-lock candidates-vs-sorted_chunk; 1 NIT: docstring contradiction). R1 Sonnet APPROVE-WITH-NITS (1 NIT: empty manifest_key bypass). R1-fix `bdf32ea` closed all 3. R2 Codex APPROVE. R3 Sonnet APPROVE-WITH-NITS (1 MAJOR: threat-model T4 stale lock-order text; 3 doc NITs: AC count, BACKLOG entry, test-file count). R3-fix `a02b02e` closed all 4. |
| 15 — Merge + cleanup | yes | yes | PR #33 merged at 9788103. Local branch deleted. 0 late-arrival Dependabot alerts. |

**Summary**: 11 of 15 steps first-try-pass; 4 steps had structural iteration (CVE baseline infra, plan-gate amendments, impl ordering bugs, PR R1+R3 fixes). All resolved in-cycle without scope expansion.

## Lessons learned

### L1 — Module-attribute monkeypatch migration needs AST-style enumeration, not just string-grep

**What happened:** AC15's enumeration found 13 `patch("kb.mcp.core.X")` sites via string-grep. After landing the migration, 17 OTHER test failures surfaced from sites using `monkeypatch.setattr(core_mod, "X", ...)` where `core_mod` is a module reference (not a string). My initial migration plan missed this entire access pattern. Required 6 more test-file edits + 1 cycle-15 `_PROMPT_TEMPLATE` lazy-load fix to land cleanly.

**Root cause lens:** Python tests use TWO syntactically-distinct ways to monkeypatch a module's callable: (a) `patch("module.path.callable")` string form (greppable as a string literal), and (b) `monkeypatch.setattr(module_ref, "callable_name", ...)` reference form (NOT greppable as a string literal — needs AST walk OR a regex matching `setattr(\w+, "callable"`). Migrations that only count form (a) UNDER-COUNT the work by ~2× in test suites that mix both styles.

**Skill patch (feature-dev Step 4 — monkeypatch enumeration extension):**

> When evaluating ANY MCP / module monkeypatch migration AC (cycle-17 L1 enumeration rule), the R1 Opus design-eval prompt MUST enumerate BOTH patterns, not just string-grep:
> 1. `rg "patch\(\"<module>\.<callable>\"" tests/` (string form)
> 2. `rg "monkeypatch\.setattr\([^,]*,\s*\"<callable>\"" tests/` (reference form via module variable)
> 3. `rg "setattr\([^,]*,\s*\"<callable>\"" tests/` (broader — catches both `monkeypatch.setattr` and bare `setattr` if used)
>
> Sum all three pattern counts before sizing the migration AC. If the reference-form count exceeds 50% of the string-form count, the migration MUST split into two ACs: (a) production code refactor + tests-with-string-form, (b) tests-with-reference-form (separate commit, easier to review). Cycle 19 example: string-form found 13 sites; reference-form found 17 more in 6 separate files — ~2× the migration work.

### L2 — Import-time `read_text` from a `kb.config`-derived path is a reload-leak hazard

**What happened:** `kb.capture` had `_PROMPT_TEMPLATE = (TEMPLATES_DIR / "capture_prompt.txt").read_text(encoding="utf-8")` at module top. `TEMPLATES_DIR = PROJECT_ROOT / "templates"` resolves at `kb.config` import time. Cycle-15 `test_no_incremental_out_dir_outside_project_rejected` does `monkeypatch.setenv("KB_PROJECT_ROOT", tmp)` + `importlib.reload(kb.config)` + `importlib.reload(kb.cli)`. The reload chain re-executed `kb.capture`'s module-top code under the contaminated TEMPLATES_DIR snapshot — leaving a `FileNotFoundError` cached in `kb.capture._PROMPT_TEMPLATE`. ANY subsequent test importing `kb.mcp.core` (which transitively imports `kb.capture`) crashed with the stale path.

**Root cause lens:** Cycle-18 L1 codified "use `import module; module.ATTR` instead of `from module import ATTR` for paths read at call time." Cycle 19 extends the rule to a related but distinct case: ANY module-top FILE I/O whose path is derived from a `kb.config` constant must be lazy. The cycle-18 rule covered NEW helpers reading paths at call time; the cycle-19 extension covers EXISTING module-top file reads that survive sibling-module reloads.

**Skill patch (feature-dev Red Flags — extend cycle-18 L1):**

> "My module has `_CACHED_FILE = (CONFIG_PATH / 'something').read_text()` at module top, paths come from kb.config" → **Reload-leak hazard.** Cycle-18 L1 covered NEW helpers; this extends to EXISTING module-top file reads. If ANY downstream test does `importlib.reload(kb.config)` (or any sibling-module reload that triggers re-execution of YOUR module's top-level code), the contaminated path snapshot caches the failure. Rule: any module-top `read_text()` / `read_bytes()` / `open()` whose path derives from `kb.config.X` MUST be wrapped in a lazy `_get_X()` cached helper. Self-check: grep `src/kb/` for `\.read_text\(\)|\.read_bytes\(\)|^\s*open\(` patterns at module top (NOT inside `def` blocks). Each one is a candidate. Cycle 19 example: `kb.capture._PROMPT_TEMPLATE` survived for 2 cycles before cycle-15's reload exposed the bug; lazy-load fix is 5 lines.

### L3 — `or`-chain validation skips falsy values; explicit empty-check must come FIRST

**What happened:** R1 Sonnet caught that `manifest_key=""` passed all 4 traversal checks: `".." in ""` is False, `"".startswith("/")` is False, `"\x00" in ""` is False, `len("") <= 512` is True. The `if X or Y or Z or W:` validation chain only fires when at least one check returns True; for empty string ALL return False. The fix `if not manifest_key or ...` adds an explicit empty-check as the first condition.

**Root cause lens:** This is a class of validation bug specific to `or`-chained attribute presence checks. `X in s` is False on empty `s`; `s.startswith(prefix)` is False on empty `s`; `len(s) > N` is False on empty `s`. So an `or` chain of "pattern present" checks always returns False on empty input. The fix is mechanical: add `not s` (or `not s.strip()`) as the first OR clause when the validator's INTENT is "reject suspicious values" (because empty IS suspicious as a dict key / filename / identifier).

**Skill patch (feature-dev Red Flags):**

> "I added a validator `if PATTERN1 in s or s.startswith(PREFIX) or '\\x00' in s or len(s) > N: raise` — defensive enough" → **`or`-chain skips empty input.** Every "pattern present" check (`in`, `startswith`, `>` length) is False on empty string. The `or` chain therefore PASSES `""` even though the validator's intent is to reject suspicious values (and an empty dict key / filename / identifier IS suspicious). Rule: any `or`-chain validator on a string MUST start with an explicit emptiness check: `if not s or PATTERN1 in s or ...`. Self-check: grep new `if .* in .* or .*startswith.* or` chains in the diff; confirm `not <var>` appears as the FIRST clause when the validator's intent is rejection (not "extract metadata"). Cycle 19 example: `manifest_key=""` was rejected only after R1 Sonnet caught the bypass.

### L4 — R3 catches synthesis-level audit-doc drift that R1/R2 architectural lenses miss

**What happened:** R1 Codex reviewed architecture/contracts and found 1 MAJOR + 1 NIT in code. R1 Sonnet reviewed edge-cases/security and found 1 NIT in code. R2 Codex verified the R1 fix landed cleanly. None of them looked at the threat-model.md document — which still described the WITHDRAWN history-FIRST lock flip as the AC10 mitigation. R3 Sonnet's synthesis-level cross-check caught this: the threat-model doc as a long-lived audit artifact would have misled a future maintainer into flipping the lock order and reintroducing the T4 liveness regression.

**Root cause lens:** The cycle-17 L4 R3-mandatory trigger criteria ("≥15 ACs + new security enforcement" etc.) capture the right DEPTH justification, but the value of R3 is its different LENS: synthesis across docs+code, not just code review. R1/R2 reviewers are scoped to PR-diff code; R3 should explicitly scope to "audit-doc consistency + cross-cluster contract drift + test-count integrity." Cycle 19's R3 prompt happened to include "synthesis-level inconsistencies between docs and code" as the first focus area — which is what caught the T4 drift.

**Skill patch (feature-dev Step 14 R3 prompt template extension):**

> When R3 fires per cycle-17 L4 trigger criteria, the dispatch prompt MUST include an explicit "audit-doc drift" focus area as the FIRST item (NOT last). Required checks:
> 1. Threat-model.md mitigations match what shipped (especially when Step-5 design gate WITHDREW or AMENDED the original mitigation — the threat-model paragraph is often left stale).
> 2. Design.md AC count matches CHANGELOG.md Quick Reference count.
> 3. CHANGELOG.md narrative test-file count matches `git log --oneline --diff-filter=A -- tests/` count.
> 4. BACKLOG.md cleanup matches lifecycle rule (resolved items deleted, not strikethrough; HIGH-Deferred entries that shipped removed).
>
> Rationale: R1 (architecture + edge-cases) and R2 (verify-fixes) are PR-diff scoped — they read CODE, not AUDIT DOCS. Cycle-19 R3 caught a threat-model T4 stale-text MAJOR that would have survived to cycle 20 and misled the next maintainer. The audit-doc-first prompt structure makes this catch reliable instead of incidental.

## Metrics

- Step count: 15 of 15 executed (Step 6 + Step 11.5 documented skips).
- First-try-pass steps: 11 of 15.
- Total commits: 9 (6 cluster commits + 1 R1-fix + 2 doc updates).
- New tests: +47 (2592 → 2639 collected; 2631 passing + 8 skipped).
- New test files: 7 (`test_cycle19_inject_wikilinks_batch`, `test_cycle19_manifest_key_consistency`, `test_cycle19_refiner_two_phase`, `test_cycle19_mcp_monkeypatch_migration`, `test_cycle19_lint_redundant_patches`, `test_cycle19_prune_base_consistency_anchor`, `test_cycle19_inject_batch_e2e`).
- PR review rounds: R1 Codex+Sonnet parallel → R1 fix → R2 Codex → R3 Sonnet → R3 fix (3/4 R3 triggers fired).
- Design-gate questions resolved: 26 (R1 Opus 9 MAJORs + R2 Codex 5 MAJORs + 12 brainstorm-Q + 11 requirements-Q = 37 distinct questions; deduplicated synthesis = ~26 unique).
- Plan-gate amendments: 5 (TASK 2 call shape, T2 null-byte, AC17 DROP, T3 docstring, revert-checks).
- Deferred ACs filed to cycle 20: 2 (`list_stale_pending` sweep tool, Windows tilde-path test fixture).
- CVE drift post-merge: 0.

## Cycle termination

Cycle 19 is COMPLETE. PR #33 merged at 2026-04-21T~16:21Z (commit `9788103`); local branch deleted; 0 post-merge Dependabot alerts; 4 skill lessons captured (L1-L4) ready to patch into `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md` Red Flags table.
