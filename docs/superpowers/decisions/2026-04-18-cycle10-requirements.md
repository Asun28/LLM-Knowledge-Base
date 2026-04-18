# Cycle 10 Requirements & Acceptance Criteria

**Date:** 2026-04-18
**Branch:** `feat/backlog-by-file-cycle10`
**Scope:** Close cycle-9 scope-out class (`_validate_wiki_dir` migration for the
remaining 4 MCP tools), standardise `_safe_call` silent-degradation use at one
open `kb_refine_page` site, harden `kb_search` / `kb_read_page` edge cases,
`capture.py` UUID prompt delimiter + submission-time `captured_at`,
`ingest.pipeline` extraction-field type validation, `hybrid_search` cosine
floor for no-results queries, and CLAUDE.md `raw/captures/` architectural
exception.

## Problem

BACKLOG.md lists ~30 open bug-class items surfaced across Phase 4.5 R1–R6 and
Phase 5 pre-merge reviews. Several are one-commit fixes that were deliberately
scoped out of earlier cycles (cycle 9 R1 explicitly flagged the
`_validate_wiki_dir` migration for 4 tools). This cycle groups them by file per
the `feedback_batch_by_file` memory (HIGH+MEDIUM+LOW together).

### Grep-verified baseline (cycle 8 Red Flag: verify symbols before scoping)

- `_validate_wiki_dir` — **exists** at `mcp/app.py:187`, signature
  `(wiki_dir: str | None) -> tuple[Path | None, str | None]`. Already used by
  `mcp/core.py:624`, `mcp/health.py:56, 116`.
- `_safe_call` — **exists** at `kb/lint/_safe_call.py:20`, signature
  `(fn, *, fallback, label, log=None) -> tuple[T|None, str|None]`. Already used
  by `lint/runner.py:137`, `mcp/health.py:72`.
- `_sanitize_error_str` — **exists** at `mcp/app.py:145`. Used throughout
  `core.py`, `browse.py`, `quality.py`, `health.py` for error-path redaction.
- `append_wiki_log` — **already has** `newline="\n"` AND `file_lock` wrap
  (wiki_log.py:114, 126-127). Cycle 2 item #29 + S1 HIGH covered both fixes.
  BACKLOG line "torn-last-line under concurrent append" is STALE. Dropped from
  AC set.
- `kb_search` — **already renders `[STALE]`** at `browse.py:57-61` (G2, Phase
  4.5 R4 HIGH). BACKLOG "stale flag NOT surfaced" is STALE. Dropped.
- `captured_at` in `capture.py:726` — is computed AFTER the `_extract_items_via_llm`
  call at 718. BACKLOG's "move to submission time" AC is still valid — move to
  before the LLM call.
- `hybrid_search` in `query/hybrid.py:54` — has per-backend try/except but no
  cosine-similarity floor. BACKLOG's "gate vector-search results on
  cosine >= VECTOR_MIN_SIMILARITY (~0.3)" is VALID.

## Non-goals

- No refactor of `compile/compiler.py` naming inversion or `ingest/pipeline.py`
  11-stage locking — those are multi-cycle structural changes.
- No new MCP tools; this cycle only hardens existing ones.
- No `kb_merge`, `belief_state`, `status` frontmatter — Phase 5 feature
  proposals, separate cycles.
- No CLI smoke test for every command (cycle 8 AC30 `kb --version` short-circuit
  is fragile; another cycle).
- No `multiprocessing`-based integration tests — Phase 4.5 HIGH deferred.

## Affected modules (blast radius)

- `src/kb/mcp/browse.py` — kb_search length cap; kb_read_page ambiguity;
  kb_stats validator migration.
- `src/kb/mcp/health.py` — kb_graph_viz / kb_verdict_trends / kb_detect_drift
  validator migration.
- `src/kb/mcp/quality.py` — `_safe_call` applied at `kb_refine_page` backlinks
  site.
- `src/kb/compile/compiler.py` — `detect_source_drift` docstring clarification.
- `src/kb/capture.py` — UUID prompt boundary; `captured_at` submission time.
- `src/kb/ingest/pipeline.py` — `_coerce_str_field` helper.
- `src/kb/config.py` — `VECTOR_MIN_SIMILARITY` constant.
- `src/kb/query/hybrid.py` — cosine-floor filter.
- `CLAUDE.md` — `raw/captures/` exception language.
- `tests/test_cycle10_*.py` — new per-area test files.

