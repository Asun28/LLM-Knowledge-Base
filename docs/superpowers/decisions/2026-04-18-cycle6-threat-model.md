# Cycle 6 — Threat Model (Step 2)

**Opus subagent output** (2026-04-18, edited for the two corrections flagged below).

## Scope corrections from subagent pre-read

1. **AC6** — `build_graph` ALREADY accepts `pages: list[dict] | None = None` (builder.py:37). Implementation target is the CALL-SITE: `_compute_pagerank_scores` (engine.py:186) currently calls `build_graph(wiki_dir)` without passing pre-loaded pages. Fix threads `pages=` through the call.

2. **AC14** — `load_purpose` lives in `src/kb/utils/pages.py` (line ~104), NOT `extractors.py`. The LRU cache goes there; callers already pass explicit `wiki_dir`.

## Analysis

This cycle groups 15 backlog items across 14 source files, concentrated in the query pipeline (engine, rewriter, embeddings, hybrid, dedup — 5 of 15 ACs), ingest pipeline (AC7, AC8, AC14), the MCP tool boundary (AC1, AC2), graph builder (AC6, AC13), plus CLI observability (AC9) and a utility shape change (AC15). Every AC is scoped to single files with no signature-refactoring of public functions, so the blast radius is narrow. Primary new trust boundaries are the process-level caches in AC4 (PageRank) and AC14 (purpose) — mtime-keyed invalidation is the entire correctness contract, and Step 11 must verify keys include `str(wiki_dir_resolved)` so two tests in the same process cannot collide. AC5 collapses per-query sqlite connections into per-instance state; if the first `__init__` load fails, subsequent `query()` calls must return `[]` without silently retrying the extension load.

Step 11 verification strategy: every AC is either (i) a new kwarg with a default that preserves positional-call compatibility, (ii) a regex/heuristic that strengthens existing input validation, (iii) a cache introduction where Step 11 must grep for the cache dict AND the key tuple AND the cache-clear helper, (iv) a connection-lifecycle refactor where Step 11 must assert `sqlite3.connect` appears EXACTLY ONCE in `__init__` and NOT in `query`, or (v) pure perf/structural refactors behaviorally invisible so pytest must exercise existing contracts. AC9 needs a test that invokes a failing CLI under `KB_DEBUG=1` and asserts `Traceback` in stderr (not `inspect.getsource` grep per `feedback_inspect_source_tests`). AC3 needs a behavioral test driving an LLM mock that returns `"Sure! Here's the rewrite: …"` through `rewrite_query` and asserts the return equals input. AC8 needs `_process_item_batch` driven with `entities_mentioned=["RAG"]` and `concepts_mentioned=["RAG"]` asserting exactly ONE created page (entity precedence) plus ONE WARNING log.

## Threat table

