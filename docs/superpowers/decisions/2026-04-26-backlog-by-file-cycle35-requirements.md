# Cycle 35 — Backlog-by-file batch (pre-Phase 5 only)

Date: 2026-04-26
Branch: `feat/backlog-by-file-cycle35`
Convention: per `feedback_batch_by_file` — group fixes by file, HIGH+MEDIUM together, ~10-20 ACs across 4-6 file groups (small/focused cycle, not the 30-40 maximum).

## Problem

The pre-Phase-5 BACKLOG.md still carries five tactical items that have well-scoped fixes and existing test anchors. Cycle 34 deferred AC4e (architecture diagram v0.11.0 sync) explicitly to cycle 35 per design-doc fallback. Cycles 33 R1 surfaced four MCP/ingest items (M11 RMW lock, M13 empty-list, M14 backtick-escape, M15 filename-validator parity) and one sanitize item (M12 UNC slash-normalize bypass) that have xfail-strict tests already in `tests/test_cycle33_mcp_core_path_leak.py` waiting to flip green.

Closing these in one batch keeps the cycle small and clears all the "documented in BACKLOG since cycle 33" tactical items so future cycles can focus on larger structural items (graph cache H3, config split M1, compile_wiki two-phase pipeline M18, IndexWriter abstraction M11 evolution).

## Non-goals

- **No new features.** AC scope is BACKLOG closures only, not new MCP tools / new CLI commands / new search modes.
- **No structural refactors.** `config.py` god-module split (M1), `compile_wiki` two-phase pipeline (M18), `graph/builder.py` shared cache (H3), `tests/` freeze-and-fold (H4), `tests/conftest.py` leak-surface lockdown (H5), MCP tool async migration (H6), 11-stage ingest mutex (H7) are all OUT of scope — they require dedicated cycles.
- **No CVE bumps that require resolver work.** litellm 1.83.7 is blocked by click<8.2 conflict; ragas / diskcache / pip have no upstream patches. Out of scope.
- **No cycle-36 follow-ups.** Per-extra requirements split (M24), strict pytest CI gate (M25), cross-OS portability (M26), and PDF text extraction (M22) / KB_DISABLE_VECTORS env flag (M23) are explicitly cycle-36+ work.
- **Phase 5 items.** User explicitly excluded Phase 5 from this batch (line 213+ in BACKLOG.md).

## Acceptance criteria

### File group A — `utils/sanitize.py` (M12)

- **AC1.** Extend `_ABS_PATH_PATTERNS` in `src/kb/utils/sanitize.py:11-19` so forward-slash UNC paths (`//server/share/...`) are matched. Reason: `_rel(Path(fn_str))` slash-normalises Windows `\\\\server\\share\\path` to `//server/share/path` BEFORE the final regex sweep; the current backslash-only UNC alternative misses the slash form. Pattern requirement: `(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)`.
- **AC2.** Existing xfail-strict test `test_windows_ordinary_unc_filename_redacts` (in `tests/test_cycle33_mcp_core_path_leak.py:477-496`) starts passing → strict=True forces the marker REMOVAL. Step-9 implementation must remove the `@pytest.mark.xfail(strict=True, reason=...)` decorator in the same commit.
- **AC3.** Add a positive regression test `test_forward_slash_unc_redacts_via_extended_pattern` in the same class that constructs a forward-slash UNC OSError filename (`//corp.example.com/share$/secret.md`) and asserts `corp.example.com` / `share$` / `secret.md` are absent from `sanitize_error_text` output. (Cycle-24 L4 — assertion must FAIL under revert of AC1; verify by mentally reverting the pattern and confirming the slash form would survive the regex.)

### File group B — `ingest/pipeline.py` (M11 + M13 + M14)

- **AC4.** Wrap `_update_sources_mapping` (currently `src/kb/ingest/pipeline.py:761-806`) read-modify-write window in `file_lock(sources_file)` covering the `read_text` + `atomic_text_write` call sequence. Per cycle-19 file-lock discipline; closes M11's RMW concurrency residual on `_sources.md`.
- **AC5.** Wrap `_update_index_batch` (currently `src/kb/ingest/pipeline.py:816-857`) RMW window in `file_lock(index_path)` covering the `read_text` + `atomic_text_write` window. Closes M11's RMW concurrency residual on `index.md`.
- **AC6.** `_update_sources_mapping` empty-list semantics: when `wiki_pages == []`, log debug + return immediately at function entry — BEFORE the `pages_str = ", ".join(...)` line, BEFORE any file read. (M13 — closes the "emit a `→ \n` line with no page refs" footgun.)
- **AC7.** `_update_sources_mapping` lookups consistently use `escaped_ref` (currently uses raw `source_ref` in the `if f"\`{source_ref}\`" not in content:` membership check at line 792 and the per-line dedup loop at line 799). Closes M14 dedup mismatch when `source_ref` contains a backtick.
- **AC8.** Test `test_update_sources_mapping_holds_file_lock_across_rmw` — spy on `file_lock` (acquire/release) AND `atomic_text_write` calls; assert the lock context entered before `read_text` and exited after `atomic_text_write` for both branches (new entry append + re-ingest dedup). Per cycle-17 L4 / cycle-24 L4: this is a call-order assertion (not a real concurrency race), but unlike cycle-17 L4's spy-mid-critical-section anti-pattern, here the spy verifies the public call-order invariant the lock provides. Test MUST FAIL under revert of AC4 (no lock acquired before read).
- **AC9.** Test `test_update_index_batch_holds_file_lock_across_rmw` — same shape for `_update_index_batch`.
- **AC10.** Test `test_update_sources_mapping_skips_empty_wiki_pages` — invoke with `wiki_pages=[]`, assert no atomic_text_write call AND `_sources.md` content unchanged (read snapshot before and after, byte-equal).
- **AC11.** Test `test_update_sources_mapping_dedups_backtick_in_source_ref` — invoke twice with `source_ref="raw/has\`backtick.md"` and `wiki_pages=["e/foo"]`; assert single-line entry (not duplicated). MUST FAIL under revert of AC7.

