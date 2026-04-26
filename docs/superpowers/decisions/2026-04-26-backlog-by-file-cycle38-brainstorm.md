# Cycle 38 — Brainstorming

**Date:** 2026-04-26
**Companion:** [requirements](2026-04-26-backlog-by-file-cycle38-requirements.md), [threat-model](2026-04-26-backlog-by-file-cycle38-threat-model.md)
**Method:** Skill `superpowers:brainstorming`. Per `feedback_auto_approve`, user-gates replaced by Step-5 Opus subagent decision gate. This doc enumerates 2-3 approaches per open question; the gate picks one with rationale.

---

## Q1 — Should `mock_scan_llm` patch also `kb.ingest.extractors.call_llm_json`?

**Context.** `kb.utils.llm.call_llm_json` is also imported at module-top by `kb.ingest.extractors` (line 12) and `kb.lint.augment` (line 32). The cycle-38 reload-leak hypothesis says that if `kb.utils.llm` is reloaded, all three modules retain their OLD function pointer. Patching `kb.utils.llm.call_llm_json` AFTER reload sets the canonical NEW slot, but the three consumers still hold the old reference — except they will look up `<module>.call_llm_json` at every call (function globals lookup), which goes through the module's `__dict__` and reads the patched value IF that module's binding is patched.

**Approach A — Patch only the two relevant sites (kb.capture + kb.utils.llm).** mock_scan_llm is for capture-flow tests; widening to extractors collides with `tests/test_extractors.py` and `tests/test_capture.py::TestPipelineFrontmatterStrip` which patch `kb.ingest.extractors.call_llm_json` directly with a different fake (capture_prompt that returns extraction-shape dicts, not capture-shape dicts). Widening to extractors would break those tests because mock_scan_llm's fake_call would intercept and assert capture-schema keys that aren't there.

**Approach B — Patch all three import sites.** Defends against any future call path. Risk: collides with existing test patches as described above.

**Approach C — Patch `kb.utils.llm.call_llm_json` only (canonical source).** Relies on Python's name-resolution to bubble up. Doesn't work if `kb.capture` re-binds via fresh `from X import Y` after a reload — the capture module's snapshot pre-dates the patch.

**Recommendation: Approach A.** Match the actual patch sites in tests today. Mock collision is the bigger risk than incomplete coverage.

---

## Q2 — AC7 fix direction: adjust test or fix production?

**Context.** `test_pre_existing_file_collision` asserts `slug == "decision-foo-2"`; cycle-36 ubuntu probe surfaced `decision-foo-3`. Production code: `_scan_existing_slugs` returns `*.md` files only; `_build_slug` iterates 2..ceiling. Hypothesis paths:

- (i) `_scan_existing_slugs` returns extra entries on POSIX (e.g., hidden `.decision-foo-2.reserving` from a prior test, but tmp_captures_dir is fresh).
- (ii) Some autouse fixture seeds an extra `decision-foo-2.md` file.
- (iii) `_build_slug` skips `-2` due to a different precondition.
- (iv) The test's `_make_item` interaction with `_build_slug` differs because of POSIX directory ordering (unlikely — `_scan_existing_slugs` returns a `set`).

**Approach A — Probe-style commit (cycle-36 commit-1 pattern).** First commit adds diagnostic `print()` in `_scan_existing_slugs` and removes the `_WINDOWS_ONLY` skipif on AC7 only. CI ubuntu run logs the actual contents of `existing` set and the slug-generation trace. Second commit applies the targeted fix based on probe output (could be production OR test). Final commit removes the prints.

**Approach B — Loosen the test assertion to `slug.startswith("decision-foo-")`.** Accept either `-2` or `-3` as POSIX-legitimate. Lowest blast radius. Risk: hides a real production POSIX bug.

**Approach C — Fix production `_scan_existing_slugs` to also include `.reserving` temps.** If the root cause is residual `.reserving` files (cycle-17 hidden temp suffix), the production scan should account for them across cross-process collision retries. But this is speculation — no evidence yet.

**Recommendation: Approach A (probe commit).** Cheapest path to ground truth; cycle-36 already established the probe-style pattern. The probe commit is REVERTED before final merge so CI hygiene is preserved.

---

## Q3 — AC6 same-class peer scan for `atomic_text_write` patches

**Context.** Cycle-16 L1 (same-class peer scan): when fixing a security-class anti-pattern, grep the entire diff for semantically identical patterns elsewhere. AC6 widens `kb.capture.atomic_text_write` patches in 2 tests; do other tests in the codebase patch `kb.capture.atomic_text_write` or `kb.utils.io.atomic_text_write` and have the same reload-leak risk?

**Approach A — Strict scope: only the two failing tests.** AC6 ships only the cycle-36 ubuntu-probe failures. Other patches are legacy that may or may not have the same risk; defer until a test fails.

**Approach B — Same-class peer scan: grep `monkeypatch.setattr.*atomic_text_write` across all of `tests/`; widen ALL hits to dual-site if they patch the `kb.capture.*` re-bound name.** Lower drift risk; closes the class.

**Approach C — Refactor the patches into a shared fixture (`mock_atomic_text_write`)** that handles both sites uniformly, then migrate all current and future patches to the fixture.

