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

## Phase 3.96 — v0.9.15 (code-review sweep, 6-agent parallel review of v0.9.14)

### CRITICAL

- `ingest/pipeline.py:126,302` `_write_wiki_page`, `_update_existing_page` — non-atomic `write_text` on wiki page files; a crash mid-write leaves a truncated `.md` with no recovery. `atomic_text_write` is already used for index/sources/manifest but bypassed here and in `compile/linker.py:198`
  (fix: replace all three `path.write_text(...)` calls with `atomic_text_write(content, path)` from `kb.utils.io`)

- `ingest/pipeline.py:247,250` `_update_existing_page` — double file read creates a TOCTOU window: reads `content` on line 247 then calls `frontmatter.load(str(page_path))` on line 250, reading the file again. Mutation uses the first read, duplicate check uses the second; a concurrent write between them yields corrupted or incorrect updates
  (fix: replace `frontmatter.load(str(page_path))` with `frontmatter.loads(content)` — content already in memory)

- `review/refiner.py:86` `refine_page` — frontmatter guard regex `r"---\n.+\n---"` requires ≥1 char between fences. An empty block `---\n---` passes the guard; the LLM can return `---\n---\nReal body` which produces double-frontmatter in the reconstructed page, corrupting it
  (fix: change `.+` to `.*?` to also catch empty frontmatter blocks)

- `mcp/core.py` `kb_query` — no empty-question guard before calling `search_pages`. `kb_search` has this guard; `kb_query` does not. In `use_api=True` mode an empty/whitespace question reaches `call_llm`, wasting an API call and producing unpredictable output
  (fix: add `if not question or not question.strip(): return "Error: Question cannot be empty."` before the `max_results` clamp)

### HIGH — Ingest / Compile

- `compile/compiler.py` `compile_wiki` — `wiki_dir` parameter is never forwarded to `ingest_source(source)`. Tests passing an isolated `wiki_dir` silently write pages into the production `WIKI_DIR` from config
  (fix: add `wiki_dir: Path | None = None` to `compile_wiki` signature and forward: `ingest_source(source, wiki_dir=wiki_dir)`)

- `compile/compiler.py:313` + `ingest/pipeline.py:583` `compile_wiki` / `ingest_source` — manifest double-write race: `ingest_source` writes the manifest, then `compile_wiki` overwrites it with its stale `manifest` dict loaded before the loop, discarding all hashes written by `ingest_source` and breaking crash-safe incremental detection
  (fix: have `compile_wiki` reload the manifest from disk at line 313 before saving, or remove the manifest write from `ingest_source` and let the compile orchestrator own it entirely)

- `compile/linker.py:177-192` `inject_wikilinks` — nested `_replace_if_not_in_wikilink` closes over loop-local `body` by reference. Semantically incorrect for `count > 1`: replacements after the first compute `before` against the original `body`, shifting positions and making the `open_count` wikilink guard wrong
  (fix: capture as a default argument: `def _replace_if_not_in_wikilink(match, _body=body):`)

- `ingest/extractors.py:135` `build_extraction_schema` — unguarded `template["extract"]` access raises `KeyError` on malformed or new templates missing the `extract:` key; surfaces as a confusing traceback rather than a clear message
  (fix: `if "extract" not in template: raise ValueError(f"Template missing 'extract' key: {template.get('name','?')}")`)

- `ingest/pipeline.py:568-573` `ingest_source` — `index_entries` re-slugifies names after `_process_item_batch` already computed and used slugs. If slugification of the raw name differs, the index slug diverges from the file slug written to disk
  (fix: return `(slug, title)` tuples from `_process_item_batch` and use them directly in `index_entries`)

### HIGH — Query / Graph

- `query/engine.py:67` + `utils/pages.py` `_page_id` — divergent implementations: `graph/builder.py:page_id()` lowercases; `utils/pages.py:_page_id()` does not. The `.lower()` call on line 67 papers over this for PageRank lookups but any new caller will hit ID mismatches
  (fix: make `utils/pages.py:_page_id` also apply `.lower()`, or extract a single canonical function imported by both)

- `query/engine.py:54` `search_pages` — BM25 index and PageRank rebuilt from disk on every query: `load_all_pages` + `BM25Index` + `build_graph` + `nx.pagerank` = two full wiki scans per call with no caching
  (note: acceptable at current scale; add module-level cache keyed on wiki-dir mtime or manifest hash before Phase 4 corpus growth)

