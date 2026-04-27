# Cycle 44 Brainstorm

Brief inline brainstorm for refactor-class work where alternatives are well-bounded. Per dev_ds Step 3.

## M1 — `lint/checks.py` split

- **A.** Per-rule files (`frontmatter.py`, `dead_links.py`, `orphan.py`, `cycles.py`, `staleness.py`, `duplicate_slug.py`, `consistency.py`, `inline_callouts.py`) + `__init__.py` registry. Matches BACKLOG suggested fix.
- B. `lint/rules/` matching `lint/runner.py` dispatch contract — same shape but different name; rejected because BACKLOG explicitly says `lint/checks/`.
- C. Single `rule_registry.py` retaining flat structure — rejected; doesn't address the 1046-LOC issue.

**Choice: A.** Re-export shim (`__init__.py`) preserves `from kb.lint.checks import X` for cycle-23 L5.

## M2 — `lint/augment.py` package

- **A.** Package with `collector.py` / `proposer.py` / `fetcher.py` / `persister.py` / `quality.py` + absorb `_augment_manifest.py` and `_augment_rate.py` as `manifest.py` / `rate.py`. Per BACKLOG fix.
- B. Inline `_augment_manifest.py` + `_augment_rate.py` only into `augment.py` — rejected; doesn't address 1186 LOC.
- C. **(refinement of A)** A + lazy-load JSON state in `manifest.py` and `rate.py` per cycle-19 L2.

**Choice: C.** Augment package historically exhibits reload-leak risk (cycle-19 L2 originally about `kb.capture._PROMPT_TEMPLATE`); applying lazy accessors in the new package files prevents future reload contamination.

## M3 — `mcp/core.py` split

- **A.** Split out `ingest.py` + `compile.py` per BACKLOG, continuing cycle-4-13 split pattern (browse / health / quality already done).
- B. One file per `@mcp.tool()` — over-engineered (29 files for 29 tools).
- C. Split write-path vs read-path — clusters still large; unclear win.

**Choice: A.** Lazy-registration via `__init__.py` `__getattr__` (cycle-23 L5) for tool registration on first attribute access.

## M4 — atomic_text_write consolidation

- **A.** Add `exclusive: bool = False` kwarg; keyword-only; `exclusive=True` uses `O_EXCL`, default uses tempfile+rename. Per BACKLOG fix.
- B. Extract a shared lower-level primitive — risk per cycle-15 L1 (helper extraction can reverse operation order).
- C. Factory function — over-engineered.

**Choice: A.** Minimal explicit kwarg. Both contract halves preserved per cycle-15 L1.

## AC10 fold (test_cycle12_sanitize_context → test_mcp_core)

- **A.** Copy test class verbatim into `test_mcp_core.py`, delete `test_cycle12_sanitize_context.py`. Run cycle-17 L3 dedup check (any tests that already exist in `test_mcp_core` are dropped, with DESIGN-AMEND if scope changes).
- B. Per-test redundancy evaluation first, then fold individuals — slower but cleaner. Apply if cycle-43 cycle12_ingest_coerce-style 7-out-of-11 redundancy is detected.

**Choice: A first, fall back to B if cycle-17 L3 redundancy is high.** Per cycle-43 progress note, AC10 is a clean fold (sanitize_context is unique).

## Vacuous-test upgrades (AC28-AC30)

- **AC28** (case-sensitivity docstring): DELETE — `test_page_id_*` in `test_utils.py` already covers behavior.
- **AC29** (mtime docstring): REPLACE with behavioral mtime-collision test.
- **AC30** (file_lock PID + atomic_*_write OneDrive): SPLIT — DELETE atomic_*_write portion (redundant vs `test_sweep_orphan_tmp_*`); REPLACE PID portion with behavioral stale-lock-reaping test.

Per cycle-16 L2 self-check: each new behavioral test must FAIL when the production helper is reverted to a no-op. Validated at Step 9.

## Implementation order (low-risk → high-risk)

1. AC28-30 (vacuous-test upgrades, isolated, low-risk)
2. AC10 fold (test move, isolated)
3. M4 (atomic_text_write, smallest src change)
4. M1 (checks.py split — medium risk, well-bounded)
5. M2 (augment package — medium risk, lazy-load required)
6. M3 (mcp/core.py split — highest risk per cycle-23 L5)

Validates infrastructure (M4, M1) before the riskiest split (M3). Test-only work first to keep early commits low-risk.

## Open questions for Step 5 design gate

1. Does `lint/checks.py` re-export need to also preserve `kb.lint.checks.WIKI_DIR` and `kb.lint.checks.RAW_DIR` constants for `tests/test_cli.py` patches? **Tentative: yes (AC8 names this).**
2. For M3, where does `_sanitize_conversation_context` live? Stays in `core.py` (used by query path) per AC19. **Confirmed.**
3. How to handle the `fix_dead_links` write path — under `dead_links.py` or `fixers.py`? Suggested: `dead_links.py` (single-file owner of dead-link concerns).
4. Should `manifest.py` and `rate.py` merge JSON state files at the package boundary? No — keep separate per BACKLOG entry. Lazy-load each independently.
5. The `lint/augment.py` private prefix (`_augment_manifest`, `_augment_rate`) is removed in the package conversion. Are there callers using `from kb.lint._augment_manifest import X`? Plan-gate must grep.
6. `mcp/core.py` cap at <=300 LOC after split (AC19): is this realistic given cross-cutting helpers? Plan must size before committing to the cap; if 350 LOC is required, document the deviation.
7. Tool decorator ordering — must the new `mcp/ingest.py` and `mcp/compile.py` be imported BEFORE `kb_query` registers? Verify via `len(mcp._tools) == 29` post-split.
8. C42-L3 patch-target migration — the requirements doc cites `tests/test_cycle13_frontmatter_migration.py` and `tests/test_cycle17_resume.py`. Plan must run THREE greps (string-form, reference-form, broader) per cycle-19 L1.
9. Does test_capture.py's collapse from dual-site to single-site monkeypatch need any test re-ordering? Plan should grep for autouse fixtures interacting with `kb.capture.atomic_text_write`.
10. Vacuous-test upgrade self-checks (AC28-30): each new behavioral test should be paired with a "mutate production to no-op" verification step in Step 9.
