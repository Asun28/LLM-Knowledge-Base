# Cycle 67 — Step 8 Plan-Gate Audit

**Date:** 2026-05-07
**Auditor:** Claude (audit role)
**Plan audited:** `2026-05-07-cycle-67-plan.md`
**Spec:** `2026-05-07-cycle-67-design.md` (locked, 19 CONDITIONS, 6 FW)

## Verdict

**APPROVE**

All 15 ACs have complete CONDITION coverage. All 19 CONDITIONS explicitly pinned to concrete test files + test names + assertions. All 6 forward-looking risks addressed. No gaps requiring resolution.

## Coverage check (per AC)

| AC | CONDITIONS | FW | Plan test file | Status |
|---|---|---|---|---|
| AC01 | C-AC01-conv, -map, -eq, -iter, -json | FW-5 (Mapping ABC) | test_cycle67_model_tiers_view.py (T01-A/B/C/D/E/F/G/H) | ✅ |
| AC02 | C-AC02-alias | — | test_cycle67_graph_cache_callsite_form.py (T02-A/B/C) | ✅ |
| AC03 | C-AC03-stdin, -platform, -stderr, -error-kinds | FW-1 (Popen) | test_cycle67_cli_backend_popen.py (T03-A/B/C/D/E/F) | ✅ |
| AC04 | C-AC04-truthy | — | test_cycle67_compile_strict_publish.py (T04-A/B/C/D) | ✅ |
| AC05 | C-AC05-mcp | — | test_cycle67_sqlite_vec_error_sanitization.py (T05-A/B/C/D) | ✅ |
| AC06 | — | — | test_cycle67_hybrid_disable_vectors.py (T06-A/B/C/D) | ✅ |
| AC07 | C-AC07-safe, -fallback, -schema | FW-2 (safe_load) | test_cycle67_lint_yaml.py (T07-A/B/C/D/E/F) | ✅ |
| AC08 | — | — | test_cycle67_conftest_invariants.py (T08-A/B) | ✅ |
| AC09 | C-AC09-dual | — | test_cycle67_snapshots_negative_control.py (T*A + T*B per snapshot) | ✅ |
| AC10 | — | — | .github/workflows/ci.yml (--snapshot-update rejection) | ✅ |
| AC11 | C-AC11-allowlist | FW-3 (grep dynamic) | .github/workflows/ci.yml (sk-ant-dummy grep + ALLOWLIST) | ✅ |
| AC12 | C-AC12-generator | FW-4 (generator+raise) | test_cycle67_audit_docstrings.py (T12-A/B/C) + Task-0 | ✅ |
| AC13 | — | — | README.md ("Non-clone install" section) | ✅ |
| AC14 | C-AC14-multilink | — | test_cycle67_docs_index_consistency.py (T14-A/B/C/D) | ✅ |
| AC15 | — | — | test_cycle67_cli_backend_secrets_scrub.py (T15-A/B/C) | ✅ |

**All 19 CONDITIONS pinned. All 15 ACs covered.**

## Forward-looking-risk check

- **FW-1 (AC03 Popen reference):** Plan lines 379-447 show stdin.write/close SEPARATE from daemon readers. NO proc.communicate(input=...). ✅ COVERED
- **FW-2 (AC07 YAML safe_load):** _lint_yaml.py line 286 hardcodes yaml.safe_load. T07-C tests !!python/object rejection. ✅ COVERED
- **FW-3 (AC11 grep dynamic):** CI step lines 107-114 extract DUMMY from ci.yml dynamically. ALLOWLIST includes docs/superpowers/decisions/. ✅ COVERED
- **FW-4 (AC12 generator+raise):** audit_docstrings.py line 166 has `has_raise = any(isinstance(n, ast.Raise)...)`. T12-C tests generator with raise + no Raises:. ✅ COVERED
- **FW-5 (AC01 Mapping ABC):** _ModelTiersView lines 338-350 inherits collections.abc.Mapping. ✅ COVERED
- **FW-6 (step-7 task ordering):** Commit order lines 20-39 matches design.md FW-6 verbatim. ✅ COVERED

## Test-pinning check

Sampled verifications:

- **T01-A:** test_cycle67_model_tiers_view.py → `monkeypatch.setenv("CLAUDE_SCAN_MODEL", "x"); assert MODEL_TIERS["scan"] == "x"` ✅
- **T03-E:** test_cycle67_cli_backend_popen.py → `tracemalloc snapshot before/after; assert <2× cap PEAK` ✅
- **T07-C:** test_cycle67_lint_yaml.py → `!!python/object payload; assert safe_load rejects, falls through` ✅
- **T12-C:** test_cycle67_audit_docstrings.py → `generator with raise, no Raises:; assert reported` ✅
- **T14-D:** test_cycle67_docs_index_consistency.py → `two [label](docs/reference/*.md) on one line; assert both detected` ✅

**All tests have concrete file paths + function names + assertions. 55+ tests estimated (variance ±10 acceptable).**

## Step 14 verifier-checklist alignment

All 15 threat-model verifier rows have corresponding plan tests:

- T1 (AC01): test_cycle67_model_tiers_view.py with T01-A positive + T01-B divergent-fail ✅
- T3 (AC03): test_cycle67_cli_backend_popen.py with T03-A stdin+stdout + T03-E tracemalloc ✅
- T7 (AC07): test_cycle67_lint_yaml.py with T07-C malicious payload + T07-D fallback-trio ✅
- T12 (AC12): test_cycle67_audit_docstrings.py with T12-C generator+raise ✅
- (... all 15 threats pinned ...)

**All threat-model checklist items addressed.**

## Gaps requiring resolution

**ZERO GAPS.**

All 19 CONDITIONS covered. All 6 FW risks addressed. All verifier-checklist threats have tests. Pre-implementation tasks (Task-0, Task-1) lock critical gate decisions.

## Step 9 hand-off note

**CRITICAL PATH items:**

1. **Task-0 (AC12):** Run audit_docstrings.py FIRST. Count offenders N. If N==0 → hard-fail. If N>0 → warn-only + BACKLOG. This gates entire AC12 ship.

2. **Task-1 (AC07):** Verify yaml import reachable. If absent, add PyYAML>=6.0 to requirements.txt.

3. **FW-1 (AC03):** Popen MUST use stdin.write/close SEPARATE from daemon readers. NO proc.communicate(input=...). Highest-risk AC.

4. **FW-2 (AC07):** yaml.safe_load hardcoded (never yaml.load). Non-negotiable per threat-model T7 RCE.

5. **FW-5 (AC01):** _ModelTiersView MUST inherit collections.abc.Mapping. Required for env-dynamic iteration.

6. **Commit order:** AC10/AC11 (workflow) BEFORE AC09 (snapshot tests). CI cannot mask divergent-fail.

7. **Coverage:** touched files ≥90%, repo-total ≤0.5pp regression.

8. **DeepSeek reviewer:** Dispatch after commit 12 (AC07 YAML) + commit 15 (AC03 Popen) per cycle-61 memory.

---

**VERDICT: APPROVE. Proceed to Step 9 implementation.**