### HIGH — Feedback

- `feedback/store.py:31-34` `_feedback_lock` — stale lock recovery calls `unlink()` then `break`s out of the acquisition loop, falling through to `yield` without holding any lock. Two concurrent writers both observing a timeout both proceed unprotected, defeating the lock
  (fix: replace `break` with `continue` to retry acquisition after removing the stale lock)

### HIGH — Evolve

- `evolve/analyzer.py:105,111` `find_cross_link_opportunities` — sort key is `len(x["shared_terms"])` but `shared_terms` is capped at 10 items before sorting. All pairs with ≥10 shared terms score identically, making ranking meaningless for top candidates
  (fix: store `shared_term_count: len(shared)` before capping, sort on that field)

### HIGH — Lint / Review

- `lint/runner.py:57` `run_all_checks` — `fix_dead_links` calls `resolve_wikilinks` again after `check_dead_links` already called it; same wiki, no writes between calls, pure duplicate I/O
  (fix: pass the already-computed result from `check_dead_links` into `fix_dead_links` as an optional parameter)

- `lint/checks.py:309` `check_source_coverage` — `make_source_ref(f, effective_raw_dir)` builds paths relative to a custom `raw_dir` but `all_raw_refs` in page content are relative to project root. Mismatches produce false "uncovered source" positives in tests and tools passing a non-default `raw_dir`
  (fix: derive `rel_path` relative to `PROJECT_ROOT`, not the passed `raw_dir`)

- `lint/semantic.py:284-290` `build_consistency_context` — full raw wiki page content appended to LLM prompt with no context budget truncation (unlike `_render_sources` which tracks cumulative size). A single large page can push context well past `QUERY_CONTEXT_MAX_CHARS`; also exposes prompt injection surface from web-scraped `raw/` content
  (fix: apply `_truncate_source` to page content here as done in `_render_sources`)

- `lint/verdicts.py:93-106` + `review/refiner.py:99-111` `add_verdict` / `save_review_history` — read-modify-write cycle with no locking. Two concurrent MCP tool calls both read the same baseline and both write, silently losing one entry. `atomic_json_write` prevents half-written files but not the race
  (fix: add a `threading.Lock` at module level wrapping the load → mutate → save sequence in both files)

### HIGH — MCP

- `mcp/quality.py:139-164` `kb_query_feedback` — `cited_pages` passed directly to `add_feedback_entry` without `_validate_page_id`, breaking the "all page-ID-accepting tools validate via `_validate_page_id`" security convention
  (fix: iterate `pages` and call `_validate_page_id(pid, check_exists=False)` before `add_feedback_entry`)

- `mcp/core.py:211-287` `kb_ingest_content`, `kb_save_source` — no content-size limit. Gigabyte inputs are written to disk; `kb_ingest_content` also bypasses the `QUERY_CONTEXT_MAX_CHARS` truncation that `kb_ingest` applies
  (fix: add content-length guard returning `"Error: Content too large (N chars). Maximum: X chars."`)

### HIGH — Utils

- `utils/text.py:21-35` `yaml_escape` — does not escape ASCII control characters 0x01–0x06, 0x07 BEL, 0x08 BS, 0x0B VT, 0x0C FF, 0x0E–0x1F, 0x7F DEL. YAML spec forbids these in double-quoted scalars; PyYAML raises `ScannerError`, causing pages to be silently dropped by `load_all_pages`
  (fix: add `re.sub(r"[\x01-\x06\x07\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)` before the existing substitution chain)

- `utils/wiki_log.py:26-28` `append_wiki_log` — `operation` and `message` sanitized for `|` but not `\n`/`\r`. An embedded newline produces a malformed log entry whose second line has no list-item prefix, corrupting parseable log structure
  (fix: add `.replace("\n", " ").replace("\r", "")` alongside the `|` replacement for both fields)

### MEDIUM — Documentation

- `CLAUDE.md` + `query/engine.py:222` `query_wiki` API contract — CLAUDE.md documents return key as `"sources"` (list of strings) but actual key is `"citations"` (list of dicts). Any new caller following the doc gets `KeyError`
  (fix: update CLAUDE.md to match actual return shape: `citations`, `context_pages`, `source_pages`)