## Acceptance Criteria (28 ACs, 13 files)

Each AC is testable pass/fail. Grouped by file per `feedback_batch_by_file`.

### File: `src/kb/mcp/quality.py`

- **AC1 — `kb_refine_page` backlinks lookup uses `_safe_call`.** The current
  `try / except Exception: affected = []` block at lines ~102-110 is replaced
  by `backlinks_map, err = _safe_call(lambda: build_backlinks(), fallback={},
  label="backlinks")`. When `err` is non-None the response string appends
  `f"\n[warn] {err}"` so users see the degradation instead of an empty
  "Affected pages" section. Existing success path unchanged.

### File: `src/kb/mcp/browse.py`

- **AC2 — `kb_read_page` ambiguity error on >1 case-insensitive match.** The
  `subdir.glob("*.md")` fallback, if two or more filenames in a single subdir
  match case-insensitively, returns
  `Error: ambiguous page_id — multiple files match {page_id}: {comma-separated sorted stems}`
  rather than silently picking `glob`-insertion-order first. Single
  case-insensitive match preserves current behaviour.
- **AC3 — `kb_stats` uses `_validate_wiki_dir`.** The manual
  `Path(wiki_dir).resolve() + wiki_path.relative_to(PROJECT_ROOT.resolve())`
  block at `browse.py:325-328` is replaced with
  `wiki_path, err = _validate_wiki_dir(wiki_dir)` from `kb.mcp.app`. Rejects
  parent-traversal and absolute-outside-project paths with
  `Error: Invalid wiki_dir — {_sanitize_error_str(e)}`, matching the cycle-9
  pattern `kb_lint` / `kb_evolve` / `kb_compile_scan` use.

Note: `kb_search` length cap is **already applied** at `browse.py:43-44`
(imported from `kb.config.MAX_QUESTION_LEN`). BACKLOG line listed this as open
— it is not. `kb_search` stale marker is also already applied at
`browse.py:57-61`. Both confirmed via grep.

### File: `src/kb/mcp/health.py`

- **AC4 — `kb_graph_viz` uses `_validate_wiki_dir`.** The `Path(wiki_dir) if
  wiki_dir else None` block at `health.py:177` is replaced with
  `wiki_path, err = _validate_wiki_dir(wiki_dir); if err: return f"Error:
  {err}"`. This TIGHTENS security — the current pattern has NO containment
  check at all; an attacker-controlled `wiki_dir` could be an absolute path
  outside the project root.
- **AC5 — `kb_verdict_trends` uses `_validate_wiki_dir`.** The manual
  `.resolve() + relative_to(PROJECT_ROOT)` block at `health.py:194-198` is
  replaced with the helper. Preserves the `verdicts_path = wiki_path.parent /
  ".data" / "verdicts.json"` derivation.
- **AC6 — `kb_detect_drift` uses `_validate_wiki_dir`.** The `Path(wiki_dir) if
  wiki_dir else None` block at `health.py:223` is replaced with the helper.
  Same security tightening as AC4.

### File: `src/kb/config.py`

- **AC7 — `VECTOR_MIN_SIMILARITY = 0.3` constant added.** New config constant
  named `VECTOR_MIN_SIMILARITY` set to `0.3`. Exported via the `kb.config`
  import surface. Module docstring comment: "Minimum vector-search cosine
  similarity before a result contributes to RRF fusion. Below this, treat the
  vector backend as silent for that query."

### File: `src/kb/query/hybrid.py`

- **AC8 — `hybrid_search` filters vec results below `VECTOR_MIN_SIMILARITY`.**
  Between the `vec_results = vector_fn(q, vector_limit)` call and the
  `all_lists.append(vec_results)`, `hybrid_search` filters:
  `vec_results = [r for r in vec_results if r.get("score", 0.0) >= VECTOR_MIN_SIMILARITY]`.
  If all variants contribute zero filtered vec-results AND BM25 is empty, the
  function returns `[]` instead of the current behaviour where any positive
  vector score surfaces a hit. Logger emits `logger.debug("vec below min-sim:
  %d dropped", n)` so operators can observe the drop rate without noise.

### File: `src/kb/compile/compiler.py`

