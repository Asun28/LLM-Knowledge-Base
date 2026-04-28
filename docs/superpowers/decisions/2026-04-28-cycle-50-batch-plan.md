# Cycle 50 — Implementation Plan (draft, awaiting Step 5 design-gate confirmation)

**Source:** `2026-04-28-cycle-50-batch-requirements.md` (25 ACs)
**Drafted in primary session** per C14-L1 (operator holds context across Steps 1-3).

## Tasks (one commit per task per `feedback_batch_by_file`)

### TASK 1 — Fold `test_cycle9_lint_checks.py` → `tests/test_lint.py`
- **Files:** `tests/test_cycle9_lint_checks.py` (DELETE), `tests/test_lint.py` (EDIT)
- **Change:** Insert `test_check_source_coverage_parses_yaml_once_per_page` immediately after `test_check_source_coverage_empty` (line 161 boundary) inside the `# ── Source coverage checks ─` section. Add `import frontmatter.default_handlers` to the import block (line 1-13).
- **Test:** `pytest tests/test_lint.py -k parses_yaml_once -x` passes.
- **Revert-verify (C40-L3):** insert `assert False` at top of moved test → `pytest -x` FAIL → restore. Records evidence in commit body.
- **AC:** AC1, AC2, AC3
- **Threat:** N/A (no production code)

### TASK 2 — Fold `test_cycle45_lint_runner_order_invariant.py` → `tests/test_lint.py`
- **Files:** `tests/test_cycle45_lint_runner_order_invariant.py` (DELETE), `tests/test_lint.py` (EDIT)
- **Change:** Insert `EXPECTED_CHECK_ORDER` constant + `test_lint_runner_enumeration_order_unchanged` immediately after `test_format_report_clean` (line 216 boundary), before the `# ── augment._resolve_raw_dir branch coverage ─` section seam. Add `from kb.lint import runner` to the import block (line 1-13). Per C40-L5 host-shape: existing `# ── Runner tests ─` section is bare functions; preserve bare-function shape (do NOT wrap in a class).
- **Test:** `pytest tests/test_lint.py -k lint_runner_enumeration -x` passes.
- **Revert-verify (C40-L3):** `assert False` insertion → FAIL → restore.
- **AC:** AC4, AC5, AC6
- **Threat:** N/A

### TASK 3 — Fold `test_cycle8_llm_telemetry.py` → `tests/test_llm.py`
- **Files:** `tests/test_cycle8_llm_telemetry.py` (DELETE), `tests/test_llm.py` (EDIT)
- **Change:** Insert `_TelemetryFakeMessages` class (renamed from `_FakeMessages` per Step-5 Q1) + `_install_telemetry_client` helper (renamed from `_install_client` per Step-5 Q1) into the `# ── Helpers ─` section after `_make_timeout_error` (line 53 boundary) per C9. Add `import logging` + `from types import SimpleNamespace` + `from kb.utils import llm` to the import block (lines 1-10). Append a new `# ── Telemetry: _make_api_call success path (cycle 50 fold) ─` section with both telemetry tests at file end (after `test_backoff_delay_cap`, line 414 boundary) per Step-5 Q4. Per C40-L5 host-shape: existing test_llm.py is bare-function only; preserve bare-function shape.
- **Test:** `pytest tests/test_llm.py -k make_api_call -x` passes (2 tests).
- **Revert-verify (C40-L3):** `assert False` insertion on `test_make_api_call_success_logs_info_record_without_prompt_leak` → FAIL → restore.
- **AC:** AC7, AC8, AC9
- **Threat:** N/A