**Recommendation: Approach B.** Cycle-16 L1 explicitly trades 5-10 lines of grep-edit work for closing the class. Approach C is a future-cycle refactor; not in scope.

---

## Q4 — AC9 `--ignore-vuln` decision flow

**Context.** If pip-audit catches up on litellm GHSA-r75f / GHSA-v4p8 between cycle-37 and cycle-38, CI will start failing because the `pip-audit` step in `.github/workflows/ci.yml` doesn't ignore those IDs (cycle-32 narrow-role rationale only covers GHSA-xqmj-j6mv-4862 today).

**Approach A — In-cycle decision.** AC9 explicitly authorises the `--ignore-vuln` addition iff (a) pip-audit emits the IDs AND (b) the narrow-role rationale (litellm dev-eval-only; zero `src/kb/` imports; click<8.2 transitive blocks 1.83.7) is unchanged. This matches the cycle-37 documented rationale + the BACKLOG Cycle-36 spawn entries.

**Approach B — Force a separate Step-5 design-gate pass for any new `--ignore-vuln` ID.** Higher friction, higher safety, but the rationale was already gated in cycle 36 Step-5 Q17.

**Approach C — Add the IDs preemptively now even if pip-audit doesn't surface them.** Belt-and-suspenders. Makes the diff cleaner if pip-audit catches up later. Risk: adds invisible noise to the CI workflow.

**Recommendation: Approach A.** The rationale IS already gated; this is a re-confirmation. Step-11 verification can re-check the click pin and the litellm transitive constraint.

---

## Q5 — AC5 regression test location: cycle-tagged or folded?

**Context.** Cycle-4 L4 + Phase 4.5 R3 freeze-and-fold rule: "once a version ships, fold its tests INTO the canonical module file". Cycle-15 L2 DROP-with-test-anchor: keep regression tests as forward-looking anchors. AC5 is a regression test for the mock_scan_llm fixture's reload-resistance.

**Approach A — Cycle-tagged file `tests/test_cycle38_mock_scan_llm_reload_safe.py`.** Matches the recent cycle pattern (cycle-36 has `test_cycle36_ci_hardening.py`, cycle-37 has `test_cycle37_requirements_split.py`). Easy to grep "what shipped in cycle N". Drift risk: BACKLOG entry about freeze-and-fold accrues.

**Approach B — Folded into `tests/test_capture.py::TestMockScanLlmReloadSafety`.** Matches the freeze-and-fold goal. Locality: the regression and the fixture-using tests live in the same file. Drift risk: test_capture.py is already 1500+ lines.

**Approach C — Folded into the conftest's mock_scan_llm fixture as an inline doctest.** Lowest blast radius; mock_scan_llm carries its own validation. Risk: doctests don't run by default in this project's pytest config.

**Recommendation: Approach A (cycle-tagged file).** Recent project convention is cycle-tagged for new ACs; the freeze-and-fold rule is for VERSIONED test files (`test_v0917_*.py`), not for cycle-tagged. The AC's regression test is also short (~50 LoC) and self-contained; folding into test_capture.py forces a future maintainer to grep the cycle number from inside a 1500-line file.

---

## Cross-cutting design decisions

**D1 — Implementation flow.** Per cycle-37 L5 (primary-session default for ≤15 ACs / ≤5 src files): cycle 38 has 10 ACs + 0-1 src files. Implementation flows through primary session, not Codex dispatch. Step-5 plan-gate still runs.

**D2 — TDD ordering.** AC1 (fixture widening) → AC2 (inline patch widening) → AC5 (regression test) → AC3+AC4 (skipif removal) → AC6 (atomic_text_write widening) → AC7+AC8 (probe + fix). AC9+AC10 are doc-only and run during Step 12.

**D3 — Step-9.5 simplify pass.** Cycle adds 0-1 src files; total `src/` diff <50 LoC. **Skip Step 9.5** per its own skip-when row.

**D4 — Step-14 review trigger.** 10 ACs, ≤5 src files, no new write surface, no new security enforcement point, ≤10 design-gate questions (5 here + cross-cuts). All cycle-17 L4 R3 triggers below threshold. **R1 + R2 only; skip R3.** Document the skip rationale in PR review trail.

**D5 — Codex dispatch.** Step 7 (plan) primary-session per cycle-14 L1. Step 8 (plan-gate) Codex subagent. Step 11 (security-verify) Codex subagent. Step 14 R1 = Codex + Sonnet parallel. Same as recent cycles.

**D6 — Probe commit hygiene.** AC7's probe commit MUST: (a) be a separate commit on the feature branch with title `probe(cycle 38): diagnostic prints for AC7 POSIX investigation`; (b) be REVERTED in a follow-up commit before Step-13 PR open; (c) the probe-CI run is for diagnostic only, not for the Step-10 hard gate.

---

## Open questions for Step-5 decision gate

The five Q1-Q5 above + D1-D6 cross-cuts + a meta-question:

**M1 — Scope cut option.** If during Step-9 implementation, AC7 OR AC8's probe reveals a deeper POSIX bug than test-side fix can address, can we narrow scope and re-pin to cycle-39+? Per requirements §6 R1, yes. Document the narrow-cut decision in the cycle-39+ BACKLOG entry. Step-5 should resolve this as standing pre-authorization.
