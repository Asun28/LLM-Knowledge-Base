# Cycle 36 — Step 5 Design Decision Gate

**Date:** 2026-04-26
**Decision gate role:** Step-5 Opus 4.7 (1M context) decision authority
**Branch:** `feat/backlog-by-file-cycle36`
**Inputs:** Step-1 requirements, Step-2 threat model, Step-3 brainstorm, Step-4 R1 Opus eval, Step-4 R2 fallback eval (primary session after Codex hang). 22 open questions (7 brainstorm + 8 R1-NEW + 7 R2-NEW) plus AC-level amendments.

This document is the binding decision record. Step-7 implementation must follow it; Step-9 self-review uses §CONDITIONS as the test-coverage checklist; Step-11 verifier greps both this file and the marker plumbing for compliance evidence.

---

## Q1: Multiprocessing test on CI — fix vs skip

OPTIONS:
- A. Skip on CI via `skipif(os.environ.get("CI") == "true")` env-var marker.
- B. Fix the underlying GHA-Windows spawn-bootstrap divergence.
- C. Move test to a separate CI workflow with longer timeout + isolation.

## Analysis

The symptom is precisely localised by Step-2 baseline evidence: pytest collection #1155 = `test_cross_process_file_lock_timeout_then_recovery`. The test passes locally on Windows in 1.03s and was added in cycle 23 specifically to cover a class of bugs that single-process thread-based tests cannot reach. The hang surfaces only on the GHA `windows-latest` runner via `popen_spawn_win32.py:112: KeyboardInterrupt` — the parent's `child.start()` blocks at `reduction.dump(prep_data, to_child)` waiting on an unresponsive pipe. This is consistent with an editable-install `.pth` resolution issue in the spawned child, a `PYTHONNOUSERSITE` divergence, or a `kb.config` `PROJECT_ROOT` heuristic failing in the spawn-fresh interpreter. None of these is a defect in the test or in production code; all are GHA-runner environment artefacts.

Option B (fix the spawn divergence) requires reproducing the failure on a GHA runner, iterating push-test-rebuild cycles against a black-box Windows image, and likely 2-3 days of unbounded debugging. The cycle's primary deliverable is the strict CI gate (AC8) — spending the budget on a single test's spawn-bootstrap mystery would block the gate. Option C (separate workflow) is purely cosmetic; it hides the failure in a different surface without addressing it and contradicts the cycle's "make CI honest" intent. Option A preserves local coverage (every developer running `pytest -q` exercises the cross-process file-lock invariant on their actual machine, where it works), pairs with a BACKLOG entry naming the GHA-spawn divergence specifically, and aligns with the brainstorm's risk-bounded approach. R1 and R2 both AGREE; the threat model T8 mitigation #4 already names the BACKLOG follow-up.

DECIDE: A — skipif on CI.
RATIONALE: The local-skip-CI pattern preserves coverage where the test can run, defers an unbounded debugging effort that does not block the cycle's primary deliverable, and ships behind a specific BACKLOG entry. Cycle 23's design asserted local Windows verification was sufficient pre-CI; cycle 36 inherits that assertion.
CONFIDENCE: HIGH

---

## Q2: pytest-timeout default

OPTIONS:
- A. 60 s default.
- B. 120 s default.
- C. 300 s default.
- D. No global default; require per-test marker.

## Analysis

Step-1 AC3 currently says `timeout = 60`. The brainstorm Q2 amendment to 120s, R1 confirmation, and R2 slow-test enumeration all converge: the local suite runs ~50s through 1151 collected tests (≈1.7s/test average through the hang point), no test currently exceeds 1.2s in the durations sample, and `@pytest.mark.integration` is used by only 2 tests (none beyond a few seconds). 60s is plenty for any individual test even on the slowest CI runner; 120s gives 2x headroom for variance. R2's E2 also notes that `pytest-timeout` on Windows uses a thread-based interrupt mechanism (no SIGALRM) — a value too tight risks false positives if a test holds the GIL via numpy work; 120s gives breathing room there too.

Option A (60s) is borderline: it would catch hangs faster, but has zero safety margin against future tests that legitimately need 30-50s for full PageRank computation, full-wiki compile-and-lint integration tier, or vector-index build-from-scratch fixtures. R1's R1-NEW-3 and R2's E2 both flag the value mismatch between the requirements doc (60s) and the brainstorm (120s) as a pre-implementation edit obligation. Option C (300s) is too generous — a 5-minute hang is already a real bug, the developer feedback loop loses signal, and aggressive-but-safe is better than lax-but-safe. Option D (no default) defeats the purpose — the entire point of AC3 is to PREVENT a future hang from looking like the cycle-23 test (silent KeyboardInterrupt at the 6-hour job ceiling) without per-test guard work.

DECIDE: B — `timeout = 120` global default with `@pytest.mark.timeout(N)` per-test override.
RATIONALE: Catches genuine hangs in 2 minutes (well under the 6-hour GHA ceiling) while leaving 70-80x headroom over the slowest current test. Per-test override mechanism preserves escape hatch for legitimately slow integration tier. AC3 in `requirements.md` MUST be edited from `timeout = 60` to `timeout = 120` before Step 7 implementation begins (R1-NEW-3 / R2 amendment ratified here).
CONFIDENCE: HIGH

---

## Q3: Wiki-content-dependent tests — mirror-rebind monkeypatch vs skipif

OPTIONS:
- A. Mirror-rebind monkeypatch chain — patch all `WIKI_DIR` snapshot bindings.
- B. Skipif marker on production-wiki dependency.
- C. Fixture-level wiki seeding via new `populated_tmp_wiki` fixture.

## Analysis

R1's symbol verification confirms the two affected tests in `test_cycle10_quality.py` already monkeypatch `kb.review.refiner.WIKI_DIR`, `kb.compile.linker.WIKI_DIR`, and `kb.mcp.quality.WIKI_DIR`, but miss `kb.config.WIKI_DIR`. R2's E4 raises a substantive concern: the cycle-35 hotfix CI run on `windows-latest` shows these tests in collect-only output without a subsequent FAILED line — meaning the tests CURRENTLY pass on `windows-latest`. AC5 may therefore be pre-emptive coverage for the upcoming `ubuntu-latest` matrix introduction (AC12), not a fix for an active CI break. R2-NEW-3 demands clarity here.

Reading `src/kb/review/refiner.py:1-100`: the production code path is `kb_refine_page` → `refine_page` → reads `WIKI_DIR` directly from the imported `kb.config` symbol at line 32 (`from kb.config import (..., WIKI_DIR, ...)`). The current test patches the downstream re-imports but the production refiner imports `WIKI_DIR` at module top — the snapshot lives on `kb.review.refiner` (which the test ALREADY patches). The test passes on `windows-latest` because the patched binding is the one production reads. The `kb.config.WIKI_DIR` mirror is necessary only if the call chain reaches a module that reads `kb.config.WIKI_DIR` directly without re-import — `kb.utils.pages.WIKI_DIR`, `kb.graph.builder.WIKI_DIR`, `kb.graph.export.WIKI_DIR` are the candidate sites per R2's section 4. R2 verified that `_find_affected_pages` reaches `kb.compile.linker` (already patched) and that `kb_affected_pages` calls `load_all_pages` (production) which the test stubs via `monkeypatch.setattr("kb.mcp.quality.load_all_pages", fail_load_all_pages)`. The actual production call chain stays inside the patched modules.

