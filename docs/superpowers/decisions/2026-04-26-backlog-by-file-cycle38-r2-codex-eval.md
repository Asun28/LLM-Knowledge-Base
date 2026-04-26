# R2 Codex Eval -- Cycle 38 Design (2026-04-26)

**Reviewer role:** Edge cases / Failure modes / Integration / Security / Perf  
**Source files read:** src/kb/capture.py (imports lines 36-37), src/kb/utils/llm.py (imports lines 12-22), src/kb/config.py (imports lines 3-9)  
**Test files read:** tests/conftest.py (mock_scan_llm lines 363-389), tests/test_capture.py (symlink test lines 701-714; inline patches lines 419 and 1126), tests/test_v099_phase39.py (reload lines 32 47 61 75), tests/test_cycle15_cli_incremental.py (reload lines 51-56 85-90), tests/test_cycle12_config_project_root.py, .github/workflows/ci.yml, BACKLOG.md

---

## 1. Edge Cases on mock_scan_llm Widening (AC1)

### Findings

1. **MAJOR -- Monkeypatch teardown does NOT rescue a sys.modules deletion that fires after install.**
   conftest.py:389 installs the mock via `monkeypatch.setattr` into `kb.capture.__dict__`. The symlink security test at test_capture.py:710-713 executes `del sys.modules["kb.capture"]` then `importlib.import_module("kb.capture")`. If this test runs AFTER mock_scan_llm is installed in the same pytest session, the re-import re-executes capture.py:37 (`from kb.utils.llm import call_llm_json`) and rebinds `kb.capture.call_llm_json` to the real function. Monkeypatch teardown cannot rescue this: it restores by setattr to the pre-install value, which is also the real function.

2. **MAJOR -- Dual-site install order must be documented.**
   The AC1 dual-site patch must apply `kb.utils.llm.call_llm_json` BEFORE `kb.capture.call_llm_json`. If `kb.capture` is re-imported between the two setattr calls (unlikely but possible under concurrent fixture ordering), the `kb.utils.llm` patch must already be in place so the re-import picks up the mock. This ordering dependency is not mentioned in the requirements and must appear in the fixture docstring.

3. **MINOR -- No autouse fixture today reloads kb.utils.llm.**
   test_cycle15_cli_incremental.py:51-56 reloads kb.config, kb.compile.publish, and kb.cli -- none touch kb.utils.llm. Risk is low today; dual-site patch future-proofs against future autouse fixture widening.

### Recommended Amendments

- F1: Apply `kb.utils.llm` setattr BEFORE `kb.capture` setattr in mock_scan_llm._install(); document ordering in fixture docstring.
- F2: Add guard: if `"kb.capture"` not in sys.modules, import it explicitly before either setattr.
- F3 (MINOR): AC5 regression test comment must state the scenario simulated is sys.modules deletion + re-import, not importlib.reload of kb.utils.llm before install.

**Section verdict: AMEND**

---

## 2. Reload-Leak Hypothesis Verification

### Findings

1. **BLOCKER -- The reload-leak hypothesis as stated is factually incorrect.**
   kb.config (config.py imports lines 3-9) imports only logging, math, os, re, and standard-library types. It does NOT import kb.utils.llm. Python reloads do not cascade to importers: `importlib.reload(kb.config)` updates `kb.config.__dict__` in place but leaves `kb.utils.llm.__dict__` untouched. kb.utils.llm imports FROM kb.config (llm.py:12-20: `from kb.config import LLM_MAX_RETRIES, ...`) -- that is a one-way dependency; kb.config has zero knowledge of kb.utils.llm. Therefore the reload calls in test_v099_phase39.py (lines 32, 47, 61, 75), test_cycle12_config_project_root.py (lines 11, 23, 34, 50, 61, 81, 97), and test_cycle15_cli_incremental.py (lines 51, 85, 126) do NOT rebind `kb.capture.call_llm_json`. The requirements AC1 hypothesis ("sibling test importlib.reload(kb.config) cascade re-binds module-top imports inside kb.capture") is wrong.

2. **BLOCKER -- The actual root cause is sys.modules deletion in the symlink security test.**
   test_capture.py:710-713 does `del sys.modules["kb.capture"]` then `importlib.import_module("kb.capture")`. Under POSIX full-suite collection order, if this test runs in the same session as tests depending on mock_scan_llm and the single-site patch is already installed, the re-import re-executes capture.py:37 and binds the real function into `kb.capture.__dict__`. Subsequent tests that reinstall mock_scan_llm per-test are fine; tests that assume the fixture persists across tests are not.

