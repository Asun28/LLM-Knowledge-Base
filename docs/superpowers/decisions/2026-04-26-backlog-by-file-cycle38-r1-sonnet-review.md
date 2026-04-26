# Cycle 38 PR #52 — R1 Sonnet Edge-Case Review

**Verdict:** APPROVE-WITH-AMENDMENTS (one MAJOR finding on AC5 vacuous-test risk; two MINOR; three NIT)

**Reviewer focus:** edge cases, failure modes, security, test gaps, vacuous-test risk
**Branch:** `feat/backlog-by-file-cycle38` · 19 files · +1972/-37
**Cycle:** 38 (10 ACs incl. AC0 NEW; below R3 thresholds)

---

## Findings by focus area

### 1. AC5 vacuous-test risk — MAJOR

**File:** `tests/test_cycle38_mock_scan_llm_reload_safe.py:106-165`

The cycle-38 simplified case (b) abandons R2-Codex's design-gate sys.modules-deletion replay (CONDITIONS §3 case b/c) in favour of an order-independent contract assertion (lines 140, 145, 150). This SHIPPED shape is partially revert-tolerant — the first assertion (line 140) DOES catch the AC1 utils.llm setattr being commented out — but two structural problems remain:

**Problem 1: assertion-order divergence point is fragile.**
If AC1's first setattr line (`monkeypatch.setattr("kb.utils.llm.call_llm_json", fake_call)` at `tests/conftest.py:401`) is reverted, line 140 fails as the test claims. GOOD. But if AC1's SECOND setattr line at `tests/conftest.py:402` is reverted instead (the original pre-cycle-38 single-site `kb.capture` patch), line 140 still PASSES (utils.llm IS patched), line 145 FAILS instead (kb.capture NOT patched). The test description says "If you reverted the utils.llm setattr line in conftest's _install, this test correctly fails" — narrow scope. If a refactor swaps the two lines (drops the kb.capture line keeping only utils.llm), the regression is *partially* caught. This is acceptable per `feedback_test_behavior_over_signature` because every code-path that breaks the contract DOES fail SOME assertion, but the diagnostic message in line 140 misleads reviewers about WHICH revert was committed.

**Problem 2: `kb_utils_llm_mod.call_llm_json is not real_call` could be True without cycle-38 AC1.**
Walk-through: `real_call = kb_utils_llm_mod.call_llm_json` at line 133 runs BEFORE `mock_scan_llm(canned)` at line 136. If ANY autouse fixture or earlier non-autouse fixture in the same test (per pytest fixture-resolution order) has previously called `monkeypatch.setattr("kb.utils.llm.call_llm_json", X)` and the monkeypatch teardown order leaves it patched at the moment line 133 runs, `real_call` captures the ALREADY-PATCHED value (some `X`). Then `mock_scan_llm` overwrites both sites with `fake_call`. Line 140 evaluates `fake_call is not X` which is True — test passes WITHOUT cycle-38 AC1. Survey of test fixtures: `tests/conftest.py:362-404 mock_scan_llm` is non-autouse so it can't fire before the test; `_reset_embeddings_state` autouse touches `kb.query.embeddings` only; `_restore_kb_capture` autouse (line 168-178 in the new file) is post-yield only. **Assessment: actual risk is LOW but not zero** — this is `feedback_inspect_source_tests` territory. The test relies on `real_call` being the ACTUAL real function, not a snapshot of an already-patched state.

**Concrete fix:** Reorder assertions so the strongest revert-detection runs first. Change line 140 vs 145 ordering: assert `kb_capture_mod.call_llm_json is fake-pointer` first (this is the always-patched site since pre-cycle-38), then assert `kb_utils_llm_mod.call_llm_json is fake-pointer` (the AC1-specific site). Better yet, capture the pre-mock identity of BOTH `kb_capture_mod.call_llm_json` AND `kb_utils_llm_mod.call_llm_json` and assert BOTH change after `mock_scan_llm(canned)`. Even better: explicitly call the CALLABLE (e.g. `kb_utils_llm_mod.call_llm_json("test", schema={})`) and verify the canned response comes back — that's behaviour-not-signature per `feedback_test_behavior_over_signature`. The existing line 156-165 `capture_items` call partially does this, but only verifies the kb.capture-bound site indirectly.

