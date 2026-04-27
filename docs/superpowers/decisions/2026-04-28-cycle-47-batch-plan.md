# Cycle 47 — Implementation Plan

**Date:** 2026-04-28
**Branch:** cycle-47-batch
**Worktree:** `D:\Projects\llm-wiki-flywheel-c47`
**Step:** 7 (implementation plan)
**Pre-condition:** Step-5 design APPROVED WITH AMENDMENTS; 12 binding CONDITIONS.

## Plan structure

Five tasks. Each task = ONE commit. Per `feedback_batch_by_file`: group by file.
Per cycle-13 L2: primary-session for ≤30 LOC mechanical changes; this is text-only +
fold-and-delete.

Workflow execution: primary-session for ALL 5 tasks (cycle-37 L5 — hygiene cycle,
≤15 ACs, ≤6 docs, primary holds context from Steps 1-5). NO Codex/DeepSeek
dispatches needed for implementation.

Branch discipline: every commit verifies `git branch --show-current` =
`cycle-47-batch` before `git add` / `git commit` (Condition 11).

---

## TASK 1 — BACKLOG.md consolidated sweep (AC1-AC6 + AC10 frontier + AC11 + AC12 + AC13)

**Files modified:**
- `BACKLOG.md` (single file edit)

**Change (per Conditions 5, 7, 9, 10):**
1. **AC1 (line 126)** — change `cycle-46 re-confirmed 2026-04-28` → `cycle-47 re-confirmed 2026-04-28`. Append `+ cycle-47` to history list (`...cycle-25 AC9 + cycle-32 + cycle-39 + cycle-40 + cycle-41 + cycle-46 + cycle-47 all show same state`).
2. **AC2 (line 129)** — same shape; replace stamp.
3. **AC3 (line 132)** — replace stamp; canonical text re-confirms 1.83.14 wheel METADATA still pins `Requires-Dist: click==8.1.8` (verified Step 2).
4. **AC4 (line 135) — RE-WORDED PER B1** — replace the entire entry with the canonical Step-5 text. Locator changes from `requirements.txt` → `.venv installer`; verb changes from "bump the pin" → "upgrade the installer". History extended with `+ cycle-47 re-confirmed`.
5. **AC5 (line 170)** — replace `cycle-37/38/39/40/41/46 re-confirmed drift persists 2026-04-28` → `cycle-37/38/39/40/41/46/47 re-confirmed drift persists 2026-04-28`. Bump tag `(cycle-47+)` stays (entry remains open per Q3 / SCOPE-OUT 4).
6. **AC6 (line 172)** — same as AC5.
7. **AC10 (line 164) — REPLACE FRONTIER PER M2** — replace `(likely in test_cycle23_workflow_e2e.py or test_cycle23_rebuild_indexes.py)` with the canonical 3-rank ranked frontier list from Step-5 M2 decision. EXPLICIT REMOVAL of the false-positive `test_cycle23_workflow_e2e.py` reference. Append `cycle-47 re-confirmed: investigation deferred — no GHA-Windows reproducer; refined frontier list above.`
8. **AC11** — append cycle-47 progress to the Phase 4.5 HIGH #4 note (line 91): `Cycle 47 folded 3 files (cycle16_config_constants → new test_config.py, cycle11_task6_mcp_ingest_type → test_mcp_core.py, cycle14_save_frontmatter → test_models.py); file count 243 → 241 (net -2). Cumulative ~190+ versioned files still to fold.`
9. **AC12** — refresh `(cycle-47+)` entries (lines 164, 166, 168, 170, 172). Per Step-5 M2 + AC12 spec:
   - 164: cycle-47 frontier text replacement (paired with AC10).
   - 166: append `cycle-47 re-confirmed N/A — prerequisite missing: self-hosted Windows runner.`
   - 168: append `cycle-47 re-confirmed N/A — prerequisite missing: POSIX shell.`
   - 170, 172: paired with AC5/AC6 timestamp refresh.