### TASK 4 — Fold `test_cycle9_mcp_path_validation.py` → `tests/test_mcp_core.py`
- **Files:** `tests/test_cycle9_mcp_path_validation.py` (DELETE), `tests/test_mcp_core.py` (EDIT)
- **Change:** Insert new section + class `TestMcpWikiDirValidation` (single class, 9 methods) immediately after `# ── kb_compile_scan ─` section (line 330 boundary), BEFORE `# ── kb_capture wrapper ─` at line 333. Per C40-L5 host-shape: existing test_mcp_core.py uses BOTH bare functions AND classes (TestKbCaptureWrapper at line 336, TestKbCreatePageHintErrors at line 624); class hosting is precedent-correct for grouped behavior tests. Single class with 9 tests is more compact than 3 sub-classes (uniform assertion shape across all 9). Convert `_missing_abs_path` to `@staticmethod`. Add `from kb.mcp.health import kb_evolve, kb_lint` to the import block.
- **Test:** `pytest tests/test_mcp_core.py::TestMcpWikiDirValidation -x` passes (9 tests).
- **Revert-verify (C40-L3):** `assert False` insertion on `test_kb_compile_scan_rejects_nonexistent_wiki_dir` (highest-coverage representative) → FAIL → restore.
- **AC:** AC10, AC11, AC12
- **Threat:** N/A

### TASK 5 — CI hard gate + count verification
- **Files:** none (verification only)
- **Change:** Run full pytest suite, ruff check, ruff format check.
- **Test:** `python -m pytest 2>&1 | tail -2` shows `3014 passed, 11 skipped`. `ruff check src/ tests/` exits 0. `ruff format --check src/ tests/` exits 0. `find tests -maxdepth 1 -name '*.py' -type f | wc -l` returns 233. `pytest --collect-only -q | tail -1` shows `3025 tests collected`.
- **AC:** AC13, AC14, AC15, AC16

### TASK 6 — Doc update (CHANGELOG + CLAUDE.md + BACKLOG + README + docs/reference)
- **Files:** `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md`, `BACKLOG.md`, `README.md`, `docs/reference/implementation-status.md`, `docs/reference/testing.md`
- **Change:**
  - `CHANGELOG.md` `[Unreleased]` Quick Reference: add compact cycle-50 entry (Items: 4 folds + dep-CVE re-confirm; Tests: 3025 (preserved); Scope: tests/ only; Detail: see CHANGELOG-history.md).
  - `CHANGELOG-history.md`: append full per-cycle bullet detail, newest first.
  - `CLAUDE.md` Quick Reference state line: `237 files` → `233 files`; `cycle 36..49` → `cycle 36..50` carry-over.
  - `BACKLOG.md` HIGH item 4 (lines 89-91): replace cycle-49 progress paragraph with cycle-50 progress paragraph documenting 4 folds + new file count math + each fold's revert-verify status.
  - `BACKLOG.md` CVE entries (diskcache / litellm / pip / ragas): timestamp updates `cycle-49` → `cycle-50` (re-confirmed against `.data/cycle-50/cve-baseline.json`).
  - `BACKLOG.md` Dependabot drift entries (cycle-49+ tagged for `GHSA-r75f-5x8p-qvmc`, `GHSA-v4p8-mg3p-g94g`): re-confirmed cycle-50.
  - `BACKLOG.md` cycle-50+ deferred tags (windows matrix re-enable, GHA-Windows multiprocessing, POSIX off-by-one in test_capture): bump to `cycle-51+`.
  - `README.md`: test count narrative sites updated (per C39-L3).
  - `docs/reference/implementation-status.md`, `docs/reference/testing.md`: test/file count updates (per C26-L2 extended).
- **Test:** Manual diff inspection. `grep -nE "cycle-50\+" BACKLOG.md` returns no hits (AC19). `grep -E "237" CLAUDE.md README.md docs/reference/{implementation-status,testing}.md` returns only stale historical hits (per-cycle history).
- **AC:** AC17, AC18, AC19, AC20, AC21, AC22, AC23, AC24, AC25
- **Threat:** N/A

## Commit graph

