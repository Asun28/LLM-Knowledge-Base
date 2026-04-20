# Cycle 16 — Design Spec (post-brainstorm, pre-eval)

**Date:** 2026-04-20
**Related:** `docs/superpowers/decisions/2026-04-20-cycle16-requirements.md`, `docs/superpowers/decisions/2026-04-20-cycle16-threat-model.md`, `docs/superpowers/decisions/2026-04-20-cycle16-design-gate.md`
**Approach:** A — vertical slices per AC cluster, commit-per-file (matches `feedback_batch_by_file`).
**Scope:** 24 ACs across 8 source files + 9 new test files.
**Step 5 decision gate:** 10 decisions baked in (Q1-Q10); 6 cross-Q conditions (C1-C6) enforced.

---

## Architecture — components and their contracts

### Component 1: `src/kb/config.py` additive constants (AC1-AC3)

Three pure data definitions inserted after existing cycle-14/15 constants:

```python
# Cycle 16 — new constants, additive
QUERY_REPHRASING_MAX: int = 3
DUPLICATE_SLUG_DISTANCE_THRESHOLD: int = 3
CALLOUT_MARKERS: tuple[str, ...] = ("contradiction", "gap", "stale", "key-insight")
```

Docstring above each names the consumer module to clear the cycle-1-in-isolation-review risk.

### Component 2: `src/kb/evolve/analyzer.py` enrichment targets (AC4-AC6)

