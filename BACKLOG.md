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

## Phase 3.96 — v0.9.15 (code-review sweep, 6-agent parallel review of v0.9.14, round 2)

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

- `compile/compiler.py:274` `compile_wiki` — partial ingest failure (exception mid-pipeline after some pages created) skips the manifest hash write, causing the failed source to be re-ingested on every subsequent incremental compile indefinitely. Combined with non-atomic page writes, each retry can create duplicate wiki pages
  (fix: record `pre_hash` in manifest even on failure with a sentinel value like `"failed:<hash>"`, or ensure `ingest_source` rolls back partial writes before raising)

- `compile/linker.py:131-136` `inject_wikilinks` — when `title` is an empty string (e.g., page created without a title field), `re.escape("")` produces `""` and the compiled pattern matches zero-length strings at every non-word boundary. `pattern.sub(callback, body, count=1)` inserts `[[target_page_id|]]` at position 0, corrupting every page in the wiki. No call-site validation prevents empty titles from reaching this function
  (fix: add guard `if not title or not title.strip(): return []` at top of `inject_wikilinks`)

- `compile/linker.py:177-192` `inject_wikilinks` — nested `_replace_if_not_in_wikilink` closes over loop-local `body` by reference. Semantically incorrect for `count > 1`: replacements after the first compute `before` against the original `body`, shifting positions and making the `open_count` wikilink guard wrong
  (fix: capture as a default argument: `def _replace_if_not_in_wikilink(match, _body=body):`)

- `ingest/pipeline.py:268` `_update_existing_page` — `source_line_pattern` matches ANY indented YAML list item with double-quoted value, not just items under the `source:` key. A page with `tags: ["python"]` in frontmatter would inject the new source ref after the tags entry, producing silently corrupted YAML where source entries appear under the wrong key
  (fix: locate the `source:` key line first, then operate only within the contiguous indented block following it; or use `python-frontmatter` for round-trip parse-and-reserialize)

- `ingest/pipeline.py:291` `_update_existing_page` — context block dedup `if ctx and ctx not in content` checks the entire multi-line block as a substring. Slight differences (trailing newline, extra space) cause the guard to miss existing `## Context` sections, injecting a duplicate on every multi-source ingest for shared entity names
  (fix: check for the section header alone: `if ctx and "## Context" not in content`)

- `ingest/extractors.py:135` `build_extraction_schema` — unguarded `template["extract"]` access raises `KeyError` on malformed or new templates missing the `extract:` key; surfaces as a confusing traceback rather than a clear message
  (fix: `if "extract" not in template: raise ValueError(f"Template missing 'extract' key: {template.get('name','?')}")`)

- `ingest/extractors.py:150-151` `build_extraction_schema` — `required` list only includes fields literally named "title" or "name". Any future template without these field names produces an empty `required` array, allowing the LLM to return a valid empty object. The empty extraction propagates through the pipeline, creating a summary page with all-None fields and a title derived from `source_path.stem`
  (fix: require at minimum the first field of every template, or validate post-extraction that at least one core field is non-null before proceeding)

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

- `feedback/store.py:27` `_feedback_lock` — `os.open(lock_path, O_CREAT | O_EXCL | O_WRONLY)` raises `FileNotFoundError` (not caught) when the `.data/` parent directory does not exist; fresh clone or CI without `.data/` crashes on the first `add_feedback_entry` call before the directory is created
  (fix: add `lock_path.parent.mkdir(parents=True, exist_ok=True)` before the `while True:` loop)

### HIGH — Evolve

- `evolve/analyzer.py:105,111` `find_cross_link_opportunities` — sort key is `len(x["shared_terms"])` but `shared_terms` is capped at 10 items before sorting. All pairs with ≥10 shared terms score identically, making ranking meaningless for top candidates
  (fix: store `shared_term_count: len(shared)` before capping, sort on that field)

### HIGH — Lint / Review

- `lint/checks.py:106` `fix_dead_links` — `pages_fixed` count is `len(broken_by_page)` (all pages with broken links), not the number of pages where content was actually modified on disk. If a broken wikilink is inside a code block and the regex matches nothing, the page is counted as fixed but was never written. Audit log over-reports fixes
  (fix: compute `pages_fixed = len({f["page"] for f in fixes})` from the actual fixes list)

- `lint/runner.py:57` `run_all_checks` — `fix_dead_links` calls `resolve_wikilinks` again after `check_dead_links` already called it; same wiki, no writes between calls, pure duplicate I/O
  (fix: pass the already-computed result from `check_dead_links` into `fix_dead_links` as an optional parameter)

- `lint/checks.py:309` `check_source_coverage` — `make_source_ref(f, effective_raw_dir)` builds paths relative to a custom `raw_dir` but `all_raw_refs` in page content are relative to project root. Mismatches produce false "uncovered source" positives in tests and tools passing a non-default `raw_dir`
  (fix: derive `rel_path` relative to `PROJECT_ROOT`, not the passed `raw_dir`)

- `lint/semantic.py:284-290` `build_consistency_context` — full raw wiki page content appended to LLM prompt with no context budget truncation (unlike `_render_sources` which tracks cumulative size). A single large page can push context well past `QUERY_CONTEXT_MAX_CHARS`; also exposes prompt injection surface from web-scraped `raw/` content
  (fix: apply `_truncate_source` to page content here as done in `_render_sources`)

- `lint/verdicts.py:93-106` + `review/refiner.py:99-111` `add_verdict` / `save_review_history` — read-modify-write cycle with no locking. Two concurrent MCP tool calls both read the same baseline and both write, silently losing one entry. `atomic_json_write` prevents half-written files but not the race
  (fix: add a `threading.Lock` at module level wrapping the load → mutate → save sequence in both files)

- `review/refiner.py:90` `refine_page` — no guard against empty or whitespace-only `updated_content`; the frontmatter-guard check (line 86) passes for empty strings, so `f"---\n{frontmatter_text}---\n\n\n"` is written, erasing the entire page body silently with no error returned
  (fix: add `if not updated_content or not updated_content.strip(): return {"error": "updated_content cannot be empty."}` before the frontmatter guard)

### HIGH — MCP

- `mcp/core.py:114-117` `kb_ingest` — path boundary check validates source is within `PROJECT_ROOT` but not within `RAW_DIR`. Any file inside the project (wiki pages, `.data/` JSON, source code) can be ingested as a raw source, creating circular wiki entries and leaking internal file content to the LLM
  (fix: tighten path check to `RAW_DIR`: `path.relative_to(RAW_DIR.resolve())`)

