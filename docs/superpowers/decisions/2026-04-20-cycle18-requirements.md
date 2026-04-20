# Cycle 18 — Requirements + Acceptance Criteria

**Date:** 2026-04-20
**Cycle theme:** close cycle-17 deferrals clustered by file — concurrency hardening (rotate-in-lock, per-page inject lock), observability (request_id + `.data/ingest_log.jsonl`), test-fixture completeness (`HASH_MANIFEST` redirection), and first end-to-end smoke.
**Scope guardrail:** batch-by-file convention (user memory `feedback_batch_by_file`). Target 16–18 ACs across 5 source/test files.

## Problem

Cycle 17 closed 16 ACs but deferred 5 items (AC15, AC19–AC21, `tmp_kb_env HASH_MANIFEST`) plus 1 follow-up (MCP monkeypatch owner-module migration) to cycle 18. Of these:

- **Concurrency gaps ship real race conditions today** — `wiki_log._rotate_log_if_oversized` runs OUTSIDE `file_lock(log_path)` (explicit comment at `wiki_log.py:107-108` acknowledges the omission), so on POSIX a concurrent appender holding a handle to a file that another process rotates will write to the archived file silently. `compile/linker.inject_wikilinks` has no per-page `file_lock`, so two concurrent `ingest_source` calls injecting wikilinks into the same target page clobber each other (last writer wins, losing one of the two new wikilinks).
- **Observability is non-existent for `ingest_source`** — 11-stage pipeline emits to `wiki/log.md` (intent), Python logger (warnings), and `wiki/contradictions.md` with no correlation ID tying them together. A flaky ingest cannot be debugged without manual timestamp correlation. Phase 4.5 MEDIUM R2 flagged this as a BACKLOG item; cycle 17 AC19 was deferred.
- **`tmp_kb_env` fixture leaks `HASH_MANIFEST`** — cycle 17 AC17 tests surfaced that the manifest path lives at `kb.compile.compiler.HASH_MANIFEST = PROJECT_ROOT / ".data" / "hashes.json"` and `_TMP_KB_ENV_PATCHED_NAMES` does NOT include it, so `kb_compile_scan`-style tests under `tmp_kb_env` fall through to the real production manifest. Cycle 17 worked around by loosening assertions; the fixture itself was filed to BACKLOG.
- **No end-to-end workflow test exists** — cycle 17 AC15 was deferred. Phase 4.5 R3 flagged that all 8 prior cross-module integration bugs ("page write vs evidence append", "manifest race", "index write order", "ingest fan-out") describe failures BETWEEN steps and cannot be caught by per-unit tests.
- **Repeated ad-hoc rotate patterns** — cycle 4 item #20 landed `_rotate_log_if_oversized` for `wiki/log.md`; cycle 18's ingest JSONL needs the same behaviour. Without extracting a shared helper, the next cycle duplicates the rotation logic.

## Non-goals

- **MCP monkeypatch owner-module migration** — DEFERRED to cycle 19. ~16 test files touch `kb.mcp.core.<symbol>`; migrating them is a standalone cycle per cycle-17 L1 (heuristic: "if count > 5, bump the AC to narrow scope").
- **`compile/linker.inject_wikilinks_batch`** (cycle 17 AC21) — deferred to cycle 19. Batch form changes the `ingest_source` inner loop shape; ships cleanly once the scalar per-page lock contract in cycle 18 AC7 is proven.
- **`compile/compiler.detect_source_drift`** manifest-write safety (Phase 4.5 HIGH R4) — cycle 17 Step 11 documented it as safe because read-only; remains out of scope here.
- **`kb rebuild-indexes`** CLI (Phase 4.5 HIGH R2 `compile_wiki(incremental=False)` surface) — architectural change deferred.
- **`ingest/pipeline.py` two-phase compile** (Phase 5 two-step CoT ingest) — deferred to Phase 5 roadmap.
- **`refine_page` two-phase write ordering** (Phase 4.5 HIGH deferred) — separate cycle.

## Acceptance criteria

Grouped by file. Each AC is a single testable pass/fail contract.

### File 1 — `tests/conftest.py`

