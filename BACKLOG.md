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

## Phase 4 (v0.10.0) — Post-release audit

- **HIGH** — all 23 items resolved in Phase 4 audit fixes (2026-04-12)

### MEDIUM

<!-- foundation -->

- `utils/pages.py:65-66` `load_all_pages` — if a wiki page's YAML frontmatter uses a full datetime (`updated: 2024-01-01 12:00:00`), PyYAML parses it as `datetime.datetime`. `str()` on that produces `'2024-01-01 12:00:00'`, which `date.fromisoformat()` in `_flag_stale_results` rejects with `ValueError`. The exception is silently caught and the page is treated as non-stale — a wrong result with no diagnostic.
  (fix: in `load_all_pages`, extract date portion before stringifying: `d = post.metadata.get('updated'); str(d.date() if isinstance(d, datetime.datetime) else d or '')`)

- `utils/text.py:35` `slugify` — the `re.ASCII` flag deletes all non-ASCII and also collapses decimal points between digits: `slugify('v1.0')` and `slugify('v10')` both produce `'v10'`, silently creating slug collisions for version-numbered pages.
  (fix: before the ASCII strip, replace `.` between digits with a separator: `re.sub(r'(?<=\d)\.(?=\d)', '-', text)` so `3.1` → `3-1`)

- `utils/io.py:23-27` `atomic_json_write` / `atomic_text_write` — the `except BaseException` cleanup block unconditionally calls `os.close(tmp_fd)` after `os.fdopen` has already closed that fd. The resulting `EBADF` is masked by `contextlib.suppress(OSError)`. If a future refactor removes the suppress, every write failure becomes a hard crash.
  (fix: track `fd_transferred = False` before `os.fdopen`; in the except block, `if not fd_transferred: os.close(tmp_fd)` — removes the need for `suppress` entirely)

<!-- graph -->

- `graph/export.py:74` `export_mermaid` — `load_all_pages(wiki_dir)` is called before pruning is applied, loading all pages even though only `nodes_to_include` (a small subset) will be queried for titles. For a 1000-page wiki, this loads all page frontmatter to use ~30 titles.
  (fix: move the `load_all_pages` call after the pruning step and filter to only pages in `nodes_to_include`)

- `graph/builder.py:80-132` `graph_stats` — `graph.degree(n)` is called per-node inside a list comprehension. `in_degrees` is already pre-computed as a dict one line above, but `degree()` recomputes `in + out` via NetworkX view lookups for each node.
  (fix: precompute `out_degrees = dict(graph.out_degree())` at the top of `graph_stats` and replace `graph.degree(n) == 0` with `in_degrees[n] == 0 and out_degrees[n] == 0`)

<!-- query / search -->

- `query/citations.py:5` `_CITATION_PATTERN` — the `[\w/_.-]` character class allows consecutive dots (`.` matched twice). A citation like `[source: raw/a..b/page]` passes the `".." in path` guard because the regex absorbs `..` as two separate `.` chars. Only the substring guard catches `../` traversals, not `..` embedded mid-component.
  (fix: reject paths where any split component is empty: `any(not part for part in path.split("/"))` catches `//` and `a..b`; or tighten the regex to disallow consecutive dots)

- `query/engine.py:306-317` `_build_query_context` — the fallback branch that handles the case where `_try_add` skipped every page adds a page without adjusting the `skipped` counter. The counter was already incremented inside `_try_add` for the failed first-page path, so `skipped` is over-counted when the fallback fires.
  (fix: set `skipped = max(0, skipped - 1)` before appending in the fallback block, or have `_try_add` return a tri-state `ADDED / TRUNCATED / SKIPPED` to avoid the implicit counting assumption)

- `query/rewriter.py:54` `rewrite_query` — the LLM response is used verbatim after only `strip().strip('"')`. If the LLM returns a multi-sentence explanation ("The question asks about X. Standalone version: ..."), the entire string including preamble is used as the search query, degrading BM25 results.
  (fix: instruct the model with "Reply with ONLY the rewritten question, no explanation" and add post-processing guard: if `len(rewritten) > 3 * len(question)`, fall back to `question`)