10. **AC13 SCOPE-EXPANDED PER M3** — line 158 (resolver-conflict entry) timestamp refresh: `Cycle-46 re-confirmed 2026-04-28` → `Cycle-47 re-confirmed 2026-04-28: all three conflicts persist verbatim per pip check output.`

**Pre-edit verification (Condition 9 gate):**
```bash
grep -nE "cycle-46 re-confirmed" BACKLOG.md  # must count 7
```

**Test:** No code change → no test. Behaviour assertion: BACKLOG.md text changes.

**Post-edit verification (Condition 9 gate):**
```bash
grep -nE "cycle-46 re-confirmed" BACKLOG.md  # must count 0
grep -nE "cycle-47 re-confirmed" BACKLOG.md  # must count 7
grep -nE "cycle-47\+" BACKLOG.md            # must count ≥5 (164, 166, 168, 170, 172)
```

**Acceptance criteria:** AC1, AC2, AC3, AC4, AC5, AC6, AC10, AC11, AC12, AC13.
**Threat:** N/A (text-only, no I/O surface change).
**Commit message format:**
```
chore(cycle 47): BACKLOG hygiene — dep-CVE re-verify + cycle-47+ refresh + AC10 frontier
```

---

## TASK 2 — AC7 fold: test_cycle16_config_constants.py → new test_config.py

**Files modified:**
- DELETE `tests/test_cycle16_config_constants.py` (38 LOC, 5 tests).
- CREATE `tests/test_config.py` (new file).

**Change (per Conditions 1, 6):**
1. Read source file verbatim (already done at Step 4).
2. Create `tests/test_config.py` with structure:
   ```python
   """Tests for kb.config constants — values, types, immutability.
   
   Cycle 47 fold receiver: TestConfigConstants from cycle 16
   (test_cycle16_config_constants.py, fold per Phase 4.5 HIGH #4).
   """
   
   import pytest
   from kb import config
   
   
   class TestConfigConstants:
       # ── Cycle 16 AC1-AC3 — config constants for query refinement + lint quality ─
       
       def test_query_rephrasing_max_is_int_three(self) -> None:
           """AC1 — QUERY_REPHRASING_MAX == 3, typed int."""
           assert isinstance(config.QUERY_REPHRASING_MAX, int)
           assert config.QUERY_REPHRASING_MAX == 3
       
       def test_duplicate_slug_distance_threshold_is_int_three(self) -> None:
           """AC2 — DUPLICATE_SLUG_DISTANCE_THRESHOLD == 3, typed int."""
           assert isinstance(config.DUPLICATE_SLUG_DISTANCE_THRESHOLD, int)
           assert config.DUPLICATE_SLUG_DISTANCE_THRESHOLD == 3
       
       def test_callout_markers_is_tuple_of_four_strings(self) -> None:
           """AC3 — CALLOUT_MARKERS is a tuple of the 4 canonical marker names."""
           assert isinstance(config.CALLOUT_MARKERS, tuple)
           assert config.CALLOUT_MARKERS == ("contradiction", "gap", "stale", "key-insight")
       
       def test_callout_markers_tuple_is_immutable(self) -> None:
           """AC3 — CALLOUT_MARKERS uses tuple semantics (no index assignment)."""
           with pytest.raises(TypeError):
               config.CALLOUT_MARKERS[0] = "other"  # type: ignore[index]
       
       def test_callout_markers_entries_are_plain_lowercase(self) -> None:
           """AC3 — each marker is a lowercase ASCII string (safe for regex + render)."""
           for marker in config.CALLOUT_MARKERS:
               assert isinstance(marker, str)
               assert marker == marker.lower()
               assert marker.replace("-", "").isalpha()
   ```
3. DELETE source file in same commit: `git rm tests/test_cycle16_config_constants.py`.

**Pre-fold verification:**
```bash
pytest --collect-only -q | tail -1  # BASELINE record (must be 3025)
```

