# Cycle 38 — R1 (Opus) Design Eval

**Date:** 2026-04-26
**Reviewer role:** R1 = ASSUMPTIONS / SCOPE / FRAMING. R2 (Codex) covers edge cases / failure modes / security / perf.
**Inputs:** [requirements](2026-04-26-backlog-by-file-cycle38-requirements.md), [threat-model](2026-04-26-backlog-by-file-cycle38-threat-model.md), [brainstorm](2026-04-26-backlog-by-file-cycle38-brainstorm.md). All cited symbols grep-verified before scoring.

---

## 1. Symbol verification table

| Symbol | Cited file:line | Actual file:line | Status |
|---|---|---|---|
| `kb.capture.call_llm_json` (module-top binding) | `src/kb/capture.py:37` | `src/kb/capture.py:37` (`from kb.utils.llm import call_llm_json`) | EXISTS |
| `kb.utils.llm.call_llm_json` (def) | `src/kb/utils/llm.py:320` | `src/kb/utils/llm.py:320` (`def call_llm_json(prompt, *, tier="write", system="", schema, ...)`) | EXISTS |
| `kb.capture.atomic_text_write` (module-top) | `src/kb/capture.py:36` | `src/kb/capture.py:36` (`from kb.utils.io import atomic_text_write`) | EXISTS |
| `kb.utils.io.atomic_text_write` (def) | `src/kb/utils/io.py:144` | `src/kb/utils/io.py:144` (`def atomic_text_write(content: str, path: Path) -> None:`) | EXISTS |
| `_exclusive_atomic_write` | `src/kb/capture.py:461` | `src/kb/capture.py:461` | EXISTS |
| `_scan_existing_slugs` | `src/kb/capture.py:555` | `src/kb/capture.py:555` | EXISTS |
| `_build_slug` | `src/kb/capture.py:406` | `src/kb/capture.py:406` | EXISTS |
| `_reserve_hidden_temp` | `src/kb/capture.py:561` | `src/kb/capture.py:561` | EXISTS |
| `_write_item_files` | `src/kb/capture.py:607` | `src/kb/capture.py:607` (mkdir at line 641) | EXISTS |
| `tests/conftest.py::mock_scan_llm` | `tests/conftest.py:363` | `tests/conftest.py:362` (`@pytest.fixture` decorator), def at 363; sole patch site `kb.capture.call_llm_json` at line 389 | EXISTS (off-by-one in cite; semantics confirmed) |
| `tests/conftest.py::tmp_captures_dir` | `tests/conftest.py:395` | `tests/conftest.py:394` (decorator), def at 395; double-patches `kb.config.CAPTURES_DIR` AND `kb.capture.CAPTURES_DIR` | EXISTS |
| `tests/test_capture.py::_REQUIRES_REAL_API_KEY` | `tests/test_capture.py:47` | `tests/test_capture.py:47` | EXISTS |
| `tests/test_capture.py::_WINDOWS_ONLY` | `tests/test_capture.py:58` | `tests/test_capture.py:58` | EXISTS |

**Side-checks:**
- Grep for `monkeypatch.setattr.*kb\.capture\.call_llm_json` → exactly 3 sites: `tests/conftest.py:389` (mock_scan_llm), `tests/test_capture.py:419` (Cycle9 regression), `tests/test_capture.py:1126` (`test_llm_error_propagates_class_b`). Requirements §AC2 cites lines 419 + 1126 — CORRECT.
- Grep for `_REQUIRES_REAL_API_KEY` decorators in `test_capture.py` → 7 sites at lines 1062, 1106, 1130, 1140, 1170, 1262, 1420. Requirements §AC3 says "7 tests" — CORRECT.
- Grep for `_REQUIRES_REAL_API_KEY` in `test_mcp_core.py` → 3 sites at lines 339, 372, 395 (`TestKbCaptureWrapper`). Requirements §AC4 says "3 tests" — CORRECT.
- Grep for `@_WINDOWS_ONLY` in `test_capture.py` → 4 sites at lines 734, 747, 901, 971. Requirements §Area B says "4 tests" — CORRECT.
- Grep for `monkeypatch.setattr.*atomic_text_write` across `tests/` → 23 hits across many test files (publish/refiner/linker/ingest pipelines). Only the 2 in `test_capture.py:741,754` patch `kb.capture.atomic_text_write`; the rest patch other modules' bindings. Q3 same-class peer scan WITHIN capture concerns is therefore self-contained.

