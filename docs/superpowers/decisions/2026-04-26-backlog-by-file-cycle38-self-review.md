# Cycle 38 — Self-Review (Step 16)

**Date:** 2026-04-26
**Branch:** `feat/backlog-by-file-cycle38` (squash-merged at `fa528c3`)
**Cycle scope:** 11 ACs (AC0-AC10 incl. AC0 NEW for subprocess refactor + design Q5 ruff T20). Closes 2 of 5 cycle-37-deferred BACKLOG candidates: Category A 10-test mock_scan_llm POSIX reload-leak (AC1-AC5) + Category B 2-test atomic_text_write POSIX patch class (AC6 strict scope). AC7+AC8 (POSIX off-by-one slug) DEFERRED to cycle-39 per design M1 standing pre-auth.

---

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + dep-CVE baseline | yes | yes | — |
| 3 — Brainstorming | yes | yes | — |
| 4 — Design eval R1 + R2 | yes | yes | **R2 Codex BLOCKER**: cycle-37 BACKLOG hypothesis (`reload-leak class`) was factually wrong; actual contamination is `del sys.modules["kb.capture"]` in TestSymlinkGuard. Forced AC0 (subprocess refactor) addition. |
| 5 — Design decision gate | yes | yes | — |
| 6 — Context7 verification | skipped (pure stdlib) | n/a | — |
| 7 — Implementation plan | yes | yes | — |
| 8 — Plan gate | yes | no (REJECT) | Codex flagged 3 findings: T2 mapped to AC0-grep instead of sibling-leak; T6 mapped to vague "CI green"; Step-10 mirror missing 4 ci.yml steps + wrong pip-audit args. **Resolved inline per cycle-21 L1** (operator held context). |
| 9 — Implementation TDD | yes | no | **AC5 case (b) iteration**: original sys.modules-deletion replay was full-suite-fragile (passed in isolation, failed under collection ordering); switched to order-independent contract assertion. **AC7+AC8 scope-cut**: invoked design M1 standing pre-auth — POSIX investigation needs deeper shell access than this cycle had. |
| 9.5 — Simplify pass | skipped (<50 LoC src) | n/a | — |
| 10 — CI hard gate (full local mirror) | yes | yes | — |
| 11 — Security verify + PR-CVE diff | yes | yes | — |
| 11.5 — Existing-CVE patch | yes (no-change branch) | yes | AC9 expected no-change branch fired: pip-audit drift unchanged. |
| 12 — Doc update | yes | yes | — |
| 13 — Branch finalise + PR | yes | yes | — |
| 14 — PR review R1 | yes | no | **R1 Sonnet MAJOR**: AC5 case (b) had vacuous-pass risk if a prior fixture had patched utils.llm — `real_call = kb_utils_llm_mod.call_llm_json` captured the already-patched value. Fixed in-cycle per cycle-12 L3 by capturing pre-mock identity of BOTH sites. R1 Codex APPROVED. |
| 14 — R2 Codex verify | primary-session per cycle-36 L2 | yes | — |
| 14 — R3 | skipped | n/a | Below cycle-17 L4 thresholds (11 ACs ≤ 25; ≤5 src files; no new write surface; ≤10 design questions). |
| 15 — Merge + CVE warn | yes | yes | Late-arrival CVE check: same 4 alerts as Step-2 baseline. ZERO new advisories during cycle. |
| 16 — Self-review | (this doc) | n/a | — |

**Cycle CI runs**: 2 (PR open + R1 fix). Both green. ZERO failed CI runs visible to user. Aligns with cycle-37 L1 zero-failed-runs target.

