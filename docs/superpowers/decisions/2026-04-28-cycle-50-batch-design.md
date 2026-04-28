# Cycle 50 — Design Decision Gate (FINAL DECIDED DESIGN)

**Date:** 2026-04-28
**Owner:** primary session (per cycle-21 L1 + C37-L5 + cycle-48/49 precedent — fold cycle, ≤25 ACs, primary holds full Steps 1-4 context)
**Inputs:** `2026-04-28-cycle-50-batch-requirements.md` + R1 DeepSeek output at `.data/cycle-50/design-eval-r1-out.txt`

## R1 DeepSeek verdict (synthesised)

**APPROVE WITH MINOR AMENDMENTS** — 3 load-bearing amendments + 5 risk flags + 8 CONDITIONS for Step 09.

R1 confirmed:
- No name collisions in any of the 4 receivers.
- All 13 migrated tests are BEHAVIORAL (C40-L3 pass) — none vacuous, none signature-only, none docstring-only.
- Host-shape compatibility per C40-L5 verified for every receiver.

R1 amendments:

1. **Helper-name collision risk** in `test_llm.py` for `_FakeMessages` (class) and `_install_client` (function). R1 recommends `_TelemetryFakeMessages` / `_install_telemetry_client`.
2. **Import additions** must be confirmed: `frontmatter.default_handlers` in `test_lint.py`, `kb.mcp.health` imports in `test_mcp_core.py`, `import logging` + `from types import SimpleNamespace` + `from kb.utils import llm` in `test_llm.py`.
3. Execute all 8 Step-09 CONDITIONS (C1-C8) before source file deletion.

## Open questions and decisions

### Q1: Adopt R1 helper-rename amendment?

**Options:**
- A. Rename to `_TelemetryFakeMessages` / `_install_telemetry_client` per R1.
- B. Keep original `_FakeMessages` / `_install_client` names (test-only scope, no current collision).
- C. Rename to a tighter prefix like `_TelemetryClient` (one helper class with `messages` attribute + classmethod `install`).

**Argue:**
- Receiver `test_llm.py` has helpers `_make_response`, `_make_empty_response`, `_make_api_status_error`, `_make_rate_limit_error`, `_make_connection_error`, `_make_timeout_error`. All factory-style, all prefixed `_make_`. Adding a class `_FakeMessages` + non-factory `_install_client` breaks the established receiver pattern. Prefixing for telemetry context makes intent explicit.
- Option C (consolidate to one helper) is closer to existing receiver style but requires structural rewrite of the 2 telemetry tests. Adds risk.
- Option B is the path of least change but risks future-cycle conflict if any other test wants to mock `llm.get_client` in a different way.
- Option A is incremental: same shape (class + factory function), different names. Two-line rename.

**Decide:** **A.** Rename `_FakeMessages` → `_TelemetryFakeMessages`; `_install_client` → `_install_telemetry_client`. Rationale: matches receiver naming pattern (telemetry-scoped, explicit), addresses R1 amendment 1 with minimal structural change, and per `feedback_test_behavior_over_signature` the test behavior is unchanged (calls go through the same `monkeypatch.setattr(llm, "get_client", ...)`).
**Confidence:** HIGH.

### Q2: Adopt R1 host-shape recommendation for fold 4 (single class vs 3 sub-classes)?

