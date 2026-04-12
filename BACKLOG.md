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

- **HIGH** — all 23 HIGH-severity audit items resolved 2026-04-12 (fixes in `CHANGELOG.md` `[Unreleased]`). MEDIUM and LOW items below remain open.

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

## Phase 5 — Community followup proposals (2026-04-12)

<!-- Feature proposals sourced from Karpathy X post (Apr 2, 2026), gist thread, and 12+ community fork repos.
     Full rationale, attribution, and sources: research/karpathy-community-followup-2026-04-12.md
     These are FEATURE items, not bugs — severity buckets here = LEVERAGE (High / Medium / Low).
     "effort" in the parenthetical replaces "fix" in the bug format. -->

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

- `query/formats/` `kb_query --format={text|marp|html|chart|jupyter}` — adapters file output under `wiki/outputs/` with provenance linking back to query + contributing pages. Directly addresses Karpathy's tweet: *"render markdown files, slide shows (Marp format), matplotlib images"*. Source: Karpathy tweet + Fabian Williams + JupyterBook reply.
  (effort: Medium — one adapter per format; matplotlib adapter emits a Python script first, optional server-side render)

- `compile/publish.py` `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` — auto-generate AI-agent-consumable outputs alongside markdown during compile: each page gets `.txt`/`.json` siblings; wiki root gets `/llms.txt`, `/graph.jsonld`, `/sitemap.xml`. Makes the wiki itself a retrievable source for other agents. Source: Pratiyush/llm-wiki.
  (effort: Low — renderers over existing frontmatter + graph)

- `lint/augment.py` `kb_lint --augment` — action-mode lint: when a gap is detected (missing entity, unresolved citation, stub page), pull missing data via `fetch` MCP and append as a new raw source, re-ingesting automatically. Distinct from deferred `kb_evolve --research` (proactive gap-filling); this is reactive to lint findings. Source: Karpathy tweet (*"impute missing data with web searchers"*).
  (effort: Medium — lint check → fetch adapter → ingest dispatcher)

### MEDIUM LEVERAGE — Synthesis & Exploration

- `lint/consolidate.py` `kb_consolidate` — scheduled async background pass modeled on biological memory consolidation: NREM (new events → concepts, cross-event pattern extraction), REM (contradiction detection → mark old edges `superseded` rather than delete), Pre-Wake (graph health audit). Runs as nightly cron at scan tier. Source: Anda Hippocampus (ICPandaDAO).
  (effort: High — three distinct sub-passes; overlaps with existing lint/evolve but with "superseded" edge state as new primitive)

- `query/synthesize.py` `kb_synthesize [t1, t2, t3]` — k-topic combinatorial synthesis: walks paths through the wiki graph across a k-tuple of topics to surface cross-domain connections. New query mode beyond retrieval. Source: Elvis Saravia reply (*"O(n^k) synthesis across k domains — stoic philosophy × saas pricing × viral content × parenting"*).
  (effort: Medium — graph traversal + synthesis prompt; budget-gate k≥3 since path count explodes)

- `export/subset.py` `kb_export_subset <topic> --format=voice` — emit a topic-scoped wiki slice (standalone blob) loadable into voice-mode LLMs or mobile clients. Addresses *"interactive podcast while running"* use case. Source: Lex-style reply.
  (effort: Low — topic-anchored BFS + single-file markdown bundle)

### HIGH LEVERAGE — Ambient Capture & Session Integration

- `mcp/` `kb_capture` MCP tool — accept up to 50KB of conversation or note text; scan-tier LLM extracts discrete knowledge items (decisions, discoveries, corrections, gotchas) and filters noise; writes each item to `raw/captures/<slug>.md` with `source: mcp-capture` frontmatter; returns filenames for subsequent `kb_ingest`. Fills the gap `kb_ingest_content` cannot handle (it expects already-structured content). Source: sage-wiki `wiki_capture`.
  (effort: Medium — scan-tier extraction prompt + raw/captures/ directory convention + per-item slug writer)

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

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