**Test:** Per Condition 6:
```bash
pytest tests/test_config.py -q                    # 5 passed (isolation)
pytest -q | tail -3                                # full suite green
pytest --collect-only -q | tail -1                # POST-fold count == 3025
```

**Acceptance criteria:** AC7. **Threat:** N/A.
**Commit message:**
```
test(cycle 47 AC7): fold test_cycle16_config_constants.py → new test_config.py
```

---

## TASK 3 — AC8 fold: test_cycle11_task6_mcp_ingest_type.py → test_mcp_core.py

**Files modified:**
- DELETE `tests/test_cycle11_task6_mcp_ingest_type.py` (78 LOC, 6 tests).
- EDIT `tests/test_mcp_core.py` (append new class).

**Change (per Conditions 1, 2, 6):**
1. Append to `tests/test_mcp_core.py` (after existing tests; before file end):
   ```python
   # ── Cycle 11 task 6: kb_create_page hint errors (cycle 47 fold) ─
   
   from kb.mcp import core as core_mod  # already imported above as different alias; verify
   
   
   class TestKbCreatePageHintErrors:
       """Cycle-11 same-class peer rule (C11-L3): kb_ingest, kb_ingest_content,
       and kb_save_source ALL reject 'comparison'/'synthesis' source_type with
       a hint pointing at kb_create_page.
       """
       
       @staticmethod
       def _assert_create_page_error(result: str) -> None:
           assert isinstance(result, str)
           assert "kb_create_page" in result
           assert "fake.md" not in result
           assert "x.md" not in result
           assert " x" not in result
       
       def test_kb_ingest_comparison_names_kb_create_page(self, tmp_path, monkeypatch):
           monkeypatch.setattr(core_mod, "PROJECT_ROOT", tmp_path)
           monkeypatch.setattr(core_mod, "RAW_DIR", tmp_path)
           source = tmp_path / "fake.md"
           source.write_text("raw content", encoding="utf-8")
           result = core_mod.kb_ingest(source_path="fake.md", source_type="comparison")
           self._assert_create_page_error(result)
       
       def test_kb_ingest_synthesis_names_kb_create_page(self, tmp_path, monkeypatch):
           monkeypatch.setattr(core_mod, "PROJECT_ROOT", tmp_path)
           monkeypatch.setattr(core_mod, "RAW_DIR", tmp_path)
           source = tmp_path / "fake.md"
           source.write_text("raw content", encoding="utf-8")
           result = core_mod.kb_ingest(source_path="fake.md", source_type="synthesis")
           self._assert_create_page_error(result)
       
       def test_kb_ingest_content_comparison_names_kb_create_page(self, monkeypatch):
           monkeypatch.setattr(core_mod, "SOURCE_TYPE_DIRS", {"article": object()})
           result = core_mod.kb_ingest_content(
               content="x",
               filename="x.md",
               source_type="comparison",
               extraction_json="{}",
           )
           self._assert_create_page_error(result)
       
       def test_kb_ingest_content_synthesis_names_kb_create_page(self, monkeypatch):
           monkeypatch.setattr(core_mod, "SOURCE_TYPE_DIRS", {"article": object()})
           result = core_mod.kb_ingest_content(
               content="x",
               filename="x.md",
               source_type="synthesis",
               extraction_json="{}",
           )
           self._assert_create_page_error(result)
       
       def test_kb_save_source_comparison_names_kb_create_page(self, tmp_project):
           result = core_mod.kb_save_source(
               content="x",
               filename="x",
               source_type="comparison",
           )
           assert "kb_create_page" in result
           assert "comparison" in result
       
       def test_kb_save_source_synthesis_names_kb_create_page(self, tmp_project):
           result = core_mod.kb_save_source(
               content="x",
               filename="x",
               source_type="synthesis",
           )
           assert "kb_create_page" in result
           assert "synthesis" in result
   ```
