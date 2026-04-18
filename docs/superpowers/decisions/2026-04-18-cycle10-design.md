# Cycle 10 Design Decision — Step 5 Gate

**Date:** 2026-04-18
**Branch:** `feat/backlog-by-file-cycle10`
**Gate:** Step 5 design decision (input to Step 7 plan + Step 8 plan gate).
**Inputs:** requirements (28 ACs), threat-model (stale on 15 threats), R1 (Opus, 6 findings), R2 (Codex, 5 blockers + 10 majors).

## Analysis

Both reviewers approved-with-revisions; the delta between R1 and R2 is almost entirely *factual correctness of AC wording* vs *scope-shaping*. R1 focuses on scope symmetry (same-class completeness on AC1 and AC13) and documentation hygiene; R2 focuses on four concrete correctness blockers: (1) `_validate_wiki_dir` does not enforce PROJECT_ROOT containment so AC3-AC6 actually loosen security unless the helper is hardened first; (2) `hybrid_search` is a dead code path for production — `engine.py:search_pages` calls `rrf_fusion` directly at lines 131-153 and never routes through `query/hybrid.py`, so AC8's filter-at-`hybrid_search` is a no-op for `kb_search` / `kb_query`; (3) `_safe_call` returns raw `{exc}` so AC1 leaks paths unless the caller sanitises; (4) `_check_and_reserve_manifest` runs BEFORE `_build_summary_content`, so a mid-summary `_coerce_str_field` raise leaves a stale manifest reservation that turns future retries into false-positive duplicates. All four blockers are real and grep-verified by the orchestrator. The single most important decision this cycle is Q2 (vector filter location) — getting that wrong makes every AC22/AC23 test green while `kb_search` continues returning noise. The orchestrator's fact #3 is decisive: route the filter where production reads, and rewrite the tests against that path.

The governing principles pull in a consistent direction. `feedback_inspect_source_tests` plus cycle 9 R2 past experience say: do not ship a test that asserts against a code path production does not exercise. That alone settles Q2 in favour of Option C — filter at `engine.py:search_pages` (production path) AND rewrite AC22/AC23 to target `search_pages`. Duplicating the 1-line filter into `hybrid.py` (Option A) is cheap but introduces drift risk with no benefit since `hybrid.py` is unused in production; Option B keeps the signature-only test and is exactly the anti-pattern. The cycle-8 Red Flag (grep-verify before trusting AC text) and the cycle-9 Red Flag (same-class completeness) both argue for (a) hardening `_validate_wiki_dir` in-cycle so all 4 migrations are actually security-positive (Q1 → Option A), (b) pulling AC1's sibling silent-continue at `kb_affected_pages:288-301` in as AC1b (Q4 → Option A) because it is the exact same class as AC1, one file, one helper, one commit; (c) keeping the `compile/linker.py:219-220` pipe-substitution fix (Q5) as an explicit AC28.5 because it's one line, same-file-as-AC9, and deferring means a data-loss bug sits open for a cycle with no owner. For the manifest-ordering hazard (Q6), pre-validation at the top of `ingest_source` is both simpler (no rollback logic) AND stricter (fails earlier, before any state mutation) than Option A's post-reservation cleanup dance — Option B wins on both axes. The other opens are smaller-blast-radius: sanitise in `_safe_call` itself (Q3 → Option B) because all three existing callers benefit for free and AC1's caller wiring becomes trivial; FS-capability probe (Q8 → Option A) because macOS APFS default is case-insensitive and `sys.platform == "win32"` misses it; monotonic clock for `captured_at` ordering (Q7 → Option C) because the format is seconds-granular making any wall-clock tolerance below 1s meaningless; split commit 3 into 3a/3b (Q9 → Option A) to honour `feedback_batch_by_file`; and bundle AC14 into the capture commit (Q10 → Option A) because the doc sentence is the semantic commentary on the code change and separating them creates a coordination hazard at Step 12.

## VERDICT

APPROVE-WITH-REVISIONS.

The four R2 blockers must be resolved in the final AC set; the R1 same-class-completeness gaps must be explicitly enumerated (added or deferred with rationale). After the decisions below, the resulting AC set is 33 ACs across 14 files (was 28 ACs / 13 files). Step 7 plan proceeds from this document.