| # | Commit message | Files |
|---|---|---|
| 1 | `test(cycle 50): fold cycle9_lint_checks → test_lint.py` | 1 delete + test_lint.py |
| 2 | `test(cycle 50): fold cycle45_lint_runner_order_invariant → test_lint.py` | 1 delete + test_lint.py |
| 3 | `test(cycle 50): fold cycle8_llm_telemetry → test_llm.py` | 1 delete + test_llm.py |
| 4 | `test(cycle 50): fold cycle9_mcp_path_validation → test_mcp_core.py` | 1 delete + test_mcp_core.py |
| 5 | `docs(cycle 50): backlog hygiene + CVE re-confirm + count updates` | CHANGELOG.md + CHANGELOG-history.md + CLAUDE.md + BACKLOG.md + README.md + docs/reference/{implementation-status,testing}.md |

5 commits per `feedback_batch_by_file` (one commit per receiver file + one doc-sync commit). Step 11 / Step 12.5 / Step 13 commits possible additions (CVE patch no-op expected).

## Verification matrix

| AC | Verification |
|---|---|
| AC1, AC4, AC7, AC10 | `! test -f tests/<source>.py` |
| AC2, AC5, AC8, AC11 | `grep -q "<test_name>" tests/<receiver>.py` |
| AC3, AC6, AC9, AC12 | per-fold revert-verify recorded in commit body |
| AC13 | `pytest --collect-only -q \| tail -1` returns `3025 tests collected` |
| AC14 | `find tests -maxdepth 1 -name '*.py' -type f \| wc -l` returns 233 |
| AC15 | `pytest 2>&1 \| tail -2` shows `3014 passed, 11 skipped` |
| AC16 | `ruff check src/ tests/` exits 0; `ruff format --check src/ tests/` exits 0 |
| AC17-AC25 | manual diff inspection of doc files |

## Risk register

- **R1 (LOW):** Receiver `test_lint.py` has a trailing `from kb.lint import augment` at line 221 (mid-file, after the bare-function tests, before `class TestRawDirDerivation`). Cycle 9's import is `import frontmatter.default_handlers` — name doesn't conflict, but ruff E402 may flag the augment import as module-level-after-other-statements. Cycle 9 import goes in the top import block. Mitigation: keep cycle 9's import at top (line 1-13) where other imports already are; do not touch the line-221 augment import.
- **R2 (LOW):** test_mcp_core.py 702 lines — adding a 9-test class adds ~70 lines. File grows to ~770 lines. Per cycle 35-style file-size split, this is below the 1000-line threshold; no split warranted yet. Defer.
- **R3 (LOW):** Cycle 9 `test_kb_compile_scan_rejects_relative_wiki_dir` calls `kb_compile_scan(wiki_dir="wiki")` without monkeypatching `PROJECT_ROOT`. The existing `test_kb_compile_scan_no_changes` and `test_kb_compile_scan_reports_*` use `monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)`. The validation tests SHOULD reject before any PROJECT_ROOT lookup happens (since `wiki_dir="wiki"` is relative — fail-fast on absolute-path check). Confirm by reading the validation logic in `kb.mcp.core.kb_compile_scan` (out of plan scope). Mitigation: revert-verify will catch any ordering bug.
- **R4 (LOW):** Repeating `_missing_abs_path` across 3 tools (compile_scan / lint / evolve) — 9 calls. As `@staticmethod` on `TestMcpWikiDirValidation` it's fine; class scope keeps it private.

No HIGH/CRITICAL risks. Plan is mechanical fold + doc-sync. Total LOC change estimate: ≤200 added / ≤230 deleted. Net diff ≤30 LoC src/ (zero — test-only), well below the Step 9.5 simplify-pass skip threshold.

## Step 9.5 simplify-pass decision

**SKIP.** Per skill rule: "Skip when: total `src/` diff < 50 LoC. Pure dep-bump cycle (no new logic, just version pins...). Signature-preserving rename / move only (no behaviour change to simplify)." This cycle is test-only (`src/` diff = 0 LoC) AND each fold is a signature-preserving move. Rationale recorded in Step 16 self-review.