- **AC1**: `_TMP_KB_ENV_PATCHED_NAMES` includes `"HASH_MANIFEST"`. Tuple ordering preserved for reviewability (append after `REVIEW_HISTORY_PATH` row, before wiki/raw subdir names).
- **AC2**: `tmp_kb_env` patches `kb.compile.compiler.HASH_MANIFEST` to `tmp_path / ".data" / "hashes.json"`. The patch uses `monkeypatch.setattr` symmetric with the existing `WIKI_LOG`/`WIKI_CONTRADICTIONS` entries. Mirror-loop at `conftest.py:224-231` also rebinds already-imported `from kb.compile.compiler import HASH_MANIFEST` references on `kb.*` modules so in-process callers (`kb.ingest.pipeline.ingest_source`, `kb.mcp.core.kb_compile_scan`) see the tmp path.
- **AC3**: Regression test `tests/test_cycle18_conftest.py::test_hash_manifest_redirected` asserts that under `tmp_kb_env`, `from kb.compile.compiler import HASH_MANIFEST; HASH_MANIFEST == tmp_project / ".data" / "hashes.json"` AND `kb_compile_scan`-style code path writes there, not to production `<PROJECT_ROOT>/.data/hashes.json`.

### File 2 — `src/kb/utils/wiki_log.py`

- **AC4**: Move the `_rotate_log_if_oversized(log_path)` call from `append_wiki_log` (currently line 109, outside the lock) to INSIDE the `with file_lock(log_path):` block in the inner `_write` function (line 126). Comment at line 107-108 ("Runs outside the file_lock so the rename doesn't contend with readers") is removed; replace with a comment citing cycle-18 AC4 and Phase 4.5 HIGH R5 concurrency-race lesson.
- **AC5**: Extract a reusable `rotate_if_oversized(path: Path, max_bytes: int, archive_stem_prefix: str) -> None` public helper in `kb.utils.wiki_log` (or a new `kb.utils.rotation` sibling if the ingest-log caller in AC11 prefers not to import from `wiki_log`). `_rotate_log_if_oversized` becomes a thin wrapper calling the helper with `max_bytes=LOG_SIZE_WARNING_BYTES` and `archive_stem_prefix="log"`.
- **AC6**: Regression test `tests/test_cycle18_wiki_log.py::test_rotate_inside_lock` asserts via a spy on `file_lock.__enter__` + `log_path.rename` that rotation happens AFTER the lock is acquired. Uses call-order spy (cycle-17 L2 pattern) — NOT simulated concurrency. A broken implementation (rotate outside lock) fails the assertion. Plus `test_rotate_if_oversized_generic` covers the generic helper with a non-`log.md` path.

### File 3 — `src/kb/compile/linker.py`

- **AC7**: Wrap the read/modify/`atomic_text_write` triple inside the `inject_wikilinks` scalar for loop (currently lines 203-260) with `with file_lock(page_path):` so concurrent injections into the same target page are serialised. The lock must be acquired BEFORE `page_path.read_text` and released AFTER `atomic_text_write`. Pages that get no modification (no match, already-linked, self) MUST NOT acquire the lock (fast-path; otherwise 5k-page scans become 5k lock-acquire/release pairs on every ingest).
- **AC8**: Regression test `tests/test_cycle18_linker_lock.py::test_inject_wikilinks_per_page_lock` asserts via a call-order spy on `file_lock` + `read_text` + `atomic_text_write` that the sequence per modified page is `file_lock.__enter__ → read_text → atomic_text_write → file_lock.__exit__`. Uses the cycle-17 L2 pattern; does NOT simulate concurrency. Also assert the fast-path: a page with no match acquires ZERO locks.

### File 4 — `src/kb/ingest/pipeline.py` (observability + index-files helper)