**Options:**
- A. Single class `TestMcpWikiDirValidation` with 9 methods (R1's recommendation).
- B. 3 sub-classes `TestKbCompileScanWikiDirValidation` / `TestKbLintWikiDirValidation` / `TestKbEvolveWikiDirValidation` with 3 methods each.
- C. Bare functions (mirror existing kb_compile_scan bare-function tests at line 282-330).

**Argue:**
- Receiver `test_mcp_core.py` uses BOTH bare functions AND classes. Existing classes: `TestKbCaptureWrapper` (semantic group: kb_capture wrapper behavior), `TestKbCreatePageHintErrors` (semantic group: kb_create_page hint validation). Both wrap a coherent feature surface.
- The 9 wiki_dir validation tests share a single semantic feature: "MCP boundary path validation". Single class matches the existing class-grouping precedent.
- 3 sub-classes would introduce 3 namespaces for what is effectively 1 contract test repeated across 3 tools. Over-fragmentation.
- Bare-function would not preserve the helper `_missing_abs_path` cleanly without polluting module scope.
- Single class allows `_missing_abs_path` as `@staticmethod` — class-scoped, private, no module pollution.

**Decide:** **A.** Single class `TestMcpWikiDirValidation` with 9 methods + `@staticmethod _missing_abs_path` helper. Placement: insert after the existing `# ── kb_compile_scan ─` section (line 330 boundary), BEFORE `# ── kb_capture wrapper ─` section at line 333. Rationale: groups MCP-boundary contract tests near their tool families, follows existing "section-then-class" pattern for grouped behavior tests.
**Confidence:** HIGH.

### Q3: Section comment placement for folds 1 and 2?

**Options:**
- A. Cycle 9 yaml-load test → INSIDE existing `# ── Source coverage checks ─` section (no new section comment).
- B. Cycle 9 yaml-load test → NEW `# ── Source coverage cycle-9 yaml-load contract ─` section.
- C. (For cycle 45) → INSIDE existing `# ── Runner tests ─` section.
- D. (For cycle 45) → NEW `# ── Runner enumeration order contract ─` section.

**Argue:**
- Existing receiver sections group by feature, not cycle. The yaml-load test extends "Source coverage" coverage; it tests `check_source_coverage` (same target as the existing 2 source-coverage tests). Same section.
- The cycle-45 runner-order test extends `run_all_checks` coverage; `# ── Runner tests ─` already groups runner tests.
- New section comments add visual noise without semantic grouping benefit.
- C40-L5 says preserve host-shape — that includes existing section organisation.

**Decide:**
- **A** for fold 1: insert into existing `# ── Source coverage checks ─` section (after `test_check_source_coverage_empty` at line 161). No new section comment.
- **C** for fold 2: insert into existing `# ── Runner tests ─` section (after `test_format_report_clean` at line 216). No new section comment.
**Confidence:** HIGH.

### Q4: Section comment placement for fold 3?

**Options:**
- A. Append at end of `test_llm.py` (after `# ── _backoff_delay helper ─` at line 393) as a NEW `# ── Telemetry: _make_api_call success path (cycle 50 fold) ─` section.
- B. Insert near the `# ── _backoff_delay helper ─` section (also internal helpers).
- C. Insert near top, immediately after `# ── Helpers ─`.

**Argue:**
- The 2 telemetry tests are the FIRST tests in the file that target `_make_api_call` directly (private function). Existing tests target `call_llm` (public function).
- Internal-helper testing is a distinct concern. Grouping with `_backoff_delay` (also internal helper) under a new section provides clear grouping.
- Top placement (option C) would push down the existing well-organised public-API tests; bad receiver shape disturbance.
- End placement (option A) preserves all existing test organisation and adds the telemetry tests as a clearly-labeled new section.

**Decide:** **A.** Append at end as `# ── Telemetry: _make_api_call success path (cycle 50 fold) ─` after the `_backoff_delay` section. Helpers `_TelemetryFakeMessages` + `_install_telemetry_client` go into the existing `# ── Helpers ─` section (after `_make_timeout_error` at line 53).
**Confidence:** HIGH.

### Q5: Skip Step 6 Context7?

**Options:**
- A. Run Step 6 — verify `frontmatter.default_handlers.yaml.load` API hasn't changed.
- B. Skip Step 6 — skill explicitly says "skip-when: pure stdlib/internal code" applies here (test-only fold of existing tests).

**Argue:**
- Cycle 9 lint test uses `frontmatter.default_handlers.yaml.load` which is a third-party library API. R1 amendment 2 requires confirming no import-side-effects.
- However, the test ALREADY exists on `main` and passes. We are MOVING it, not editing it. Library API hasn't changed (test is green on `main`).
- C31-L1 says Step 6 Context7 is MANDATORY when Step 5 references any third-party library kwarg. We don't reference any new kwargs — we just preserve existing usage.

**Decide:** **B.** Skip Step 6. Rationale: pure mechanical move; library API surface is unchanged from cycle-9 ship state which has been green for ~40 cycles.
**Confidence:** HIGH.

### Q6: Skip Step 9.5 simplify pass?

Per skill skip-when: "Skip when: total `src/` diff < 50 LoC. Pure dep-bump cycle. Signature-preserving rename / move only."

**Decide:** Skip. `src/` diff is 0 LoC (test-only). Each fold is signature-preserving. Recorded in Step 16.
**Confidence:** HIGH.

### Q7: Skip Step 11.5 existing-CVE patch?

All 4 baseline CVEs:
- diskcache CVE-2025-69872 — `fix_versions=[]`
- litellm GHSA-xqmj-j6mv-4862 — `fix_versions=['1.83.7']` BUT 1.83.7..1.83.14 transitively pin `click==8.1.8` which conflicts with our `click==8.3.2` pin (per BACKLOG.md cycle-22 L4).
- pip CVE-2026-3219 — `fix_versions=[]`
- ragas CVE-2026-6587 — `fix_versions=[]`

**Decide:** Skip. No patchable upstream version. Re-confirm BACKLOG entries with cycle-50 timestamps. Same posture as cycles 32-49.
**Confidence:** HIGH.

### Q8: PR review rounds — R1 only, R1+R2, or R1+R2+R3?

Per `feedback_3_round_pr_review`: "For batches >25 items, run 3 independent review rounds; round 3 typically APPROVES but still catches regressions". This cycle has 25 ACs.

Per cycle-16 L4 / C36-L2: R3 trigger criteria include >=15 ACs when there's a NEW security enforcement point. This cycle has zero new src/ + zero new security surface.

Per cycle-49 precedent: 18 ACs, R1 only (R2 SKIP per cadence match — hygiene-only cycle, no security surface).

**Decide:** **R1 only.** R2 skip per cycle-49 precedent (hygiene cycle, no security surface, zero src/ diff). If R1 surfaces blockers, address inline + re-verify but do not promote to R2/R3 unless they cite security or correctness regressions. R3 explicitly out.
**Confidence:** HIGH.

## FINAL DECIDED DESIGN

### Folds (4 commits)

| # | Source (DELETE) | Receiver (EDIT) | Insertion shape | Insertion point |
|---|---|---|---|---|
| 1 | `tests/test_cycle9_lint_checks.py` | `tests/test_lint.py` | bare function | line 161 (after `test_check_source_coverage_empty`) inside `# ── Source coverage checks ─` |
| 2 | `tests/test_cycle45_lint_runner_order_invariant.py` | `tests/test_lint.py` | bare function + module-level `EXPECTED_CHECK_ORDER` constant | line 216 (after `test_format_report_clean`) inside `# ── Runner tests ─` |
| 3 | `tests/test_cycle8_llm_telemetry.py` | `tests/test_llm.py` | bare functions + module-level helpers `_TelemetryFakeMessages` (class) + `_install_telemetry_client` (function) | helpers in `# ── Helpers ─` section after line 53; tests in NEW `# ── Telemetry: _make_api_call success path (cycle 50 fold) ─` section after line 414 |
| 4 | `tests/test_cycle9_mcp_path_validation.py` | `tests/test_mcp_core.py` | single class `TestMcpWikiDirValidation` (9 methods + `@staticmethod _missing_abs_path`) | line 331 (between `# ── kb_compile_scan ─` and `# ── kb_capture wrapper ─`) |

### Doc-sync (1 commit)

Files: CHANGELOG.md + CHANGELOG-history.md + CLAUDE.md + BACKLOG.md + README.md + docs/reference/{implementation-status,testing}.md.

### CONDITIONS (binding for Step 09 — load-bearing)

| ID | Condition | Verification |
|---|---|---|
| C1 | Per-fold revert-verify per C40-L3 — insert `assert False` at top of highest-coverage migrated test → run `pytest <receiver> -k <test_substring> -x` → confirm FAIL → restore. Record in commit body. | Manual; per-fold |
| C2 | Collision-free insertion — grep receiver for exact symbol names BEFORE writing | `grep -n` |
| C3 | Test count preserved at 3025 after all 4 folds | `pytest --collect-only -q \| tail -1` |
| C4 | No broken imports — `python -c "import tests.test_lint; import tests.test_llm; import tests.test_mcp_core"` returns 0 | shell exit 0 |
| C5 | `ruff check src/ tests/` exits 0; `ruff format --check src/ tests/` exits 0 (run AFTER all Edits, per `feedback_ruff_edit_ordering`) | shell exit 0 |
| C6 | Doc-sync completeness — grep CLAUDE.md / README.md / docs/reference/{testing,implementation-status}.md for `237` (current count) and update to `233` | grep returns only historical narrative hits |
| C7 | Source files `git rm`'d only AFTER C1-C5 pass per fold | `git status` confirms 4 deletions |
| C8 | CHANGELOG / BACKLOG timestamp updates per AC17-AC25 | manual diff |
| C9 | Helpers `_TelemetryFakeMessages` and `_install_telemetry_client` placed in `# ── Helpers ─` section (NOT inline above tests) — preserves `test_llm.py` host-shape per C40-L5 | grep position vs section markers |
| C10 | `from kb.mcp.health import kb_evolve, kb_lint` added to `test_mcp_core.py` import block ABOVE the new `TestMcpWikiDirValidation` class | grep import position |
| C11 | `import frontmatter.default_handlers` added to `test_lint.py` import block (line 1-13 region) — NOT mid-file | grep import position |
| C12 | Full pytest suite passes (3014 + 11 skipped) on Windows local before commit-5 (doc-sync) | `pytest 2>&1 \| tail -2` |

### SCOPE-OUT items (explicit deferrals)

| ID | Item | Rationale |
|---|---|---|
| S1 | Fold of `test_cycle12_conftest.py` | No clear canonical receiver (closest match `test_conftest.py` doesn't exist; creating new file = net 0 fold). Defer. |
| S2 | Windows-latest CI matrix re-enable (BACKLOG cycle-50+) | Bumped to cycle-51+ per cycle-36 L1 CI-cost discipline + still-missing self-hosted Windows runner prerequisite. |
| S3 | GHA-Windows multiprocessing spawn investigation (BACKLOG cycle-50+) | Bumped to cycle-51+ — investigation requires self-hosted runner. |
| S4 | TestWriteItemFiles POSIX off-by-one (BACKLOG cycle-50+) | Bumped to cycle-51+ — investigation requires POSIX shell access. |
| S5 | LiteLLM CVE patch attempt | Blocked by `click==8.1.8` transitive constraint (cycle-22 L4 conservative posture preserved). |
| S6 | Phase 5 community proposals / Phase 6/7/8 candidates | User explicitly excluded from cycle 50 scope. |

## Verdict

**APPROVE.** All R1 amendments incorporated. 12 binding CONDITIONS. 6 explicit SCOPE-OUT items.

Cycle 50 is a routine fold + hygiene cycle following the established cycle-38..49 cadence. Risk profile: LOW. Test-only diff (`src/` = 0 LoC). No new security surface. No new CI dimension.

Proceed to Step 7 (implementation plan refinement) → Step 8 (plan gate) → Step 9 (TDD implementation per task) → Step 10 (CI hard gate) → Step 11 (security verify; minimal) → Step 12 (doc update) → Step 13 (PR) → Step 14 (R1 only) → Step 15 (merge).