- **AC9 — `detect_source_drift` docstring documents deletion-pruning
  persistence.** The docstring of `detect_source_drift` explicitly states:
  "Deletion-pruning of manifest entries is always persisted even though
  `save_hashes=False` is passed to `find_changed_sources`, because lingering
  deleted-source entries would corrupt subsequent `find_changed_sources`
  calls. This is the single exception to the read-only contract; callers
  should NOT assume `detect_source_drift` is side-effect-free on the manifest
  when raw sources have been deleted." A matching one-line note is added to
  CLAUDE.md's "Error Handling Conventions" section. No code change.

### File: `src/kb/capture.py`

- **AC10 — `_extract_items_via_llm` uses UUID-boundary delimiters.** A
  per-call boundary is computed via `boundary = secrets.token_hex(16)`. The
  prompt template references `f"<<<INPUT-{boundary}>>>"` /
  `f"<<<END-INPUT-{boundary}>>>"`. Before rendering, the function verifies
  neither fence string appears in the input; on collision (cryptographically
  implausible but checked), a fresh boundary is regenerated up to 3 times
  before raising `CaptureError("boundary collision after 3 retries — input
  may be adversarial")`. The existing `_escape_prompt_fences` + `_FENCE_*_RE`
  regex machinery stays in place as defense-in-depth; the new UUID boundary
  is an ADDITIONAL layer.
- **AC11 — `captured_at` reflects submission time.** The
  `captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` line at
  `capture.py:726` is moved to immediately after `_resolve_provenance(...)`
  at line 668, so the persisted timestamp is close to submission rather than
  post-LLM completion. Variable passed through to `_write_item_files` at
  727-728 remains unchanged. `CaptureResult` docstring updated to describe
  `captured_at` as "submission time (UTC ISO-8601)".

### File: `src/kb/ingest/pipeline.py`

- **AC12 — `_coerce_str_field(extraction, field)` helper added.** New private
  helper:
  ```python
  def _coerce_str_field(extraction: dict, field: str) -> str:
      value = extraction.get(field)
      if value is None:
          return ""
      if isinstance(value, str):
          return value
      raise IngestError(
          f"extraction field {field!r} must be string, "
          f"got {type(value).__name__}"
      )
  ```
  If `IngestError` is not yet defined, raises `ValueError` instead. Does NOT
  mutate the extraction dict. Returns `""` for missing/None keys so downstream
  `.lower()` / `.replace()` work.
- **AC13 — `_coerce_str_field` applied at `_build_summary_content` sites.**
  The specific string-consuming sites in `_build_summary_content` (~321-400)
  where the code does `.lower()`, `.replace()`, or f-string concatenation on
  `extraction["title"]`, `extraction["author"]`, `extraction["core_argument"]`
  use `_coerce_str_field(extraction, field)`. Scope is INTENTIONALLY LIMITED
  to `_build_summary_content` for cycle 10 (the most-hit path where
  extraction-field malformedness cascades into filesystem writes). Phase 4.5
  MEDIUM's "10+ read sites" is tracked for follow-up.

### File: `CLAUDE.md`

- **AC14 — `raw/captures/` exception carved out.** The "Three-Layer Content
  Structure" section's `raw/` description gains a parenthetical:
  `(except raw/captures/, which is the sole LLM-written output directory
  inside raw/ — atomised via kb_capture, then treated as raw input for
  subsequent ingest)`. The existing `raw/captures/` subdirectory listing
  cross-references the exception.

### File: `tests/test_cycle10_quality.py` (new)

- **AC15 — Test `kb_refine_page` surfaces `backlinks_error`.** Create a wiki
  page, monkeypatch `kb.compile.linker.build_backlinks` to raise
  `OSError("corrupt manifest")`. Call `kb_refine_page(page_id, "new content",
  "notes")`. Assert the returned string contains the substring
  `"[warn] backlinks_error:"` AND `"corrupt manifest"`. Assert the refine
  itself still succeeded (response starts with `"Refined: {page_id}"`).

### File: `tests/test_cycle10_browse.py` (new)

