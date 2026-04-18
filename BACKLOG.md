# Backlog

<!-- FORMAT GUIDE — read before adding items
Each phase section groups items by severity, then by module area.
Resolved phases collapse to a one-liner; active phases list every item.

## Severity Levels

| Level      | Meaning                                                        |
|------------|----------------------------------------------------------------|
| CRITICAL   | Data loss, crash with no recovery, or security exploit — blocks release |
| HIGH       | Silent wrong results, unhandled exceptions reaching users, reliability risk |
| MEDIUM     | Quality gaps, missing test coverage, misleading APIs, dead code |
| LOW        | Style, docs, naming, minor inconsistencies — fix opportunistically |

## Item Format

```
- `module/file.py` `function_or_symbol` — description of the issue
  (fix: suggested remedy if non-obvious)
```

Rules:
- Lead with the file path (relative to `src/kb/`), then the function/symbol.
- Include line numbers only when they add precision (e.g. `file.py:273`).
- End with `(fix: ...)` when the remedy is non-obvious or involves a design choice.
- One bullet = one issue. Don't combine unrelated problems.
- When resolving an item, delete it (don't strikethrough). Record the fix in CHANGELOG.md.
- Move resolved phases under "## Resolved Phases" with a one-line summary.
-->

---

## Cross-reference

| File | Role | Update rule |
|------|------|-------------|
| **BACKLOG.md** ← you are here | Open work only, ranked by severity | Add on discovery; **delete** on resolve |
| [CHANGELOG.md](CHANGELOG.md) | Every shipped change, newest first (2026-04-16+) | Every merge to main |
| [CHANGELOG-history.md](CHANGELOG-history.md) | Archive: Phase 4.5 CRITICAL (2026-04-15) and older releases | Read-only after initial split; new archive entries require explicit split from CHANGELOG.md |

**Resolve lifecycle:** Delete item here → record fix in `CHANGELOG.md [Unreleased]` → done.

> **For all LLMs (Sonnet 4.6 · Opus 4.7 · Codex/GPT-5.4):** BACKLOG = open work; CHANGELOG = shipped fixes. If an item says _"see CHANGELOG"_, it is resolved and can be safely deleted from this file.

---

## Phase 4 (v0.10.0) — Post-release audit

_All items resolved — see `CHANGELOG.md` `[Unreleased]`._

---

## Phase 4.5 — Multi-agent post-v0.10.0 audit (2026-04-13)

<!-- Discovered by 5 specialist reviewers (Python, security, code-review, architecture, performance)
     running 3 sequential rounds against v0.10.0 after the Phase 4 HIGH/MEDIUM/LOW audit shipped.
     Items grouped by severity, keyed by file. Round tag in parens (R1/R2/R3). -->

### CRITICAL

<!-- All 18 Phase 4.5 CRITICAL items resolved. Cycle 1 (16 items, PR #9 merged 2026-04-16)
     shipped the code fixes. Cycle 1-docs-sync (items 4 + 5, this PR) aligns version strings
     across pyproject.toml/__init__.py/README and updates CLAUDE.md stats + adds
     scripts/verify_docs.py as a pre-push guard against future drift. See CHANGELOG. -->

_All CRITICAL items resolved — see CHANGELOG `[Unreleased]` Phase 4.5 cycle 1 + docs-sync._

_Items closed in CHANGELOG [Unreleased] "Backlog-by-file cycle 4" (2026-04-17):
`_rel()` error-string sweep in `mcp/core.py` (#1), `<prior_turn>` sentinel +
fullwidth angle-bracket fold + control-char strip in `mcp/core.py`
`conversation_context` (#2), `Error[partial]` on post-create OSError in
`kb_ingest_content` / `kb_save_source` (#5), `kb_read_page` body cap with
`[Truncated:]` footer (#7), `kb_affected_pages` `check_exists=True` (#11),
`add_verdict` per-issue description cap at library boundary (#12),
`_validate_page_id` Windows-reserved + 255-char cap cross-platform (#13),
`kb_detect_drift` source-deleted third category (#14), `query/rewriter`
CJK short-query gate (#15), `_WIKI_BM25_CACHE` + `BM25_TOKENIZER_VERSION`
in `_RAW_BM25_CACHE` key (#16 + #18 cache-invalidation path), running
type-diversity quota in `dedup` (#17), STOPWORDS prune of 8 overloaded
quantifiers (#18), `yaml_sanitize` BOM + U+2028 + U+2029 strip (#19),
`wiki_log` monthly rotation `log.YYYY-MM.md` + ordinal collision (#20),
`ingest/pipeline` caller migration to `detect_contradictions_with_metadata`
+ truncation WARNING (#22), `export_mermaid` Path-shim DeprecationWarning
(#23), `BM25Index` postings precompute (#24), `_template_hashes`
VALID_SOURCE_TYPES whitelist (#25), `load_purpose(wiki_dir)` required arg
(#28), `inject_wikilinks` caller-side `sorted()` by title length (#29).
Deferred: `[source: X]` → `[[X]]` citation migration (#3, too large for
mechanical cleanup; tracked as dedicated Phase 4.5 atomic migration)._

### HIGH

- `compile/compiler.py` naming inversion (~16-17) — `compile_wiki` is a thin orchestration shell over `ingest_source` + a manifest; real compilation primitives (`linker.py`) live in `compile/` but are consumed by `ingest/`. Dependency arrows invert the directory names; every new feature placement becomes a coin-flip. (R1)
  (fix: rename to `pipeline/orchestrator.py` and treat `compile/` as wikilink primitives only; or collapse `compile/compiler.py` into `kb.ingest.batch`)

- `utils/llm.py` — `LLMError` is the only custom exception in the codebase; CLI (`cli.py:54,79,98,121,135`), `compile/compiler.py:349`, and MCP catch bare `Exception` and string-format. Cannot retry selectively, cannot test error paths, bugs in manifest-write are indistinguishable from LLM failures. (R1)
  (fix: `kb.errors` with `KBError` → `IngestError` / `CompileError` / `QueryError` / `ValidationError` / `StorageError`; narrow `except` at the boundary)

- `review/refiner.py` `refine_page` (~114-137) — writes page atomically, THEN appends `review_history.json`, THEN `wiki/log.md`. Crash or disk-full between steps leaves the page mutated with zero audit record, violating the documented refine-has-audit-trail guarantee; `append_wiki_log` further swallows `OSError` with a warning. (R2)
  (fix: write audit record first with `status="pending"`, write page, flip status to `"applied"`; or stage via a `page.md.pending` sidecar flipped only after log is synced)

- `ingest/pipeline.py` state-store fan-out — a single `ingest_source` mutates summary page, N entity pages, N concept pages, `index.md`, `_sources.md`, `.data/hashes.json`, `wiki/log.md`, `wiki/contradictions.md`, plus N `inject_wikilinks` writes across existing pages. Every step is independently atomic, none reversible. A crash between manifest-write (step 6) and log-append (step 7) leaves the manifest claiming "already ingested" while the log shows nothing; a mid-wikilink-injection failure leaves partial retroactive backlinks. (R2)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests; retries idempotent at step granularity)

- `compile/compiler.py` `compile_wiki(incremental=False)` — "full" compile rescans and re-ingests but does NOT: clear manifest (deleted sources linger until a dedicated prune branch runs); rebuild vector index; invalidate in-process `_index_cache` in `embeddings.py`; re-validate evidence trails / contradictions / injected wikilinks. A page corrupted by a half-finished ingest stays corrupt across `--full`. (R2)
  (fix: document exactly what `--full` does and does not invalidate; add `kb rebuild-indexes` CLI that wipes manifest + vector DB + in-memory caches before a full compile)

- `graph/builder.py` no shared caching policy — cycle 6 added a query-side PageRank cache and preloaded-page threading for `kb_query`, and cycle 7 threaded page bundles through several callers, but the graph layer itself still has no reusable cache/invalidation contract. `lint/runner.py` and `lint/checks.py` can still rebuild graphs independently in one lint pass, and no policy doc defines when graph-derived caches are invalidated after ingest/refine. (R2; query hot-path portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
  (fix: `kb.graph.cache` keyed on `(wiki_dir, max_mtime_of_wiki_subdirs)`; share within lint/evolve/query call stacks; invalidate at end of `ingest_source` + `refine_page`; document in CLAUDE.md alongside the manifest contract)

- `mcp/core.py` `kb_ingest` source-file cap inconsistency — cycle 1/5 fixes consolidated `MAX_NOTES_LEN` and capped `kb_refine_page`, `kb_query_feedback`, and `kb_save_lint_verdict` notes, but `kb_ingest` still silently truncates source-file content to `QUERY_CONTEXT_MAX_CHARS=80K` with only a `logger.warning` while sibling tools reject oversized content at the MCP boundary. (R3; notes/constant-duplication portions resolved in CHANGELOG `[Unreleased]`)
  (fix: reject oversized `kb_ingest` source files at MCP boundary instead of silently truncating; share the same size-limit wording used by `kb_ingest_content` / `kb_save_source`)


- `tests/test_v0p5_purpose.py` purpose-threading coverage gap — cycle 6 added `rewrite_query` tests that mock `call_llm` and reject leaked preambles, but `test_v0p5_purpose.py` still checks only that the string "KB FOCUS" appears in the extraction prompt; it never verifies `query_wiki` threads `purpose.md` to the synthesizer. Phase 5's `kb_capture` will follow this template if not corrected. (R3; rewriter coverage portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
  (fix: add `query_wiki(..., wiki_dir=tmp)` integration test asserting purpose text reaches the synthesis prompt)

- `tests/` coverage-visibility — ~50 of 94 files are named `test_v0NNN_taskNN.py` / `test_v0NNN_phaseNNN.py` / `test_phase4_audit_*.py`. To verify `evolve/analyzer.py` has tier-budget coverage you must grep ~50 versioned files because canonical `test_evolve.py` has only 11 tests (none touch numeric tokens, redundant scans, or three-level break — all open in Phase 4.5 MEDIUM). `_compute_pagerank_scores` is searched across 25 files. (R3)
  (fix: freeze-and-fold rule — once a version ships, fold its tests INTO the canonical module file (`test_v0917_dedup.py` → `test_query.py::class TestDedup`); enable `coverage` in CI and surface per-module % in PR comments)

- `tests/` no end-to-end ingest→query workflow — grepping for `end_to_end`, `e2e`, `workflow`, `ingest_to_query` returns only single-module tests; no test chains `ingest_source` → `build_graph` → `search` → `query_wiki` against the same `tmp_wiki`. `test_phase4_audit_query.py::test_raw_fallback_truncates_first_oversized_section` mocks `search_raw_sources`, `search_pages`, AND `call_llm` — only the glue is exercised. The Phase 4.5 items about "page write vs evidence append", "manifest race", "index-file write order", "ingest fan-out" all describe failures BETWEEN steps; pure-unit tests cannot catch them. (R3)
  (fix: `tests/test_workflow_e2e.py` with 3-5 multi-step scenarios (ingest article → query entity → refine page → re-query) using real modules + mocked LLM at the boundary; mark `@pytest.mark.integration`)

- `tests/conftest.py` `project_root` / `raw_dir` / `wiki_dir` leak surface — fixtures point at REAL `PROJECT_ROOT` and are documented as "read-only use" but nothing enforces it. `test_cli.py:61-63` proves the global-escape paths exist (multi-global monkeypatch). Phase 4.5 already flagged `WIKI_CONTRADICTIONS` leaking, `load_purpose()` reading the real file, `append_wiki_log` defaulting to production. Phase 5 will add `wiki/hot.md`, `wiki/overview.md`, `wiki/_schema.md`, `raw/captures/` — one more leak surface each. (R3; cycle 7 only added autouse embeddings reset)
  (fix: make read-only fixtures fail loudly — return paths under a sandbox by default; provide explicit `real_project_root` fixture requiring `pytest --use-real-paths`; autouse monkeypatch of all `WIKI_*` constants to `tmp_path` for tests that don't explicitly opt out)

- `mcp/__init__.py:4` + `mcp_server.py:10` — FastMCP `run()` eagerly imports `core, browse, health, quality`; those pull `kb.query.engine` → `kb.utils.llm` → `anthropic` (548 modules, 0.58s), and `kb.mcp.health` pulls `kb.graph.export` → `networkx` (285 modules, 0.23s). Measured cold MCP boot: 1.83s / +89 MB / 2,433 modules — of which ~0.8s / ~35 MB is unnecessary for sessions using only `kb_read_page`/`kb_list_pages`/`kb_save_source`. (R3)
  (fix: defer `from kb.query.engine import …`, `from kb.ingest.pipeline import …`, `from kb.graph.export import …` into each tool body (pattern already used for feedback, compile); module-level imports in `kb/mcp/*` limited to `kb.config`, `kb.mcp.app`, stdlib)

- `query/embeddings.py` `_get_model` (~32-41) cold load — measured 0.81s + 67 MB RSS delta for `potion-base-8M` on first `kb_query` that touches vector search. `engine.py:87` gates on `vec_path.exists()` — per R2, vector index is almost always stale/absent so the model load is skipped AND hybrid silently degrades to BM25. Either outcome hurts: if the index exists we pay 0.8s on first user query; if it doesn't, "hybrid" is a lie. (R3)
  (fix: warm-load on MCP startup ONLY IF `vec_path.exists()`, and in a background thread so the user's first query isn't charged; or emit a "first query warm-up: embedding model loading…" progress line if user-facing latency crosses 300ms)

- `mcp/core.py` + `browse.py` + `health.py` + `quality.py` — all 25 MCP tools are sync `def`. FastMCP runs them via `anyio.to_thread.run_sync` on a default 40-thread pool. A `kb_query(use_api=True)` (30s+), `kb_lint()` (multi-second disk walk), `kb_compile()` (minutes), or `kb_ingest_content(use_api=True)` (10+s) each hold a thread; under concurrent tool calls the pool saturates and subsequent calls queue. Claude Code often fires multiple tool calls in parallel; this turns invisible latency spikes into observed user-facing stalls. (R3; cycle 7 did not address)
  (fix: make long-I/O tools `async def` and `await anyio.to_thread.run_sync(...)` around the SDK call; or document / tune `FastMCP(num_threads=N)`; at minimum surface the concurrency model in the `app.py` instructions block)

- `compile/compiler.py:367-380` `compile_wiki` full-mode manifest pruning — `stale_keys` filter uses `raw_dir.parent / k` to check `.exists()`, but `raw_dir.parent` is NOT the project root when a caller passes a non-default `raw_dir` — every entry gets pruned. The prune also runs on `current_manifest` AFTER the per-source loop wrote successful hashes; between the two `load_manifest` calls there's no lock, so a concurrent `kb_ingest` adding a manifest entry in the window gets silently deleted on save. (R4)
  (fix: compute prune base once as `raw_dir.resolve().parent` matching `_canonical_rel_path`'s base; wrap "reload + prune + update templates + save" in `file_lock(manifest_path)` matching the per-source reload-save pattern)

- `compile/compiler.py:343-347` `compile_wiki` manifest write — after a successful `ingest_source`, the code does `load_manifest → manifest[rel_path] = pre_hash → save_manifest`. But `ingest_source` itself writes `manifest[source_ref] = source_hash` via `kb.ingest.pipeline:687` using its own path resolution. Two code paths write the same key with potentially different normalization (`source_ref` via `make_source_ref` vs `_canonical_rel_path`). Windows case differences or `raw_dir` overrides produce two divergent keys for the same file — `find_changed_sources` sees it as "new" and re-extracts. (R4)
  (fix: pipe `rel_path` into `ingest_source` (add `manifest_key: str | None = None`) OR delete the redundant per-loop write in `compile_wiki` and rely solely on `ingest_source`'s internal manifest update; assert one-key-per-source in tests)

- `compile/linker.py:219-220` `inject_wikilinks` safe_title `\u2014` swap — `title.replace("|", "\u2014")` silently replaces pipes with em-dashes. A legitimate title containing `|` (rare but reachable via LLM extraction) loses the character with no warning; display shows an em-dash instead of the real character. Worse, this is not a correct fix — `]` and `[` still pass through (see R3 item for injected-wikilink close-bracket escape), so "sanitize" is false assurance. (R4)
  (fix: reject titles containing `|`/`]`/`[` at ingest time (escalate to extraction validation) rather than silently transliterate; or centralize via `wikilink_display_escape()` that also strips `[`/`]`)

- `mcp/browse.py:15-45` `kb_search` — (a) no query length cap: `query="x"*1_000_000` accepted and run through `tokenize()` + BM25; (b) `stale` flag NOT surfaced in output even though `search_pages` attaches it (kb_query emits `[STALE]`, kb_search drops it). Discoverability of staleness inconsistent between two search tools. (R4)
  (fix: (a) enforce `MAX_QUESTION_LEN` like `kb_query`; (b) include `[STALE]` / `[trust: X.XX]` marker next to score in the formatted snippet)

- `compile/linker.py:178-241` `inject_wikilinks` cascade-call write race — `ingest_source` calls `inject_wikilinks` once per newly-created page (`pipeline.py:714-721`). For an ingest creating 50 entities + 50 concepts = 100 sequential calls in one process. Each iterates ALL wiki pages, reads each, may rewrite each via `atomic_text_write`. NO file lock. Concurrent ingest_source from another caller is identically iterating and rewriting the SAME pages. Caller A reads page X, caller B reads page X, A writes "X with link to A", B writes "X with link to B" — only B's wikilink survives. The retroactive-link guarantee silently fails under concurrent ingest. Compounds R4 overlapping-title (intra-process); R5 is the cross-process write-write race on the SAME page. (R5)
  (fix: per-target-page lock — `with file_lock(page_path): content = read; if needs_change: write`; or a wiki-wide writer lock during the inject phase since updates are usually fast)

- `ingest/pipeline.py:594-611,715` slug + path collision under concurrent ingest — two concurrent `ingest_source` calls extracting different titles that slugify to the same `summary_slug` (e.g., `"My Article"` and `"My  Article"` both → `my-article`) both check `summary_path.exists()` (603), both see False, both call `_write_wiki_page → atomic_text_write` to the SAME `wiki/summaries/my-article.md`. Last writer wins — first source's summary silently overwritten. Frontmatter `source:` lists only the second source, evidence trail is wrong, all entity references from the first source point to a now-deleted summary. Same flow at line 496 for entities/concepts. R1 flagged `kb_create_page` TOCTOU vs O_EXCL but `_write_wiki_page` and `_process_item_batch` have the SAME pattern AND are the actual hot path. (R5)
  (fix: replace `_write_wiki_page`'s `atomic_text_write` with exclusive-create — `os.open(O_WRONLY | O_CREAT | O_EXCL)` + temp-file rename; on `FileExistsError`, fall through to `_update_existing_page` (the merge path); same change in `_process_item_batch`)

- `ingest/pipeline.py:603,715-721,729-754` lock acquisition order risk between same-ingest stages — within one `ingest_source`: stage 1 writes summary page (line 609) → `append_evidence_trail` to SAME page; stage 2 calls `_update_existing_page` on each entity (re-reads + re-writes); stage 9 `inject_wikilinks` re-reads + re-writes some of the SAME pages it just wrote in stages 1-3; stage 11 writes `wiki/contradictions.md`. None use `file_lock`. Within ONE process this is OK. Under concurrent ingest A + B, the read-then-write windows in different stages of A overlap with different stages of B in non-deterministic order; debugging becomes impossible because each `kb_ingest` run shows different conflict patterns. R5 highlights the **systemic absence of any locking discipline across the entire 11-stage ingest pipeline** — a problem that compounds with every Phase 5 feature. (R5)
  (fix: introduce a per-page write-lock helper `with page_lock(page_path):` wrapping `read_text → modify → atomic_text_write` and use consistently across `_write_wiki_page`, `_update_existing_page`, `append_evidence_trail`, and `inject_wikilinks`; OR adopt a coarse wiki-wide ingest mutex)

- `compile/compiler.py` `load_manifest` swallows only JSON/Unicode corruption — cycle 3/5/7 widened `load_feedback`, `load_verdicts`, and `load_review_history`, but `load_manifest()` still does not catch transient `OSError` from Windows atomic-rename/read races. A mid-rename manifest read can still bubble raw errors through drift/compile/ingest paths instead of recovering to `{}` with an operator warning. (R5; feedback/verdicts/review-history portions resolved in CHANGELOG `[Unreleased]`)
  (fix: widen `load_manifest` to catch `OSError` alongside `json.JSONDecodeError` / `UnicodeDecodeError`, log a warning, and return `{}`; consider one short retry as in `load_verdicts`)

### HIGH — Additional (surfaced post-cycle-2 or deferred from cycle-1)

> All items below are HIGH severity. Grouped here because they were either surfaced after cycle-2 shipped or explicitly deferred from Phase 4.5 HIGH cycle-1 for a dedicated follow-up cycle.

- `mcp/browse.py` `kb_search` — `test_kb_search_no_results` fails on `main` (and cycle 2) because `hybrid_search` now returns results for nonsense queries like `"xyzzyplugh"` — the vector-search backend assigns a non-zero similarity to any wiki content. Expected behaviour is "No matching pages found." for queries with zero token overlap + near-zero vector similarity. Likely root cause: RRF fusion keeps any result with `score > 0` from either backend, and vector search has no minimum-cosine threshold. *(Surfaced 2026-04-17 during cycle-2 regression run; pre-existed on `main`.)*
  (fix: gate vector-search results on `cosine >= VECTOR_MIN_SIMILARITY` (tune ~0.3); or require BM25 to contribute at least one non-zero-score hit for the results to surface)

- `review/refiner.py` `refine_page` write-then-audit ordering — after H1's page-file lock (cycle 1), a crash/OSError on the history-lock step still leaves the page body updated without an audit record. Adopt two-phase write (pending audit first → write page → flip to applied). See `docs/superpowers/decisions/2026-04-16-phase4.5-high-cycle1-design.md` Q_H. *(Deferred from Phase 4.5 HIGH cycle 1.)*

- `query/embeddings.py` vector-index lifecycle — Phase 4.5 HIGH cycle 1 shipped H17 hybrid (mtime-gated rebuild + batch skip), but deferred: (1) atomic temp-DB-then-replace rebuild (crash-mid-rebuild leaves empty index), (2) cold-load latency (0.8s+67MB on first query), (3) dim-mismatch (stored embedding dim vs current model not validated), (4) `_index_cache` cross-thread lock symmetry. Bundle into dedicated vector-index lifecycle cycle. *(Deferred from Phase 4.5 HIGH cycle 1.)*

- `tests/` multiprocessing tests for cross-process `file_lock` semantics — cycle 1 HIGH used in-process threading as a proxy but Windows NTFS lock behavior is not exercised. Add `@pytest.mark.slow` multiprocessing tests in a dedicated test-infrastructure cycle. *(Deferred from Phase 4.5 HIGH cycle 1.)*

### LOW — Deferred from cycle-2

- `utils/llm.py` `_make_api_call` — truncation of `e.message` prevents simple prompt-content leak but does not REDACT (user prompts, image base64 fragments, API keys echoed by Anthropic). Follow-up cycle should add pattern-based redaction or prompt-prefix hashing before truncation. (references BACKLOG:701; deferred Step 5 gate Q11)

### MEDIUM

_Items closed in CHANGELOG [Unreleased] "Backlog-by-file cycle 1" (2026-04-17):
`_build_schema_cached` deepcopy (D1), `ingest/contradiction.py` logger
placement + tokens hoist + single-char language names (E1 + verified
pre-fixed), `kb_create_page` O_EXCL (F1), `kb_list_sources` cap (G1),
`kb_refine_page` caps (F2), `_TEXT_EXTENSIONS` library enforcement (C2),
`query/rewriter.py` length guard (J1), `search_raw_sources` BM25 cache
(I2), `_flag_stale_results` UTC (I1), `_dedup_by_text_similarity`
tokens (K1)._

- `models/page.py` dataclasses are dead — `WikiPage` / `RawSource` exist but nothing returns them; `load_all_pages` / `ingest_source` / `query_wiki` each return ad-hoc dicts. "What is a page?" has ≥4 answers (dict, `Post`, `Path`, markdown blob); chunk indexing in Phase 5 will fork it again. (R1)
  (fix: delete dataclasses, or make them the canonical return type and migrate callers)

- `cli.py` function-local imports (~32, 63, 88-89, 107, 129, 143) — every command does `from kb.X import Y` inside the body; import errors only surface on first invocation of that specific command, defeating static dep analysis. (R1)
  (fix: move imports to module top (Click startup is fine), or add a smoke test that exercises every command-import path)

- `compile/linker.py` (~9) — imports `page_id` and `scan_wiki_pages` from `kb.graph.builder`; these are filesystem helpers, not graph helpers. `utils/pages.py` already has a near-duplicate private `_page_id`. `compile/` → `graph/` dependency is fake. (R1)
  (fix: move `page_id` / `scan_wiki_pages` into `kb.utils.pages`; `graph/builder.py` imports from utils; delete the duplicate)

- `config.py` god-module — 35+ unrelated constants (paths, model IDs, BM25 hyperparameters, dedup thresholds, retries, ingest/evolve/lint limits, retention caps, query budgets, RRF, embeddings). Single-file churn invalidates import cache for the whole package in tests. (R1)
  (fix: split into `config/paths.py` / `config/models.py` / `config/limits.py` / `config/search.py` / `config/lint.py`; or a `Settings` dataclass with grouped subfields; keep `from kb.config import *` shim)

- `compile/compiler.py` `compile_wiki` (~320-380) — per-source loop saves manifest after ingest but does not roll back wiki writes if a later manifest save fails; failure-recording branch swallows nested exceptions with a warning; final `append_wiki_log` runs even on partial failure. (R1)
  (fix: per-source "in-progress" marker in manifest cleared only after page write + log append; escalate manifest-write failure to CRITICAL)

_`lint/verdicts.py` `load_verdicts` mtime cache — closed in CHANGELOG [Unreleased] "Backlog-by-file cycle 1" (M1)._

- `lint/checks.py` `check_source_coverage` (~370-382) — reads the file, then `frontmatter.loads(content)` re-splits the YAML fence and runs PyYAML on the exact same string. At 5k pages this is 5k redundant YAML parses on top of the duplication above. (R1)
  (fix: reuse parsed frontmatter from the shared corpus; or `FRONTMATTER_RE` + `yaml.safe_load` on captured fence)

- `utils/io.py` `atomic_json_write` + `file_lock` pair — 6+ Windows filesystem syscalls per small write (acquire `.lock`, load full list, serialize, `mkstemp` + `fdopen` + `replace`, release). `file_lock` polls at 50 ms, adding minimum-latency floor on every verdict add. (R1)
  (fix: append-only JSONL with `msvcrt.locking` / `fcntl` locking; compact on read or via explicit `kb_verdicts_compact`)

- **[MEDIUM] `diskcache==5.6.3` — CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v)**
  Pickle-deserialization RCE in diskcache cache files. No patched version available as of 2026-04-18.
  Mitigation: diskcache is only used by trafilatura's robots.txt cache in `kb.lint.fetcher`; exploit requires local write access to the cache directory. Track upstream for a patched release.

- `lint/checks.py:251, 325, 446` + `lint/semantic.py:93` `frontmatter.load(str(path))` hot-path — reopens every file per rule; 4×5k = 20k file opens for a 5k-page wiki just for frontmatter. (R1)
  (fix: subsumed by the shared pre-loaded corpus; or `@functools.lru_cache` keyed on `(path, mtime_ns)` returning `(metadata, body)`)

- `utils/io.py` `file_lock` PID-liveness (~81-94) — after 5 s timeout, waiter calls `os.kill(pid, 0)` on the recorded PID. On Windows PIDs are aggressively recycled, so `os.kill(pid, 0)` succeeds for an unrelated process sharing the PID (AV, shell, service); conversely, a dead holder whose PID got reassigned to a live unrelated process makes the waiter raise `TimeoutError` instead of stealing. Either failure mode corrupts the verdict / feedback RMW chain. (R2)
  (fix: on Windows use `msvcrt.locking` or `CreateFile(FILE_SHARE_NONE)` and hold the handle; POSIX `fcntl.flock`. Do not use PID-liveness heuristics for correctness.)

- `graph/builder.py` `page_id()` lowercasing (~27-34) — lowercases the node ID while `path` attribute keeps original case. On case-sensitive filesystems (CI Linux), any consumer that reconstructs `wiki_dir / f"{pid}.md"` (e.g. `semantic.build_consistency_context:275`) hits `FileNotFoundError` and the page is silently skipped as `*Page not found*`. Windows dev + Linux CI diverge on the same corpus. (R2)
  (fix: normalize filenames on disk to lowercase at ingest; or stop lowercasing in `page_id()` and route all comparisons through a shared `normalize_id` helper applied only on lookup)

- `ingest/pipeline.py` index-file write order (~653-700) — per ingest: `index.md` → `_sources.md` → manifest → `log.md` → `contradictions.md`. A crash between `_sources.md` and manifest writes can duplicate entries on re-ingest. (R2)
  (fix: introduce an `IndexWriter` helper wrapping all four writes with documented order and recovery)

- `ingest/pipeline.py` observability — one `ingest_source` emits to `wiki/log.md` (step 7) + Python `logger.warning` (frontmatter parse failures, manifest failures, contradiction warnings, wikilink-injection failures, 8+ sites) + `wiki/contradictions.md` + N evidence-trail appends. No correlation ID connects them. `wiki/log.md` records intent ("3 created, 2 updated"), not outcome. Debugging a flaky ingest requires correlating stderr against `wiki/log.md` against `contradictions.md` by timestamp window. (R2)
  (fix: generate `request_id = uuid7()` at top of `ingest_source` and thread through every emitter; add structured `.data/ingest_log.jsonl` with full result dict per call, sharing the id with `wiki/log.md`)

- `ingest/pipeline.py` + `ingest/evidence.py` page write vs evidence append (~150-151, 362-365) — `_write_wiki_page` and `_update_existing_page` perform atomic page write, then call `append_evidence_trail` which does its own read+write+atomic-rename. If the second call fails (disk full, permission flap, lock contention), the page has a new source reference with no evidence entry explaining why. Phase 4's provenance guarantee is conditional. (R2)
  (fix: combine page body + evidence trail into a single rendered output and write atomically; or wrap the pair in a file lock and surface the second-call failure)

- CLI ↔ MCP parity — `cli.py` exposes 6 commands; MCP exposes 25. Operational tasks (view trends, audit a verdict, refine a page, read a page, search, stats, list pages/sources, graph viz, drift, save source, create page, affected pages, reliability map, feedback) require an MCP-speaking client. Tests cannot piggyback on CLI invocation; debugging in CI / cron is by `python -c` only. (R2)
  (fix: auto-generate CLI subcommands from the FastMCP tool registry; or collapse MCP + CLI onto a shared `kb.api` service module — also kills the function-local-import issue cleanly)

- `compile/compiler.py` `compile_wiki` (~279-393) — a 50-line `for source in changed: ingest_source(source)` loop + manifest save. CLAUDE.md describes compile as "LLM builds/updates interlinked wiki pages, proposes diffs, not full rewrites" — no second pass, no cross-source reconciliation, no diff proposal exists in code. MCP `kb_compile` and `kb compile` CLI are cosmetic wrappers. Phase 5's two-phase compile / pre-publish gate / cross-source merging would land in the wrong layer because `compile_wiki` has no batch context. (R2)
  (fix: make `compile_wiki` a real two-phase pipeline (collect extractions → reconcile cross-source → write) and document the contract; or rename to `batch_ingest` and stop pretending compile is distinct)

- `tests/test_ingest.py:86-159` — manually builds wiki subdirs + index files + 6 separate `patch()` calls duplicating what `tmp_project`/`tmp_wiki` fixtures provide. When project scaffolding evolves (new index file, new subdir), tests bypassing fixtures diverge silently. (R3)
  (fix: replace manual scaffolding with `tmp_project`; forward `wiki_dir=` to `ingest_source` instead of patching module globals)

- `ingest/pipeline.py` extraction field type validation (~157, 162-163, 180, 186-188, 248-249, 253-254, 592, 625, 640, 726) — `call_llm_json` enforces schema only for the Anthropic-API path; Claude Code mode accepts `extraction_json` from the MCP client and validates only `isinstance(extraction, dict)` + `title` presence, NOT field types. A malformed `extraction_json={"title":"x", "core_argument": {...}, "key_claims": [42, null]}` hits `.lower()`/`.replace()` on non-string values at multiple sites, aborting mid-ingest with the state-store-fan-out hazard (R2): summary page created, index/sources updated, manifest NOT updated → re-ingest appears "new" and duplicates entries. (R3)
  (fix: `_coerce_str_field(extraction, field)` helper rejecting non-string values with a single up-front error BEFORE any filesystem write; reuse for all 10+ read sites)

- `.env.example` vs `config.py` env-var drift — `.env.example` lists 4 vars; code also reads `CLAUDE_SCAN_MODEL`, `CLAUDE_WRITE_MODEL`, `CLAUDE_ORCHESTRATE_MODEL` (`config.py:66-68`). CLAUDE.md's model tier table documents them but `.env.example` doesn't. Conversely `EMBEDDING_MODEL` is hardcoded (`"minishlab/potion-base-8M"`) with no env override despite Phase 4 roadmap language about "EMBEDDING_MODEL availability." (R3)
  (fix: add three `CLAUDE_*_MODEL` vars (commented, with defaults) to `.env.example`; either add an env override for `EMBEDDING_MODEL` in `config.py:128` or clarify in CLAUDE.md that only the 3 model IDs are env-overridable)

- `tests/` no golden-file / snapshot tests — grep for `snapshot`/`golden`/`syrupy`/`inline_snapshot`/`approvaltests` returns zero hits. Wiki rendering (`_build_summary_content`, `append_evidence_trail`, contradictions append, `build_extraction_prompt`, `_render_sources`, Mermaid export, lint report) is verified only by `assert "X" in output`. `test_v0917_evidence_trail.py` checks `"## Evidence Trail" in text` — the actual format (order of `date | source | action`, prepend direction, whitespace) is unverified. Phase 5's output-format polymorphism (`kb_query --format=marp|html|chart|jupyter`), `wiki/overview.md`, and `wiki/_schema.md` all produce structured output that LLM-prompt tweaks silently reformat. (R3)
  (fix: add `pytest-snapshot` or `syrupy`; start with frontmatter rendering, evidence-trail format, Mermaid output, lint report format; commit `tests/__snapshots__/`)

- `tests/` thin MCP tool coverage — of 25 tools, `kb_compile_scan`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift`, plus the entire `health.py` cluster each have 1-2 assertion smoke tests. Deeply-tested tools (`kb_query`, `kb_ingest`, `kb_refine_page`) accumulated coverage organically across version files. Phase 4.5 flags `kb_graph_viz` `export_mermaid` non-deterministic tie-break and `kb_detect_drift` happy-path-only, both unprotected by per-tool test. (R3)
  (fix: one `tests/test_mcp_<tool>.py` per tool with at minimum: happy path, validation error, path-traversal rejection, large-input cap, missing-file branch; auto-generate skeletons from the FastMCP registry)

- `tests/test_phase4_audit_concurrency.py` single-process file_lock coverage — `test_file_lock_basic_mutual_exclusion` spawns threads, never `multiprocessing.Process` / `subprocess.Popen`. Phase 4.5 R2 flags `file_lock` PID-liveness broken on Windows (PIDs recycled, `os.kill(pid, 0)` succeeds for unrelated process); threads share PID so this is structurally impossible to surface with the current test. Manifest race, evidence-trail RMW race, contradictions append race, feedback eviction race all involve separate processes — autoresearch loop, file watcher, SessionStart hook (Phase 5) all run in separate processes alongside MCP. (R3)
  (fix: `multiprocessing.Process`-based test holding the lock from a child while parent attempts acquire; `@pytest.mark.integration`; assert PID file contains the child's PID)

- `ingest/pipeline.py:154-222` `_build_summary_content` — comparison/synthesis source types declare extract fields `subjects`, `dimensions`, `findings`, `recommendation` (`templates/comparison.yaml`), but the renderer hardcodes only title/author/core_argument/key_claims/entities/concepts variants. A `comparison` ingest produces a page with only title and dropped fields. Worse, `detect_source_type` at `pipeline.py:116-129` cannot detect `comparison`/`synthesis` because `SOURCE_TYPE_DIRS` omits both directories; they're in `VALID_SOURCE_TYPES` but have no `raw/` subdir. So comparison/synthesis templates exist but cannot be ingested AT ALL via `ingest_source`. Dead feature path. (R4)
  (fix: either remove `comparison.yaml` and `synthesis.yaml` from `templates/` until the pipeline supports them, or add `comparisons/`/`synthesis/` to `SOURCE_TYPE_DIRS` AND extend `_build_summary_content` with type-specific renderers)

- `ingest/pipeline.py:712-721` `ingest_source` inject_wikilinks per-page loop — for each newly-created entity/concept page, `inject_wikilinks` is called independently, each time re-scanning ALL wiki pages from disk via `scan_wiki_pages` + per-page `read_text`. A single ingest creating 50 entities + 50 concepts = 100 `inject_wikilinks` calls × N pages = 100·N disk reads. At 5k pages that's 500k reads per ingest — worse than R2-flagged graph/load double-scan. (R4)
  (fix: batch-aware `inject_wikilinks_batch(titles_and_ids, pages)` that scans each page once and checks for all new titles; compile N patterns into a single alternation; write back once)

- `compile/compiler.py:199-276` `detect_source_drift` — calls `find_changed_sources(..., save_hashes=False)` but the `elif deleted_keys:` branch at 192-194 STILL writes the manifest to persist pruning. `detect_source_drift` is advertised as read-only (the `save_hashes=False` kwarg exists for this caller per 127-129 docstring), yet a wiki with deleted raw sources triggers silent manifest mutation on every `kb_detect_drift` call. Violates the documented contract. (R4)
  (fix: split `save_hashes` into `save_template_hashes` + `prune_deleted`; `detect_source_drift` passes both False; or doc-note that deletion pruning is always persisted because stale entries break subsequent reads)


- `mcp/core.py` `kb_compile_scan` — no `wiki_dir` plumbing. (Cycle 6 AC2 closed `kb_detect_drift`, `kb_evolve`, `kb_graph_viz`; cycle 8 closed `kb_stats` and `kb_verdict_trends`.)
  (fix: extend the Cycle-6 pattern — `wiki_dir: str | None = None` converted to `Path` and forwarded to the library function; mirror `kb_lint`'s Phase 5.0 plumbing)

- `query/engine.py:131,717` vector-index path ignores `wiki_dir` — `rebuild_vector_index(wiki_dir)` writes to `wiki_dir.parent / ".data" / "vector_index.db"`, but both `search_pages` and `query_wiki` check `PROJECT_ROOT / VECTOR_INDEX_PATH_SUFFIX`. A custom-project query can have a valid sibling vector index and still report/use BM25-only; worse, if the repo-default vector DB exists, the static `search_mode` gate is computed from the wrong project. (2026-04-18 two-round review R1)
  (fix: derive `vec_path` with `kb.query.embeddings._vec_db_path(wiki_dir or WIKI_DIR)` in both vector search and `search_mode` classification; add a custom `wiki_dir` regression with a temp `.data/vector_index.db`)

- `query/engine.py:175,228-250` `_flag_stale_results` defaults to `PROJECT_ROOT` even when `search_pages(wiki_dir=tmp_wiki)` loaded pages from a custom project. Source refs like `raw/articles/foo.md` are checked under the repo root, so stale markers are false-negative when only the temp raw source changed and false-positive if the same ref exists in the production checkout with a newer mtime. (2026-04-18 two-round review R1)
  (fix: pass `project_root=wiki_dir.parent` from `search_pages`; when `wiki_dir is None`, preserve `PROJECT_ROOT`; add a temp wiki/raw test that proves stale marking follows the override)

- `mcp/health.py:65-83,121-135` `kb_lint(wiki_dir=...)` and `kb_evolve(wiki_dir=...)` append feedback-derived sections from default `FEEDBACK_PATH`. The main lint/evolve report is scoped to the override, but "Low-Trust Pages" and "Coverage Gaps" can leak production feedback into a temp/demo project and point at page IDs that do not exist there. (2026-04-18 two-round review R2)
  (fix: derive `feedback_path = wiki_path.parent / ".data" / "feedback.json"` when `wiki_dir` is provided and pass it into `get_flagged_pages(path=...)` / `get_coverage_gaps(path=...)`; cover both tools with custom `wiki_dir` tests)

- `evolve/analyzer.py:24-60` `analyze_coverage` orphan-concept backlinks via unresolved `build_backlinks` — `build_backlinks` in `compile/linker.py:100` skips bare-slug wikilinks (no resolver, unlike `build_graph`). A concept referenced only via bare slug `[[foo]]` is falsely reported as orphan. `find_connection_opportunities` uses `build_graph` which DOES resolve bare slugs, creating inconsistency within the same evolve report: orphan list disagrees with graph edges. (R4)
  (fix: centralize bare-slug resolution so both `build_graph` and `build_backlinks` use the same resolver; or pass the resolved graph into `build_backlinks`)

- `ingest/pipeline.py:682-693 + compile/compiler.py:117-196` manifest hash key inconsistency under concurrent ingest — `_is_duplicate_content` (102) calls `load_manifest` to check whether ANY entry matches `source_hash`. If caller A is mid-ingest of `raw/articles/foo.md` (passed dedup at 566 but not yet written manifest at 688), caller B starts ingest of an IDENTICAL-content `raw/articles/foo-copy.md` — B's `_is_duplicate_content` sees no match (A hasn't saved), B proceeds to full extraction + page writes, BOTH succeed and write to manifest. Wiki now has TWO summary pages with identical content but different titles. R2 flagged the duplicate-check race; R5 specifies the **window**: the entire LLM extraction (~30 seconds) + all 11 ingest stages between dedup-check and manifest-save is unprotected. (R5)
  (fix: hold `file_lock(manifest_path)` across the entire `ingest_source` body OR write a "claim" entry to manifest as `{source_ref: "in_progress:{hash}"}` immediately after the dedup check, with `try/finally` to either commit the real hash on success or remove the claim on failure)

- `utils/wiki_log.py:36-46` reader sees torn last line during concurrent append — `lint/checks.py:138 _INDEX_FILES = ("index.md", "_sources.md", "_categories.md", "log.md")` so any lint pass that reads `log.md` reads the file while ingest is mid-`f.write(entry)`. On Windows, text-mode `\n→\r\n` translation makes a single `f.write("- 2026-04-13 | ingest | ...\n")` non-atomic at the OS level; reader can see the entry up to the `\r` but not the `\n`. Lint's split-by-lines parser silently drops the truncated entry. R2 flagged the file's lack of a lock; R5 is the **specific cross-tool reader symptom**: the lint report appears clean while the log truly contains the entry — no warning surfaces. (R5)
  (fix: switch `wiki_log.py` writes to `newline="\n"` open mode for consistency with atomic-writes, AND wrap append in `file_lock(log_path)`; readers in lint should also acquire the lock for the brief read)

- `mcp/core.py:108-117` + `mcp/quality.py:99-102,282-283` silent-degradation sites — remaining MCP sites still use the identical "log warning + use empty default" pattern. A corrupt store or unavailable dependency can look like a legitimate empty project instead of a degraded result. (R5; cycle 7 addressed verdict_history + feedback_flagged_pages only)
  (fix: standardize a `_safe_call(fn, fallback, label)` helper that logs warnings AND attaches `{label}_error: str(e)` to the returned report so the user sees "verdict_history unavailable: …" alongside the rest of the lint output)

### LOW

- `tests/test_compile.py` `test_compile_loop_does_not_double_write_manifest` monkeypatch at module level — the CRITICAL cycle 1 item 14 regression test uses `monkeypatch.setattr(pipeline, "save_manifest", ...)` AND `monkeypatch.setattr(compiler_mod, "save_manifest", ...)` to count calls. If `save_manifest` is ever relocated or renamed in the future, the test passes silently with call_count=0 instead of failing loudly. Surfaced by the 2026-04-15 post-PR 2-round review (Sonnet round 2). (R6)
  (fix: add a secondary behavioral assertion that doesn't depend on module-level patching — e.g., count actual file writes to the manifest path via `os.stat` inode checks, or inspect manifest contents before/after to verify single-source single-write contract)

- `mcp/core.py` `kb_query` `conversation_context` (~70-83) — capped at `MAX_QUESTION_LEN * 4` chars but not stripped of control chars / role headers; passed verbatim to the rewriter LLM in the `use_api` branch. (R1)
  (fix: strip control chars + explicit role-tag patterns; wrap in `<prior_turn>…</prior_turn>` sentinel for LLM)

- `tests/` missing coverage — no focused test for `_build_query_context` tier-budget logic (`engine.py:235-324`) or `_flag_stale_results` edge cases (missing `sources`, non-ISO `updated`, mtime-eq-page-date). (R1)
  (fix: parametric test asserting per-tier byte budgets given sized summaries; stale-flag edge cases)

- `mcp/app.py:15-36` FastMCP `instructions` block — 25-line bulleted summary duplicating the first line of every tool docstring; sent on every session init. When a tool description changes both must be edited; thematic grouping already broken (`kb_detect_drift` / `kb_graph_viz` / `kb_verdict_trends` appended out-of-order). No anchor connecting the block to the registry. (R3)
  (fix: generate the instructions programmatically from the FastMCP tool registry; or replace with a one-paragraph pointer to `kb_list_pages` / CLAUDE.md and let FastMCP's auto tool listing do the work)

- `tests/test_mcp_*.py`, `test_v098_fixes.py`, `test_v099_phase39.py`, `test_drift_detection_v094.py` — five ad-hoc helpers (`_setup_quality_paths`, `_setup_browse_dirs`, `_setup_project`, `_patch_source_type_dirs`, `_patch_source_dirs`) re-invent the same monkeypatch dance over slightly different `WIKI_*` / `.data/` subsets, across both `kb.config` AND importing modules (because of `from kb.config import X` re-binding). None in `conftest.py`; each file copy-pastes a variant and risks missing a global. Phase 5's new globals (hot.md, overview.md, captures/, schema.md, vector_index.db, ingest_locks/, pagerank.json) each require updating all five OR more leaks. (R3)
  (fix: single `tmp_kb_env` fixture in `conftest.py` that reflects `kb.config`'s `WIKI_*` / `RAW_DIR` / `PROJECT_ROOT` / `*_PATH` constants and monkeypatches BOTH `kb.config` AND every module that imported them via `sys.modules` reflection; collapse all five helpers)

- `src/kb/__init__.py` + `src/kb/cli.py:143` + `src/kb/mcp_server.py:10` — three import layers to boot MCP: `kb mcp` → `cli.mcp()` → `from kb.mcp_server import main` → `from kb.mcp import mcp` → tool modules. Each layer runs an `__init__.py` and a `sys.modules` lookup. Harmless (<5 ms) but blocks clean "click entry → tool module" import-time profiling. (R3)
  (fix: collapse `kb/mcp_server.py` into `kb.mcp` as `kb.mcp.main`; `kb = "kb.mcp:main"` script entry in `pyproject.toml`; CLI's `kb mcp` becomes `from kb.mcp import main`)

- `ingest/__init__.py` empty package — `__init__.py` is only a docstring/header; no `__all__`, no public-API curation. Every caller reaches into `kb.ingest.pipeline`/`kb.ingest.extractors`/`kb.ingest.contradiction`/`kb.ingest.evidence` directly. R1 flagged top-level package; the pattern recurs inside `kb.ingest`. Phase 5 additions (kb_capture, URL adapters, chunk-indexing hooks) will keep reaching into ever-deeper submodules unless a seam is created now. (R4)
  (fix: add `from kb.ingest.pipeline import ingest_source; __all__ = ["ingest_source"]` — single public entry point)

- `mcp/browse.py:48-73` `kb_read_page` case-insensitive fallback — the `subdir.glob("*.md")` loop iterates every file for every miss, lowercase-compares stems, picks first match. On collision (two files differing only in case) the fallback is insertion-order-dependent: first file `glob` returns wins. Two pages with canonical IDs differing only in case shadow each other. Logger warning notes the match but doesn't mention the ambiguity. (R4)
  (fix: if >1 case-insensitive match exists, return `Error: ambiguous page_id — multiple files match {page_id} case-insensitively: {matches}`; or lowercase all page IDs at slug time and drop the fallback)

- `config.py:7` `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` — assumes package layout `src/kb/config.py` always sits 3 levels under PROJECT_ROOT. When installed via `pip install -e .` from checkout it works; installed from a built wheel into `site-packages/kb/config.py`, it points at `site-packages/kb/../../` — the `site-packages` directory itself, NOT the user's project. `PROJECT_ROOT` then derives `RAW_DIR`, `WIKI_DIR`, etc. Package only works when installed via `-e` from a checkout containing `raw/`+`wiki/`; undocumented. (R4)
  (fix: prefer `os.environ.get("KB_PROJECT_ROOT", ...)` with explicit detection — walk up from cwd looking for `pyproject.toml` + `wiki/`, fall back to the heuristic; document in README that the package is checkout-local, not pip-installable as a library)

- `utils/io.py:18,44` `tempfile.mkstemp(dir=path.parent)` + `Path(tmp_path).replace(path)` on network mounts — if `path.parent` is an offline OneDrive/SMB mount, `mkstemp` succeeds locally then `replace` fails; temp file is unlinked on `BaseException`, but on partial network failure (write fd closes ok, replace times out), the temp file may linger if `unlink` also times out. No retry path, no orphaned-temp cleanup. (R4)
  (fix: document that the package is not safe on network drives; or add startup orphan-temp sweep — find `*.tmp` siblings of known data files older than 1h and unlink)


---

## Phase 5 — Community followup proposals (2026-04-12)

<!-- Feature proposals sourced from Karpathy X post (Apr 2, 2026), gist thread, and 12+ community fork repos.
     Full rationale, attribution, and sources: research/karpathy-community-followup-2026-04-12.md
     These are FEATURE items, not bugs — severity buckets here = LEVERAGE (High / Medium / Low).
     "effort" in the parenthetical replaces "fix" in the bug format. -->

### RECOMMENDED NEXT SPRINT — Karpathy gist re-evaluation (2026-04-13)

<!-- Ranked priority derived from re-reading Karpathy's gist against current state.
     All items below already exist as entries in the leverage-grouped subsections — this block only SEQUENCES them.
     Rationale: research/karpathy-community-followup-2026-04-12.md §Prioritized roadmap additions + 2026-04-13 ranking pass.
     Ranking axes: (1) Karpathy-verbatim fidelity, (2) unsolved-gap coverage, (3) effort vs leverage. -->

**Tier 1 — Karpathy-verbatim behaviors the project can't yet reproduce:**
<!-- Tier 1 #1 (`kb_query --format=…` output adapters) SHIPPED in Phase 4.11 (2026-04-14). -->
<!-- Tier 1 #2 (`kb_lint --augment`) SHIPPED in Phase 5.0 (2026-04-15). -->
1. `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen — makes the wiki retrievable by other agents; renderers over existing frontmatter/graph. Cross-ref: HIGH LEVERAGE — Output-Format Polymorphism.
2. `wiki/_schema.md` vendor-neutral schema + `AGENTS.md` thin shim — Karpathy: *"schema is kept up to date in AGENTS.md"*; enables Codex / Cursor / Gemini CLI / Droid portability without forking schema per tool. Cross-ref: LOW LEVERAGE — Operational.

**Tier 2 — Epistemic integrity (unsolved-gap closers every community voice flagged):**
5. `belief_state: confirmed|uncertain|contradicted|stale|retracted` frontmatter — cross-source aggregate orthogonal to per-source `confidence`. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
6. `kb_merge <a> <b>` + duplicate-slug lint check — catches `attention` vs `attention-mechanism` drift; top-cited contamination failure mode in the thread. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
7. `kb_query` coverage-confidence refusal gate — refuses low-signal queries with rephrase suggestions instead of synthesizing mediocre answers. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
8. Inline `[EXTRACTED]` / `[INFERRED]` / `[AMBIGUOUS]` claim tags with `kb_lint_deep` sample verification — complements page-level `confidence` with claim-level provenance; directly answers "LLM stated this as sourced fact but it's not in the source." Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.

**Tier 3 — Ambient capture + security rail (distribution UX):**
9. `.llmwikiignore` + pre-ingest secret/PII scanner — missing safety rail given every ingest currently sends full content to the API. Cross-ref: HIGH LEVERAGE — Ambient Capture & Session Integration.
10. `SessionStart` hook + `raw/` file watcher + `_raw/` staging directory — ship as a three-item bundle that eliminates the "remember to ingest" step. Cross-ref: HIGH LEVERAGE — Ambient Capture & Session Integration.

**Recommended next target:** #1 (`/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen). Reasons: with output adapters (Phase 4.11) and reactive gap-fill (Phase 5.0) shipped, the next-highest Karpathy-fidelity item is the machine-consumable publish format — renderers over existing frontmatter + graph, low effort, makes the wiki itself a retrievable source for other agents. Contained blast radius in `kb.compile.publish` (new module) + compile-pipeline hook.

**Already in flight (excluded from ranking):** `kb_capture` MCP tool (spec landed 2026-04-13 in `docs/superpowers/specs/2026-04-13-kb-capture-design.md`), `wiki/purpose.md` KB focus document (shipped 2026-04-13, commit `d505dca`).

**Explicit scope-out from this re-evaluation pass (keep deferred to Phase 6 or decline):**
- `kb_consolidate` sleep-cycle pass — high effort; overlaps with existing lint/evolve; defer until lint is load-bearing.
- Hermes-style independent cross-family supervisor — infra-heavy (second provider + fail-open policy); Phase 6.
- `kb_drift_audit` cold re-ingest diff — defer until `kb_merge` + `belief_state` land (surface overlap).
- `kb_synthesize [t1, t2, t3]` k-topic combinatorial synthesis — speculative; defer until everyday retrieval is saturated.
- `kb_export_subset --format=voice` for mobile/voice LLMs — niche; defer until a second-device use case emerges.
- Multi-agent swarm + YYYYMMDDNN naming + capability tokens (redmizt) — team-scale pattern; explicit single-user non-goal.
- RDF/OWL/SPARQL native storage — markdown + frontmatter + wikilinks cover the semantic surface.
- Ed25519-signed page receipts — git log is the audit log at single-user scale.
- Full RBAC / compliance audit log — known and acknowledged ceiling; document as a README limitation rather than fix.
- Hosted multiplayer KB over MCP HTTP/SSE — conflicts with local-first intent.
- `qmd` CLI external dependency — in-process BM25 + vector + RRF already ships.
- Artifact-only lightweight alternative (freakyfractal) — sacrifices the persistence that is the reason this project exists.
- FUNGI 5-stage rigid runtime framework — same quality gain expected from already-deferred two-step CoT ingest.
- Synthetic fine-tuning of a personal LLM on the compiled wiki — over the horizon.

### HIGH LEVERAGE — Epistemic Integrity 2.0

- `models/` `belief_state` frontmatter — add `belief_state: confirmed|uncertain|contradicted|stale|retracted` field orthogonal to `confidence`. `belief_state` is the cross-source aggregate (lint-propagated); `confidence` stays per-source attribution. Query engine filters/weights on belief_state; lint updates it when contradictions or staleness are detected. Source: epistemic-mapping proposal (dangleh, gist).
  (effort: Low — one frontmatter field + propagation rules in `lint/checks.py` and query ranking)

- `ingest/pipeline.py` `source` subsection-level provenance — allow `source: raw/file.md#heading` or `raw/file.md:L42-L58` deep-links in frontmatter; ingest extractor captures heading context so citations point at the actual section that grounds the claim. Source: Agent-Wiki (kkollsga, gist — two-hop citation traceability).
  (effort: Medium — extractor update + citation renderer + backlink resolver for the new form)

- `lint/drift.py` `kb_drift_audit` — cold re-ingest a random sample of raw sources with no prior wiki context, diff against current wiki pages, surface divergence as "potential LLM drift" warnings. Different from existing `kb_detect_drift` which checks source mtime changes; this catches *wiki-side* drift where compilation has diverged from source truth. Source: Memory Drift Prevention (asakin, gist — cites ETH Zurich study: auto-generated context degraded 5/8 cases).
  (effort: Medium — new module; reuse existing `ingest_source` with `wiki_dir=tmp` then diff)

- `compile/merge.py` `kb_merge <a> <b>` + `lint/checks.py` duplicate-slug — lint detects near-duplicate slugs (`attention` vs `attention-mechanism`, `rag` vs `retrieval-augmented`); `kb_merge` MCP tool merges two pages, updates all backlinks across `wiki/` and `wiki/outputs/`, archives absorbed page to `wiki/archive/` with a redirect stub, one git commit per merge. Source: Louis Wang.
  (effort: Medium — merge is the new work; dup-slug detection adds one lint check)

- `query/engine.py` coverage-confidence gate — compute mean cosine similarity between query and top-K results; if <0.45, return "low confidence" warning with LLM-suggested rephrasings instead of synthesizing a mediocre answer. Source: VLSiddarth Knowledge-Universe.
  (effort: Low — threshold check after existing hybrid search; use scan-tier LLM for rephrasing)

- `models/` `authored_by: human|llm|hybrid` frontmatter — formalize human-written vs LLM-generated pages; query engine applies mild weight boost to human-authored; lint flags user-declared human pages that have been auto-edited by ingest without flag removal. Source: PKM-vs-research-index critique (gpkc, gist).
  (effort: Low — one field + ranking hook + lint rule)

- `ingest/pipeline.py` `lint/semantic.py` inline claim-level confidence tags — emit `[EXTRACTED]`, `[INFERRED]`, `[AMBIGUOUS]` inline markers in wiki page bodies during ingest; modify ingest LLM prompts to annotate individual claims at source; `kb_lint_deep` spot-verifies a random sample of EXTRACTED-tagged claims against the raw source file, flagging hallucinated attributions. Complements page-level `confidence` frontmatter without replacing it; directly answers "LLM stated this as sourced fact but it's not in the source." Source: llm-wiki-skill confidence annotation + lint verification model.
  (effort: Medium — ingest prompt update + regex claim parser + lint spot-check against raw source text)

### HIGH LEVERAGE — Output-Format Polymorphism

<!-- `query/formats/` `kb_query --format=…` adapters SHIPPED in Phase 4.11 (2026-04-14). -->

- `compile/publish.py` `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` — auto-generate AI-agent-consumable outputs alongside markdown during compile: each page gets `.txt`/`.json` siblings; wiki root gets `/llms.txt`, `/graph.jsonld`, `/sitemap.xml`. Makes the wiki itself a retrievable source for other agents. Source: Pratiyush/llm-wiki.
  (effort: Low — renderers over existing frontmatter + graph)

### MEDIUM LEVERAGE — Synthesis & Exploration

- `lint/consolidate.py` `kb_consolidate` — scheduled async background pass modeled on biological memory consolidation: NREM (new events → concepts, cross-event pattern extraction), REM (contradiction detection → mark old edges `superseded` rather than delete), Pre-Wake (graph health audit). Runs as nightly cron at scan tier. Source: Anda Hippocampus (ICPandaDAO).
  (effort: High — three distinct sub-passes; overlaps with existing lint/evolve but with "superseded" edge state as new primitive)

- `query/synthesize.py` `kb_synthesize [t1, t2, t3]` — k-topic combinatorial synthesis: walks paths through the wiki graph across a k-tuple of topics to surface cross-domain connections. New query mode beyond retrieval. Source: Elvis Saravia reply (*"O(n^k) synthesis across k domains — stoic philosophy × saas pricing × viral content × parenting"*).
  (effort: Medium — graph traversal + synthesis prompt; budget-gate k≥3 since path count explodes)

- `export/subset.py` `kb_export_subset <topic> --format=voice` — emit a topic-scoped wiki slice (standalone blob) loadable into voice-mode LLMs or mobile clients. Addresses *"interactive podcast while running"* use case. Source: Lex-style reply.
  (effort: Low — topic-anchored BFS + single-file markdown bundle)

### HIGH LEVERAGE — Ambient Capture & Session Integration

- `ingest/session.py` — auto-ingest Claude Code / Codex CLI / Cursor / Gemini CLI session JSONLs as raw sources. Distinct from `kb_capture` (user-triggered, any text) and deferred "conversation→KB promotion" (positive-rated query answers only): this is ambient, runs on every session. Source: Pratiyush/llm-wiki.
  (effort: Medium — JSONL parsers per agent + dedup against existing raw/conversations/)

- `hooks/` `SessionStart` hook + `raw/` file watcher — hooks auto-sync on every Claude Code launch; file watcher with debounce triggers ingestion on new files in `raw/` without explicit CLI invocation. Source: Pratiyush/llm-wiki + Memory-Toolkit (IlyaGorsky, gist).
  (effort: Low — Claude Code hook + `watchdog` file observer)

- `ingest/filter.py` `.llmwikiignore` + secret scanner — pre-ingest regex-based secret/PII filter (API keys, tokens, passwords, paths on `.llmwikiignore`); rejects or redacts before content leaves local. Missing safety rail given every ingest currently sends full content to the API. Source: rohitg00 LLM Wiki v2 + Louis Wang security note.
  (effort: Low — `detect-secrets`-style regex list + glob-pattern ignore)

- `_raw/` staging directory — vault-internal drop-and-forget directory for clipboard pastes / rough notes; next `kb_ingest` promotes to `raw/` and removes originals. Distinct from `raw/` (sourced documents) and deferred `kb_capture` (explicit tool). Source: Ar9av/obsidian-wiki.
  (effort: Low — directory convention + promotion step in ingest)

- `ingest/pipeline.py` per-subdir ingest rules — infer source type from `raw/web/`, `raw/papers/`, `raw/transcripts/` subdirectory rather than requiring explicit `--type` argument. Source: Fabian Williams.
  (effort: Low — path→type lookup table; `--type` stays as override)

### MEDIUM LEVERAGE — Refinements to existing Phase 5 deferred items

- Deferred "multi-signal graph retrieval" — use empirical weights 3 (direct link) / 4 (source-overlap) / 1.5 (Adamic-Adar) / 1 (type-affinity). Source: nashsu/llm_wiki (concrete ratios from production use).
  (effort: N/A — parameter choice for the existing deferred item)

- Deferred "community-aware retrieval boost" — Louvain intra-edge density <0.15 = "sparse/weak" threshold; surface sparse communities in `kb_evolve`. Source: nashsu.
  (effort: N/A — threshold choice)

- Deferred "stale flagging at query time" — per-platform decay half-lives: HuggingFace 120d, GitHub 180d, StackOverflow 365d, arXiv 1095d, Wikipedia 1460d, OpenLibrary 1825d; ×1.1 volatility multiplier on LLM/React/Docker/Claude topics. Replaces single-threshold staleness. Source: VLSiddarth.
  (effort: Low delta on the existing deferred item — `SOURCE_DECAY_DAYS` dict in config)

- `query/engine.py` `CONTEXT_TIER1_BUDGET` → 60/20/5/15 split (wiki pages / chat history / index / system) instead of single 20K-of-80K split. Source: nashsu.
  (effort: Low — replace single constant with proportional calculator)

- Deferred "graph topology gap analysis" — expose as card types: "Isolated (degree ≤ 1)", "Bridge (connects ≥ 3 clusters)", "Sparse community (cohesion < 0.15)" — each with one-click trigger that dispatches `kb_evolve --research` on the specific gap. Source: nashsu.
  (effort: N/A — card-type taxonomy for existing deferred item)

### LOW LEVERAGE — Testing Infrastructure

- `tests/test_e2e_demo_pipeline.py` hermetic end-to-end pipeline test — single test driving `ingest_source` → `query_wiki` → `run_all_checks` over the committed `demo/raw/karpathy-x-post.md` and `demo/raw/karpathy-llm-wiki-gist.md` sources with the synthesis LLM stubbed. Catches cross-module integration regressions (ingest ↔ compile manifest ↔ query engine ↔ lint runner) that single-module unit tests miss. Uses `ingest_source(..., extraction=dict)` to skip LLM extraction entirely; only monkeypatches the synthesis `call_llm` at `kb.query.engine.call_llm`, plus the module-level constants `RAW_DIR`/`PROJECT_ROOT`/`WIKI_CONTRADICTIONS`/`HASH_MANIFEST` at both `kb.config.X` and each consuming module. Deferred in favor of the active Phase 4.5 bug-fix backlog. Design spec content was drafted in-session but not committed; rewrite from this bullet when picked up. Source: Layer 1 of the three-layer e2e strategy (Layer 2 = MCP contract test via `fastmcp.Client` in-process; Layer 3 = gated `@pytest.mark.live` smoke test against real Anthropic API).
  (effort: Low — ~100-line single test file, no new fixtures or dependencies; `tmp_project` in `tests/conftest.py` is sufficient. Asserts page IDs in `pages_created`/`pages_updated`, frontmatter source-list merge on shared entities, `wikilinks_injected` on second ingest, `[source: …]` citation round-trip, and `lint_report["summary"]["error"] == 0`. Run cadence: every CI, hermetic, ~1s.)

### LOW LEVERAGE — Operational

- `wiki/_schema.md` vendor-neutral single source of truth — move project schema (page types, frontmatter fields, wikilink syntax, operation contracts) out of tool-convention files and into `wiki/_schema.md` co-located with the data it describes. Existing `CLAUDE.md` / future `AGENTS.md` / `GEMINI.md` stay as thin (~10-line) vendor shims that point at `_schema.md` for project rules. Schema is machine-parseable (fenced YAML blocks under markdown headers) and validated by lint on every ingest. Innovation vs. the common "symlink AGENTS.md → CLAUDE.md" pattern: the schema lives WITH the wiki, portable across agent frameworks (Codex, Cursor, Gemini CLI, shell scripts). Follows the existing `_sources.md` / `_categories.md` convention. Source: Karpathy tweet (schema portability prompt) + project design.
  (effort: Medium — (a) write `wiki/_schema.md` starter as self-describing meta page; (b) `kb.schema.load()` parser; (c) `kb_lint` integration validates frontmatter against schema; (d) `schema_version` + `kb migrate` CLI; (e) optional multi-persona sections `### for ingest` / `### for query` / `### for review` so agents load scoped context. Defer vendor shim updates — keep `CLAUDE.md` unchanged until user chooses to slim it)

- `cli.py` `kb search <query>` subcommand — colorized terminal output over the existing hybrid search; `kb search --serve` exposes a minimal localhost web UI. Power-user CLI over the same engine the LLM already uses via MCP. Source: Karpathy tweet (*"small and naive search engine, web ui and CLI"*).
  (effort: Low — Click command + Flask/FastAPI localhost UI)

- Git commit receipts on ingest — emit `"four new articles appeared: Amol Avasari, Capability Overhang, CASH Framework, Success Disasters"` style summary with commit hash and changed files per source. Source: Fabian Williams.
  (effort: Low — wrap existing ingest return dict with a formatter)

### HIGH LEVERAGE — Ingest & Query Convenience

- `mcp/core.py` `kb_ingest` URL-aware 5-state adapter — upgrade `kb_ingest`/`kb_ingest_content` to accept URLs alongside file paths; URL routing table in `kb.config` maps patterns to source type + `raw/` subdir + preferred adapter; before executing, checks 5 explicit states: `not_installed`, `env_unavailable`, `runtime_failed`, `empty_result`, `unsupported` — each emits a specific recovery hint and offers manual-paste fallback. Eliminates the "run crwl, save file, then kb_ingest file" three-step friction. Source: llm-wiki-skill adapter-state.sh 5-state model.
  (effort: Medium — URL routing table in config + per-state error handling + adapter dispatcher)

- `mcp/core.py` `kb_delete_source` MCP tool — remove raw source file and cascade: delete source summary wiki page, strip source from `source:` field on shared entity/concept pages without deleting them, clean dead wikilinks from remaining wiki pages, update `index.md` and `_sources.md`. Fills the only major operational workflow gap not addressed by existing tooling.
  (effort: Medium — cascade deletion logic + backlink cleanup + atomic index/sources update)

- `mcp/core.py` `kb_query` `save_as` parameter — immediately create a `wiki/synthesis/{slug}.md` page from the query answer with citations mapped to `source:` refs and proper frontmatter; no feedback gate required, faster knowledge accumulation for high-confidence answers. Coexists with feedback-gated conversation→KB promotion as the immediate save path. Source: llm-wiki-agent interactive save.
  (effort: Low — slug from question + frontmatter builder + atomic write; CLI `--save` flag mirrors it)

- `evolve/analyzer.py` `kb_evolve mode=research` — for each identified coverage gap, decompose into 2–3 web search queries, fetch top results via fetch MCP, save to `raw/articles/` via `kb_save_source`, return file paths for subsequent `kb_ingest`; capped at 5 sources per gap, max 3 rounds (broad → sub-gaps → contradictions). Turns evolve from advisory gap report into actionable source acquisition pipeline. Source: claude-obsidian autoresearch skill.
  (effort: Medium — gap decomposition prompt + fetch MCP integration + 3-round loop with source cap)

- `wiki/purpose.md` KB focus document — lightweight file defining KB goals, key questions, and research scope; included in `kb_query` context and ingest system prompt so the LLM biases extraction toward the KB's current direction. Source: nashsu/llm_wiki purpose.md.
  (effort: Low — one markdown file + read in query_wiki + prepend in ingest system prompt)

### MEDIUM LEVERAGE — Search & Indexing

- `query/bm25.py` `query/embeddings.py` chunk-level sub-page indexing — split wiki pages into topically coherent chunks using Savitzky-Golay boundary detection (embed sentences with model2vec, compute adjacent cosine similarities, SG smoothing 5-window 3rd-order polynomial, find zero-crossings as topic boundaries); each chunk indexed as `<page_id>:c<n>`; query engine scores chunks, deduplicates to best chunk per page, loads full pages for synthesis. Resolves the weakness where relevant content is buried in long pages. Source: garrytan/gbrain semantic.ts + sage-wiki FTS5 chunking.
  (effort: High — SG chunking module + BM25 index schema change + chunk-to-page dedup aggregation layer)

- `compile/linker.py` cross-reference auto-linking — when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` added to A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`. Builds graph density automatically without requiring typed relations. Source: garrytan/gbrain ingest cross-reference link creation.
  (effort: Low — post-injection pass over co-mentioned entity pairs; reuses existing inject_wikilinks infrastructure)

- `lint/checks.py` `query/engine.py` PageRank-prioritized semantic lint sampling — when `kb_lint_deep` must limit its page budget, select pages by PageRank descending rather than arbitrary order; high-authority pages with quality issues have outsized downstream impact on citing pages. Source: existing `graph_stats` PageRank scores.
  (effort: Low — sort by graph_stats PageRank before sampling; zero new infrastructure required)

### MEDIUM LEVERAGE — Page Lifecycle & Quality Signals

- `models/` `status` frontmatter field — `status: seed|developing|mature|evergreen` orthogonal to `confidence`; seed = stub/single-source, developing = multi-source but incomplete, mature = well-sourced + reviewed, evergreen = stable reference. `kb_evolve` targets seed pages; lint flags mature pages not updated in 90+ days as potentially stale; query engine applies mild ranking boost to mature/evergreen. Source: claude-obsidian page lifecycle.
  (effort: Low — one frontmatter field + rule hooks in evolve, lint, and query ranking)

- `wiki/` inline quality callout markers — embed `> [!contradiction]`, `> [!gap]`, `> [!stale]`, `> [!key-insight]` callouts at the point of relevance in wiki page bodies; lint parses callouts for aggregate reporting ("3 pages have unresolved contradictions"); ingest auto-inserts `[!contradiction]` when auto-contradiction detection fires; renders natively in Obsidian. Source: claude-obsidian custom callout system.
  (effort: Low — callout emitter in ingest/contradiction.py + lint parser for aggregate counts)

- `wiki/hot.md` wake-up context snapshot — ~500-word compressed context updated at session end (recent facts, recent page changes, open questions); read at session start via `SessionStart` hook; survives context compaction and session boundaries; enables cross-session continuity without full wiki crawl. Source: MemPalace concept + claude-obsidian hot cache.
  (effort: Low — append-on-ingest + SessionStart hook reads + one markdown file)

- `wiki/overview.md` living overview page — auto-revised on every ingest as the final pipeline step; always-current executive summary across all sources; updated not replaced on each ingest. Source: llm-wiki-agent living overview.
  (effort: Low — scan-tier LLM over index.md + top pages; one file auto-updated per ingest)

### MEDIUM LEVERAGE — Knowledge Promotion & Ingest Quality

- `query/engine.py` `feedback/store.py` conversation→KB promotion — positively-rated query answers (rating ≥ 4) auto-promote to `wiki/synthesis/{slug}.md` pages with citations mapped to `source:` refs; coexists with `save_as` parameter (immediate, no gate) as the feedback-gated deferred path. Source: garrytan/gbrain maintain skill.
  (effort: Medium — feedback store hook + synthesis page writer + conflict check against existing pages)

- `ingest/pipeline.py` two-step CoT ingest analysis pass — split ingest into: (1) analysis call producing entity list + connections to existing wiki + contradictions + wiki structure recommendations; (2) generation call using analysis as context. Improves extraction quality and enables richer contradiction flagging; feeds Phase 4 auto-contradiction detection. Source: nashsu/llm_wiki two-step chain-of-thought.
  (effort: Medium — split single ingest LLM call into two sequential calls with analysis-as-context)

### Phase 6 candidates (larger scope, not yet scheduled)

- Hermes-style independent quality-gate supervisor — different-model-family validator (not same-family self-review) before page promotion. Source: Secondmate (@jumperz, via VentureBeat).
  (effort: High — adds a second provider; challenges fail-open defaults)

- Mesh sync for multi-agent writes — last-write-wins with timestamp conflict resolution; private-vs-shared scoping (personal preferences private, architecture decisions shared). Source: rohitg00.
  (effort: High — assumes multi-writer concurrency model)

- Hosted MCP HTTP/SSE variant — multi-device access (phone Claude app, ChatGPT, Cursor, Claude Code) reading/writing the same KB. Source: Hjarni/dev.to.
  (effort: High — MCP transport + auth; currently stdio-only)

- Personal-life-corpus templates — Google Takeout / Apple Health / AI session exports / bank statements as a domain starter kit. Privacy-aware ingest layered on `.llmwikiignore`. Source: anonymous personal-data-RAG reply.
  (effort: Medium — per-source-type extractor templates; depends on `.llmwikiignore` landing first)

- Multi-signal graph retrieval — BM25 seed → 4-signal graph expansion: direct wikilinks ×3 + source-overlap ×4 + Adamic-Adar shared-neighbor similarity ×1.5 + type-affinity ×1; nodes ranked by combined BM25 + graph score with budget-proportional context assembly. Prerequisite: typed semantic relations (below). Source: nashsu/llm_wiki relevance model.
  (effort: High — graph score combination layer + per-signal weight tuning + typed relations as prerequisite)

- Typed semantic relations on graph edges — extract 6 relation types via keyword matching: `implements`, `extends`, `optimizes`, `contradicts`, `prerequisite_of`, `trades_off`; stored as edge attribute in NetworkX + SQLite; enables typed graph traversal in `kb_query`. Prerequisite for multi-signal retrieval. Source: sage-wiki configurable ontology.
  (effort: Medium — relation extractor pass + NetworkX/SQLite graph schema update)

- Temporal claim tracking — `valid_from`/`ended` date windows on individual claims within pages; enables staleness/contradiction resolution at claim granularity rather than page granularity. Requires new SQLite KG schema. Source: MemPalace SQLite KG pattern.
  (effort: High — claim-level SQLite schema + ingest extractor update + query-time filtering)

- Semantic edge inference in graph — two-pass graph build: existing wikilink edges as EXTRACTED + LLM-inferred implicit relationships as INFERRED/AMBIGUOUS with confidence 0–1; re-infers only changed pages via content hash cache. Source: llm-wiki-agent.
  (effort: High — 2-pass build logic + confidence-weighted edges + per-page change detection)

- Answer trace enforcement — require synthesizer to tag every factual claim with `[wiki/page]` or `[raw/source]` citation at synthesis time; post-process strips or flags uncited claims as gaps. Source: epistemic integrity requirement.
  (effort: High — synthesis prompt rewrite + citation parser + enforcement pass + graceful fallback)

- Multi-mode search depth toggle (`depth=fast|deep`) — `depth=deep` uses Monte Carlo evidence sampling for complex multi-hop questions; `depth=fast` is current BM25 hybrid. Depends on MC sampling infrastructure. Source: Sirchmunk Monte Carlo evidence sampling.
  (effort: High — MC sampler architecture + budget allocation + fast/deep routing logic)

- Semantic deduplication pre-ingest — embedding similarity check before ingestion to catch same-topic-different-wording duplicates beyond content hash; flag if cosine similarity >0.85 to any existing raw source. Source: content deduplication research.
  (effort: Medium — embed new source + nearest-neighbor check vs existing vector store)

- Interactive knowledge graph HTML viewer — self-contained vis.js HTML export from `kb_graph_viz` with `format=html`; dark theme, search bar, click-to-inspect nodes, Louvain community clustering, edge type legend. Source: llm-wiki-agent graph.html.
  (effort: Medium — vis.js template + Louvain community IDs per node + edge type legend)

- Two-phase compile pipeline + pre-publish validation gate — phase 1: batch cross-source merging before writing; phase 2: validation gate rejects pages with unresolved contradictions or missing required citations. Architecture change to current single-pass compiler. Source: compilation best practices.
  (effort: High — compiler refactor into two phases + validation gate + publish/reject state machine)

- Actionable gap-fill source suggestions — enhance `kb_evolve` to suggest specific real-world sources for each gap ("no sources on MoE, consider the Mixtral paper"). Mostly superseded by `kb_evolve mode=research` (Phase 5) which fetches sources autonomously; keep as fallback for offline/no-fetch environments. Source: nashsu/llm_wiki.
  (effort: Low delta on evolve — add one LLM call per gap; ship only if mode=research is blocked)

### Design tensions to document in README (not items to implement)

- **Container boundary / atomic notes tension (WenHao Yu)** — `kb_ingest` forces a "which page does this merge into?" decision, same failure mode as Evernote's "which folder" and Notion's "which tag". Document that our model merges aggressively and that atomic-note alternative exists.
- **Model collapse (Shumailov 2024, Nature)** — cite in "known limitations": LLM-written pages feeding next LLM ingest degrade across generations; our counter is evidence-trail provenance plus two-vault promotion gate.
- **Enterprise ceiling (Epsilla)** — document explicit scope: personal-scale research KB, not multi-user enterprise; no RBAC, no compliance audit log, file-I/O limits at millions-of-docs scale.
- **Vibe-thinking critique (HN)** — *"Deep writing means coming up with things through the process of producing"*; defend with mandatory human-review gates on promotion, not optional.

---

## Phase 5 pre-merge (feat/kb-capture, 2026-04-14)

<!-- Discovered by 6 specialist reviewers (security, logic, performance, reliability, maintainability, architecture)
     running Rounds 1 and 2 against feat/kb-capture. Primary scope: new kb.capture module + supporting changes.
     Items grouped by severity, keyed by file. Round tag in parens (R1/R2). -->

<!-- 2026-04-17 cleanup pass: R1 HIGH items (fence-break, os.close, yaml_escape double-escape,
     unlink swallow), R1 MEDIUM items (env-var secret false-negative, CAPTURES_DIR.resolve caching,
     80-char collision cap, _write_item_files hardcoded CAPTURES_DIR), R1 LOW items (Authorization Bearer,
     env-var export form, body maxLength, normalised superset unconditionally), R2 rating corrections,
     R3 MEDIUM items (dead slug param, captures_dir threading) — ALL VERIFIED FIXED in current capture.py
     (see commit history). Remaining entries are genuinely open items. -->

### CRITICAL

- `capture.py:341-372, 428-460` two-pass write architecture needed — STRUCTURAL: `alongside_for[i]` is a frozen list built from Phase A slugs and never recomputed after a Phase C slug reassignment. Items 0..i-1 already written to disk retain `captured_alongside` entries pointing at item i's Phase A slug (which was never written) under cross-process collision. Only complete fix is two-pass: Pass 1 = `O_EXCL`-reserve all N slugs with retry; Pass 2 = compute `alongside_for` from finalized slugs, write all files. Documented as "v1 limitation" in `_write_item_files` docstring. (R3)
  (fix: implement two-pass `_write_item_files`; OR keep TODO(v2) marker and document explicitly in `CaptureResult` docstring)

### HIGH

- `capture.py:235-288` `_PROMPT_TEMPLATE` fence handling still uses static delimiters — current code escapes `--- INPUT ---` / `--- END INPUT ---` variants before building the prompt, but `_verify_body_is_verbatim` checks returned bodies against the original normalized content. A faithful LLM return of an escaped delimiter span is dropped as non-verbatim — silent data loss on legitimate user content containing a delimiter-like line. UUID boundaries avoid both injection and delimiter-content loss without mutating user text. (R3, revalidated 2026-04-17)
  (fix: generate `boundary = _secrets.token_hex(16)` per call in `_extract_items_via_llm`; replace static delimiters with `f"<<<INPUT-{boundary}>>>"` / `f"<<<END-INPUT-{boundary}>>>"`; verify absence in input before rendering)

### MEDIUM

- `capture.py:146-161` `_normalize_for_scan` except clause too narrow — `except (ValueError, binascii.Error, UnicodeDecodeError)` does not catch `TypeError`; a future refactor passing non-str to `unquote` would propagate uncaught, silently aborting the normalization pass with no log. (R1)
  (fix: `except Exception: continue` with a comment "normaliser is best-effort; any decode failure silently skips that segment")

- `capture.py:36-56` + `capture.py:40` `_check_rate_limit` per-process scope undocumented — docstring and `_check_rate_limit` body say "sliding 1-hour window" with no mention of per-process scope. MCP server and CLI (once added) each maintain independent deques, effectively doubling the allowed rate. Future developers adding a CLI wrapper will not realize the limit is not global. (R1)
  (fix: add explicit docstring note on per-process scope; use `.data/capture_rate.json` + `atomic_json_write` for system-wide limit if required)

- `capture.py:209-238` `_PROMPT_TEMPLATE` inline string vs templates/ convention — all other LLM prompts live as YAML files in `templates/` loaded via `load_template()`. R2 NIT refined: existing `templates/*.yaml` define JSON-Schema `extract:` fields for `build_extraction_schema()` — a structurally different purpose, so a plain format-string prompt does not fit there. (R1 + R2 NIT)
  (fix: `templates/capture_prompt.txt` in a new `prompts/` subdirectory; OR keep inline but extract to named module-level constant with comment)

- `config.py:40-53` + `CLAUDE.md` architectural contradiction — `CAPTURES_DIR = RAW_DIR / "captures"` places the capture write target inside `raw/`, which CLAUDE.md defines as "Immutable source documents. The LLM reads but **never modifies** files here." `raw/captures/` is the only LLM-written output directory inside `raw/`. (R1)
  (fix: either (a) move `CAPTURES_DIR` to `captures/` at project root, or (b) carve out an explicit exception in CLAUDE.md and the config comment)

- `tests/test_capture.py:21` `CAPTURE_KINDS` implicit re-export — test imports from `kb.capture` rather than its authoritative source `kb.config`. If `capture.py` is refactored to reference `CAPTURE_KINDS` via a different import form, the test import breaks silently. (R1)
  (fix: `from kb.config import CAPTURE_KINDS` in the test; OR explicit re-export in `capture.py`)

- `capture.py:403-435` + `tests/test_capture.py:632-715` yaml_escape double-escape fix lacks round-trip regression test — current tests still use alphanumeric-only titles; no test passes a backslash, double-quote, or embedded newline in the title and asserts `_fm.loads()` round-trip. A future accidental re-introduction of yaml_escape would pass all tests silently. (R2, revalidated 2026-04-17)
  (fix: add `test_title_with_backslash_round_trips` and `test_title_with_double_quote_round_trips` for `r"C:\path\to\file"` and `'"quoted"'`)

### LOW

- `capture.py:137-161` `_normalize_for_scan` iteration bound implicit on `CAPTURE_MAX_BYTES` — decode attempt count is O(input_size / 17) ≈ 2,941 max at the 50KB cap; bound is load-bearing on `CAPTURE_MAX_BYTES` not being raised without reviewing this function. (R1)
  (fix: add a comment documenting the implicit bound; assert `CAPTURE_MAX_BYTES <= 200_000` at module level)

- `capture.py:240-243` `_extract_items_via_llm` no pre-flight context window guard — prompt inlines up to 50KB of content (≈12.7K tokens). If `CAPTURE_MAX_BYTES` is later raised above ~600KB the Haiku context window will be silently exceeded at the API layer with an opaque error. (R1)
  (fix: `MAX_PROMPT_CHARS = 600_000; assert len(prompt) <= MAX_PROMPT_CHARS` or derive from a config constant)

- `capture.py:288-298` `_path_within_captures` naming inconsistency — only predicate (bool-returning) function in the module; all others use verb-first names. (R1)
  (fix: rename to `_is_path_within_captures`; update two call sites in `_write_item_files`)

- `capture.py:164-181` `_scan_for_secrets` encoded `location` lacks encoding type — `"via encoded form"` does not distinguish base64 vs URL-encoded secrets, making triage harder. (R1)
  (fix: split `_normalize_for_scan` into annotated passes returning `(text, label)` tuples; emit `"via base64"` or `"via URL-encoding"`)

- `capture.py:455-459` `os.scandir` on every `FileExistsError` retry is O(N×E) — with N=20 items and 10 retries each plus E=10,000 existing captures, pathological case is ~2M string operations. Non-issue under normal operation; degrades linearly under sustained cross-process race. (R2)
  (fix: on `FileExistsError`, add the conflicting slug directly to `existing` before calling `_build_slug` again; re-scan only when write-retries are exhausted)

- `capture.py:546` `captured_at` timestamp computed post-LLM — runs after `_extract_items_via_llm`; for Haiku calls under load, the gap can be 5-30s. Files are timestamped "when persisted", not "when submitted". (R2)
  (fix (optional): move `captured_at = datetime.now(UTC).strftime(...)` to immediately after `_resolve_provenance(...)` so both session-identity fields reflect submission time)

- `capture.py:319-343` `_build_slug` collision suffix while-loop is unbounded — `while True` with monotonic suffix; no hard upper bound on `n`. Production requires millions of colliding names to be an issue, but a test accidentally constructing a large collision set could hang. (R3, revalidated 2026-04-17)
  (fix: cap attempts to `len(existing) + 2` or a fixed defensive ceiling, raise/return a clear collision-exhausted error)

### NIT

- `capture.py:247-265` `_verify_body_is_verbatim` — `body.strip()` used for containment check but original unstripped `item` returned in `kept`; downstream writer receives bodies with leading/trailing whitespace. (R1)
  (fix: set `item["body"] = body_stripped` before appending to `kept`, or document that callers must strip)

- `tests/conftest.py:149-159` `tmp_captures_dir` — patches both `kb.config.CAPTURES_DIR` and `kb.capture.CAPTURES_DIR` but does not re-verify the patched path satisfies `is_relative_to(PROJECT_ROOT)`. A future test passing an intentionally-escaping path would bypass the security assertion silently. (R1)
  (fix: add `assert captures.resolve().is_relative_to(PROJECT_ROOT.resolve())` inside the fixture)

- `capture.py:86-134` `_CAPTURE_SECRET_PATTERNS` `list[tuple]` — two-element tuples accessed as `label, pattern`; a `NamedTuple` would make access self-documenting and adding a third field (e.g., `severity`) non-breaking. (R1)
  (fix: `class _SecretPattern(NamedTuple): label: str; pattern: re.Pattern[str]`)

- `tests/conftest.py:11` `RAW_SUBDIRS` incomplete — lists only 5 subdirs (`articles`, `papers`, `repos`, `videos`, `captures`); missing `podcasts`, `books`, `datasets`, `conversations`, `assets`. Tests using `tmp_project` that exercise those subdirs find them absent with no documented explanation. (R1)
  (fix: derive from `SOURCE_TYPE_DIRS` keys dynamically)

- `tests/test_capture.py:120-122` comment mismatch — says "25001 CRLF pairs = 50002 raw bytes / 50001 post-LF bytes" while the actual expression is `'ab\r\n' * 12501 = 50004 raw bytes` and `37503` post-LF. (R1, revalidated 2026-04-17)
  (fix: `# 'ab\r\n' * 12501 = 50004 raw bytes, 37503 post-LF bytes`)

- `tests/test_capture.py:11-12` duplicate `import re` — `import re` then `import re as _test_re`; the alias is used only once. Ruff F811. (R2)
  (fix: remove `import re as _test_re`; change the usage to `re.search(...)`)

---

## Phase 5 pre-merge (feat/phase-5-kb-lint-augment, 2026-04-15)

<!-- Discovered by the three reviewers (Codex branch review, spec compliance, code quality)
     running against feat/phase-5-kb-lint-augment after the feature was declared ready-to-merge.
     Items ordered by severity. Primary scope: src/kb/lint/augment.py and helpers. -->

### MEDIUM

- `lint/augment.py` `run_augment` — `Manifest.resume()` is implemented in `_augment_manifest.py` but `run_augment(resume=<run_id>)` was never wired through to it; the kwarg was declared and then ignored. Removed the declaration in this branch until the CLI/MCP surface exposes a resume flag. Spec §9 still documents crash-resume as the intended behaviour; re-adding the kwarg should ship alongside a `--resume=<id>` CLI flag and matching MCP parameter. (resolved-here, deferred re-wiring)
  (fix: re-add `resume: str | None = None` kwarg to `run_augment`; at entry, call `Manifest.resume(run_id_prefix=resume)` and if present skip Phase A and restart iteration from `manifest.incomplete_gaps()`; add `--resume` to cli.py `lint` command and to `mcp/health.py::kb_lint`)

---

## Phase 5 three-round code review (2026-04-17)

<!-- Discovered by 3 sequential Codex review rounds against the current tree.
     R1 focused on correctness and API wiring, R2 on reliability/security/state
     isolation, R3 on tests/config coverage gaps. -->

### HIGH

_All 3 HIGH items resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 1" (raw_dir threading, ingest raw_dir parameter, manifest failed-state advance)._

### MEDIUM

- `lint/augment.py` `run_augment` (~706-729, summary block) — one stub with multiple candidate URLs can record both a failed attempt and a later saved attempt in `fetches`. The summary counts failed entries, not final stub outcomes, so a successful fallback URL reports `Saved: 1, Failed: 1` for a single gap. This makes the run look partially failed when the gap actually succeeded. (R1)
  (fix: store URL-attempt details under each stub, or compute summary counts from final per-stub states in the manifest)

_3 of 4 MEDIUM items resolved (data_dir threading, max_gaps lower bound, proposal URL re-validation). Summary-count semantic change deliberately deferred — observable behavior change._

### LOW

- `tests/test_v5_lint_augment_cli.py` + `tests/test_v5_kb_lint_signature.py` — CLI/MCP augment coverage only exercises propose/no-stub or validation paths. No test runs `execute` or `auto_ingest` through the public CLI/MCP entry points with `--wiki-dir` / `wiki_dir=` and asserts raw files, manifests, and rate-limit files stay under the same temp project. This is why the custom-dir leaks above remain invisible. (R3)
  (fix: add public-surface tests for `kb lint --augment --execute --wiki-dir <tmp>/wiki` and `kb_lint(augment=True, execute=True, wiki_dir=...)`; assert writes land in `<tmp>/raw` and `<tmp>/.data`, not repo defaults)

- `tests/test_v5_lint_augment_orchestrator.py` execute-mode cases — direct `run_augment` tests always pass `raw_dir=tmp_project / "raw"` and monkeypatch `MANIFEST_DIR` / `RATE_PATH`, which bypasses the default-path behavior users hit through CLI/MCP. The suite therefore tests a safer dependency-injected path than the product actually exposes. (R3)
  (fix: add at least one unmonkeypatched default-path regression using an isolated temp project API, or refactor `run_augment` so data/raw dirs are explicit dependencies and public callers must provide them)

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
- **Phase 4 post-release audit** — all items resolved (23 HIGH + ~30 MEDIUM + ~30 LOW) in CHANGELOG.md [Unreleased]