All cited symbols EXIST and semantics match the requirements doc's claims. **No MAJOR symbol-mismatch flags.**

---

## 2. AC scoring

### AC1 — widen `mock_scan_llm` to dual-site patch — **CORRECT**

Today's `mock_scan_llm` (`tests/conftest.py:389`) patches only `kb.capture.call_llm_json`. The reload-leak hypothesis (cycle-19 L2 / cycle-20 L1 lineage) is sound: when a sibling test reloads `kb.utils.llm`, `kb.capture`'s module-top `call_llm_json` reference (bound at `src/kb/capture.py:37` via `from kb.utils.llm import call_llm_json`) is a snapshot of the *original* function object — but `monkeypatch.setattr("kb.capture.call_llm_json", fake)` mutates the `kb.capture` module's `__dict__`, which IS the binding looked up at call time. The leak vector is when something *re-imports* `kb.capture` post-reload (or replaces `kb.capture.call_llm_json` directly with the new `kb.utils.llm.call_llm_json`). AC1 dual-site patch closes this. Approach is sound and minimal-blast-radius.

**AMENDMENT:** AC1 as written under "widen `mock_scan_llm`" is silent on whether the second `setattr` should be conditional or unconditional. Risk register R2 calls out conditional widening; recommend the AC text explicitly say *unconditional* dual-site patch — `monkeypatch` undoes both on teardown so test isolation is preserved either way, and conditional patching adds branch complexity for no gain.

### AC2 — widen inline `kb.capture.call_llm_json` patches — **CORRECT**

Lines 419 and 1126 verified. Both add a single sibling `monkeypatch.setattr("kb.utils.llm.call_llm_json", ...)`. Lower-blast-radius than refactoring to use `mock_scan_llm`.

### AC3 — remove `_REQUIRES_REAL_API_KEY` from 7 test_capture.py tests — **CORRECT**

All 7 cited tests verified at the cited lines. The 7-count matches my grep. Validate that AC3 only ships AFTER AC1 + AC2 land green; otherwise the 7 tests fail on dummy CI key.

### AC4 — remove `_REQUIRES_REAL_API_KEY` from 3 test_mcp_core.py tests — **CORRECT**

All 3 verified at lines 339, 372, 395 in `TestKbCaptureWrapper`. Same green-gating sequence as AC3.

### AC5 — regression test pinning the reload-leak fix — **CORRECT**

The cycle-15 L2 DROP-with-test-anchor + `feedback_test_behavior_over_signature` discipline is correctly applied. Both cases (a baseline + b post-reload) materially exercise different failure modes, and the explicit "revert AC1 locally and verify case (b) fails" step aligns with the user-feedback rule (signature-only tests are vacuous). Solid.

