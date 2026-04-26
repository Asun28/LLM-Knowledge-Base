# Cycle 35 — Brainstorm: 3 candidate approaches

Skill: `superpowers:brainstorming` (autonomous mode — no human gate per `feedback_auto_approve`).

## Context

18 ACs across 4 file groups (utils/sanitize.py, ingest/pipeline.py, mcp/core.py, docs/architecture/). All ACs are tactical fixes against existing code; no new modules, no public-API changes, no deferred-import refactors. Test anchors already exist for AC1-2 (cycle-33 xfail-strict marker).

Open questions the brainstorm narrows:

1. **Commit granularity** — per-file group (4 commits) vs per-AC (~18 commits) vs split-by-concern (lock fixes / semantic fixes / doc fixes).
2. **Test file naming** — single `test_cycle35_batch.py` vs per-file-group (`test_cycle35_sanitize.py`, `test_cycle35_pipeline_index_writers.py`, `test_cycle35_mcp_core_filename_validator.py`) vs co-located with existing test files (extend `test_cycle33_*` etc.).
3. **Lock-fix scope** — function-local `with file_lock(...)` per cycle-19 discipline (small) vs introduce the BACKLOG-mentioned `IndexWriter` helper that wraps all four index files (`_sources.md`, `index.md`, `_categories.md`, `log.md`) (medium) vs full coarse wiki-wide ingest mutex (large, out of scope).
4. **T1b (slash UNC long-path) inclusion** — defer to BACKLOG (smallest diff) vs include if Step-11 REPL probe surfaces a leak (medium) vs proactively close (largest diff, may touch the same regex twice).
5. **Step 11b GitPython bump** — bundle into the cycle's PR (single doc-update pass per cycle-7 ordering) vs separate PR (cleaner audit trail, doubles CI time).

## Approach A — "Per-file commit, function-local lock, T1b deferred"

**Shape.** 4 implementation commits (one per file group) + 1 Step-11b dep-bump commit (`fix(deps): patch GitPython 3.1.46 → 3.1.47`) + 1 doc-update commit + 1 self-review commit. Total ~7 commits on the branch.

**Lock fix.** Function-local `with file_lock(sources_file): content = ...; atomic_text_write(...)` and same for `_update_index_batch`. No new helper. Existing cycle-19 patterns followed verbatim.

**Tests.** Per-file-group test files: `test_cycle35_sanitize_unc_slash.py` (extends cycle-33 with the new positive test + xfail marker removal happens in `test_cycle33_*`), `test_cycle35_pipeline_index_writers.py`, `test_cycle35_mcp_core_filename_validator.py`.

**T1b.** Deferred to BACKLOG entry (one-liner, picked up next time someone touches sanitize.py).

**Tradeoffs.**
- (+) Smallest diff per file group → easiest R1 review.
- (+) Matches cycle 33-34 commit shape — reviewers know what to expect.
- (+) Preserves the `IndexWriter` BACKLOG entry for a dedicated cycle that can also tackle `_categories.md` + `log.md` (out-of-scope for cycle 35).
- (-) Two RMW-locking commits in two functions duplicate the `with file_lock` pattern (potential for divergence if one is updated later).

## Approach B — "Per-AC commit, IndexWriter helper, T1b in-scope"

**Shape.** 18 implementation commits + dep-bump + doc-update + self-review. Total ~21 commits.

**Lock fix.** Introduce `IndexWriter` helper class wrapping the four index files with documented locking order. Refactor `_update_sources_mapping` and `_update_index_batch` to be methods on it. Closes BACKLOG M11 entirely.

**Tests.** Per-AC test files (one per AC) + an `IndexWriter`-level integration test.

**T1b.** Proactively closed — same regex extension covers both ordinary-UNC slash form AND `//?/UNC/...` long-path slash form.

**Tradeoffs.**
- (+) Closes the entire `IndexWriter` BACKLOG entry in one cycle.
- (+) Most aggressive scope reduction.
- (-) ~21 commits — exceeds cycle-22 / cycle-24 commit-count baseline (most cycles ship 4-8 commits).
- (-) Per-AC commits violate `feedback_batch_by_file` ("Group backlog fixes by file ... not by severity"). The user's explicit memory.
- (-) IndexWriter introduction is a STRUCTURAL refactor — out of scope per the requirements doc's non-goals.
- (-) T1b proactive close adds untested regex complexity (the existing test suite has no `//?/UNC/...` coverage; we'd be adding code without a forcing function).

## Approach C — "Per-file commit, function-local lock, T1b probed at Step 11"

**Shape.** Same as Approach A for commits — but at Step 11 verification, run the REPL probe `python -c "from kb.utils.sanitize import sanitize_text; print(sanitize_text('//?/UNC/server/share/x.md'))"`. If the output is NOT `<path>`, add T1b coverage in the same Step-14 R1 fix commit (cycle-23 L3 deferred-promise enforcement applied: every threat-model deferred clause needs a BACKLOG entry OR a same-cycle close).

**Tradeoffs.**
- (+) Inherits all of Approach A's pros.
- (+) Step 11 REPL probe is concrete (not "consider" hand-waving).
- (+) Catches the T1b regex hole IF it actually leaks (data-driven inclusion).
- (-) Slightly more Step-11 work than A (~30s for the REPL).
- (-) Mid-cycle scope expansion (T1b add) if probe surfaces a leak — but contained, single regex line.

## Recommendation

**Approach C.** It matches Approach A's commit shape (which the project's reviewers know how to read), keeps `feedback_batch_by_file` discipline, leaves the IndexWriter BACKLOG entry for a dedicated cycle that can tackle all four index files together, and makes T1b inclusion DATA-DRIVEN rather than speculative.

Step 5 design gate decisions to surface:
- Q1: A vs B vs C — confirm C.
- Q2: Per-file test file naming — confirm `test_cycle35_<file_group>.py` shape.
- Q3: Should AC18 PNG re-render commit be SEPARATE from AC16/17 HTML edits, or bundled? (One commit per CLAUDE.md "Architecture Diagram Sync MANDATORY" — prefer bundled.)
- Q4: Step-11b GitPython bump — same PR as the cycle work or separate? (Per cycle-7 ordering: same PR, separate commit; Step 12 doc-update covers both diffs in one Codex pass.)
- Q5: `_update_sources_mapping` empty-list AC6 location — function entry (before docstring? after docstring?) AND log level (debug vs trace). Confirm: AFTER docstring + `logger.debug` (debug, not warning — empty is legitimate per AC6).
- Q6: Same-class peer scan for cycle-19 file-lock discipline — `_write_index_files` itself wraps `_update_sources_mapping` + `_update_index_batch` in its own try/except. Should we lock at the wrapper level (single lock spans both writes) or at each callee? Per cycle-24 L3 (cache-cleanup-must-stay-in-lock) and the existing per-file lock granularity at `_write_wiki_page` / `append_evidence_trail`, lock at the CALLEE level so each index file's read-write is independent.
- Q7: AC11 backtick-dedup test — also test that the FIRST call's escaping behaviour is preserved (single-call invariant) so we don't accidentally over-fix. Yes — include both single-call and double-call assertions.
- Q8: AC18 Playwright re-render — what fallback if Playwright isn't installed in the venv? Per cycle-34 design-doc fallback: defer with BACKLOG entry. But cycle 34 already deferred this once; deferring again would violate the "MANDATORY" rule indefinitely. Alternative: invoke the real Playwright via `python -c "from playwright..."` — install if missing.
