# Backlog-by-file cycle 6 — Requirements (Step 1)

**Date:** 2026-04-18
**Branch:** `feat/backlog-by-file-cycle6`
**Base:** `main` at 9bf8a51 (1842 tests / 129 test files)
**Feature-dev pipeline:** full 16 steps, zero human gates

## Problem

Continuing the file-grouped backlog-reduction cadence (cycles 1–5 shipped 14–38 items per cycle). Post-cycle-5 redo (PR #19), BACKLOG.md Phase 4.5 section still lists ~80 genuinely-open items across HIGH/MEDIUM/LOW. Cycle 3 R1 Opus flagged "9 of 30 items already shipped" — this cycle **verifies every candidate against current source BEFORE design lock** to avoid that waste.

## Non-goals

- Any item flagged "architecturally deep" (two-phase compile pipeline, split config god-module, models dataclass promotion, kb.errors taxonomy rollout) — defer to dedicated cycles.
- Items requiring multi-process tests (`file_lock` PID-liveness on Windows, cross-process concurrent `inject_wikilinks`) — deferred to a test-infrastructure cycle per BACKLOG L219.
- Any change that refactors an existing public function signature without a caller-grep checkpoint (per `feedback_signature_drift_verify` memory).
- Net-new features (Phase 5 proposals: `/llms.txt`, `kb_merge`, `belief_state`, etc.).

## Acceptance criteria (AC1–AC10)

Each AC must be pass/fail verifiable with either a grep assertion or a pytest assertion.

- **AC1** `mcp/core.py` `kb_ingest_content` accepts `use_api: bool = False` kwarg and, when true, calls `ingest_source(path, source_type)` after save rather than requiring `extraction_json`. Signature compat preserved (positional args unchanged).

- **AC2** `mcp/health.py` `kb_detect_drift`, `kb_evolve`, `kb_graph_viz` each accept `wiki_dir: str | None = None` param and thread it to the underlying library calls (matching `kb_lint`'s Phase 5.0 pattern). Existing callers without kwarg continue to work.

- **AC3** `query/rewriter.py` `rewrite_query` rejects LLM preamble-leaked rewrites (patterns: `"The standalone question is:"`, `"Sure!"`, `"Here's"`, `"The rewrite is:"`, or any `[A-Z][a-z]+:` at start of output) by returning the original question.

- **AC4** `query/engine.py` `_compute_pagerank_scores` uses a process-level cache keyed on `(str(wiki_dir_resolved), max_mtime_ns)` — recomputation only happens when any wiki page's mtime exceeds the cached snapshot.

- **AC5** `query/embeddings.py` `VectorIndex.query` reuses a single `sqlite3.Connection` per `VectorIndex` instance (loaded once in `__init__` after `sqlite_vec.load`); extension-load failure in `__init__` degrades the instance to empty-results mode with one WARNING log; subsequent queries return `[]` without re-attempting load.

- **AC6** `graph/builder.py` `build_graph` accepts `pages: list[dict] | None = None`; when provided, extracts wikilinks from the `content` field instead of re-reading each page from disk. Existing no-arg callers keep current behavior.

- **AC7** `ingest/pipeline.py` `_update_existing_page` normalizes `content.replace("\r\n", "\n")` after read so `_SOURCE_BLOCK_RE` (LF-only) matches CRLF-encoded frontmatter; write back uses LF via existing `atomic_text_write` contract.

- **AC8** `ingest/pipeline.py` `_process_item_batch` shares a `seen_slugs` dict across entity+concept batches so an extraction with `entities_mentioned=["RAG"]` and `concepts_mentioned=["RAG"]` produces ONE page (entity takes precedence) with a single-line collision warning.

- **AC9** `cli.py` exposes a `KB_DEBUG=1` env-var trigger that prints `traceback.format_exc()` to stderr before `SystemExit(1)` on any CLI subcommand error. `--verbose` flag is an alias. Default behavior (no env, no flag) preserves the current user-facing message.

- **AC10** `query/hybrid.py` RRF fusion stores `scores[pid] = (rrf_score, result)` tuple instead of shallow-copy dict; output list assembled at sort time. Matches existing test expectations (no signature change on `rrf_fusion` return).

### Secondary AC (LOW severity / test-only)

- **AC11** `query/dedup.py` `_dedup_by_text_similarity` skips the 0.85 Jaccard threshold when comparing pages of different `type`; lowers cross-type asymmetric pruning.

- **AC12** `evolve/analyzer.py` `find_connection_opportunities` replaces the three-level `break` chain with an `itertools.islice(pairs, MAX_PAIRS)` or helper that surfaces the truncation threshold in one place.

- **AC13** `graph/builder.py` `graph_stats` betweenness computation gated behind `include_centrality: bool = False` kwarg; `kb_stats` and `kb_lint` callers pass `False` by default. Opt-in via `include_centrality=True` on the rare `kb_stats --detail` path (future work).

- **AC14** `ingest/extractors.py` `load_purpose` caches via `@functools.lru_cache(maxsize=4)` keyed on `wiki_dir`; invalidation contract documented in docstring (tests that mutate `purpose.md` mid-run must call `load_purpose.cache_clear()`).

- **AC15** `utils/pages.py` `load_all_pages` accepts `return_errors: bool = False` kwarg; when True returns `{"pages": [...], "load_errors": N}` dict so callers can detect "0 pages found because 0 load errors" vs "0 pages found because 100 permission errors."

- **AC16** Tests: every AC above has a behavioral regression test (not signature-only). New tests land in `tests/test_backlog_by_file_cycle6.py` unless a canonical test file already exists.

### Blast radius

Files touched (anticipated):

| File | ACs | Classification |
|------|-----|----------------|
| `src/kb/mcp/core.py` | AC1 | HIGH — new kwarg |
| `src/kb/mcp/health.py` | AC2 | HIGH — 3 tools plumbed |
| `src/kb/query/rewriter.py` | AC3 | HIGH — output validation |
| `src/kb/query/engine.py` | AC4 | HIGH — process-level cache |
| `src/kb/query/embeddings.py` | AC5 | HIGH — connection lifecycle |
| `src/kb/graph/builder.py` | AC6, AC13 | HIGH + MEDIUM |
| `src/kb/ingest/pipeline.py` | AC7, AC8 | MEDIUM — regex + batch |
| `src/kb/cli.py` | AC9 | HIGH — observability |
| `src/kb/query/hybrid.py` | AC10 | MEDIUM — perf |
| `src/kb/query/dedup.py` | AC11 | LOW |
| `src/kb/evolve/analyzer.py` | AC12 | LOW |
| `src/kb/ingest/extractors.py` | AC14 | MEDIUM |
| `src/kb/utils/pages.py` | AC15 | MEDIUM |
| `tests/test_backlog_by_file_cycle6.py` | AC16 | NEW |

14 files + 1 new test file. Commit cadence: one commit per file per cycle's file-grouping convention. Tests must exercise production code paths (not `inspect.getsource` greps per `feedback_inspect_source_tests` memory).

### Scope-boundary verification log (pre-Step 2)

All candidates verified as still-open via `grep` / `Read` against current `main`:

- ✅ `kb_ingest_content use_api` — grep: `use_api` appears only on `kb_query`/`kb_ingest`, not `kb_ingest_content`.
- ✅ `kb_detect_drift wiki_dir` — `mcp/health.py:180` function signature `kb_detect_drift()` takes no args.
- ✅ `rewrite_query leak-prefix` — rewriter.py line 136 only does `.strip(_QUOTE_CHARS)`, no preamble rejection.
- ✅ `_compute_pagerank_scores` not cached — `engine.py:177` calls `build_graph(wiki_dir)` unconditionally.
- ✅ `VectorIndex.query` reconnects — `embeddings.py:269` opens fresh `sqlite3.connect` per call.
- ✅ `build_graph` no `pages=` param — `graph/builder.py` still re-reads per page.
- ✅ `_SOURCE_BLOCK_RE` LF-only — pipeline.py:45 pattern has no `\r?\n`.
- ✅ `_process_item_batch` seen_slugs scoped per-batch — pipeline.py:617 reset each call.
- ✅ `cli.py` no traceback — no `traceback` import in cli.py.
- ✅ `rrf_fusion` stores dict copies — hybrid.py line ~27 uses `{**result, "score": rrf_score}`.
- ✅ `_dedup_by_text_similarity` no type-guard — dedup.py applies threshold uniformly.
- ✅ `find_connection_opportunities` three-break — analyzer.py:128,133,143 confirm chain.
- ✅ `graph_stats betweenness` unconditional — builder.py:~122 runs on every `kb_stats`.
- ✅ `load_purpose` no cache — extractors.py:329 no `lru_cache` decorator.
- ✅ `load_all_pages` no error count — utils/pages.py:~83 returns bare list.

**Verify-before-design pass complete — no items in this scope are already shipped.**