- **AC9**: At the entry of `ingest_source`, generate `request_id = uuid.uuid4().hex[:16]` (16-hex characters, 64 bits of entropy — sufficient for per-ingest correlation). Thread it through the function body as a local variable; subsequent ACs consume it.
- **AC10**: Prefix every `append_wiki_log(...)` call inside `ingest_source` with `[req={request_id}]` — mirrored in the entry body so the pipe-delimited format remains parseable. Change `append_wiki_log` signature? NO — prefix the message on the caller side so the helper remains a generic append (no cross-module dependency on request_id shape). Update existing call-sites in `ingest_source` only.
- **AC11**: Add `_emit_ingest_jsonl(request_id, source_ref, source_hash, outcome, pages_created, pages_updated, pages_skipped, stage)` that appends one JSON object per line to `<PROJECT_ROOT>/.data/ingest_log.jsonl`. **Writer mechanics (threat model action item 3)**: wraps append in `file_lock(jsonl_path)` + `open("a", encoding="utf-8", newline="\n")` + `f.write(json.dumps(row, ensure_ascii=False) + "\n")` + `f.flush()` + `os.fsync(f.fileno())`. **MUST NOT use `atomic_text_write`** — its temp+rename semantics replace the entire file per append and destroy history. Fields required: `ts` (ISO-8601 UTC `Z`-suffix), `request_id`, `source_ref`, `source_hash`, `stage` (enum: `start`, `duplicate_skip`, `success`, `failure`), `outcome` (dict with counts + redacted `error_summary`). Called at start, on duplicate-skip, on success, and on failure.
- **AC12**: `_emit_ingest_jsonl` uses the `rotate_if_oversized` helper from AC5 to archive `.data/ingest_log.jsonl` when it exceeds 500KB (same threshold as `wiki_log.py` `LOG_SIZE_WARNING_BYTES`). Archive naming mirrors wiki log: `ingest_log.YYYY-MM.jsonl`, ordinal-collision fallback. **The `rotate_if_oversized` call MUST run INSIDE `file_lock(jsonl_path)`**, symmetric with AC4's wiki-log fix — the exact "rotate outside lock" anti-pattern AC4 removes.
- **AC13**: `_emit_ingest_jsonl` redacts absolute paths (Windows `C:\...`, `D:\...`, UNC, POSIX `/home/...`, `/Users/...`, `/opt/...`, `/var/...`, `/srv/...`, `/tmp/...`, `/mnt/...`, `/root/...`) from free-text fields (error summaries, status messages). Because `kb.utils.sanitize.sanitize_error_text(exc, *paths)` takes a `BaseException` (not a string), extract a sibling **`sanitize_text(s: str) -> str`** in `kb.utils.sanitize` that shares the `_ABS_PATH_PATTERNS` regex. `_emit_ingest_jsonl` calls `sanitize_text`; `sanitize_error_text` internally calls `sanitize_text` after its exception-attribute sweep (no behaviour change for existing callers). Raw source content / page bodies are NEVER written to the JSONL. Only `source_ref` (relative path) + `source_hash` (SHA-256 hex) + counts.
- **AC14**: Extract `_write_index_files(wiki_dir, created_entries, source_ref)` helper in `pipeline.py` that wraps the existing `_update_sources_mapping(source_ref, wiki_dir, ...)` at `pipeline.py:641` + `_update_index_batch(created_entries, wiki_dir, ...)` at `pipeline.py:681` pair with a documented ordering contract (`_sources.md` update BEFORE `index.md` update — index is the human-facing catalog and must reference sources that the map already knows about). Each call is independently atomic; helper does NOT retry or roll back on partial failure — preserves existing `logger.warning` pass-through. Existing callers in `ingest_source` switch to the new helper. **Symbol constraint (threat model T10 / monkeypatch enumeration)**: `_update_sources_mapping` and `_update_index_batch` MUST remain callable as module attributes (`kb.ingest.pipeline._update_sources_mapping` / `_update_index_batch`) — 2 test monkeypatch sites in `test_v01008_ingest_pipeline_fixes.py` depend on it. Do NOT inline.
- **AC15**: Regression tests in `tests/test_cycle18_ingest_observability.py`:
  - `test_request_id_prefix_in_log_md` — assert the log.md line for one successful ingest begins with `[req=<16-hex>]` and the hex exactly matches the JSONL entry's `request_id` field.
  - `test_jsonl_emitted_on_success` — assert one line per ingest with required fields; successful ingest → `stage="success"`.
  - `test_jsonl_emitted_on_duplicate` — assert duplicate-skip path emits `stage="duplicate_skip"`.
  - `test_jsonl_rotation` — write >500KB of ingest_log content via direct fixture, call `_emit_ingest_jsonl` once, assert archived and new file created.
  - `test_jsonl_redacts_absolute_paths` — inject a synthetic failure whose error message contains `C:\\Users\\Admin\\...`, assert the path is replaced with `<path>` in the JSONL entry.
  - `test_write_index_files_ordering` — spy on `_update_sources_md` + `_update_index_md`; assert sources is called BEFORE index; both called exactly once per `_write_index_files(...)` invocation.