- **New function** `suggest_enrichment_targets(wiki_dir: Path | None = None, pages_dicts: list[dict] | None = None, *, status_priority: Sequence[str] = ("seed", "developing")) -> list[dict]`
  - Walks `load_all_pages(wiki_dir)` when `pages_dicts is None` (reuses cycle-14 AC23's loader-side `status` field).
  - **Q4/amendment (2026-04-20):** absent-status pages INCLUDED (sorted last). Two filters ONLY:
    - Drop if `status` is a non-empty value NOT in `PAGE_STATUSES` (T13 — rejects `"<script>"` / injection).
    - Drop if `status in {"mature", "evergreen"}` per AC4.
  - Sort key: `(priority_index, page_id)` where `priority_index = status_priority.index(status)` if `status in status_priority` else `len(status_priority)` (unknown/absent statuses sort last).
  - Dict shape: `{"page_id": str, "status": str, "reason": str}` — `reason` is a short human-readable string (`"status=seed — needs initial fleshing out"` / `"status=developing — needs refinement"` / `"status=<unknown> — needs triage"` for absent/empty).
- **`generate_evolution_report` extension**: threads the already-loaded `pages_dicts` into the new helper, adds `enrichment_targets` key to the returned dict. If `enrichment_targets` is non-empty, append one recommendation string mirroring the existing pattern ("N page(s) ranked by status priority. Top: x, y, z.").
- **`format_evolution_report` extension**: render a new `### Enrichment targets` section listing top 10 by priority. Status values passed through `yaml_escape` (existing helper) for safety (T13 defense-in-depth).

### Component 3: `src/kb/query/engine.py` rephrasings (AC7-AC9)

- **New module-level helper** `_normalise_for_echo(s: str) -> str: return re.sub(r"[\W_]+", " ", s).strip().lower()` — used by the echo filter (Q6/C5).
- **New private helper** `_suggest_rephrasings(question: str, context_pages: list[dict], *, max_suggestions: int = QUERY_REPHRASING_MAX) -> list[str]`:
  - Returns `[]` when `context_pages` is empty (skip LLM call).
  - Returns `[]` on exception from `call_llm(tier="scan")` — narrow except `(LLMError, OSError) as exc: logger.debug("rephrasings failed: %s", exc); return []` (Q5/C5).
  - Prompt template (constant module-level string):
    ```
    The user asked: "<QUESTION_TRUNCATED_80>"
    Known wiki pages (titles only):
    <page_title>TITLE_1</page_title>
    <page_title>TITLE_2</page_title>
    ...
    Suggest up to N alternative phrasings that would match different page titles.
    Return one phrasing per line. Do not repeat the original question.
    ```
    Titles are truncated to 200 chars each (T4) and run through `yaml_escape` to strip bidi / control chars. The prompt never interpolates the full question body — only `question[:80]` (T11).
  - Parse LLM output line-by-line. Per-line hardening (Q5/C5):
    - strip whitespace
    - strip leading bullets/numbers via `re.sub(r"^\s*(?:\d+[.)]|[-*•])\s*", "", line)`
    - drop empties
    - drop lines > 300 chars (garbage)
    - drop lines containing `\n` after strip (malformed)
    - drop lines whose `_normalise_for_echo` equals the original question's `_normalise_for_echo` (Q6/C5 — catches `"X?"` / `"X."` / case-shifted echoes)
    - cap at `max_suggestions`
  - Logging: `logger.info("rephrasing request for q=%r", question[:80])` — truncated (T11).
- **`query_wiki` extension** at the low-coverage refusal branch (current line ~1060):
  - Before building `refusal_advisory`, call `rephrasings = _suggest_rephrasings(normalized_question, matching_pages)`.
  - Extend `result_dict` with `"rephrasings": rephrasings` when `low_confidence` is True. Not emitted on the non-refusal path.
  - Advisory text unchanged (AC8 says additive — the rephrasings live in the result dict, not embedded in the string).

### Component 4: `src/kb/lint/checks.py` duplicate-slug + callouts (AC10-AC13)

- **New helper** `_bounded_edit_distance(a: str, b: str, threshold: int) -> int`: pure-stdlib two-row dynamic-programming Levenshtein that early-exits when the running row minimum exceeds `threshold`, returning `threshold + 1`. Unit-tested directly.
- **New check** `check_duplicate_slugs(wiki_dir: Path | None = None, pages: list[Path] | None = None) -> list[dict]`:
  - Loads pages via `scan_wiki_pages`, extracts `page_id(p, wiki_dir)` for each.
  - **Length-bucket strategy (T6 + Q10/C6)**: group slugs by `len(slug)`. Iteration: for each bucket of length L, compare slugs against buckets `[L, L+1, ..., L+DUPLICATE_SLUG_DISTANCE_THRESHOLD]` — radius = threshold, NOT ±1. (Levenshtein lower bound: `distance >= abs(len(a) - len(b))`; radius 1 misses distance-2/3 pairs.) Symmetric below handled by iteration order.
  - Hard cap: `len(pages) <= 10_000` — when exceeded, returns a single dict `{"slug_a": "<skipped>", "slug_b": "<skipped>", "distance": -1, "page_a": "", "page_b": "", "skipped_reason": "wiki too large"}`. One-line warning in `runner.format_report` handles this gracefully.
  - For each candidate pair, call `_bounded_edit_distance(slug_a, slug_b, DUPLICATE_SLUG_DISTANCE_THRESHOLD)`. Keep pairs with `0 < distance <= threshold`.
  - Return dicts: `{"slug_a": str, "slug_b": str, "distance": int, "page_a": str, "page_b": str}`.
- **New helper** `parse_inline_callouts(content: str) -> list[dict]`:
  - Page-body cap: skip pages > 1 MB raw (T5).
  - Pattern (compile once at module scope):
    ```python
    _CALLOUT_MARKER_PATTERN = "|".join(re.escape(m) for m in CALLOUT_MARKERS)
    _CALLOUT_RE = re.compile(
        r"^> \[!(" + _CALLOUT_MARKER_PATTERN + r")\][^\n]*$",
        re.MULTILINE | re.IGNORECASE,
    )
    ```
  - Iterate matches; return list of `{"marker": m.group(1).lower(), "line": line_number, "text": m.group(0)}`.
  - **Per-page cap: 500 matches** (T12); one truncation record appended as `{"marker": "__truncated__", "line": 0, "text": "truncated at 500 matches"}`.
- **New check** `check_inline_callouts(wiki_dir: Path | None = None, pages: list[Path] | None = None) -> list[dict]`:
  - Walks pages via `scan_wiki_pages`; skips unreadable ones with `logger.warning`.
  - **Cross-page cap: 10_000 results total** (T12); appends one truncation dict and breaks outer loop.
  - Return dicts: `{"page_id": str, "marker": str, "line": int, "text": str}`.

### Component 5: `src/kb/lint/runner.py` wiring (AC14-AC16)

- `run_all_checks` adds two calls:
  ```python
  report["duplicate_slugs"] = check_duplicate_slugs(wiki_dir=wiki_dir, pages=pages)
  report["inline_callouts"] = check_inline_callouts(wiki_dir=wiki_dir, pages=pages)
  ```
  Both receive the already-scanned `pages` list (no extra disk walk).
- Summary counters: `warning += len(duplicate_slugs)`, `info += len(inline_callouts)`. **Q7 amendment (2026-04-20):** `severity_counts` is already initialised at `runner.py:138` with `{"error": 0, "warning": 0, "info": 0}` — do NOT emit a defensive `setdefault("info", 0)`. Add lock-in test `report["summary"]["info"] == len(inline_callouts)` so any future regression to the init shape is caught by test, not masked by dead code.
- `format_report` appends two new sections ONLY when non-empty:
  - `## Duplicate slugs` — one bullet per item: `- {slug_a} <-> {slug_b} (distance {d}): {page_a}, {page_b}`.
  - `## Inline callouts` — one bullet per item: `- [{marker}] {page_id}:{line} — {text[:80]}`.

### Component 6: `src/kb/mcp/core.py` `kb_query save_as` (AC17-AC19)

- **New private helper** `_validate_save_as_slug(slug: str) -> tuple[str, str | None]`:
  - Returns `(normalized_slug, None)` on success OR `("", "Error: ...")` on failure.
  - Rejects (returning error strings, NEVER raising — T15/C2):
    - `len(slug) > 80` → `"Error: save_as too long (max 80 chars)"`
    - `slug.strip() != slug` OR `not slug.strip()` → `"Error: save_as cannot be empty or whitespace-padded"`
    - `".." in slug` or `slug.startswith("/")` or `"\\" in slug` → `"Error: save_as cannot contain path separators or .."`
    - **Q3/C4 amendment (2026-04-20):** BOTH checks required:
      - `slugify(slug) != slug` → `"Error: save_as must match slug form (lowercase, hyphenated)"` (catches uppercase / whitespace / symbols)
      - `not re.fullmatch(r"[a-z0-9-]+", slug)` → `"Error: save_as must be ASCII lowercase alphanumeric with hyphens only"` (T1 anti-homoglyph — catches Cyrillic `а` and CJK that slugify preserves via `\w` without `re.ASCII`)
    - Windows reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) — reuse `_is_windows_reserved` from `src/kb/mcp/app.py:198`
  - On success, returns the normalised slug.