## DECISIONS

- **Q1 — DECIDE A.** Harden `_validate_wiki_dir` with PROJECT_ROOT containment in cycle 10 as new AC0 (~5 LoC in `mcp/app.py`). RATIONALE: Option B duplicates the containment check at 4 call sites violating DRY and re-opens the cycle-9 scope-out as a new cycle-10 scope-out. CONFIDENCE: HIGH.

- **Q2 — DECIDE C.** Filter at `engine.py:search_pages` (production path) ONLY; rewrite AC22/AC23 to target `search_pages` via an empty-result assertion with a fake `vector_search` thunk. RATIONALE: R2 blocker #2 — `hybrid.py` is a dead path for `kb_search`/`kb_query`; duplicating the filter is drift-prone; `hybrid.py` stays unchanged so the 1-line filter is a single-source fix. CONFIDENCE: HIGH.

- **Q3 — DECIDE B.** Modify `_safe_call` itself (`src/kb/lint/_safe_call.py:44-46`) to route `exc` through `_sanitize_error_str` before interpolating into the error string. RATIONALE: all three existing callers (`lint/runner.py:137`, `mcp/health.py:72`, new `mcp/quality.py`) get sanitisation for free — net-positive security; signature stays unchanged (still returns `(result, err_string)`), so cycle-4 signature-preservation Red Flag is honoured. CONFIDENCE: HIGH.

- **Q4 — DECIDE A.** Include `kb_affected_pages:288-301` shared-sources silent-continue as AC1b. RATIONALE: cycle-9 Red Flag "same-class completeness" — exact pattern, same helper, one commit (quality.py already touched by AC1); deferring would require rediscovery in cycle 11. CONFIDENCE: HIGH.

- **Q5 — DECIDE A.** Include `compile/linker.py:219-220` pipe→em-dash silent substitution as AC28.5. RATIONALE: one-line fix, same file cluster as AC9 (compile/compiler.py docstring), data-loss-class bug; R1 explicitly called out as bonus fix. CONFIDENCE: HIGH.

- **Q6 — DECIDE B.** Pre-validation pass at top of `ingest_source` (before any reservation) AND defensive `_coerce_str_field` at `_build_summary_content` sites. RATIONALE: R2 blocker #4 — no rollback logic needed, fails fast before any state mutation; double-check is trivial (coerce on a string returns the string, on None returns ""). CONFIDENCE: HIGH.

- **Q7 — DECIDE C.** Monotonic clock before/after to establish ordering, not equality. RATIONALE: R2 major #2 — `captured_at` format is `"%Y-%m-%dT%H:%M:%SZ"` (seconds-granular), making any wall-clock tolerance below 1s meaningless; `time.monotonic()` before/after the `kb_capture` call, assert `captured_at` ISO string parses to a timestamp between the two monotonic samples. CONFIDENCE: HIGH.

- **Q8 — DECIDE A.** FS-capability probe at test setup (write `Foo.md` then `foo.md`; check whether the second is distinct). RATIONALE: R2 major #5 — macOS APFS default is case-insensitive, Windows NTFS can be configured case-sensitive per dir; a platform string is wrong on both OSes. CONFIDENCE: HIGH.

- **Q9 — DECIDE A.** Split into commit 3a (`browse.py` kb_stats + related tests) + commit 3b (`health.py` 3 tools + related tests). RATIONALE: `feedback_batch_by_file` says one file per commit when safe; these are independent file edits, no cross-file dependency. CONFIDENCE: MED.

- **Q10 — DECIDE A.** CLAUDE.md AC14 edit lands in the SAME commit as AC10/AC11 (capture.py). RATIONALE: AC14's doc text is the semantic commentary on the capture.py behaviour; splitting creates a coordination hazard at Step 12 where CLAUDE.md could drift from unfinished capture changes. The `raw/captures/` exception is a code+doc atom. CONFIDENCE: HIGH.

## CONDITIONS

Pre-Step-7 conditions for the verdict to stand:

1. Step 7 plan's task #1 must grep `_validate_wiki_dir` current behaviour at `mcp/app.py:187-200`, confirm the lack of PROJECT_ROOT containment check, and write AC0's hardening as a prerequisite before AC3-AC6 migrations.
2. Step 7 plan must explicitly enumerate AC0 as the FIRST commit (before AC3/AC4/AC5/AC6 migration commits) so the 4 migration commits are truly security-positive.
3. Step 7 plan must grep-verify `kb_affected_pages:288-301` silent-continue site pre-implementation (same file as AC1, but different function).
4. Step 7 plan task for AC8 must include a grep-verify of `src/kb/query/engine.py:131-153` confirming the vector path is `local vector_search → rrf_fusion` (not `hybrid_search`) BEFORE writing the filter line at `engine.py:search_pages`.
5. Step 7 plan must route the AC1 caller change through the upgraded `_safe_call` (Q3 Option B) — no local `_sanitize_error_str` wrapping at the `quality.py` site needed.
6. Step 7 plan must include an explicit rollback-unnecessary note for Q6 (because Option B puts validation before reservation) — plan reviewer must not add rollback logic "just in case".
7. Step 7 plan's AC22/AC23 test file must target `search_pages` not `hybrid_search`; plan must explicitly call this out in the test-task description so a future reviewer does not regress AC22/AC23 back to hitting `hybrid.py`.
8. Step 12 doc pass (CHANGELOG / BACKLOG / CLAUDE.md) must delete the STALE BACKLOG items (torn-last-line, kb_search stale, kb_search length cap) and log them in CHANGELOG as STALE-at-cycle-10 review.

## FINAL DECIDED DESIGN

Canonical cycle 10 AC set: **33 ACs across 14 files**. Numbering uses AC0 (new PROJECT_ROOT hardening), AC1b (kb_affected_pages sibling), AC28.5 (linker pipe-substitution). AC14 stays bundled with AC10/AC11.

### File: `src/kb/mcp/app.py`

**AC0 — `_validate_wiki_dir` enforces PROJECT_ROOT containment.** Current implementation (`app.py:187-200`) validates `is_absolute() AND exists() AND is_dir()` but does NOT check containment. Add a containment check: after `resolve()`, verify `resolved_path` is `==` PROJECT_ROOT or a descendant via `resolved_path.is_relative_to(PROJECT_ROOT.resolve())`. On failure, return `(None, f"wiki_dir must be inside project root — got {_sanitize_error_str(str(wiki_dir))}")`. Error-string prefix standardised to `"Error: wiki_dir "` (drop em-dash inconsistency). Callers already in place (`mcp/core.py:624`, `mcp/health.py:56,116`) are re-grepped to confirm they pattern-match `if err: return f"Error: {err}"`.
- Test strategy: unit test in `tests/test_cycle10_validate_wiki_dir.py` — (a) `/tmp/outside_project` resolves outside PROJECT_ROOT and returns `(None, err)` where `err` starts with `"wiki_dir must be inside project root"`; (b) `tmp_project / "wiki"` returns `(path, None)`; (c) symlink-inside-pointing-outside case resolves to target and is rejected (documents `.resolve()` semantics per R1 recommendation).

### File: `src/kb/lint/_safe_call.py`