3. **MAJOR -- AC1 fix is mechanically correct but for the wrong stated reason.**
   Patching `kb.utils.llm.call_llm_json` first means any subsequent re-import of `kb.capture` will bind the mocked function via `from kb.utils.llm import call_llm_json`. The fix works; the stated causal mechanism does not.

### Recommended Amendments

- F1 (BLOCKER): Revise AC1 hypothesis: replace "importlib.reload(kb.config) cascade" with "del sys.modules[kb.capture] + re-import in symlink security test at test_capture.py:710-713".
- F2 (BLOCKER): Revise AC5 case (b): replace "importlib.reload(kb.utils.llm) BEFORE installing" with "del sys.modules[kb.capture] + re-import AFTER installing single-site patch".
- F3 (MAJOR): Before writing AC5, confirm experimentally that reload(kb.config) alone does NOT break the single-site patch, and that sys.modules deletion DOES break it. Document findings in AC5 notes.

**Section verdict: AMEND** (hypothesis correction required; otherwise AC5 test is vacuous)

---

## 3. AC5 Regression Test Correctness

### Findings

1. **MAJOR -- The AC5 test as specified in requirements will be vacuous.**
   Case (b) as written: "importlib.reload(kb.utils.llm) BEFORE installing mock_scan_llm, then call, assert mock STILL fires." Analysis: reloading kb.utils.llm before fixture install does NOT defeat the single-site patch. The single-site setattr runs after the reload, overwriting `kb.capture.call_llm_json` with `fake_call`; that binding holds. The pre-cycle-38 fixture will PASS case (b). The test proves nothing and violates `feedback_test_behavior_over_signature`.

2. **MAJOR -- Correct non-vacuous test shape: sys.modules deletion after single-site install.**
   (a) Install single-site mock (temporarily bypass AC1 for this assertion). (b) `del sys.modules["kb.capture"]` + `importlib.import_module("kb.capture")`. (c) Call `kb.capture.capture_items`. (d) Assert mock did NOT fire -- proves single-site patch is broken post-reimport. With dual-site (post-AC1): (a) install dual-site mock. (b) same deletion + re-import. (c) call `capture_items`. (d) assert mock fired. Reverting AC1 locally makes step (d) fail, proving the test is not vacuous.

3. **MINOR -- sys.modules deletion in a test requires teardown.** Use `monkeypatch.delitem(sys.modules, "kb.capture", raising=False)` for automatic teardown; direct `del` is not safe without explicit try/finally.

### Recommended Amendments

- F1 (MAJOR): Replace reload scenario in AC5 spec with sys.modules deletion + re-import.
- F2 (MAJOR): AC5 implementation must include a manual revert-and-fail check confirming the test is not vacuous.
- F3 (MINOR): Use `monkeypatch.delitem` instead of direct `del`.

**Section verdict: AMEND**

---

## 4. AC6 Same-Class Peer Scan for atomic_text_write

### Findings

Grep results for `monkeypatch.setattr.*atomic_text_write` across `tests/`:

| File | Line(s) | Patch style | Reload-leak risk | AC6 action |
|------|---------|-------------|-----------------|------------|
| test_capture.py | 741, 754 | String path `"kb.capture.atomic_text_write"` | **YES** -- kb.capture is the module deleted+reimported by symlink test | Widen both |
| test_backlog_by_file_cycle7.py | 821-822 | Module object refs (io_mod, refiner) | LOW -- no sys.modules deletion for these | No change |
| test_cycle15_publish_atomic.py | 47,63,79,103 | Module object ref (publish) | LOW | No change |
| test_cycle15_publish_incremental.py | 67,91,115,147 | Module object ref (publish) | LOW | No change |
| test_cycle18_linker_lock.py | 126, 192 | Module object ref (linker) | LOW | No change |
| test_cycle24_evidence_inline_new_page.py | 50 | Module object ref (pipeline_mod) | LOW | No change |
| test_cycle33_ingest_index_idempotency.py | 68,99,119,161,187 | String path `"kb.ingest.pipeline.*"` | MEDIUM -- no deletion today; defer | Note as deferred |
| test_cycle35_ingest_index_writers.py | 45 | Module object ref (pipeline) | LOW | No change |
| test_v0914_phase395.py | 858 | String path `"kb.review.refiner.*"` | LOW | No change |
| test_v0915_task02.py | 17, 45 | String path `"kb.ingest.pipeline.*"` | MEDIUM -- defer | Note as deferred |

