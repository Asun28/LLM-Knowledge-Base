# Cycle 65 Step 20 R1 review

**Verdict:** APPROVE  
**Confidence:** high (10+ grep/read anchors; both Step 09 BLOCKERs fixed; all cycle-lessons PASS)  
**Coverage:** R1 angle (BLOCKER+MAJOR + cycle-lessons-rule audit).

## Summary

Both Step 09 background review BLOCKERs (DeepSeek-flagged) were fixed:
- **BLOCKER-1 (AC16):** Fixed in commit 6d728fc. Substring containment via `if secret_value in elem`.
- **BLOCKER-2 (AC23):** Fixed in commit ff1c0fd. AST-walk (not string grep) via `find_calls_of`.

All cycle-lessons compliance (7 lessons across 10 angles) PASS with grep evidence.

## Cycle-lessons compliance

**Cycle-7 L1 (revert-tolerance):** PASS
- AC23 uses AST-walk (comments don't match Call nodes).
- AC10 revert (delete is_symlink check) causes test FAIL.

**Cycle-19 L2 (reload-leak):** PASS
- AC1 `get_project_root()` reads `os.environ.get("KB_PROJECT_ROOT")` at call time (lines 64-66).
- Test exercises monkeypatch post-import; verifies new env value (test_cycle65_config_call_time.py:14-37).

**Cycle-23 L4 (same-class peer scan):** PASS
- OOS-3 modules (mcp/browse.py, mcp/compile.py, mcp/health.py) documented in threat-model.md line 327.
- AC21 scope (core/ingest/quality) properly isolated.

**Cycle-22 L5 (conditions-as-tests):** PASS
- All 23 conditions mapped to named test functions.
- Sample: C1→test_get_project_root_call_time_accessor, C8→test_three_historical_sites_present, C18→test_actual_env_value_blocked.

**Cycle-19 L3 (empty-secret skip):** PASS
- Line 155-156: `if not secret_value: continue` (skips key, not elem loop).

**Cycle-24 L4 (revert-tolerance):** PASS
- AC23 + AC10 both revert-immune via AST-walk and integration test logic.

**Q2.x design-lock:**
- Q2.1: MODEL_TIERS constants retained ✓
- Q2.2: _assert_under_project_root has exactly 4 kwonly params ✓
- Q2.3: Fallback logs once-per-process warning ✓
- Q2.10: AC16 tests use monkeypatch.setenv exclusively (no os.environ.get) ✓

## Step-12 scope-reduction audit

AC9 originally consolidated 3 sites; Step 12 hard-gate discovered:
- `_validate_page_id` anchored to WIKI_DIR (not PROJECT_ROOT); tests construct tmp_path WIKI_DIR outside worktree. Reverted to inline (mcp/app.py:316-320).
- `_validate_wiki_dir` has cycle-29 explicit `project_root=` override; helper breaks contract. Preserved as thin wrapper.
- `_validate_path_under_project_root` successfully migrated to _assert_under_project_root in compile/compiler.py.

**Equivalence verdict:** Both inline checks semantically correct for their respective contracts ✓

## AC10 Windows defense

**TOCTOU race window:** Windows `path.is_symlink()` check is non-atomic (race between check and unlink). POSIX O_NOFOLLOW is atomic.

**Cycle-66 deferral acceptable?** YES — single-process threat model covered; multi-process requires ctypes HANDLE revision (deferred).

## PR body accuracy

- **Commits:** 38 ✓
- **Tests:** 47+ collected; plan claims 30 named ✓
- **Version:** v0.12.0 in src/kb/__init__.py + pyproject.toml ✓

## Final verdict

- BLOCKER findings: 0 ✓
- MAJOR findings: 0 ✓
- NIT findings: 0 ✓
- Cycle-lessons: 7/7 compliance verified ✓
- Design-lock fidelity: Q2.1-Q2.10 PASS ✓

**APPROVE for merge to main.**