| AC | Surface | Trust input | Threat | Mitigation in scope | Step-11 grep |
|----|---------|-------------|--------|---------------------|--------------|
| AC1 | `mcp/core.py` `kb_ingest_content` | MCP: `use_api`, `content`, `filename` | API path bypasses `extraction_json` requirement; positional-arg drift | `use_api: bool = False` default; when True call `ingest_source(path, source_type)`; preserve existing positional slots | `grep -n "use_api" src/kb/mcp/core.py` hit inside `kb_ingest_content`; `ingest_source(` new call-site |
| AC2 | `mcp/health.py` 3 tools | MCP: `wiki_dir: str\|None` | Path-traversal via user-supplied wiki_dir reaching library calls | Default None preserves current behavior; convert `Path(wiki_dir) if wiki_dir else None`; library callees accept `wiki_dir` kwarg | `grep -n "wiki_dir" src/kb/mcp/health.py` ≥4 new hits; library signatures updated |
| AC3 | `query/rewriter.py` `rewrite_query` | scan-tier LLM output | Preamble leak (`"The standalone question is:"`, `"Sure!"`, `"Here's"`) flows into BM25+vector+synthesis | New regex at rewriter tail; on match log WARNING and return `question` unchanged | `grep -nE "standalone question\|Sure!\|Here'?s" src/kb/query/rewriter.py` ≥1 hit; behavioral pytest |
| AC4 | `query/engine.py` `_compute_pagerank_scores` | filesystem mtime, wiki_dir | Cross-test contamination; thread-safety under FastMCP pool | Module-level `_PAGERANK_CACHE` + `_PAGERANK_CACHE_LOCK`; key `(str(wiki_dir.resolve()), max_mtime_ns)`; check-under-lock pattern from `_RAW_BM25_CACHE` | `grep -n "_PAGERANK_CACHE\b" src/kb/query/engine.py` ≥3; `st_mtime_ns` present |
| AC5 | `query/embeddings.py` `VectorIndex.query` | sqlite-vec extension, sqlite3 | Connection leak; extension-load silently retried per call | Load once in `__init__`; on failure `self._disabled = True` + WARNING; `query` checks first | `sqlite3.connect` count drops by 1; `self._disabled` new attr |
| AC6 | `query/engine.py` call-site to `build_graph` | pages list[dict] | Wasted disk I/O (double-read) | Pass `pages=` kwarg when already loaded upstream | `build_graph(.*pages=` ≥1 new hit |
| AC7 | `ingest/pipeline.py` `_update_existing_page` | Raw file CRLF bytes | CRLF frontmatter bypasses `_SOURCE_BLOCK_RE` → double `source:` key | `content.replace("\r\n", "\n")` after read; atomic_text_write already LF | `replace("\r\n"` ≥1 new hit |
| AC8 | `ingest/pipeline.py` `_process_item_batch` | LLM extraction dict | Cross-batch slug collision creates two canonical pages | Share `seen_slugs` across entity+concept batches; entity-first precedence | `seen_slugs\|shared_seen` ≥3 hits; WARNING on collision |
| AC9 | `cli.py` all subcommands | `KB_DEBUG` env, `--verbose` flag | Information disclosure widened (acceptable for single-user local) | Env var OR flag triggers `traceback.format_exc()` to stderr before SystemExit(1); default unchanged | `import traceback` ≥1; `KB_DEBUG\|verbose` ≥2 |
| AC10 | `query/hybrid.py` `rrf_fusion` | result dicts | No trust threat; correctness risk at unpack | Store `(rrf_score, result)` tuple; unpack at sort | `scores\[pid\] *= *\(` tuple assignment |
| AC11 | `query/dedup.py` `_dedup_by_text_similarity` | result dicts | No trust threat; cross-type pruning quality | Skip threshold when `a.get("type") != b.get("type")` | `.get("type")` new hit in dedup |
| AC12 | `evolve/analyzer.py` `find_connection_opportunities` | in-memory pages | No trust threat; readability | `itertools.islice` OR helper | `itertools.islice\|_iter_connection_pairs` ≥1 |
| AC13 | `graph/builder.py` `graph_stats` | NetworkX DiGraph | DoS via betweenness centrality at 5k nodes | `include_centrality: bool = False` kwarg gates computation | `include_centrality` definition + caller |
| AC14 | `utils/pages.py` `load_purpose` | Filesystem `wiki_dir/purpose.md` | Cross-test contamination if cache not keyed on wiki_dir | `@lru_cache(maxsize=4)`; docstring documents `cache_clear()` contract | `@lru_cache(maxsize=4)` above `load_purpose`; `cache_clear` mentioned |
| AC15 | `utils/pages.py` `load_all_pages` | filesystem wiki pages | Shape extension risk — existing callers must not break | Default False → list[dict] unchanged; True → `{"pages": [...], "load_errors": N}` | `return_errors` kwarg; both return shapes pytest-verified |

## Trust boundaries crossed

1. **MCP client → tool** (AC1, AC2) — user-supplied strings to `@mcp.tool()` entrypoints.
2. **LLM output → rewriter return** (AC3).
3. **Raw file → frontmatter parse** (AC7).
4. **Extraction dict → slug namespace** (AC8).
5. **Filesystem → cache key** (AC4, AC14) — NEW BOUNDARY this cycle.
6. **sqlite-vec extension → VectorIndex instance** (AC5).
7. **CLI exception → stderr** (AC9).

## Authn/authz

Out of scope (single-user local tool). DoS surfaces to note:
- **AC4** PageRank cache: must NOT grow unbounded; accept `max_mtime_ns` monotonicity OR bound with `OrderedDict` LRU eviction.
- **AC13** EXPLICITLY REDUCES DoS: betweenness O(V*E) gated behind `include_centrality=False` default.
- **AC5** per-instance connection is bounded — single VectorIndex per process is typical.
- **AC1** `use_api=True` enables Anthropic API spend — default `False` is the mitigation.

## Logging/audit

AC3, AC5, AC8 need new WARNING logs (preamble-leak, ext-load-fail, slug-collision). All other ACs rely on existing logging. No `wiki/log.md` appends required.

## Step-11 verification checklist

Full checklist with 20 greps/pytest commands is embedded in the subagent output above (items 1–20). Key commands:

```bash
# Signature/behavior verification
python -m pytest tests/test_backlog_by_file_cycle6.py -v   # new test file — ≥15 cases
python -m pytest -v                                         # full suite — 1842 baseline + new
ruff check src/ tests/
ruff format --check src/ tests/

# Per-AC greps (see subagent output items 1–20 above)
grep -nE "_PAGERANK_CACHE\b" src/kb/query/engine.py
grep -nE "seen_slugs\|shared_seen" src/kb/ingest/pipeline.py
grep -nE "sqlite3\.connect" src/kb/query/embeddings.py   # count down by 1
grep -nE "include_centrality" src/kb/graph/builder.py src/kb/mcp/*.py src/kb/lint/*.py
```

## Dep-CVE baseline

- 0 open Dependabot alerts (`gh api` → `[]`).
- 2 pip-audit findings on main, both CLASS A (existing):
  - `diskcache==5.6.3` — CVE-2025-69872, no patch available (accepted risk from cycle 4).
  - `pip==24.3.1` — CVE-2025-8869, CVE-2026-1703, ECHO-ffe1, ECHO-7db2 — toolchain only (not runtime).
- Step 12.5: re-check `diskcache` for a patched release; otherwise skip.