- `query/bm25.py:160-165` `BM25Index.__init__` — the `avgdl == 0` guard fires when every document has zero tokens, which is a valid edge case that produces correct all-zero scores. The `logger.warning` misleads operators into thinking a data error occurred.
  (fix: downgrade to `logger.debug` to avoid alarming operators during tests with empty-content fixtures)

<!-- compile / evolve -->

- `compile/compiler.py:343-344` `compile_wiki` — inside the `except Exception` block, `content_hash(source)` is called again. If `content_hash` was the operation that raised (e.g., `PermissionError`), the inner call will raise the same error. The `failed:` hash sentinel is then never written, meaning the file won't be retried on the next compile via the normal mechanism (it will appear as "new" instead).
  (fix: capture `rel_path` and `pre_hash` before the `try` block so they are available in the except handler without re-calling potentially-failing functions)

- `compile/compiler.py:300-302` `compile_wiki` — the final `save_manifest(current_manifest, manifest_path)` at line 368 runs unconditionally even in incremental mode with zero sources to process. On every incremental compile with no changes, the manifest mtime updates even though nothing was modified.
  (fix: only call the final `save_manifest` when `not incremental` or when the loop actually modified the manifest)

- `evolve/analyzer.py:94-102` `find_connection_opportunities` — `pair_shared_terms` is a `dict[tuple, list[str]]` built before the `MIN_SHARED_TERMS` filter is applied. For 200 pages each sharing 50 qualifying terms, this grows to ~1M entries. No memory or pair-count guard exists.
  (fix: apply the `MIN_SHARED_TERMS` threshold inline during accumulation, or add a cap of `len(pair_shared_terms) > 50_000` with a warning)

- `evolve/analyzer.py:47` `analyze_coverage` — `generate_evolution_report` calls `analyze_coverage` and `find_connection_opportunities` separately. Both call `scan_wiki_pages` and read every page file from disk. The entire wiki is read at least three times for a single evolve run.
  (fix: pass a pre-scanned `pages` list through the call chain in `generate_evolution_report`)

- `compile/linker.py:21-26` `_CODE_MASK_RE` — fenced code blocks delimited with `~~~` (valid CommonMark fencing) are not masked. Wikilink injection can fire inside `~~~`-fenced blocks, producing corrupted output.
  (fix: add `~~~.*?~~~` with `re.DOTALL` to the `_CODE_MASK_RE` alternation; document the known limitation for indented code blocks)

- `compile/linker.py:210` `inject_wikilinks` — the `_replace_if_not_in_wikilink` inner function is re-defined on every loop iteration (one per entity/concept term). Each iteration allocates a new function object and closes over loop variables.
  (fix: extract the replacement logic as a direct `if` block inside the loop, eliminating per-iteration function object allocation)

<!-- ingest -->

- `ingest/pipeline.py:677-694` `ingest_source` — `contradiction_warnings` are detected and returned in the result dict (line 710) but never written to `wiki/contradictions.md`. `WIKI_CONTRADICTIONS` is defined in `config.py` but never imported in the ingest package. The architecture docs state this file is updated on ingest, but no code does this.
  (fix: after contradiction detection, append each warning to `WIKI_CONTRADICTIONS` in a structured format, similar to how `append_wiki_log` appends to `wiki/log.md`)

- `ingest/pipeline.py:554-573` `ingest_source` — on re-ingest when a summary page already exists, `_build_summary_content` is called (line 565) but its result is immediately discarded (line 567 calls `_update_existing_page` with the original existing content). This O(n) work on the extraction dict is always thrown away on update.
  (fix: move `_build_summary_content` inside the `else` branch so it is only called when creating a new page)