**Verdict:** MAJOR but not blocking — case (a) baseline at line 91-104 plus the line 156-165 behavioural sanity does provide a non-vacuous floor. Recommend a follow-up commit BEFORE squash-merge that adds explicit pre-mock identity capture. If not addressed in cycle 38, register as cycle-39 BACKLOG entry.

---

### 2. AC0 subprocess probe failure modes — MINOR

**File:** `tests/test_capture.py:713-762`

Reviewed each failure mode:

- **Exit 0 because `sys.exit(2)` doesn't fire** — covered. The probe at line 749-750 emits stderr "module imported without raising" and `sys.exit(2)`. Parent at line 759 asserts `result.returncode == 42`. Any non-42 exit (0, 1, 2, or unexpected) trips the assertion with full stdout/stderr in the failure message. GOOD.

- **`RuntimeError` wrapped in another exception** — partially covered. Line 744 catches `RuntimeError` only. If a future cycle introduces a subclass like `SecurityError(RuntimeError)`, it still matches. If the guard is changed to raise a non-`RuntimeError` (e.g. `OSError`, `SystemExit`), this test silently exits 2 without distinguishing. Acceptable today since `src/kb/capture.py:840` raises `RuntimeError(...)` literally. Not a NIT — production code change would naturally update this test.

- **Windows developer-mode symlink syntax differences** — line 720-723 wraps `symlink_to` in try/except OSError → `pytest.skip`. Robust.