### File group C — `mcp/core.py` (M15)

- **AC12.** Extract a shared `_validate_filename_slug(filename: str) -> tuple[str, str | None]` helper. The helper covers Windows-reserved-name + homoglyph (non-ASCII letter that slugify preserves) + NUL-byte + path-separator + length checks for unstructured user-supplied filenames. Place near `_validate_save_as_slug` (`src/kb/mcp/core.py:188-217`) so both share the reserved-name + ASCII-alphanumeric primitives. Note: `_validate_save_as_slug` enforces an additional `slugify(slug) == slug` round-trip equality (cycle-16 L1) — this strict round-trip is appropriate for `save_as` (an explicit slug parameter) but NOT for free-form filenames that legitimately differ from their slug form. The new helper performs the looser check (no path separators / no NUL / no Windows-reserved / no non-ASCII / length cap) without forcing slug equality.
- **AC13.** Wire `_validate_filename_slug` into `_validate_file_inputs` (`src/kb/mcp/core.py:167-178`). Both `kb_ingest_content` (`mcp/core.py:695`) and `kb_save_source` (`mcp/core.py:832`) gain the same boundary defense.
- **AC14.** Tests pinning rejection at `_validate_file_inputs` for: (a) NUL-byte (`"foo\x00.md"`); (b) homoglyph (`"а.md"` — Cyrillic а U+0430 vs ASCII a U+0061); (c) Windows-reserved (`"CON.md"`, `"PRN.txt"`, `"NUL"`); (d) path-traversal (`"../escape.md"`, `"foo/bar.md"`, `"foo\\bar.md"`).
- **AC15.** Test `test_validate_file_inputs_accepts_valid` pins the existing baseline — empty / oversized / valid plain ASCII filenames behave as before (no false positives introduced by the new helper).

### File group D — `docs/architecture/` (M21, AC4e deferred from cycle 34)

- **AC16.** `docs/architecture/architecture-diagram.html:501` `v0.10.0` → `v0.11.0`.
- **AC17.** `docs/architecture/architecture-diagram-detailed.html:398` `v0.10.0` → `v0.11.0`.
- **AC18.** Re-render `docs/architecture/architecture-diagram.png` from the updated HTML via headless Playwright (1440×900 viewport, device_scale_factor=3, full_page=True, --type=png) per `docs/reference/conventions.md` "Architecture Diagram Sync (MANDATORY)" rule. Single source HTML → single PNG (the `-detailed` variant has no PNG sibling — verify with `ls docs/architecture/*.png`).

## Blast radius

- `src/kb/utils/sanitize.py` — 1 file, `_ABS_PATH_PATTERNS` regex addition (1-2 lines).
- `src/kb/ingest/pipeline.py` — 1 file, `_update_sources_mapping` + `_update_index_batch` modifications (~20 line delta). Functions are called from `ingest_source` (the 11-stage pipeline). All callers internal to `kb.ingest.pipeline`.
- `src/kb/mcp/core.py` — 1 file, helper extraction + `_validate_file_inputs` wiring (~30 line delta).
- `tests/test_cycle33_mcp_core_path_leak.py` — xfail-marker removal + 1 new positive test.
- `tests/test_cycle35_*.py` — 2-3 new test files for the ingest + mcp/core ACs.
- `docs/architecture/architecture-diagram.html` + `architecture-diagram-detailed.html` — 1 line each.
- `docs/architecture/architecture-diagram.png` — re-render (binary diff).

No public API changes. No new module created. No deferred-import refactor. No deferred-test-file pin gymnastics.

## Threat-model anchors (Step 2 will deepen)

- **T-Sanitize-1** — UNC slash-normalize bypass leaks evidence (server / share names) into `Error[partial]:` MCP responses + sanitize_error_text outputs that flow to logs / wiki/log.md. Mitigation in AC1 + AC3.
- **T-Pipeline-1** — RMW races between concurrent `ingest_source` calls cause lost-update on `_sources.md` and `index.md`. Mitigation in AC4 + AC5 + AC8 + AC9.
- **T-Pipeline-2** — Empty `wiki_pages` writes a malformed `→ \n` line that future re-ingests scan as a stale entry. Mitigation in AC6 + AC10.
- **T-Pipeline-3** — Backtick-bearing `source_ref` defeats the dedup membership check, allowing duplicate entries on re-ingest. Mitigation in AC7 + AC11.
- **T-MCP-1** — `kb_ingest_content` / `kb_save_source` accept homoglyph / NUL / Windows-reserved filenames that slugify happily passes through, creating filesystem entries with attacker-influenced names. Mitigation in AC12 + AC13 + AC14 + AC15.
- **T-Doc-1** — Architecture diagram displays `v0.10.0` while pyproject.toml + README + CLAUDE.md all say `v0.11.0`; a reviewer trusting the diagram could be misled about the running version. Mitigation in AC16 + AC17 + AC18.