1. **MINOR -- Only test_capture.py:741,754 require AC6 widening in cycle 38.** The symlink security test is the unique risk amplifier; no other module in the suite is subject to `sys.modules` deletion.

2. **NIT -- cycle33/v0915 kb.ingest.pipeline string-path patches should be noted as deferred** in implementation notes to satisfy the cycle-16 L1 same-class peer scan documentation requirement.

### Recommended Amendments

- F1: AC6 scope is correct. Document cycle33/v0915 `kb.ingest.pipeline` sites as monitored-but-deferred in implementation notes.

**Section verdict: PROCEED**

---

## 5. AC7 + AC8 Probe-Commit Risk

### Findings

1. **MAJOR -- CI hard gate does NOT catch print() in src/.**
   ci.yml runs `ruff check src/ tests/` with rules E/F/I/W/UP (per pyproject.toml). Rule group T20 (flake8-print, which catches bare `print()` calls) is NOT selected. The `pytest -q` step captures stdout. No ci.yml step fails if diagnostic `print()` calls land in `src/kb/capture.py`. The threat-model Step-11 verification checklist includes a manual grep for `print(` in the diff but this is not automated and can be skipped under time pressure.

2. **MAJOR -- Probe commit can reach main if PR is opened before revert.**
   Brainstorm section D6 says REVERT before Step-13 PR open but does NOT mandate squash-merge. If an implementer opens the PR with two commits (probe + revert) and CI passes (it will), a non-squash merge lands both commits on main. The `print()` statements do not affect runtime correctness but produce noisy `src/kb/capture.py` diffs and could expose internal state via MCP server stdout on a production instance.

3. **MINOR -- The cycle-36 strict gate (continue-on-error: false on pytest step) catches test failures** introduced by probe commits but does not catch debug prints in source.

### Recommended Amendments

- F1 (MAJOR): Add ruff rule T20 to `pyproject.toml` `[tool.ruff.lint].select` to gate `print()` in `src/` via the existing Ruff check CI step. Also future-proofs all subsequent cycles.
- F2 (MAJOR): Update brainstorm section D6: mandate squash-merge of probe+revert before Step-13 PR open, OR require interactive rebase to remove the probe commit from the feature branch history before PR creation.
- F3 (MINOR): Promote the manual Step-11 grep (`grep -n 'print(' src/kb/capture.py` against the diff) to an explicit numbered checklist item in the implementation plan.

**Section verdict: AMEND**

---

## 6. CI Hard Gate Completeness Check (cycle-34 L6)

### Findings

1. **MINOR -- pip-audit in threat-model Step-11 uses wrong invocation.**
   threat-model section 7 Step-11 table lists: `pip-audit -r requirements.txt --format=json`. The ci.yml pip-audit step (cycle-34 fix-after-CI-failure-4 comment) audits the LIVE installed environment (no -r flag) specifically because `-r requirements.txt` triggers ResolutionImpossible on the arxiv 2.4.1 vs requests 2.33.0 conflict. The local mirror command as documented diverges from CI and produces false-pass or false-fail signals on machines where that conflict manifests.