### File 5 — `tests/test_workflow_e2e.py` (NEW)

- **AC16**: Three scenarios driving `ingest_source` → `query_wiki` → `refine_page` over `tmp_project` (cycle-17 AC15 deferral). Mock ONLY the boundary LLM calls (`kb.utils.llm.call_llm`, `kb.utils.llm.call_llm_json`, and `kb.query.engine.call_llm`). Scenarios:
  - (a) Ingest one article with extraction payload → `query_wiki("What is X?")` returns a non-empty answer referencing the summary page; `citations` contains both `type='wiki'` and `type='raw'` entries.
  - (b) After scenario (a), call `refine_page(<entity_page_id>, "refined body", notes="test")` → re-ingest related article → `query_wiki` returns the refined body in context.
  - (c) Ingest two articles sharing entity "Anthropic" → second ingest's result dict contains `wikilinks_injected` with the first article's entity/concept pages.
  - Total test count for this file: 3 tests. Marked `@pytest.mark.integration` to enable future slow-suite separation if needed.

## Blast radius

| Module | Change | Risk |
|---|---|---|
| `tests/conftest.py` | additive `HASH_MANIFEST` patch to `tmp_kb_env` | LOW — affects tests only |
| `src/kb/utils/wiki_log.py` | concurrency semantic change (rotate-in-lock) + helper extraction | MEDIUM — touches hot append path; mitigated by call-order test |
| `src/kb/compile/linker.py` | per-page `file_lock` around read/modify/write in scalar `inject_wikilinks` | MEDIUM — adds lock overhead on every modified page; fast-path bypass for no-op pages |
| `src/kb/ingest/pipeline.py` | new `request_id` in log lines (prefix) + new `.data/ingest_log.jsonl` write path + index-files helper refactor | MEDIUM-HIGH — new FS write surface + secret-redaction requirement |
| `tests/test_workflow_e2e.py` | new file, 3 integration tests | LOW — additive |

## Threat surfaces for Step 2

- `T1` (new): `.data/ingest_log.jsonl` writing — must not leak raw source content, API keys, absolute filesystem paths, or PII from error strings.
- `T2` (existing, now reinforced): `wiki/log.md` rotation-append race — rotate-in-lock fix closes the POSIX handle-holding-stale-file window.
- `T3` (existing, now reinforced): `inject_wikilinks` cross-process clobber — per-page `file_lock` serialises concurrent injections on the same target.
- `T4` (new): `request_id` uniqueness — 64-bit entropy from `uuid4` is sufficient per-process; collision probability negligible.
- `T5` (fixture): `tmp_kb_env` `HASH_MANIFEST` redirect — production `HASH_MANIFEST` must not be written to by any test that uses `tmp_kb_env`. Regression test AC3 pins this.

## Dep-CVE baseline snapshot (for Step 11 diff)

Captured at Step 2 dispatch; files:
- `/tmp/cycle-18-alerts-baseline.json` — `gh api repos/Asun28/llm-wiki-flywheel/dependabot/alerts` open-only.
- `/tmp/cycle-18-cve-baseline.json` — `pip-audit -r requirements.txt --format json`.

## R3 trigger assessment (per cycle-17 L4)

R3 MANDATORY if >=25 ACs OR >=15 ACs AND any of:
- (a) new FS write surface — **YES** (`.data/ingest_log.jsonl`)
- (b) vacuous-test regression risk — **YES** (file_lock tests per cycle-17 L2)
- (c) new security enforcement point — **YES** (secret redaction in JSONL writer)
- (d) design-gate resolved >=10 open questions — TBD at Step 5

Cycle 18 AC count: 16. R3 is likely mandatory at Step 14.