- **`kb_query` extension** (keyword-only arg): `save_as: str | None = None`.
  - **Q8 amendment (2026-04-20):** Docstring MUST prominently note: "`save_as` performs a filesystem write to `wiki/synthesis/` — when set, this tool is a write, not a read. Frontmatter is hardcoded (`type=synthesis`, `confidence=inferred`, `authored_by=llm`); `source` is derived from `source_pages`."
  - When `save_as` is truthy AND answer synthesised (NOT a refusal — `result_dict.get("low_confidence") != True`):
    - Validate via `_validate_save_as_slug(save_as)`.
    - Build target path: `WIKI_DIR / "synthesis" / f"{slug}.md"` (reuse existing `WIKI_SYNTHESIS` constant from `config.py:66` if present; otherwise compose).
    - Final check: `target.resolve().is_relative_to((WIKI_DIR / "synthesis").resolve())` — belt-and-suspenders (T1).
    - **Q1/C1 amendment (2026-04-20):** `source_list = list(result_dict.get("source_pages") or [])`. If `source_list` is empty, return `"Error: cannot save synthesis — query returned no source_pages"` (do NOT write — `validate_frontmatter` at `src/kb/models/frontmatter.py:48` rejects empty `source:` list).
    - Build frontmatter dict — hardcoded, NOT parameterised (T2):
      ```python
      import frontmatter
      post = frontmatter.Post(
          answer_text,
          title=save_as.replace("-", " ").title(),  # "my-great-topic" → "My Great Topic" (inline, no helper)
          source=source_list,          # derived from query's source_pages (Q1/C1)
          created=today_iso(),
          updated=today_iso(),
          type="synthesis",
          confidence="inferred",
          authored_by="llm",
      )
      save_page_frontmatter(target, post)
      ```
    - On collision (file exists): return `"Error: save_as target already exists"` (do not overwrite). MCP tool returns error string, query result still returned.
    - On success: append `result_dict["saved_as"] = str(target.relative_to(WIKI_DIR))` to the returned dict.