- `mcp/core.py:233-241` `kb_ingest_content`, `kb_save_source` — no filename length cap. A 10,000-char filename produces a proportionally long slug and filesystem path without error, enabling resource exhaustion. Combined with the missing content-size limit (below), this is a DoS vector
  (fix: add `if len(filename) > 200: return "Error: filename too long (max 200 chars)."` before slugification)

- `mcp/quality.py:139-164` `kb_query_feedback` — `cited_pages` passed directly to `add_feedback_entry` without `_validate_page_id`, breaking the "all page-ID-accepting tools validate via `_validate_page_id`" security convention
  (fix: iterate `pages` and call `_validate_page_id(pid, check_exists=False)` before `add_feedback_entry`)

- `mcp/quality.py:379-385` `kb_create_page` — `source_refs` validation checks for `..` and leading `/` or `\` but does not call `os.path.isabs()`. On Windows, `C:\foo\bar` passes all string checks. Inconsistent with the stronger validation in `feedback/store.py:107-113` which correctly includes `os.path.isabs()`
  (fix: add `or os.path.isabs(src)` to the source_refs validation guard)

- `mcp/core.py:211-287` `kb_ingest_content`, `kb_save_source` — no content-size limit. Gigabyte inputs are written to disk; `kb_ingest_content` also bypasses the `QUERY_CONTEXT_MAX_CHARS` truncation that `kb_ingest` applies
  (fix: add content-length guard returning `"Error: Content too large (N chars). Maximum: X chars."`)

### HIGH — Utils

- `utils/text.py:21-35` `yaml_escape` — does not escape ASCII control characters 0x01–0x06, 0x07 BEL, 0x08 BS, 0x0B VT, 0x0C FF, 0x0E–0x1F, 0x7F DEL. YAML spec forbids these in double-quoted scalars; PyYAML raises `ScannerError`, causing pages to be silently dropped by `load_all_pages`
  (fix: add `re.sub(r"[\x01-\x06\x07\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)` before the existing substitution chain)

- `utils/wiki_log.py:26-28` `append_wiki_log` — `operation` and `message` sanitized for `|` but not `\n`/`\r`. An embedded newline produces a malformed log entry whose second line has no list-item prefix, corrupting parseable log structure
  (fix: add `.replace("\n", " ").replace("\r", "")` alongside the `|` replacement for both fields)

- `utils/pages.py:21-27` `normalize_sources` — dict-typed `source:` field (e.g. `source:\n  url: ...\n  title: ...`) iterates dict keys, silently returning `["url", "title"]` — no exception, no warning; distinct from the int/float `TypeError` (MEDIUM — Utils) because the function succeeds with wrong data, producing false "uncovered source" entries in lint reports
  (fix: same guard: `if not isinstance(sources, (str, list)): logger.warning("Unexpected source type %r", type(sources).__name__); return []`)

### MEDIUM — Documentation

- `CLAUDE.md` + `query/engine.py:222` `query_wiki` API contract — CLAUDE.md documents return key as `"sources"` (list of strings) but actual key is `"citations"` (list of dicts). Any new caller following the doc gets `KeyError`
  (fix: update CLAUDE.md to match actual return shape: `citations`, `context_pages`, `source_pages`)

### MEDIUM — Ingest / Compile

- `ingest/pipeline.py:176-178,185-187` `_build_summary_content` — when an entity/concept name produces an empty slug via `slugify()` (e.g., purely non-ASCII names like "北京大学"), the generated wikilink becomes `[[entities/|北京大学]]` — a path with an empty segment. The page creation step correctly skips zero-slug items, but the broken wikilink is already written into the summary page, producing a permanently broken link that lint flags repeatedly
  (fix: guard wikilink generation behind `if slug:`, otherwise emit plain text)

- `ingest/pipeline.py:260` `_update_existing_page` — frontmatter-splitting regex `\A(---\r?\n.*?\r?\n---\r?\n?)(.*)` uses lazy `.*?` with `re.DOTALL`, stopping at the *first* `\n---\n` occurrence. If a YAML value contains an embedded `---` on its own line (valid YAML), the regex splits mid-frontmatter, corrupting both `fm_text` and `body_text` silently
  (fix: use a stricter regex `r"\A(---\n(?:(?!---\n)[\s\S])*?---\n?)([\s\S]*)"` or use `python-frontmatter` for round-trip parse)

- `ingest/pipeline.py:260` `_update_existing_page` — if the frontmatter regex mismatches, `body_text` is silently set to `""`, discarding the entire page body with no warning
  (fix: add `logger.warning("frontmatter regex missed on %s — body lost", page_id)` when `fm_match` is None)

- `ingest/pipeline.py:278-280` `_update_existing_page` — reference lines are prepended after `## References\n` header, reversing chronological order on each subsequent ingest. Each new source pushes older refs down; N ingests produce N reversals of the reference list
  (fix: append to end of References section instead of prepending after header)

- `ingest/pipeline.py:279-282` `_update_existing_page` — `content.replace("## References\n", ...)` applies to the full document including code blocks and YAML values; the linker implements code-masking for this class of issue but ingest does not
  (fix: scope the replacement to `body_text` only, after the frontmatter/body split)

- `ingest/pipeline.py:464-471` `ingest_source` — path-traversal guard uses `Path.resolve()` + `relative_to()` for case comparison. On Windows NTFS (case-insensitive), two paths differing only in case are the same file but `Path.resolve()` does not canonicalize case. A caller passing `RAW/articles/foo.md` (capital RAW) causes `relative_to()` to raise `ValueError`, spuriously rejecting a valid file
  (fix: apply `os.path.normcase()` to both paths before `relative_to` comparison)

- `ingest/pipeline.py:477-478` `ingest_source` — `raw_content` and `source_hash` read the same file in two separate I/O calls; a concurrent write between them yields an inconsistent content/hash pair
  (fix: read once; compute hash from in-memory string: `sha256(raw_content.encode()).hexdigest()[:32]`)

- `ingest/pipeline.py:583` `ingest_source` — manifest update catch uses bare `except Exception`, swallows `OSError` on missing `.data/` with only a DEBUG log; incremental detection breaks silently
  (fix: narrow to `except (OSError, json.JSONDecodeError)` and log at WARNING)

- `compile/linker.py:13-14` `_FRONTMATTER_RE` — same lazy-match vulnerability as `ingest/pipeline.py:260`: regex stops at the first `\n---\n` inside YAML values. The misleading comment claims correctness "for --- inside YAML values" which is false. Wikilinks injected into frontmatter YAML silently corrupt the file
  (fix: use `python-frontmatter` for round-trip parse, or use negative-lookahead regex)

- `compile/linker.py:92-99` `build_backlinks` — deduplication check `if source_id not in backlinks[target]` performs a linear scan of the list on every link addition — O(n) per link, O(n²) overall for pages with many inbound links
  (fix: accumulate with `dict[str, set[str]]` internally, convert to sorted lists at return)

- `ingest/pipeline.py:178,186` `_build_summary_content` — LLM-returned entity/concept display names inserted raw into wikilink labels; a name containing `|` (e.g. `"GPT-4 | Turbo"`) produces `[[entities/gpt-4-turbo|GPT-4 | Turbo]]` where Obsidian truncates at the first `|`; names with `\n` produce multi-line wikilinks that break syntax
  (fix: sanitize display labels: `safe = name.replace("|", "-").replace("\n", " ").replace("\r", "")`)

- `compile/linker.py:192` `inject_wikilinks` — `re.sub(..., count=1)` stops after one match; if the first match is inside an existing wikilink (guard returns it unchanged), all subsequent plain-text mentions are silently skipped — injection is never applied even though valid mentions exist later in the body
  (fix: replace `count=1` with a manual `finditer` loop that skips blocked matches and stops at the first successful replacement)

- `compile/linker.py:198` `inject_wikilinks` — code-masking protects fenced/inline code but not markdown link text `[text](url)`, image alt text `![alt](url)`, or URL paths; injecting a title that appears as link text produces `[[[page|Title]] tutorial](url)`, breaking the markdown link
  (fix: mask markdown links and images with the same placeholder pattern as code blocks, then restore after injection)

- `compile/linker.py:24-35` `_mask_code_blocks` / `_unmask_code_blocks` — placeholder `\x00CODEn\x00` is not unique: if page content already contains the literal bytes `\x00CODE0\x00`, `_unmask_code_blocks` replaces both occurrences with the first real code span, corrupting the document
  (fix: generate a per-call UUID prefix so placeholders cannot collide with pre-existing page content)

### MEDIUM — Query / Graph

- `query/citations.py:15` `extract_citations` — wikilink normalization (`[[...]]` → bare text) is dead code: the stripped text never matches the `[source: ...]` citation pattern the LLM is instructed to produce
  (fix: remove the regex, or change it to emit `[source: \1]`)

- `query/citations.py:21-23` `extract_citations` — path-traversal guard rejects `..` and leading `/` but not paths starting with `./` (e.g., `[source: ./config]`). A crafted LLM response can produce `./`-prefixed references that resolve as local links in markdown renderers and confuse lint dead-link checks
  (fix: extend guard: `if ".." in path or path.startswith("/") or path.startswith(".")`)

- `graph/builder.py:64` `build_graph` — no self-loop guard on edge addition. A page containing its own wikilink adds a self-loop; NetworkX allows it but the page appears in neither `no_inbound` nor `isolated` categories, distorting orphan statistics
  (fix: add `if target in existing_ids and target != source_id: graph.add_edge(...)`)

- `graph/builder.py:90-93` `graph_stats` — `nx.pagerank()` only catches `PowerIterationFailedConvergence` but not `NetworkXError` for degenerate graph shapes. The `betweenness_centrality` block below correctly uses broad `except Exception`. A NetworkX version change or unusual topology causes an unhandled crash in health/lint operations
  (fix: add `except (nx.PowerIterationFailedConvergence, nx.NetworkXError)` consistent with betweenness block)

- `graph/export.py:69` `export_mermaid` — calls `load_all_pages` for titles after `build_graph` already scanned the same directory; ~2× the file reads per visualization call
  (fix: store title as a node attribute during `build_graph` to avoid the second scan)

- `graph/builder.py:100` `graph_stats` — `nx.betweenness_centrality(graph, k=500)` omits `seed`; for wikis exceeding 500 nodes, repeated `kb_stats` calls return different `bridge_nodes` rankings with no wiki change, making centrality guidance non-deterministic
  (fix: add `seed=0`: `nx.betweenness_centrality(graph, k=500, seed=0)`)

- `graph/builder.py:56` + `compile/linker.py:58,89` + `evolve/analyzer.py:136` `build_graph` / `resolve_wikilinks` / `build_backlinks` / `find_cross_link_opportunities` — `extract_wikilinks` called on full file text including YAML frontmatter; `[[wikilink]]` syntax in a `title:` or other frontmatter field produces phantom graph edges, false broken-link warnings, and erroneous cascade-review triggers
  (fix: strip frontmatter before calling `extract_wikilinks` — use `frontmatter.loads(content).content` or apply `_FRONTMATTER_RE` to take body only)

### MEDIUM — Lint / Review

- `lint/checks.py:264` `check_frontmatter` — bare `except Exception` while all other check functions catch specific exception tuples; masks programming bugs as lint warnings
  (fix: narrow to `(OSError, ValueError, AttributeError, yaml.YAMLError, UnicodeDecodeError)`)

- `lint/semantic.py:97` `_group_by_shared_sources` — same bare `except Exception` pattern
  (fix: same narrow exception tuple)

- `lint/semantic.py:103-129` `_group_by_wikilinks` — star-topology graphs produce incomplete groups depending on iteration order. If spoke B is processed first, group [A, B] is emitted and A is marked seen; when hub A is later skipped, spokes C and D are never grouped with A, causing consistency checks to silently miss related pages
  (fix: use `nx.connected_components(graph.to_undirected())` instead of manual neighbor-first-seen walk)

- `lint/trends.py:79-89` `get_verdict_trends` — trend direction computed with no minimum sample size on the previous period; a prior week with 1 verdict can swing the trend from a single data point
  (fix: apply the same 3-verdict minimum to both periods before reporting a trend)

- `lint/semantic.py:208` `_group_by_term_overlap` — frontmatter strip regex uses `\n` not `\r?\n`, diverging from the linker's CRLF-aware pattern. On CRLF files, frontmatter field names leak into the term corpus, producing spurious high-overlap groups
  (fix: use `r"\A(---\r?\n.*?\r?\n---\r?\n?)(.*)"` with `re.DOTALL`, take `match.group(2)` for body)

- `lint/runner.py:60` `run_all_checks` — fix dicts use key `"page"`, issue dicts use key `"source"`; the `get("source", get("page"))` fallback is fragile to schema changes
  (fix: standardize on one key name across `check_dead_links` and `fix_dead_links` output dicts)

- `lint/checks.py` + `lint/runner.py` `run_all_checks` — `scan_wiki_pages` called ≥6 times per lint run (once per check function plus once inside `build_graph`); growing duplicate I/O
  (fix: call once in `run_all_checks` and pass the result as optional parameter to each check function)

- `review/context.py:117` `build_review_checklist` — checklist specifies verdict values `"approve | revise | reject"` but `add_verdict()` in `lint/verdicts.py:63` only accepts `"pass"`, `"fail"`, or `"warning"`. Any agent that feeds checklist output directly to `kb_save_lint_verdict` raises `ValueError`. The two vocabularies are silently misaligned
  (fix: update checklist to use `"pass | warning | fail"` vocabulary matching `add_verdict`)

- `review/refiner.py:68` `refine_page` — frontmatter regex requires literal `\n`; old Mac-style `\r`-only files fail to match, returning `{"error": "Invalid frontmatter format"}` for valid pages
  (fix: use `r"\A\s*---\r?\n(.*?\r?\n)---\r?\n?(.*)"`)

- `lint/checks.py:199-221` `check_staleness` — pages with an unexpected `updated` type (e.g. `updated: 20260405` parsed as `int`) fall through all `isinstance` guards silently; page is neither flagged as stale nor as missing a date, making the malformed field invisible to lint
  (fix: add an `else` clause: log a warning and emit a "unrecognised updated type" lint issue)

- `lint/semantic.py:248-267` `build_consistency_context` — `MAX_CONSISTENCY_GROUP_SIZE` chunking is only applied when `page_ids` is explicit; auto-selected groups (the `else` branch) have no size cap — a hub page linked to 50+ others produces a single group of 50+ pages dumped into context
  (fix: apply the same `range(0, len(g), MAX_CONSISTENCY_GROUP_SIZE)` chunking to auto-selected groups)

- `lint/verdicts.py:113` `get_page_verdicts` — `v["page_id"]` raises `KeyError` if a verdict entry is missing the `page_id` field (possible after manual edits or schema migration); `load_verdicts` does no per-entry field validation
  (fix: use `v.get("page_id")` in the filter: `[v for v in verdicts if v.get("page_id") == page_id]`)

- `review/context.py:45` `pair_page_with_sources` — `frontmatter.load()` raises `yaml.YAMLError` for malformed YAML, violating the documented "returns dict with error key" contract; callers in `lint/semantic.py` check for `"error" in paired` but receive an uncaught exception instead
  (fix: wrap `frontmatter.load()` in `try/except yaml.YAMLError as e: return {"error": f"...", "page_id": page_id}`)

- `feedback/reliability.py:42` `get_coverage_gaps` — `e["question"]` raises `KeyError` if a feedback entry is missing the `question` field (possible after manual edits or schema migration); `load_feedback` validates only top-level structure, not individual entry fields
  (fix: use `e.get("question", "")` and filter with `e.get("rating") == "incomplete" and e.get("question")`)

### MEDIUM — MCP

- `mcp/core.py:44` `kb_query` (API mode) — `result["citations"]` and `result["source_pages"]` accessed outside the `try` block wrapping `query_wiki`; a future key rename raises `KeyError` that propagates to FastMCP as an unhandled exception
  (fix: extend the `try` block to cover these lines, or use `.get()` with safe defaults)

- `mcp/core.py:78` `kb_query` — trust label suppressed via float equality `!= 0.5`; floating-point representation can produce `0.5000000000001`, incorrectly showing the label
  (fix: use `abs(trust - 0.5) > 1e-9`)

- `mcp/core.py:185-196` `kb_ingest` — no file extension check when returning extraction prompt. Binary files (PDFs, images) in `raw/assets/` pass the `RAW_DIR` check and have their raw bytes echoed to the caller, producing garbage prompts and wasting API context
  (fix: add extension allowlist: `if path.suffix.lower() not in {".md", ".txt", ".rst"}: return "Error: Unsupported file type"`)

- `mcp/browse.py:57-69` `kb_read_page` — case-insensitive fallback glob scans the subdirectory with `subdir.glob("*.md")` performing O(n) linear scan. The fallback silently accepts case-variant IDs that never appear in the manifest, masking stale link bugs
  (fix: log a warning when the case-insensitive fallback matches: `logger.warning("Case-insensitive match for '%s' → '%s'", page_id, page_path.stem)`)

- `mcp/quality.py:110-133` `kb_lint_consistency` — page_id from comma-split input is stripped but not sanitized for control characters. A page_id like `"concepts/rag\n"` passes `_validate_page_id` checks and produces confusing "Page not found" errors with embedded control characters in log output
  (fix: strip control characters before validation: `re.sub(r'[\x00-\x1f]', '', pid)`)

- `mcp/quality.py:322-428` `kb_create_page` — when `page_type` is explicitly provided, subdir validation is bypassed and `mkdir(parents=True)` runs for any `page_id`, creating arbitrary directories under `WIKI_DIR`
  (fix: after `_validate_page_id`, verify `page_id.split("/")[0]` is in `WIKI_SUBDIR_TO_TYPE`)

- `mcp/browse.py:90` `kb_list_pages` — filter uses `p["id"].startswith(page_type)` where `page_type` is expected as a subdir prefix (`"concepts"`) but callers/other tools use singular forms (`"concept"`); silently returns empty on singular input
  (fix: normalize to subdir prefix: `p["id"].startswith(page_type.rstrip("/") + "/")` and document expected format)

- `mcp/quality.py:147-148` `kb_query_feedback` — `from kb.feedback.store import add_feedback_entry` outside the `try` block; an `ImportError` propagates uncaught to FastMCP
  (fix: move the import inside the `try` block)

- `mcp/quality.py:139` `kb_query_feedback` — no guard against empty `question`; `add_feedback_entry` validates only the upper-bound length, so empty-string questions are stored verbatim, polluting trust-score calculations and appearing as empty "coverage gap" questions in `kb_evolve` output
  (fix: add `if not question or not question.strip(): return "Error: question cannot be empty."` before `add_feedback_entry`)

### MEDIUM — Utils

- `utils/markdown.py:17-21` `extract_raw_refs` — regex not anchored, matches `raw/` inside URLs (e.g. `https://example.com/raw/articles/file.md`), producing false-positive source references in `check_source_coverage`
  (fix: require `raw/` preceded by a non-word character: `(?<!\w)raw/[\w/.-]+\.(?:md|txt|...)`)

- `utils/markdown.py:5` `WIKILINK_PATTERN` — no guard against triple brackets `[[[...]]]`; extracts `[concepts/rag` (with leading bracket) as a wikilink target, creating phantom graph edges
  (fix: `(?<!\[)\[\[([^\]|]+)(?:\|[^\]]+)?\]\](?!\])`)

- `utils/pages.py:21-27` `normalize_sources` — raises `TypeError` when YAML `source:` is a bare integer or float (valid YAML); page is silently dropped from search results
  (fix: `if not isinstance(sources, (str, list)): logger.warning(...); return []`)

- `evolve/analyzer.py:75` `find_connection_opportunities` — word-stripping uses `w.strip(".,!?()[]{}\"'")` but omits `-` and `/`, diverging from `semantic.py:_group_by_term_overlap` which strips `:-/`. URL fragments like `"https://example.com/path"` survive as one long token, causing false-positive connection suggestions between pages sharing a URL domain substring
  (fix: add `-` and `/` to strip chars: `w.strip(".,!?()[]{}\"':-/")`)

- `evolve/analyzer.py:36-46` `analyze_coverage` — `under_covered_types` only flags types with zero pages, missing sparse types (e.g. one stub synthesis page)
  (fix: use a configurable minimum threshold, e.g. `< 3`, rather than `== 0`)

- `utils/pages.py:55-56` `load_all_pages` — `str(post.metadata.get("updated", ""))` returns the literal string `"None"` when the YAML key exists with a `null` value (`updated: null`); any future caller parsing this as a date raises `ValueError`
  (fix: use `str(post.metadata.get("updated") or "")` to coerce `None` to empty string; apply to both `created` and `updated`)

- `utils/pages.py:13` + `graph/builder.py:18` + `evolve/analyzer.py:26` `WIKI_SUBDIRS` — the set of wiki subdirectory names is defined as independent literals in three modules rather than derived from `config.WIKI_SUBDIR_TO_TYPE`; adding a new page type to config silently leaves pages of that type invisible to page loading, graph building, and coverage analysis
  (fix: replace all three with `WIKI_SUBDIRS = tuple(WIKI_SUBDIR_TO_TYPE.keys())` imported from `kb.config`)

### MEDIUM — Tests

- `tests/conftest.py:63-84` `create_wiki_page` fixture — single `updated` parameter drives both `created:` and `updated:` frontmatter fields; impossible to write staleness or drift tests that need distinct creation and modification dates
  (fix: add a separate `created` parameter with default `created or updated or today`)

### MEDIUM — CLI

- `cli.py:43-57` `ingest` CLI command — duplicate content detected by `ingest_source` (returns `{"duplicate": True, ...}`) prints "Pages created: 0 / Pages updated: 0 / Done." with no duplicate indicator; the MCP `kb_ingest` tool shows "Duplicate content detected" prominently, creating an inconsistent user experience
  (fix: check `result.get("duplicate")` and print `"  Duplicate skipped (hash: {result['content_hash']})"` then return early)

### LOW — Ingest / Compile

- `ingest/extractors.py:93-94` `_parse_field_spec` — inline-comment stripping uses `str.index(" #")` which truncates descriptions containing literal ` #` (e.g., "Category key for #hashtag systems" → "Category key for"). Only affects JSON Schema description sent to LLM but could silently strip meaningful context from future templates
  (fix: only strip trailing inline comments preceded by double space: `"  # "`)

- `ingest/pipeline.py:286` `_update_existing_page` — `updated:` date regex `r"updated: \d{4}-\d{2}-\d{2}"` applied to full `content` string (frontmatter + body), not just frontmatter. If the body contains prose like "was updated: 2024-06-15", `re.sub` replaces all occurrences, silently corrupting body text
  (fix: apply date substitution to `fm_text` only, before recombining with `body_text`)

- `ingest/pipeline.py:324-337` `_SECTION_HEADERS`, `_SUBDIR_MAP` — these dicts are manual inverses of `config.py:WIKI_SUBDIR_TO_TYPE`; must be kept in sync when a new page type is added
  (fix: derive both from `WIKI_SUBDIR_TO_TYPE` at module load time)

- `ingest/pipeline.py:513` `ingest_source` — `summary_slug` fallback uses raw `source_path.stem` when `slugify` returns empty; stem may contain spaces or special characters, producing an invalid file path
  (fix: use `"untitled"` as the final fallback)

- `compile/compiler.py:274` `compile_wiki` — dead manifest load: `manifest = load_manifest(manifest_path)` is unconditionally overwritten at line 280 in incremental mode and unused in full mode. Unnecessary disk I/O on every compile
  (fix: remove the load at line 274)

- `compile/linker.py` `build_backlinks` — backlinks dict keyed on lowercase IDs but values are non-lowercased `source_id` from `load_all_pages`; `_find_affected_pages` lookups on mixed-case `pid` miss entries silently

- `compile/linker.py:38-101` `resolve_wikilinks` / `build_backlinks` — `extract_wikilinks` called on full file text including YAML frontmatter; wikilinks in frontmatter field values add phantom graph edges and false counts (related to MEDIUM — Query / Graph frontmatter scanning item, specific to linker functions)
  (fix: strip frontmatter before `extract_wikilinks` call in both functions)

- `compile/compiler.py` `load_manifest` / `find_changed_sources` — deleted source files are never pruned from the hash manifest; entries accumulate indefinitely; `_is_duplicate_content` iterates all entries on every ingest call as the manifest bloats
  (fix: in `find_changed_sources`, remove entries whose source path no longer exists on disk before returning)

- `ingest/extractors.py:20-61` `KNOWN_LIST_FIELDS` — contains three dead entries (`"key_themes"`, `"chapters"`, `"key_exchanges"`) absent from all 10 templates; misleads future template authors and would incorrectly force those names to list type if re-added as scalars
  (fix: remove the three entries)

- `ingest/pipeline.py:603-610` `ingest_source` — `wikilinks_injected` return list is not deduplicated; if two new page titles both match the same existing page, that page ID appears twice in the list shown to users
  (fix: `wikilinks_injected = sorted(set(wikilinks_injected))`)

- `models/frontmatter.py:17-24` `validate_frontmatter` — `source` list items not validated as strings; `[None, 42, "raw/articles/foo.md"]` passes validation and `normalize_sources` converts `42` to `"42"`, an invalid source reference that propagates silently
  (fix: add `elif not all(isinstance(s, str) for s in source): errors.append("Source list items must all be strings.")`)

- `ingest/extractors.py:64-80` `load_template` — `@functools.lru_cache` caches YAML with no TTL; in a long-running MCP server session, on-disk template changes are silently ignored until process restart; pytest cross-test cache sharing can return stale templates when `TEMPLATES_DIR` is patched
  (fix: document "process restart required" in docstring, or switch to a dict cache keyed on `(source_type, mtime)`)

### LOW — Query / Graph

- `query/bm25.py:119` `_tokenize` — second regex alternative `\b\w{2,}\b` is dead code; first alternative already matches all ≥2-char words
  (fix: simplify to `r"\b[\w][\w-]*[\w]\b"`)

- `query/engine.py:99-163` `_build_query_context` — when the top-ranked page is too large, it is skipped rather than truncated; lower-ranked pages fill the budget instead, silently degrading answer quality
  (fix: for `i==0` oversize case, truncate to `max_chars` rather than skipping)

- `query/engine.py:209` `query_wiki` — `max_tokens=2048` is a magic constant in the `call_llm` call
  (fix: add `QUERY_MAX_TOKENS = 2048` to `config.py`)

- `graph/export.py:24` `_sanitize_label` — does not strip semicolons. In Mermaid Live Editor and some embedded renderers (Obsidian, GitHub markdown preview), semicolons inside quoted node labels cause parse warnings or silent truncation. Wiki page titles with semicolons (e.g., "PyTorch vs JAX; performance") render as truncated labels
  (fix: add `;` to the stripped character set)

- `graph/export.py:34` `_safe_node_id` — replaces `/` and `-` with `_` but not `.`; a page named `entities/gpt-3.5-turbo` produces Mermaid node ID `entities_gpt_3.5_turbo` with a literal dot that may break diagram rendering in some Mermaid versions
  (fix: add `.replace(".", "_")` alongside the existing replacements)

- `query/bm25.py:119` `_tokenize` — consecutive hyphens (e.g. `"multi--hop"`) produce a single token `"multi--hop"` rather than two; the constituent words are lost for BM25 scoring and the compound token never matches query terms
  (fix: normalize `re.sub(r"-{2,}", "-", text)` before the main tokenization regex)

- `query/engine.py:49` `search_pages` — appending `title_tokens * SEARCH_TITLE_WEIGHT` inflates each document's length in the BM25 corpus, simultaneously increasing TF (intended boost) and the length-penalty denominator `|D|/avgdl`, partially cancelling the boost; effective title advantage is ~50–60% of what the weight constant implies
  (fix: document the muted effect, or increase `SEARCH_TITLE_WEIGHT` to 5–7 to achieve the intended boost, or implement BM25F-style separate field scoring)

- `query/engine.py:94` `_compute_pagerank_scores` — `except Exception` catches `MemoryError` and `KeyboardInterrupt`; a memory-exhausted graph silently degrades to pure BM25 with only a DEBUG log and no operator signal
  (fix: catch `(nx.PowerIterationFailedConvergence, nx.NetworkXError, ValueError)` specifically; re-raise or log WARNING for unexpected exceptions)

- `graph/builder.py:83-84` `graph_stats` — `most_linked[:10]` includes nodes with `in_degree=0`; for sparse wikis with fewer than 10 pages that have any inbound links, `kb_stats` reports zero-link pages under "Most linked pages"
  (fix: filter before slicing: `most_linked = [(n, d) for n, d in sorted_by_in if d > 0][:10]`)

### LOW — Feedback / Evolve

- `feedback/store.py:130` `add_feedback_entry` — entry cap silently evicts oldest entries with no log warning; at 10,000 entries this is meaningful data loss with no operator signal
  (fix: `logger.warning("Feedback store at capacity, evicting oldest entries")`)

- `feedback/store.py:153-160` `add_feedback_entry` — `page_scores` eviction uses `MAX_FEEDBACK_ENTRIES` (10,000), the same cap as entries. No separate `MAX_PAGE_SCORES` config constant; the two caps cannot be tuned independently. At near-capacity with many distinct pages, sort-and-slice runs O(N log N) on every call inside the lock window
  (fix: extract a `MAX_PAGE_SCORES` config constant)

- `evolve/analyzer.py` `_strip_frontmatter` — regex `r"\A\s*---\n..."` accepts leading whitespace before `---`, potentially matching non-frontmatter content
  (fix: tighten to `r"\A---\n..."` — YAML convention requires `---` at column 0)

- `lint/trends.py:92,109` `compute_verdict_trends` / `format_verdict_trends` — `total = len(verdicts)` counts all entries including those with unrecognised verdict strings; `format_verdict_trends` computes `pass_rate = o["pass"] / total` where `o` counts only valid verdicts, producing an artificially depressed pass rate when legacy entries exist
  (fix: compute `pass_rate = o["pass"] / sum(o.values())` when `sum(o.values()) > 0`)

### LOW — Lint / Review

- `lint/verdicts.py:72` `_validate_verdict_page_id` — path traversal guard misses null bytes (`\x00`)
  (fix: add `or "\x00" in page_id`)

- `lint/semantic.py:219` `_group_by_term_overlap` — `seen_pairs` set is redundant; `j > i` loop already prevents duplicates. Set grows to O(n²) with no benefit
  (fix: remove `seen_pairs`)

- `review/refiner.py:90` `refine_page` — `updated_content` not stripped before reconstruction; body starting with blank lines produces triple blank lines after the closing `---`
  (fix: `updated_content.lstrip()` in the f-string)

- `lint/semantic.py:57,303` `build_fidelity_context`, `build_completeness_context` — `pair_page_with_sources` called twice for the same page in the same lint session, reading the same files twice

- `lint/checks.py:306` `check_source_coverage` — `effective_raw_dir = raw_dir` is an unused alias; `raw_dir` is already in scope and the alias is never used except on the same next line; dead-code noise
  (fix: remove the alias)

### LOW — MCP

- `mcp/core.py:199-208` `kb_ingest` — `_rel(path)` embedded in extraction prompt code snippet is not escaped. If the relative path contains a double-quote character (possible on non-Windows filesystems), the returned code snippet is syntactically broken
  (fix: apply `yaml_escape` to the embedded path and source_type)

- `mcp/health.py:21,50` `kb_lint`, `kb_evolve` — error strings `"Error running lint checks: {e}"` / `"Error running evolution: {e}"` lack the `"Error: "` prefix used by all other tools; breaks client code checking for the prefix
  (fix: `f"Error: Lint checks failed — {e}"` / `f"Error: Evolution analysis failed — {e}"`)

- `mcp/health.py:83` `kb_graph_viz` — `max_nodes=0` (unbounded) is undocumented; 500-node Mermaid output is likely unrenderable in most clients
  (fix: document in the tool description that values >100 may produce unrenderable output)

- `mcp/core.py:233` `kb_ingest_content` — whitespace-only `filename` slugifies to `""`, becomes `"untitled.md"` silently with no user error
  (fix: `if not filename or not filename.strip(): return "Error: filename cannot be empty."`)

- `mcp/app.py:58` `_validate_page_id` — belt-and-suspenders check uses `startsWith("/")` and `startsWith("\\")` but not `os.path.isabs()`, inconsistent with complete path-absolute detection on all platforms

- `mcp/quality.py:295` `kb_save_lint_verdict` — `import json` inside the function body; move to top-level imports for consistency. Separately, no length cap on `notes` at the MCP boundary — `add_verdict` truncates silently at 2,000 chars with only a logger.warning, but a 100,000-char notes string is held in memory until then
  (fix: add `if len(notes) > 2000: return "Error: notes too long (max 2000 chars)."` at MCP boundary)

- `mcp/browse.py:52` + `mcp/app.py:58` `kb_read_page` / `_validate_page_id` — page IDs without a subdir prefix (e.g. `"log"`, `"_sources"`, `"index"`) pass validation and resolve to internal wiki administrative files (`wiki/log.md`, etc.), which are not "pages" by the system's definition; undocumented access path
  (fix: require `"/" in page_id`, or validate that `page_id.split("/")[0]` is in the known wiki subdirs tuple)

- `cli.py:30-34` `ingest` CLI command — `click.Choice` includes `"comparison"` and `"synthesis"` but these types have no `raw/` directory mapping in `SOURCE_TYPE_DIRS`; using them raises `ValueError: Source path must be within raw/ directory` with no explanation
  (fix: remove `"comparison"` and `"synthesis"` from the `click.Choice` list, or add a pre-check with a clear message)

- `cli.py:105-125` `lint` CLI command — `raise SystemExit(1)` on the error-count check is inside the `try` block guarded by `except SystemExit: raise`; while functionally correct, `format_report` exceptions are caught by the same `except Exception` block, conflating formatting failures with lint-execution failures
  (fix: move the error-count check and exit outside the `try` block)

### LOW — Models

- `models/frontmatter.py:10-33` `validate_frontmatter` — no date format validation for `created` and `updated` fields. When YAML loads a non-date value (e.g., `created: not-a-date`), it returns the raw string; `validate_frontmatter` reports no error and the corrupt value propagates into every page dict via `load_all_pages`
  (fix: check `isinstance(val, date)` for both date fields and report an error if not)

### LOW — Utils

- `utils/hashing.py:10` `content_hash` — SHA-256 truncated to 128 bits (32 hex chars); undocumented. A crafted collision could cause ingest to skip a source as "already processed"
  (fix: document the security assumption; consider upgrading to full 64-char hash)

- `utils/markdown.py` `WIKILINK_PATTERN` — no code-block awareness; wikilinks inside fenced code blocks are extracted as live links. The linker masks code blocks before injection but `extract_wikilinks` (used by `graph/builder.py` and `lint/checks.py`) does not, producing false graph edges and orphan reports from code examples

- `config.py:53-57` `MODEL_TIERS` — evaluated once at import time; environment variable overrides set after import are silently ignored; comment implies live override but process restart is required
  (fix: document "process restart required" in the `MODEL_TIERS` comment, or call `os.environ.get()` at call time in `_resolve_model`)

- `utils/markdown.py:5` `WIKILINK_PATTERN` — `[^\]|]+` quantifier has no upper bound; a malformed `[[` with kilobytes before the next `]]` returns a very long string, bloating graph node IDs and lint reports
  (fix: cap the match: `[^\]|]{1,200}`)

- `utils/hashing.py:7-10` `content_hash` — `path.read_bytes()` loads the entire file into memory before hashing; for large source documents (200 MB+ books or datasets), this doubles peak memory during the manifest scan
  (fix: use a 64 KB streaming chunk reader)

- `config.py:39-48` + `ingest/pipeline.py:96-104` `SOURCE_TYPE_DIRS` / `detect_source_type` — `raw/assets/` is defined in config but absent from `SOURCE_TYPE_DIRS`; `kb ingest raw/assets/image.png` raises `ValueError: Cannot detect source type` with no hint that assets are not ingestable
  (fix: add a guard: `if "assets" in rel.parts: raise ValueError("raw/assets/ files are not ingestable — assets are referenced by other sources")`)

- `utils/io.py:20` `atomic_json_write` — `json.dump` defaults allow `float("nan")` and `float("inf")`, writing non-standard `NaN`/`Infinity` literals; a future trust-score NaN would silently corrupt the JSON store, making it unreadable by non-Python parsers
  (fix: pass `allow_nan=False` to `json.dump` to surface the bug immediately as a `ValueError`)

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
- `feedback/store.py` — no test for `_feedback_lock` `FileNotFoundError` on missing `.data/` directory
- `feedback/reliability.py` — no test for `get_coverage_gaps` with entries missing `question` field
- `lint/verdicts.py` — no test for `get_page_verdicts` with entries missing `page_id` field
- `lint/semantic.py` — no test for `build_consistency_context` auto-selected groups exceeding `MAX_CONSISTENCY_GROUP_SIZE`
- `review/refiner.py` — no test for `refine_page` with empty or whitespace-only `updated_content`
- `compile/linker.py` — no test for `inject_wikilinks` when first regex match is inside an existing wikilink (count=1 skip-all scenario)
- `compile/linker.py` — no test for `_mask_code_blocks` / `_unmask_code_blocks` with pre-existing `\x00CODEn\x00` bytes in page content
- `graph/builder.py` — no test for `graph_stats` determinism (betweenness centrality with identical seed)
- `ingest/pipeline.py` — no test for `_update_existing_page` with `updated: YYYY-MM-DD` in the body (not just frontmatter)

## Phase 3.97 — v0.9.16 (context7-assisted review of v0.9.15, second-pass sweep)

### CRITICAL — Data Integrity (non-atomic writes not covered by Phase 3.96 CRITICAL fix)

- `review/refiner.py:94` `refine_page` — `page_path.write_text(new_text, encoding="utf-8")` is non-atomic. Phase 3.96 CRITICAL names three `write_text` calls to fix but omits this fourth one. A crash mid-write leaves a truncated wiki page with no recovery
  (fix: replace with `atomic_text_write(new_text, page_path)` from `kb.utils.io`)

- `lint/checks.py:99` `fix_dead_links` — `page_path.write_text(content, encoding="utf-8")` is non-atomic; auto-fix of broken wikilinks can truncate a page on crash, the same hazard as the three calls in Phase 3.96 CRITICAL
  (fix: replace with `atomic_text_write(content, page_path)`)

- `mcp/quality.py:411` `kb_create_page` — `page_path.write_text(frontmatter + content, encoding="utf-8")` is non-atomic; a crash while creating a comparison or synthesis page leaves a truncated `.md` file
  (fix: replace with `atomic_text_write(frontmatter + content, page_path)`)

### HIGH — Data Integrity

- `mcp/core.py:269` `kb_ingest_content` and `mcp/core.py:330` `kb_save_source` — raw source files written via `file_path.write_text(save_content, encoding="utf-8")`, non-atomic. A crash mid-write leaves a truncated `.md` in `raw/`. On the next compile scan the corrupt file passes the extension filter and `ingest_source` reads garbled content and computes a new hash, re-ingesting indefinitely
  (fix: replace with `atomic_text_write(save_content, file_path)` and ensure parent mkdir is called first)

### HIGH — Ingest / Compile

- `ingest/pipeline.py:468-471` `ingest_source` — path boundary check uses hard-coded `RAW_DIR.resolve()`, not a parameterizable raw directory. When `compile_wiki(raw_dir=custom_dir)` calls `ingest_source(source)`, the source paths from `scan_raw_sources(custom_dir)` fail the `source_path.relative_to(RAW_DIR.resolve())` check with `ValueError: Source path must be within raw/ directory`, even when within `custom_dir`. Related to Phase 3.96 `wiki_dir` forwarding bug but distinct — even a corrected `compile_wiki` with forwarded `wiki_dir` would still fail here for non-default `raw_dir`
  (fix: add `raw_dir: Path | None = None` parameter to `ingest_source` and replace `RAW_DIR.resolve()` with `(raw_dir or RAW_DIR).resolve()`)

- `ingest/pipeline.py` `_update_index_batch` — index de-dup guard `f"{subdir}/{slug}" in content` is a plain substring match, not a wikilink-boundary match. A slug that is a proper prefix of an existing slug (e.g., `"openai"` vs `"openai-corporation"`) causes `"entities/openai" in content` to return True when only `[[entities/openai-corporation|...]]` is listed. The shorter-slug page is silently dropped from the index; it exists on disk but is invisible to users browsing `wiki/index.md`
  (fix: tighten to `f"[[{subdir}/{slug}|" in content or f"[[{subdir}/{slug}]]" in content` to require an exact wikilink boundary after the slug)

- `compile/linker.py:174` `inject_wikilinks` — `title` parameter embedded unsanitized in the wikilink replacement `f"[[{target_page_id}|{title}]]"`. A title containing `|` (e.g., `"GPT-4 | Preview"`) produces `[[concepts/gpt-4|GPT-4 | Preview]]` which Obsidian truncates at the first `|`, silently hiding the rest; a title with `\n` produces a multi-line wikilink that breaks rendering. Same class of issue as Phase 3.96 `_build_summary_content` unsanitized label bug, but in the retroactive wikilink injection path which was added later
  (fix: sanitize before use: `safe_title = title.replace("|", "—").replace("\n", " ").replace("\r", "")`, then use `f"[[{target_page_id}|{safe_title}]]"`)

### HIGH — Feedback

- `feedback/store.py:47-61` `load_feedback` — shape validation checks only for key *presence*, not *type*. Valid JSON `{"entries": null, "page_scores": null}` satisfies `"entries" in data and "page_scores" in data` and is returned verbatim. Any caller that then calls `data["entries"].append(...)` or `data["page_scores"].items()` raises `AttributeError: 'NoneType' object has no attribute ...`, crashing feedback storage and trust-score queries
  (fix: extend the guard: `or not isinstance(data["entries"], list) or not isinstance(data["page_scores"], dict)` → return `_default_feedback()`)

- `feedback/store.py:145-149` `add_feedback_entry` — page score dicts loaded from JSON are used without validating required keys before arithmetic. An existing `page_scores` entry missing `"wrong"` or `"incomplete"` (possible after manual edits or schema migration) raises `KeyError` at `scores[rating] += 1` or `scores["wrong"]` inside the weighted-negative formula, crashing on the first feedback update for that page
  (fix: before computing, initialize defaults: `for k, d in [("useful", 0), ("wrong", 0), ("incomplete", 0), ("trust", 0.5)]: scores.setdefault(k, d)`)

### MEDIUM — Ingest / Compile / Evolve

- `evolve/analyzer.py:72` `find_connection_opportunities` — frontmatter strip regex uses literal `\n`, not `\r?\n`. On Windows, wiki pages with CRLF line endings are not stripped; YAML field names (`"title"`, `"confidence"`, `"source"`, `"updated"`) enter the word-frequency corpus and generate false-positive connection suggestions between pages sharing frontmatter vocabulary. Same root cause as Phase 3.96 `lint/semantic.py:208` CRLF bug but in a separate function with no fix applied
  (fix: change the `re.sub` pattern to `r"\A---\r?\n.*?\r?\n---\r?\n?"` with `re.DOTALL` — consistent with `compile/linker.py:_FRONTMATTER_RE`)

- `compile/compiler.py:84-90` `scan_raw_sources` vs `lint/checks.py:312` `check_source_coverage` — `scan_raw_sources` filters by extension whitelist (`.md`, `.txt`, `.pdf`, `.json`, `.yaml`) but `check_source_coverage` uses `actual_dir.iterdir()` with no extension filter. Files like `raw/datasets/data.csv` or `raw/papers/figure.png` are permanently flagged as "uncovered sources" by lint since the compiler will never ingest them; there is no mechanism to suppress the false-positive warnings
  (fix: apply the same extension whitelist in `check_source_coverage`, or derive a shared constant `INGESTABLE_EXTENSIONS` in `config.py` imported by both)

### LOW — MCP

- `mcp/browse.py:118-120` `kb_list_sources` — `subdir.glob("*")` returns all files including `.gitkeep` placeholder files; users see `.gitkeep` listed as a "source file" in every unpopulated subdirectory, creating confusion about the knowledge base contents
  (fix: add `and f.name != ".gitkeep"` to the filter condition, mirroring `scan_raw_sources`'s existing `.gitkeep` exclusion)

### LOW — Tests (coverage gaps)

- `review/refiner.py` — no test for `refine_page` crash safety: write succeeds but history save fails (demonstrates the new `atomic_text_write` fix is needed)
- `feedback/store.py` — no test for `load_feedback` with `{"entries": null, "page_scores": null}` JSON
- `feedback/store.py` — no test for `add_feedback_entry` with a page_scores entry missing "wrong" or "incomplete" keys
- `ingest/pipeline.py` — no test for `_update_index_batch` where a new slug is a proper prefix of an existing slug (e.g., "openai" vs "openai-corporation")
- `compile/linker.py` — no test for `inject_wikilinks` with a title containing `|` or `\n`
- `mcp/core.py` — no test for `kb_ingest_content` / `kb_save_source` with a simulated crash between `write_text` start and completion

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