2. **MINOR -- Step-10 mirror checklist omits pip check (soft-fail) and twine check dist/*.**
   ci.yml runs `pip check` with `continue-on-error: true` and `python -m twine check dist/*` as part of the Build step. Neither appears in the Step-10 local mirror. A new pip resolver conflict introduced by cycle 38 changes would not be caught locally before push.

3. **NIT -- Pytest collection smoke check (--collect-only -q) is in ci.yml but absent from Step-10 mirror.** Low impact since full `pytest -q` catches collection errors, but the smoke check provides a faster diagnostic signal.

4. **PASS -- No cycle-35 or cycle-37 steps were added to ci.yml.** Full ci.yml reviewed. Structure (Checkout, Setup Python 3.12, Install package + extras, Install CI tooling, Ruff check, Pytest collection smoke, Pytest full suite strict, Pip resolver check soft-fail, Pip-audit, Build + twine check) is unchanged since cycle 34. Step-10 mirror is complete for this structure minus the items above.

### Recommended Amendments

- F1 (MINOR): Correct threat-model section 7 pip-audit command to live-env mode: `pip-audit --ignore-vuln=...` (no -r flag).
- F2 (MINOR): Add `pip check` (continue-on-error) and `python -m twine check dist/*` to Step-10 local mirror checklist.
- F3 (NIT): Add `--collect-only` smoke check as optional fast-fail pre-check in Step-10.

**Section verdict: AMEND** (pip-audit invocation mismatch is a functional gap in the local mirror)

---

## 7. Missing ACs

### Findings

1. **PASS -- windows-latest CI matrix and GHA-Windows spawn investigation are correctly excluded.** BACKLOG.md:163,165 note cycle-38+ scope. Requirements section 2 explicitly excludes both. No oversight.

2. **MINOR -- AC10 does not pre-register test_cycle38_mock_scan_llm_reload_safe.py freeze-and-fold as a cycle-39+ BACKLOG candidate.**
   Brainstorm section Q5 chose the cycle-tagged file approach. Per cycle-4 L4 freeze-and-fold, versioned test files must eventually fold into the canonical module test file. The new test file should be pre-registered as a cycle-39+ fold-into-test_capture.py candidate.

3. **MINOR -- AC9 no-change branch is underspecified.**
   If pip-audit does NOT surface GHSA-r75f or GHSA-v4p8, AC9 produces only a BACKLOG.md date-refresh with no ci.yml, SECURITY.md, or requirements.txt change. This is correct but not explicitly stated as the expected outcome, risking implementer confusion.

4. **NIT -- cycle-34 hygiene test not referenced in AC10 doc-hygiene pass.** The test auto-gates scratch file presence (findings.md, progress.md, task_plan.md, claude4.6.md); an explicit mention reduces implementer surprise.

5. **PASS -- No uncovered cycle-38 BACKLOG items exist.** BACKLOG.md:163,165,167,169,171,173 enumerate all six cycle-38+ entries. AC1-AC10 address four; two (windows-latest, GHA-Windows spawn) are explicitly out-of-scope per requirements section 2.

### Recommended Amendments

- F1 (MINOR): Add cycle-39+ BACKLOG entry for test_cycle38_mock_scan_llm_reload_safe.py freeze-and-fold as part of AC10.
- F2 (MINOR): Add to AC9: "If pip-audit does not surface the IDs, only BACKLOG.md changes (re-check date updated). ci.yml and SECURITY.md are unchanged. This is the expected path."
- F3 (NIT): Add to AC10 doc-hygiene note: verify no scratch files (findings.md, progress.md, task_plan.md, claude4.6.md) exist under the project root before PR open.

**Section verdict: PROCEED** (no missing ACs of consequence; amendments are documentation polish)

---

## Overall Verdict

**APPROVE-WITH-AMENDMENTS**

Three findings require amendment before implementation begins:

1. **Hypothesis correction (Sections 2 + 3, BLOCKER):** The reload-leak root cause stated in the requirements is factually wrong. `importlib.reload(kb.config)` does not cascade to `kb.utils.llm` or `kb.capture` -- confirmed by reading config.py which contains zero `kb.utils.llm` imports. The actual failure vector is `del sys.modules["kb.capture"]` + re-import in the symlink security test (test_capture.py:710-713). AC5 case (b) as specified (reload-before-install) will be vacuous -- the pre-cycle-38 single-site fixture already passes it. Rewrite AC5 case (b) to simulate sys.modules deletion + re-import after single-site install.

2. **pip-audit invocation mismatch (Section 6, MINOR/FUNCTIONAL):** The Step-10/Step-11 local mirror lists `pip-audit -r requirements.txt` but ci.yml audits the live installed environment (no -r flag) due to the cycle-34 ResolutionImpossible fix. This divergence means the local mirror produces different results than CI on machines where the arxiv/requests conflict manifests. Correct the Step-11 command in threat-model section 7 before Step-10 runs.

3. **Probe-commit print escape not CI-gated (Section 5, MAJOR):** Ruff T20 is not in pyproject.toml; no ci.yml step catches `print()` in `src/`. An unreverted probe commit with diagnostic prints in `src/kb/capture.py` will pass CI and can reach main. Add ruff T20 to pyproject.toml before the probe commit is pushed, or add an explicit grep step in ci.yml. Also mandate squash-merge or rebase-out of the probe+revert pair before PR creation.

All other findings (Section 1 fixture ordering guards, Section 4 peer-scan scope, Section 7 documentation gaps) are MINOR or NIT and can be resolved during implementation without a requirements rewrite.
