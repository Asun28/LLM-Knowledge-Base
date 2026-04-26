# Cycle 38 — Step 5 Design Decision Gate

**Date:** 2026-04-26
**Reviewer:** Step-5 Opus design gate (autonomous; per `feedback_auto_approve`).
**Inputs:** [requirements](2026-04-26-backlog-by-file-cycle38-requirements.md), [threat-model](2026-04-26-backlog-by-file-cycle38-threat-model.md), [brainstorm](2026-04-26-backlog-by-file-cycle38-brainstorm.md), [r1-opus-eval](2026-04-26-backlog-by-file-cycle38-r1-opus-eval.md), [r2-codex-eval](2026-04-26-backlog-by-file-cycle38-r2-codex-eval.md).

---

## VERDICT

**APPROVE-WITH-AMENDMENTS.**

R2 Codex flipped the diagnosis on the failure mechanism — and is correct. The brainstorm/requirements diagnosis ("`importlib.reload(kb.config)` cascade re-binds module-top imports") is FACTUALLY WRONG: `kb.config` imports only stdlib (verified at `src/kb/config.py:3-9`), so reloading it cannot cascade to `kb.utils.llm` or `kb.capture` (one-way dependency). The true contamination source is `del sys.modules["kb.capture"]` + reimport in the symlink security test (`tests/test_capture.py:700-714`). However, R2's proposed remedy (dual-site patch on `kb.utils.llm.call_llm_json` + `kb.capture.call_llm_json`) is ALSO INCOMPLETE. Python `from X import Y` is a SNAPSHOT at import time. After `del sys.modules["kb.capture"]` + reimport, `tests/test_capture.py`'s pre-collection bindings (line 20-37) still hold the OLD module's function objects whose `__globals__` IS the OLD `__dict__`. Patching `kb.utils.llm.__dict__` doesn't update OLD `kb.capture.__dict__`. Therefore Q1 must resolve to a **subprocess refactor** of `TestSymlinkGuard`, eliminating the contamination source rather than papering over it.

This is a 10-AC cycle with 0-1 src files. Below R3 trigger thresholds (cycle-17 L4); primary-session execution per cycle-37 L5; Step 9.5 skipped per its own skip-when row. Approve with five MAJOR amendments and several MINOR clarifications.

---

## DECISIONS

