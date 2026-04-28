# Cycle 48 — Batch Requirements

**Date:** 2026-04-28
**Branch:** `cycle-48-batch` (worktree `D:/Projects/llm-wiki-flywheel-c48`)
**Author:** Opus main session (primary-session per cycle-37 L5)
**Scope:** Hygiene + cycle-48+ targeted upgrades (cadence inherited from cycle 47)

## Problem

Two cycle-48+ upgrade-candidates were filed by cycle-47 R2 Codex review (BACKLOG.md HIGH §lines 93-95) with concrete fix-shapes:
1. `tests/test_mcp_core.py::TestKbCreatePageHintErrors` — patches `kb.mcp.core.{PROJECT_ROOT,RAW_DIR,SOURCE_TYPE_DIRS}` only, but cycle-45 split moved ingest tools to `kb.mcp.ingest` whose `_refresh_legacy_bindings()` mirrors core globals. Self-healing today (next ingest call refreshes), but latent fragility per C42-L3.
2. `tests/test_models.py::TestSaveFrontmatterBodyVerbatim` + `TestSaveFrontmatterAtomicWrite` — substring-only assertions inherited from `test_cycle14_save_frontmatter.py` would pass under production reverts (signature-only smell per cycle-15 L2).

In addition, cycle-46/47 hygiene cadence (dep-CVE re-confirms × 4, Dependabot drift × 2, BACKLOG cleanup, freeze-and-fold continuation) needs to roll forward to cycle 48.

## Non-goals

- Phase 5 work (deferred to dedicated cycle).
- Large refactors (`config.py` god-module split, `compile/compiler.py` rename, `IndexWriter` consolidation) — all open in BACKLOG MEDIUM with size-too-big justification.
- Windows CI matrix re-enable (cycle-48+ tagged but needs self-hosted runner).
- POSIX `_write_item_files` investigation (needs POSIX shell access).
- Brand-new feature work; brand-new dependency bumps beyond CVE patch.

## Acceptance Criteria

### Group A — Test-quality upgrades (cycle-48+ candidates from cycle-47 R2)
- **AC1.** `tests/test_mcp_core.py::TestKbCreatePageHintErrors` adds `monkeypatch.setattr(_ingest_mod, "PROJECT_ROOT"/"RAW_DIR"/"SOURCE_TYPE_DIRS", ...)` for the 4 methods that exercise `_core_mod.kb_ingest` / `_core_mod.kb_ingest_content` (which delegate to `kb.mcp.ingest`). The 2 `kb_save_source` methods are unaffected (uses `tmp_project` fixture which is sandbox-safe). Verified by full suite passing AND by removing the new `_ingest_mod` patches → tests still pass under current ordering (proves cycle-23 L5 self-healing works in main, then re-add for forward-protection).
- **AC2.** `tests/test_models.py::TestSaveFrontmatterBodyVerbatim::test_body_content_with_trailing_newline` asserts exact byte equality of the body region (`text.split("---", 2)[2]` equals expected body), not just substring presence. Revert-verify: if `save_page_frontmatter` is replaced with a stub that strips trailing blank lines, the test FAILS.
- **AC3.** `tests/test_models.py::TestSaveFrontmatterAtomicWrite::test_no_tmp_sibling_left_after_success` adds a spy on `kb.utils.io.atomic_text_write` and asserts `spy.call_count == 1`. Revert-verify: if `save_page_frontmatter` is reverted to a direct `open(target, "w").write(...)`, the test FAILS.

### Group B — Freeze-and-fold continuation (HIGH item progress)
- **AC4.** `tests/test_cycle9_evolve.py` (20 LOC, 1 test) folded into `tests/test_evolve.py` as a top-level test function with cycle-9 source citation comment. Source file deleted in same commit.
- **AC5.** `tests/test_cycle9_compiler.py` (28 LOC, 1 test) folded into `tests/test_compile.py` as a top-level test function with cycle-9 source citation comment. Source file deleted in same commit.
- **AC6.** Test count preserved: `pytest --collect-only | tail -1` shows `3025 tests collected` (unchanged — folds preserve every test).
- **AC7.** File count: `ls tests/*.py | wc -l` shows `239` (was 241 at cycle-47 end; -2 from folds).

