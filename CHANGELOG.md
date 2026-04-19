# Changelog

All notable changes to this project are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org/).

<!-- CHANGELOG FORMAT GUIDE
## [version] — YYYY-MM-DD (Phase X.Y)

### Added      — new features, tools, modules, test files
### Changed    — behavior changes, refactors, performance improvements
### Fixed      — bug fixes
### Removed    — deleted code, deprecated features
### Stats      — test count, tool count, module count (one line)

Rules:
- One bullet per change, start with the module/file affected in backticks
- Newest release at the top
- Keep bullets concise — what changed and why, not how
-->

<!--
## Document Relationship

| File          | Role                                          | When updated                     |
|---------------|-----------------------------------------------|----------------------------------|
| CHANGELOG.md  | Authoritative record of all shipped changes   | Every merge to main              |
| BACKLOG.md    | Open work items, ranked by severity           | On discovery; deleted on resolve |

**For all LLMs (Sonnet 4.6 · Opus 4.7 · Codex/GPT-5.4):** Read these two files together for a complete picture of project state.
CHANGELOG = what shipped; BACKLOG = what is open. Cross-link: each CHANGELOG cycle lists items deferred to BACKLOG by item number.
Resolved items are *deleted* from BACKLOG (not struck through) — the fix record lives here under the relevant phase.
-->

## [Unreleased]

### Phase 4.5 -- Backlog-by-file cycle 12 (2026-04-19)

17 AC across 13 files / 10 implementation commits. Tests: 2089 to 2115 (+26); full suite 2108 passed + 7 skipped. No dependency changes; 0 PR-introduced CVEs.

#### Added
- `tests/conftest.py` — `tmp_kb_env` fixture for isolated project roots in write-sensitive tests (AC1).
- `src/kb/utils/io.py` — `sweep_orphan_tmp` helper for non-recursive stale `.tmp` sibling cleanup (AC2).
- `src/kb/utils/pages.py` — LRU-cached `load_page_frontmatter` helper keyed by path and `mtime_ns` (AC8).
- `pyproject.toml` / `kb.mcp` — `kb-mcp` console script alongside the existing CLI entry point (AC7).
- Cycle-12 regression coverage — `test_cycle12_*.py` files including `sanitize_context` (AC14), plus augment regressions in `test_v5_lint_augment_cli.py` and `test_v5_lint_augment_orchestrator.py` (AC12, AC13).

#### Changed
- `src/kb/config.py` — `KB_PROJECT_ROOT` environment override plus bounded walk-up fallback from the current working directory (AC5, AC6).
- `src/kb/utils/io.py` — docstring caveats for `file_lock` PID behavior and atomic-write behavior on network mounts (AC3, AC4).
- `src/kb/utils/pages.py` — `load_all_pages` now uses `load_page_frontmatter` (AC9).
- `src/kb/lint/checks.py` — four `frontmatter.load` sites migrated to `load_page_frontmatter` (AC11).
- `src/kb/mcp_server.py` — back-compat shim for the package-level MCP entry point (AC7).
- `src/kb/graph/builder.py` — module docstring documents `page_id()` lowercasing and case-sensitive filesystem caveat (AC10).

#### Fixed
- None - cycle 12 is additive housekeeping.

#### Security
- `KB_PROJECT_ROOT` is OS-trusted; `Path.resolve()` plus `.is_dir()` gates invalid values, logs `WARNING`, and falls back safely. A hostile local environment can still redirect file I/O in the single-user CLI context, which is documented here for awareness. AC14 pins `conversation_context` sanitization across both `kb_query` branches.

### Phase 4.5 — Backlog-by-file cycle 11 (2026-04-19)

14 AC across 14 files / 13 implementation commits. Tests: 2041 → 2081 (+40); full suite 2081 passed + 7 skipped. No dependency changes; 0 PR-introduced CVEs.

#### Added
- `tests/test_cycle11_ingest_coerce.py` — regression coverage for `_coerce_str_field` scalar/list/dict/missing-field handling, comparison/synthesis rejection, and MCP no-file no-write behavior (AC1, AC2, AC3).
- `tests/test_cycle11_utils_pages.py` — direct canonical coverage for `page_id` / `scan_wiki_pages`, including lowercasing, subdir IDs, sentinel skip, deterministic order, and graph-builder re-export identity (AC6).
- `tests/test_cycle11_cli_imports.py` — CLI command smoke tests for function-local import paths plus subprocess `--version` / `-V` short-circuit checks that avoid importing `kb.config` (AC7, AC8).
- `tests/test_cycle11_stale_results.py` — `_flag_stale_results` edge-case coverage for missing/empty sources, non-ISO `updated`, non-string `updated`, and mtime-equals-page-date (AC9, AC10, AC11).
- `tests/test_cycle11_task6_mcp_ingest_type.py` — MCP same-class coverage that `kb_ingest`, `kb_ingest_content`, and `kb_save_source` steer comparison/synthesis callers to `kb_create_page` (AC2).

#### Changed
- `src/kb/utils/pages.py` — canonical home for `page_id(page_path, wiki_dir=None)` and `scan_wiki_pages(wiki_dir=None)`; `src/kb/graph/builder.py` now re-exports both for back-compat (AC4, AC5).
- `src/kb/compile/compiler.py`, `src/kb/compile/linker.py`, `src/kb/evolve/analyzer.py`, `src/kb/lint/checks.py`, `src/kb/lint/runner.py`, `src/kb/lint/semantic.py` — internal callers now import page filesystem helpers from `kb.utils.pages` instead of `kb.graph.builder` (AC4, AC5).
- `tests/test_ingest.py` — `test_ingest_source` uses `tmp_project` plus explicit `wiki_dir=` / `raw_dir=` instead of manual wiki scaffolding and module-global patching (AC12).
- `tests/test_compile.py` — manifest double-write regression now includes a behavioral manifest-content assertion in addition to the existing save-count pin (AC13).

#### Fixed
- `src/kb/ingest/pipeline.py` — remaining scalar extraction read sites use `_coerce_str_field`; `source_type="comparison"` / `"synthesis"` now rejects early with a `kb_create_page` hint instead of falling into the broken ingest-render path (AC1, AC2, AC3).
- `src/kb/mcp/core.py` — `kb_ingest`, `kb_ingest_content`, and `kb_save_source` return explicit comparison/synthesis guidance naming `kb_create_page` before generic unknown-source-type handling (AC2).

#### Security
- Cycle-11 security verify recorded no dependency diff in `requirements.txt` / `pyproject.toml`; no Class-B PR-introduced CVEs. Same-class comparison/synthesis MCP handling was completed in follow-up (AC2).

### Backlog-by-file cycle 10 (2026-04-18)

- `src/kb/mcp/app.py` — AC0: `_validate_wiki_dir` now enforces `PROJECT_ROOT` containment; error strings standardised (commit `ee1279f`).
- `src/kb/mcp/quality.py` — AC1+AC1b: `kb_affected_pages` surfaces `backlinks` / `shared_sources` warnings (commit `4f045a4`).
- `src/kb/mcp/browse.py` — AC3: `kb_stats` migrated to `_validate_wiki_dir`. AC2 regression-pinned (commit `a1c1f79`).
- `src/kb/mcp/health.py` — AC4+AC5+AC6: `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift` migrated to `_validate_wiki_dir` (commit `82b582a`). Plus security follow-up `1c3832e` removing `Path.resolve()` bypass.
- `src/kb/query/engine.py` + `src/kb/config.py` — AC7+AC8: `VECTOR_MIN_SIMILARITY` cosine floor in `search_pages` (commit `6159d85`).
  - **Note — RRF ranking interaction with `VECTOR_MIN_SIMILARITY`.** When a page is returned by BM25 but the vector backend returns the same page with cosine score below `VECTOR_MIN_SIMILARITY` (0.3), the vector contribution to RRF fusion is intentionally dropped. This tightens ranking so marginal-vector-similarity pages no longer receive a dual-backend boost; pages with strong BM25 match retain their BM25 rank. If observed regressions in recall suggest the threshold is too strict, tune via the `VECTOR_MIN_SIMILARITY` constant in `src/kb/config.py`.
- `src/kb/compile/compiler.py` — AC9: `find_changed_sources` docstring documents deletion-pruning persistence (commit `70b5e49`).
- `src/kb/utils/text.py` — AC28.5: `wikilink_display_escape` now backslash-escapes `|` instead of silently substituting an em dash (commit `70b5e49`).
- `src/kb/capture.py` — AC10+AC11: UUID prompt boundary + submission-time `captured_at` (commit `46f0e34`).
- `src/kb/ingest/pipeline.py` — AC12+AC13a+AC13b: `_coerce_str_field` helper + `extraction_json` pass before manifest reservation + defensive checks in `_build_summary_content` (commit `01bb1bb`).
- `src/kb/lint/_safe_call.py` — AC1s: sanitises embedded exception text via `_sanitize_error_str` (commit `9d4b447`).
- `src/kb/capture.py` — AC14: `CaptureError` exception + `raw/captures` side-effect note (commit `46f0e34`).
- Tests: 2004 → 2041 (+37 new tests); all passing, 7 Windows-skips (case-insensitive FS + symlinks); 0 new Dependabot alerts.
- STALE at cycle 10 review (already fixed, removed from BACKLOG): `utils/wiki_log.py` torn-last-line (MEDIUM); `mcp/browse.py` query-length-cap + stale-flag (HIGH-Additional).

### Quick Reference — Unreleased cycles (2026-04-16 · 2026-04-19)