- `ingest/pipeline.py:309-321` `_update_existing_page` — the `## References` section regex alternation `(?:[^\n].*\n|\n)*?` fails on whitespace-only lines (e.g., a line with only spaces). The regex stops at such a line, and the new reference is then appended at the end of the file outside the References section, duplicating the section.
  (fix: change the alternation to `(?:[^\n].*\n|[ \t]*\n)*?` to handle whitespace-only lines within the section)

- `ingest/pipeline.py:283-293` `_update_existing_page` — when the frontmatter regex fails (`fm_match` is `None`), the fallback sets `fm_text = content` and `body_text = ""`. The `_SOURCE_BLOCK_RE` and `updated:` date substitution are then applied to the full file content. A page with `updated: 2025-01-01` in its body text (e.g., in an Evidence Trail entry) will have that date silently rewritten.
  (fix: when `fm_match` is `None`, log a warning and return early without modifying the file rather than falling through with a corrupted split)

- `ingest/extractors.py:63-81` `load_template` — `lru_cache` stores and returns the same mutable dict. Any caller that modifies the returned dict corrupts the cache for all subsequent calls in the same process.
  (fix: return `copy.deepcopy(template)` from `load_template`, or add a docstring warning "Do not mutate the returned dict — it is a shared cached object")

- `ingest/pipeline.py:419` `_process_item_batch` — `_SUBDIR_MAP[page_type]` is an unguarded dict lookup. An invalid `page_type` raises a bare `KeyError` that propagates uncaught.
  (fix: add `if page_type not in _SUBDIR_MAP: raise ValueError(f"Unknown page_type: {page_type!r}")` at the top of the function)

- `ingest/evidence.py:37` `append_evidence_trail` — section detection uses `re.search(r"^## Evidence Trail\n", ...)`. On Windows with CRLF line endings, the header is `## Evidence Trail\r\n` and the pattern fails to match. A second `## Evidence Trail` section is appended at the end of the file.
  (fix: use `r"^## Evidence Trail\r?\n"` in the regex pattern)

<!-- lint / review / feedback -->

- `lint/checks.py:138-177` `check_orphan_pages` — `wiki/index.md`, `_sources.md`, `_categories.md`, and `log.md` are not scanned for outbound wikilinks when building the backlink graph. An entity or concept page linked only from `index.md` is reported as orphaned even though it is reachable.
  (fix: scan index-level files for outbound wikilinks when building the backlink graph, or document the deliberate exclusion with a comment)

- `lint/semantic.py:196-206` `_group_by_term_overlap` — O(n²) pairwise comparison with no timeout or page-count guard. With n=500 pages this is 124,750 pairs, each computing a set intersection. This blocks the MCP request thread for large wikis.
  (fix: add an early-exit guard if `len(page_ids_list) > 500`, falling back to the cheaper shared-source and wikilink groupings; or build an inverted index for O(n·t) candidate pair extraction)

- `review/refiner.py:103` `refine_page` — the frontmatter corruption guard pattern `r"---\n.*?\n?---"` does not use `re.DOTALL`. `.*?` matches any character except newline, so a multi-line frontmatter block with several fields does not match the pattern, and the guard fails to catch a well-formed frontmatter block passed as body content.
  (fix: add `re.DOTALL` to the guard: `re.match(r"---\n.*?\n?---", stripped_content, re.DOTALL)`)

- `lint/trends.py:54-55` `compute_verdict_trends` — timestamp strings that are date-only (no `T` separator) cause `datetime.fromisoformat` to raise on Python ≤ 3.10, silently skipping the entry via `except (ValueError, TypeError): continue`. Any manually-crafted verdict or migration from an older schema will produce silent data loss in trend reports.
  (fix: document the expected `timespec="seconds"` timestamp format in the module docstring; consider normalising with `datetime.fromisoformat(ts_str.replace("Z", "+00:00"))` for forward compatibility)

<!-- MCP -->