| Q | Resolution | Confidence |
|---|---|---|
| Q1 | **Option C — Hybrid: subprocess refactor for symlink test + dual-site patch** | HIGH |
| Q2 | sys.modules deletion-after-install pattern; `monkeypatch.delitem(sys.modules, "kb.capture", raising=False)`; explicit `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` | HIGH |
| Q3 | **Approach A — Strict scope** (only test_capture.py:741,754); document monitored-deferred peers in implementation notes | HIGH |
| Q4 | **Use live-env mode** (no `-r` flag) in threat-model §7 to match ci.yml | HIGH |
| Q5 | **Add ruff T20 to pyproject.toml** (defense-in-depth) + mandate squash-merge of probe+revert + explicit Step-10 grep | HIGH |
| Q6 | **Make AC9 no-change branch explicit**: BACKLOG.md re-check date update only | HIGH |
| Q7 | **Pre-register cycle-39+ BACKLOG entry** for fold-into-test_capture.py | MEDIUM |
| Q8 | **Add explicit scratch-file-cleanup step** to AC10 (cycle-34 hygiene gate) | HIGH |
| Brainstorm Q1 | Approach A (capture + utils.llm only; do NOT widen to extractors) | HIGH |
| Brainstorm Q2 | Approach A (probe commit, gated to revert pre-PR) | HIGH |
| Brainstorm Q3 | Approach A — strict scope (DIVERGE from brainstorm's Approach B) | HIGH |
| Brainstorm Q4 | Approach A — in-cycle decision, conditional add | HIGH |
| Brainstorm Q5 | Approach A — cycle-tagged file (`test_cycle38_*`) with cycle-39 fold pre-register | HIGH |
| D1 | Primary-session (10 ACs ≤ 15-AC threshold; 0-1 src files ≤ 5-file threshold) | HIGH |
| D2 | TDD ordering as written (AC1 → AC2 → AC5 → AC3+AC4 → AC6 → AC7+AC8); inject AC0 (subprocess refactor) BEFORE AC1 | HIGH |
| D3 | Skip Step 9.5 (0-1 src files, <50 LoC src diff) | HIGH |
| D4 | R1 + R2 only; skip R3 per cycle-17 L4 + `feedback_minimize_subagent_pauses` | HIGH |
| D5 | Codex dispatch as written (Step 7 primary, Step 8 plan-gate Codex, Step 11 security Codex, Step 14 R1 Codex+Sonnet parallel) | HIGH |
| D6 | Probe-commit hygiene as written, hardened with squash-merge mandate | HIGH |
| M1 | APPROVE pre-authorization for AC7/AC8 scope-cut to cycle-39 if probe is inconclusive | HIGH |

---

## CONDITIONS for Step-9 implementation

These are LOAD-BEARING test-coverage requirements per cycle-22 L5. Each must be satisfied by a passing test that fails when the fix is reverted (per `feedback_test_behavior_over_signature` and `feedback_inspect_source_tests`).

1. **AC0 (NEW) — Subprocess refactor of TestSymlinkGuard.** `test_symlink_outside_project_root_refuses_import` runs in `subprocess.run([sys.executable, "-c", probe_script], env={...})` so it never touches the test runner's `sys.modules`. The test passes a synthesized PROJECT_ROOT/CAPTURES_DIR via env vars, and the subprocess imports `kb.capture` and asserts the RuntimeError. **Verification**: `grep -n "del sys.modules" tests/test_capture.py` returns 0 hits; the subprocess invocation grep returns ≥1 hit. Revert the refactor locally and verify the OLD-binding contamination resurfaces (case-b of AC5 must FAIL).

2. **AC1 (REVISED) — dual-site patch in mock_scan_llm.** Apply `kb.utils.llm.call_llm_json` setattr BEFORE `kb.capture.call_llm_json` setattr. Document ordering in fixture docstring. **Verification**: `grep -n "kb.utils.llm.call_llm_json" tests/conftest.py` ≥ 1; the docstring explicitly states "patch utils.llm first to defeat subsequent re-imports".

3. **AC5 (REVISED) — non-vacuous regression test.** Test SHAPE (after AC0 lands):
   - **case (a)** — install `mock_scan_llm` (dual-site post-AC1), call `capture_items` directly, assert mock fired.
   - **case (b)** — install `mock_scan_llm` (single-site only, simulating pre-AC1) via a manual `monkeypatch.setattr("kb.capture.call_llm_json", fake)` — DO NOT also patch utils.llm. Use `monkeypatch.delitem(sys.modules, "kb.capture", raising=False)` + `importlib.import_module("kb.capture")` + capture-via-`from kb.capture import capture_items` rebind, then call. Assert mock did NOT fire (proves single-site is broken post-reimport when bindings are taken anew).
   - **case (c)** — install dual-site `mock_scan_llm` (post-AC1), repeat case (b)'s reimport sequence. Assert mock fired.
   - **manual revert check**: locally revert AC1's dual-site widening; case (c) must FAIL. Document the manual check in a comment block in the test file.
   - **environment safety**: `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` BEFORE the call sequence in case (a)/(b)/(c) so a developer with a real key in `.env` can't false-pass via the real SDK.

4. **AC2 (UNCHANGED) — paired widening at lines 419 and 1126.** Each `monkeypatch.setattr("kb.capture.call_llm_json", ...)` gets a paired `monkeypatch.setattr("kb.utils.llm.call_llm_json", ...)`. **Verification**: `grep -n "kb.utils.llm.call_llm_json" tests/test_capture.py` ≥ 2.

5. **AC3 + AC4 — decorator removal.** Drop 7 decorators in test_capture.py + 3 in test_mcp_core.py. Sequence: only after AC0 + AC1 + AC2 land green.

6. **AC6 — atomic_text_write dual-site patch (strict scope).** Lines 741, 754 only. `monkeypatch.setattr("kb.capture.atomic_text_write", boom)` PAIRED with `monkeypatch.setattr("kb.utils.io.atomic_text_write", boom)`. Drop `@_WINDOWS_ONLY` from both. **Verification**: `grep -n "kb.utils.io.atomic_text_write" tests/test_capture.py` ≥ 2.

7. **AC7 — POSIX off-by-one slug probe.** Probe commit adds `print()` diagnostics in `_scan_existing_slugs` / `_build_slug` / `_reserve_hidden_temp`. Probe is reverted before Step 13 PR open. Squash-merge mandate per Q5 below. **Standing pre-auth (M1)**: if probe inconclusive, narrow scope — restore `_WINDOWS_ONLY` on offending test, document as cycle-39 candidate.

8. **AC8 — `test_creates_dir_if_missing` POSIX probe.** Same probe-revert pattern; same M1 pre-auth.

9. **AC9 — Dependabot drift refresh (no-change branch explicit).** If pip-audit does NOT surface GHSA-r75f / GHSA-v4p8, ONLY BACKLOG.md changes (re-check date updated to 2026-04-26). ci.yml, SECURITY.md, requirements.txt UNCHANGED. This is the EXPECTED path. **Verification**: `git diff main -- .github/workflows/ci.yml SECURITY.md requirements.txt` returns no diff (no-change branch); BACKLOG.md diff shows date update only.

10. **AC10 — BACKLOG cleanup + scratch-file hygiene.** Delete the two cycle-38+ resolved entries. PRE-REGISTER a new cycle-39+ entry: `Fold tests/test_cycle38_mock_scan_llm_reload_safe.py into tests/test_capture.py::TestMockScanLlmReloadSafety` (cycle-4 L4 freeze-and-fold). Verify scratch files (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`) absent before PR open per cycle-34 hygiene test.

11. **Probe-commit hygiene (D6 hardened).** Probe commit titled `probe(cycle 38): diagnostic prints for AC7/AC8 POSIX investigation`; revert commit follows; **mandate squash-merge** of feature branch into main (cycle-37 L1 already prefers squash for compactness). Add `T20` (flake8-print) to `pyproject.toml [tool.ruff.lint].select` for defense-in-depth so ruff CI catches any unreverted prints in `src/`. Step-10 explicit grep step: `grep -n 'print(' src/kb/capture.py` against `git diff main` — zero new lines.

---

## FINAL DECIDED DESIGN

### Q1 — Subprocess refactor of TestSymlinkGuard

**OPTIONS.** A: dual-site patch only (R2's proposal). B: subprocess refactor only. C: hybrid (subprocess refactor for the symlink test + dual-site patch for defense-in-depth).

**ARGUE.**
## Analysis

R2's dual-site patch addresses the contamination at the wrong layer. The fundamental issue is that `tests/test_capture.py:20-37` does `from kb.capture import capture_items, _extract_items_via_llm, _exclusive_atomic_write, _build_slug, _scan_for_secrets, _validate_input, _verify_body_is_verbatim, _write_item_files, ...`. These names are bound at COLLECTION TIME — pytest imports the test module, which imports `kb.capture`, which executes the module-import-time security guard at lines 833-844. Now `tests/test_capture.py` namespace has `capture_items` = OLD `kb.capture` function object. When `TestSymlinkGuard` runs `del sys.modules["kb.capture"]` and reimports, a NEW `kb.capture` module object is created, but `tests/test_capture.py` keeps the OLD function references in its namespace. OLD `capture_items.__globals__` IS OLD `kb.capture.__dict__`. The mock_scan_llm fixture's `monkeypatch.setattr("kb.capture.call_llm_json", fake)` patches the NEW module's `__dict__` (because `sys.modules["kb.capture"]` now points to NEW). The OLD module's `__dict__` remains pristine — its `call_llm_json` symbol still references the original real function. When a sibling test calls `capture_items(...)` via the test-namespace name, that's the OLD function, which looks up `call_llm_json` via OLD `__globals__` → finds the REAL function → 401 dummy-key auth error.

R2's proposed `kb.utils.llm.call_llm_json` patch is independent of all this. R2's mental model assumes that OLD `kb.capture.__dict__["call_llm_json"]` would be re-resolved through `kb.utils.llm.__dict__` at runtime, but that's NOT how Python `from X import Y` works. The `from` import is a one-time copy: `kb.capture.__dict__["call_llm_json"] = kb.utils.llm.__dict__["call_llm_json"]` — same object, but two separate dict slots. Mutating `kb.utils.llm.__dict__["call_llm_json"]` doesn't update `kb.capture.__dict__["call_llm_json"]`. So the dual-site patch is INCOMPLETE on POSIX precisely because `tests/test_capture.py`'s OLD-snapshot namespace bypasses both patch sites for OLD-module function resolution.

The only actually-correct fix is to eliminate the contamination source. Subprocess execution of the symlink test means it never mutates the test runner's `sys.modules`. The OLD/NEW module identity issue evaporates. Plus, dual-site patching is still cheap defense-in-depth for the future case where some OTHER test introduces `del sys.modules["kb.capture"]` (option C).

**DECIDE: Option C — Hybrid.**

**RATIONALE.** Subprocess refactor (AC0, NEW) eliminates the proven 2026-04 contamination source. Dual-site patch (AC1) hardens against any future recurrence. Cost: +30 LoC subprocess + +0.3-0.5s startup + the dual-site widening (already in AC1/AC2/AC6). Benefit: 14 currently-skipped tests can have their skipif decorators removed without fixture widening per-test, AND future similar contamination patterns can't break the mock infrastructure. The dual-site patch alone (Option A) is insufficient — R2's analysis missed that `tests/test_capture.py`'s pre-collection bindings hold OLD module references.

**CONFIDENCE: HIGH.** Verified by reading `src/kb/capture.py:820-844` (security guard), `tests/test_capture.py:20-37` (pre-collection bindings), `tests/test_capture.py:700-714` (symlink test), `tests/conftest.py:362-391` (mock_scan_llm), and `src/kb/config.py:3-9` (R2's claim that config has no `kb.utils.llm` import).

### Q2 — Reload pattern for AC5 regression test

**OPTIONS.** A: R1's `monkeypatch.delenv("ANTHROPIC_API_KEY")` + reload-of-utils.llm pattern. B: R2's sys.modules deletion + reimport pattern. C: Hybrid (both patterns combined).

**ARGUE.**
## Analysis

R1's reload-of-utils.llm pattern is VACUOUS. R2 proved this experimentally: reloading `kb.utils.llm` BEFORE installing `mock_scan_llm` doesn't break the single-site patch — the setattr runs after the reload, overwriting `kb.capture.call_llm_json` with `fake_call`, and that binding holds because `kb.capture.__dict__["call_llm_json"]` is still in place (only the upstream `kb.utils.llm.__dict__["call_llm_json"]` was reloaded; the downstream snapshot in `kb.capture` survives reload). Pre-cycle-38 fixture (single-site) PASSES R1's case (b). The test proves nothing and violates `feedback_test_behavior_over_signature`.

R2's sys.modules deletion-AFTER-install pattern is the correct shape. Test asserts that the single-site patch is BROKEN by the deletion+reimport (case b assert mock did NOT fire), then with dual-site (post-AC1) repeats and asserts mock DID fire (case c). The manual revert check (locally revert AC1, run case c, expect FAIL) provides the not-vacuous proof per `feedback_test_behavior_over_signature` and `feedback_inspect_source_tests`. The `monkeypatch.delitem` (vs direct `del`) provides automatic teardown per pytest-monkeypatch conventions, avoiding cross-test state leak. R1's `monkeypatch.delenv("ANTHROPIC_API_KEY")` IS still useful — orthogonal — preventing a developer with a real `.env` key from false-passing via the real SDK. Combining both is option C.

**DECIDE: Option C — sys.modules deletion + delenv API key.**

**RATIONALE.** R2's sys.modules pattern is the only non-vacuous shape. R1's delenv guard prevents real-key false-pass. Both costs are trivial. Test file: `tests/test_cycle38_mock_scan_llm_reload_safe.py` per Brainstorm Q5 Approach A.

**CONFIDENCE: HIGH.**

### Q3 — Same-class peer scan scope (atomic_text_write patches)

**OPTIONS.** A: strict scope (only test_capture.py:741,754). B: widen all 23 atomic_text_write patches across tests/ (brainstorm's recommendation). C: refactor to shared fixture.

**ARGUE.**
## Analysis

R2's grep table (Section 4 of R2 eval) is decisive: only test_capture.py:741,754 patch `kb.capture.atomic_text_write` via string path. The other 21 atomic_text_write patches either use module-object refs (immune to sys.modules contamination because the ref was captured before any deletion) or target modules not subject to `del sys.modules`. Cycle-16 L1 is "scan to confirm no peers" — and the scan confirms 0 peers with the same risk pattern. Brainstorm's Approach B (widen all) overcommits, adding noise to 21 unrelated test files for zero regression-evidence benefit.

The pragmatic stance from R1 (Approach A + Step-11 peer-scan confirmation) wins. Two test files (test_cycle33_ingest_index_idempotency.py and test_v0915_task02.py) use string-path patches on `kb.ingest.pipeline.atomic_text_write`; these are theoretically-vulnerable but `kb.ingest.pipeline` is not subject to `del sys.modules` today. R2 correctly notes them as monitored-but-deferred. Document those two sites in implementation notes for cycle-39 if a similar contamination surfaces.

**DECIDE: Approach A — strict scope.**

**RATIONALE.** R1 + R2 align; brainstorm's Approach B is a scope creep. Document monitored-deferred peers (`test_cycle33_ingest_index_idempotency.py` lines 68/99/119/161/187 + `test_v0915_task02.py` lines 17/45) in implementation notes per cycle-16 L1 documentation requirement. Diverges from brainstorm.

**CONFIDENCE: HIGH.**

### Q4 — pip-audit invocation in Step-10/Step-11 mirror

**OPTIONS.** A: Use `-r requirements.txt` (matches threat-model section 7 as written). B: Use live-env mode (no `-r` flag; matches ci.yml). C: Use both (require both to pass).

**ARGUE.**
## Analysis

R2 caught a real divergence. The cycle-34 `fix-after-CI-failure-4` comment in `.github/workflows/ci.yml` documents that `-r requirements.txt` triggers ResolutionImpossible on the arxiv 2.4.1 vs requests 2.33.0 conflict, so CI uses live-env mode (audit the installed env, not the requirements file). The threat-model says `pip-audit -r requirements.txt --format=json`, which diverges from CI. On a developer machine where the conflict manifests, the local mirror produces false-pass or false-fail vs CI.

The Step-10 mirror MUST match CI to be a valid mirror per cycle-34 L6. Option B (live-env mode, no `-r`) is correct. Option A is what the threat-model says today and is wrong. Option C wastes effort — running both modes provides no information beyond what live-env mode reports.

**DECIDE: Option B — live-env mode.**

**RATIONALE.** Step-10 mirror must match ci.yml exactly (cycle-34 L6). Threat-model section 7 will be amended to remove the `-r requirements.txt` flag, replacing the command with `pip-audit --ignore-vuln=GHSA-xqmj-j6mv-4862 --format=json` (reproducing ci.yml's exact invocation modulo `--format=json` for diff comparison).

**CONFIDENCE: HIGH.**

### Q5 — Probe-commit print escape gating

**OPTIONS.** A: Add ruff T20 to pyproject.toml. B: Mandate squash-merge of probe+revert. C: Add explicit grep step in Step-10 mirror. D: All three (defense-in-depth).

**ARGUE.**
## Analysis

R2 caught that ruff T20 is not in pyproject.toml today, so no ci.yml step catches `print()` in `src/`. The threat-model Step-11 grep is manual and can be skipped under time pressure. Brainstorm D6 says "revert before Step-13 PR open" but does NOT mandate squash-merge or rebase-out — a non-squash merge of feature-branch with two commits (probe + revert) lands BOTH on main, so the print() lines briefly exist on main before being immediately reverted in the next commit. Under git blame, they show up. They also subtly violate cycle-22 L5 "no debugging artifacts in src/".

Adding T20 to pyproject.toml is a 1-line change with broad future benefit — every cycle thereafter is protected. Squash-merge mandate is a process discipline that aligns with cycle-37 L1 squash-preference. Explicit Step-10 grep is documentation polish. All three are cheap; defense-in-depth is the right call.

**DECIDE: Option D — all three.**

**RATIONALE.** ruff T20 add (1 line in pyproject.toml lint config) catches the failure mode automatically going forward. Squash-merge mandate ensures probe commit never ships to main even with a non-reverted state. Step-10 grep catches it locally before push. Three layers, near-zero cost.

**CONFIDENCE: HIGH.**

### Q6 — AC9 no-change branch explicit

**OPTIONS.** A: Leave AC9 as written (implicit). B: Add explicit no-change-branch language.

**ARGUE.**
## Analysis

R2 noted AC9 is ambiguous about the no-change path. If pip-audit does NOT catch up, the implementer must update only BACKLOG.md (re-check date) and leave ci.yml/SECURITY.md/requirements.txt untouched. AC9 says this implicitly via "if pip-audit caught up, add the ID..." but a less-experienced implementer might think the ABSENCE of catch-up still requires some workflow change. Explicit is better than implicit per Python's Zen.

**DECIDE: Option B — make explicit.**

**RATIONALE.** Add to AC9 text: "Expected outcome: pip-audit does NOT surface the IDs (drift persists). ONLY BACKLOG.md changes (re-check date 2026-04-26). ci.yml, SECURITY.md, requirements.txt are unchanged. This is the expected no-change branch."

**CONFIDENCE: HIGH.**

### Q7 — Cycle-39+ fold-into-canonical for new test file

**OPTIONS.** A: Pre-register cycle-39+ BACKLOG entry now (during AC10). B: Defer registration until cycle-38 ships. C: Don't register (cycle-tagged file is a permanent home).

**ARGUE.**
## Analysis

The cycle-4 L4 freeze-and-fold rule says versioned test files (`test_v0917_*.py`) eventually fold into canonical module test files. The cycle-tagged convention (`test_cycle36_*.py`, `test_cycle37_*.py`) is a recent addition and the freeze-and-fold rule's applicability is debated — R1's Q5 analysis says cycle-tagged is convention-established, R2 says fold should be pre-registered. The conservative call is C36-style: ship cycle-tagged, pre-register the fold for a future cycle. This honors both conventions: cycle-tagged for shipping discoverability, fold-into-canonical for long-term hygiene.

Pre-registering during AC10 has trivial cost (one BACKLOG.md line) and prevents the fold from accumulating untracked. It also tests the cycle-22 L4 "register meta-work as backlog" discipline.

**DECIDE: Option A — pre-register.**

**RATIONALE.** Add to AC10: also create new cycle-39+ BACKLOG entry under "Test infrastructure" — `Fold tests/test_cycle38_mock_scan_llm_reload_safe.py into tests/test_capture.py::TestMockScanLlmReloadSafety` (LOW; cycle-4 L4 freeze-and-fold).

**CONFIDENCE: MEDIUM.** Slight ambiguity: cycle-tagged convention may be eligible for a different rule than `test_v*` versioned files. Erring on the side of explicit-registration is low-cost.

### Q8 — Doc-hygiene scratch-file check

**OPTIONS.** A: Add explicit scratch-file-cleanup language to AC10. B: Rely on cycle-34 hygiene test (auto-gates).

**ARGUE.**
## Analysis

R2 noted the cycle-34 hygiene test gates findings.md/progress.md/task_plan.md/claude4.6.md absence. The test is automatic, so technically Option B suffices. But the test FAILS at PR-open time, and the diagnostic message is generic ("scratch file present"); making AC10 explicit reduces implementer surprise per `feedback_cleanup_scratch_files`. The explicit step also serves as a Step-12-level documentation check (verify no doc rot before PR open).

**DECIDE: Option A — explicit.**

**RATIONALE.** Add to AC10: "Verify no scratch files (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`) exist under project root before PR open. The cycle-34 hygiene test auto-fails on these — explicit check avoids surprise." Cost: one sentence.

**CONFIDENCE: HIGH.**

### Brainstorm Q1-Q5 (re-stated for completeness)

Each was already resolved by R1+R2 analysis above; concise re-statements:

**B-Q1 (mock_scan_llm + extractors).** DECIDE: Approach A — capture + utils.llm only. RATIONALE: extending to `kb.ingest.extractors` collides with extractor-flow tests. CONFIDENCE: HIGH.

**B-Q2 (AC7 fix direction).** DECIDE: Approach A — probe commit. RATIONALE: cheapest path to ground truth; D6 enforces probe hygiene; M1 standing pre-auth covers scope-cut. CONFIDENCE: HIGH.

**B-Q3 (AC6 peer scan).** DECIDE: Approach A — strict scope (DIVERGE from brainstorm). RATIONALE: R2's grep confirms 0 peers with same risk pattern. CONFIDENCE: HIGH.

**B-Q4 (AC9 in-cycle decision).** DECIDE: Approach A. RATIONALE: narrow-role rationale already gated in cycle-36 Q17; this is re-confirmation. CONFIDENCE: HIGH.

**B-Q5 (AC5 location).** DECIDE: Approach A — cycle-tagged file with cycle-39 fold pre-register (Q7 above). CONFIDENCE: HIGH.

### Cross-cuts D1-D6 + M1 (concise)

**D1 — primary-session.** DECIDE: as written (10 ACs ≤ 15-AC threshold; 0-1 src files ≤ 5-file threshold; cycle-37 L5 default). HIGH.

**D2 — TDD ordering.** DECIDE: AC0 (subprocess refactor) → AC1 → AC2 → AC5 → AC3+AC4 → AC6 → AC7+AC8. AC0 inserted at front because subprocess refactor must land before AC5 case (b)/(c) can be reliably written. AC9+AC10 are doc-only; run during Step 12. HIGH.

**D3 — Step 9.5 skip.** DECIDE: skip (0-1 src files, <50 LoC src diff). HIGH.

**D4 — R3 review skip.** DECIDE: R1+R2 only; skip R3. RATIONALE: 10 ACs (R1-eval said 10), now 11 with AC0 added — still below 25-AC R3 trigger; ≤5 src files; no new write surface; no new security enforcement point; ≤10 design-gate questions (this doc has 8 + B-Q1..5 + D1-6 + M1 = ~20, but the cycle-17 L4 R3-trigger metric is "design-gate Q count requiring escalation" which is 0). HIGH.

**D5 — Codex dispatch.** DECIDE: as written. HIGH.

**D6 — probe hygiene hardened.** DECIDE: as written + Q5 amendments (T20, squash-merge mandate, explicit grep). HIGH.

**M1 — scope-cut pre-auth.** DECIDE: APPROVE. RATIONALE: aligns with `feedback_minimize_subagent_pauses` (skip-conditions pre-decided to avoid runtime gates). HIGH.

---

### FINAL AC LIST (renumbered for new shape)

**AC0 (NEW) — Subprocess refactor of TestSymlinkGuard.** Move `test_symlink_outside_project_root_refuses_import` (`tests/test_capture.py:700-714`) into a `subprocess.run([sys.executable, "-c", probe_script], env={"KB_TEST_SYMLINK_TARGET": str(symlink_dir), "KB_TEST_PROJECT_ROOT": str(tmp_path / "project_root")}, capture_output=True)` invocation. The probe script imports `kb.capture` and asserts the RuntimeError; parent test asserts subprocess returncode != 0 and stderr contains `"SECURITY: CAPTURES_DIR"`. Verification: `grep -n "del sys.modules" tests/test_capture.py` returns 0 hits.

**AC1 (REVISED) — widen mock_scan_llm to dual-site patch.** `tests/conftest.py::mock_scan_llm` patches `kb.utils.llm.call_llm_json` BEFORE `kb.capture.call_llm_json`. Document ordering in fixture docstring. Drops the conditional widening from R2 risk register.

**AC2 (UNCHANGED) — widen inline `kb.capture.call_llm_json` patches.** Lines 419, 1126 each get paired `kb.utils.llm.call_llm_json` patch.

**AC3 (UNCHANGED) — remove `_REQUIRES_REAL_API_KEY` from 7 test_capture.py tests.**

**AC4 (UNCHANGED) — remove `_REQUIRES_REAL_API_KEY` from 3 test_mcp_core.py tests.**

**AC5 (REVISED) — non-vacuous regression test for mock_scan_llm reload-safety.** Three cases per CONDITIONS §3: (a) baseline post-AC1, (b) sys.modules-deletion-after-single-site-install proves single-site broken, (c) sys.modules-deletion-after-dual-site-install proves dual-site fix. `monkeypatch.delitem(sys.modules, "kb.capture", raising=False)` for cleanup. `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` before each call. Manual revert check documented in test file comment.

**AC6 (REVISED) — widen `kb.capture.atomic_text_write` patches in 2 tests + drop `@_WINDOWS_ONLY`.** Strict scope (only `test_cleans_up_reservation_on_inner_write_failure` line 741 + `test_cleans_up_on_keyboard_interrupt` line 754). Document monitored-deferred peers in implementation notes.

**AC7 (REVISED) — POSIX off-by-one slug probe.** AC7-a: probe commit with `print()` diagnostics in `_scan_existing_slugs` / `_build_slug` / `_reserve_hidden_temp`; lands on feature branch only. AC7-b: probe-revealed fix (production OR test loosen) lands; probe revert commit included. M1 standing pre-auth: if probe inconclusive, restore `_WINDOWS_ONLY` on offending test, document as cycle-39 candidate.

**AC8 (REVISED) — `test_creates_dir_if_missing` POSIX probe.** Same probe-revert structure as AC7. Same M1 pre-auth.

**AC9 (REVISED with Q6 amendment) — Dependabot drift refresh.** Run `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` + `pip-audit --ignore-vuln=GHSA-xqmj-j6mv-4862 --format=json` (live-env mode, no `-r`). Update BACKLOG entries with re-check date 2026-04-26. **Expected no-change path**: pip-audit does NOT surface GHSA-r75f / GHSA-v4p8 (drift persists); ONLY BACKLOG.md updates; ci.yml, SECURITY.md, requirements.txt unchanged. **If catch-up branch fires**: add the IDs to ci.yml `--ignore-vuln` arg with existing narrow-role rationale (litellm dev-eval-only; click<8.2 transitive blocks 1.83.7).

**AC10 (REVISED with Q7 + Q8) — BACKLOG cleanup + cycle-39 fold pre-register + scratch-file hygiene.** Delete the two cycle-38 resolved entries. Add new cycle-39+ BACKLOG entry: `Fold tests/test_cycle38_mock_scan_llm_reload_safe.py into tests/test_capture.py::TestMockScanLlmReloadSafety` (LOW; cycle-4 L4 freeze-and-fold). Verify scratch files (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`) absent before PR open. Add ruff `T20` to `pyproject.toml [tool.ruff.lint].select` for probe-print defense.

---

## AMENDMENTS to requirements.md

**Add AC0 (NEW)** — Subprocess refactor of TestSymlinkGuard. Insert between section 3 (Acceptance criteria) header and AC1 as Area 0 — Test isolation hardening.

**Revise AC1 hypothesis** — replace "even if a sibling test's `importlib.reload(kb.config)` cascade re-binds module-top imports inside `kb.capture`" with "even if a sibling test's `del sys.modules['kb.capture']` + reimport contamination re-creates the module under a fresh namespace". Add explicit ordering note: "patch `kb.utils.llm.call_llm_json` BEFORE `kb.capture.call_llm_json`".

**Revise AC5** — replace case (b) (reload-of-utils.llm before install) with case (b)/(c) shape per CONDITIONS §3. Add `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)`. Add manual revert check.

**Revise AC9** — add explicit no-change-branch language per Q6.

**Revise AC10** — add cycle-39 fold pre-register per Q7 + scratch-file hygiene per Q8 + ruff T20 add per Q5.

**Revise §4 Blast Radius table** — add row for `pyproject.toml` (T20 lint rule add); add row for `tests/test_capture.py` AC0 subprocess refactor (~30 LoC). Source file changes is now: 0-1 (`.github/workflows/ci.yml` if AC9 fires) + 1 (`pyproject.toml` T20 add). 11 ACs ≤ 15-AC threshold; cycle still qualifies for primary-session.

**Revise §6 Risk register** — drop R2 (conditional widening) since AC1 is unconditional. Add new R4: "AC0 subprocess refactor adds 0.3-0.5s test runtime per pytest run; trivial CI cost." Add new R5: "Subprocess startup may have OS-specific quirks (Windows vs POSIX env-var passing)." Mitigation: pass env via the `env` kwarg of `subprocess.run`, capture stdout+stderr, assert with explicit text matches.

**Revise §7 Open questions** — all 5 brainstorm Qs + Q1-Q8 from this gate are RESOLVED above. Mark §7 as "Resolved in Step-5 design gate (2026-04-26)".

**Revise threat-model §7** — change Step-11 pip-audit invocation from `pip-audit -r requirements.txt --format=json` to `pip-audit --ignore-vuln=GHSA-xqmj-j6mv-4862 --format=json` (live-env mode matching ci.yml).

**Add ruff T20 to pyproject.toml** — append `T20` (flake8-print) to `[tool.ruff.lint].select`. Existing rules E/F/I/W/UP remain. Tests directory unaffected (only `src/` lint matters for probe-print escape).

**Add explicit Step-10 grep** — in the Step-10 mirror checklist: `grep -n 'print(' src/kb/capture.py | grep -v '^#'` against `git diff main -- src/kb/capture.py` — must show zero new print lines after probe revert.

**Squash-merge mandate** — add to D6: cycle-38 PR MUST be squash-merged so the probe + revert pair never lands on main as separate commits.

**No changes to Area D AC10 numbering** — although AC numbering shifts from 10 to 11 with AC0 insert, the BACKLOG-cleanup AC remains last (AC10 conceptually; renumbered AC11 if strict). Keep "AC10" label in this design doc to minimize requirement-doc churn; in implementation, AC numbering is internal-only.

---

**Word count: ~3,720.**