- **AC16 — Test `kb_read_page` ambiguity on >1 case-insensitive match.** Seed
  `tmp_wiki / "concepts" / "foo-bar.md"` and (on case-sensitive FS) also
  `tmp_wiki / "concepts" / "Foo-Bar.md"` (use `Path.write_text` directly,
  bypassing slugify). Call `kb_read_page("concepts/FOO-BAR")` (or similar
  case-mismatch). Assert response starts with `"Error: ambiguous page_id"`
  AND includes both stems in the list. On case-insensitive FS (Windows NTFS
  default), skip the duplicate-file seeding and skip via
  `@pytest.mark.skipif(sys.platform == "win32", reason="case-insensitive FS")`.
- **AC17 — Test `kb_stats` wiki_dir override + traversal rejection.** (See
  `tests/test_cycle10_validate_wiki_dir.py` AC18 — consolidated there.)

### File: `tests/test_cycle10_validate_wiki_dir.py` (new)

- **AC18 — `kb_stats` respects wiki_dir override.** Seed `tmp_project / "wiki"`
  with 2 pages. Call `kb_stats(wiki_dir=str(tmp_project / "wiki"))`, assert the
  result mentions exactly 2 pages (regex `Total pages:\*\* 2`).
- **AC19 — `kb_stats` rejects parent-traversal.** Call
  `kb_stats(wiki_dir="../../evil")`, assert the response starts with
  `"Error: Invalid wiki_dir"` AND contains no absolute path leak of the
  attempted target.
- **AC20 — `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift` each respect
  wiki_dir override + reject traversal.** Parametric test hitting all three
  tools. For each: (a) valid override returns non-error output, (b) traversal
  `"../../evil"` returns `"Error: Invalid wiki_dir"`.
- **AC21 — All four tools return consistent error-shape.** Parametric test
  asserts the rejection error from `kb_stats`, `kb_graph_viz`,
  `kb_verdict_trends`, `kb_detect_drift` all start with
  `"Error: Invalid wiki_dir — "` (same prefix cycle 9 established). This
  locks the error-string contract against future drift.

### File: `tests/test_cycle10_vector_min_sim.py` (new)

- **AC22 — `hybrid_search` filters low-cosine vec results.** Build
  `bm25_fn` returning `[]`, `vector_fn` returning
  `[{"id": "a", "score": 0.1}, {"id": "b", "score": 0.5}]`. Call
  `hybrid_search("q", bm25_fn, vector_fn)`. Assert result contains only
  `"b"` (score 0.5 ≥ 0.3), not `"a"` (score 0.1 < 0.3).
- **AC23 — `hybrid_search` returns `[]` when BM25 empty + all vec results
  below threshold.** Build `bm25_fn` returning `[]`, `vector_fn` returning
  `[{"id": "a", "score": 0.1}, {"id": "b", "score": 0.29}]`. Assert result
  is `[]`.

### File: `tests/test_cycle10_capture.py` (new)

- **AC24 — `_extract_items_via_llm` uses UUID boundary.** Monkeypatch
  `secrets.token_hex` to return `"0123456789abcdef0123456789abcdef"`
  deterministically. Monkeypatch `kb.capture.call_llm_json` to capture the
  prompt argument and return a minimal valid response. Call
  `_extract_items_via_llm("benign content")`. Assert the captured prompt
  contains `"<<<INPUT-0123456789abcdef0123456789abcdef>>>"` AND the prompt
  does NOT contain the legacy `"--- INPUT ---"` literal (the static fence
  is fully replaced by the UUID form).
- **AC25 — `captured_at` reflects submission time.** Monkeypatch
  `_extract_items_via_llm` to sleep 0.5 seconds before returning a valid
  response. Call `kb_capture("benign content")`. Assert the returned
  `CaptureResult.items[*]["captured_at"]` ISO-8601 timestamp is within
  100 ms of the pre-call wall-clock time — NOT 500+ ms later (which it
  would be under current post-LLM timestamp ordering).

### File: `tests/test_cycle10_extraction_validation.py` (new)

- **AC26 — `ingest_source` rejects non-string extraction fields up-front.**
  Call `ingest_source(raw_path, extraction={"title": "x", "core_argument":
  {"nested": "dict"}})` against a `tmp_project / "raw" / "articles" / x.md`
  source. Assert the call raises `IngestError` (or `ValueError`) with a
  message containing `"core_argument"` and `"must be string"`. Assert
  `os.listdir(tmp_wiki / "summaries")` is EMPTY after the exception (no
  half-written summary).
