# Cycle 10 Brainstorm — Cycle Shape

**Date:** 2026-04-18
**Context:** 28 ACs across 13 files, mostly applying established cycle-9 /
cycle-7 helpers. Per `feedback_auto_approve` + `feedback_batch_by_file`
memories, the cycle runs autonomously with file-grouped commits.

## Options

### Option A — Per-file commits, tests paired with source (≈13 commits)

Each commit modifies one source file plus its matching test file. Example:
- Commit 1: `mcp/quality.py` + `tests/test_cycle10_quality.py`
- Commit 2: `mcp/browse.py` (kb_read_page ambiguity) + test
- Commit 3: `mcp/browse.py` (kb_stats validator) + `mcp/health.py` (3 tools) +
  `tests/test_cycle10_validate_wiki_dir.py`

**Pros:** Exact match to `feedback_batch_by_file`. Per-file rollback safe.
Maps cleanly to BACKLOG line items.
**Cons:** ~13 commits; PR reviewers wade through more history. The
`validate_wiki_dir` theme naturally spans two source files — pure per-file
would split it artificially.

### Option B — Per-theme commits (≈5 commits)

Group fully by theme, regardless of file count:
- Commit 1: wiki_dir migration (browse + health, 4 tools)
- Commit 2: silent-degradation (quality)
- Commit 3: vector-min-sim (config + hybrid)
- Commit 4: capture hardening (capture)
- Commit 5: ingest validation (pipeline)
- + doc commit (CLAUDE.md + CHANGELOG/BACKLOG)

**Pros:** Fewest commits; easiest PR story.
**Cons:** A single commit can touch 3+ files, which violates the
file-grouped-commit discipline cycle 4 plan-gate REJECTed (Red Flag:
"Multi-file tasks break AC6 file-grouped-commit discipline").

### Option C — Per-AC commits (28 commits)

One commit per AC. Pure TDD-red → TDD-green granularity.

**Pros:** Absolute atomic rollback; each AC is independently revertable.
**Cons:** 28 commits in a 2-hour session would cost disproportionate CI runs
(cycle 9 had 18 commits and 2,003 tests — ~15 min each). Signal-to-noise
drops.

## Recommendation — Option A with theme-collapse exception

Run per-file commits, but allow ONE commit to span two files when the theme
is a single helper applied identically (e.g., `_validate_wiki_dir` used across
`browse.py` kb_stats and `health.py` kb_graph_viz / kb_verdict_trends /
kb_detect_drift — one commit titled "migrate 4 MCP tools to
_validate_wiki_dir"). This respects the cycle-4 plan-gate Red Flag (multi-file
commits must be flagged as "cluster" with rationale) by documenting the
cluster explicitly in the commit message.

Commit shape (8 commits for code + 1 commit for docs):

1. `fix(cycle10): kb_refine_page backlinks via _safe_call` — quality.py + test
2. `fix(cycle10): kb_read_page ambiguous-match error` — browse.py + test
3. `fix(cycle10): migrate 4 MCP tools to _validate_wiki_dir helper`
   (cluster: kb_stats, kb_graph_viz, kb_verdict_trends, kb_detect_drift —
   single helper, identical pattern) — browse.py + health.py + test
4. `feat(cycle10): VECTOR_MIN_SIMILARITY cosine floor in hybrid_search`
   — config.py + hybrid.py + test
5. `docs(cycle10): detect_source_drift deletion-pruning behaviour`
   — compiler.py docstring
6. `fix(cycle10): capture.py UUID prompt boundary + submission captured_at`
   (cluster: both touch `_extract_items_via_llm`, ship together) —
   capture.py + test
7. `fix(cycle10): ingest extraction-field type validation`
   — pipeline.py + test
8. `docs(cycle10): raw/captures/ architectural exception`
   — CLAUDE.md

Doc commit (AC28) lands in Step 12 as a separate commit:
9. `docs(cycle10): CHANGELOG + BACKLOG for cycle 10`

## File ordering

Run lowest-risk first so CI stays green longer:

1. `detect_source_drift` docstring (AC9) — zero code change, safest
2. `_validate_wiki_dir` migration (AC3-AC6, AC18-AC21) — cycle-9 pattern
   replay, security-harden
3. `kb_refine_page` `_safe_call` (AC1, AC15) — cycle-7 pattern replay
4. `kb_read_page` ambiguity (AC2, AC16) — new logic, small surface
5. `VECTOR_MIN_SIMILARITY` + `hybrid_search` (AC7-AC8, AC22-AC23) — new
   filter, test-covered
6. `capture.py` UUID boundary + `captured_at` (AC10-AC11, AC24-AC25) —
   prompt change, highest risk
7. `ingest/pipeline.py` `_coerce_str_field` (AC12-AC13, AC26-AC27) — touches
   hot path; ship with full test coverage
8. `CLAUDE.md` (AC14) — doc-only
9. Step 12 docs (AC28) — last

## Spec self-review (per brainstorming skill)

- No TBDs / TODOs in requirements doc.
- Internal consistency: AC numbering is continuous 1-28; file mapping is
  1:1 with section headings.
- Scope: 28 ACs in 8 code commits + 1 doc commit is within a single cycle
  (cycle 8 had 11 commits, cycle 9 had 18).
- Ambiguity: AC1 "response string appends `[warn] {err}`" — format is
  explicit and testable.

Proceeding to Step 4 design eval.