2. **NOTE on imports:** `test_mcp_core.py` already imports `kb_save_source`, `kb_ingest_content`, `kb_compile_scan` (top of file). The cycle-11 tests use `core.kb_ingest` (not currently imported in receiver). Add `from kb.mcp import core as core_mod` (alias since `core` may collide with existing `kb.config` import). Also need NOT-import-aliased `core` if not present; verify at edit time.
3. DELETE source file in same commit: `git rm tests/test_cycle11_task6_mcp_ingest_type.py`.

**Test:** Per Condition 6:
```bash
pytest tests/test_mcp_core.py -q                  # ~10 passed (isolation, includes existing)
pytest -q | tail -3                                # full suite green
pytest --collect-only -q | tail -1                # POST-fold count == 3025
```

**Acceptance criteria:** AC8. **Threat:** N/A.
**Commit message:**
```
test(cycle 47 AC8): fold test_cycle11_task6_mcp_ingest_type.py → test_mcp_core.py
```

---

## TASK 4 — AC9 fold: test_cycle14_save_frontmatter.py → test_models.py

**Files modified:**
- DELETE `tests/test_cycle14_save_frontmatter.py` (139 LOC, 9 tests across 5 classes).
- EDIT `tests/test_models.py` (append 5 new classes).

**Change (per Conditions 1, 3, 6):**
1. Append to `tests/test_models.py` (after existing tests; before file end):
   ```python
   # ── Cycle 14 TASK 3 — save_page_frontmatter wrapper (cycle 47 fold) ─
   # Covers AC16/AC17. Threat T4: atomic-write + sort_keys=False contract.
   # Per Step-5 Condition 3: NO test calls load_page_frontmatter; frontmatter.Post
   # construction stays function-local; renamed source TestAtomicWriteProof to
   # TestSaveFrontmatterAtomicWrite.
   
   import frontmatter
   from kb.utils.pages import save_page_frontmatter
   
   
   class TestSaveFrontmatterInsertionOrder:
       """AC17(a) — 4+ non-alphabetical keys round-trip in insertion order."""
       
       def test_six_required_fields_order_preserved(self, tmp_path):
           # ... (verbatim from source) ...
       
       def test_nonalphabetical_insertion_order(self, tmp_path):
           # ... (verbatim from source) ...
   
   
   class TestSaveFrontmatterBodyVerbatim:
       """AC17(b) — body content verbatim including trailing newline."""
       
       def test_body_content_with_trailing_newline(self, tmp_path):
           # ... (verbatim from source) ...
       
       def test_body_preserved_with_special_chars(self, tmp_path):
           # ... (verbatim from source) ...
   
   
   class TestSaveFrontmatterListValuedMetadataOrder:
       """AC17(c) — list-valued metadata order preserved."""
       
       def test_source_list_order(self, tmp_path):
           # ... (verbatim from source) ...
   
   
   class TestSaveFrontmatterExtraKeysPreserved:
       """AC17(d) — custom metadata keys preserved."""
       
       def test_custom_keys_survive_roundtrip(self, tmp_path):
           # ... (verbatim from source) ...
   
   
   class TestSaveFrontmatterAtomicWrite:
       """AC17(e) — writes atomically; no partial .tmp sibling on success.
       
       Renamed from source TestAtomicWriteProof per Step-5 design (cycle 47
       N1 + Condition 3).
       """
       
       def test_no_tmp_sibling_left_after_success(self, tmp_path):
           # ... (verbatim from source) ...
       
       def test_write_overwrites_existing(self, tmp_path):
           # ... (verbatim from source) ...
   ```
2. **NOTE on imports:** Source uses `import frontmatter` AND `from kb.utils.pages import save_page_frontmatter`. Receiver `test_models.py` already imports `from kb.utils import pages`. Add `import frontmatter` and `from kb.utils.pages import save_page_frontmatter` at fold site with `# noqa: E402` if past top-of-file imports, OR add to existing import block. Per cycle-43 L1: minimal disruption — add at fold site with E402.
3. DELETE source file in same commit: `git rm tests/test_cycle14_save_frontmatter.py`.