- **`sys.argv[1]` / `sys.argv[2]` escaping** — `subprocess.run` uses argv list-form, NOT shell. `tmp_path` from pytest is a controlled tmp directory (no spaces, no quotes typically). On Windows, `tmp_path` could be `C:\Users\Admin\AppData\Local\Temp\pytest-of-Admin\pytest-N\test_*\`. Backslashes in `str(symlink_dir)` are passed as raw argv elements — Python receives them as-is. `Path(sys.argv[1])` constructs a Path from the string. **Edge case I checked**: If `tmp_path` ever contains a space (e.g. `C:\Program Files\...`), argv list-form still works (each list element is a single argv item; no shell quoting needed). If `tmp_path` contains a Unicode character not encodable in the system's stdio encoding, the subprocess might receive mojibake; but `subprocess.run(..., text=True)` defaults to `locale.getpreferredencoding()` which on modern Windows is UTF-8 with `PYTHONUTF8=1` on Python 3.13 (Python 3.15 default). **Acceptable.** Not blocking.

**Verdict:** MINOR — robust enough for the stated test purpose. Consider adding `encoding="utf-8"` explicitly to the `subprocess.run` call for forward-portability across locales. One-line change at `tests/test_capture.py:756`.

---

### 3. Reload-leak class — defensive coverage gap — MINOR

Ran the requested `git grep -nE "del sys\.modules|sys\.modules\.pop|importlib\.reload" tests/`. 35 hits across 14 files. Per-file assessment:

- `test_v45_h17_vector_rebuild.py:218,220,233,249` — `sys.modules.pop("kb.query.embeddings", None)`. This is `kb.query.embeddings`, NOT `kb.capture`. AC0/AC1 don't cover this site, but the cycle-38 fix is scoped to capture-flow contamination. If the embeddings module ever gets its `call_llm_json` snapshot equivalent re-imported under a contaminating sys.modules state, similar dual-site widening would be needed. NOT in scope for cycle 38.
- `test_v099_phase39.py:32-82` — repeated `importlib.reload(kb.config)`. Per the design doc's R2 finding (`kb.config` imports only stdlib), this CANNOT cascade into `kb.utils.llm` or `kb.capture`. Cycle-38 fix unaffected.
- `test_cycle12_config_project_root.py`, `test_cycle15_cli_incremental.py`, `test_v0912_phase393.py`, `test_v5_augment_config.py` — all reload `kb.config` only. Same analysis: safe.
- `test_cycle20_errors_taxonomy.py:242` — `importlib.reload(kb.errors)`. Distinct module. No cycle-38 interaction.
- `test_v0915_task06.py:312` — `importlib.reload(checks)` (lint.checks). No interaction.
- `test_cycle33_mcp_core_path_leak.py:295` — comment only, no actual deletion.
- `test_cycle19_mcp_monkeypatch_migration.py`, `test_cycle22_wiki_guard_grounding.py`, `test_cycle23_rebuild_indexes.py`, `test_cycle28_first_query_observability.py` — comments documenting prior reload-leak patterns; no executable deletions.

**Net:** zero remaining `del sys.modules["kb.capture"]` hits in tests/ post-cycle-38. AC0 closes the only test that did this. Defensive coverage of cycle-19 L2 / cycle-20 L1 reload-leak class is COMPLETE for the kb.capture module. The dual-site AC1 hardens against a hypothetical future re-introduction. 

**Verdict:** MINOR documentation gap — the cycle-38 design doc claims AC0+AC1 close 2 of cycle-19 L2's vector classes; the actual scan confirms zero cycle-38-relevant deletions remain in tests/. Suggest adding to the cycle-38 lessons file: "AC0 confirms `del sys.modules` pattern eliminated for kb.capture; vector class for kb.query.embeddings remains (test_v45_h17_vector_rebuild.py)". Not blocking.

---

### 4. AC1 fixture ordering — concurrent fixture race — MINOR

**File:** `tests/conftest.py:399-402`

`monkeypatch.setattr` calls in `_install` are sequential within a single test's setup phase. Pytest-monkeypatch teardown runs in reverse-of-install order — so the kb.capture site is unwound first, then utils.llm. The two setattr calls touch different module objects (`kb.utils.llm.__dict__` vs `kb.capture.__dict__`), so no deadlock or atomic-sequence issue.

**pytest-xdist** (the concurrency vector named in the prompt) — verified `pyproject.toml` does NOT pull pytest-xdist. CI doesn't use `-n auto`. Within a single worker, fixtures run in the test's own setup phase serially. Even if pytest-xdist were enabled, each worker has its OWN python process with its OWN sys.modules — cross-worker race is impossible.

For AC2 inline patches at `tests/test_capture.py:421-422` (line 419's comment) and `tests/test_capture.py:1181-1182` — same pattern. Sequential setattr; reverse-order teardown. No race.

**Edge case checked:** Is there an interaction where `monkeypatch.setattr("kb.utils.llm.call_llm_json", X)` triggers an attribute lookup that REIMPORTS `kb.utils.llm`, which in turn triggers a `from kb.utils.llm import ...` cascade in `kb.capture`? Verified by reading `src/kb/utils/llm.py` (not shown but cross-referenced). The setattr is a `dict.__setitem__` on the module dict — no reimport, no cascade. Safe.

**Verdict:** MINOR — no race exists. Consider documenting the install-order invariant in `tests/conftest.py:399` more prominently (current comment at lines 399-400 implies it but doesn't state "MUST be utils.llm before kb.capture"). One-line clarification.

---

### 5. AC6 strict scope — same-class peer scan — PASS

**File:** `tests/test_capture.py:794, 808`

Confirmed via grep: `_exclusive_atomic_write` is defined ONLY in `src/kb/capture.py:461` and called from `src/kb/capture.py:472` (which itself calls `atomic_text_write` imported at line 36 from `kb.utils.io`). No OTHER call paths.

External callers of `kb.utils.io.atomic_text_write` across `src/kb/`: pages, review/refiner, compile/linker, compile/publish, lint/augment, mcp/core, lint/checks, ingest/evidence, query/formats/__init__, ingest/pipeline. **None of these go through `_exclusive_atomic_write`** — they call `atomic_text_write` directly. AC6's dual-site patch doesn't affect them because no test patches them via `kb.capture.atomic_text_write` string-path.

**Same-class peers in tests/** (per design Q3 monitored-deferred list):
- `test_cycle33_ingest_index_idempotency.py:68,99,119,161,187` — patches `kb.ingest.pipeline.atomic_text_write`. Different module. Cycle-38 AC6 doesn't widen these because `kb.ingest.pipeline` is NOT subject to `del sys.modules` today.
- `test_v0915_task02.py:17,45,74,99,128` — same module `kb.ingest.pipeline.atomic_text_write`. Same analysis.
- `test_v0915_task11.py:340,360,381,402` — same module. Same.
- `test_cycle24_evidence_inline_new_page.py:48` — comment about `kb.ingest.pipeline.atomic_text_write`. Comment only.

**Production code paths affected by AC6's dual-site:** zero. The dual-site adds a SECOND test-only setattr to `kb.utils.io.atomic_text_write`. Production callers always use the canonical `kb.utils.io.atomic_text_write`. Test paths now patch BOTH the canonical and the snapshot in `kb.capture` — same fake function reaches both sites. Behaviour identical for production-flow tests.

**Verdict:** PASS — strict scope correct. Design Q3 decision sound.

---

### 6. Q5 ruff T20 — pre-flight gap — NIT

**File:** `pyproject.toml:62`, `src/kb/query/formats/chart.py:37,54`

Ran `python -m ruff check src/ tests/` (via venv) — `All checks passed!`. T20 is active and reports zero violations.

**Borderline cases:**
- `src/kb/query/formats/chart.py:37,54` contain literal `print(...)` BUT they're INSIDE a triple-quoted string `_SCRIPT_TEMPLATE` (line 15-55). Ruff correctly excludes these because lexically they're string contents, not Python statements. Checked: ruff passes.
- `src/kb/cli.py:1-19` — uses `sys.stdout.write(...)` at line 18 for `--version`, NOT `print()`. Defensive against ruff T20 by design (cycle 7 AC30 short-circuit BEFORE click is loaded).
- `src/kb/__init__.py` — checked (not shown). Just `__version__` constant. No prints.

**Forward-compatibility concern:**
Future cycles adding a legitimate user-facing `print()` (e.g. a debug subcommand, a CLI banner) WILL hit T20 and need `# noqa: T201`. There is NO documentation in `pyproject.toml` (line 62) of WHEN T20 should be `# noqa`'d vs WHEN a print should be replaced with `click.echo()` or `logger.info()`. The current `[tool.ruff.lint]` block has a clear comment about cycle 38 AC7/AC8 probe defense, but doesn't articulate the path forward for legitimate prints.

