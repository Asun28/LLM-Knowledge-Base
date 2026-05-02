# Cycle 58 — Brainstorming

## Approaches

### A — Per-fold commit (matches cycles 50/51/52/55/56/57 cadence) **PREFERRED**

Each AC = one mechanical commit:
1. Read source file (110-220 LoC each)
2. Copy classes/functions into receiver under a clearly-labeled section header `# ── <feature> (cycle 58 fold) ─`
3. Apply helper-name rename per C52-L4 (P4: `_write_page` → `_write_status_mature_page`; P5: `_make_items` → `_make_two_pass_items`)
4. Apply class-wrap for P2 (`TestSanitizePathRedaction`) to disambiguate from existing `test_sanitize_*` (yaml_sanitize) tests in receiver
5. Delete source file
6. Run `ruff format` + `ruff check` (in that order per `feedback_ruff_edit_ordering`)
7. Run isolated pytest on receiver (`pytest tests/test_<receiver>.py -q`)
8. Revert-verify per C40-L3 (`assert False` proof on a moved method shows pytest -x FAIL on the receiver)
9. Commit with descriptive message: `test(cycle 58): fold test_<source> into <receiver> (N/5)`

**Pros:** Easy bisect on regression; matches established cadence reviewers expect; clean review trail (5 fold commits + 1 doc-sync commit + 1 self-review commit).
**Cons:** 5x commit ceremony; minor overhead vs batch.

### B — Single batched commit

Land all 5 folds in one commit message. Faster to write but harder to bisect — `git revert` only works at file granularity.

**Pros:** ~5 min faster end-to-end.
**Cons:** Loses bisect granularity. Reviewers cannot see "fold 3 broke" vs "fold 3+4 interaction broke." Conflicts with cycle-50+ established cadence.

### C — Sub-file fold (test-method-level)

Move only specific test methods rather than whole files; leave source file with reduced surface.

**Pros:** Even tighter granularity per pick.
**Cons:** Breaks the freeze-and-fold contract from BACKLOG HIGH ("freeze-and-fold rule — once a version ships, fold its tests INTO the canonical module file"). Source must disappear to reduce file-count.

## Decision (carried into Step 5)

**Approach A.** Established precedent + bisect-able regression handling + alignment with cycle-50+ cadence. The overhead of 5 commits vs 1 is not material against the gains.

## Open questions for Step 5

1. **Q1** — `wiki_log` belongs in `kb.utils.wiki_log`; receiver candidates were `test_utils.py` (already has `append_wiki_log` tests at line 78+) vs `test_ingest.py` (wiki_log is consumed by ingest pipeline). Decision pre-anchored to `test_utils.py` based on grep evidence — the 5 incoming `test_rotate_*` tests test the rotation contract on the same module the receiver already exercises. Confirm at Step 5.

2. **Q2** — `test_cycle18_sanitize.py` tests `kb.utils.sanitize.sanitize_text` (path-redaction) while `test_utils_text.py` already tests `kb.utils.text.yaml_sanitize` (different production module, same test-name prefix `test_sanitize_*`). Class-wrap (`TestSanitizePathRedaction`) vs bare-function-with-prefix-rename (`test_path_redaction_*`). Pre-anchored to class-wrap per cycle-50 cross-feature-hosting analogue.

3. **Q3** — Helper rename for P5 (`_make_items` → `_make_two_pass_items`): cycle-prefix variant (`_make_cycle17_items`) vs feature-prefix variant (`_make_two_pass_items`). Per C52-L4 the goal is uniqueness; feature-prefix is more semantically descriptive and survives future cycle renames. Pre-anchored to feature-prefix.

4. **Q4** — P5 has 220 LoC source — at the upper end of the C13-L2 sizing heuristic (≤30 lines per task code change + ≤100 lines test code). The fold itself is 100% test code (no production change), so the heuristic's 220-LoC concern doesn't apply (no novel APIs to look up — Step 6 SKIPPED). Confirm primary-session per C37-L5.

5. **Q5** — Should AC2's class-wrap break receiver host-shape (test_utils_text.py is currently bare-function-only)? Trade-off: host-shape preservation (C40-L5) vs namespace-clarity (avoid 16 individual prefix renames AND avoid name collision with existing yaml_sanitize tests). Class-wrap matches the cycle-50 precedent (`TestMcpWikiDirValidation` was a NEW class added to test_mcp_core.py because it bridged cross-module hosting concerns). Pre-anchored to class-wrap.
