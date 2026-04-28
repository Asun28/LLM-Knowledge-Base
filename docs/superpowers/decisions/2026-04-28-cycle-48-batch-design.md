# Cycle 48 — Design Decision Gate

**Date:** 2026-04-28
**Owner:** Opus main (per cycle-21 L1 + cycle-37 L5 — primary-session decision gate for ≤20-AC hygiene cycle)
**R1 input:** DeepSeek V4 Pro design eval at `/tmp/c48-design-out.txt` (17 KB, 110 lines, ~5 min runtime)
**R2 input:** SKIP (single-round eval matches cycle-47 cadence; no architectural change in scope)

## VERDICT

**APPROVE** with 4 conditions promoted from R1 DeepSeek + 1 self-derived from C41-L1.

## R1 DeepSeek summary

`APPROVE-WITH-CONDITIONS`. Per-AC: A1-A20 all PASS. Conditions raised:
1. Verify `save_page_frontmatter` docstring states body-verbatim contract before AC2 lands.
2. Verify docstring mentions `atomic_text_write` delegation before AC3 lands.
3. AC14 (BACKLOG line 93-95 removal) as separate commit AFTER AC1-AC3 verified.
4. AC1 monkeypatch coverage — both `kb.mcp.core` AND `kb.mcp.ingest` globals must be patched (additive, not replacement).

## CONDITIONS (Step 9 must satisfy)

**C1.** Before AC2 commit lands, audit `src/kb/utils/pages.py:240-252` `save_page_frontmatter` docstring. **Already verified:** docstring already mentions `atomic_text_write` (line 245-246: "Delegates to ``atomic_text_write`` for crash-safe temp+rename"). C2 satisfied. For C1 (body verbatim): add a one-line docstring augment "Body content is written verbatim from `post.content` (no normalization)" if absent — required per C41-L1 (test pins behavior; docstring must align with intent).

**C2.** AC1 monkeypatch is ADDITIVE — keep existing `kb.mcp.core.{PROJECT_ROOT,RAW_DIR,SOURCE_TYPE_DIRS}` patches (today's `_refresh_legacy_bindings()` reads from `core` to seed `ingest`; both must point to tmp_path during the test). Add `kb.mcp.ingest.{...}` patches AFTER each existing core patch (4 methods × 1-2 lines each).

**C3.** AC14 (BACKLOG line 93-95 removal) lands in a separate commit AFTER AC1-AC3 commits, AFTER full pytest passes. Ordering: commit AC1+AC2+AC3 (one commit each or one combined); run `pytest`; only then commit AC14 (BACKLOG cleanup) + AC15 (HIGH #4 progress note).

**C4.** Folds AC4+AC5 must preserve test count at 3025 — verify via `pytest --collect-only | tail -1` after each fold. File count target 239 verified via `ls tests/test_*.py | wc -l`.

**C5.** Per cycle-23 L5 self-healing: today's `kb.mcp.core` patch self-heals via `_refresh_legacy_bindings()` running at next ingest call. AC1 forward-protection adds explicit `kb.mcp.ingest` patches so a future test that reads `kb.mcp.ingest.PROJECT_ROOT` directly without first invoking an ingest tool sees tmp_path, not stale core values. Document this rationale in commit message.

## SCOPE-OUT (not this cycle)

- Cycle-23 L5 root-cause fix (autouse fixture forcing `_refresh_legacy_bindings()` at teardown) — out of scope; per-test-method patching is simpler and sufficient.
- Re-asserting frontmatter.dumps key order in TestSaveFrontmatterBodyVerbatim — already covered by separate `TestSaveFrontmatterMetadataKeyOrder` (out of cycle-48 scope).

## FINAL DECIDED DESIGN

Implement AC1-AC20 as documented in requirements.md. Commit cadence (per C3 + cycle-47 file-grouped pattern):
- Commit 1: AC1 (test_mcp_core.py forward-protection patches)
- Commit 2: AC2 + AC3 (test_models.py exact body equality + atomic spy) + C1 docstring augment to src/kb/utils/pages.py
- Commit 3: AC4 + AC5 (folds — `git mv` semantics impossible without source-content move; manual fold + delete)
- Commit 4: AC8-AC13 (BACKLOG dep-CVE timestamp refresh + resolver-conflicts refresh)
- Commit 5: AC14-AC16 (BACKLOG cleanup of resolved cycle-48+ candidates + HIGH #4 progress + cycle-49+ tag bump on N/A items)
- Commit 6: AC17-AC20 (doc sync: CHANGELOG / CHANGELOG-history / CLAUDE.md / README / docs/reference)