### MEDIUM — Ingest / Compile

- `ingest/pipeline.py:260` `_update_existing_page` — if the frontmatter regex mismatches, `body_text` is silently set to `""`, discarding the entire page body with no warning
  (fix: add `logger.warning("frontmatter regex missed on %s — body lost", page_id)` when `fm_match` is None)

- `ingest/pipeline.py:279-282` `_update_existing_page` — `content.replace("## References\n", ...)` applies to the full document including code blocks and YAML values; the linker implements code-masking for this class of issue but ingest does not
  (fix: scope the replacement to `body_text` only, after the frontmatter/body split)

- `ingest/pipeline.py:477-478` `ingest_source` — `raw_content` and `source_hash` read the same file in two separate I/O calls; a concurrent write between them yields an inconsistent content/hash pair
  (fix: read once; compute hash from in-memory string: `sha256(raw_content.encode()).hexdigest()[:32]`)

- `ingest/pipeline.py:583` `ingest_source` — manifest update catch uses bare `except Exception`, swallows `OSError` on missing `.data/` with only a DEBUG log; incremental detection breaks silently
  (fix: narrow to `except (OSError, json.JSONDecodeError)` and log at WARNING)

### MEDIUM — Query / Graph

- `query/citations.py:15` `extract_citations` — wikilink normalization (`[[...]]` → bare text) is dead code: the stripped text never matches the `[source: ...]` citation pattern the LLM is instructed to produce
  (fix: remove the regex, or change it to emit `[source: \1]`)

- `graph/builder.py:64` `build_graph` — no self-loop guard on edge addition. A page containing its own wikilink adds a self-loop; NetworkX allows it but the page appears in neither `no_inbound` nor `isolated` categories, distorting orphan statistics
  (fix: add `if target in existing_ids and target != source_id: graph.add_edge(...)`)

- `graph/export.py:69` `export_mermaid` — calls `load_all_pages` for titles after `build_graph` already scanned the same directory; ~2× the file reads per visualization call
  (fix: store title as a node attribute during `build_graph` to avoid the second scan)

### MEDIUM — Lint / Review

- `lint/checks.py:264` `check_frontmatter` — bare `except Exception` while all other check functions catch specific exception tuples; masks programming bugs as lint warnings
  (fix: narrow to `(OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError)`)

- `lint/semantic.py:97` `_group_by_shared_sources` — same bare `except Exception` pattern
  (fix: same narrow exception tuple)

- `lint/trends.py:79-89` `get_verdict_trends` — trend direction computed with no minimum sample size on the previous period; a prior week with 1 verdict can swing the trend from a single data point
  (fix: apply the same 3-verdict minimum to both periods before reporting a trend)

- `lint/semantic.py:208` `_group_by_term_overlap` — frontmatter strip regex uses `\n` not `\r?\n`, diverging from the linker's CRLF-aware pattern. On CRLF files, frontmatter field names leak into the term corpus, producing spurious high-overlap groups
  (fix: use `r"\A(---\r?\n.*?\r?\n---\r?\n?)(.*)"` with `re.DOTALL`, take `match.group(2)` for body)

- `lint/runner.py:60` `run_all_checks` — fix dicts use key `"page"`, issue dicts use key `"source"`; the `get("source", get("page"))` fallback is fragile to schema changes
  (fix: standardize on one key name across `check_dead_links` and `fix_dead_links` output dicts)

- `lint/checks.py` + `lint/runner.py` `run_all_checks` — `scan_wiki_pages` called ≥6 times per lint run (once per check function plus once inside `build_graph`); growing duplicate I/O
  (fix: call once in `run_all_checks` and pass the result as optional parameter to each check function)

- `review/refiner.py:68` `refine_page` — frontmatter regex requires literal `\n`; old Mac-style `\r`-only files fail to match, returning `{"error": "Invalid frontmatter format"}` for valid pages
  (fix: use `r"\A\s*---\r?\n(.*?\r?\n)---\r?\n?(.*)"`)

### MEDIUM — MCP

- `mcp/core.py:44` `kb_query` (API mode) — `result["citations"]` and `result["source_pages"]` accessed outside the `try` block wrapping `query_wiki`; a future key rename raises `KeyError` that propagates to FastMCP as an unhandled exception
  (fix: extend the `try` block to cover these lines, or use `.get()` with safe defaults)