**Test:** Per Condition 6:
```bash
pytest tests/test_models.py -q                    # 21+ passed (isolation, includes existing)
pytest -q | tail -3                                # full suite green
pytest --collect-only -q | tail -1                # POST-fold count == 3025
```

**Acceptance criteria:** AC9. **Threat:** N/A.
**Commit message:**
```
test(cycle 47 AC9): fold test_cycle14_save_frontmatter.py → test_models.py
```

---

## TASK 5 — AC14-AC18 doc-sync (CHANGELOG + history + CLAUDE + README + reference docs)

**Files modified:**
- `CHANGELOG.md` (cycle-47 Quick Reference under [Unreleased])
- `CHANGELOG-history.md` (cycle-47 detailed entry)
- `CLAUDE.md` (Quick Reference cycle-stamp append)
- `README.md` (verify test count unchanged; no edit needed if 3025)
- `docs/reference/testing.md` (cycle-47 history entry)
- `docs/reference/implementation-status.md` (cycle-47 latest-cycle notes)

**Change (per Conditions 6, 8):**

1. **CHANGELOG.md** — add new compact entry under `## [Unreleased]` `### Quick Reference` (newest first):
   ```markdown
   #### 2026-04-28 — cycle 47 (Backlog hygiene + dep-CVE re-verify + freeze-and-fold continuation)
   - **Items shipped:** 18 ACs (AC1-AC6 dep-CVE re-verify; AC7-AC9 3 folds; AC10 Windows CI frontier refinement; AC11-AC13 BACKLOG hygiene; AC14-AC18 doc sync).
   - **Tests:** 3025 → 3025 (unchanged — folds preserve all 20 tests as classes/parametrize); files 243 → 241 (net -2: -3 folded + 1 new test_config.py).
   - **Scope:** test fold (cycle16_config_constants → new test_config.py, cycle11_task6_mcp_ingest_type → test_mcp_core.py, cycle14_save_frontmatter → test_models.py); 7 BACKLOG re-confirmed stamps refreshed cycle-46 → cycle-47; AC4 re-worded (pip is .venv installer, not requirements.txt pin); AC10 BACKLOG frontier list re-grounded on grep-proven Thread/MP candidates.
   - **Detail:** see CHANGELOG-history.md.
   ```

2. **CHANGELOG-history.md** — add full per-AC bullet detail (newest first), enumerating AC1-AC18.

3. **CLAUDE.md** line 7 (Quick Reference State line) — append cycle-47 to carry-over list:
   - BEFORE: `cycle-39/40/41/42/43/44/45/46 carry-over`
   - AFTER: `cycle-39/40/41/42/43/44/45/46/47 carry-over`
   - Test count `3025` STAYS — verified via `pytest --collect-only -q | tail -1` = 3025.

4. **README.md** — VERIFY tree-block "tests/  # 3025 tests across N files" unchanged. If file count chained to "243 files" anywhere, update to "241 files". Likely no README edit needed since tree-block typically uses test count only. Verify at edit time.

5. **docs/reference/testing.md** line 13 narrative — append cycle-47 entry to the multi-cycle history paragraph:
   - Append after cycle-46 detail: `cycle 47 folded 3 small files (cycle16_config_constants → new test_config.py with TestConfigConstants class; cycle11_task6_mcp_ingest_type → test_mcp_core.py as TestKbCreatePageHintErrors with @staticmethod _assert_create_page_error; cycle14_save_frontmatter → test_models.py as 5 classes including TestSaveFrontmatterAtomicWrite renamed from TestAtomicWriteProof) — file count 243 → 241 (-2 net), test count unchanged at 3025.`

6. **docs/reference/implementation-status.md** — add cycle-47 latest-cycle section.

**Test:** No code change → no test. Doc-text changes only.