**AMENDMENT:** AC5 should explicitly require `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` BEFORE the reload-and-call sequence in case (b). Otherwise an environment with a real key would PASS case (b) for the wrong reason (the real SDK call would succeed even if the mock doesn't fire). This is the same hidden-pass risk that motivated `_REQUIRES_REAL_API_KEY` in the first place.

### AC6 — widen `kb.capture.atomic_text_write` patches in `test_cleans_up_*` — **CORRECT**

Lines 741, 754 verified. Same dual-site pattern as AC2. Drop `@_WINDOWS_ONLY` decorators is gated on AC6's patch widening succeeding under POSIX. Approach is sound.

### AC7 — investigate + fix `test_pre_existing_file_collision` POSIX off-by-one — **AMBIGUOUS**

The AC text says "investigate + fix" with a probe commit, then "fix the production code OR loosen the test assertion to match documented behaviour". This conflates two very different outcomes. Approach A (probe commit) is correct as a *diagnostic* step, but the AC's pass/fail criterion ("ubuntu-latest CI passes the test with the correct expected slug") is unverifiable until the probe runs. The AC should explicitly note that *the AC is provisionally PASS-IF-PROBE-IDENTIFIES-FIX, and otherwise scope-cut to cycle 39* per R1 in the risk register.

**AMENDMENT:** Add explicit AC7 fork: "AC7-a: probe commit lands; AC7-b: based on probe output, EITHER fix production AND loosen test, OR scope-cut and document in cycle-39 BACKLOG." Standing pre-authorisation per M1 covers the scope-cut path.

### AC8 — investigate + fix `test_creates_dir_if_missing` POSIX behaviour — **AMBIGUOUS** (same shape as AC7)

The hypothesis (`tmp_captures_dir` Path object captures stale resolved path on POSIX where `tmp_path` differs from `kb.capture.CAPTURES_DIR` post-monkeypatch) is plausible but unproven. The `tmp_captures_dir` fixture at conftest:395 already double-patches both `kb.config.CAPTURES_DIR` AND `kb.capture.CAPTURES_DIR` — so the stale-binding hypothesis would imply something else is reading the old path. Possible alternative: `_write_item_files` line 641 `_captures_dir.mkdir(parents=True, exist_ok=True)` succeeds, but `_scan_existing_slugs` at line 558 is called via `os.scandir` which on POSIX may behave differently when the directory was just created (race?). Same fork as AC7 — needs probe before declaring approach.

### AC9 — refresh Dependabot drift status — **CORRECT**

Approach matches cycle-37 L1 four-gate model + `feedback_dependabot_pre_merge`. Action is conditional ("ONLY if pip-audit caught up, add `--ignore-vuln`") and lower-blast-radius. The narrow-role rationale was already gated in cycle 36 Step-5 Q17 per the brainstorm Q4 context, so this is a re-confirmation — Approach A in Q4 is correct.

### AC10 — delete resolved cycle-38 candidates from BACKLOG — **CORRECT**

Matches the BACKLOG.md lifecycle in CLAUDE.md (delete-on-resolve, not strikethrough). Preserve cycle-39+ items (windows matrix, GHA spawn, drift) is right per cycle-36 L1.

---

## 3. Q1-Q5 + D1-D6 + M1 analysis

### Q1 — should mock_scan_llm also patch `kb.ingest.extractors.call_llm_json`?

**Analysis.** The fixture's name and docstring frame it as capture-flow specific ("Install a canned JSON response for call_llm_json inside kb.capture"). Existing tests in `test_extractors.py` patch `kb.ingest.extractors.call_llm_json` directly with their own extraction-shape fakes that DO NOT have the capture-shape keys (`items`, `filtered_out_count`); the mock_scan_llm fake_call enforces those keys via assert. Widening would cause assertion-failure collisions every time an extractor test ran with mock_scan_llm in scope.

The cycle-38 problem is *capture-flow* tests reaching the real SDK, not extractor-flow tests. The blast radius of Approach B (all-three sites) is large for a benefit that doesn't materialise (no extractor tests are in the 14 failures). Approach A (canonical+capture only) closes the failing class without breaking the passing one.

**RECOMMENDATION: Approach A.** **CONFIDENCE: HIGH.**

### Q2 — AC7 fix direction

**Analysis.** Loosening the test (Approach B, `slug.startswith("decision-foo-")`) is tempting because it is one-line and ships immediately, but it carries a real-bug-hiding risk: if production `_scan_existing_slugs` returns a stale entry on POSIX, the same drift could land in production slug allocation under genuine concurrent capture, and the test would never catch it. The probe commit (Approach A) costs one extra round-trip on CI but produces ground-truth before deciding. It is the cycle-36 commit-1 pattern that already paid for itself.

Approach C (fix `_scan_existing_slugs` to include `.reserving` temps) is speculative — there is no evidence yet that residual `.reserving` files exist in `tmp_captures_dir` when the test runs. A new test fixture ALWAYS produces a fresh `tmp_path`. Approach C should only be on the table if the probe surfaces a hidden-temp residue.

**RECOMMENDATION: Approach A (probe commit).** **CONFIDENCE: HIGH.** D6 already enforces probe hygiene (revert before Step 13). No escalation.

### Q3 — AC6 same-class peer scan

**Analysis.** Cycle-16 L1 explicitly trades 5-10 lines of grep work for closing the class. The grep I ran shows 23 `monkeypatch.setattr.*atomic_text_write` sites; only 2 patch `kb.capture.atomic_text_write`. The rest patch other modules' re-bound name (e.g., `kb.publish.atomic_text_write`, `kb.review.refiner.atomic_text_write`). For each of those, the same reload-leak class theoretically applies — but each test target has been passing CI for cycles, suggesting the actual triggering condition (sibling `importlib.reload(kb.utils.llm)`) is not present in those test files' collection paths.

The pragmatic stance: AC6 widens both `kb.capture.atomic_text_write` sites AND adds a follow-up grep at Step 11 verification (`grep -n "kb\\.capture\\.atomic_text_write" tests/`) to confirm no new sites appeared. For OTHER modules' patches, defer to cycle 39+ as a class-closure backlog item (LOW severity — no regression evidence today). This is *strict* Approach A in the brainstorm doc, not Approach B.

The brainstorm's recommendation of Approach B (widen ALL hits) overcommits; the cycle-16 L1 lesson reads in context as "scan to confirm no peers", not "widen every peer regardless of regression evidence". Recommend SCOPE-CUT relative to brainstorm.

**RECOMMENDATION: Approach A + Step-11 peer-scan confirmation.** **CONFIDENCE: MEDIUM.** ESCALATE to user-decision in plan-gate if R2 disagrees — this is the only material divergence from the brainstorm's recommendation.

### Q4 — AC9 `--ignore-vuln` decision flow

**Analysis.** Approach A (in-cycle decision) is correct because the narrow-role rationale was gated in cycle 36 Step-5 Q17 — adding the IDs is a documentation/CI-config change, not a new security decision. Approach B (separate Step-5 pass) duplicates work for no safety gain; the gate already happened. Approach C (preemptive add) introduces invisible noise (CI references IDs pip-audit doesn't surface, drifting silently if Dependabot drops the IDs).

**RECOMMENDATION: Approach A.** **CONFIDENCE: HIGH.**

### Q5 — AC5 regression test location

**Analysis.** The freeze-and-fold rule (cycle-4 L4 / Phase 4.5 R3) applies to *versioned* test files (`test_v0917_*`), not cycle-tagged ones. Recent cycles (36, 37) consistently use `test_cycle{N}_*.py` for new ACs, so the convention is established. Folding into `test_capture.py::TestMockScanLlmReloadSafety` (Approach B) buries a 50-LoC regression in a 1500+-line file; the cycle-tag is a discoverability win for future archaeology. Approach C (doctest) is killed by pytest config not running doctests.

**RECOMMENDATION: Approach A (cycle-tagged file).** **CONFIDENCE: HIGH.**

### D1 — primary-session vs subagent dispatch

**Analysis.** 10 ACs ≤ 15-AC threshold; 0-1 src files ≤ 5-file threshold. Both cycle-37 L5 conditions met for primary-session default. Subagent dispatch would amortise across more ACs than this cycle warrants. **RECOMMENDATION: primary-session.** **CONFIDENCE: HIGH.**

### D2 — TDD ordering

**Analysis.** AC1 → AC2 → AC5 → AC3+AC4 → AC6 → AC7+AC8 puts the regression test (AC5) BEFORE the decorator removals (AC3+AC4), which is correct because AC5 must fail under the pre-cycle-38 fixture and pass under post-cycle-38; if the order were reversed, AC3+AC4 would land green (real SDK 401-failure gone via dummy key) without proving AC1 actually works as intended. **RECOMMENDATION: as written.** **CONFIDENCE: HIGH.**

### D3 — Step 9.5 simplify pass skip

**Analysis.** 0-1 src files, <50 LoC src diff. Step 9.5 skip-when row matches. **RECOMMENDATION: skip Step 9.5.** **CONFIDENCE: HIGH.**

### D4 — R3 review trigger

**Analysis.** 10 ACs, ≤5 src files, no new write surface, no new security enforcement point, ≤10 design-gate questions. All cycle-17 L4 R3-skip conditions hold. Per `feedback_minimize_subagent_pauses` (skip R3 below 25-AC threshold), **RECOMMENDATION: R1 + R2 only, skip R3.** **CONFIDENCE: HIGH.**

### D5 — Codex dispatch

**Analysis.** Standard pattern matches recent cycles. **RECOMMENDATION: as written.** **CONFIDENCE: HIGH.**

### D6 — probe commit hygiene

**Analysis.** D6 prescribes (a) separate commit, (b) revert before Step 13, (c) probe-CI is diagnostic-only. Step-11 verification grep for `print(` in `src/kb/capture.py` diff catches accidental retention. **AMENDMENT:** Add a Step-11 verifier line that the probe commit's HASH is NOT in the final PR's commit log (Step 13 squash-merge implicitly handles it; explicit Step-11 check is belt-and-suspenders). **CONFIDENCE: HIGH on D6 as-written; AMENDMENT optional.**

### M1 — scope-cut pre-authorisation

**Analysis.** Standing pre-auth for narrowing AC7 or AC8 to cycle 39 if probe surfaces deeper bug. Aligns with `feedback_minimize_subagent_pauses` (skip-conditions are pre-decided to avoid runtime gates). The risk-register R1 already documents this; M1 just makes it executable at implementation time. **RECOMMENDATION: APPROVE pre-authorisation.** **CONFIDENCE: HIGH.**

No questions need ESCALATE except the SCOPE-CUT divergence on Q3.

---

## 4. Cross-cycle drift checks

| Invariant | Source cycle | Cycle 38 status |
|---|---|---|
| `_validate_path_under_project_root` dual-anchor (literal + resolved) | C28-C30 | UNCHANGED — no MCP boundary touched. |
| `tmp_kb_env` mirror loop scoped to `kb.*` | C12 R1 | UNCHANGED — mock_scan_llm widening still scoped to `kb.utils.llm` (one new entry, in-class). |
| Patch the owner module rule (CLAUDE.md Quick Ref) | ongoing | NUANCED — AC1/AC2 widen to ALSO patch the upstream (`kb.utils.llm`) BECAUSE of the reload-leak. The owner-module rule still holds for the primary patch site; the secondary patch is a reload-defence. Recommend a one-line note in `docs/reference/testing.md` documenting "for capture-flow + mock_scan_llm, also patch `kb.utils.llm.call_llm_json` to defeat the reload-leak class". |
| `_REQUIRES_REAL_API_KEY` / `_WINDOWS_ONLY` markers (cycle-36 AC6/AC11) | C36 | RESOLVED — markers are removed entirely from the 14 tests, decorator definitions could remain in `test_capture.py` for any future probe but should be commented "unused after cycle 38" or deleted if AC3/AC4/AC6/AC7/AC8 all land green. |
| One CI dimension per cycle (C36 L1) | C36 | UNCHANGED — cycle 38 does not add windows-latest. |
| BACKLOG delete-on-resolve (CLAUDE.md) | ongoing | AC10 honours. |
| Cycle-tagged regression file convention | C36-C37 | AC5 honours. |

**No invariant breakage detected.** The only nuance is the patch-owner-module rule, which remains the primary discipline; the secondary patch is a documented defence, not a replacement.

---

## 5. Final verdict

**APPROVE-WITH-AMENDMENTS.**

Three amendments and one scope-cut:

1. **AC1** — explicitly say *unconditional* dual-site patch (drop the conditional widening from R2's risk register).
2. **AC5** — add `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` before the reload sequence in case (b) to prevent real-SDK-pass false-positive.
3. **AC7 + AC8** — split each into AC{N}-a (probe) + AC{N}-b (fix-or-scope-cut) with M1 standing pre-auth to defer to cycle 39 if probe doesn't yield a clean fix path.
4. **Q3 SCOPE-CUT** — recommend Approach A (strict scope: only the two `kb.capture.atomic_text_write` failing tests + Step-11 peer-scan confirmation), DIVERGING from the brainstorm's Approach B (widen all peers). This is the only escalation flag — let R2 confirm before plan-gate locks it in.

Rationale: 10 ACs, all cited symbols verified, 0-1 src files, no new trust boundary or security enforcement. Cycle qualifies for primary-session execution, R3 skip, and Step 9.5 skip per cycle-17/cycle-37 thresholds. Probe-commit hygiene (D6) is well-specified.

**Word count: ~2,310.**