Option A is the cycle-19 L1 pattern; adding `kb.config.WIKI_DIR` is a 2-line change that defends against future code paths reaching the snapshot via a freshly-imported module. Even if `windows-latest` doesn't currently fail, the pattern is the canonical one for this hazard and costs ~zero implementation effort. Option B (skipif on production-wiki dependency) loses CI coverage permanently for this class of test and is the requirements doc's fallback, not the default. Option C (fixture seeding) is functionally equivalent to A at outcome level but adds new shared state to `conftest.py` — the test ALREADY uses `tmp_wiki + create_wiki_page("concepts/rag", ...)` so the seeding is already done; only the binding chain is incomplete.

DECIDE: A — mirror-rebind monkeypatch chain, adding `kb.config.WIKI_DIR` mirror to both affected tests.
RATIONALE: Cycle-19 L1 is the canonical pattern; the targeted test already uses `tmp_wiki + create_wiki_page` so wiki content IS seeded. Adding the missing `kb.config.WIKI_DIR` mirror is mechanical (~2 lines/test) and prepares for `ubuntu-latest` matrix introduction without losing CI coverage. Step-9 condition: AC5 implementation must trace the call chain (per R2-NEW-3) and add mirrors for any module-top `WIKI_DIR` import that the chain actually reaches; if the chain proves not to need `kb.config.WIKI_DIR` mirror, document the trace and DROP that mirror rather than add a no-op.
CONFIDENCE: HIGH

---

## Q4: CI dummy-key strategy for Anthropic SDK tests

OPTIONS:
- A. `requires_real_api_key()` predicate + skipif.
- B. Mock the SDK at conftest level via autouse fixture.
- C. Use a real test API key in CI via secrets.

## Analysis

R1-NEW-5 and R2's E5 both surface that grep for `anthropic.Anthropic(api_key=` in `tests/` returns ZERO direct hits. The 4 enumerated test files (`test_cycle21_cli_backend.py`, `test_v5_lint_augment_orchestrator.py`, `test_env_example.py`, `test_backlog_by_file_cycle1.py`) reach Anthropic SDK construction indirectly through fixtures or environment-driven init paths inside `kb.utils.llm`, `kb.capture`, or `kb.review` modules. The original AC6 framing assumed a literal-string callsite; the actual risk surface is broader. R2-NEW-4 asks Step-5 to rescope.

Option C is rejected on the threat model alone: it breaks the `permissions: read-all` posture (T3), introduces fork-PR leak risk, and burns API credits per CI run. Option B (autouse fixture mocking) is invasive, risks breaking tests that legitimately verify SDK initialisation shape (e.g., that the constructor accepts a particular argument), and requires SDK cooperation (the autouse must intercept the right entry point — `messages.create`, `client.messages.with_streaming_response`, etc.). The maintenance surface is large.

Option A is correctly scoped if it's understood as "any test entering code that ULTIMATELY calls `anthropic.Anthropic(...).messages.create(...)`". The helper gates on `os.environ.get("ANTHROPIC_API_KEY")` matching the dummy prefix `sk-ant-dummy-key-` (broad match) — independent of where in the call chain construction happens. The marker stops the test from entering the call chain at all when the env signals a CI dummy key. Step-9 must therefore implement AC6 as a per-test annotation strategy ("mark every test that, on a developer machine with a real key, would issue a real API call, regardless of where the construction happens in the chain") rather than the literal-string strategy ("mark every test containing `anthropic.Anthropic(api_key=`"). The 4 enumerated files are starting candidates; Step-9 must trace each to confirm fit and add or remove from the annotated set as warranted.

DECIDE: A — `requires_real_api_key()` predicate + skipif, with rescope per R2-NEW-4.
RATIONALE: Aligns with existing test-mocking pattern, no new attack surface, no SDK cooperation required. Predicate gates on env-var prefix match (`sk-ant-dummy-key-`); behaviour tests in `tests/test_cycle36_ci_hardening.py` cover unset/dummy/real-prefix cases per T7 mitigation #2. Step-9 condition: AC6 implementation traces the call chain for each of the 4 enumerated test files; tests that actually risk a real API call get the skipif; tests that don't are documented as out-of-scope rather than annotated.
CONFIDENCE: MED (HIGH on the helper/predicate approach; MED on the exact set of test files that need annotation pending Step-9 trace)

---

## Q5: Cross-OS matrix scope

OPTIONS:
- A. Skipif on the 6 enumerated tests + add matrix simultaneously.
- B. Probe `ubuntu-latest` first; enumerate from real failures; then add matrix.
- C. Defer Area D entirely to cycle 37.

## Analysis

R1-NEW-1 and R2's E9 both verify that AC11's literal enumeration is partly stale: `test_cycle10_validate_wiki_dir.py::test_validate_wiki_dir_symlink_to_outside_rejected` is already gated `skipif(sys.platform == "win32")` (POSIX-only — opposite direction from AC11). `test_phase45_theme3_sanitizers.py::test_qb_symlink_outside_raw_rejected` is already gated `os.name == "nt" and not env(ALLOW_SYMLINK_TESTS)` (POSIX-by-default opt-in). `TestExclusiveAtomicWrite` has no `os.symlink` calls (R1-NEW-2). Of the 6 enumerated tests, only 2 are unguarded and need the AC11 skipif: `test_cycle11_utils_pages.py::test_page_id_normalizes_backslashes_to_posix_id` (Windows backslash semantics) and `test_v0915_task09.py::TestValidatePageIdAbsoluteCheck::test_absolute_path_rejected` (Windows-style absolute paths). R2 also surfaces additional unguarded sites that may need POSIX-only or Windows-only guards: `test_backlog_by_file_cycle1.py:622`, `test_backlog_by_file_cycle2.py:149`, `test_capture.py:682`, `test_cycle19_manifest_key_consistency.py:283/307`. Whether these need guards depends on actual probe results — guessing risks both false-skipif (loses coverage) and false-no-skipif (CI breaks).

Option A trusts a partly-stale enumeration and ships skipif markers in the wrong direction for two of six listed tests. Option C defers the Area D BACKLOG entry to cycle 37, breaking the cycle-36 stated purpose ("close the three explicit cycle-36 BACKLOG items"). Option B is data-driven: a probe push to a feature branch with `runs-on: ubuntu-latest` (single OS, not matrix) for one CI run reveals the actual failure set in ~5-10 CI minutes. The skipif additions are then made against actual failures rather than guesses, the matrix is added in a follow-up commit on the same branch, and AC11's enumeration becomes "the data-driven list from the probe run" rather than the partly-stale literal list.

R1's "Recommendation" says AGREE-STRONG for B; R2 reinforces with the additional unguarded sites enumeration. The probe approach also doubles as detection for the threat model T6 concern (POSIX-specific code paths exposed to the matrix that were never tested before — the production `_validate_path_under_project_root` is platform-agnostic, but undiscovered failures are by definition undiscovered).

