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
- **Phase 3.96** — all items resolved in v0.9.15