**Concrete fix:** Add a one-line note in the comment block at `pyproject.toml:60`: `# Legitimate print() in src/ MUST be wrapped with # noqa: T201 + a comment explaining why click.echo / logger is unsuitable. Default: replace with click.echo().` Alternatively, add an entry to `BACKLOG.md` under "Documentation" — LOW priority.

**Verdict:** NIT — T20 active and correct; documentation polish only.

---

### 7. AC10 BACKLOG cleanup — cycle-39+ tag drift — PASS

**File:** `BACKLOG.md` lines 162-176 (post-cycle-38)

Read the BACKLOG diff. Cycle-37+ tags are correctly re-pinned to cycle-39+. Verified entries:

- L162: `windows-latest CI matrix re-enable (cycle-39+)` ✓
- L164: `GHA-Windows multiprocessing spawn investigation (cycle-39+)` ✓
- L166: `tests/test_capture.py::TestWriteItemFiles POSIX off-by-one + creates_dir investigation (cycle-39+)` ✓ — this is the AC7+AC8 scope-cut per design M1 standing pre-auth, correctly retained as cycle-39+
- L168: `tests/test_cycle38_mock_scan_llm_reload_safe.py fold-into-canonical (cycle-39+)` ✓ — pre-registered per design Q7
- L170, L172: Dependabot drift entries re-pinned to `cycle-39+` ✓

**Resolved entries deleted (not strikethrough)** per `BACKLOG.md` lifecycle rules: the two cycle-38+ entries `mock_scan_llm POSIX reload-leak investigation` and `TestExclusiveAtomicWrite + TestWriteItemFiles POSIX cleanup behaviour` no longer appear in the post-cycle-38 BACKLOG. ✓