DECIDE: B — probe `ubuntu-latest` first; enumerate from real failures; then add matrix.
RATIONALE: AC11's literal list is partly stale (verified by R1+R2 grep); a probe run replaces guesswork with data in ~5-10 CI minutes, surfaces additional fragility classes if any, and bounds blast radius. Step-9 condition: AC11 enumeration is REPLACED with the probe-driven list (R1-NEW-1 ratified). Step-9 must produce TWO distinct lists — anti-Windows-skipif (`skipif(sys.platform == "win32")` for POSIX-only tests) and anti-POSIX-skipif (`skipif(sys.platform != "win32")` for Windows-only tests) — per R2-NEW-5. If the probe surfaces >10 new fragility classes beyond the 2 confirmed unguarded tests, file BACKLOG entries for cycle-37 follow-up rather than expanding cycle-36 scope (per AC13 instruction).
CONFIDENCE: HIGH

---

## Q6: Requirements split-file structure

OPTIONS:
- A. Self-contained per-extra files.
- B. Layered: each extra file uses `-r requirements-runtime.txt`.
- C. Generate from pyproject + requirements.txt via tooling.

## Analysis

This question is conditional on Q7. If Q7 = B (drop Area E), this question becomes moot for cycle 36 and merely informs the cycle-37 BACKLOG entry shape. The brainstorm's preferred answer is B (layered) on the merits independent of timing: it avoids pin duplication across 6 files, matches `pip install` semantics, is trivial to maintain by hand, and aligns with the cycle-35 L8 lesson (single source of truth for floor pins). Self-contained files (A) duplicate the runtime pin set 5+ times, multiplying drift risk surface (T4 in threat model). Tool-generated files (C) introduce a new script to maintain — over-engineered for a use case where users want one of four canonical install paths.

Per Q7 below, Area E is dropped from cycle 36. The decision here is therefore a deferred-design commitment: when cycle 37 ships Area E, the structure is layered `-r requirements-runtime.txt` includes per Option B. This is captured as a BACKLOG entry shape so Step-11 verify can grep for it.

DECIDE: B — layered `-r requirements-runtime.txt` includes (deferred to cycle 37 per Q7).
RATIONALE: Avoids pin duplication, matches `pip install` semantics, minimises drift surface (T4). Decision is documented but not implemented in cycle 36. BACKLOG entry shape: "**Phase 4.5 — Requirements split (deferred from cycle 36)** — Generate `requirements-runtime.txt` + 5 per-extra files (`requirements-{hybrid,augment,formats,eval,dev}.txt`) using layered `-r requirements-runtime.txt` includes per cycle-36 design Q6. README install-section update follows. Cycle-35 L8 floor pin (`langchain-openai>=1.1.14`) must appear in `requirements-eval.txt`."
CONFIDENCE: HIGH

---

## Q7: Cycle scope cap

OPTIONS:
- A. All 27 ACs — full closure of all three cycle-36 BACKLOG entries + opportunistic CVE recheck.
- B. Drop Area E (requirements split) — 23 ACs covering A/B/C/D/F/G.
- C. Drop Area D AND E — 20 ACs focusing only on strict-gate closure.

## Analysis

Cycle-19 L4's R3 trigger fires at >=15 ACs when (a) new filesystem-write surface, (b) hard-to-reach defensive check, (c) new security enforcement point, OR (d) >=10 design-gate questions resolved. None of (a)-(c) apply to cycle 36 (test+CI infrastructure only, no production-code mutations). Criterion (d) clearly applies — 22 questions plus AC-level amendments puts this well over 10. R3 review will fire regardless of A/B/C choice.

Option A's risk surface is large: AC14-AC17 introduce 5 new `requirements-*.txt` files (T4 drift surface), require a new parsing test in `test_cycle36_ci_hardening.py`, force a README install-section overhaul, and need cross-validation with `pyproject.toml` extras for each file. Net: ~7 ACs for documentation-side improvement with no CI/test impact, in a cycle whose primary deliverable is the strict CI gate. Option C drops Area D, breaking the cycle's stated purpose of closing the cross-OS portability BACKLOG entry — that's a regression of intent. Option B threads the needle: ships A+B+C+F+G (16 must) plus D (3 ACs for cross-OS closure), defers E (4 ACs) to cycle 37 with a specific BACKLOG entry. Total ≈ 23 ACs — still triggers R3 review on (d), but bounds blast radius to test+CI changes only.

R1 and R2 both AGREE on Option B. The Q7=B decision cascades: Q6 deferral, AC14-AC17 dropped from cycle 36, AC26 (README install update) dropped, the parsing test in `test_cycle36_ci_hardening.py` for `requirements-*.txt` ↔ `pyproject.toml` extras consistency dropped (per R1-NEW-Q6).

DECIDE: B — drop Area E; ship A+B+C+D+F+G (~23 ACs).
RATIONALE: Areas A+B+C are inseparable for the strict gate. Area F (CVE recheck) is opportunistic and prevents cross-cycle drift. Area D closes the explicit cycle-36 BACKLOG entry on cross-OS portability. Area E is documentation-side only with no test/CI impact; deferring costs a BACKLOG entry and saves 5-7 new files of drift surface. R3 review fires on criterion (d) regardless — 3-round PR review per `feedback_3_round_pr_review.md` is the right gating posture (cycle-22 L5 + cycle-34 L5).
CONFIDENCE: HIGH

---

## Q8 (R1-NEW-1): AC11 enumeration is partly mis-directional

OPTIONS:
- A. Keep AC11's literal enumeration as a starting point; add probe-augment.
- B. REPLACE AC11 with AC13's probe-driven list.

## Analysis

R1's grep evidence is decisive: 2 of the 6 listed tests are already gated in the OPPOSITE direction from AC11's prescription. Keeping the literal list (Option A) means Step-7 implementation either skips inspection (mis-applies skipif markers) or re-checks each entry (duplicates the probe work). Option B is the cleaner outcome and is what Q5 already commits to. This is a confirmation of Q5=B's downstream effect.

DECIDE: B — replace AC11 with AC13's probe-driven list.
RATIONALE: Eliminates the mis-directional enumeration; AC11 becomes "TBD pending probe" until AC13 surfaces the real list. Implementation step ordering is probe → enumerate → fix, not enumerate-from-stale-list → fix → probe.
CONFIDENCE: HIGH

---

## Q9 (R1-NEW-2): TestExclusiveAtomicWrite has no os.symlink calls

OPTIONS:
- A. Drop `TestExclusiveAtomicWrite` from AC11.
- B. Keep it on AC11 for symmetry.

## Analysis

R1's read of `tests/test_capture.py:693-731` confirms the class uses `tmp_captures_dir`, `_exclusive_atomic_write`, and `os.replace` monkeypatches — no symlink ops, no Windows-privileged calls. The privileged-symlink rationale at AC11 line 70 does not apply. The actual symlink-bearing test at `test_capture.py:674` is already correctly gated `skipif(sys.platform == "win32", reason="symlink creation requires admin on Windows")`. Keeping a no-op skipif on `TestExclusiveAtomicWrite` adds noise without value.

DECIDE: A — drop `TestExclusiveAtomicWrite` from AC11 enumeration.
RATIONALE: The privileged-symlink rationale is not applicable; the class has no symlink ops. Add a one-line note in the design implementation step that this drop is verified.
CONFIDENCE: HIGH

---

## Q10 (R1-NEW-3): AC3 60s ↔ Q2 brainstorm 120s mismatch

OPTIONS:
- A. Pre-implementation edit `requirements.md` AC3 from 60 to 120.
- B. Step-7 ratifies the amendment in-place.