- `mcp/core.py:78` `kb_query` — trust label suppressed via float equality `!= 0.5`; floating-point representation can produce `0.5000000000001`, incorrectly showing the label
  (fix: use `abs(trust - 0.5) > 1e-9`)

- `mcp/quality.py:322-428` `kb_create_page` — when `page_type` is explicitly provided, subdir validation is bypassed and `mkdir(parents=True)` runs for any `page_id`, creating arbitrary directories under `WIKI_DIR`
  (fix: after `_validate_page_id`, verify `page_id.split("/")[0]` is in `WIKI_SUBDIR_TO_TYPE`)

- `mcp/browse.py:90` `kb_list_pages` — filter uses `p["id"].startswith(page_type)` where `page_type` is expected as a subdir prefix (`"concepts"`) but callers/other tools use singular forms (`"concept"`); silently returns empty on singular input
  (fix: normalize to subdir prefix: `p["id"].startswith(page_type.rstrip("/") + "/")` and document expected format)

- `mcp/quality.py:147-148` `kb_query_feedback` — `from kb.feedback.store import add_feedback_entry` outside the `try` block; an `ImportError` propagates uncaught to FastMCP
  (fix: move the import inside the `try` block)

### MEDIUM — Utils

- `utils/markdown.py:17-21` `extract_raw_refs` — regex not anchored, matches `raw/` inside URLs (e.g. `https://example.com/raw/articles/file.md`), producing false-positive source references in `check_source_coverage`
  (fix: require `raw/` preceded by a non-word character: `(?<!\w)raw/[\w/.-]+\.(?:md|txt|...)`)

- `utils/markdown.py:5` `WIKILINK_PATTERN` — no guard against triple brackets `[[[...]]]`; extracts `[concepts/rag` (with leading bracket) as a wikilink target, creating phantom graph edges
  (fix: `(?<!\[)\[\[([^\]|]+)(?:\|[^\]]+)?\]\](?!\])`)

- `utils/pages.py:21-27` `normalize_sources` — raises `TypeError` when YAML `source:` is a bare integer or float (valid YAML); page is silently dropped from search results
  (fix: `if not isinstance(sources, (str, list)): logger.warning(...); return []`)

- `evolve/analyzer.py:36-46` `analyze_coverage` — `under_covered_types` only flags types with zero pages, missing sparse types (e.g. one stub synthesis page)
  (fix: use a configurable minimum threshold, e.g. `< 3`, rather than `== 0`)

### MEDIUM — Tests

- `tests/conftest.py:63-84` `create_wiki_page` fixture — single `updated` parameter drives both `created:` and `updated:` frontmatter fields; impossible to write staleness or drift tests that need distinct creation and modification dates
  (fix: add a separate `created` parameter with default `created or updated or today`)

### LOW — Ingest / Compile

- `ingest/pipeline.py:324-337` `_SECTION_HEADERS`, `_SUBDIR_MAP` — these dicts are manual inverses of `config.py:WIKI_SUBDIR_TO_TYPE`; must be kept in sync when a new page type is added
  (fix: derive both from `WIKI_SUBDIR_TO_TYPE` at module load time)

- `ingest/pipeline.py:513` `ingest_source` — `summary_slug` fallback uses raw `source_path.stem` when `slugify` returns empty; stem may contain spaces or special characters, producing an invalid file path
  (fix: use `"untitled"` as the final fallback)

- `compile/linker.py` `build_backlinks` — backlinks dict keyed on lowercase IDs but values are non-lowercased `source_id` from `load_all_pages`; `_find_affected_pages` lookups on mixed-case `pid` miss entries silently

### LOW — Query / Graph

- `query/bm25.py:119` `_tokenize` — second regex alternative `\b\w{2,}\b` is dead code; first alternative already matches all ≥2-char words
  (fix: simplify to `r"\b[\w][\w-]*[\w]\b"`)

- `query/engine.py:99-163` `_build_query_context` — when the top-ranked page is too large, it is skipped rather than truncated; lower-ranked pages fill the budget instead, silently degrading answer quality
  (fix: for `i==0` oversize case, truncate to `max_chars` rather than skipping)

- `query/engine.py:209` `query_wiki` — `max_tokens=2048` is a magic constant in the `call_llm` call
  (fix: add `QUERY_MAX_TOKENS = 2048` to `config.py`)