- `mcp/quality.py:154-188` `kb_query_feedback` — `question` is not length-bounded at the MCP layer. Validation happens inside `add_feedback_entry` (raises `ValueError`), which is caught by `except Exception` and returned as an error — but not before the full question is emitted to the log in the error path.
  (fix: add `if len(question) > MAX_QUESTION_LEN: return f"Error: Question too long (max {MAX_QUESTION_LEN} chars)."` before calling the library function)

- `mcp/quality.py:127-151` `kb_lint_consistency` — no cap on the number of page IDs in the comma-separated input. A caller can pass hundreds of page IDs, causing `build_consistency_context` to load and concatenate hundreds of full wiki pages — potentially many megabytes.
  (fix: add `if ids and len(ids) > 50: return "Error: Too many page IDs — max 50."`)

- `mcp/health.py:73-91` `kb_graph_viz` — `max_nodes=0` is the sentinel that disables pruning entirely (all nodes exported) with no warning. For a large wiki this produces an unbounded Mermaid payload.
  (fix: treat `max_nodes=0` as "use default 30" at the MCP layer; require callers to pass an explicit positive integer for unbounded output)

- `mcp/core.py:259-339` `kb_ingest_content` — the file existence check (line 309) and `atomic_text_write` are not atomic. Two concurrent `kb_ingest_content` calls with the same filename can both pass the existence check, both write, and the loser's cleanup `unlink` deletes the winner's file.
  (fix: use an exclusive open (`O_CREAT | O_EXCL`) to atomically create the file, removing the TOCTOU window)

- `mcp/browse.py:83-110` `kb_list_pages` — `page_type` is not validated against the known set of subdirectory names. Passing an unrecognised type silently returns "No pages found" rather than "Error: invalid page_type".
  (fix: add `if page_type and page_type not in WIKI_SUBDIR_TO_TYPE and page_type not in _TYPE_TO_SUBDIR: return f"Error: Unknown page_type '{page_type}'. Valid: ..."`)

<!-- existing items carried forward -->

- `query/rewriter.py:37-40` `rewrite_query` — skip heuristic misclassifies follow-ups as standalone: "Tell me more about that approach" has 5 words with len > 3 and is skipped despite containing deictic reference "that". The guard should check for pronoun/deictic tokens, not just word count.
  (fix: add `_REFERENCE_WORDS = re.compile(r"\b(it|this|that|they|these|those)\b", re.I)` and only skip when no reference words are present AND word count ≥ 5)

- `ingest/pipeline.py:617-634` `ingest_source` — O(n²) slug lookup when building `index_entries`: for each `pid` in created/updated lists, does `next((e for e in e_valid if slugify(e) == slug), slug)`. With max 50 entities + 50 concepts this is up to 400 linear scans per ingest.
  (fix: have `_process_item_batch` return a `slug_to_name: dict[str, str]` instead of recomputing slugs in the caller)

- `query/engine.py:159` `_flag_stale_results` — redundant inner import `from kb.config import PROJECT_ROOT` shadows the module-level import on line 13. Dead code.
  (fix: remove the inner import; `PROJECT_ROOT` is already in module scope)

- `query/engine.py:83` `vector_search` closure — `VectorIndex(vec_path)` re-instantiated on every query call; `idx.query()` opens a fresh SQLite connection, enables extension, loads `sqlite_vec`, executes, and closes. This runs for every search.
  (fix: cache the `VectorIndex` object at module level alongside the `_model` singleton in `embeddings.py`, keyed on `vec_path`)

- `ingest/evidence.py:34-46` `append_evidence_trail` — triple file I/O per new page: `_write_wiki_page` atomically writes the page (pipeline.py:139), then immediately calls `append_evidence_trail` which reads the file back and rewrites it (evidence.py:34,46). Every new page = write → read → write.
  (fix: accept an optional `initial_entry: str` param in `_write_wiki_page` and include the evidence trail section in the initial atomic write, skipping the separate read-modify-write)

