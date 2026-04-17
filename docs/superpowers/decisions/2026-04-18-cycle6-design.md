# Cycle 6 — Design Decision (Step 5)

**Opus subagent verdict:** APPROVE with 6 conditions.
**Date:** 2026-04-18.
**Source:** Step 1 requirements + Step 2 threat model + project principles; 12 open questions resolved.

## Decisions (OQ1–OQ12)

| OQ | Title | Option | Key |
|----|-------|--------|-----|
| OQ1 | PageRank cache key composition | B | `(str(wiki_dir.resolve()), max_mtime_ns, page_count)` — 3-tuple mirroring `_WIKI_BM25_CACHE` |
| OQ2 | PageRank cache bounded vs unbounded | A | Unbounded dict; documented in docstring |
| OQ3 | VectorIndex __init__ ext-load failure | B | `self._disabled = True` + single WARNING + `query` returns [] |
| OQ4 | sqlite3.Connection GC lifetime | B | Leave open until process exit |
| OQ5 | Slug collision precedence | A | Entity wins, WARNING logged, added to `pages_skipped` |
| OQ6 | shared_seen threading pattern | A | `shared_seen: dict[str, str] \| None = None` kwarg added |
| OQ7 | CLI env/flag naming | A | `KB_DEBUG=1` env + `--verbose` flag alias |
| OQ8 | load_purpose cache size/invalidation | A | `@functools.lru_cache(maxsize=4)` + `.cache_clear()` docstring |
| OQ9 | load_all_pages API shape | A | Keyword-only `return_errors: bool = False` kwarg |
| OQ10 | AC6 call-site scope | A | Only `_compute_pagerank_scores` call-site in engine.py:186 |
| OQ11 | include_centrality MCP exposure | A | Library kwarg only; not exposed via MCP |
| OQ12 | Preamble-leak regex strategy | A | Regex keyword list + word boundary — mirror `_LEAK_KEYWORD_RE` |

## Conditions (must ship at Step 9)

1. **Reuse `_LEAK_KEYWORD_RE` pattern** from `engine.py:296-307` in `rewriter.py` (prefer import-and-reuse over duplication to prevent drift). The regex has two rounds of false-positive hardening behind it.

2. **Thread `shared_seen` from `ingest_source`'s outer call site.** Both `_process_item_batch` calls (entity batch, concept batch) must receive the same dict so cross-batch collisions are caught.

3. **Step 11 caller-grep checkpoint:**
   ```bash
   grep -n "load_all_pages(" src/kb/ tests/   # confirm positional callers not broken
   grep -n "_process_item_batch(" src/kb/ tests/   # confirm kwarg addition compatible
   ```

4. **AC14 docstring contract:** explicitly state *"Tests that mutate `purpose.md` after first read must call `load_purpose.cache_clear()`."*

5. **AC9 CLI test must be behavioral** (not `inspect.getsource` grep, per `feedback_inspect_source_tests` memory). Use Click's `CliRunner` with `env={"KB_DEBUG": "1"}` and assert `"Traceback"` substring in stderr.

6. **AC5 Step-11 grep contract:** `grep -c "sqlite3.connect" src/kb/query/embeddings.py` baseline=2 (build + query), target=2 (build keeps own; query switches to `self._conn`). ≠2 = regression.

## Final design (single paragraph)

Cycle 6 threads mtime+count-keyed process-level caches into `_compute_pagerank_scores` (unbounded, 3-tuple key mirroring `_WIKI_BM25_CACHE`) and `load_purpose` (lru_cache maxsize=4 with documented `cache_clear()` test contract), preserves graceful degradation on `VectorIndex.__init__` via a `_disabled` flag + single idempotent WARNING (query returns [] without retry), threads a shared `seen_slugs: dict | None = None` kwarg through `_process_item_batch` so entity-concept slug collisions collapse to a single entity-winning page with a WARNING + `pages_skipped` entry, adds `KB_DEBUG=1`/`--verbose` traceback output to every CLI subcommand without altering default behavior, extends `load_all_pages` with a keyword-only `return_errors=False` shape toggle that preserves every existing caller, gates `graph_stats` betweenness computation behind an internal `include_centrality=False` kwarg (not exposed to MCP), plumbs `wiki_dir` through three `mcp/health` tools matching `kb_lint`'s Phase 5.0 pattern, adds a CRLF-normalization line to `_update_existing_page`, rewrites RRF fusion to store `(score, result)` tuples instead of shallow dict copies, type-guards dedup across-type, refactors the three-break chain in `find_connection_opportunities`, and rejects LLM-preamble-leaked rewrites in `rewrite_query` by reusing the battle-tested keyword-anchored regex pattern from `engine.py`'s `_LEAK_KEYWORD_RE`. Every change is signature-preserving (additive kwargs with safe defaults) or internal-only, one commit per file, one behavioral regression test per AC in `tests/test_backlog_by_file_cycle6.py`.
