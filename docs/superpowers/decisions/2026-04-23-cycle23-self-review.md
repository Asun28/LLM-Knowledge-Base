# Cycle 23 — Step 16 Self-Review

**Date:** 2026-04-23
**PR:** #37 (merged `acc859d`)
**Commits on branch:** 6 (`4da9b3a`, `7302d36`, `79b8ef6`, `e9bf324`, `bbc646f`, `3f4b377`)
**Tests:** 2725 → 2743 (+18 across 4 new test files)

## Step-by-step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|---|---|---|---|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + CVE baseline | yes | no | `pip-audit` not on PATH; had to invoke via `.venv/Scripts/pip-audit` |
| 3 — Brainstorming | yes | yes | — (3 of 4 ACs had a single realistic option; Step 3 was mostly "confirm obvious picks") |
| 4 — Design eval parallel rounds | yes | yes | R1 Opus caught AC4 `_TEXT_EXTENSIONS` blocker pre-implementation; R2 Codex added `kb.query.__init__` eager-engine detail |
| 5 — Design decision gate | yes (primary, cycle-14 L1) | yes | — all 13 questions resolved inline (12 High + 1 Medium confidence) |
| 6 — Context7 | skipped (pure stdlib + internal) | n/a | — |
| 7 — Plan | yes (primary, cycle-14 L1) | yes | — |
| 8 — Plan gate | yes (inline, cycle-21 L1) | yes | zero PLAN-AMENDS-DESIGN |
| 9 — TDD impl | yes (primary, cycle-13 L2) | **no** | **5 missteps**: (a) `_TEXT_EXTENSIONS` forced pipeline load — pre-caught by R1 Opus; (b) `kb/mcp/__init__` eager-imports broke `from kb.mcp import mcp` contract — caught by R1 Codex; (c) docstring appeared AFTER imports in `kb_query` — caught on my own diff-read; (d) `_flag_stale_results` stub returned None — caught by R1 debug; (e) `.cache_info()` called on wrapper not inner cache — caught on first test run |
| 10 — CI hard gate | yes | yes | 2734 passed + 9 skipped; full suite, not isolation (cycle-22 L3) |
| 11 — Security verify | yes | **no** | I1 PARTIAL — dual-anchor containment only resolved-path checked, needed literal-path pre-check too. cycle-21 L2 reminder validated |
| 11.5 — CVE opportunistic patch | skipped | n/a | both open CVEs (diskcache, ragas) have `fix_versions: []` |
| 12 — Doc update | yes | **no** | commit count drifted 4 → 6 across R1+R2+R3 fix commits; test count 2742 → 2743 after R1 fix added 1 test (cycle-15 L4 applied) |
| 13 — PR | yes | yes | PR #37 clean |
| 14 — PR review rounds | yes (R1 Codex + R1 Sonnet + R2 Codex + R3 Sonnet) | **no** | R1 caught 2 MAJORs + 1 NIT (Codex) + 1 BLOCKER + 3 MAJORs + 2 NITs (Sonnet); R2 1 NIT; R3 2 drift NITs |
| 15 — Merge + cleanup | yes | yes | zero mid-cycle CVE late-arrivals |

## Skill patches committed (6 lessons)

Patched `C:\Users\Admin\.claude\skills\feature-dev\SKILL.md` Red Flags table with 5 new rows:

- **L1 — Docstring + function-body import ordering**: function-local `from X import Y` statements added BEFORE the closing `"""` orphan `function.__doc__`. Rule: imports go AFTER the docstring.
- **L2 — Stubs must preserve return type**: `monkeypatch.setattr(target, lambda *a, **kw: None)` breaks callers that assign the return value. Rule: read the target's return annotation; for identity-style helpers return the first positional arg unchanged.
- **L3 — Threat-model deferred-promise enforcement**: text like "will be flagged in BACKLOG as deferred follow-up" is a Step-11 contract. Rule: Step-11 security-verify prompt must grep BACKLOG.md for every "deferred / scope-out" mention in threat-model.md.
- **L4 — Count-sensitive doc fields drift across fix commits**: extends cycle-15 L4 to ALL numeric claims (commits, files, ACs, MCP tools — not just test count). Rule: re-verify every numeric claim after each R1/R2/R3 fix commit cascade.
- **L5 — Package-top re-exports depend on eager side effects**: `kb/mcp/__init__.py` eager imports existed to trigger `@mcp.tool()` decorator side effects. Removing them breaks `from kb.mcp import mcp` callers that expect tools pre-registered. Rule: PEP 562 `__getattr__` on the package is the bridge.

R1 Codex + R1 Sonnet review findings were ALL addressable via targeted fixes; no REJECT outcomes, no Step-5 re-runs, no Step-9 scope narrowing.

## What went right

- **cycle-17 L1 monkeypatch-target enumeration** prevented a naive function-body deferral from breaking `tests/test_cycle19_mcp_monkeypatch_migration.py:57`. PEP 562 chosen instead of simple function-body imports because the cycle-19 AC15 contract requires `kb.mcp.core.ingest_pipeline` as a reachable module attribute.
- **cycle-22 L1 `.data/cycle-N/` project-relative artifact sinks** prevented the Windows `/tmp/` bash-path trap.
- **cycle-22 L3 full-suite-not-isolation gate** at Step 10 caught zero new reload-leak classes (the boot-lean test uses subprocess probes which sidestep intra-pytest-session pollution).
- **cycle-17 L4 R3 trigger** (13 design-gate questions + new filesystem-write surface + new security enforcement point) fired correctly even at 8 ACs; R3 Sonnet caught 2 real drift NITs R1+R2 missed.
- **cycle-19 L4 R3 audit-doc drift** FIRST-priority check surfaced the commit-count drift that R1+R2 missed (they focus on code).
- **cycle-20 L4 background-agent hang threshold** did not fire — all agents returned within normal timing budgets this cycle.

## What was surprising enough to deserve a lesson

See L1-L5 above — all five patched into the Red Flags table.

## Cycle termination note

Cycle 23 complete. 6 commits landed on `main` via PR #37.
