# R1 Opus Design Evaluation — Cycle 35

(Output captured 2026-04-26. Becomes input to Step 5 decision gate.)

## Per-symbol verification table

| Symbol | File:line | Status | Notes |
|--------|-----------|--------|-------|
| `_ABS_PATH_PATTERNS` | `src/kb/utils/sanitize.py:11-19` | EXISTS | 4 alternatives. AC1 requires 5th (slash UNC). |
| `sanitize_text` | `src/kb/utils/sanitize.py:34` | EXISTS | Single-pass `.sub("<path>", s)`. |
| `sanitize_error_text` | `src/kb/utils/sanitize.py:56` | EXISTS | 3-stage redact. |
| `_update_sources_mapping` | `src/kb/ingest/pipeline.py:761-806` | EXISTS | Matches AC4. RMW unguarded. |
| `_update_index_batch` | `src/kb/ingest/pipeline.py:816-857` | EXISTS | Matches AC5. Has `if not entries: return` at 831. RMW unguarded. |
| `_write_index_files` | `src/kb/ingest/pipeline.py:866-890` | EXISTS | Calls both `_update_*` callees. |
| `_validate_file_inputs` | `src/kb/mcp/core.py:167-178` | EXISTS | Returns `str | None`. |
| `_validate_save_as_slug` | `src/kb/mcp/core.py:188-217` | EXISTS | Returns `tuple[str, str | None]`. |
| `_is_windows_reserved` | `src/kb/mcp/app.py:230-247` | EXISTS | Imported into `core.py:68`. |
| `_validate_filename_slug` | nowhere | WILL-CREATE | Confirmed absent. |
| `kb_ingest_content` call | `src/kb/mcp/core.py:695` | EXISTS | Matches AC13 cite. |
| `kb_save_source` call | `src/kb/mcp/core.py:832` | EXISTS | Matches AC13 cite. |
| Existing xfail-strict | `tests/test_cycle33_mcp_core_path_leak.py:477-486` | EXISTS | Matches AC2 cite. |
| Playwright | `.venv` | EXISTS | `from playwright.sync_api import sync_playwright` works. |

## Per-symbol monkeypatch table

| Modified Symbol | Monkeypatch sites | Risk |
|-----------------|------------------|------|
| `_update_sources_mapping` | 4 — `test_cycle18_ingest_observability.py:450,476`, `test_v01008_ingest_pipeline_fixes.py:99` (passthrough lambdas) | LOW |
| `_update_index_batch` | 4 — `test_cycle18_ingest_observability.py:451,477`, `test_v01008_ingest_pipeline_fixes.py:98` | LOW |
| Direct un-mocked callers | many — cycle-33 ingest-index-idempotency, phase4_audit, v0912/v0913/v0914/v0916 | MEDIUM — `file_lock(sources_file)` requires writable real dir; all current invokers pass `tmp_wiki` (real `tmp_path`) |
| `sanitize_text` / `_ABS_PATH_PATTERNS` | 0 monkeypatches | NONE |
| `_validate_file_inputs` / `_validate_save_as_slug` | 0 monkeypatches | NONE |

## AC scoring summary

