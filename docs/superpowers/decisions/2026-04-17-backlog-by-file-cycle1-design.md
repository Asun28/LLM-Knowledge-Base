# Design Decisions — Backlog-by-File Cycle 1

**Date:** 2026-04-17
**Spec:** `docs/superpowers/specs/2026-04-17-backlog-by-file-cycle1-design.md`

## Decisions

### Q1: Batch size — 40 items OR split into 2 PRs?

**OPTIONS:** (A) Single 40-item PR, per-file commits. (B) Split into PR-A (28 safe) + PR-B (8 coordinated).

**ARGUE:** Design reviewer recommended (B) citing reviewability cliff. User instruction is explicit: "fix as possible as one time" + "group by file, multi-severity together." User preference ranks above design reviewer per feature-dev Step 5 priority table.

**DECIDE:** (A) Single PR, per-file commits. Reviewer reads one file at a time; blast radius per commit is one file.

**RATIONALE:** User's explicit scope directive + established per-file commit pattern + prior cycles of 22 items succeeded. CONFIDENCE: HIGH.

### Q2: Which 3 items to defer from the batch?

**OPTIONS:** Defer (a) D2b purpose.md sentinel, (b) B5-extra summary counts semantics, (c) L hybrid.py try/except.

**ARGUE:** D2b introduces new `<kb_focus>` contract — feature, not fix. B5-extra changes observable output semantics. L wraps hot-path search errors — needs failure-injection tests, deserves its own PR.

**DECIDE:** Defer all three. Keep D2a (purpose.md size cap only, no sentinel).

**RATIONALE:** Preserves "mechanical only" batch discipline. Items stay in BACKLOG.md for a future cycle. CONFIDENCE: HIGH.

### Q3: C1 raw_dir + B1 augment threading — order?

**OPTIONS:** (A) One commit. (B) C1 first, then B1.

**ARGUE:** If C1 lands in a separate PR before B1, augment's ingest_source call still compiles (it just doesn't yet pass raw_dir). If B1 lands before C1, augment passes raw_dir= to an unknown kwarg and fails.

**DECIDE:** Single commit (wave 0) containing both, landed as "fix(wave0): thread raw_dir + data_dir through augment/ingest." Already committed.

**RATIONALE:** Avoid partial-compile window. CONFIDENCE: HIGH.

### Q4: `_TEXT_EXTENSIONS` vs `SUPPORTED_SOURCE_EXTENSIONS` at library boundary?

**OPTIONS:** (A) Use the stricter `_TEXT_EXTENSIONS` (rejects .pdf). (B) Use broader `SUPPORTED_SOURCE_EXTENSIONS` (allows .pdf, lets UTF-8 decode fail helpfully).

**ARGUE:** (A) blocks `compile_wiki` PDF ingest which users expect to work (even though it ultimately raises the "convert first" ValueError). (B) keeps behavior identical to pre-fix for PDFs while still closing the suffix-less-file gap.

**DECIDE:** (B). CONFIDENCE: HIGH.

### Q5: `data_dir` derivation — explicit kwarg OR derive from wiki_dir?

**OPTIONS:** (A) Caller passes explicit `data_dir=...`. (B) Derive `data_dir = wiki_dir.parent / ".data"` when wiki_dir is non-default.

**ARGUE:** (A) needs callers to thread through yet another parameter. (B) matches the three-round review's suggested fix — "derive a default data directory from wiki_dir.parent / .data when a custom wiki is supplied; preserve repo-global defaults for standard runs."

**DECIDE:** Both — explicit `data_dir` kwarg takes precedence; derive from `wiki_dir.parent / ".data"` when user supplied custom wiki but not explicit data_dir; fall through to `None` (module default) for standard runs.

**RATIONALE:** Honors three-round review's explicit guidance + preserves clean extension point. CONFIDENCE: HIGH.

## Conditions

- Wave 0 (B+C) landed. Remaining 30 items in wave 1 (per-file commits).
- Codex plan + plan gate + implementation must run before merge.
- Regression test file `tests/test_backlog_by_file_cycle1.py` lands with implementation, not after.
- Step 11 security verification uses threat-model checklist against final diff.

## FINAL DECIDED PLAN

Execute per spec doc, 38 items total (40 minus 3 deferred), one PR with per-file commits. Wave 0 shipped. Remaining items proceed via Codex-led implementation waves.
