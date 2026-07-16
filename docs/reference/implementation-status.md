# Implementation Status
<!-- FORMAT GUIDE
Purpose: Current test-suite state + one-row-per-cycle history. Keep this file as a compact index.
- "Current State" table: update once per cycle (tests, files, version).
- "Cycle History" table: add ONE ROW per cycle (newest first). Columns: Cycle | Date | Theme | Tests | Files.
- "Latest Feature Cycles" section: keep the last ~3 feature cycles only; fold-only cycles are omitted.
- Do NOT paste per-AC narratives or fold details here — those live in CHANGELOG-history.md.
-->

> **Part of [CLAUDE.md](../../CLAUDE.md)** — compact status index. Full per-cycle detail → [CHANGELOG-history.md](../../CHANGELOG-history.md).

## Current State

| Metric | Value |
|--------|-------|
| Tests | 3397 passed + 24 skipped + 16 xfailed (3437 collected) |
| Test files | ~241 |
| Version | v0.12.0 |
| CI | ubuntu-latest strict-gated (cycle 36+); windows-latest deferred to cycle-53+ |

## Cycle History (newest first)

| Cycle | Date | Theme | Tests | Files |
|-------|------|-------|-------|-------|
| 75 | 2026-07-17 | Dep-hygiene re-check (6 pip-audit findings + 3 resolver conflicts cleared; zero src changes) | 3437 (preserved) | ~241 |
| 74 | 2026-07-17 | Tier-boundary verifier hardening (max_keys + proposer/capture re-gates + required_keys) | 3413→3437 (+24) | 239→241 |
| 73 | 2026-05-09 | Completeness wrap + verdict prompt-version + tier-boundary verifier + hygiene | 3369→3411 (+42) | 234→239 |
| 72 | 2026-05-09 | wrap_wiki_context residual-surface completion | ~3345→~3369 (+24) | ~233→~234 |
| 71 | 2026-05-09 | wrap_wiki_context sibling-surface completion | ~3288→~3306 (+18) | ~234→~235 |
| 70 | 2026-05-08 | MCP prompt-injection boundary + snapshot subjects | 3288→3302 (+14) | ~232→~234 |
| 69 | 2026-05-08 | Backlog hygiene + test-quality + folds + snapshots | 3274→3288 (+14) | ~232 |
| 68 | 2026-05-07 | CLI hardening + lint/deps hygiene + docstring gate | 3248→3274 (+26) | ~226→~232 |
| 67 | 2026-05-07 | mimo-audit residual + Phase 4.5 cleanup | 3173→~3231 (+~58) | ~218→~226 |
| 66 | 2026-05-06 | Carry-over hardening | 3134→3173 (+39) | ~213→~218 |
| 65 | 2026-05-04 | Security hardening + config consistency | 3039→3134 (+95) | 207→~213 |
| 64 | 2026-05-03 | Backlog batch: autouse sandbox + graph cache + auto-publish | 3021→3039 (+18) | 200→207 |
| 58 | 2026-05-03 | Freeze-and-fold (4 folds) | 3021 (preserved) | 204→200 |
| 54-pickup | 2026-05-03 | Freeze-and-fold salvage (4 folds) | 3021 (preserved) | 208→204 |
| 57 | 2026-05-02 | Freeze-and-fold + sentinel-DELETE | 3022→3021 (-1) | 213→208 |
| 56 | 2026-05-02 | Freeze-and-fold (5 folds) + dep-CVE re-confirm | 3026 (preserved) | 219→214 |
| 55 | 2026-05-02 | Freeze-and-fold (4 folds) + dep-CVE re-confirm | 3025→3026 (+1) | 225→221 |
| 52 | 2026-04-28 | Backlog hygiene + freeze-and-fold | 3025 (preserved) | 229→225 |
| 51 | 2026-04-28 | Backlog hygiene + freeze-and-fold | 3025 (preserved) | 233→229 |
| 50 | 2026-04-28 | Backlog hygiene + freeze-and-fold | 3025 (preserved) | 237→233 |
| 49 | 2026-04-28 | Backlog hygiene + freeze-and-fold | 3025 (preserved) | 241→237 |
| 48 | 2026-04-28 | Test-quality upgrades + freeze-and-fold | 3025 (preserved) | 243→241 |
| 47 | 2026-04-28 | Backlog hygiene + dep-CVE + freeze-and-fold | 3025 (preserved) | 243→241 |
| 46 | 2026-04-28 | Phase 4.6 LOW closeout (shim deletion) | 3025 (preserved) | ~221→219 |
| 45 | 2026-04-27 | M3 mcp/core.py split + regression tests | 3019→3027→3025 | 241→244→243 |
| 44 | 2026-04-27 | Phase 4.6 M1+M2+M4 splits + vacuous-test upgrades | 3007→3019 (+12) | 242→241 |
| 43 | 2026-04-27 | Freeze-and-fold continuation (11 folds) | 3014→3007 (-7) | 251→242 |
| 41 | 2026-04-26 | Backlog hygiene + freeze-and-fold + dep-drift | 3014 (preserved) | 255→251 |
| 40 | 2026-04-26 | Backlog hygiene + freeze-and-fold + dep-drift | 3014 (preserved) | 258→255 |
| 39 | 2026-04-26 | Backlog hygiene + dep-drift + cycle-38 fold | 3014 (preserved) | 259→258 |
| 38 | 2026-04-26 | POSIX test re-enable + dual-site mock_scan_llm | 3012→3014 (+2) | 259 |
| 37 | 2026-04-26 | POSIX symlink fix + requirements split | 3014 (preserved) | 259 |
| 36 | 2026-04-26 | CI infrastructure hardening + strict gate | ~2990→3014 | 260+ |
| 35 | 2026-04-25 | Pre-Phase-5 BACKLOG batch | — | — |
| 34 | 2026-04-25 | Release hygiene + packaging + CI bootstrap | — | — |
| 33 | 2026-04-24 | MCP path-leak redaction + idempotency docstrings | — | — |
| 32 | 2026-04-23 | CLI↔MCP parity + _is_mcp_error_response widening | — | — |

## Latest Feature Cycles

- **Cycle 65** (2026-05-04): Security hardening — config call-time accessors (`get_project_root`, `get_model_tier`, `get_allowed_domains`), `path_safety.py` NEW (`_assert_under_project_root` + `_open_no_follow`), `mcp/_error_boundary.py` NEW (16 wraps), `_validate_page_id` Windows-char/segment hardening, `fetcher.py` http-only allowlist, `VectorIndex.build` file_lock, CLI secret-scrub fix. +95 tests across 12 new files. Five cycle-66 deferrals.
- **Cycle 64** (2026-05-03): Backlog batch — autouse `_autouse_kb_path_sandbox` (every test), `VectorIndex` dim-mismatch auto-rebuild, `kb.graph.cache` NEW (bespoke LRU), `auto_publish_after_compile`, syrupy snapshot infrastructure. +18 tests across 6 new files.
- **Cycle 36** (2026-04-26): CI foundation — strict pytest gate, `requires_real_api_key()`, pytest-timeout, platform skipifs, ubuntu-latest matrix. Test suite stabilised at 3014+.

Per-AC rationale, question logs, R1/R2 fix trails → `CHANGELOG-history.md` + `docs/superpowers/decisions/`.