- **AC1** PROCEED-WITH-CONDITION (insertion order: alternative #4)
- **AC2** PROCEED
- **AC3** PROCEED-WITH-CONDITION (hostname must contain dot; `\s` whitespace-only)
- **AC4 + AC5** PROCEED-WITH-CONDITION (sequential locks; no AB/BA via `_write_index_files` wrapper)
- **AC6** PROCEED (AFTER docstring + BEFORE `sources_file = ...`; `logger.debug`)
- **AC7** PROCEED-WITH-CONDITION (BOTH line 792 AND line 799 to `escaped_ref`; verify with grep)
- **AC8/AC9** PROCEED-WITH-CONDITION (spy `kb.ingest.pipeline.file_lock`, not `kb.utils.io.file_lock`)
- **AC10** PROCEED (also assert no warning in T8 verification)
- **AC11** PROCEED-WITH-CONDITION (raw string `r"raw/has\`backtick.md"`; add single-call invariant)
- **AC12** **AMEND** — Opus recommended narrow signature `str | None`; **R2 Codex Q5 disagrees** (recommends `tuple[str, str | None]` matching `_validate_save_as_slug`). Step 5 must resolve.
- **AC13** PROCEED-WITH-CONDITION (wiring placed AFTER existing checks)
- **AC14** PROCEED (`"\x00"` literal NUL; Cyrillic via `а`)
- **AC15** PROCEED (parametrize over `karpathy-llm-knowledge-bases.md`, `my_doc.md`, `file-2026-04-26.md`)
- **AC16/AC17** PROCEED-WITH-CONDITION (grep verifies no other v0.10.0 survives)
- **AC18** PROCEED — Playwright works; cycle-34 deferral closes

## OPEN QUESTIONS (for Step 5)

- **Q1** AC12 helper return signature: `tuple[str, str | None]` (R2 view) or `str | None` (R1 view)?
- **Q2** AC12 — reject leading-dot `".env"` / trailing-dot `"foo."` / leading-dash `"-foo"`? R1 said NO (out of scope); R2 Q4 said REJECT trailing dot/space.
- **Q3** AC12 — `[^\x00-\x7F]` (any non-ASCII) or non-ASCII-letter only?
- **Q4** AC1 — alternative #4 vs #5 ordering?
- **Q5** AC10 — assert no `_sources.md not found` warning under T8?
- **Q6** AC8/AC9 spy — `time.monotonic()` timestamps OR `unittest.mock.call_args_list` ordering?
- **Q7** Step-11b GitPython 3.1.46 → 3.1.47 — bundle into cycle 35 PR?
- **Q8** AC11 — add single-call invariant assertion?
- **Q9** AC18 — re-render commit bundled with AC16/AC17 HTML edits or separate?

## CONDITIONS (Step 9 must satisfy)

C1. AC1 regex inserted as alternative #4, with comment citing T1 + AC1.
C2. AC3 hostname must contain a dot (`corp.example.com`).
C3. AC4/AC5 lock acquires are SEQUENTIAL (sources released before index acquired) — no AB/BA deadlock. **NO wrapper-level lock in `_write_index_files`** (R2 Q2 confirmed file_lock is not reentrant).
C4. AC6 early-return placed AFTER docstring + BEFORE `sources_file = ...`; uses `logger.debug` not `logger.warning`.
C5. AC7 changes BOTH line 792 AND line 799 to `escaped_ref` (verify with grep before commit).
C6. AC8/AC9 spy `kb.ingest.pipeline.file_lock` (not `kb.utils.io.file_lock`).
C7. AC11 uses raw Python string literal; add single-call invariant assertion.
C8. AC12 helper signature per Step-5 decision (Q1 above).
C9. AC13 wiring: `_, err = _validate_filename_slug(filename); if err: return err` placed AFTER the existing empty/length checks.
C10. AC14 NUL test uses `"\x00"` literal in source.
C11. AC16/AC17 grep verifies line numbers + no other v0.10.0 survives.
C12. AC18 Playwright invocation uses `device_scale_factor=3, full_page=True, type="png"`, viewport `1440x900`.
C13. Step 11 same-class peer scan: re-grep `with file_lock(` in `src/kb/ingest src/kb/utils src/kb/compile`.

## SCOPE-EXPANSION

- **T1b (slash UNC long-path `//?/UNC/...`)**: Per Approach C this was deferred to data-driven inclusion at Step 11. **R2 Q1 recommends INCLUDING IT NOW** via a separate alternative `(?://\?/UNC/[^\s'\"]+/[^\s'\"]+(?:/[^\s'\"]*)?)`. Step 5 must resolve.

## SCOPE-NARROW

- **AC12 narrow signature.** R1 recommended `str | None`; R2 Q5 reverses to `tuple[str, str | None]`. Step 5 decides.

## Verification gaps Step 5 must close

Exact line numbers in `architecture-diagram*.html` (AC16/AC17) and the AC11 single-call invariant assertion.