**Post-edit verification:**
```bash
pytest --collect-only -q | tail -1                         # MUST be 3025
ls tests/test_*.py | wc -l                                 # MUST be 241
grep -c "243 files\|3019 tests" CLAUDE.md README.md        # WARN if hits (drift detection)
grep -c "cycle-47" CHANGELOG.md CHANGELOG-history.md       # MUST be ≥1 each
```

**Acceptance criteria:** AC14, AC15, AC16, AC17, AC18.
**Threat:** N/A.
**Commit message:**
```
docs(cycle 47): CHANGELOG + CHANGELOG-history + CLAUDE + testing.md + implementation-status.md sync
```

---

## Plan summary

| Task | ACs | Files | LOC delta | Commit |
|---|---|---|---|---|
| 1 | AC1-AC6, AC10, AC11, AC12, AC13 | BACKLOG.md | ~30 lines edited | TASK 1 |
| 2 | AC7 | tests/test_cycle16_config_constants.py (DEL), tests/test_config.py (NEW) | -38 + 38 ≈ 0 | TASK 2 |
| 3 | AC8 | tests/test_cycle11_task6_mcp_ingest_type.py (DEL), tests/test_mcp_core.py (EDIT) | -78 + 78 ≈ 0 | TASK 3 |
| 4 | AC9 | tests/test_cycle14_save_frontmatter.py (DEL), tests/test_models.py (EDIT) | -139 + 139 ≈ 0 | TASK 4 |
| 5 | AC14-AC18 | CHANGELOG.md, CHANGELOG-history.md, CLAUDE.md, README.md, docs/reference/{testing,implementation-status}.md | ~50 lines | TASK 5 |

**Total: 5 commits across 9 distinct files.**

## Pre-flight checks (before TASK 1)

```bash
git -C D:/Projects/llm-wiki-flywheel-c47 branch --show-current  # MUST be cycle-47-batch
git -C D:/Projects/llm-wiki-flywheel-c47 status                  # MUST be clean (only docs/superpowers/decisions/2026-04-28-cycle-47-batch-*.md untracked)
pytest --collect-only -q | tail -1                                # BASELINE 3025
ls tests/test_*.py | wc -l                                        # BASELINE 243
```

## Post-cycle gate (before TASK 5 ships)

```bash
pytest -q | tail -3                                              # full suite green
ruff check src/ tests/                                            # clean
ruff format --check src/ tests/                                  # clean
pytest --collect-only -q | tail -1                                # POST 3025 (must equal baseline)
ls tests/test_*.py | wc -l                                        # POST 241 (= 243 - 2)
grep -nE "cycle-46 re-confirmed" BACKLOG.md                       # MUST count 0
grep -nE "cycle-47 re-confirmed" BACKLOG.md                       # MUST count 7
grep -nE "test_cycle16_config_constants|test_cycle11_task6|test_cycle14_save_frontmatter" tests/  # MUST count 0
```

## Plan→Design fidelity check (PLAN-AMENDS-DESIGN scan)

No PLAN-AMENDS-DESIGN deviations. Plan follows the Step-5 final design exactly:
- Q1 → TASK 2 (new test_config.py).
- Q2 → TASK 4 (no load_page_frontmatter calls; function-local Post construction).
- Q3 → No CI workflow edits in any task.
- Q4 → File-count chain `243 → 241` in TASK 5.
- Q5 → AC13 covers all 7 stamps in TASK 1.
- B1 → TASK 1 step 4 re-words AC4 BACKLOG entry.
- B2 → TASK 5 uses canonical `243 → 241` chain across all surfaces.
- M1 → TASK 3 uses class-local `@staticmethod` helper.
- M2 → TASK 1 step 7 inserts ranked frontier list.
- M3 → TASK 1 step 10 expands AC13 scope to 7 entries.
- All 12 binding CONDITIONS embedded in task verification gates.
- All 10 SCOPE-OUT items NOT touched.