### Group C — Dep-CVE re-confirmation (mechanical)
- **AC8.** `BACKLOG.md` diskcache entry (line 130) timestamp refreshed cycle-47 → cycle-48 with re-verification: `pip-audit` empty `fix_versions`, `pip index versions diskcache` confirms 5.6.3 = LATEST.
- **AC9.** `BACKLOG.md` ragas entry (line 133) timestamp refreshed cycle-47 → cycle-48 with same verification.
- **AC10.** `BACKLOG.md` litellm entry (line 136) timestamp refreshed cycle-47 → cycle-48 with `pip download litellm==1.83.14 --no-deps` METADATA verification (`Requires-Dist: click==8.1.8` still present).
- **AC11.** `BACKLOG.md` pip entry (line 139) timestamp refreshed cycle-47 → cycle-48 with `gh api advisories/GHSA-58qw-9mgm-455v` `first_patched_version: null` re-verification.
- **AC12.** `BACKLOG.md` 2 Dependabot drift entries (lines 174, 176) timestamps refreshed cycle-47 → cycle-48.
- **AC13.** `BACKLOG.md` resolver-conflicts entry (line 162) timestamp refreshed cycle-47 → cycle-48.

### Group D — BACKLOG hygiene + remove resolved upgrade-candidates
- **AC14.** Remove the 2 cycle-48+ upgrade-candidate entries from BACKLOG.md (lines 93-95) once AC1-AC3 land — they're resolved-this-cycle.
- **AC15.** Update HIGH #4 freeze-and-fold cycle-44/47 progress note to include cycle-48 (2 more folds; file count 241 → 239).
- **AC16.** Bump cycle-48+ tag → cycle-49+ on remaining N/A prerequisite-missing entries (Windows CI matrix, GHA-Windows mp investigation, POSIX off-by-one) so re-confirmation cadence rolls.

### Group E — Doc sync
- **AC17.** `CHANGELOG.md` `[Unreleased]` Quick Reference: cycle-48 entry with Items / Tests / Scope / Detail.
- **AC18.** `CHANGELOG-history.md`: full cycle-48 bullet detail.
- **AC19.** `CLAUDE.md` Quick Reference: file count 241 → 239 (test count unchanged at 3025).
- **AC20.** `README.md` + `docs/reference/testing.md` + `docs/reference/implementation-status.md` count narrative sites synced (per C26-L2 + C39-L3).

## Blast radius

- `tests/test_mcp_core.py` (AC1, +4 monkeypatch lines × 4 methods)
- `tests/test_models.py` (AC2-AC3, body-equality + spy assertions)
- `tests/test_evolve.py` (AC4 fold in)
- `tests/test_compile.py` (AC5 fold in)
- `tests/test_cycle9_evolve.py` DELETED
- `tests/test_cycle9_compiler.py` DELETED
- `BACKLOG.md` (AC8-AC16)
- `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md`, `README.md`, `docs/reference/{testing,implementation-status}.md` (AC17-AC20)

Zero `src/kb/` changes. Zero new dependencies. Zero new tests added (folds preserve, upgrades modify in-place).

## Constraints

- Branch discipline (cycle-42 L4): every commit on `cycle-48-batch`, verified with `git branch --show-current`.
- Worktree at `D:/Projects/llm-wiki-flywheel-c48`; editable install repointed there.
- CVE baseline artifacts at `.data/cycle-48/` (project-relative per C40-L4).
- C40-L3 + C41-L1: AC2/AC3 upgrades MUST verify production behavior matches docstring/intent before pinning new contract.