**AC1s — `_safe_call` sanitises the embedded exception string.** At lines 44-46 the helper formats `f"{label}_error: {type(exc).__name__}: {exc}"` — replace the `{exc}` with `_sanitize_error_str(str(exc))` via import from `kb.mcp.app`. All 3 existing callers (`lint/runner.py:137`, `mcp/health.py:72`, new `quality.py`) benefit transparently; signature unchanged `(fn, *, fallback, label, log=None) -> tuple[T|None, str|None]`.
- Test strategy: new test in `tests/test_cycle10_safe_call.py` — monkeypatch a callable to raise `OSError("disk full at /home/user/secret.txt")`; assert returned err string contains `"disk full"` but does NOT contain the absolute path literal (relies on `_sanitize_error_str`'s path redaction).

### File: `src/kb/mcp/quality.py`

**AC1 — `kb_refine_page` backlinks lookup uses `_safe_call`.** Replace the `try / except Exception: affected = []` block at ~102-110 with `backlinks_map, err = _safe_call(lambda: build_backlinks(), fallback={}, label="backlinks")`. On non-None `err`, append `f"\n[warn] {err}"` to the response. Existing success path unchanged.

**AC1b — `kb_affected_pages` shared-sources lookup uses `_safe_call`.** Same pattern applied at `quality.py:288-301` — replace silent-continue with `shared, err = _safe_call(lambda: load_shared_sources(page_id), fallback=[], label="shared_sources")`; on err, append `[warn] shared_sources_error: ...` to the response. Same class as AC1 (observability-class silent-degradation).
- Test strategy (shared for AC1 + AC1b): `tests/test_cycle10_quality.py` — (a) monkeypatch `kb.compile.linker.build_backlinks` to raise `OSError("corrupt manifest")`; call `kb_refine_page(...)`; assert response contains `"[warn] backlinks_error:"` and `"corrupt manifest"` AND response starts with `"Refined: ..."`. (b) monkeypatch `load_shared_sources` to raise; call `kb_affected_pages(page_id)`; assert `[warn] shared_sources_error:` in response.

### File: `src/kb/mcp/browse.py`

**AC2 — `kb_read_page` ambiguity error on >1 case-insensitive match.** Collect ALL case-insensitive matches instead of picking first; if `len(matches) > 1`, return `Error: ambiguous page_id — multiple files match {page_id}: {comma-separated sorted stems}`. Single case-insensitive match preserves current behaviour.

**AC3 — `kb_stats` uses `_validate_wiki_dir`.** Replace manual `Path(wiki_dir).resolve() + wiki_path.relative_to(PROJECT_ROOT.resolve())` block at `browse.py:325-328` with `wiki_path, err = _validate_wiki_dir(wiki_dir)`; `if err: return f"Error: {err}"`. (Double `Error: Error:` avoided because AC0 drops the `"Error: "` prefix from the helper's return — the helper returns the message portion only, caller adds the `Error: ` prefix.)
- Test strategy: see AC16-AC20 (consolidated in `tests/test_cycle10_validate_wiki_dir.py`).

### File: `src/kb/mcp/health.py`

**AC4 — `kb_graph_viz` uses `_validate_wiki_dir`.** Replace `Path(wiki_dir) if wiki_dir else None` at `health.py:177` with the helper + err check. Tightens security (current code has no containment check).

**AC5 — `kb_verdict_trends` uses `_validate_wiki_dir`.** Replace manual `.resolve() + relative_to(PROJECT_ROOT)` block at `health.py:194-198` with the helper. Preserves `verdicts_path = wiki_path.parent / ".data" / "verdicts.json"` derivation.

**AC6 — `kb_detect_drift` uses `_validate_wiki_dir`.** Replace `Path(wiki_dir) if wiki_dir else None` at `health.py:223` with the helper.
- Test strategy for AC4/AC5/AC6: see AC18-AC20.

### File: `src/kb/config.py`

**AC7 — `VECTOR_MIN_SIMILARITY = 0.3` constant added.** New config constant `VECTOR_MIN_SIMILARITY = 0.3`. Module-level comment documents the semantics: "Minimum cosine similarity (post-`1/(1+distance)` conversion in `engine.vector_search`) a vector hit must reach before contributing to RRF fusion. Below this, the vector backend is treated as silent for that query."
- Test strategy: constant-import test in `tests/test_cycle10_vector_min_sim.py`; unit assertion `VECTOR_MIN_SIMILARITY == 0.3`.

### File: `src/kb/query/engine.py`

**AC8 — `search_pages`'s `vector_search` filters results below `VECTOR_MIN_SIMILARITY`.** Between the distance→score conversion at `engine.py:143` (`1.0 / (1.0 + dist)`) and the downstream `rrf_fusion` call, filter: `results = [r for r in results if r.get("score", 0.0) >= VECTOR_MIN_SIMILARITY]`. If vector returns zero filtered hits AND bm25 returns zero, `search_pages` returns `[]`. Emit `logger.debug("vec below min-sim: %d dropped, %d kept", dropped, kept)` so operators can tune. Applied at PRODUCTION path, not `hybrid.py`.
- Test strategy (AC22/AC23): see dedicated file below.

### File: `src/kb/compile/compiler.py`

**AC9 — `detect_source_drift` docstring documents deletion-pruning persistence.** Add docstring paragraph explaining that `save_hashes=False` still persists deletion-pruning because lingering deleted-source manifest entries corrupt subsequent `find_changed_sources` calls. Matching one-line note in CLAUDE.md "Error Handling Conventions" section.
- Test strategy: doc-assertion test — import `detect_source_drift.__doc__`; assert it contains `"deletion-pruning"` and `"save_hashes=False"`. This is explicitly a docstring test (R2 flagged AC9 as doc-only, which is acceptable).

### File: `src/kb/compile/linker.py`

**AC28.5 — `inject_wikilinks` rejects pipe in titles instead of silent em-dash substitution.** At `linker.py:219-220`, replace the silent `title.replace("|", "\u2014")` with an explicit escape via Obsidian's bracket-escape convention: `title.replace("|", r"\|")` (the wikilink syntax accepts backslash-escaped pipes). Fallback: if escape is not supported in the caller's renderer, log `logger.warning("pipe in page title %r — escaping to backslash-pipe", title)` once per title. Preserves existing tests that check wikilink output doesn't crash on pipe-containing titles.
- Test strategy: unit test — inject a wikilink for a page with title `"A|B"`; assert output contains `"A\\|B"` (escaped) or similar renderer-safe form; assert `"A—B"` (em-dash) is NOT in output.

### File: `src/kb/capture.py`

**AC10 — `_extract_items_via_llm` uses UUID-boundary delimiters.** Compute `boundary = _secrets.token_hex(16)` (use existing `_secrets` alias per R2 major #3). Prompt template references `f"<<<INPUT-{boundary}>>>"` / `f"<<<END-INPUT-{boundary}>>>"`. Before rendering, verify neither fence appears in input; regenerate up to 3 times; on exhaustion raise `ValueError("boundary collision after 3 retries — input may be adversarial")` (no new `CaptureError` class — orchestrator fact #5 says use ValueError since IngestError doesn't exist, and symmetry dictates CaptureError shouldn't either unless added). Existing `_escape_prompt_fences` + `_FENCE_*_RE` machinery STAYS as defense-in-depth.

**AC11 — `captured_at` reflects submission time.** Move the `captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")` line from `capture.py:726` to immediately after `_resolve_provenance(...)` at line 669 (pre-LLM). The 4 early-return paths between 669-726 already construct `CaptureResult` without `captured_at` — no change to those. `CaptureResult` docstring updated to "submission time (UTC ISO-8601)".
- Test strategy (AC24/AC25): see capture test file.

### File: `src/kb/ingest/pipeline.py`

**AC12 — `_coerce_str_field(extraction, field)` helper added.** New private helper raising `ValueError` (not `IngestError` — does not exist per orchestrator fact #5). Returns `""` for missing/None keys; returns the string unchanged for str; raises `ValueError(f"extraction field {field!r} must be string, got {type(value).__name__}")` for everything else.

**AC13 — Pre-validation pass at top of `ingest_source`.** Before `_check_and_reserve_manifest` is called, run `_coerce_str_field(extraction, f)` for every known string field (`title`, `author`, `core_argument`, and any other `_build_summary_content` consumer). If any raises, `ingest_source` propagates the `ValueError` BEFORE any state mutation — no manifest reservation exists to clean up. `_build_summary_content` ALSO calls `_coerce_str_field` defensively at its read sites (idempotent double-check per Q6 Option B), so a mutation between the pre-check and the summary render is still safe. Scope intentionally limited to `_build_summary_content` + pre-validation pass; remaining 10+ read sites (pipeline.py:157, 162-163, 180, 186-188, 413-415, 395) are tracked in BACKLOG as cycle-11 follow-up.
- Test strategy: see AC26/AC27.

### File: `CLAUDE.md`

**AC14 — `raw/captures/` exception carved out + `detect_source_drift` note.** Two edits, same commit as AC10/AC11:
1. In "Three-Layer Content Structure" section's `raw/` description, add parenthetical: `(except raw/captures/, which is the sole LLM-written output directory inside raw/ — atomised via kb_capture, then treated as raw input for subsequent ingest)`.
2. In "Error Handling Conventions" section, add one-liner: "`compile.compiler.detect_source_drift` persists deletion-pruning to the manifest even though `save_hashes=False` is passed — this is the sole exception to the read-only contract; see function docstring."
- Test strategy: docs-grep assertion (covered in AC28 housekeeping).

### File: `tests/test_cycle10_validate_wiki_dir.py` (new)

**AC15 — `_validate_wiki_dir` rejects paths outside PROJECT_ROOT.** Unit test for AC0 hardening — (a) `str(Path("/tmp/outside"))` returns `(None, err)` where `err` starts with `"wiki_dir must be inside project root"`; (b) relative path `"../../evil"` is rejected; (c) valid `str(tmp_project / "wiki")` returns `(path, None)`.

**AC16 — `kb_stats` respects wiki_dir override + rejects traversal.** Seed `tmp_project / "wiki"` with 2 pages. (a) `kb_stats(wiki_dir=str(tmp_project / "wiki"))` → result mentions exactly 2 pages. (b) `kb_stats(wiki_dir="../../evil")` → response starts with `"Error: wiki_dir "` (new standardised prefix) AND contains no absolute path leak of the attempted target.

**AC17 — `kb_graph_viz` respects wiki_dir override + rejects traversal.** Parametric — valid override returns non-error output; traversal returns `"Error: wiki_dir "`.

**AC18 — `kb_verdict_trends` respects wiki_dir override + rejects traversal.** Same pattern; also verify `verdicts_path` derivation: seed `tmp_project / ".data" / "verdicts.json"` with 1 verdict; call with `wiki_dir=str(tmp_project / "wiki")`; assert result reflects 1 verdict.

**AC19 — `kb_detect_drift` respects wiki_dir override + rejects traversal.** Same pattern.

**AC20 — All four tools return consistent error-shape.** Parametric — assert rejection error from `kb_stats`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift` all start with `"Error: wiki_dir "` (AC0 standardised prefix). Locks error-string contract.

### File: `tests/test_cycle10_browse.py` (new)

**AC21 — `kb_read_page` ambiguity on >1 case-insensitive match.** FS-capability probe first: write `tmp_wiki / "concepts" / "probe.md"` then `tmp_wiki / "concepts" / "PROBE.md"`; if both files are distinct on the test FS, proceed with the ambiguity test; otherwise skip with `pytest.skip("case-insensitive FS detected via capability probe")`. Write `foo-bar.md` and `Foo-Bar.md`; call `kb_read_page("concepts/FOO-BAR")`; assert response starts with `"Error: ambiguous page_id"` AND includes both stems in the listed comma-separated matches.

### File: `tests/test_cycle10_quality.py` (new — see AC1/AC1b test strategy above)

Tests for AC1 (backlinks silent-degradation via `_safe_call`) and AC1b (shared-sources silent-degradation via `_safe_call`). Monkeypatch-based; asserts `[warn] <label>_error:` appears in response.

### File: `tests/test_cycle10_safe_call.py` (new — see AC1s test strategy above)

Unit test for the sanitised `_safe_call` helper.

### File: `tests/test_cycle10_vector_min_sim.py` (new)

**AC22 — `search_pages` filters vector results below `VECTOR_MIN_SIMILARITY`.** Target `search_pages` NOT `hybrid_search` per Q2 decision. Monkeypatch `bm25_search` to return `[]` and the local `vector_search` inside `engine.py` (or patch `VectorIndex.query` to return known `(pid, distance)` pairs that convert via `1/(1+dist)` to scores `0.1` and `0.5`). Call `search_pages("noise query", max_results=10)`; assert result contains only the `score=0.5` hit.

**AC23 — `search_pages` returns `[]` when BM25 empty + all vec results below threshold.** Same setup as AC22 but all vec scores below 0.3 (e.g. 0.1, 0.29). Assert `search_pages(...)` returns `[]`.

### File: `tests/test_cycle10_capture.py` (new)

**AC24 — `_extract_items_via_llm` uses UUID boundary.** Monkeypatch `kb.capture._secrets.token_hex` to return `"0123456789abcdef0123456789abcdef"` (use the `_secrets` alias per R2 major #3). Monkeypatch `kb.capture.call_llm_json` to capture the prompt argument. Call `_extract_items_via_llm("benign content")`. Assert prompt contains `"<<<INPUT-0123456789abcdef0123456789abcdef>>>"` AND does NOT contain the legacy `"--- INPUT ---"` literal as a TEMPLATE fence (escaped user content is allowed to contain it per R2 major #4 — assert against the template-rendered fence, not against every occurrence).

**AC24b — Collision retry exhaustion raises.** Monkeypatch `_secrets.token_hex` to return a constant value that appears in the input; call with input containing that constant. Assert `ValueError` is raised with message containing `"boundary collision after 3 retries"`.

**AC25 — `captured_at` reflects submission time.** Use monotonic clock for ordering (per Q7 Option C). Sample `t_before = time.monotonic()`, monkeypatch `_extract_items_via_llm` to sleep 2 seconds before returning a valid response, call `kb_capture("benign content")`, sample `t_after = time.monotonic()`. Parse `captured_at` ISO-8601 string to a datetime and convert to UTC epoch seconds. Because `captured_at` is seconds-granular and the LLM sleeps 2s: assert `captured_at` is at MOST 1 second later than the pre-call wall-clock time AND at least 1 second earlier than the post-call wall-clock time (i.e. demonstrably pre-LLM). Use `datetime.now(UTC)` samples bracketing the call as the wall-clock endpoints.

### File: `tests/test_cycle10_extraction_validation.py` (new)

**AC26 — `ingest_source` rejects non-string extraction fields up-front (pre-reservation).** Call `ingest_source(raw_path, extraction={"title": "x", "core_argument": {"nested": "dict"}})` against a `tmp_project / "raw" / "articles" / x.md` source. Assert `ValueError` raised with message containing `"core_argument"` and `"must be string"`. Assert BOTH `os.listdir(tmp_wiki / "summaries")` AND `os.listdir(tmp_wiki / "entities")` AND `os.listdir(tmp_wiki / "concepts")` are EMPTY (extends R1's AC26 recommendation). Assert the source hash manifest at `tmp_project / ".data" / "ingest_manifest.json"` does NOT contain the raw_path's hash (confirms pre-validation beats pre-reservation ordering).

**AC27 — `_coerce_str_field` round-trip for valid types.** Unit parametric — valid str returns unchanged; missing key returns `""`; None returns `""`; int 42 raises with `"must be string"` + `"int"`; dict raises with `"dict"`; list raises with `"list"`; bytes raises with `"bytes"`.

### File: `tests/test_cycle10_linker.py` (new — AC28.5)

**AC28a — `inject_wikilinks` does not silently substitute pipe to em-dash.** Create a page with title `"A|B"`; call `inject_wikilinks` with that title; assert output does NOT contain `"A—B"` (em-dash) AND DOES contain either the backslash-escaped form `"A\\|B"` or another renderer-safe form.

### Housekeeping AC

**AC28 — CHANGELOG, BACKLOG, CLAUDE.md updated to reflect cycle 10.** Step 12 Codex doc pass:
- **CHANGELOG.md `[Unreleased]`**: add "Backlog-by-file cycle 10" section listing AC0-AC27 + AC28.5 resolutions with file/line refs.
- **BACKLOG.md deletes**: wiki_dir migration scope-out (cycle-9 residual), silent-degradation `_safe_call` at kb_refine_page, silent-degradation at kb_affected_pages, kb_read_page ambiguity, VECTOR_MIN_SIMILARITY, `detect_source_drift` doc, capture UUID boundary, captured_at, extraction type validation, compile/linker.py pipe→em-dash.
- **BACKLOG.md STALE deletes (logged in CHANGELOG as STALE-at-cycle-10)**: torn-last-line under concurrent append (already fixed), kb_search stale flag NOT surfaced (already done), kb_search length cap (already done).
- **BACKLOG.md new deferral line**: `_coerce_str_field` remaining 10+ read sites at `pipeline.py:157, 162-163, 180, 186-188, 395, 413-415` — pinned as cycle-11 followup.
- **CLAUDE.md**: `raw/captures/` parenthetical (AC14 edit #1) + `detect_source_drift` note (AC14 edit #2). No other changes.

### Scope-outs (explicit enumeration per cycle-9 Red Flag)

Each scope-out is listed with same-class completeness check:

1. **`_coerce_str_field` remaining 10+ extraction-field read sites** at `pipeline.py:157, 162-163, 180, 186-188, 395, 413-415`. Class: correctness-class pre-write validation. Scope-out reason: R1/R2 both accept the `_build_summary_content`-only scope; AC13 pre-validation pass at top of `ingest_source` covers MOST of the concrete fields any site reads (title, author, core_argument) so the cycle-11 follow-up is defensive double-check at the non-summary sites, not an open security hole. BACKLOG pin required.
2. **`multiprocessing`-based integration tests** — class: test-coverage. Scope-out reason: Phase 4.5 HIGH multi-cycle deferral, not addressed in cycle 10. BACKLOG entry exists.
3. **`compile/compiler.py` naming inversion refactor** — class: structural. Scope-out: multi-cycle refactor, only the docstring (AC9) and in-source note land this cycle.
4. **`ingest/pipeline.py` 11-stage locking refactor** — class: structural. Same reason as #3.
5. **`kb_merge`, `belief_state`, `status` frontmatter** — class: Phase 5 feature. Out of scope per non-goals.
6. **`review/refiner.py` write-then-audit ordering** — class: data-integrity. Explicitly R1's BACKLOG pickup suggestion for cycle 11. Not cycle 10 scope. BACKLOG entry exists.
7. **CLI smoke test for every command (`kb --version` short-circuit in cycle 8 was fragile)** — class: test-coverage. Multi-cycle deferral. BACKLOG entry exists.

### Commit shape (input to Step 7 plan)

Step 7 plan should produce roughly the following commit plan (file-grouped per `feedback_batch_by_file`):

1. **commit 1**: `src/kb/mcp/app.py` (AC0) + `tests/test_cycle10_validate_wiki_dir.py` (AC15 portion).
2. **commit 2**: `src/kb/lint/_safe_call.py` (AC1s) + `tests/test_cycle10_safe_call.py`.
3. **commit 3**: `src/kb/mcp/quality.py` (AC1 + AC1b) + `tests/test_cycle10_quality.py`.
4. **commit 4a**: `src/kb/mcp/browse.py` (AC2 + AC3) + `tests/test_cycle10_browse.py` + `tests/test_cycle10_validate_wiki_dir.py` AC16 row.
5. **commit 4b**: `src/kb/mcp/health.py` (AC4 + AC5 + AC6) + `tests/test_cycle10_validate_wiki_dir.py` AC17-AC20 rows.
6. **commit 5**: `src/kb/config.py` (AC7) + `src/kb/query/engine.py` (AC8) + `tests/test_cycle10_vector_min_sim.py` (AC22 + AC23).
7. **commit 6**: `src/kb/compile/compiler.py` (AC9 docstring) + `src/kb/compile/linker.py` (AC28.5) + `tests/test_cycle10_linker.py` (AC28a).
8. **commit 7**: `src/kb/capture.py` (AC10 + AC11) + `CLAUDE.md` (AC14 both edits) + `tests/test_cycle10_capture.py` (AC24 + AC24b + AC25).
9. **commit 8**: `src/kb/ingest/pipeline.py` (AC12 + AC13) + `tests/test_cycle10_extraction_validation.py` (AC26 + AC27).
10. **commit 9**: `CHANGELOG.md` + `BACKLOG.md` (AC28 doc pass). Lands post-Step-11.5 CVE patch per `feedback_cve_patch_before_docs`.

Commit 4a + 4b split honours Q9 Option A. Commit 7 bundles AC14 with AC10/AC11 per Q10 Option A.