## Analysis

If `requirements.md` AC3 still reads 60s when Step-7 begins, implementation will diverge from the design decision (Q2=B). The implementer either edits the requirements doc in the same commit (creating a backwards-causal artefact — the requirements doc is a sealed input by Step-7 time) or implements 60s contradicting the design. Option A is the clean fix: amend the requirements doc as part of this design-gate output, with a note in the doc that the amendment was made by Step-5.

DECIDE: A — edit `requirements.md` AC3 from `timeout = 60` to `timeout = 120` as a Step-5 amendment with provenance note.
RATIONALE: Keeps the requirements doc as a true source-of-truth for Step-7 implementation; the Step-5 amendment is recorded in the design doc (this file) and reflected in the requirements doc with a `*Step-5 amendment 2026-04-26 per Q2/R1-NEW-3*` annotation.
CONFIDENCE: HIGH

---

## Q11 (R1-NEW-4): AC7 must NOT touch the static-clock test

OPTIONS:
- A. Widen ONLY `test_over_cap_rejected_with_retry_after` (wall-clock); leave `test_over_cap_retry_after_static_clock_is_one_hour` (frozen clock) at exact equality `== 3600`.
- B. Widen both for symmetry.

## Analysis

R1's read at `tests/test_capture.py:167-175` confirms the static-clock test monkeypatches `time.time` to `1000.0` and asserts `retry_after == 3600`. With a frozen clock, no scheduler/clock-resolution variance is possible; the equality is correct as a deterministic assertion of business logic. Widening it to `<= 3601` would weaken the assertion (the production code could compute 3599.99999, which equals 3599.0 once int-rounded — still `<= 3601` true, but `== 3600` would be false). Option B trades correctness for symmetry and is wrong.

R2's E6 raises a separate concern: even `<= 3601` for the wall-clock variant may flake under extreme CI load. Two paths: widen further to `<= 3602` (Option A2), or apply `pytest.mark.flaky(reruns=3)` after installing `pytest-rerunfailures`. The latter introduces a new dep; the former is a one-character change. Step-9 should pick `<= 3602` if local probe runs show flakiness at `<= 3601`.

DECIDE: A — widen ONLY the wall-clock test; static-clock equality stays exact.
RATIONALE: Frozen clock = deterministic assertion; widening would degrade signal. Wall-clock test gets `<= 3601` initial (one-second tolerance per cycle-30 L3 same-class peer pattern). If Step-9 probe shows flakiness at 3601, widen to `<= 3602` rather than introduce `pytest-rerunfailures`. AC7 amendment: "ONLY widen `test_over_cap_rejected_with_retry_after`; verify static-clock variant remains `== 3600` exact." (R1-NEW-4 / R2-NEW-6 ratified.)
CONFIDENCE: HIGH

---

## Q12 (R1-NEW-5): AC6's literal-string assumption uncertain

OPTIONS:
- A. Re-scope AC6 to predicate-based marker (gate on env var, not on grep for `anthropic.Anthropic(api_key=`).
- B. Keep literal-string framing.

## Analysis

This is the same finding as R2-NEW-4. The grep verification shows zero direct `anthropic.Anthropic(api_key=` matches in `tests/`; SDK construction happens inside `kb.utils.llm` or `kb.capture` modules and is reached transitively. The marker correctly gates on env-var prefix match — that's the single point of control. Keeping the literal-string framing risks mis-marking tests (annotating tests with no real-API risk, leaving tests with real-API risk un-annotated). Re-scoping to "any test that, on a real-key developer machine, would enter a code path that ULTIMATELY calls the Anthropic SDK" is the correct framing.

DECIDE: A — re-scope to env-var predicate.
RATIONALE: Aligns with Q4=A. AC6 implementation strategy: (1) helper gates on `ANTHROPIC_API_KEY` matching dummy prefix; (2) Step-9 traces each of the 4 enumerated test files to determine fit; (3) annotates only tests that actually risk a real API call; (4) documents the decision per file in the test-cycle36-investigation doc. (R1-NEW-5 / R2-NEW-4 ratified.)
CONFIDENCE: HIGH

---

## Q13 (R1-NEW-6): WIKI_DIR monkeypatch surface widening for cycle 37

OPTIONS:
- A. Plan cycle-37 widening of the 200-site `WIKI_DIR` monkeypatch surface.
- B. No widening; current state is stable.

## Analysis

R1's grep tally (50 `patch(...)` callsites + 110 `monkeypatch.setattr` callsites = 204 occurrences across 45 files) shows a large but stable surface. The cycle-18/19 mirror-rebind pattern is widely understood and applied. AC5 is a targeted fix for 2 specific tests that miss `kb.config.WIKI_DIR`; the rest are correct. There is no class-wide widening obligation. Cycle-37 follow-up is unnecessary unless a future regression is discovered.

DECIDE: B — no widening; current state is stable.
RATIONALE: 204 sites, 45 files, all already follow the cycle-18/19 pattern; only 2 tests are deficient and AC5 fixes them. No cycle-37 BACKLOG entry needed for this surface.
CONFIDENCE: HIGH

---

## Q14 (R1-NEW-7): pytest-timeout interaction with mp.Event

OPTIONS:
- A. Document the interaction; rely on AC2 skipif on CI to sidestep it.
- B. Add an explicit `@pytest.mark.timeout(N)` per-test override.

## Analysis

The cycle-23 multiprocessing test uses internal mp-Event timeouts (15s + 10s + 5s = 30s typical) and is skipped on CI per AC2. With `pytest-timeout = 120` (Q2=B), the pytest timeout dominates only on hangs, not happy-path. AC2 skipif on CI sidesteps the interaction entirely on CI; locally, the test runs in 1.03s, well under both internal and pytest timeouts. Adding an explicit per-test override is unnecessary noise.

DECIDE: A — document the interaction; rely on AC2 skipif.
RATIONALE: Local test runs in 1.03s (well under both timeouts); CI skips per AC2; no false-positive risk. One-line acknowledgement in the design doc and the investigation doc satisfies the audit trail.
CONFIDENCE: HIGH

---

## Q15 (R1-NEW-8): Cycle scope at 23 ACs likely fires R3 review trigger

OPTIONS:
- A. Plan for 3-round PR review per `feedback_3_round_pr_review.md`.
- B. Single-round review.

## Analysis

Cycle-19 L4 R3 trigger fires on criterion (d) "≥10 design-gate questions resolved" — 22 open questions plus AC-level amendments resolved here puts this well over. Independent of (a)-(c), criterion (d) alone fires the trigger. `feedback_3_round_pr_review.md` says batches >25 items get 3 independent review rounds. Cycle 36 ships ~23 ACs plus 5-10 new test additions in `test_cycle36_ci_hardening.py` plus 1 new helper file plus 1 new investigation doc — total LoC delta is bounded but the conceptual surface is wide enough that R3 is the safe default.

DECIDE: A — plan for 3-round PR review.
RATIONALE: R3 trigger fires on criterion (d). Step-12 PR-review plan must dispatch 3 independent rounds (Opus / Codex / Opus or equivalent), with round-3 typically catching regressions introduced by round-2 fixes per `feedback_3_round_pr_review.md`.
CONFIDENCE: HIGH

---