### Component 7: `src/kb/compile/publish.py` siblings + sitemap (AC20-AC22)

- **New builder** `build_per_page_siblings(wiki_dir: Path, out_dir: Path, *, incremental: bool = False) -> list[Path]`:
  - `pages = load_all_pages(wiki_dir)` — reuses loader.
  - `kept, excluded = _partition_pages(pages)` — BEFORE `_publish_skip_if_unchanged` (T10 cycle-15 L3 pattern).
  - Target base: `pages_dir = out_dir / "pages"`; create via `pages_dir.mkdir(parents=True, exist_ok=True)`.
  - **Q2/C3 amendment (2026-04-20):** Stale-sibling cleanup runs UNCONDITIONALLY (every call, regardless of `incremental`), BEFORE `_publish_skip_if_unchanged`. For each `page in excluded`, compute `target_txt = pages_dir / f"{page_id}.txt"` and `target_json = target_txt.with_suffix(".json")` and call `.unlink(missing_ok=True)` on each. One-line comment: `# T10 — retracted-page cleanup must run BEFORE skip; incremental=True would otherwise leak stale siblings`. Follow-up for manifest-based approach tracked in BACKLOG when N(retracted) > ~1000.
  - Incremental skip: if `incremental=True` and `_publish_skip_if_unchanged(wiki_dir, pages_dir)` returns True, return the existing set of files (cleanup already ran).
  - For each `page in kept`:
    - `page_id = page["id"]`.
    - `target_txt = pages_dir / f"{page_id}.txt"`.
    - **T9 containment check**: `assert target_txt.resolve().is_relative_to(pages_dir.resolve())` — skip with `logger.warning` if not.
    - `target_txt.parent.mkdir(parents=True, exist_ok=True)` (handles subdir page IDs).
    - Body = `title + "\n\n" + body` (plaintext, no markdown stripping this cycle).
    - `atomic_text_write(body, target_txt)`.
    - `target_json = target_txt.with_suffix(".json")`.
    - **R1 amendment — determinism:** `atomic_json_write` does NOT accept `sort_keys`; compose via stdlib instead: `json_body = json.dumps({"title":..., "page_id":..., "url":..., "updated":..., "confidence":..., "belief_state":..., "authored_by":..., "status":..., "source":[...]}, indent=2, sort_keys=True, ensure_ascii=False)` then `atomic_text_write(json_body + "\n", target_json)`. `sort_keys=True` gives deterministic byte output cross-platform; AC22 "idempotent" invariant holds.
  - Return sorted list of paths written.
- **New builder** `build_sitemap_xml(wiki_dir: Path, out_path: Path, *, incremental: bool = False) -> Path`:
  - `pages = load_all_pages(wiki_dir)`; `kept, _ = _partition_pages(pages)` — BEFORE skip.
  - Incremental skip: `_publish_skip_if_unchanged(wiki_dir, out_path)` → return `out_path`.
  - Construct XML via `ET`:
    ```python
    import xml.etree.ElementTree as ET
    urlset = ET.Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for page in sorted(kept, key=lambda p: p["id"]):
        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = f"pages/{page['id']}.txt"  # T8 relative POSIX
        lastmod_text = str(page.get("updated", "")).strip()
        if lastmod_text:
            ET.SubElement(url, "lastmod").text = lastmod_text
    body = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(urlset, encoding="unicode")
    atomic_text_write(body, out_path)
    ```
  - Return `out_path`.