- `ingest/contradiction.py:95-101` `_has_contradiction_signal` — symmetric negation check produces false negatives: `claim_has_signal != existing_has_signal` is False when both sides contain negation words (e.g., "X is not fast" vs "X is not slow"), so two negated claims about the same entity are never flagged.
  (fix: document this known limitation in the function docstring; or extend to also check for contradictory claim pairs where both sides are negated but negating different properties)

- `config.py:127-128` `EMBEDDING_DIM` — constant defined but never imported or validated anywhere. `embeddings.py` infers dimensionality at runtime from the model output with no assertion against this constant.
  (fix: either delete `EMBEDDING_DIM` or add `assert len(entries[0][1]) == EMBEDDING_DIM` in `VectorIndex.build()`)

---

### LOW

<!-- foundation -->

- `utils/markdown.py:5` `WIKILINK_PATTERN` — the pattern `[^\]|]{1,200}` permits embedded newlines in wikilink targets. `extract_wikilinks` passes these through after only `strip()`, producing page IDs with embedded newlines that generate dead-link warnings rather than being rejected at parse time.
  (fix: after `link.strip().removesuffix('.md').lower()`, add `.replace('\n', ' ').replace('\r', '')` — or reject links containing newlines entirely)

- `utils/wiki_log.py:28` `append_wiki_log` — `safe_op` and `safe_msg` sanitize `|` and newlines but leave tab characters intact. A tab in a log entry breaks the `date | operation | message` column format when log files are parsed by downstream tooling.
  (fix: add `.replace("\t", " ")` to both sanitization chains)

- `cli.py:49,50` `ingest` command error handler — `LLMError` messages can include the raw Anthropic API response body (several KB), printed untruncated to stderr. Applies to all five CLI command error handlers.
  (fix: `msg = str(e); click.echo(f"Error: {msg[:500]}{'...' if len(msg) > 500 else ''}", err=True)`)

<!-- graph -->

- `graph/builder.py:13-15` `_FRONTMATTER_RE` — defined identically in both `builder.py` and `compile/linker.py`. Two regexes compiled from the same pattern string at module load; both must be updated if the frontmatter format changes.
  (fix: move `_FRONTMATTER_RE` into `kb.utils.markdown` as a public constant and import it in both files)

- `graph/__init__.py:3` — `scan_wiki_pages` is exported in `__all__` but is only used internally. Exporting it invites callers that bypass the `build_graph` abstraction boundary.
  (fix: remove `scan_wiki_pages` from `__all__`; keep accessible as `kb.graph.builder.scan_wiki_pages` for internal use)

- `graph/builder.py:31-34` `page_id` — the function lowercases the result for the node ID, but the `path` node attribute stores the original-case filesystem path. On a case-sensitive filesystem, code that reconstructs paths from node IDs would get the wrong case. This inconsistency is undocumented.
  (fix: add a docstring note: "`path` node attributes retain original case and must be used for all filesystem I/O — do not reconstruct from the lowercased node ID")

- `graph/export.py:101-103` `export_mermaid` — Mermaid edge ordering is non-deterministic (depends on NetworkX internal adjacency dict order), making diagram output unstable across Python versions and harder to diff.
  (fix: replace `for source, target in subgraph.edges()` with `for source, target in sorted(subgraph.edges())`)

<!-- query / search -->

- `query/hybrid.py:63-64` `hybrid_search` — the comment "BM25 on original query only" is correct but the intentional asymmetry (BM25 uses original, vector uses expanded variants) is not explained. Easy to misread as an accidental omission.
  (fix: add comment: "# Intentional: BM25 uses original query only; expanded variants are for vector search where semantic drift is handled by cosine similarity")

- `query/engine.py:264-267` `_build_query_context` — `page['type']` and `page['confidence']` are accessed without `.get()` defaults. `load_all_pages` guarantees these fields, but the function signature accepts any `list[dict]`, making it brittle for ad-hoc callers.
  (fix: use `page.get('type', 'unknown')` and `page.get('confidence', 'unknown')`)