## Q16 (R2-NEW-1): AC8 strict-gate landing should be a SEPARATE commit AFTER probe-clean

OPTIONS:
- A. Single PR with all changes including AC8 in one commit.
- B. Three commits in sequence on the cycle-36 branch — probe (markers + matrix without strict-gate) → fix (any probe-revealed issues) → strict-gate (AC8 drop continue-on-error).
- C. Two separate PRs (markers/matrix first, strict-gate second).

## Analysis

The chicken-and-egg risk (T9 in threat model) is real. Dropping `continue-on-error: true` (AC8) before AC1+AC2+AC3+AC5+AC6+AC7+AC11 land would block every PR including the cycle-36 PR itself. Option A (single commit) means the first CI run validates the entire stack atomically — if it fails strict on any unforeseen issue, the entire PR appears red and iterate-fix-rerun loops happen on a red branch. Option C (separate PRs) creates a sequencing dependency where PR-2 is gated by PR-1's CI run; this delays cycle-36 by one merge cycle and adds a second review burden.

Option B threads the needle: a single PR with three logical commits. Commit 1 lands all marker fixes + ubuntu probe (matrix not yet introduced; probe is a single-OS run via `runs-on: ubuntu-latest` toggle on the workflow). The first CI run validates marker fixes + ubuntu compatibility before strict-gate enforcement is enabled. Commit 2 fixes any probe-revealed issues (per Q5=B / AC13 probe-then-enumerate). Commit 3 adds matrix + drops `continue-on-error` (the strict-gate flip). If commit 3's CI run is red, it bisects to AC8 enforcement specifically, not to a tangled marker+gate change. The PR remains atomic from a review/merge perspective; the commit history is forensically clean.

R2-NEW-1 explicitly recommends this; R2-NEW-6 reinforces it. The cycle-34 L6 lesson (CI workflow steps mirror) means each commit's local probe should match its CI shape — Step-9 must verify this.

DECIDE: B — three commits in sequence on the cycle-36 branch (probe → fix → strict-gate).
RATIONALE: Bisection-friendly forensic trail; first CI run validates marker fixes before strict-gate enforcement; chicken-and-egg risk neutralised. Step-9 condition: implementation produces three commits, each with a local probe that mirrors the CI step shape it lands. R2-NEW-1 / R2-NEW-6 ratified.
CONFIDENCE: HIGH

---

## Q17 (R2-NEW-2): AC9 `--ignore-vuln` set inconsistent with Dependabot alerts

OPTIONS:
- A. Verify pip-audit actual report on CI's installed env via `pip-audit --format json`; reconcile workflow `--ignore-vuln` set + `SECURITY.md` table to match what pip-audit emits.
- B. Add all 4 Dependabot GHSAs to `--ignore-vuln` regardless of pip-audit report.

## Analysis

R2's E8 surfaces the substantive concern: workflow currently has 4 `--ignore-vuln` flags (CVE-2025-69872, GHSA-xqmj-j6mv-4862, CVE-2026-3219, CVE-2026-6587) but Dependabot reports 4 alerts (3 litellm GHSAs + 1 ragas GHSA). Only 2 of 3 litellm GHSAs are in the ignore list, and CI is currently passing pip-audit. Two hypotheses: (i) pip-audit's PyPI advisory db is not 1:1 with GitHub's GHSA db, so pip-audit may emit only certain IDs even when Dependabot lists more; (ii) pip-audit's data freshness lags Dependabot's. Without knowing what pip-audit actually emits on the live install env, adding all GHSAs (Option B) risks adding ignore flags for IDs pip-audit never reports (workflow noise; future-confusion risk). Adding only what pip-audit reports (Option A) keeps the workflow minimal and the `SECURITY.md` table 1:1 with what the gate actually evaluates.

Option A is the verification-driven approach. Step-9 must run `pip-audit --format json` (no `--ignore-vuln`) on a fresh CI-equivalent install and inspect the actual advisory IDs. The workflow `--ignore-vuln` set updates to include exactly those IDs; the `SECURITY.md` table updates to 1:1 match. If pip-audit emits an ID Dependabot doesn't (unlikely but possible), it's a Class A advisory deserving an explicit `SECURITY.md` row. If Dependabot reports an ID pip-audit doesn't (possible per the 1.5+ litellm GHSAs case), the BACKLOG carries the cross-cycle drift entry per cycle-22 L4.

DECIDE: A — verify pip-audit actual report; reconcile to match.
RATIONALE: Keeps workflow + `SECURITY.md` table synchronized to what the gate actually evaluates. Cycle-32 L2 governs the verification cadence. Step-9 condition: AC9 + AC20 implementation runs `pip-audit --format json` on the live CI-equivalent install env (e.g., `pip install -e '.[dev,formats,augment,hybrid,eval]'` then `pip-audit --format json`); the workflow `--ignore-vuln` set and `SECURITY.md` Known Advisories table are reconciled to exactly the IDs pip-audit emits; any Dependabot alert NOT in pip-audit's report gets a cycle-37 BACKLOG entry shape "**Phase 4.6 — Dependabot/pip-audit drift on `<package>` `<GHSA-id>`** — Dependabot reports the advisory but pip-audit on live install env does not; document in cycle-36 investigation, monitor for pip-audit data refresh, escalate if pip-audit catches up." (R2-NEW-2 ratified.)
CONFIDENCE: HIGH

---

## Q18 (R2-NEW-3): AC5 may be patching a non-problem

OPTIONS:
- A. Determine call chain via Step-9 trace; AC5 implements only what the trace requires.
- B. Implement full mirror-rebind regardless of trace.

## Analysis

This is downstream from Q3=A. R2's E4 raised the substantive concern that the affected tests pass on `windows-latest` CI today (per cycle-35 hotfix run). The trace I performed at Q3 showed the production refiner reads `WIKI_DIR` from `kb.config` at module top — the symbol IS the `kb.config.WIKI_DIR` snapshot. Adding the `kb.config.WIKI_DIR` mirror is correct ANYWAY because cycle-19 L1's pattern says: "patch every module that imports `WIKI_DIR` at module top from `kb.config`." The test currently patches three modules; adding the fourth (`kb.config` itself, which is the source) is the canonical pattern, not redundant.

Option A says: trace first, mirror only what the trace requires. The trace at Q3 confirms `kb.config.WIKI_DIR` is required (it's the source of the snapshot). If Step-9 trace surfaces additional sites (e.g., `kb.utils.pages.WIKI_DIR`, `kb.graph.builder.WIKI_DIR`, `kb.graph.export.WIKI_DIR` per R2's section 4), those are also added.