**Cycle-39+ tag consistency:** ALL deferred items now pin cycle-39+, no stragglers at cycle-37+ or cycle-38+. ✓

**Verdict:** PASS.

---

### 8. Test-count narrative drift — PASS

Ran `.venv/Scripts/python.exe -m pytest --collect-only -q | tail -1`: **`3014 tests collected in 3.84s`**.

Test files: `find tests -name 'test_*.py' | wc -l` → **259**. ✓

Doc citations:
- `CLAUDE.md:7` — "3014 tests / 259 files (3003 passed + 11 skipped on Windows local; ubuntu-latest CI strict-gated since cycle 36; windows-latest CI matrix deferred to cycle-39+ per cycle-36 L1 CI-cost discipline)" ✓
- `docs/reference/implementation-status.md:5` — "3014 tests / 259 files · 3003 passed + 11 skipped on Windows local" ✓
- `docs/reference/testing.md` — checked, matches.
- `CHANGELOG.md:35` — "Tests: 3012 → 3014 (+2: cycle-38 mock_scan_llm reload-safety regression — case (a) baseline + case (b) dual-site contract assertion; full Windows local: 3003 passed + 11 skipped, was 2991 + 21)" ✓
- `CHANGELOG-history.md:37` — matches.

All five doc sites match the actual collection count of 3014 / 259. **Verdict: PASS.** No NIT.

---

### 9. Manual revert check verification — NIT

The PR body and test docstring (`tests/test_cycle38_mock_scan_llm_reload_safe.py:15-25`) both claim the cycle-38 author manually reverted AC1's utils.llm setattr line and confirmed case (b) fails. There is **NO CI-time mechanism** that pins this revert behaviour automatically. The check is purely manual.

**Risk:** A future refactor that changes AC1's assertion order (per finding 1) or removes the `kb.utils.llm.call_llm_json` setattr could land green. The `is not real_call` assertion at line 140 is the only signal — and as noted in finding 1, it's slightly fragile to fixture-resolution order.

**Concrete options:**
- (a) Add a self-test that uses `inspect.getsource(mock_scan_llm)` to verify the string `kb.utils.llm.call_llm_json` is present in the fixture body. *(Covered by `feedback_inspect_source_tests`: such tests are signature-only.)*
- (b) Add a parametrized test that DELIBERATELY toggles a manual second-site patch and verifies the dual-site behaviour breaks under specific conditions. Higher cost.
- (c) Accept the manual-only verification, document in `feedback_test_behavior_over_signature` lessons file that "manual revert proofs SHOULD be re-verified during quarterly health checks". Lowest cost.

**Verdict:** NIT — accept option (c). The cost of a CI mechanism exceeds the benefit at this scope. Document in cycle-38 lessons.

---

## Vacuous-test risk assessment of AC5

**Case (a) baseline (line 91-104):**
Calls `capture_items` directly. If mock fires, `result.rejected_reason is None` and `len(result.items) == 1`. If mock does NOT fire (real SDK called with no API key), the real call raises `LLMError` from `kb.utils.llm.call_llm_json`. The test would fail at `capture_items(...)` raising. Non-vacuous: revert AC1 → real call → `LLMError` → test fails. ✓

**Case (b) signature contract (line 106-165):**

Walk-through of revert tolerance:

1. Revert AC1 utils.llm setattr (`tests/conftest.py:401`):
   - line 133: `real_call = kb_utils_llm_mod.call_llm_json` captures the REAL function
   - line 136: `mock_scan_llm(canned)` patches ONLY `kb.capture.call_llm_json` (line 402 still active)
   - line 140: `kb_utils_llm_mod.call_llm_json is not real_call` — utils.llm STILL points to real_call → assertion FAILS ✓ (non-vacuous)

2. Revert AC1 kb.capture setattr (`tests/conftest.py:402`):
   - line 133: real_call = real
   - line 136: mock_scan_llm patches ONLY utils.llm
   - line 140: utils.llm is fake_call, `fake_call is not real_call` → True → PASSES
   - line 145: `kb_capture_mod.call_llm_json is not real_call` — kb.capture STILL points to real → assertion FAILS ✓ (non-vacuous)