- `query/embeddings.py:12-13` — module-level `_model` singleton is never reset between tests. Test suites that monkeypatch or unload `model2vec` mid-run can leave `_model` pointing to a stale object in subsequent tests within the same process.
  (fix: expose a `_reset_model()` function for test teardown; document that the singleton persists for the process lifetime)

- `query/dedup.py:62-73` `_enforce_type_diversity` — the type ratio is enforced on the input to this layer, not the output. Post-filter the ratio can exceed `max_type_ratio` if few other types are present. The approximation is intentional but undocumented.
  (fix: add a docstring note explaining the known approximation)

<!-- compile / evolve -->

- `compile/compiler.py:27-34` `_template_hashes` — `sorted(TEMPLATES_DIR.glob("*.yaml"))` includes editor backup files (`~file.yaml`). Any YAML file dropped in the templates directory is treated as a template.
  (fix: add `if not tpl.stem.startswith(("~", "."))` filter, or check `tpl.stem in VALID_SOURCE_TYPES`)

- `evolve/analyzer.py:230-231` `generate_evolution_report` — `except (ImportError, AttributeError)` around `get_flagged_pages()` is too narrow. `OSError` and `json.JSONDecodeError` from a corrupt feedback file are not caught; the function propagates an unhandled exception instead of logging a warning and continuing.
  (fix: broaden to `except (ImportError, AttributeError, OSError, ValueError)`)

<!-- ingest -->

- `ingest/pipeline.py:314-321` `_update_existing_page` — if the existing References block ends with a trailing blank line, the appended reference is placed after it rather than before, producing inconsistent spacing.
  (fix: strip trailing blank lines: `m.group(1).rstrip("\n") + "\n" + ref_line + "\n"`)

- `ingest/pipeline.py:354` `_update_sources_mapping` — `source_ref` is embedded unescaped in the entry string and the containment check. If a `source_ref` contains a backtick (unusual but possible), the containment check may produce a false-positive match against an unrelated entry.
  (fix: escape backticks: `source_ref.replace("`", r"\`")` when embedding)

- `ingest/contradiction.py:28` `detect_contradictions` — `new_claims[:max_claims]` silently truncates with no log. With `CONTRADICTION_MAX_CLAIMS_TO_CHECK = 10` and sources that can have up to 50 key claims, 80% of claims are routinely dropped with no indication.
  (fix: add `if len(new_claims) > max_claims: logger.debug("Checking first %d of %d claims for contradictions", max_claims, len(new_claims))`)

<!-- lint / review / feedback -->

- `lint/semantic.py:37-48` `_render_sources` — budget is initialised from `sum(len(line) for line in lines)` but excludes the `\n` separators that `"\n".join` will insert. For a list of 70 entries, the budget is undercounted by 69 characters — negligible against 80K but technically incorrect.
  (fix: add `len(lines) - 1` to the initial `used` estimate to account for join separators)

- `lint/checks.py:356-383` `check_source_coverage` — `actual_dir.iterdir()` is not recursive. Source files nested in subdirectories (e.g., `raw/articles/2024/paper.md`) are silently ignored.
  (fix: use `actual_dir.rglob("*")` instead of `actual_dir.iterdir()`, or document that nested raw source directories are unsupported)

- `review/refiner.py:86-92` `refine_page` — the updated-date regex `r"updated: \d{4}-\d{2}-\d{2}"` is not anchored to line start. It would also match `last_updated: 2024-01-01` or a date pattern anywhere in the frontmatter body.
  (fix: anchor to line start: `r"^updated: \d{4}-\d{2}-\d{2}"` with `re.MULTILINE`)

- `lint/verdicts.py:68-76` `add_verdict` — `VALID_VERDICT_TYPES` is hard-coded in the `add_verdict` whitelist, and separately hard-coded in `get_verdict_summary`'s `by_type` dict. Adding a new verdict type to one place silently drops it from the other.
  (fix: define `VALID_VERDICT_TYPES = ("fidelity", "consistency", "completeness", "review")` at module level and reference it in both functions)