DECIDE: A — Step-9 trace; mirror only what the trace requires.
RATIONALE: Avoids speculative monkeypatch additions; the cycle-19 L1 pattern says mirror what the production code actually reads. Step-9 condition: AC5 implementation traces `kb_refine_page` and `kb_affected_pages` call chains; documents the trace in the test docstring or in a comment; mirrors exactly the modules the chain reaches. Document any module-top `WIKI_DIR` import that the chain does NOT reach (so future readers don't add speculative mirrors). (R2-NEW-3 ratified.)
CONFIDENCE: HIGH

---

## Q19 (R2-NEW-4): AC6 literal-string scope clarification

OPTIONS:
- A. Step-9 traces the SDK call chain in each of the 4 enumerated tests; helper-gates only those that actually risk a real API call.
- B. Keep literal-string scope.

## Analysis

This is the same finding as Q12. Re-affirming for clarity per R2-NEW-4: Step-9 must trace each test's call chain to the Anthropic SDK construction site. Tests where construction is mocked at the HTTP layer (existing pattern) need NO marker. Tests where construction reaches a real call need the marker. The 4 enumerated test files are starting candidates, not the final list.

DECIDE: A — Step-9 trace per file; annotate only those at risk.
RATIONALE: Same reasoning as Q12 (re-affirmed). Step-9 condition: AC6 implementation produces a per-file trace summary (one line per file: "annotated because X" or "not annotated because Y"); the investigation doc records the trace.
CONFIDENCE: HIGH

---

## Q20 (R2-NEW-5): AC11 enumeration must produce TWO lists

OPTIONS:
- A. Two lists — anti-Windows-skipif (POSIX-only tests with `skipif(sys.platform == "win32")`) and anti-POSIX-skipif (Windows-only tests with `skipif(sys.platform != "win32")`).
- B. Single list with implicit direction.

## Analysis

R1's grep showed 2 of 6 AC11 entries are already gated POSIX-only and 2 are unguarded Windows-only. The probe (Q5=B) will surface additional entries in either direction. A single-list framing risks mis-applying the marker direction; two distinct lists make the direction explicit and reviewable. R2-NEW-5 explicitly demands this.

DECIDE: A — two distinct lists.
RATIONALE: Eliminates direction-confusion risk. Step-9 condition: AC11 implementation produces "anti-Windows-skipif" list (tests that should NOT run on Windows; marker is `skipif(sys.platform == "win32")`) and "anti-POSIX-skipif" list (tests that should NOT run on POSIX; marker is `skipif(sys.platform != "win32")`). The investigation doc presents both lists with one-line rationale per entry.
CONFIDENCE: HIGH

---

## Q21 (R2-NEW-6): Chicken-and-egg sequencing

OPTIONS:
- A. Three-commit sequence on the cycle-36 branch (probe → fix → strict-gate).
- B. Single commit.

## Analysis

This is the same finding as Q16. Re-affirming per R2-NEW-6 for explicit sequencing commitment.

DECIDE: A — three-commit sequence on the cycle-36 branch.
RATIONALE: Same reasoning as Q16 (re-affirmed). Step-9 condition: implementation produces commits 1 (probe — markers + ubuntu single-OS without matrix without strict-gate), 2 (fix — any probe-revealed issues), 3 (strict-gate — matrix + drop continue-on-error).
CONFIDENCE: HIGH

---

## Q22 (R2-NEW-7): Test count drift after marker additions

OPTIONS:
- A. Step-12 doc update re-collects via `pytest --collect-only` after each fix-cascade and commits the methodology, deferring exact numbers.
- B. Commit specific test count claims now.

## Analysis

R2's E12 estimates ~9-13 added skips depending on the mirror-rebind-vs-skipif decisions. Q3=A (mirror-rebind for AC5) means 0 added skips for those 2 tests. Q5=B probe drives AC11 enumeration; final count depends on probe results. Q4=A's helper-gated tests add some skips on a CI environment but zero on a developer machine with a real key. Net Windows test count after all skipif additions: estimate "2985 + N (new cycle-36 tests in test_cycle36_ci_hardening.py) - M (CI-conditional skips)" where M is unknown until probe + Step-9 trace.

Per `feedback_taskcreate_zero_pad.md` cycle-23 L4 lesson: re-collect via `pytest --collect-only | tail -1` AFTER all skipif markers add. Per cycle-26 L2 (test-count narrative drift): doc updates must re-grep CLAUDE.md AND `docs/reference/testing.md` for stale counts. The methodology is committed here; the actual numbers defer to Step-12 doc update where the live `pytest --collect-only` output is the authoritative source.

DECIDE: A — Step-12 doc update re-collects; commit methodology now.
RATIONALE: Test count claims must trace to live pytest output, not to design-time estimates. Step-9 condition: do not commit test count numbers in the design doc or in commit messages; the Step-12 doc update is the single point of truth. Methodology: run `python -m pytest --collect-only -q | tail -3` after AC1+AC2+AC3+AC5+AC6+AC7+AC11 land; record the collected/passed/skipped triple in CLAUDE.md, `docs/reference/testing.md`, and `CHANGELOG.md` Quick Reference. (R2-NEW-7 ratified.)
CONFIDENCE: HIGH

---

## VERDICT: PROCEED — APPROVE-WITH-AMENDMENTS

The cycle-36 design is sound and bounded. All 22 open questions resolve to decisions that preserve blast-radius discipline and align with project principles. AC-level amendments to AC3 / AC5 / AC6 / AC7 / AC9 / AC11 / AC20 are formalised below; the requirements doc must reflect these before Step-7 implementation begins (per Q10).

## DECISIONS (per Q1..Q22)

| Q | Question | Decision | Confidence |
|---|---|---|---|
| Q1 | multiprocessing fix vs skip | A — skipif on CI | HIGH |
| Q2 | pytest-timeout default | B — 120 s + per-test override | HIGH |
| Q3 | wiki-content monkeypatch | A — mirror-rebind including `kb.config.WIKI_DIR` | HIGH |
| Q4 | CI dummy-key strategy | A — `requires_real_api_key()` + skipif (rescoped) | MED |
| Q5 | cross-OS scope | B — probe ubuntu first | HIGH |
| Q6 | requirements split structure | B — layered (deferred to cycle 37 per Q7) | HIGH |
| Q7 | cycle scope cap | B — drop Area E; ship ~23 ACs | HIGH |
| Q8 (R1-NEW-1) | AC11 mis-direction | B — replace with probe-driven list | HIGH |
| Q9 (R1-NEW-2) | TestExclusiveAtomicWrite | A — drop from AC11 | HIGH |
| Q10 (R1-NEW-3) | AC3 60s ↔ Q2 120s | A — pre-implementation edit requirements doc | HIGH |
| Q11 (R1-NEW-4) | AC7 static-clock test | A — widen ONLY wall-clock variant | HIGH |
| Q12 (R1-NEW-5) | AC6 literal-string | A — re-scope to env-var predicate | HIGH |
| Q13 (R1-NEW-6) | WIKI_DIR widening cycle 37 | B — no widening; current state stable | HIGH |
| Q14 (R1-NEW-7) | timeout × mp.Event | A — document; rely on AC2 skipif | HIGH |
| Q15 (R1-NEW-8) | scope at 23 ACs → R3 | A — plan 3-round PR review | HIGH |
| Q16 (R2-NEW-1) | AC8 separate commit | B — three-commit sequence | HIGH |
| Q17 (R2-NEW-2) | AC9 ignore-vuln drift | A — verify pip-audit actual report; reconcile | HIGH |
| Q18 (R2-NEW-3) | AC5 non-problem? | A — Step-9 trace; mirror what trace requires | HIGH |
| Q19 (R2-NEW-4) | AC6 literal scope | A — Step-9 trace per file | HIGH |
| Q20 (R2-NEW-5) | AC11 two lists | A — anti-Windows + anti-POSIX | HIGH |
| Q21 (R2-NEW-6) | chicken-and-egg | A — three-commit sequence (re-affirmed) | HIGH |
| Q22 (R2-NEW-7) | test count drift | A — Step-12 re-collect; methodology committed | HIGH |

## CONDITIONS (Step 09 must satisfy)

These are LOAD-BEARING test-coverage requirements per cycle-22 L5. Each is a discrete check Step-11 verifier will grep for.

- **C1 (Q1 / AC2).** `tests/test_cycle23_file_lock_multiprocessing.py::test_cross_process_file_lock_timeout_then_recovery` carries `@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Windows multiprocessing spawn hangs on GHA — tracked C36-investigation.md, cycle-37 candidate")`. Test still runs locally.

- **C2 (Q2 / AC3 / Q10).** `pyproject.toml` `[tool.pytest.ini_options]` has `timeout = 120`. `pyproject.toml` `[project.optional-dependencies] dev` and `requirements.txt` include `pytest-timeout >= 2.3`. The `requirements.md` AC3 line is amended from `60` to `120` with a `*Step-5 amendment 2026-04-26 per Q2/R1-NEW-3*` annotation.

- **C3 (Q3 / Q18 / AC5).** Both `test_cycle10_quality.py::test_kb_refine_page_surfaces_backlinks_error_on_failure` and `test_kb_affected_pages_surfaces_shared_sources_error_on_failure` mirror-rebind `kb.config.WIKI_DIR`. The implementation includes a Step-9 trace summary (1-3 lines per test) documenting which `WIKI_DIR` snapshot bindings the production code path actually reaches; mirrors are added for exactly those bindings.

- **C4 (Q4 / Q12 / Q19 / AC6).** `tests/_helpers/__init__.py` and `tests/_helpers/api_key.py` exist. `requires_real_api_key()` is ≤10 lines, gates on `os.environ.get("ANTHROPIC_API_KEY")` matching dummy prefix `sk-ant-dummy-key-` (broad match) OR being unset. Behaviour tests in `tests/test_cycle36_ci_hardening.py` cover unset / dummy-exact / dummy-prefix / real-prefix cases (T7 mitigation #2). Each of the 4 enumerated test files (`test_cycle21_cli_backend.py`, `test_v5_lint_augment_orchestrator.py`, `test_env_example.py`, `test_backlog_by_file_cycle1.py`) has a Step-9 trace summary in the cycle-36 investigation doc; tests confirmed to risk a real API call carry `@pytest.mark.skipif(not requires_real_api_key(), reason=...)`; tests NOT at risk are explicitly listed as out-of-scope.

- **C5 (Q5 / Q8 / Q9 / Q20 / AC11 / AC13).** Implementation produces TWO lists in the cycle-36 investigation doc: anti-Windows-skipif (POSIX-only tests; marker `skipif(sys.platform == "win32")`) and anti-POSIX-skipif (Windows-only tests; marker `skipif(sys.platform != "win32")`). Both lists are data-driven from the probe `ubuntu-latest` CI run (commit 1 of the three-commit sequence). `TestExclusiveAtomicWrite` is NOT on either list. Tests already gated correctly in either direction are listed under "already-gated; no change" with one-line provenance.

- **C6 (Q11 / AC7).** `tests/test_capture.py::test_over_cap_rejected_with_retry_after` widens to `<= 3601` (or `<= 3602` if Step-9 probe shows flakiness at 3601). `tests/test_capture.py::test_over_cap_retry_after_static_clock_is_one_hour` STAYS at `== 3600` exact equality (frozen-clock determinism preserved).

- **C7 (Q16 / Q21 / AC8).** PR ships as three commits on the `feat/backlog-by-file-cycle36` branch in this order: commit 1 (probe — markers + ubuntu single-OS via `runs-on: ubuntu-latest` toggle, NO matrix, NO strict-gate, `continue-on-error: true` STILL ON); commit 2 (fix — any probe-revealed issues); commit 3 (strict-gate — matrix `[ubuntu-latest, windows-latest]` + DROP `continue-on-error: true` from the pytest step + step-name update from "(soft-fail per cycle 34 R1 fallback)" to "(strict — cycle 36 closure)"). `pip check` step retains `continue-on-error: true` per AC10.

- **C8 (Q17 / AC9 / AC20).** Step-9 implementation runs `pip-audit --format json` on the live CI-equivalent install env (`pip install -e '.[dev,formats,augment,hybrid,eval]'`) and inspects actual advisory IDs. Workflow `--ignore-vuln` set + `SECURITY.md` Known Advisories table are reconciled 1:1 with what pip-audit emits. Any Dependabot alert NOT in pip-audit's report gets a cycle-37 BACKLOG entry of the shape "**Phase 4.6 — Dependabot/pip-audit drift on `<package>` `<GHSA-id>`** — Dependabot reports the advisory but pip-audit on live install env does not; document in cycle-36 investigation; monitor for pip-audit data refresh."

- **C9 (T7 / AC6 helper).** Behaviour tests for `requires_real_api_key()` are in `tests/test_cycle36_ci_hardening.py`. The helper is callable in isolation (per `feedback_inspect_source_tests.md` — extract helper, test directly; do NOT use `inspect.getsource + 'X' in src`). Tests cover: unset env var → False; `ANTHROPIC_API_KEY == "sk-ant-dummy-key-for-ci-tests-only"` → False; `startswith("sk-ant-dummy")` → False; split-string-constructed real-prefix → True (per `feedback_no_secrets_in_code.md`).

- **C10 (T5 / AC20 parsing test).** `tests/test_cycle36_ci_hardening.py` includes a parsing test cross-referencing `SECURITY.md` advisory IDs (regex `(CVE-\d{4}-\d+|GHSA-[a-z0-9-]+)`) against `.github/workflows/ci.yml` `--ignore-vuln=` flags — list-equality check on the two sets. This is a behaviour test (parses live files), not a signature test.

- **C11 (T1 / collect-only diff).** `pytest --collect-only -q | tail -3` is run after each commit in the three-commit sequence; the collected/passed/skipped triple is recorded in the cycle-36 investigation doc. Per Q22, exact numbers are committed only at Step-12 doc update where they trace to a live pytest run.

- **C12 (Q13).** No cycle-37 BACKLOG entry for `WIKI_DIR` monkeypatch widening — the 204-site surface is stable.

- **C13 (Q15).** Step-12 dispatches 3 independent PR review rounds (Opus / Codex / Opus or equivalent) per `feedback_3_round_pr_review.md`.

- **C14 (Q22 / cycle-26 L2).** Step-12 doc update re-collects test counts for CLAUDE.md Quick Reference, `docs/reference/testing.md` (currently stale at `2941 / 254`), and `CHANGELOG.md` Quick Reference Items / Tests / Scope / Detail entry.

- **C15 (cycle-34 hygiene).** Sub-agents delete scratch files (findings.md, progress.md, task_plan.md, claude4.6.md) before declaring done — gitignored but enforced by cycle 34 hygiene test.

- **C16 (Q14).** The cycle-23 multiprocessing test's pytest-timeout interaction is documented in the cycle-36 investigation doc with a one-line acknowledgement (local 1.03s; CI-skipped per AC2; no false-positive risk).

## FINAL DECIDED DESIGN

Cycle 36 ships as one PR on `feat/backlog-by-file-cycle36`, three commits in sequence (probe → fix → strict-gate), with ~23 ACs across Areas A, B, C, D, F, G. Area E (requirements split) is deferred to cycle 37 with a specific BACKLOG entry shape.

**Area A — Windows CI hang fix (4 ACs).**
- AC1: cycle-23 multiprocessing test #1155 identified as the hanger; documented in `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md`.
- AC2: `@pytest.mark.skipif(os.environ.get("CI") == "true", reason="Windows multiprocessing spawn hangs on GHA — tracked C36-investigation.md, cycle-37 candidate")`. Local coverage preserved.
- AC3 *(amended from 60s to 120s per Q2)*: `pytest-timeout >= 2.3` in `[dev]` extras + `requirements.txt`; `pyproject.toml` `[tool.pytest.ini_options] timeout = 120` with per-test `@pytest.mark.timeout(N)` override mechanism preserved.
- AC4: local probe `pytest -q` after AC1+AC2+AC3 confirms no regression.

**Area B — Fragility-class fixes (3 ACs).**
- AC5 *(amended per Q3 / Q18)*: mirror-rebind monkeypatch chain on `kb.config.WIKI_DIR` for both quality tests, with Step-9 call-chain trace documented in test comments / investigation doc; mirrors added for any additional module-top `WIKI_DIR` sites the chain reaches.
- AC6 *(amended per Q4 / Q12 / Q19)*: `tests/_helpers/api_key.py::requires_real_api_key()` predicate (gates on env-var prefix, not on literal-string grep); Step-9 traces each of 4 enumerated test files; only those at real-API risk get the marker.
- AC7 *(amended per Q11)*: widen ONLY `test_over_cap_rejected_with_retry_after` to `<= 3601` (or `<= 3602` if probe shows flakiness); `test_over_cap_retry_after_static_clock_is_one_hour` stays at `== 3600` exact equality.

**Area C — Strict CI gate (3 ACs).**
- AC8 *(sequencing per Q16/Q21)*: drop `continue-on-error: true` from the pytest step in commit 3 of the three-commit sequence; step name updates to "(strict — cycle 36 closure)".
- AC9 *(amended per Q17)*: workflow `--ignore-vuln` set reconciled 1:1 with `pip-audit --format json` actual emission on live CI-equivalent install env.
- AC10: `pip check` step retains `continue-on-error: true` (the three known transitive conflicts remain — non-goal #7).

**Area D — Cross-OS matrix (3 ACs).**
- AC11 *(amended per Q5 / Q8 / Q9 / Q20)*: TWO data-driven lists from the probe — anti-Windows-skipif (POSIX-only) and anti-POSIX-skipif (Windows-only). `TestExclusiveAtomicWrite` is NOT on either list. Already-correctly-gated tests are listed as "no change" with provenance.
- AC12: `strategy.matrix.os: [ubuntu-latest, windows-latest]` added in commit 3.
- AC13: ubuntu-latest CI run validates AC11+AC12; >10 new fragility classes file cycle-37 BACKLOG entries rather than expanding cycle-36 scope.

**Area E — DEFERRED to cycle 37.** BACKLOG entry shape per Q6: "**Phase 4.5 — Requirements split (deferred from cycle 36)** — Generate `requirements-runtime.txt` + 5 per-extra files (`requirements-{hybrid,augment,formats,eval,dev}.txt`) using layered `-r requirements-runtime.txt` includes per cycle-36 design Q6. README install-section update follows. Cycle-35 L8 floor pin (`langchain-openai>=1.1.14`) must appear in `requirements-eval.txt`." AC14-AC17 and AC26 are NOT in cycle 36 scope.

**Area F — CVE recheck (3 ACs).**
- AC18: `gh api` Dependabot snapshot saved to `.data/cycle-36/alerts-baseline.json` (gitignored).
- AC19: verify `litellm 1.83.7` still requires `click==8.1.8`; BACKLOG entry stays if blocked.
- AC20 *(amended per Q17)*: `SECURITY.md` Known Advisories table + workflow `--ignore-vuln` reconciled 1:1 with pip-audit actual emission. Any Dependabot alert NOT in pip-audit's report gets a cycle-37 BACKLOG entry.

**Area G — Documentation (5 ACs).**
- AC21: `CHANGELOG.md [Unreleased]` Quick Reference compact entry (Items / Tests / Scope / Detail).
- AC22: `CHANGELOG-history.md` per-cycle bullet detail.
- AC23: `BACKLOG.md` cleanup — delete the 2 cycle-36 entries that close (strict-gate, cross-OS portability); the requirements-split entry stays under "Phase 4.5 deferred" with the new shape from Q6. Cycle-32 deferred-CVE-recheck entry deletes once AC18 confirms state.
- AC24: `CLAUDE.md` Quick Reference numbers re-collected per Q22 / C14.
- AC25: `docs/reference/testing.md` refresh — test count re-collected; new conventions documented (cross-OS skipif marker pattern, `requires_real_api_key()` helper, pytest-timeout default + override mechanism, CI vs local skip strategy, dummy-key prefix `sk-ant-dummy-key-for-ci-tests-only` documented per T7 verification step #4).
- AC26 (README install-section): NOT in cycle 36 scope (Q7=B Area E deferred).

**Test additions (NEW):** `tests/test_cycle36_ci_hardening.py` with regression tests per C4 (helper behaviour), C9 (helper isolation), C10 (SECURITY.md ↔ workflow parsing), C5 (skipif markers + collect-only diff sanity).

**Test helper (NEW):** `tests/_helpers/__init__.py` + `tests/_helpers/api_key.py::requires_real_api_key()`.

**Sequencing (per Q16 / Q21).**
1. **Commit 1 (probe):** AC1+AC2+AC3+AC5+AC6+AC7 markers; `runs-on: ubuntu-latest` (single-OS toggle, NO matrix, NO strict-gate); `continue-on-error: true` STILL ON. CI runs full suite on ubuntu, surfacing actual failures.
2. **Commit 2 (fix):** Apply AC11 markers based on probe results; any other probe-revealed test fixes; cycle-32 / cycle-35 lessons applied.
3. **Commit 3 (strict-gate):** AC8 drop `continue-on-error: true`; AC12 matrix `[ubuntu-latest, windows-latest]`; step name update; pre-merge CI validates the strict gate.

**Evidence trail.** `docs/superpowers/decisions/2026-04-26-backlog-by-file-cycle36-investigation.md` records: (i) AC1 hanger identification, (ii) AC5 call-chain traces, (iii) AC6 per-file SDK call-chain traces, (iv) AC11 two-list enumeration, (v) AC9 / AC20 pip-audit actual emission JSON snippet, (vi) AC11 probe collect-only diff, (vii) Q14 pytest-timeout × mp.Event acknowledgement.

**R3 review (per Q15).** Step-12 dispatches 3 independent PR review rounds. Round 3 typically APPROVES but catches regressions introduced by round 2 fixes per `feedback_3_round_pr_review.md`.

**Test count claim (per Q22 / cycle-26 L2).** Specific numbers defer to Step-12 doc update where the live `pytest --collect-only -q | tail -3` output is the authoritative source. Methodology committed: re-collect after AC1+AC2+AC3+AC5+AC6+AC7+AC11 land; record collected / passed / skipped triple in CLAUDE.md, `docs/reference/testing.md`, `CHANGELOG.md` Quick Reference.

End of decision document.