| Cycle | Date | Items | Test Δ | Primary areas |
|-------|------|-------|--------|---------------|
| [**backlog-by-file cycle 12**](#phase-45--backlog-by-file-cycle-12-2026-04-19) | 2026-04-19 | 17 AC / 13 files / 10 commits | 2089 to 2115 (+26) | conftest fixture, io sweep, KB_PROJECT_ROOT, frontmatter LRU cache, lint/checks migration, kb-mcp console script, graph docstring, augment regression coverage, sanitizer pin |
| [**backlog-by-file cycle 11**](#phase-45--backlog-by-file-cycle-11-2026-04-19) | 2026-04-19 | 14 AC / 14 files / 13 commits | 2041 → 2081 (+40) | ingest coercion + comparison/synthesis reject, page helper relocation, CLI import smoke, stale-result edge cases, test fixture cleanup, MCP same-class guard |
| [**backlog-by-file cycle 9**](#phase-45--backlog-by-file-cycle-9-2026-04-18) | 2026-04-18 | 30 AC + 2 security fixes / 14 files | 1949 → 2003 (+54) | ingest lazy export, wiki_dir isolation, MCP boundary validation, compile/lint/evolve consistency, capture hardening, LLM redaction, env docs |
| [**backlog-by-file cycle 8**](#phase-45--backlog-by-file-cycle-8-2026-04-18) | 2026-04-18 | 30 AC / 19 files | 1919 → 1949 (+30) | package surface, model validators, LLM telemetry, wiki_dir plumbing, consistency caps, PageRank→RRF, contradictions idempotency, notes validation helper (PR #22) |
| [Backlog-by-file cycle 7](#phase-45--backlog-by-file-cycle-7-2026-04-18) | 2026-04-18 | 30 / 22 files | 1868 → 1919 (+51) | mcp/app, mcp/core, mcp/health, lint/_safe_call, lint/checks, lint/verdicts, lint/runner, lint/semantic, query/embeddings, query/engine, graph/builder, graph/export, compile/linker, evolve/analyzer, ingest/pipeline, ingest/extractors, review/context, review/refiner, utils/text, utils/io, config, cli |
| [Backlog-by-file cycle 6](#phase-45--backlog-by-file-cycle-6-2026-04-18) | 2026-04-18 | 15 / 14 files | 1836 → 1868 (+32) | mcp/core, mcp/health, query/rewriter, query/engine, query/embeddings, query/hybrid, query/dedup, ingest/pipeline, cli, evolve/analyzer, graph/builder, utils/pages |
| [Cycle 5 redo (hardening)](#phase-45--cycle-5-redo-hardening-2026-04-18) | 2026-04-18 | 6 / 6 files | 1821 → 1836 (+15) | query/engine, query/citations, mcp/app, lint/augment, utils/text, tests |
| [Backlog-by-file cycle 5](#phase-45--backlog-by-file-cycle-5-2026-04-18) | 2026-04-18 | 14 / 13 files | 1811 → 1820 (+9) | config, text, verdicts, engine, extractors, pipeline, mcp/core, mcp/app, cli, mcp_server, llm, pyproject, tests |
| [Concurrency fix + docs tidy (PR #17)](#concurrency-fix--docs-tidy-pr-17-2026-04-18) | 2026-04-18 | 3 / 3 files | 1810 → 1811 (+1) | verdicts, capture, test_v0915_task06 |
| [Backlog-by-file cycle 4](#phase-45--backlog-by-file-cycle-4-2026-04-17) | 2026-04-17 | 22 / 16 files | 1754 → 1810 (+56) | mcp/core, browse, quality, app, health, rewriter, engine, dedup, text, wiki_log, pipeline, bm25, compiler, pages, linker |
| [Backlog-by-file cycle 3](#phase-45--backlog-by-file-cycle-3-2026-04-17) | 2026-04-17 | 24+2 / 16 files | 1727 → 1754 (+27) | llm, io, feedback, embeddings, engine, hybrid, contradiction, extractors, pipeline, checks, runner, export, browse, health |
| [Backlog-by-file cycle 2](#phase-45--backlog-by-file-cycle-2-2026-04-17) | 2026-04-17 | 30 / 19 files | → 1727 | hashing, markdown, wiki_log, io, llm, text, evidence, linker, feedback, reliability, analyzer, trends, semantic, citations, hybrid, dedup, rewriter, engine |
| [Backlog-by-file cycle 1](#phase-45--backlog-by-file-cycle-1-2026-04-17) | 2026-04-17 | 38 / 18 files | → 1697 | pipeline, lint/augment, cli, capture, extractors, contradiction, mcp/quality, mcp/browse, mcp/core, engine, rewriter, dedup, verdicts, checks, markdown, feedback, refiner, wiki_log |
| [HIGH cycle 2](#phase-45--high-cycle-2-2026-04-17) | 2026-04-17 | 22 / 16 files | → 1645 | markdown, refiner, analyzer, semantic, extractors, compiler, checks, trends, feedback, contradiction, pipeline, engine, hybrid, rewriter, builder, pages |
| [HIGH cycle 1](#phase-45--high-cycle-1-2026-04-16) | 2026-04-16 | 22 / multi | → baseline | refiner, evidence, pipeline, wiki_log, engine, linker, citations, markdown, rewriter, mcp/core, embeddings, compiler |
| [CRITICAL docs-sync](#phase-45--critical-cycle-1-docs-sync-2026-04-16) | 2026-04-16 | 2 | 1546 → 1552 | pyproject.toml, CLAUDE.md, scripts/verify_docs.py |

> Older history (Phase 4.5 CRITICAL audit 2026-04-15 + all released versions): [CHANGELOG-history.md](CHANGELOG-history.md)

---

### Phase 4.5 — Backlog-by-file cycle 9 (2026-04-18)

30 AC across 14 files plus 2 security-review fixes. Tests: 1949 → 2003 (+54, across 150 test files). Full feature-dev pipeline (requirements → threat model + design gate → implementation + security verify → docs). 0 PR-introduced CVEs.

#### Added
- `src/kb/ingest/__init__.py` — lazy `__getattr__` re-export for `ingest_source`, preserving the package public API without loading the ingest pipeline on package import (AC29).
- `src/kb/mcp/app.py` — `_validate_wiki_dir(wiki_dir)` boundary helper for MCP wiki override paths (security review).
- `src/kb/evolve/analyzer.py` — `_orphan_via_graph_resolver` helper so orphan-concept detection uses `build_graph`'s bare-slug resolver (AC13).
- `src/kb/utils/llm.py` — `_redact_secrets` helper for LLM error text before truncation (AC27).
- Cycle-9 regression coverage across compiler, evolve, lint augment/checks, LLM redaction, MCP app/core/health/path validation, package exports, query engine, and env example tests.

#### Changed
- `src/kb/query/engine.py` — vector-index lookup, stale-flag project root, `search_mode`, and raw fallback now derive paths from the active `wiki_dir` override instead of repo defaults (AC1, AC2, AC3, AC4).
- `src/kb/mcp/core.py` — `kb_compile_scan(wiki_dir=None)` threads custom wiki directories into changed-source scanning; `kb_ingest` rejects over-cap source files instead of silently truncating; `kb_ingest_content` validates boundary content size consistently (AC7, AC8, AC9).
- `src/kb/mcp/health.py` — `kb_lint` and `kb_evolve` scope feedback-derived sections to the provided wiki project's `.data/feedback.json` (AC5, AC6).
- `src/kb/mcp/app.py` — MCP instructions render from alphabetized `_TOOL_GROUPS` instead of a monolithic FastMCP instructions string (AC28).
- `src/kb/lint/augment.py` — `run_augment` summary counts final per-stub outcomes, so fallback URL success no longer reports a failed stub (AC11).
- `src/kb/lint/checks.py` — `check_source_coverage` parses frontmatter once and extracts body refs from parsed content (AC12).
- `tests/conftest.py` — `RAW_SUBDIRS` derives from `SOURCE_TYPE_DIRS`; `tmp_captures_dir` asserts containment under `PROJECT_ROOT` (AC25, AC26).
- `.env.example` — `ANTHROPIC_API_KEY` documented as optional for Claude Code/MCP mode and required only for direct API-backed flows (AC30).

#### Fixed
- `src/kb/compile/compiler.py` — `load_manifest` now catches transient `OSError` alongside JSON/Unicode read failures (AC10).
- `src/kb/capture.py` — capture scanner and writer hardening: best-effort decode logging, bounded slug collision attempts, `_is_path_within_captures` rename, encoded-secret labels, `NamedTuple` secret patterns, stripped accepted bodies, prompt-size guard, and per-process rate-limit documentation (AC14, AC15, AC16, AC17, AC18, AC19, AC20, AC21).
- `tests/test_capture.py` — capture tests import `CAPTURE_KINDS` from config, add YAML title round-trip regressions, correct the CRLF-size comment, and remove duplicate `re` import (AC22, AC23, AC24).

#### Security
- `src/kb/utils/llm.py` — four LLM error sites redact API keys/tokens/secrets before truncation and surfacing errors (AC27).
- `src/kb/mcp/app.py`, `src/kb/mcp/core.py`, `src/kb/mcp/health.py` — `wiki_dir` overrides are validated at the MCP boundary before use (security review).
- Test secret literals were split so redaction fixtures do not carry scanner-triggering full secret strings (security review).

---

### Phase 4.5 — Backlog-by-file cycle 8 (2026-04-18)

30 AC across 19 files. Tests: 1919 → 1949 (+30, across 138 test files). Full feature-dev pipeline (requirements → threat model + CVE baseline → Opus design decision gate → Codex plan + plan-gate → TDD impl + CI gate → Codex security verify + PR-introduced CVE diff → docs). 0 PR-introduced CVEs.

#### Added
- `src/kb/config.py` — new config constants: `MAX_CONSISTENCY_GROUPS`, `MAX_CONSISTENCY_PAGE_CONTENT_CHARS`.
- `src/kb/models/page.py` — `WikiPage` and `RawSource` model validators, `WikiPage.to_dict()`, and `WikiPage.from_post()` class methods.
- `src/kb/__init__.py`, `src/kb/utils/__init__.py`, `src/kb/models/__init__.py` — curated `__all__` for top-level `kb` package, `kb.utils`, and `kb.models`.
- `src/kb/mcp/app.py` — `_validate_notes(notes, field_name)` helper.
- `src/kb/mcp/browse.py::kb_stats` and `src/kb/mcp/health.py::kb_verdict_trends` MCP tools gain `wiki_dir` override with path-traversal rejection.
- `src/kb/utils/llm.py` — LLM success INFO telemetry: logs model/attempt/tokens_in/tokens_out/latency_ms on each successful call.
- 30 new tests across 7 test files (`tests/test_cycle8_*.py`).

#### Changed
- `src/kb/query/engine.py` — PageRank no longer applied as a post-fusion score multiplier; it now enters `rrf_fusion` as a separate ranked list (union of BM25 + vector candidates), giving it equal standing in Reciprocal Rank Fusion.
- `src/kb/ingest/pipeline.py::_persist_contradictions` is now idempotent: a re-ingest with the same source, same date, and same claims produces no duplicate block (exact block match inside `wiki/contradictions.md`).
- `src/kb/lint/semantic.py::build_consistency_context` auto mode now caps at `MAX_CONSISTENCY_GROUPS` (20) total groups and truncates per-page body at `MAX_CONSISTENCY_PAGE_CONTENT_CHARS` (4096 chars) after frontmatter strip.

#### Fixed
- Eager `kb.__init__` imports at package import time caused a circular import on the `kb --version` short-circuit path (regression from cycle-8 TASK 3); fixed via PEP 562 lazy `__getattr__` in `src/kb/__init__.py`.
- `src/kb/query/engine.py` — PageRank tie-order non-determinism when multiple pages share the same score.

#### Security
- (Class A) `pip` upgraded 24.3.1 → 26.0.1 in venv; patches CVE-2025-8869 and CVE-2026-1703 plus 2 ECHO advisories.
- `diskcache==5.6.3` (CVE-2025-69872, GHSA-w8v5-vhqr-4h9v) has no upstream patch as of 2026-04-18; recorded in BACKLOG. No Class B (PR-introduced) CVEs.

---

### Phase 4.5 — Backlog-by-file cycle 7 (2026-04-18)

30 items across 22 source files. Tests: 1868 → 1919 (+51, including 48 new behavioural tests in `test_backlog_by_file_cycle7.py` + 3 inline template-sentinel + updated cycle-5 wrap_purpose pin). Full feature-dev pipeline (requirements → threat model + CVE baseline → Opus design decision gate → Codex plan + plan-gate → TDD impl + CI gate → Codex security verify + PR-introduced CVE diff → docs). 0 PR-introduced CVEs.

#### Added
- `src/kb/lint/_safe_call.py` — new module hosting `_safe_call(fn, *, fallback, label)` helper so lint/runner and mcp/health silent-degradation sites surface `<label>_error: …` instead of silent `None` (AC27).
- `src/kb/mcp/app.py::_sanitize_error_str(exc, *paths)` — helper that strips Windows absolute/UNC paths, POSIX absolute paths, and `OSError.filename`/`filename2` attributes from exception strings before MCP tools return them to the client (AC12/AC13 shared helper).
- `src/kb/config.py::get_model_tier(tier)` — lazy env-aware alternative to the import-time `MODEL_TIERS` dict so tests and long-lived processes observe `CLAUDE_*_MODEL` env mutations mid-run (AC24).
- `tests/test_backlog_by_file_cycle7.py` — 48 behavioural regression tests covering every cycle-7 AC. Red-flag self-checks: no `re.findall` source-scans, no `inspect.getsource` grep, no negative-assert patterns.
- `CLAUDE.md` — new `### Evidence Trail Convention` subsection documenting the reverse-chronological insert-after-sentinel behaviour (AC25).

#### Changed
- `src/kb/graph/builder.py` `build_graph(wiki_dir, *, pages=None)` — `pages` is now keyword-only; callers supplying preloaded page dicts skip the internal `scan_wiki_pages` walk (AC11).
- `src/kb/compile/linker.py` `build_backlinks(wiki_dir, *, pages=None)` — same pattern (AC10).
- `src/kb/lint/semantic.py` — `build_consistency_context` + `_group_by_shared_sources` / `_group_by_wikilinks` / `_group_by_term_overlap` accept optional `pages=` bundle (AC19).
- `src/kb/evolve/analyzer.py::generate_evolution_report` — loads `pages_dicts` once via `load_all_pages` and threads into `build_graph(pages=…)` + `analyze_coverage(pages_dicts=…)` (AC9).
- `src/kb/ingest/pipeline.py::_find_affected_pages` — passes preloaded pages into `build_backlinks` so the cascade path no longer does a second disk walk (AC8).
- `src/kb/ingest/pipeline.py::_update_existing_page` — References regex masks fenced code blocks before substitution + normalises trailing newline (AC5); re-ingest context enrichment now appends `### From {source_ref}` subsection under existing `## Context` header instead of silently dropping the new context (AC7); `ctx=` kwarg added for direct callers; bare contradiction `except` narrowed to `(KeyError, TypeError, re.error)` so bug-indicating `ValueError` / `AttributeError` propagate (AC6).
- `src/kb/ingest/pipeline.py::_write_wiki_page` — hand-rolled f-string YAML frontmatter replaced with `frontmatter.Post` + `frontmatter.dumps()` so YAML-escaping becomes the library's responsibility; back-compat shim accepts `page_path=` or legacy `path=` (AC29).
- `src/kb/ingest/extractors.py::clear_template_cache` — serialized via module-level `_template_cache_lock` so concurrent clears vs readers cannot observe mid-clear state (AC28).
- `src/kb/query/embeddings.py::rebuild_vector_index` — batch path bypasses `embed_texts`, calls `model.encode(texts)` directly and passes each numpy row via buffer protocol to `sqlite_vec.serialize_float32` (AC2). `_index_cache` now bounded at `MAX_INDEX_CACHE_SIZE=8` with FIFO eviction under `_index_cache_lock` (AC3).
- `src/kb/query/engine.py::query_wiki` — docstring documents the `stale` flag on each citation entry + the `stale_citations` return field (AC4).
- `src/kb/lint/checks.py::check_dead_links` — skips targets matching root-level `_INDEX_FILES` (`index.md`/`_sources.md`/`log.md`) when the file exists (AC18).
- `src/kb/lint/verdicts.py::load_verdicts` — adds single 50 ms retry on transient `OSError` / `JSONDecodeError` / `UnicodeDecodeError` for Windows atomic-rename window (AC20).
- `src/kb/lint/runner.py::run_all_checks` — verdict-summary load routed through `_safe_call(label="verdict_history")`; report dict gains `verdict_history_error` field on failure (AC27).
- `src/kb/mcp/core.py` — ingest/read/scan/compile/search/capture error-string sites route `{e}` through `_sanitize_error_str(e, <path>)`; R1 security verify caught 4 residual sites (API-mode ingest, `read_text`, `kb_compile_scan`, `kb_compile`) patched in follow-up commit (AC12).
- `src/kb/mcp/health.py` — 5 error-string sites (`kb_lint`, `kb_evolve`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`) piped through `_sanitize_error_str`; feedback-flagged-pages block in `kb_lint` routed through `_safe_call` (AC13 + AC27 wiring).
- `src/kb/mcp/app.py::_rel()` — defensive guard for `None` / non-`Path` inputs so `_sanitize_error_str` can safely scan `exc.filename` without `AttributeError` (AC12 follow-up).
- `src/kb/review/context.py::pair_page_with_sources` — accepts explicit keyword-only `project_root=` ceiling; falls back to `raw_dir.parent` for back-compat (AC21).
- `src/kb/review/refiner.py::refine_page` — parses frontmatter block with `yaml.safe_load` before rewriting; malformed YAML pages return `Error` instead of being laundered through a successful write (AC22).
- `src/kb/utils/text.py::wrap_purpose` — now escapes attacker-planted `</kb_purpose>` closers to the inert `</kb-purpose>` hyphen variant, mirroring `_escape_source_document_fences` (AC23).
- `src/kb/utils/io.py` module docstring — documents lock-ordering convention `VERDICTS → FEEDBACK → REVIEW_HISTORY` (AC17).
- `src/kb/cli.py` — `--version` short-circuits BEFORE any `kb.config` import so operators with broken configs can still query the installed version; module docstring documents exit-code contract (AC16 + AC30).
- `src/kb/graph/export.py` — Mermaid title-fallback uses the unmodified filename stem when `_sanitize_label` strips the title to empty, preserving `-` in the rendered label (AC26).
- `tests/conftest.py` — autouse fixture `_reset_embeddings_state` clears `kb.query.embeddings._model` and `_index_cache` between every test (AC1).
- `tests/test_phase4_audit_compile.py::test_manifest_pruning_keeps_unchanged_source` — asserts `_template/article` sentinel key AND hash value preserved across unrelated-source mutation (AC15).
- `tests/test_cycle5_hardening.py::test_wrap_purpose_escapes_sentinel_closer` — flipped from pinning non-escape (cycle 5 decision) to asserting the escape fires (cycle 7 AC23 supersedes).

#### Fixed
- `src/kb/mcp/core.py` — 4 residual raw `{e}` error-string sites flagged by R1 Codex security verify (AC12 follow-up, commit `32b9387`).

---

### Phase 4.5 — Backlog-by-file cycle 6 (2026-04-18)

15 items across 14 source files. Tests: 1836 → 1868 (+32). Full feature-dev pipeline (requirements → threat model + CVE baseline → Opus design decision gate → Codex plan → TDD impl + CI gate → Codex security verify + PR-introduced CVE diff → docs). 0 PR-introduced CVEs.

#### Process artifacts (new)

- `docs/superpowers/decisions/2026-04-18-cycle6-requirements.md` — Step 1 AC1-AC16 (15 backlog items + tests).
- `docs/superpowers/decisions/2026-04-18-cycle6-threat-model.md` — Step 2 threat table + Step 11 checklist.
- `docs/superpowers/decisions/2026-04-18-cycle6-design.md` — Step 5 Opus decision gate verdict: APPROVE with 6 conditions.

#### Added

- `src/kb/query/engine.py` — `_PAGERANK_CACHE` process-level cache + `_PAGERANK_CACHE_LOCK` (AC4). Keyed on `(str(wiki_dir.resolve()), max_mtime_ns, page_count)` matching `_WIKI_BM25_CACHE_LOCK` precedent; unbounded per single-user local stance; thread-safe under FastMCP pool via check-under-lock + double-check-store pattern.
- `src/kb/query/embeddings.py` — `VectorIndex._ensure_conn()` + `self._disabled` + `self._ext_warned` attrs (AC5). sqlite3 connection opened ONCE per VectorIndex instance; on `sqlite_vec.load` failure the instance is marked disabled, a single WARNING is logged, and every subsequent `query()` call returns `[]` without retrying extension load. Connection left open for instance lifetime (process exit closes fd).
- `src/kb/cli.py` — `_is_debug_mode()` + `_error_exit()` + `_setup_logging()` helpers plus top-level `--verbose` / `-v` flag (AC9). `KB_DEBUG=1` env var OR `--verbose` prints full `traceback.format_exc()` to stderr BEFORE the truncated `Error:` line. Default behavior unchanged.
- `src/kb/evolve/analyzer.py` — `_iter_connection_pairs` generator helper (AC12). Replaces the three-level `break` + `_pairs_truncated` flag with a single-source-of-truth cap gate that emits one WARNING on truncation.
- `tests/test_backlog_by_file_cycle6.py` — 31 behavioral regression tests for AC1-AC15 + Step-11 condition (`sqlite3.connect(` count == 3 in embeddings.py). Every test exercises production code paths, not `inspect.getsource` greps (per `feedback_inspect_source_tests` memory).

#### Changed

- `src/kb/mcp/core.py` — `kb_ingest_content` accepts `use_api: bool = False` kwarg (AC1). When `True`, skips the `extraction_json` requirement and falls through to `ingest_source`'s LLM extraction path — mirroring `kb_query` / `kb_ingest`'s existing contract.
- `src/kb/mcp/health.py` — `kb_detect_drift`, `kb_evolve`, `kb_graph_viz` each accept `wiki_dir: str | None = None` (AC2) and thread it to `detect_source_drift`, `generate_evolution_report`, `export_mermaid` respectively. Matches the Phase 5.0 `kb_lint(wiki_dir=...)` pattern.
- `src/kb/query/rewriter.py` — `rewrite_query` rejects LLM preamble leaks by reusing `_LEAK_KEYWORD_RE` from `engine.py` (AC3). Patterns include "Sure! Here's…", "The standalone question is:", "Rewritten query:", etc. Previously leaked preambles flowed into BM25 tokenize + vector embed + synthesis prompt, silently degrading retrieval quality.
- `src/kb/query/engine.py` — `_compute_pagerank_scores(wiki_dir, *, preloaded_pages=None)` now accepts pre-loaded pages and threads them into `build_graph(pages=...)` (AC6). `search_pages` passes its already-loaded `pages` list, eliminating a second disk walk per query.
- `src/kb/query/hybrid.py` — `rrf_fusion` stores `(accumulated_score, merged_metadata)` tuples in the intermediate dict instead of shallow-copy result dicts (AC10). Defers dict materialization to sort time; preserves late-list-wins metadata merge (Phase 4.5 HIGH Q2).
- `src/kb/query/dedup.py` — `_dedup_by_text_similarity` skips the Jaccard threshold when comparing results of different `type` (AC11). Summaries quoting an entity's text no longer collapse the entity row under layer-2 similarity pruning.
- `src/kb/ingest/pipeline.py` — `_update_existing_page` normalizes `content.replace("\r\n", "\n")` after read (AC7) so CRLF-encoded frontmatter matches `_SOURCE_BLOCK_RE` (LF-only). Previously CRLF files fell through to a weak fallback, producing double `source:` keys that crashed the next frontmatter parse.
- `src/kb/ingest/pipeline.py` — `_process_item_batch` accepts `shared_seen: dict[str, str] | None = None` keyword-only (AC8). When provided, slug collisions are detected across entity+concept batches. Entity batch runs first → concept batch colliding on same slug is skipped with `pages_skipped` entry + WARNING per OQ5 entity-precedence.
- `src/kb/graph/builder.py` — `graph_stats(graph, *, include_centrality: bool = False)` (AC13). Default `False` skips `nx.betweenness_centrality` (O(V*E) at 5k-node scale dominated every `kb_stats` / `kb_lint` call). `bridge_nodes` returns `[]`, `bridge_nodes_status` returns `"skipped"`. NOT exposed via MCP per OQ11.
- `src/kb/utils/pages.py` — `load_purpose` decorated with `@functools.lru_cache(maxsize=4)` (AC14). Docstring documents the `load_purpose.cache_clear()` invalidation contract for tests that mutate `purpose.md` mid-run.
- `src/kb/utils/pages.py` — `load_all_pages` accepts keyword-only `return_errors: bool = False` (AC15). Default returns `list[dict]` (backward-compatible); `True` returns `{"pages": list[dict], "load_errors": int}` so callers can distinguish "fresh install" from "100 permission errors."

#### Docs

- `CHANGELOG.md` — this cycle-6 entry. Test count 1836 → 1868 (+32).
- `CLAUDE.md` — test count, file count, cycle-6 reference.
- `BACKLOG.md` — 15 resolved items deleted per BACKLOG lifecycle rule.

#### Security posture (cycle 6)

- **PR-introduced CVE diff:** 0 entries vs Step-2 baseline (`pip-audit` + Dependabot clean).
- **Class-A existing CVEs (unchanged from cycle 5):** `diskcache==5.6.3` CVE-2025-69872 — no upstream patch; accepted risk. `pip==24.3.1` toolchain CVEs — not runtime.
- **Threat-model mitigations:** all 15 AC rows grep-verified at Step 11. New trust boundary (process-level PageRank cache, `load_purpose` lru_cache) keyed on `wiki_dir.resolve()` path so multiple tmp wikis in one process do not collide.

#### Legacy test adaptations

- `tests/test_phase45_high_cycle2.py::TestQ4CentralityStatusMetadata::test_bridge_nodes_has_status` — updated to pass `include_centrality=True` (AC13 made it opt-in).
- `tests/test_v0913_phase394.py::TestKbGraphVizMaxNodes::test_max_nodes_clamped` — mock signature accepts new `wiki_dir` kwarg.
- `tests/test_v09_cycle5_fixes.py::test_cli_configures_logging_when_root_has_no_handlers` — calls `cli._setup_logging()` directly (Click group callback now requires context).

#### Stats

1868 tests across 130 test files; +32 tests vs cycle 5 redo baseline; 15 items across 14 source files on `feat/backlog-by-file-cycle6`.

---

### Phase 4.5 — Cycle 5 redo (hardening, 2026-04-18)

6 items across 6 files. Tests: 1821 → 1836 (+15). Cycle 5 shipped 14 items but shortcut the feature-dev pipeline (no Step 2 threat model artifact, no Step 5 decision gate doc, only 1 PR review round). This redo ran the full pipeline retroactively and surfaced concrete gaps the missing process would have caught.

#### Process artifacts (new)

- `docs/superpowers/decisions/2026-04-18-cycle5-redo-requirements.md` — Step 1 AC1-AC8.
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-threat-model.md` — Step 2 threat table + Step 11 verification checklist.
- `docs/superpowers/decisions/2026-04-18-cycle5-redo-design.md` — Step 5 Opus decision gate verdict: CONDITIONAL-APPROVE with 6 conditions.

#### Fixed

- `query/engine.py` + `query/citations.py` — **T1 citation-format symmetry.** API-mode synthesis prompt at line 733 said `[source: page_id]` while MCP-mode instructions at `mcp/core.py:208` said `[[page_id]]`. Asymmetric → API-mode answers produced zero extractable citations because `extract_citations`' regex only matched the legacy form. Fixed by coordinating both: prompt now instructs `[[page_id]]`; `_CITATION_PATTERN` widened with alternation to accept both legacy and canonical forms (backward compat preserved).
- `mcp/app.py` — **T3 page-id length single source of truth.** Local `_MAX_PAGE_ID_LEN=255` diverged from `config.MAX_PAGE_ID_LEN=200`. Removed the local constant; `_validate_page_id` now imports from config. Pre-change grep confirmed no existing page IDs exceed 200 chars.
- `lint/augment.py` — **Step 11 verify finding.** Third purpose callsite (`_build_proposer_prompt`) bypassed `wrap_purpose`, breaking the "every purpose interpolation goes through the sentinel" invariant. Now wraps via `wrap_purpose(purpose_text, max_chars=1000)`.
- `tests/test_v0913_phase394.py` — updated legacy negative-assert for T1b regex widening (nested `[source: [[X]]]` now extracts the inner wikilink correctly).

#### Added (tests)

- `tests/test_cycle5_hardening.py` — 15 tests covering: T1 prompt + regex coordination, T1 backward compat, T2 CJK entity boundary (pins Python `re` Unicode-aware `\b` behavior), T3 page-id length at boundary (200 accept, 201 reject), T4 wrap_purpose sentinel-forgery pinning (textual-only defense documented), T4 byte-exact newline preservation, T5 verdict + feedback `logger.warning` on corrupted UTF-8 via `caplog`, augment proposer sentinel wrapping, pytest integration marker smoke test.

#### Changed

- `utils/text.py` — one-line trust-model comment on `wrap_purpose`: *"Defense is textual-only: wiki/purpose.md is human-curated (trusted). The helper strips non-whitespace C0 controls and caps length, but does NOT escape an attacker-supplied `</kb_purpose>` closer inside the input — sentinel semantics are an LLM-trust boundary, not a hard parse."*

---

### Phase 4.5 — Backlog-by-file cycle 5 (2026-04-18)

14 items across 13 files. Tests: 1811 → 1820 (+9). 1-round PR review.

#### Added

- `utils/text.py` — `wrap_purpose(text, max_chars=4096)` helper: strips control characters, caps at 4096 chars, wraps in `<kb_purpose>` sentinel tags for safe injection in LLM prompts.
- `pyproject.toml` — registered `slow`, `network`, `integration`, `llm` pytest markers to eliminate `PytestUnknownMarkWarning`.

#### Changed

- `config.py` — added `VALID_SEVERITIES = ("error", "warning", "info")` and `VALID_VERDICT_TYPES` tuple; deleted orphaned `WIKI_CATEGORIES` constant (zero importers confirmed).
- `lint/verdicts.py` — migrated `VALID_SEVERITIES`, `VALID_VERDICT_TYPES`, `MAX_NOTES_LEN` to `kb.config`; re-exported for backward compat; widened `load_verdicts` except to `(json.JSONDecodeError, OSError, UnicodeDecodeError)`.
- `query/engine.py` — replaced raw purpose f-string injection with `wrap_purpose()` sentinel call.
- `ingest/extractors.py` — replaced raw purpose f-string injection with `wrap_purpose()` sentinel call.
- `mcp/core.py` — updated citation format in Claude Code mode instructions from `[source: page_id]` to `[[page_id]]` wikilink syntax; applied `yaml_escape(source_type)` in hint string.
- `utils/llm.py` — added `default_headers={"User-Agent": "llm-wiki-flywheel/<version>"}` to Anthropic client constructor.
- `cli.py` and `mcp_server.py` — added `logging.basicConfig` with handler guard to prevent duplicate log lines.

#### Fixed

- `ingest/pipeline.py` — `_extract_entity_context()` now uses `\b{name}\b` word-boundary regex instead of `name in string` substring match, preventing false matches (e.g., "Ray" matching "stray").
- `mcp/app.py` — `_validate_page_id()` now rejects page IDs containing any control character (`\x00`–`\x1f`, `\x7f`) with a clear error; fail-closed posture consistent with existing path-traversal guard.
- `tests/` — fixed midnight boundary flake in `test_basic_entry` (explicit `entry_date`); replaced false-positive-prone contradiction test vocabulary; corrected `content_lower` mock values to exclude frontmatter.

---

### Concurrency fix + docs tidy (PR #17, 2026-04-18)

3 source-file changes. Tests: 1810 → 1811 (+1). 2-round parallel Codex PR review (R1: 1 MAJOR-non-regression, 2 MINORs fixed; R2: pass).

#### Fixed

- `lint/verdicts.py` — `add_verdict` pre-existing concurrency flake (`test_concurrent_add_verdict_no_lost_writes`): added `_VERDICTS_WRITE_LOCK` (threading.Lock) as in-process write serializer. Root cause: Windows PID-liveness heuristic in `file_lock` could steal the lock from a live same-PID thread under heavy suite load, putting two threads in the critical section simultaneously → lost entries. Threads now queue via `_VERDICTS_WRITE_LOCK` before acquiring `file_lock`; lock order documented (`_VERDICTS_WRITE_LOCK → file_lock → _VERDICTS_CACHE_LOCK`); `save_verdicts` scope boundary documented.
- `capture.py` — `_normalize_for_scan` docstring: cost note now separately documents base64 scan bound `O(n/17)` (16-char minimum) and URL-decode scan bound `O(n/10)` (9-char minimum), both load-bearing on `CAPTURE_MAX_BYTES`. `_check_rate_limit` docstring: per-process scope and cross-process persistence path documented.

#### Added

- `tests/test_v0915_task06.py` — `test_concurrent_writes_trim_at_max_verdicts`: pre-fills store to `MAX_VERDICTS-3`, runs 5 concurrent `add_verdict` threads, asserts final count `≤ MAX_VERDICTS`. Previously the trim branch (`verdicts[-MAX_VERDICTS:]`) was never reached by the concurrency test (10 entries vs 10,000 cap).

#### Docs

- `BACKLOG.md` — cross-reference table added (was HTML comment); 20+ verified-shipped items deleted across Phase 4.5 HIGH and Phase 5 kb-capture sections; `load_verdicts` readers-without-lock item updated to note write-write race is now fixed (remaining: reader PermissionError on Windows mid-rename).
- `CHANGELOG.md` — split into active (2026-04-16+) and `CHANGELOG-history.md` archive (Phase 4.5 CRITICAL 2026-04-15 and earlier) for multi-LLM scannability.

---

### Phase 4.5 — Backlog-by-file cycle 4 (2026-04-17)

22 mechanical bug fixes across 16 source files (HIGH + MEDIUM + LOW). File-grouped commits, continuing cycles 1–3 cadence. Tests: 1754 → 1810 (+56).

**Pipeline:** requirements → threat model + CVE baseline → brainstorm → parallel R1 Opus + R2 Codex design review → Opus decision gate → Codex plan + gate → TDD impl → CI hard gate → security verify + CVE diff → docs → PR → 2-round PR review.

**Scope narrowed to 22 at design gate** (cycle 3 verify-before-design lesson applied up-front):

- **7 already shipped** (grep-confirmed): #4 source_type whitelist, #6 MAX_QUESTION_LEN + stale marker, #8 ambiguous page_id match, #9 title cap 500, #10 source_refs is_file, #21 frontmatter_missing_fence, #30 FRONTMATTER_RE
- **1 deferred** (too architecturally deep for mechanical cleanup): #3 `[source: X]` → `[[X]]` citation migration — requires atomic update of 15+ test callsites + `extract_citations()` + `engine.py` — tracked in [BACKLOG.md](BACKLOG.md) Phase 4.5

Test behavioural rewrites: `TestSortedWikilinkInjection` + `TestContradictionMetadataMigration` after PR R1 Sonnet flagged both as signature-only.

#### Fixed — Backlog-by-file cycle 4 (22 items)

- `mcp/core.py` — `_rel()` sweep on error-string `Path` interpolations; `kb_ingest` 'source file not found' no longer leaks absolute filesystem paths (item #1)
- `mcp/core.py` + `utils/text.py` — `_sanitize_conversation_context` strips `<prior_turn>` / `</prior_turn>` fences (case-insensitive, with optional attributes) AND fullwidth angle-bracket variants (U+FF1C / U+FF1E) limited to fence-match region AND control characters via `yaml_sanitize`, before passing context to the rewriter LLM. Prevents fence-escape prompt injection via attacker-controlled conversation context (item #2)
- `mcp/core.py` — `kb_ingest_content` and `kb_save_source` post-create OSError paths now return `Error[partial]: ...` string with `overwrite=true` retry hint + `logger.warning` for operator audit. Previous `except BaseException: ... raise` violated the MCP "tools return strings, never raise" contract (item #5)
- `mcp/browse.py` — `kb_read_page` caps response body at `QUERY_CONTEXT_MAX_CHARS` with explicit `[Truncated: N chars omitted]` footer. Prevents MCP transport DoS from a runaway wiki page whose append-only Evidence Trail grew unbounded (item #7)
- `mcp/quality.py` — `kb_affected_pages` tightened to `_validate_page_id(check_exists=True)`; a typo'd page_id now returns `Error: Page not found: ...` instead of silently reporting 'No pages are affected' (false-negative). Legacy `test_kb_affected_pages_no_affected` test updated in the same commit per cycle 3 `feedback_migration_breaks_negatives` memory (item #11)
- `lint/verdicts.py` — `add_verdict` caps per-issue `description` at `MAX_ISSUE_DESCRIPTION_LEN=4000` inside the library function. Prevents a direct-library caller passing `issues=[{'description': 1_000_000*'x'}] × 100` from inflating a single verdict entry to ~100MB and thrashing the mtime-keyed verdict cache (item #12)
- `mcp/app.py` — `_validate_page_id` rejects Windows reserved basenames cross-platform (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) AND enforces `len(page_id) <= 255`. Reject happens on basename stem (before first dot), so `CON.backup` also fails matching Windows CreateFile semantics. Rationale: cross-platform corpus portability — a wiki file named `NUL.md` created on Linux would brick the whole Windows sync path (item #13)
- `compile/compiler.py` + `mcp/health.py` — `kb_detect_drift` surfaces deleted raw sources as distinct 'source-deleted' category + companion 'Pages Referencing Deleted Sources' section. `detect_source_drift()` return dict gains `deleted_sources` + `deleted_affected_pages` keys. Previously the drift case most likely to corrupt lint fidelity (wiki page still cites a deleted source) was silently pruned from the manifest without surfacing (item #14)
- `query/rewriter.py` — `_should_rewrite` adds `_is_cjk_dominant` + universal short-query gate (`len(question.strip()) < 15`) so CJK follow-ups like `什么是RAG` / `它是什么` skip the scan-tier LLM rewrite call. Prior heuristic used `question.split()` which returns `[question]` for CJK (no whitespace separators), causing every CJK query to ALWAYS trigger rewrite (item #15)
- `query/engine.py` + `utils/text.py` — new `_WIKI_BM25_CACHE` mirrors cycle 3's `_RAW_BM25_CACHE`. Both keys now include `BM25_TOKENIZER_VERSION` so tokenizer-semantic changes (STOPWORDS prune, new sanitize) invalidate stale indexes without requiring a file touch (items #16 + #18 invalidation path)
- `query/dedup.py` — `_enforce_type_diversity` uses running quota (`tentative_kept * max_ratio` recomputed each iteration) instead of fixed cap based on input length. Ensures 'no type exceeds X%' contract holds regardless of input-to-output compression ratio from prior dedup layers (item #17)
- `utils/text.py` — STOPWORDS pruned by 8 overloaded quantifiers (`new`, `all`, `more`, `most`, `some`, `only`, `other`, `very`) that appear in legitimate technical entity names (All-Reduce, All-MiniLM, New Bing). `BM25_TOKENIZER_VERSION = 2` added as cache-key salt so cycle 4 deploys invalidate stale on-disk / in-memory BM25 indexes (item #18)
- `utils/text.py` — `yaml_sanitize` silently strips BOM (U+FEFF), LINE SEPARATOR (U+2028), PARAGRAPH SEPARATOR (U+2029). Common noise from Word / Google Docs / Obsidian pastes that corrupt YAML with no security benefit from rejection (item #19)
- `utils/wiki_log.py` — monthly rotation with ordinal collision. When `log.md` exceeds `LOG_SIZE_WARNING_BYTES` (500KB), append rotates to `log.YYYY-MM.md` (or `log.YYYY-MM.2.md`, `.3.md` on mid-month overflow). Rotation event logs at INFO before rename to preserve audit chain. Replaces the warn-only path that let `wiki/log.md` grow unbounded (item #20)
- `ingest/pipeline.py` — migrated contradiction-detection caller from list-returning `detect_contradictions` to `detect_contradictions_with_metadata` sibling. When `truncated=True`, pipeline now emits `logger.warning` naming the source_ref + checked/total counts so operators can detect coverage gaps. Legacy `detect_contradictions` signature preserved for non-pipeline callers (item #22)
- `graph/export.py` — `export_mermaid(graph=<Path>)` positional-form shim emits `DeprecationWarning` with v0.12.0 removal target. Behaviour preserved so no existing caller breaks this cycle (item #23)
- `query/bm25.py` — `BM25Index.__init__` precomputes `_postings: dict[str, list[int]]` inverted index; `score()` iterates only docs that contain a query term instead of walking every doc per term. ~25× speedup on sparse queries at 5k-page scale. Memory profile documented as ~150 MB (item #24)
- `compile/compiler.py` — `_template_hashes` filters by `VALID_SOURCE_TYPES` instead of just excluding tilde/dotfile prefixes. Prevents editor backup files (`article.yaml.bak`, `*.yaml.swp`) from entering the manifest and triggering a full re-ingest when they change (item #25)
- `.env.example` — added commented `CLAUDE_SCAN_MODEL` / `CLAUDE_WRITE_MODEL` / `CLAUDE_ORCHESTRATE_MODEL` env-override vars to close drift vs `config.py:65-69` + CLAUDE.md model tier table (item #26)
- `CLAUDE.md` — documented `query_wiki` return-dict `stale` + Phase 4.11 output-adapter `output_format` / `output_path` / `output_error` keys (item #27)
- `utils/pages.py` — `load_purpose` signature tightened: `wiki_dir` is now REQUIRED. Previous `wiki_dir: Path | None = None` fallback silently leaked production `WIKI_DIR` into tests that forgot to pass `tmp_wiki`. All current callers (`query/engine.py:653`, `ingest/extractors.py:335`) already pass explicit `wiki_dir`; `extract_from_source` gains a local default via `from kb.config import WIKI_DIR` for its own `wiki_dir=None` back-compat (item #28)
- `ingest/pipeline.py` — retroactive wikilink injection loop sorts `(pid, title)` pairs descending by title length before iterating `inject_wikilinks`. Prevents short titles like `RAG` from swallowing body text that longer entities like `Retrieval-Augmented Generation` should own; tie-break on pid for deterministic ordering (item #29)

#### Test-backfill (already-shipped items #6, #8, #9, #10)

- `tests/test_backlog_by_file_cycle4.py::TestStaleMarkerInSearch` — shipped `[STALE]` surfacing in `kb_search` output
- `tests/test_backlog_by_file_cycle4.py::TestAmbiguousPageId` — shipped ambiguous case-insensitive match rejection in `kb_read_page` (NTFS-safe via mocked glob since NTFS can't hold two case-variants simultaneously)
- `tests/test_backlog_by_file_cycle4.py::TestTitleLengthCap` — shipped 500-char title cap in `kb_create_page`
- `tests/test_backlog_by_file_cycle4.py::TestSourceRefsIsFile` — shipped `is_file()` check on `source_refs` in `kb_create_page`

#### Security posture (cycle 4)

- **PR-introduced CVE diff:** 0 entries vs Step-2 baseline (`pip-audit` clean).
- **Class-A existing CVEs patched at Step 12.5:** `langsmith` 0.7.25 → 0.7.32 (GHSA-rr7j-v2q5-chgv resolved), `python-multipart` 0.0.22 → 0.0.26 (CVE-2026-40347 resolved). `requirements.txt` already pinned the patched versions — cycle 4 only synced the stale local venv.
- **Accepted risk:** `diskcache==5.6.3` CVE-2025-69872 — no patched release published; tracked in BACKLOG for next-cycle watchlist. `pip==24.3.1` toolchain CVEs — not runtime code.

#### Stats

1810 tests across 127 test files; +56 tests vs cycle 3 baseline (1754); 22 items across 16 source files on `feat/backlog-by-file-cycle4`.

### Phase 4.5 — Backlog-by-file cycle 3 (2026-04-17)

24 mechanical bug fixes across 16 source files (HIGH + MEDIUM + LOW) plus 2 security-verify follow-ups. One commit per file; full feature-dev pipeline (threat model → parallel design review → Opus decision gate → Codex plan + gate → TDD impl → CI hard gate → Codex security verify → docs → PR → review rounds) gated via subagents. Test count 1727 → 1754 (+27).

During design review, R1 Opus flagged that 9 of the original 30-item design-spec entries were ALREADY SHIPPED in cycles 1 and 2 (wiki_log is_file, markdown code-block strip, load_feedback widen, reliability trust-recompute, rewriter WH-question, kb_search stale marker, source_type validation, kb_ingest stat pre-check, rewrite_query leak-prefix). Decision-gate dropped those items and rescoped to 24 genuinely-open items plus 2 security-verify closures. This is the first cycle where "verify-before-design" changed scope midflight and the lesson is recorded in the self-review.

#### Fixed — Backlog-by-file cycle 3 (24 items + 2 security-verify)

- `utils/llm.py` `_make_api_call` — branch `anthropic.BadRequestError` / `AuthenticationError` / `PermissionDeniedError` BEFORE generic `APIStatusError`; raise non-retryable `LLMError(kind="invalid_request"|"auth"|"permission")`. Caller-bug 4xx classes no longer consume retries. `LLMError` gains a typed `kind` attribute with documented taxonomy so callers can programmatically recover without string-matching (H1)
- `utils/llm.py` `_make_api_call` — drop dead `last_error = e` on non-retryable `APIStatusError` branch (raise-immediately path has no consumer) (L1)
- `utils/io.py` `file_lock` — split over-broad `except (FileExistsError, PermissionError)` into separate branches. `FileExistsError` continues retry / stale-lock handling; `PermissionError` raises `OSError(f"Cannot create lock at {lock_path}: {exc}")` immediately instead of spinning to deadline and then attempting to "steal" a lock the operator cannot create (H2)
- `feedback/store.py` `add_feedback_entry` — `unicodedata.normalize("NFC", pid)` on every cited page id before dedup/`page_scores` mutation. Pages whose IDs differ only in NFC vs NFD form (macOS HFS+ filenames vs everywhere-else) now collapse into one trust-score entry instead of accumulating separate (useful, wrong, incomplete, trust) tuples (M3)
- `feedback/reliability.py` `compute_trust_scores` — docstring documents the Bayesian asymptote: wrong-weight is ~1.5× at small N, converging to 2× at high N. Prevents future tests from asserting literal 2× at small N (L5)
- `query/embeddings.py` `VectorIndex.query` — cache stored dim via `PRAGMA table_info(vec_pages)` on first query; on dim mismatch log ONE warning and return `[]` without raising. Empty DB / missing-table returns `[]` silently (not a mismatch). Prevents silent hybrid→BM25-only degradation after a model swap without rebuild (H7)
- `query/embeddings.py` `get_vector_index` — add `_index_cache_lock` with double-checked locking matching `_model_lock` + `_rebuild_lock` pattern. Concurrent FastMCP worker threads observe a single shared `VectorIndex` instance (H8)
- `query/embeddings.py` `VectorIndex.build` — validate `dim` is `int` in `[1, 4096]` before f-string interpolation into `CREATE VIRTUAL TABLE vec_pages USING vec0(embedding float[{dim}])`. Hardens SQL path against bug-introduced non-int or oversized dim from future chunk-indexing callers (L2)
- `query/engine.py` `_build_query_context` — prefix page header with `[STALE]` marker when `page["stale"]` is True. Surfaces staleness INSIDE the synthesis prompt so the LLM can caveat or demote stale facts (H9)
- `query/engine.py` `query_wiki` — add `stale_citations: list[str]` to return dict, derived from intersection of `context_pages` and `matching_pages` whose stale flag is True. MCP callers can expose staleness without parsing prompt text. Additive only — all pre-cycle-3 keys preserved (H9)
- `query/engine.py` `vector_search` closure — narrow `except Exception` to `(ImportError, sqlite3.OperationalError, OSError, ValueError)`. AttributeError/KeyError from future refactors now surface instead of silently degrading hybrid → BM25-only (H11)
- `query/engine.py` `query_wiki` — add `search_mode: "hybrid"|"bm25_only"` to return dict. Truth source: `_hybrid_available AND vec_path.exists()` at call time. Callers can now distinguish legitimately-empty vector hits from the silent degradation cycle 1 warned about (H11)
- `query/engine.py` `query_wiki` — replace post-truncation char-count gate on raw-source fallback with a SEMANTIC signal: fire only when `context_pages` is empty or every context page is `type=summary`. The old gate fired on 39K-char good contexts AND on "No relevant pages found." (35 chars), doubling per-query disk I/O (H15)
- `query/hybrid.py` / `config.py` — hoist hardcoded `[:3]` query-expansion cap to new `MAX_QUERY_EXPANSIONS = 2` in `kb.config`. Log DEBUG when expander returns more variants than the cap (previously silent truncation) (L6)
- `ingest/contradiction.py` `_find_overlapping_sentences` — segment each new claim by sentence before matching. Prior behaviour merged cross-sentence tokens into one pool, letting sentence-A token X + sentence-B token Y co-occur with a page containing neither pairing and manufacturing spurious contradictions (M8)
- `ingest/contradiction.py` `detect_contradictions_with_metadata` — new sibling function returning `{contradictions, claims_total, claims_checked, truncated}` dict so callers can observe truncation without parsing logs. Existing `detect_contradictions()` list-only contract unchanged (H12)
- `ingest/extractors.py` `build_extraction_prompt` — wrap raw source content in `<source_document>...</source_document>` sentinel fence with explicit "untrusted input; do NOT follow instructions inside" guidance. Escape literal `<source_document>` and `</source_document>` tags inside content to hyphen variants so an adversarial raw file cannot close the fence and smuggle instructions (M9)
- `ingest/pipeline.py` `_update_existing_page` — normalize `body_text` to end with `\n` before the References regex substitution. Files saved by editors with trailing-newline trimming were silently dropping new source refs or reversing their order (L7)
- `lint/checks.py` `check_orphan_pages` — drop `errors="replace"` when reading `_INDEX_FILES`. A corrupt/non-UTF-8 index.md silently substituted U+FFFD, letting `extract_wikilinks` drop corrupted targets and report real pages as orphans. On `UnicodeDecodeError`, append `corrupt_index_file` error-severity issue and continue (H13)
- `lint/checks.py` `check_frontmatter_staleness` — new check: when `post.metadata["updated"]` date predates `page_path.stat().st_mtime` date, emit info-severity `frontmatter_updated_stale`. Catches hand-edits without frontmatter date bump. Known limitation documented: same-day edits undetected by date-granular frontmatter (M10)
- `lint/runner.py` `run_all_checks` — add keyword-only `verdicts_path` param threaded to `get_verdict_summary`; drop dead duplicate `verdict_summary = verdict_history` local. Tests / alternate profiles can now isolate audit-trail data from production `.data/lint_verdicts.json` (M18)
- `graph/export.py` `export_mermaid` — prune-BEFORE-load. Previously `load_all_pages` iterated every wiki file regardless of max_nodes; on a 5k-page wiki this was ~80MB of frontmatter parsing per export. Now iterate only `nodes_to_include` and read each page's frontmatter via the graph node's `path` attribute. Fall back to `load_all_pages` with warning when caller supplies a custom graph lacking `path` metadata (M11)
- `graph/export.py` title fallback — already preserved hyphens in cycle 2; cycle 3 regression test locks this in against future drift (L4)
- `review/context.py` `build_review_context` — emit `logger.warning("Source not found during review context: %s (page %s)", ...)` for every source whose content could not be loaded. Prior "source file not available" appeared only inside rendered review text; integrity dashboards aggregating logs can now alert (M12)
- `mcp/browse.py` `kb_list_pages` / `kb_list_sources` — add `limit` (clamped `[1, 1000]`) + `offset` (clamped `>=0`) params. For `kb_list_sources`, flatten per-subdir entries after the G1 per-subdir cap so pagination is deterministic. Preserve legacy `Total: N page(s)` line alongside the new `Showing Y of N (offset=X, limit=L)` pagination header for backcompat with existing test assertions (M13)
- `mcp/health.py` `kb_graph_viz` — reject `max_nodes=0` with explicit Error string. Docstring previously advertised 0 as "all nodes" but code silently remapped to 30, returning a 30-node slice with no signal to agents following the docstring (M16)
- `utils/text.py` `truncate` — head+tail smart truncation with `"...N chars elided..."` marker. Prior head-only slice destroyed diagnostic tails in tracebacks (exception class in head, failing frame in tail). Default limit bumped 500 → 600 (M17)
- `cli.py` `_truncate` — delegate to `kb.utils.text.truncate` so CLI errors inherit the new head+tail behaviour. Default limit aligned at 600 (M17 security-verify follow-up)
- `mcp/browse.py` `kb_list_pages` / `kb_list_sources` — wrap `int(limit)` / `int(offset)` coercion in `try/except (TypeError, ValueError)` returning an Error string; malformed MCP input (e.g. `limit="x"`) no longer raises through the FastMCP framework boundary (MCP contract: tools never raise) (Security-verify follow-up)

#### Changed

- `LLMError` gains a keyword-only `kind` attribute (default `None`); documented taxonomy: `invalid_request` / `auth` / `permission` / `status_error`. Existing `raise LLMError(msg) from e` callers unchanged.
- `query_wiki` result dict gains `stale_citations: list[str]` and `search_mode: "hybrid"|"bm25_only"` as additive keys — no existing key was removed or renamed.
- `kb_list_pages` / `kb_list_sources` MCP tools gain `limit`/`offset` kwargs with documented defaults.
- `rrf_fusion` still merges metadata on collision (cycle 1 Q2 preserved); `MAX_QUERY_EXPANSIONS` constant replaces hardcoded `[:3]` slice.

#### Stats

1754 tests across 126 test files; +27 tests vs cycle 2 baseline (1727); 24 items across 16 source files + 2 security-verify follow-ups landed as 20 commits on `feat/backlog-by-file-cycle3`.

### Phase 4.5 — Backlog-by-file cycle 2 (2026-04-17)

30 mechanical bug fixes across 19 files (HIGH + MEDIUM + LOW) grouped by file, cycle-1 profile. One commit per file; full pipeline (threat model → design gate → plan gate → implementation → regression tests → security verification) gated end-to-end via subagents.

#### Fixed — Backlog-by-file cycle 2 (30 items)

- `utils/hashing.py` `content_hash` / `hash_bytes` — normalize CRLF / lone CR to LF before hashing so Windows clones with `core.autocrlf=true` hash the same as POSIX; prevents full corpus re-ingest on first compile (LOW)
- `utils/markdown.py` `_strip_code_spans_and_fences` — fast-path `startswith("---")` before running `FRONTMATTER_RE.match`; saves regex work for every page without frontmatter in `build_graph` + `load_all_pages` hot paths (MED R2)
- `utils/wiki_log.py` `append_wiki_log` — zero-width-space-escapes leading `#`/`-`/`>`/`!` and `[[...]]` wikilinks in operation + message; audit entries no longer render as active headings, lists, callouts, or clickable links when an ingested source contains markdown markup (MED R4 #8 + R5 #9 retained + LF `newline="\n"` #29)
- `utils/io.py` `file_lock` — sets `acquired=True` only AFTER `os.write` returns successfully; cleanup branch unlinks the lock file if `os.write` fails so the next waiter does not encounter an empty-content lock that the RAISE-on-unparseable policy rejects forever (LOW R6 #1 + PR review R3 MAJOR regression fix); ASCII-decodes lock PID and RAISES `OSError` on decode/int-parse failure instead of silently stealing the lock; `_purge_legacy_locks()` now runs LAZILY on first `file_lock` acquisition rather than at module import (PR review R1 MAJOR) (MED R3 #2)
- `utils/io.py` `atomic_json_write` / `atomic_text_write` — `f.flush() + os.fsync()` before `Path.replace` to prevent half-written files from atomically replacing a good file on crash (MED R5 #3); tempfile cleanup failures now log WARNING instead of silent swallow, without masking the original exception (MED R5 #4)
- `utils/llm.py` `call_llm_json` — collects ALL `tool_use` blocks and raises listing every block name when Claude returns multiple; prior code silently discarded all but the first (HIGH R4 #5)
- `utils/llm.py` `_backoff_delay` — applies 0.5-1.5× jitter per attempt then clamps to `RETRY_MAX_DELAY`; prevents thundering-herd retries when two MCP processes hit 429 simultaneously. Pre-existing `test_llm.py::test_call_llm_exponential_backoff` + `test_backoff_delay_values` updated to assert jittered window instead of exact-value equality (MED R5 #6)
- `utils/llm.py` `_make_api_call` — `LLMError` truncates `e.message` to ≤500 chars via shared `kb.utils.text.truncate` helper; preserves exception class name, model ID, and `status_code` verbatim; prevents Anthropic error bodies that echo full prompts from leaking into logs. Truncation applies to BOTH the non-retryable branch and the retry-exhausted branch (Step 11 security verify gap fix) (MED R4 #7)
- `utils/text.py` `truncate` — moved from `kb.cli._truncate` so utility modules (`llm`, `wiki_log`, etc.) no longer import downward into the CLI layer; eliminates latent circular-import risk on the LLM error path (PR review R1 MAJOR)
- `utils/io.py` `file_lock` PID liveness — Windows-specific: any `OSError` from `os.kill(pid, 0)` treats the PID as unreachable and steals (Windows `os.kill` raises generic `OSError` on nonexistent PIDs). POSIX: only `ProcessLookupError` steals; non-`ProcessLookupError` `OSError` (typically EPERM) correctly raises `TimeoutError` to avoid stealing a live lock held by another user (PR review R1 MAJOR)
- `graph/export.py` `export_mermaid` — tie-break switched from `heapq.nlargest(key=(x[1], x[0]))` (ID DESC on ties) to `sorted(key=(-degree, id))[:max_nodes]` so equal-degree nodes are ordered `id ASC` per spec (PR review R1 MAJOR #27)
- `ingest/evidence.py` `build_evidence_entry` vs `format_evidence_entry` — split restored: `build_*` stores byte-clean raw `source_ref`/`action`; `format_*(date_str, source, summary)` (RENDER path, original positional contract preserved per PR review R3 MAJOR) backtick-wraps pipes; `append_evidence_trail` calls `format_*` so stored entries remain backward-compatible
- `query/engine.py` `query_wiki` — `normalized_question = re.sub(r"\s+", " ", question)` is the SINGLE source of truth; `rewrite_query` receives the normalized form, leak-fallback reverts to normalized (not raw), so item 12's whitespace collapse is no longer silently undone on the rewrite path (PR review R1 MAJOR)
- `ingest/evidence.py` `format_evidence_entry` — backtick-wraps `source`/`summary` when either contains `|`; pipe-delimited parsers no longer misalign on a legitimate pipe. `build_evidence_entry` stays byte-for-byte clean; `append_evidence_trail` now writes via `format_evidence_entry` (LOW R4 #28 + PR review R1 MAJOR restored after R3 positional review)
- `compile/linker.py` `inject_wikilinks` — single `_FRONTMATTER_RE.match` call per page; body-check and split share the match result, halving regex cost for N-titles-per-ingest (MED R4 #26)
- `feedback/store.py` `load_feedback` — one-shot schema migration backfills legacy `useful` / `wrong` / `incomplete` count keys once at load; `trust` is NOT backfilled so `get_flagged_pages` can recompute it from counts (cycle-1 Q2 semantics); per-write `setdefault` loop removed from `add_feedback_entry` (LOW R4 #24)
- `feedback/reliability.py` `get_coverage_gaps` — dedup now keeps entry with LONGEST notes (ties broken by newest timestamp); prior first-occurrence policy suppressed later, more-specific notes (MED R2 #25)
- `evolve/analyzer.py` `find_connection_opportunities` — strips `[[wikilink]]` markup + drops purely-numeric tokens before tokenising; prior behaviour flagged pages sharing year/version numbers or wikilink slug fragments as false "connection opportunities" (MED R2+R4 #18, #19)
- `evolve/analyzer.py` `generate_evolution_report` — narrowed over-broad `(ImportError, AttributeError, OSError, ValueError)` catch around `get_flagged_pages` to `(KeyError, TypeError)`; OSError on feedback read now propagates so disk faults surface instead of producing a silent empty flagged-list (MED R4 #20)
- `lint/trends.py` `compute_verdict_trends` — now accepts either a path or a list of verdict dicts; surfaces `parse_failures` counter in the returned dict so malformed-timestamp counts no longer silently widen the gap between `total` and `sum(periods)` (MED R5 #21)
- `lint/trends.py` `_parse_timestamp` — dropped vestigial `ValueError` fallback for date-only strings; project pins Python 3.12+ where `datetime.fromisoformat` parses both forms natively (LOW R4 #22)
- `lint/semantic.py` `_group_by_term_overlap` — already imports shared `FRONTMATTER_RE` from `kb.utils.markdown`; cycle-2 regression test locks the import in place to prevent re-divergence in future edits (LOW R4 #23)
- `graph/export.py` `export_mermaid` — auto-prune key bumped from `lambda x: x[1]` to `lambda x: (x[1], x[0])` so equal-degree nodes are selected deterministically (degree desc, id asc); prevents the committed architecture PNG from churning between runs (MED R2 #27)
- `query/citations.py` `extract_citations` — dedups citations by `(type, path)` preserving the first occurrence's context (LOW R1 #17)
- `query/hybrid.py` `hybrid_search` — wraps `bm25_fn()` and `vector_fn()` in try/except returning `[]`; structured WARN log reports backend name, exception class, exception text, and `len(question.split())` as token proxy; prevents a corrupt page dict or sqlite-vec schema drift from crashing the MCP tool (HIGH R4 #16)
- `query/dedup.py` `dedup_results` — optional `max_results: int | None = None` clamp applied AFTER all four dedup layers (MED R4 #15); layer 2 falls back to lowercasing `content` when `content_lower` is missing so MCP-provided citations and future chunk rows participate in similarity dedup (MED R4 #30)
- `query/rewriter.py` `_should_rewrite` — cycle-1 WH-question + proper-noun skip is now locked in by a cycle-2 regression test (LOW R4 #14 retained)
- `query/engine.py` `query_wiki` — `effective_question` uses `re.sub(r"\s+", " ", …).strip()` so ALL Unicode whitespace (tabs, vertical tab, U+2028, U+2029, non-breaking space, …) collapses to a single space before search; prior code only replaced `\n`/`\r` in the synthesis prompt (LOW R4 #12)
- `query/engine.py` `search_raw_sources` — `path.stat().st_size > RAW_SOURCE_MAX_BYTES` pre-check skips oversized files with an INFO log BEFORE `read_text`, so a 10 MB scraped article cannot balloon the in-memory corpus; YAML frontmatter stripped via shared `FRONTMATTER_RE` before tokenizing so title/tags no longer mis-rank results (MED R4 #13)
- `config.py` — new `RAW_SOURCE_MAX_BYTES = 2_097_152` (2 MiB) paired with `CAPTURE_MAX_BYTES`; single source of truth for the raw-source size cap (MED R4 #13)

### Phase 4.5 — Backlog-by-file cycle 1 (2026-04-17)

38 mechanical bug fixes across 18 files (HIGH + MEDIUM + LOW) grouped by file instead of by severity. One commit per file; full pipeline (threat model → design review → plan gate → implementation → regression tests → security verification) gated end-to-end via subagents.

#### Fixed — Backlog-by-file cycle 1 (38 items)

- `ingest/pipeline.py` `ingest_source` — accepts `raw_dir=None` kwarg threaded to `detect_source_type` + `make_source_ref` so custom-project augment runs can honor caller raw/ (three-round HIGH)
- `ingest/pipeline.py` `ingest_source` — enforces `SUPPORTED_SOURCE_EXTENSIONS` inside the library, not only at the MCP wrapper; suffix-less files (README, LICENSE) now rejected (Phase 4.5 MED)
- `ingest/pipeline.py` contradiction detection — narrowed bare `except Exception` to `(KeyError, TypeError, ValueError, re.error)`; warnings promoted from DEBUG (Phase 4.5 R4 HIGH)
- `lint/augment.py` `run_augment` — passes `raw_dir` to `ingest_source`; adds `data_dir` kwarg derived from `wiki_dir.parent / .data` on custom-wiki runs; rejects `max_gaps < 1`; re-runs `_url_is_allowed` on reviewed proposal URLs before `RateLimiter.acquire` (three-round HIGH + 3× MED)
- `lint/_augment_manifest.py` `Manifest` — `start` / `resume` accept `data_dir` so custom-project runs do not leak manifests into the main repo's `.data/` (three-round MED)
- `lint/_augment_rate.py` `RateLimiter` — accepts `data_dir` kwarg; rate state follows the supplied project (three-round MED)
- `cli.py` / `mcp/health.py` — both reject `max_gaps < 1` at the public surface (three-round MED)
- `capture.py` `_render_markdown` — removed dead `slug: str` param + 6 test call sites (R3 MED)
- `capture.py` `_CAPTURE_SCHEMA` — `body.maxLength=2000` caps LLM return size (LOW)
- `capture.py` `capture_items` / `_write_item_files` — `captures_dir=None` kwarg threaded to all three `CAPTURES_DIR` references (R2 MED + R3 MED)
- `capture.py` `_CAPTURE_SECRET_PATTERNS` — env-var regex matches suffix variants (`ANTHROPIC_API_KEY`, `DJANGO_SECRET_KEY`, `GH_TOKEN`, `ACCESS_KEY`) + optional shell `export ` prefix; requires `\S{8,}` value to reject `TOKEN_EXPIRY=3600` (MED + 2× LOW)
- `capture.py` `_path_within_captures` — accepts `base_dir=None` and uses the module-level `_CAPTURES_DIR_RESOLVED` cache (MED)
- `capture.py` Authorization regex — split into Basic + Bearer patterns; opaque OAuth/Azure/GCP Bearer tokens (16+ chars) now detected (LOW)
- `ingest/extractors.py` `extract_from_source` — deepcopy schema from the `lru_cache` before handing to the SDK so mutation in one call cannot poison the next (Phase 4.5 MED)
- `ingest/extractors.py` `build_extraction_prompt` — caps `purpose` interpolation at 4096 chars (R4 HIGH — cap-only subset; sentinel markup deferred)
- `ingest/contradiction.py` `_extract_significant_tokens` — two-pass tokenization preserves single-char / acronym language names (C, R, C#, C++, F#, Go, .NET) (R4 HIGH)
- `mcp/quality.py` `kb_create_page` — O_EXCL exclusive-create replaces `exists()` + `atomic_text_write`; source_refs existence check; title capped at 500 chars + control-char stripped (Phase 4.5 MED + 2× LOW)
- `mcp/quality.py` `kb_refine_page` — caps `revision_notes` at `MAX_NOTES_LEN` and `page_id` at 200 chars before path construction / log writes (Phase 4.5 MED)
- `mcp/browse.py` `kb_list_sources` — `os.scandir` + per-subdir cap 500 + total response size cap 64KB; skips dotfiles (Phase 4.5 MED)
- `mcp/browse.py` `kb_search` — rejects queries over `MAX_QUESTION_LEN`; surfaces `[STALE]` alongside score (R4 HIGH)
- `mcp/browse.py` `kb_read_page` — returns ambiguity error when case-insensitive fallback matches >1 file (R4 LOW)
- `mcp/core.py` `kb_ingest` — `stat().st_size` pre-check against `MAX_INGEST_CONTENT_CHARS*4` bytes prevents OOM read before truncate; validates `source_type in SOURCE_TYPE_DIRS` (Phase 4.5 HIGH + R4 HIGH)
- `query/engine.py` `_flag_stale_results` — UTC-aware `datetime.fromtimestamp(..., tz=UTC).date()` eliminates local-TZ/naive mismatch (Phase 4.5 MED)
- `query/engine.py` `search_raw_sources` — BM25 index cached keyed on `(raw_dir, file_count, max_mtime_ns)` (Phase 4.5 MED)
- `query/engine.py` `query_wiki` — rejects rewrite output containing newlines or `Sure|Here|Rewritten|Standalone|Query:` preambles; falls back to original (R4 HIGH)
- `query/rewriter.py` `rewrite_query` — absolute `MAX_REWRITE_CHARS=500` ceiling + floor `max(3*len, 120)`; replaces the 3×-only bound (Phase 4.5 MED)
- `query/rewriter.py` `_should_rewrite` — skips WH-questions ending in `?` that contain a proper-noun / acronym body (R4 LOW)
- `query/dedup.py` `_dedup_by_text_similarity` — caches `_content_tokens` per kept result; eliminates O(n·k) re-tokenization (Phase 4.5 MED)
- `lint/verdicts.py` `load_verdicts` — `(mtime_ns, size)` cache with explicit `save_verdicts` invalidation (Phase 4.5 MED)
- `lint/checks.py` `check_source_coverage` — short-circuits on pages missing opening frontmatter fence, emitting a frontmatter issue (R4 HIGH)
- `utils/markdown.py` `extract_wikilinks` — `_strip_code_spans_and_fences` helper strips fenced blocks, inline code, and frontmatter before pattern matching (R4 HIGH)
- `feedback/store.py` `load_feedback` — widened except to `(JSONDecodeError, OSError, UnicodeDecodeError)` for full corruption-recovery (R5 HIGH)
- `feedback/reliability.py` `get_flagged_pages` — recomputes trust from raw counts when `trust` key missing instead of defaulting to 0.5 (R4 HIGH)
- `review/refiner.py` `refine_page` — imports shared `FRONTMATTER_RE`; caps `revision_notes` at `MAX_NOTES_LEN` before log writes (R4 HIGH + R4 LOW)
- `utils/wiki_log.py` `append_wiki_log` — verifies `log_path.is_file()` so directory / symlink / FIFO targets raise a clear `OSError` instead of a misleading second error from `open("a")` (R5 HIGH)

#### Added — regression coverage

- `tests/test_backlog_by_file_cycle1.py` — 30 parameter / behaviour / regex / path fixtures covering the batch above

#### Decisions

- `docs/superpowers/decisions/2026-04-17-backlog-by-file-cycle1-design.md` — batch-size, deferral, and dependency ordering rationales
- `docs/superpowers/specs/2026-04-17-backlog-by-file-cycle1-design.md` — file-grouped scope + test expectations per item

#### PR review — 3 rounds (Opus + Sonnet + 3× Codex)

Round 1 (Opus + Sonnet parallel, Codex round 1): 11 findings addressed
in commit `fix(pr-review-r1)`:
- `lint/checks.py` O1 issue key drift `type` → `check: frontmatter_missing_fence`
- `utils/wiki_log.py` S1 symlink rejection via `lstat` + `S_ISLNK`
- `lint/verdicts.py` M1 cache thread-safety + return-copy + invalidate-before-save
- `mcp/quality.py` F1 O_EXCL + fdopen in one try-block (signal-race fix)
- `mcp/core.py` H1 size cap aligned to `QUERY_CONTEXT_MAX_CHARS*4`
- `query/engine.py` I3 removed `_LEAK_PREFIX_RE` (dropped legit "RAG:…" rewrites); added raw BM25 cache lock
- `capture.py` A4 env-var regex accepts quoted-with-spaces values
- `feedback/store.py` Q1 re-raises `PermissionError` instead of swallowing
- Test updates: D1 exercises `extract_from_source` with SDK-mutating stub; A3 uses public `capture_items`; S1 symlink regression; I3 legit "RAG:" preserved; A4 quoted-secret; Q1 EACCES propagation

Round 2 (Codex round 2): 4 MAJORS addressed in commit `fix(pr-review-r2)`:
- `query/engine.py` I3 removed bare "sure"/"okay"/"alright" over-match
- `query/engine.py` I2 rebuild outside lock + double-check under lock
- `ingest/contradiction.py` E1 short-token whitelist {c,r,go,f,d}
- `BACKLOG.md` Phase 4.5 MEDIUM items collapsed to summary pointer

Round 3 (Codex round 3): **APPROVE** — no blocker-severity regressions. One pre-existing scope issue noted (`>= 2` overlap threshold in contradiction detection makes single-token language-name contradictions invisible; predates this PR).

Post-release audit fixes for Phase 4 v0.10.0 — all HIGH (23) + MEDIUM (~30) + LOW (~30) items.
Plus Phase 4.1 sweep: 16 LOW/NIT backlog items applied directly. One test expectation
(`TestSymlinkGuard.test_symlink_outside_project_root_refuses_import`) was updated to match
production (`RuntimeError` rather than `AssertionError`, following the assert → raise
migration that shipped in the original kb_capture PR); no new tests added, no test semantics changed.

Plus Phase 4.11: `kb_query --format={markdown|marp|html|chart|jupyter}` output adapters.

Plus Phase 5.0: `kb_lint --augment` reactive gap-fill (modules `kb.lint.fetcher` / `kb.lint.augment` / `kb.lint._augment_manifest` / `kb.lint._augment_rate`; CLI + MCP flags; three-gate propose → execute → auto-ingest). Plus three bundled fixes: `kb_lint` MCP signature drift (CLAUDE.md:245 `--fix` claim), `kb_lint` MCP `wiki_dir` plumbing, `_AUTOGEN_PREFIXES` consolidation, and npm / Postgres DSN secret patterns.

Plus backlog cleanup: removed 3 stale assert→RuntimeError items from Phase 5 kb-capture pre-merge section (all fixed and shipped in Phase 5 kb-capture release).

Plus Phase 4.5 CRITICAL cycle 1: 16 CRITICAL items from the post-v0.10.0 multi-agent audit, fixed across 4 themed commits (test-isolation, contract-consistency, data-integrity, error-chain) via an automated feature-dev pipeline with Opus decision gates + adversarial gates + branch-level Codex + security review.

Plus Phase 4.5 CRITICAL cycle 1 docs-sync (items 4 + 5): version-string alignment across `pyproject.toml` / `__init__.py` / README badge, CLAUDE.md stats updated to current counts (1552 tests / 119 test files / 67 py files / 26 MCP tools), and new `scripts/verify_docs.py` pre-push check. Also 5 new R6 BACKLOG entries from the 2-round post-PR review deferrals.

Plus Phase 4.5 HIGH cycle 1: 22 HIGH-severity items from the post-v0.10.0 multi-agent audit, fixed across 4 themed commits (wiki_dir plumbing, cross-process RMW locking, prompt-injection sanitization + security, error-handling + vector-index lifecycle) via the automated feature-dev pipeline with Opus design + plan decision gates.

### Phase 4.5 — HIGH cycle 2 (2026-04-17)

22 HIGH-severity bugs across 5 themes (Query, Lint, Data Integrity, Performance, DRY).

#### Fixed — Phase 4.5 HIGH cycle 2 (22 items)

- `utils/markdown.py` `FRONTMATTER_RE` — bounded to 10KB to prevent catastrophic backtracking on malformed pages (D3)
- `review/refiner.py` frontmatter guard — require YAML key:value between fences; horizontal rules (`---`) no longer rejected (D1)
- `review/refiner.py` — strip UTF-8 BOM before frontmatter parsing (D2)
- `evolve/analyzer.py` — replaced inlined frontmatter regex with shared `FRONTMATTER_RE` import (P3)
- `lint/semantic.py` `_group_by_term_overlap` — fixed `group(1)` → `group(2)` so consistency checking tokenizes body text, not YAML keys (L7)
- `ingest/extractors.py` — removed duplicate `VALID_SOURCE_TYPES`; uses `SOURCE_TYPE_DIRS` directly (C1)
- `compile/compiler.py` — imports `SOURCE_TYPE_DIRS` from config instead of extractors (C1)
- `lint/checks.py` `check_cycles` — bounded `nx.simple_cycles` to 100 via `itertools.islice` (L1)
- `lint/semantic.py` `_group_by_term_overlap` — replaced O(n²) pairwise loop with inverted postings index; removed 500-page wall (L2)
- `graph/builder.py` `build_graph` — accepts optional `pages: list[dict]` param to avoid redundant disk reads (L3)
- `lint/trends.py` `_parse_timestamp` — all timestamps now UTC-aware; date-only strings treated as midnight UTC (L4)
- `lint/trends.py` `compute_verdict_trends` — parse failures excluded from both `overall` and `period_buckets` (L5)
- `lint/semantic.py` `_render_sources` — per-source minimum budget floor of 500 chars; large wiki pages no longer starve source context (L6)
- `feedback/store.py` — eviction changed from activity-count to timestamp-based; oldest entries evicted first (D4)
- `ingest/contradiction.py` — claim truncation promoted from `logger.debug` to `logger.warning` with unchecked count (D5)
- `ingest/pipeline.py` — contradiction detection excludes pages created in current ingest to prevent noisy self-comparison (D6)
- `query/engine.py` `_build_query_context` — tier 1 budget enforced per-addition; one oversized summary no longer starves tier 2 (Q1)
- `query/hybrid.py` `rrf_fusion` — metadata merge preserves all fields on id collision, not just score (Q2)
- `query/rewriter.py` — strips smart quotes, backticks, and single quotes from LLM-rewritten queries (Q3)
- `graph/builder.py` `graph_stats` — PageRank and betweenness centrality include `status` metadata (ok/failed/degenerate) (Q4)
- `graph/builder.py` `build_graph` — bare-slug resolution uses pre-built `slug_index` dict for O(1) lookup (P1)
- `utils/pages.py` `load_all_pages` — `include_content_lower` param (default True) allows callers to skip unnecessary `.lower()` computation (P2)

#### Stats

- 1645 tests across 126 test files

### Phase 4.5 — HIGH cycle 1 (2026-04-16)

22 HIGH-severity bugs from Rounds 1-6 of the Phase 4.5 multi-agent audit. 4 themed commits.

#### Fixed — Phase 4.5 HIGH (22 items)

- `review/refiner.py` `refine_page` — page-file RMW lock via `file_lock(page_path)` (R6 HIGH)
- `ingest/evidence.py` `append_evidence_trail` — page-file lock around RMW (R2)
- `ingest/pipeline.py` `_persist_contradictions` — contradictions-path `file_lock` (R4)
- `utils/wiki_log.py` `append_wiki_log` — `file_lock` + retry-once; `log_path` now required (R2)
- `query/engine.py` `query_wiki` — dropped dead `raw_dir` containment `try/except` (R6 MEDIUM)
- `ingest/pipeline.py` `_is_duplicate_content` → `_check_and_reserve_manifest` — dual-phase `file_lock(MANIFEST_PATH)` around hash-dedup check+save (R2; fulfills cycle-1 C8 commitment)
- `ingest/pipeline.py` contradictions path — derived from `effective_wiki_dir` (R1)
- `utils/wiki_log.py` `append_wiki_log` — `wiki_dir`/`log_path` required parameter, no default (R2)
- `utils/pages.py` `load_purpose` + MCP `load_all_pages` — `wiki_dir` parameter (R2)
- `tests/conftest.py` `create_wiki_page` — factory requires explicit `wiki_dir` kwarg (R3)
- `ingest/pipeline.py` `_build_summary_content` + `_update_existing_page` — `sanitize_extraction_field` on all untrusted fields (R1; Q_J expansion)
- `compile/linker.py` `inject_wikilinks` — `wikilink_display_escape` replaces ad-hoc `safe_title` (R3)
- `ingest/evidence.py` — HTML-comment sentinel `<!-- evidence-trail:begin -->` with FIRST-match heuristic (R2)
- `ingest/pipeline.py` `_persist_contradictions` — `source_ref` newline/leading-`#` stripped (R2)
- `review/context.py` `build_review_context` — XML sentinels + untrusted-content instruction in `build_review_checklist` (R4; Q_L)
- `review/context.py` `pair_page_with_sources` — symlink traversal blocked outside `raw/` (R1 HIGH security)
- `query/citations.py` `extract_citations` — per-segment leading-dot rejection (R4)
- `utils/markdown.py` `WIKILINK_PATTERN` — 200→500-char cap + `logger.warning` on drop (R4)
- `query/rewriter.py` `rewrite_query` — narrowed `except` to `LLMError`; logs at WARNING (R5)
- `mcp/core.py` `kb_query` — category-tagged errors via `ERROR_TAG_FORMAT` in `mcp/app.py` (R5)
- `query/embeddings.py` + `ingest/pipeline.py` + `compile/compiler.py` — hybrid vector-index lifecycle: mtime-gated `rebuild_vector_index`, `_skip_vector_rebuild` for batch callers (R2)
- `mcp/core.py` `kb_query` — `conversation_context` wired in Claude Code mode (R4)
- `ingest/pipeline.py` `_update_existing_page` — returns on frontmatter parse error (R1)

#### Added

- `sanitize_extraction_field(value, max_len=2000)` helper in `kb.utils.text` — strips control chars, frontmatter fences, markdown headers, HTML comments, length-caps untrusted extraction fields
- `wikilink_display_escape(title)` helper in `kb.utils.text` — strips `]`/`[`/`|`/newlines for safe wikilink display
- `ERROR_TAG_FORMAT` constant + `error_tag(category, message)` helper in `kb.mcp.app` — categories: `prompt_too_long`, `rate_limit`, `corrupt_page`, `invalid_input`, `internal`
- `rebuild_vector_index(wiki_dir, force=False)` in `kb.query.embeddings` — mtime-gated with `_hybrid_available` flag
- `_persist_contradictions` helper extracted from inline `ingest_source` code
- `_check_and_reserve_manifest` replacing `_is_duplicate_content` with lock discipline
- `tests/fixtures/injection_payloads.py` — attack payload catalog from BACKLOG R1-R4

#### Fixed — Post-PR 2-round adversarial review (2026-04-16)

2-round review (1 Opus + 1 Sonnet) surfaced 1 major + 8 minors; 4 fixed in commit `330db40`:

- `ingest/pipeline.py` + `review/refiner.py` — `append_wiki_log` retry-then-raise crashed callers after successful page writes; now wrapped in try/except OSError with best-effort semantics (MAJOR)
- `utils/io.py` lock-order doc — corrected to note `refine_page` holds two locks (page_path then history_path)
- `ingest/pipeline.py` `_persist_contradictions` — space-then-hash source_ref edge case; `.strip()` before `.lstrip("#")`
- `review/refiner.py` — added missing `logger` import for new OSError warning

### Phase 4.5 — CRITICAL cycle 1 docs-sync (2026-04-16)

Immediately-following PR after cycle 1 merged. Addresses the 2 items the second-gate Opus review deferred from cycle 1 as preventive-infrastructure drive-by:

#### Fixed — Phase 4.5 CRITICAL (items 4 + 5)

- **`pyproject.toml` version alignment** (item 4) — bumped from `0.9.10` → `0.10.0` to match `src/kb/__init__.py.__version__` and the README badge. `pip install -e .` / `pip freeze` now report the correct version.
- **CLAUDE.md stats refresh** (item 5) — test count updated (1531 → 1552 actual), test-file count updated (1434-era claim → 119 actual), replaced ambiguous "24 modules" with "67 Python files in src/kb/", and added Phase 4.5 CRITICAL cycle 1 + docs-sync to the shipped-unreleased list.

#### Added

- **`scripts/verify_docs.py`** — pre-push / CI-friendly drift check:
  - Verifies `pyproject.toml` version == `src/kb/__init__.py.__version__` == README badge version.
  - Runs `pytest --collect-only` and compares collected count against CLAUDE.md's claimed "N tests" lines (tolerance ±10 by default; `KB_VERIFY_STRICT=1` env var for exact match).
  - Checks `CLAUDE.md`'s "across N test files" claim against the actual test-file count.
  - Reports source file count for reference (not gated — `src/kb/` file count shifts naturally across cycles).
  - Exit 0 on alignment, exit 1 on drift. Only REPORTS; does not auto-fix.

#### Changed — BACKLOG.md R6 additions

Five deferred findings from the post-PR 2-round adversarial review (commit `99e99d8` addendum) now logged for the next cycle:

- **Phase 4.5 HIGH:** `refine_page` page-file RMW race (no lock on the wiki page body itself; only history RMW was fixed in cycle 1 item 13).
- **Phase 4.5 MEDIUM:** `query_wiki` raw_dir containment-check tautology (the `try/except ValueError` block is dead code by construction; either remove or anchor against `PROJECT_ROOT` to make it enforce something).
- **Phase 4.5 LOW ×3:** `utils/io.py` `acquired = True` timing comment misleading; `utils/llm.py` `last_error = e` on non-retryable branch dead code; `test_compile_loop_does_not_double_write_manifest` monkeypatch brittleness.


---

> **Older history** (Phase 4.5 CRITICAL audit 2026-04-15 and all released versions): see [CHANGELOG-history.md](CHANGELOG-history.md).