**Wall time**: `/feature-dev` invocation → merge ≈ 4 hours (longer than cycle 37's ~50 min due to design-eval round-trip on the hypothesis correction + R1 PR review + R1 follow-up fix).

---

## Lessons (skill patches)

Four lessons extracted. Append to `references/cycle-lessons.md` under `## Cycle 38 skill patches (2026-04-26)`.

### C38-L1 — Hypothesis-correction loop: R2 Codex's grep-verify checks BACKLOG narrative, not just AC text

**Rule.** Step-4 R2 Codex eval should grep-verify the cycle's *root-cause hypothesis* against the codebase BEFORE accepting the AC list — not just verify each AC's cited symbols exist. BACKLOG entry text from prior cycles can encode incorrect causal claims that survive into the current cycle's requirements.

**Why.** Cycle-37 BACKLOG entry attributed Category A `mock_scan_llm` failures to a "reload-leak class (cycle-19 L2 / cycle-20 L1)" matching `importlib.reload(kb.config)` cascade. The cycle-38 requirements doc inherited this hypothesis verbatim. R2 Codex's Step-4 review verified at `src/kb/config.py:3-9` that `kb.config` imports only stdlib (no `kb.utils.llm` reference); reloading it CANNOT cascade. The actual contamination source is `del sys.modules["kb.capture"]` + reimport in `TestSymlinkGuard` at `tests/test_capture.py:700-714`. Without R2's hypothesis-level grep, the cycle would have shipped a fix (dual-site patch only) that wouldn't fully address the contamination — `tests/test_capture.py`'s pre-collection bindings still hold OLD module function objects whose `__globals__` is the OLD `__dict__`, and dual-site patching of `sys.modules["kb.capture"]` doesn't reach OLD `__dict__`.

**How to apply.** Step-4 R2 Codex prompts must include: "Verify the cycle's stated root-cause hypothesis against the codebase. Read the cited code and trace the data/control flow. If the hypothesis cites a `reload`/`from-import` cascade, grep the importer for the imported symbol and confirm the cascade actually fires. Output `HYPOTHESIS-CONFIRMED` or `HYPOTHESIS-REFUTED: <evidence>` as a top-line verdict before scoring ACs." Without this prompt addition, R2 verifies only AC-cited symbols and may miss hypothesis-level errors.

**Refines cycle-15 L1** (grep-verify every cited symbol BEFORE scoring AC). C15-L1 was symbol-level; C38-L1 elevates to hypothesis-level: "verify the WHY, not just the WHAT."

**Self-check at Step 4 dispatch.** R2 prompt template now requires hypothesis-verification block. Add to feature-dev SKILL.md Step-4 section.

### C38-L2 — Order-independent assertions over scenario-replay for full-suite-fragile contracts

**Rule.** When a regression test must pin a contract that involves global state (sys.modules, monkeypatch order, fixture proliferation), prefer an *order-independent contract assertion* (capture pre-state + post-state identities, assert change) over a *scenario replay* (recreate the contamination). Scenario replays are full-suite-fragile under collection ordering; identity-change assertions are order-independent and revert-tolerant.

**Why.** Cycle-38 AC5's first iteration (per Step-5 design gate CONDITIONS §3) replayed the cycle-36 contamination via `monkeypatch.delitem(sys.modules, "kb.capture")` + `importlib.import_module`. Passed in isolation. Failed under full-suite collection ordering — sibling tests' state leaked through. Switched to order-independent: capture pre-mock identity of BOTH `kb.utils.llm.call_llm_json` and `kb.capture.call_llm_json`, install mock, assert BOTH `is not` the captured pre-mock value. Order-independent passed full-suite. R1 Sonnet then caught the FIRST iteration of this fix had a residual vacuous-pass risk: if a prior fixture had ALREADY patched utils.llm to some `X`, `pre_utils = X`, then mock_scan_llm patches to `fake_call`, assertion `fake_call is not X` passes WITHOUT cycle-38 AC1. Fix: capture pre-mock identity of BOTH sites (NOT just the AC1-specific site) and assert BOTH change.

**How to apply.** When a regression test involves "did the fixture install land?" or "did the contract apply?", prefer the pattern:
```python
pre_a = mod_a.symbol
pre_b = mod_b.symbol
fixture_under_test(...)
assert mod_a.symbol is not pre_a, "AC contract: mod_a must be patched"
assert mod_b.symbol is not pre_b, "AC contract: mod_b must be patched"
```
over `mod_a.symbol = X; do_something_that_should_break_X(); assert ...`.

**Refines cycle-22 L3** (full-suite ordering can break tests that pass in isolation). C22-L3 was reactive (debug the failure); C38-L2 is preventive (write the test order-independent in the first place).

**Refines cycle-24 L4** (revert-tolerant content-presence assertions are vacuous; need POSITION assertions). C24-L4 was about position; C38-L2 is about IDENTITY change.

**Self-check at Step 9 TDD.** When writing a regression test, ask: "Does this test depend on global state being in a specific configuration (sys.modules, monkeypatch stack, env vars)?" If yes, capture the relevant state PRE-action and assert the state CHANGED post-action — don't just assert post-action state alone.

### C38-L3 — Scope-cut at Step 9 + Step 14 R1 fix-in-cycle: cycle-12 L3 in action

**Rule.** When R1 PR review surfaces a MAJOR finding on an in-scope AC, fix it in-cycle BEFORE squash-merge per cycle-12 L3 (in-scope contract-deviation closes BEFORE Step 13). When Step 9 implementation reveals an AC needs deeper investigation than this cycle has access to, invoke design M1 standing pre-auth and scope-cut to the next cycle.

**Why.** Cycle 38 hit both:
- **Step 9 scope-cut**: AC7 + AC8 (POSIX off-by-one slug + creates_dir) needed direct POSIX shell access to instrument `_scan_existing_slugs` / `_build_slug` / `_reserve_hidden_temp` and trace the divergence. Local Windows + WSL Ubuntu (no venv install rights) couldn't reproduce. Per design M1 standing pre-auth, re-pinned to cycle-39 with concrete fix-shape ("instrument these 3 functions with diagnostic prints, push to feature branch, read CI logs").
- **Step 14 R1 fix-in-cycle**: R1 Sonnet's MAJOR on AC5 case (b) vacuous-pass risk fixed via 28-line patch (capture pre-mock identity of BOTH sites + invariant comment + subprocess encoding). Per cycle-12 L3, fix landed before squash-merge; CI re-ran green; merged.

**How to apply.**
- Step 9 — when implementation reveals "this AC needs X access I don't have", check if design has M1 (or equivalent) standing pre-auth for scope-cut. If yes, narrow scope, document in cycle-N+1 BACKLOG with concrete fix-shape, ship the rest.
- Step 14 — when R1 finds a MAJOR on an in-scope AC, default to fix-in-cycle UNLESS the fix exceeds the cycle's scope budget. If fix < ~50 LoC, fix in-cycle. If ≥ ~100 LoC or requires new tests beyond the originally-scoped surface, scope-cut to cycle-N+1 with PR-comment documentation.

**Refines cycle-12 L3** (PARTIAL on in-scope AC = contract-deviation; close BEFORE Step 13). C38-L3 adds the COMPLEMENTARY rule for Step 9: scope-cut UPSTREAM if access constraints are real.

**Self-check at Step 9 + Step 14.** Maintain explicit "fix-in-cycle vs scope-cut" decision log in the cycle's plan doc. Update at each iteration. The decision is reversible until merge.

### C38-L4 — pre-existing skipif decorators at fixture sites need to-be-loaded module imported at test-module top to defeat fixture-resolution-time imports

**Rule.** When a test file uses fixtures that monkeypatch `kb.X.Y` via dotted-path string, ensure `kb.X` is in `sys.modules` BEFORE the fixture runs by importing it at the test-module top. Otherwise `monkeypatch.setattr` triggers a fresh import of `kb.X` during fixture setup, which can fire module-import-time side effects (security guards, module-level cache initialization) against fixture-patched-but-not-yet-applied dependencies.

**Why.** Cycle 38 AC5's `tests/test_cycle38_mock_scan_llm_reload_safe.py` uses `tmp_captures_dir` fixture which does `monkeypatch.setattr("kb.capture.CAPTURES_DIR", captures)`. Without an explicit `import kb.capture` at the test-module top, isolation runs of just this file would trigger `monkeypatch.setattr` to FRESH-IMPORT `kb.capture`, which executes the module-import-time security guard at `src/kb/capture.py:832-844` (`SECURITY: CAPTURES_DIR resolves outside PROJECT_ROOT`) against the FIXTURE-patched `kb.config.CAPTURES_DIR` (tmp path) but UN-patched `kb.config.PROJECT_ROOT` (real project root). Result: spurious RuntimeError during fixture setup, test errors out.

Fix: add `import kb.capture as _kb_capture  # noqa: F401, E402` at the test-module top so `kb.capture` is loaded under the real (non-patched) PROJECT_ROOT FIRST. Subsequent fixture monkeypatches operate on the already-loaded module without triggering re-import.

**How to apply.** Test files that use fixtures monkeypatching `kb.X.Y` via string-path must:
1. Import `kb.X` at test-module top with `# noqa: F401` if not otherwise used.
2. Add comment block explaining the module-load-order invariant for future maintainers.

**Refines cycle-18 L1** (snapshot-bind hazard in tests — module-level `from X import Y` captures Y's current value at import time). C18-L1 was about RUNTIME binding drift; C38-L4 is about FIXTURE-SETUP-time binding drift triggering import-time side effects.

**Self-check.** When creating a NEW test file that uses `mock_scan_llm` / `tmp_captures_dir` / similar fixtures targeting `kb.capture` or other modules with import-time side effects, run the test in isolation (`pytest <newfile> -v`) BEFORE running the full suite. If isolation errors out at fixture setup with a "SECURITY:" RuntimeError, add the missing top-of-file import.

---

## Step 16 — Index entries to add to `references/cycle-lessons.md`

Add at the TOP under `## Cycle 38 skill patches (2026-04-26)`:
- C38-L1 — Hypothesis-correction loop (refines cycle-15 L1)
- C38-L2 — Order-independent assertions over scenario-replay (refines cycle-22 L3 + cycle-24 L4)
- C38-L3 — Step 9 scope-cut + Step 14 fix-in-cycle (refines cycle-12 L3)
- C38-L4 — Test-module-top import to defeat fixture-resolution-time fresh import (refines cycle-18 L1)

## Step 16 — Index entries to add to SKILL.md

Append one-line pointers to "Accumulated rules index" under appropriate concern areas:

- **Test authoring** — `C38-L2 — order-independent identity-change assertions over scenario-replay (refines C22-L3 + C24-L4)`
- **Test authoring** — `C38-L4 — explicit kb.X import at test-module top defeats fixture-resolution-time fresh import (refines C18-L1)`
- **Subagent dispatch and fallback** — `C38-L1 — R2 Codex must verify root-cause hypothesis, not just AC-cited symbols (refines C15-L1)`
- **Scope and same-class peers** — `C38-L3 — Step 9 scope-cut on access-blocked ACs + Step 14 R1 MAJOR fixes default to in-cycle (refines C12-L3)`

---

## Final cycle stats

- **AC count**: 11 (AC0-AC10) + design Q5 (ruff T20)
- **Files shipped**: 4 test files + 1 conftest + 1 pyproject.toml + 1 BACKLOG.md + 5 doc-routing files (CHANGELOG.md / CHANGELOG-history.md / CLAUDE.md / docs/reference/{implementation-status,testing}.md) + 10 cycle-38 decision artifacts
- **Test count delta**: 3012 → 3014 (+2 cycle-38 regression tests; +12 unskipped on Windows where 10 used to require real API key + 2 used to be Windows-only)
- **Commits on branch**: 6 (subprocess refactor + design docs + main implementation + R1 fix + R1 review docs + post-merge backfill); squash-merged to main at `fa528c3`
- **CI runs**: 2 (both green)
- **Subagent dispatches**: 5 (Step-2 threat model, Step-4 R1 Opus, Step-4 R2 Codex, Step-5 design gate, Step-7 plan gate, Step-14 R1 Codex, Step-14 R1 Sonnet) — all primary-decision plus the parallel R1 dual reviewers
- **Hypothesis correction**: 1 (R2 Codex flipped reload-leak → sys.modules deletion at Step 4)
- **Plan-gate REJECT resolved inline**: 1 (cycle-21 L1 — 3 findings inline-amended)
- **R1 fixes shipped before squash-merge**: 1 MAJOR + 2 MINOR (cycle-12 L3)
- **Scope-cuts via M1 standing pre-auth**: 2 ACs (AC7 + AC8 deferred to cycle-39)
- **Late-arrival CVEs**: 0 (Dependabot drift unchanged)
- **Net BACKLOG change**: -2 resolved cycle-38 entries deleted; +5 cycle-39+ candidates re-pinned with refresh date 2026-04-26 (4 carried over from cycle-37 deferral + 1 new fold-into-canonical entry per design Q7)