### LOW — Feedback / Evolve

- `feedback/store.py:130` `add_feedback_entry` — entry cap silently evicts oldest entries with no log warning; at 10,000 entries this is meaningful data loss with no operator signal
  (fix: `logger.warning("Feedback store at capacity, evicting oldest entries")`)

- `evolve/analyzer.py` `_strip_frontmatter` — regex `r"\A\s*---\n..."` accepts leading whitespace before `---`, potentially matching non-frontmatter content
  (fix: tighten to `r"\A---\n..."` — YAML convention requires `---` at column 0)

### LOW — Lint / Review

- `lint/verdicts.py:72` `_validate_verdict_page_id` — path traversal guard misses null bytes (`\x00`)
  (fix: add `or "\x00" in page_id`)

- `lint/semantic.py:219` `_group_by_term_overlap` — `seen_pairs` set is redundant; `j > i` loop already prevents duplicates. Set grows to O(n²) with no benefit
  (fix: remove `seen_pairs`)

- `review/refiner.py:90` `refine_page` — `updated_content` not stripped before reconstruction; body starting with blank lines produces triple blank lines after the closing `---`
  (fix: `updated_content.lstrip()` in the f-string)

- `lint/semantic.py:57,303` `build_fidelity_context`, `build_completeness_context` — `pair_page_with_sources` called twice for the same page in the same lint session, reading the same files twice

### LOW — MCP

- `mcp/health.py:21,50` `kb_lint`, `kb_evolve` — error strings `"Error running lint checks: {e}"` / `"Error running evolution: {e}"` lack the `"Error: "` prefix used by all other tools; breaks client code checking for the prefix
  (fix: `f"Error: Lint checks failed — {e}"` / `f"Error: Evolution analysis failed — {e}"`)

- `mcp/health.py:83` `kb_graph_viz` — `max_nodes=0` (unbounded) is undocumented; 500-node Mermaid output is likely unrenderable in most clients
  (fix: document in the tool description that values >100 may produce unrenderable output)

- `mcp/core.py:233` `kb_ingest_content` — whitespace-only `filename` slugifies to `""`, becomes `"untitled.md"` silently with no user error
  (fix: `if not filename or not filename.strip(): return "Error: filename cannot be empty."`)

- `mcp/app.py:58` `_validate_page_id` — belt-and-suspenders check uses `startswith("/")` and `startswith("\\")` but not `os.path.isabs()`, inconsistent with complete path-absolute detection on all platforms

- `mcp/quality.py:295` `kb_save_lint_verdict` — `import json` inside the function body; move to top-level imports for consistency

### LOW — Utils

- `utils/hashing.py:10` `content_hash` — SHA-256 truncated to 128 bits (32 hex chars); undocumented. A crafted collision could cause ingest to skip a source as "already processed"
  (fix: document the security assumption; consider upgrading to full 64-char hash)

- `utils/markdown.py` `WIKILINK_PATTERN` — no code-block awareness; wikilinks inside fenced code blocks are extracted as live links. The linker masks code blocks before injection but `extract_wikilinks` (used by `graph/builder.py` and `lint/checks.py`) does not, producing false graph edges and orphan reports from code examples

### LOW — Tests (coverage gaps)

- `utils/text.py` — no test for `yaml_escape` with ASCII control characters (BEL, FF, VT, ESC, BS)
- `utils/wiki_log.py` — no test for newline injection in `operation`/`message`; no test for `LOG_SIZE_WARNING_BYTES` threshold
- `utils/io.py` — no test for `atomic_text_write` fd-leak safety on serialization failure (symmetric to existing `TestAtomicJsonWriteFdSafety`)
- `utils/markdown.py` — no test for `extract_raw_refs` matching URLs containing `raw/`; no test for `WIKILINK_PATTERN` on triple-bracketed text
- `utils/pages.py` — no test for `normalize_sources` with integer/float `source:` field
- `query/engine.py` — no test for `_compute_pagerank_scores` with a non-empty graph; no test for `_build_query_context` truncation/fallback path
- `graph/export.py` — no test for `export_mermaid`
- `utils/llm.py` — no test for `call_llm_json` "Wrong tool in response" branch
- `tests/conftest.py` — `create_raw_source` fixture does not assert `source_ref.startswith("raw/")`, allowing accidental path traversal in test setup

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