3. Revert BOTH AC1 setattrs (single-site fall-back to real on both):
   - line 140: utils.llm IS real_call → False → assertion FAILS ✓

4. Revert AC1 dual-site, replace with single setattr on a THIRD site (e.g. `kb.mcp.core.call_llm_json`):
   - line 140: utils.llm IS real_call → assertion FAILS ✓

5. Edge case: someone adds a NEW autouse fixture that calls `monkeypatch.setattr("kb.utils.llm.call_llm_json", ...)` BEFORE `mock_scan_llm` runs:
   - line 133: `real_call = X` (the autouse-patched value)
   - line 136: mock_scan_llm overwrites both sites with `fake_call`
   - line 140: `fake_call is not X` → True → PASSES even WITHOUT cycle-38 AC1 ⚠️

**Case 5 is the residual vacuous-risk path identified in finding 1.** Today no such autouse fixture exists. The test correctly asserts revert tolerance for cases 1-4 (the realistic revert scenarios). **Net assessment:** non-vacuous for the intended threat model; mild residual risk for fixture additions in future cycles.

**Behavioural sanity at line 156-165** further hardens: even in case 5, if `kb.capture.call_llm_json` revert leaves it pointing at the real function, `capture_items(_CANONICAL_CONTENT, ...)` will fail with `LLMError` from no-API-key. So the `result.rejected_reason is None` assertion at line 164 catches the kb.capture-site revert.

**Combined verdict:** AC5 is **non-vacuous for cases 1-3** (the realistic AC1-revert scenarios) but has a **theoretical vacuous-pass path under autouse-fixture proliferation**. MAJOR finding above mitigates this with the suggested explicit pre-mock identity capture pattern.

---

## Same-class peer scan results (Section 5)

`grep -nE "_exclusive_atomic_write|atomic_text_write" src/kb/`: 28 hits across `kb.capture`, `kb.utils.io`, `kb.utils.pages`, `kb.review.refiner`, `kb.compile.linker`, `kb.compile.publish`, `kb.lint.augment`, `kb.lint.checks`, `kb.mcp.core`, `kb.mcp.quality` (comment), `kb.lint.verdicts` (docstring), `kb.query.formats.common` (docstring), `kb.query.formats.__init__`, `kb.ingest.evidence`, `kb.ingest.pipeline`. Of these, `_exclusive_atomic_write` is defined and called ONLY in `kb.capture` (lines 461, 472). All other modules call `atomic_text_write` directly without going through the helper.

**No non-test code path is affected by the AC6 dual-site pattern.** Production callers always import from `kb.utils.io` directly. The dual-site monkeypatch in tests adds a redundant test-side setattr that catches the case where `kb.capture` re-imports under a contaminated sys.modules state. Strict scope decision sound.

---

## Final verdict + rationale

**APPROVE-WITH-AMENDMENTS.**

Cycle 38 closes the cycle-37-deferred POSIX test re-enable cleanly. AC0's subprocess refactor is the correct architectural fix (eliminates contamination at root); AC1's dual-site is sound defense-in-depth; AC6's strict-scope is well-supported by the same-class peer scan; AC10's BACKLOG cleanup is meticulous. T20 add is a valuable forward-protection.

**One MAJOR finding (AC5 case-b assertion-order fragility) is the only meaningful concern.** The test correctly catches reverts of either individual AC1 setattr line, but a fixture-proliferation scenario could theoretically vacuous-pass. Recommended fix: capture pre-mock identity of BOTH sites in case (b), assert BOTH change, and verify behavioural sanity through a CALLABLE invocation rather than identity check alone. Cost: ~10 LoC; benefit: closes residual vacuous-risk path for future fixture additions.

**Three NITs** (subprocess `encoding="utf-8"` polish, T20 documentation, manual-revert quarterly check) are documentation-grade and non-blocking.

**MAJOR fix can land in a follow-up commit before squash-merge OR be deferred to cycle-39 with explicit BACKLOG entry.** Either acceptable per cycle-38 risk profile (10 ACs, below R3, primary-session, ≤5 src files).

Word count: ~2,420.
