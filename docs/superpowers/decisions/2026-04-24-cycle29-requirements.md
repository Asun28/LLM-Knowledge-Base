# Cycle 29 — Requirements

**Date:** 2026-04-24
**Branch:** `feat/backlog-by-file-cycle29`
**Scope:** Group as many pre-Phase-5 BACKLOG items as possible into one cycle, following full feature-dev skill workflow, batch-by-file.

## Problem

Four small-to-medium items have been identified in the pre-Phase-5 BACKLOG that are (a) genuinely one-cycle-sized, (b) carry non-trivial operator / security value, and (c) naturally group by file. The cycle also needs to retire two stale BACKLOG entries discovered during session-start triage (cycle-28 L3 session-start inventory rule).

**M1 — `rebuild_indexes` audit status does not surface partial clears.** `compile/compiler.py::rebuild_indexes` cycle-25 AC1 added sibling-tmp cleanup AND cycle-25 CONDITION 1 decided "a tmp-unlink failure MUST NOT blank the main `cleared=True` status." The compound error is correctly stored in `result["vector"]["error"]` (lines 717-723). BUT the persisted audit line at lines 752-756 renders `vector=cleared` whenever `result["vector"]["cleared"]` is True — swallowing the tmp-unlink error. Operators reviewing `wiki/log.md` (the durable signal) cannot tell a rebuild left a stale `<vec_db>.tmp` behind. Source: cycle-28 R2 Codex BACKLOG addition.

**M2 — `rebuild_indexes` bypasses PROJECT_ROOT containment on overrides.** `rebuild_indexes(wiki_dir=..., *, hash_manifest=None, vector_db=None)` applies dual-anchor PROJECT_ROOT validation to `wiki_dir` (lines 638-656) but accepts `hash_manifest` and `vector_db` overrides at lines 658-661 and `unlink()`s them (lines 673-675, 687-689, 708-710) without the same check. The CLI does not expose the overrides today, so there is no externally-reachable exploit; but the Python API's safety boundary is inconsistent with the documented project-root guard. A future contributor or plugin author invoking `rebuild_indexes(wiki_dir=proj/wiki, hash_manifest=Path("/etc/passwd"))` would hit the `unlink()` with no validation. Source: cycle-28 R3 Codex BACKLOG addition.

**M3 — `config.py` lacks the architectural carve-out comment for `CAPTURES_DIR`.** CLAUDE.md explicitly carves out `raw/captures/` from the "LLM never modifies `raw/`" rule ("sole LLM-written output directory inside raw/ — atomised via kb_capture, then treated as raw input for subsequent ingest"). `config.py:80` declares `CAPTURES_DIR = RAW_DIR / "captures"` with no matching comment, so a maintainer reading only the config will see the architectural contradiction flagged by Phase 5 pre-merge R1 but not the resolution. Source: Phase 5 pre-merge BACKLOG item.

**M4 — BACKLOG contains a stale `_PROMPT_TEMPLATE` entry.** Cycle-19 AC15 already migrated the inline prompt string to `templates/capture_prompt.txt` with a lazy `_get_prompt_template()` helper (verified: `ls templates/` shows the file; `capture.py:310-318` shows the lazy loader; CLAUDE.md feedback Red Flags L2 documents the reload-leak fix). The "Phase 5 pre-merge MEDIUM" entry is a leftover from before cycle 19 shipped.

**M5 — BACKLOG Phase 4.5 HIGH #6 cold-load entry is stale.** The entry describes the unmitigated first-query cold-load problem (0.81s + 67 MB RSS). Cycle-26 AC1-AC5 shipped `maybe_warm_load_vector_model` + MCP-boot warm-load hook + `_get_model()` latency instrumentation + `get_vector_model_cold_load_count()` getter. Cycle-28 AC1-AC5 extended observability to `sqlite-vec` extension load + BM25 index build. The fix scope described by the entry IS shipped; the HIGH-Deferred text at line 109 correctly documents the remaining true-deferred surface (dim-mismatch AUTO-rebuild). Two entries describing the same item creates BACKLOG drift.

## Non-goals