- `lint/checks.py:207-275` `check_staleness` — the `elif updated is not None and not isinstance(updated, date)` branch can only be reached if YAML parses the field as something other than a string, date, or datetime (e.g., an integer). In practice this is dead code for all standard YAML date representations; it adds maintenance noise without being exercisable by standard test fixtures.
  (fix: collapse to `else` with a clarifying comment, or add a test fixture that exercises it)

- `feedback/store.py:171-178` `add_feedback_entry` — the eviction strategy when `page_scores` exceeds `MAX_PAGE_SCORES` sorts by total activity count, which is undocumented. The 2× wrong-penalty used in the trust formula is not reflected in the eviction key.
  (fix: add a comment explaining the deliberate policy; or sort by trust-weighted activity for consistency with the trust formula)

<!-- MCP -->

- `mcp/quality.py:295-344` `kb_save_lint_verdict` — `issues` JSON array has no element count cap. An input with thousands of issue objects inflates `.data/verdicts.json`. The `MAX_VERDICTS` cap bounds entry count but not per-entry issue array size.
  (fix: add `if issue_list and len(issue_list) > 100: return "Error: Too many issues (max 100 per verdict)."`)

- `mcp/core.py:43-127` `kb_query` — `question` and `conversation_context` have no length bounds at the MCP layer. Very long questions are passed to `search_pages` without truncation and logged in error messages on failure.
  (fix: add `question = question[:MAX_QUESTION_LEN]` or return an error for oversized inputs, matching `kb_query_feedback`'s enforcement)

- `mcp/health.py:111-143` `kb_detect_drift` — `", ".join(ap["changed_sources"])` raises `TypeError` if `changed_sources` is `None` (possible after a schema change). This violates the MCP convention of never raising to the client.
  (fix: `sources_str = ", ".join(ap.get("changed_sources") or [])`)

<!-- existing items carried forward -->

- `query/bm25.py:21-104` `STOP_WORDS` and `ingest/contradiction.py:69-73` `_STOPWORDS` — two separate stopword frozensets with partial overlap. Adding a word to one does not update the other.
  (fix: consolidate into a single `STOPWORDS` constant in `kb.utils.text` and import in both modules)

- `ingest/pipeline.py:39` `_SOURCE_BLOCK_RE` — regex `(?:  - [^\n]*\n)*` assumes exactly 2-space YAML indentation. Manually-edited pages with 4-space or tab indentation won't match; the new source entry is then inserted with 2-space indent, creating mixed indentation.
  (fix: use `(?:[ \t]+- [^\n]*\n)*` and capture the indentation of the first existing entry to replicate it)

- `mcp/core.py:162-167` `kb_ingest` — path traversal check uses `path.relative_to(RAW_DIR.resolve())` without `os.path.normcase`, while `ingest_source` in pipeline.py uses `normcase` for Windows case-insensitive comparison. On Windows, a path with different casing could pass the MCP check and produce a confusing error from the pipeline layer.
  (fix: apply `Path(os.path.normcase(str(path)))` / `Path(os.path.normcase(str(RAW_DIR.resolve())))` in the MCP check, matching pipeline.py's approach)

- `query/dedup.py:47` `_dedup_by_text_similarity` — Jaccard similarity computed on `content_lower.split()` which includes wikilink syntax (`[[entities/foo|Bar]]`), Evidence Trail section headers, References section boilerplate, etc. Shared markup tokens inflate intersection for all pages, potentially over-deduplicating pages that share formatting but not content.
  (fix: strip markdown formatting and wikilinks before splitting, or reuse the BM25 tokenizer output which already filters these)

- `mcp/core.py:108` `kb_query` — `except Exception` in trust score merge block has no log entry. Failures are completely invisible, not even at debug level.
  (fix: add `logger.debug("Trust score merge failed: %s", e, exc_info=True)`)

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