### Component 8: `src/kb/cli.py` publish flag extension (AC23-AC24)

- `publish --format` `click.Choice` grows to `["llms", "llms-full", "graph", "siblings", "sitemap", "all"]`.
- Existing `out_dir` path derivation unchanged.
- New dispatch clauses:
  ```python
  if fmt in ("siblings", "all"):
      build_per_page_siblings(WIKI_DIR, out_dir, incremental=incremental)
  if fmt in ("sitemap", "all"):
      build_sitemap_xml(WIKI_DIR, out_dir / "sitemap.xml", incremental=incremental)
  ```

---

## Data flow summary

```
kb_query(question, save_as)
    ├─ query_wiki(question) → result_dict {answer, low_confidence?, rephrasings?}
    │     └─ if low_confidence: _suggest_rephrasings(question, matching_pages) → list[str]
    ├─ if save_as and not refusal: _validate_save_as_slug → save_page_frontmatter
    └─ return result_dict + saved_as?

kb lint
    └─ run_all_checks → report {..., duplicate_slugs, inline_callouts}
          ├─ check_duplicate_slugs → length-bucketed pairs → bounded edit-distance
          └─ check_inline_callouts → _CALLOUT_RE over each page

kb evolve
    └─ generate_evolution_report → report {..., enrichment_targets}
          └─ suggest_enrichment_targets → status-priority sort on load_all_pages

kb publish --format=all
    ├─ build_llms_txt (existing)
    ├─ build_llms_full_txt (existing)
    ├─ build_graph_jsonld (existing)
    ├─ build_per_page_siblings → {out_dir}/pages/{page_id}.{txt,json}
    └─ build_sitemap_xml → {out_dir}/sitemap.xml
```

## Error handling contract

- MCP tools (`kb_query`): return `"Error: ..."` strings on validation failure (T15). Never raise past the boundary.
- Library functions (`_suggest_rephrasings`, `check_duplicate_slugs`, `check_inline_callouts`, `build_per_page_siblings`, `build_sitemap_xml`): return best-effort results; log warnings on individual page failures; never abort a full scan for one bad file.
- `_validate_save_as_slug`: returns `(slug, None | error_str)` — explicit tuple, no exceptions.

## Testing plan (9 new test files)

| File | ACs | Key assertions |
|---|---|---|
| `test_cycle16_config_constants.py` | AC1-AC3 | Values + types + immutability of `CALLOUT_MARKERS` tuple |
| `test_cycle16_enrichment_targets.py` | AC4-AC6, T13 | Status-priority sort; `mature`/`evergreen` excluded; unknown status excluded; `<script>` status filtered; `generate_evolution_report` new key; `format_evolution_report` renders new section |
| `test_cycle16_rephrasings.py` | AC7-AC9, T3/T4/T11 | `[]` on empty context; `[]` on LLM error; echo filter case-insensitive; hostile title truncated in prompt; prompt log truncated to ≤80 chars; max_suggestions cap |
| `test_cycle16_duplicate_slugs.py` | AC10, AC13, T6, T14 | `attention` vs `attnetion` flagged (d=2); `attention` vs `attention-mechanism` NOT flagged (d=10); `concepts/attention` vs `entities/attention` treated correctly; 15k-page fixture returns skip record |
| `test_cycle16_inline_callouts.py` | AC11-AC12, T5, T12 | All 4 markers recognised; case-insensitive marker; 1MB body cap; 500-match per-page truncation; 10K cross-page truncation; unclosed `> [!gap` not matched |
| `test_cycle16_lint_wiring.py` | AC14-AC16 | `run_all_checks` emits new keys; `format_report` renders sections when non-empty; omits sections when empty; summary counters incremented |
| `test_cycle16_kb_query_save_as.py` | AC17-AC19, T1/T2/T15 | Happy path writes `wiki/synthesis/my-topic.md` with hardcoded frontmatter; `..`/`/abs`/`\\backslash`/Unicode homoglyph rejected as error strings; refusal path skips save; collision returns error; never raises under `KB_DEBUG=1` |
| `test_cycle16_publish_siblings_sitemap.py` | AC20-AC22, T7/T8/T9/T10 | Happy path emits `.txt`+`.json` per kept page; retracted excluded; stale-sibling cleanup on non-incremental; incremental skip honoured; subdir page IDs write correctly; sitemap XML escapes `&`/`<`; `<loc>` relative POSIX; round-trip parse via `ET.fromstring` |
| `test_cycle16_cli_publish.py` | AC23-AC24 | `--format=siblings` dispatches sibling builder only; `--format=sitemap` dispatches sitemap only; `--format=all` dispatches all 5; `--incremental` honoured |