- **AC27 — `_coerce_str_field` round-trip for valid types.** Unit test
  parametric: valid string returns the string unchanged; missing key returns
  `""`; None value returns `""`; `int` 42 raises with `"must be string"` +
  `"int"`; dict `{"a": 1}` raises with `"dict"`; list `["a"]` raises with
  `"list"`; bytes `b"a"` raises with `"bytes"`.

### Housekeeping AC

- **AC28 — CHANGELOG, BACKLOG, CLAUDE.md updated to reflect cycle 10.** Step
  12 Codex doc pass updates CHANGELOG.md `[Unreleased]` with a "Backlog-by-file
  cycle 10" section listing AC1-AC27 resolutions. BACKLOG.md deletes the
  resolved items (wiki_dir migration scope-out, silent-degradation
  `_safe_call` at kb_refine_page, kb_search length cap [already done — just
  delete stale entry], kb_read_page ambiguity, VECTOR_MIN_SIMILARITY,
  detect_source_drift doc, capture UUID boundary, captured_at, extraction
  type validation). CLAUDE.md gains the `raw/captures/` exception paragraph
  (AC14) and the `detect_source_drift` side-effect note (AC9).

## Non-AC implementation details (for plan gate)

These must appear as distinct Step 7 plan task items but are not raised to AC
status:

1. `_safe_call` call in `kb_refine_page` uses `label="backlinks"` and the
   returned `err` is routed through `_sanitize_error_str` if present; the
   existing `_safe_call` helper already produces `f"{label}_error: {type}:
   {msg}"` which itself contains the exception text. If the exception string
   contains absolute paths, we scrub in `_safe_call`'s caller, NOT in
   `_safe_call` itself (keep the helper platform-agnostic).
2. `_coerce_str_field` raises `IngestError` if the symbol exists in
   `kb.ingest.errors` or `kb.errors`. If not, fallback to `ValueError`. Plan
   step 1 must `grep -n "class IngestError"` src/ to resolve this choice.
3. AC10 UUID boundary uses `secrets.token_hex(16)` (32-char hex). Keep the
   `_escape_prompt_fences` regex scrub as defense-in-depth; the UUID boundary
   is added, not replacing.
4. AC14 CLAUDE.md edit must land in the SAME commit as AC10 / AC11
   (capture.py) so reviewers see the `raw/captures/` semantic change
   atomically.
5. AC8 `hybrid_search` filter is applied AFTER per-variant try/except (so a
   vec backend exception still degrades gracefully) and BEFORE `all_lists`
   append. Existing behaviour where vec-empty results are skipped before
   append stays.
6. All new tests use `tmp_project` / `tmp_wiki` / `create_wiki_page` /
   `create_raw_source` fixtures. No new ad-hoc `_setup_*` helpers.
7. AC16 test uses `@pytest.mark.skipif(sys.platform == "win32", ...)` for the
   duplicate-file seed; on Windows NTFS, writing `foo.md` then `Foo.md`
   overwrites, so the ambiguity case is unreachable. Plan must document this
   skip condition.

## Dependencies / coordination

- AC3 / AC4 / AC5 / AC6 depend on `_validate_wiki_dir` being importable
  from `kb.mcp.app`. Verified via grep — exists at `app.py:187`.
- AC1 depends on `_safe_call` being importable from `kb.lint._safe_call`.
  Verified via grep — exists at `_safe_call.py:20`. Import added alongside
  the existing `from kb.mcp.app import ...` in `quality.py:21`.
- AC8 depends on `vector_fn` results having `score` key set to cosine
  similarity. Plan step 1 must grep `vector_fn`'s concrete implementation
  (`query.embeddings.VectorIndex.query`) to confirm. If the score field is a
  distance rather than similarity, AC8 threshold comparison direction must
  flip, and AC22/AC23 expected values update.
- AC13 changes `_build_summary_content` — plan step must scan every call
  site of `_build_summary_content` to ensure no caller passes an extraction
  dict that would now hit the new validation failure mode. (Expected: all
  callers are the extract-and-render path, and a malformed extraction is
  already a data-quality bug; the new exception surfaces it earlier.)
- AC14 (CLAUDE.md) + AC10/AC11 (capture.py) land in same commit.
- AC28 (doc update) is Step 12's responsibility; plan doesn't allocate it to
  Step 9.