- **NOT implementing the Phase 4.5 HIGH architectural refactors:** `compile/compiler.py` naming inversion, `ingest/pipeline.py` state-store fan-out receipt design, `mcp/*.py` async def conversion, `tests/conftest.py` sandbox-by-default, `graph/builder.py` shared caching policy, `query/embeddings.py` dim-mismatch AUTO-rebuild. Each requires a dedicated design pass.
- **NOT touching `utils/io.py` `file_lock` fair-queue / starvation.** High blast radius (ingest/compile/refine hot path); needs a dedicated cycle with platform-specific (`fcntl` vs `msvcrt.locking`) decisions.
- **NOT touching `capture.py` two-pass write CRITICAL.** Structural refactor; "v2 limitation" tag in the docstring is intentional.
- **NOT adding new CLI commands, new MCP tools, or changing public signatures** beyond the M1/M2 internal validation additions.
- **NOT extending `rebuild_indexes` to recover the stale tmp-on-partial-clear** (that is M1's responsibility to SURFACE, not fix-automatically). A stuck `.tmp` left from a crashed rebuild is already unlinked at the start of the NEXT rebuild_vector_index call (cycle-24 AC6); the tmp produced by a FAILED rebuild_indexes clean-slate is a different class because the main DB already succeeded.
- **NOT adding a CLI command for `rebuild_indexes` override validation.** M2 is a library-API invariant fix only.

## Acceptance Criteria

### AC1 — `rebuild_indexes` audit status reflects partial clears

- **Precondition:** `rebuild_indexes` runs with the main vector DB unlink succeeding AND the sibling `.tmp` unlink failing (e.g., permission denied, file-locked by another process).
- **Current behavior:** `result["vector"]["cleared"] = True` AND `result["vector"]["error"] = "tmp: <msg>"`. The audit line writes `vector=cleared`, losing the `tmp:` error tail.
- **Required behavior:** The audit line renders a compound status that ALWAYS surfaces a non-None `error` even when `cleared=True`. Proposed format: `vector=cleared (warn: tmp: <msg>)` when `cleared=True AND error` is truthy; `vector=cleared` when `cleared=True AND error is None`; `vector=<error>` when `cleared=False`. Same rule MIRRORED to the `manifest` block for symmetry (a future edit could introduce a similar `manifest.cleared=True AND error` combination).
- **Test:**
  1. `test_audit_renders_vector_cleared_with_tmp_error` — monkeypatch `Path.unlink` to fail on the `.tmp` path only; assert the `wiki/log.md` line contains `vector=cleared` AND `tmp:` AND the error message substring.
  2. `test_audit_renders_vector_cleared_clean_when_no_error` — happy path; assert the log line is exactly `vector=cleared` (no `(warn:` suffix).
  3. `test_audit_renders_vector_error_when_main_unlink_fails` — monkeypatch so main `vector_path.unlink` raises; assert the log line contains the main error without `cleared`.

### AC2 — `rebuild_indexes` validates `hash_manifest` + `vector_db` overrides under PROJECT_ROOT

- **Precondition:** Caller invokes `rebuild_indexes(wiki_dir=proj/wiki, hash_manifest=Path("/etc/passwd"))` or `vector_db=Path("/outside/project/x.db")`.
- **Current behavior:** `ValidationError` raised only for `wiki_dir`; overrides `unlink()`ed without validation.
- **Required behavior:** When an override is absolute, apply the SAME dual-anchor containment check `wiki_dir` uses: (a) the literal absolute path must equal PROJECT_ROOT or be relative-to PROJECT_ROOT, AND (b) its `.resolve()` target must equal PROJECT_ROOT or be relative-to PROJECT_ROOT. Raise `ValidationError("hash_manifest must be inside project root")` / `vector_db must be inside project root` on failure. Relative inputs skip the pre-check per the existing `wiki_dir` policy (resolve-only check applies; CWD may legitimately differ from project root). `None` overrides (the default case using `HASH_MANIFEST` / `_vec_db_path(wiki_dir)`) skip validation entirely.
- **Test:**
  1. `test_hash_manifest_override_outside_project_raises` — `rebuild_indexes(wiki_dir=proj/wiki, hash_manifest=Path("C:/Windows/system32/secret.txt"))` on Windows / `Path("/etc/passwd")` on POSIX; assert `ValidationError` raised BEFORE any unlink call (spy on `Path.unlink`).
  2. `test_vector_db_override_outside_project_raises` — mirror for `vector_db`.
  3. `test_hash_manifest_override_symlink_to_outside_raises` — create a symlink `<proj>/wiki/.lnk` pointing to `<outside>/x.json`; pass as `hash_manifest`; assert `ValidationError` (dual-anchor catches the `.resolve()` escape that a resolve-only check would miss).
  4. `test_hash_manifest_override_inside_project_succeeds` — pass `proj/.data/custom-hashes.json`; assert no `ValidationError`, manifest unlinked per the normal flow.
  5. `test_none_override_uses_default_without_validation_drift` — pass `hash_manifest=None`, `vector_db=None`; assert defaults `HASH_MANIFEST` + `_vec_db_path(wiki_dir)` used unchanged; no extra `Path.resolve()` calls (backward compat with cycle-25 callers).

### AC3 — `config.py` CAPTURES_DIR architectural carve-out comment

- **Current behavior:** `config.py:80` declares `CAPTURES_DIR = RAW_DIR / "captures"` with no explanatory comment.
- **Required behavior:** Add a single comment BLOCK above the `CAPTURES_DIR` line (3-5 lines max, per CLAUDE.md convention) stating: (a) `raw/captures/` is the sole LLM-written output directory inside `raw/`, (b) items are atomised via `kb_capture`, (c) then treated as raw input for subsequent ingest, (d) cross-reference CLAUDE.md §raw/ bullet. No code change.
- **Test:**
  1. `test_captures_dir_has_carve_out_comment` — open `src/kb/config.py`, locate the `CAPTURES_DIR = RAW_DIR / "captures"` line (grep), assert at least 3 of the preceding 6 lines contain one of these tokens: `LLM-written`, `carve-out`, `kb_capture`, `raw input for subsequent ingest`. Lightweight source-scan test per cycle-11 L2 — acceptable here because the assertion IS the documentation presence check; reverting the comment MUST fail this test (divergent-fail property preserved).

### AC4 — Delete stale `_PROMPT_TEMPLATE` BACKLOG entry

- **Current BACKLOG state:** Line 193-194 still lists `capture.py:209-238 _PROMPT_TEMPLATE inline string vs templates/ convention` as Phase 5 pre-merge MEDIUM (R1 + R2 NIT).
- **Current code state:** `capture.py:313-318` shows lazy `_get_prompt_template()` reading `TEMPLATES_DIR / "capture_prompt.txt"`. `ls templates/` confirms `capture_prompt.txt` exists.
- **Required action:** Delete the BACKLOG bullet. No code change. (Cycle-19 L2 reload-leak fix comment already documents the migration rationale.)
- **Test:** `test_captures_backlog_entry_deleted` — open BACKLOG.md, assert `_PROMPT_TEMPLATE` substring NOT present in any MEDIUM or below section. (Source-scan test — acceptable per cycle-11 L2 because the assertion IS the "doc hygiene shipped" check.)

### AC5 — Narrow stale Phase 4.5 HIGH #6 cold-load BACKLOG entry

- **Current BACKLOG state:** Line 95-96 lists `query/embeddings.py _get_model cold load — measured 0.81s + 67 MB RSS...` as Phase 4.5 HIGH with the R3 tag. The full fix scope described ("warm-load on MCP startup... background thread... progress line") is SHIPPED per cycle-26 AC1-AC5 + cycle-28 AC1-AC5.
- **Current HIGH-Deferred state:** Line 109 correctly summarises the shipped observability variants AND the remaining true-deferred surface (dim-mismatch AUTO-rebuild + sub-item (a)).
- **Required action:** Delete the stale HIGH bullet (line 95-96) entirely. The HIGH-Deferred entry at line 109 is the authoritative source-of-truth for what remains.
- **Test:** `test_cold_load_high_entry_deleted` — open BACKLOG.md, assert no HIGH-level bullet contains the substring `0.81s + 67 MB` (cycle-26/cycle-28 shipped work) OR `cold load — measured` (prior-cycle language). The HIGH-Deferred entry's text survives intact (different section, different rationale).

## Blast radius

| File | Kind | Risk |
|------|------|------|
| `src/kb/compile/compiler.py` | AC1 audit-message edit + AC2 validation guard at line 658-661 | MEDIUM — `rebuild_indexes` is invoked from CLI + public API; validation change is additive (fails closed on new attack surface) |
| `src/kb/config.py` | AC3 comment-only addition at line 80 | NONE — pure docstring/comment |
| `BACKLOG.md` | AC4 + AC5 deletions | NONE — pure documentation |
| `tests/test_cycle29_*.py` | 5 new test files | NONE — test-only |
| `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md` | Step-12 doc update | NONE |

No `src/kb/` public-signature changes. `rebuild_indexes` keyword-only overrides remain accepted; validation is strictly additive.

## Measured commit plan

1. TASK 1 — AC1 tests → AC1 impl (`compile/compiler.py` audit-message rewrite) → commit
2. TASK 2 — AC2 tests → AC2 impl (override dual-anchor validation) → commit
3. TASK 3 — AC3 test + `config.py` comment → commit
4. TASK 4 — AC4 + AC5 BACKLOG deletions + their regression tests → commit
5. Step-12 doc update → commit
6. Any R1/R2 fixes → commits

Target: 4 implementation commits + 1 doc commit + up to 2 review-fix commits = ~5-7 commits (matches prior small cycles).