Each test file imports from production via `from kb.<module> import <symbol>` and calls the symbol directly — no `inspect.getsource`, no `read_text().splitlines()` (cycle-11 L2 Red Flag).

## Rollback plan

Every AC's production change is additive:
- Dropping the cycle-16 branch reverts `config.py` to cycle-15 state (constants go away, no consumer breakage because every consumer is also added in this cycle).
- Dropping `suggest_enrichment_targets` leaves `generate_evolution_report` output unchanged (keys not present).
- Dropping `_suggest_rephrasings` leaves `result_dict` without `rephrasings` key (optional; consumers check `.get()`).
- Dropping new lint checks leaves `run_all_checks` report without the two new keys (formatter omits).
- Dropping `save_as` kwarg: callers not passing it see no change.
- Dropping sibling + sitemap builders: CLI falls back to previous `--format` choices.

## Step 5 decision gate — RESOLVED

All 6 pre-gate questions + 10 Step-5 questions resolved in `docs/superpowers/decisions/2026-04-20-cycle16-design-gate.md`. Conditions C1-C6 hold as invariants. See design-gate doc for per-question rationale.

Key pre-gate decisions (retained):
1. Slug length cap: **80 chars**.
2. `mature/evergreen` exclusion: stays — staleness surfaces via cycle-15 `check_status_mature_stale`.
3. Per-sibling content-skip: NOT this cycle; `incremental=True` gate at dir level matches existing builders.
4. Sitemap `<changefreq>` / `<priority>`: OMIT.
5. Rephrasings in result_dict as separate key (not embedded in advisory string).
6. Enrichment recommendation AFTER stubs in `format_evolution_report`.

Q1-Q10 decisions (see design-gate doc): b, a, b, b, b, b, drop-conditional, c, c, b.

## Symbol verification (cycle-15 L1 gate)

Ran at Step 1 on these call sites; confirmed EXISTS:
- `load_all_pages` → `src/kb/utils/pages.py` with `status` field (cycle-14 AC23)
- `save_page_frontmatter` → `src/kb/utils/pages.py` (cycle-14 AC16)
- `scan_wiki_pages`, `page_id` → `src/kb/utils/pages.py`
- `slugify`, `yaml_escape` → `src/kb/utils/text.py`
- `atomic_text_write`, `atomic_json_write` → `src/kb/utils/io.py`
- `_partition_pages`, `_publish_skip_if_unchanged`, `_is_excluded` → `src/kb/compile/publish.py` (cycle-14/15)
- `generate_evolution_report`, `suggest_new_pages` → `src/kb/evolve/analyzer.py` (existing; `suggest_new_pages` returns DEAD-LINK TARGETS, not existing pages — cycle-16 new function complements, does not duplicate)
- `query_wiki`, `low_confidence` branch → `src/kb/query/engine.py` (cycle-14 AC5 lines 1060-1066)
- `kb_query` MCP tool → `src/kb/mcp/core.py:89-227`
- `run_all_checks`, `format_report` → `src/kb/lint/runner.py`
- `publish` CLI → `src/kb/cli.py:340-389`
- `PAGE_STATUSES`, `BELIEF_STATES`, `AUTHORED_BY_VALUES` → `src/kb/config.py` (cycle-14 AC1)
- `QUERY_COVERAGE_CONFIDENCE_THRESHOLD` → `src/kb/config.py` (cycle-14 AC4)

Zero symbol mismatches.
