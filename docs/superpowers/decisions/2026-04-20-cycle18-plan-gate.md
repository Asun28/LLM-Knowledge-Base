# Cycle 18 — Plan Gate Report

## Verdict
APPROVE-WITH-AMENDMENTS

The plan maps all AC1-AC16 and T1-T10, includes named assertion targets, honors the AC7 TOCTOU contract, and preserves the design-gate decisions. Two task-bullet amendments are required before implementation:

- TASK 1 must not put `HASH_MANIFEST` through the `kb.config` patch loop; `tests/conftest.py:217-218` patches only config attributes, while `HASH_MANIFEST` lives at `kb.compile.compiler`.
- TASK 5 must enforce the JSONL `outcome` field allowlist, not copy `dict(outcome)` wholesale. As written, extra caller fields could enter `.data/ingest_log.jsonl`, weakening T1/AC11.

## AC coverage table
| AC# | TASK# | Status |
|---|---|---|
| AC1 | TASK 1 | Covered: tuple addition at plan:37-40. Amend TASK 1 patch-loop mechanics. |
| AC2 | TASK 1 | Covered: compiler patch/mirror loop at plan:39-42. Amend TASK 1 patch-loop mechanics. |
| AC3 | TASK 1 | Covered: `test_hash_manifest_redirected` assertions at plan:43-48. |
| AC4 | TASK 2 | Covered: rotate moved inside lock at plan:73-81. |
| AC5 | TASK 2 | Covered: `rotate_if_oversized` NEW helper at plan:62-70. |
| AC6 | TASK 2 | Covered: total-order rotate test at plan:90-93. |
| AC7 | TASK 4 | Covered: pre-lock fast path and under-lock RMW at plan:153-233. |
| AC8 | TASK 4 | Covered: five explicit lock/TOCTOU assertions at plan:235-240. |
| AC9 | TASK 5 | Covered: uuid request_id at plan:320-329. |
| AC10 | TASK 5 | Covered: `[req=]` prefix at plan:369-377. |
| AC11 | TASK 5 | Covered with amendment: writer mechanics and try/except at plan:255-365; outcome allowlist must be fixed. |
| AC12 | TASK 5 | Covered: rotate inside JSONL lock at plan:279, 301-305, 442-444. |
| AC13 | TASK 3, TASK 5 | Covered: `sanitize_text` + UNC in TASK 3 at plan:106-140; pipeline usage at plan:280, 316, 361. |
| AC14 | TASK 5 | Covered: `_write_index_files` ordering and independent failure at plan:379-428. |
| AC15 | TASK 5 | Covered: 11 named tests and assertions at plan:430-454. Amend field-allowlist assertion. |
| AC16 | TASK 6 | Covered: 3 integration scenarios at plan:461-503. |

## Threat coverage table
| T# | TASK# | Test name | Status |
|---|---|---|---|
| T1 | TASK 3, TASK 5 | `test_jsonl_redacts_absolute_paths`; add field-allowlist extra-key assertion | AMEND: redaction covered at plan:446; outcome-field allowlist not enforced by plan:288-290. |
| T2 | TASK 2 | `test_rotate_inside_lock` | Covered: plan:90-91. |
| T3 | TASK 4 | `test_inject_wikilinks_sequence_order`, `test_inject_wikilinks_toctou_skip` | Covered: plan:238-239. |
| T4 | TASK 5 | `test_request_id_prefix_in_log_md` | Covered structurally by uuid4 and correlation assertion at plan:326, 434; uniqueness is design-guaranteed, no randomness test needed. |
| T5 | TASK 1 | `test_hash_manifest_redirected` | Covered with amendment: test at plan:43-48; patch-loop mechanics must avoid config attr failure. |
| T6 | TASK 2, TASK 5 | `test_rotate_inside_lock`, `test_jsonl_rotation_inside_lock` | Covered: plan:90-91 and plan:444. |
| T7 | TASK 5 | `test_jsonl_error_summary_truncation`, `test_jsonl_emitted_on_success` | Covered: fsync/line append at plan:301-306, row-size pin at plan:450, parseable rows at plan:436. |
| T8 | TASK 4 | `test_inject_wikilinks_fast_path_no_lock_on_no_match` | Covered: plan:236. |
| T9 | TASK 5 | `test_request_id_prefix_in_log_md` | Covered: hex-only prefix assertion at plan:434. |
| T10 | TASK 5 | `test_write_index_files_ordering`, `test_write_index_files_independent_failure` | Covered: real symbols used at plan:452-454; Step 11 caller-grep at plan:526. |

## Symbol verification
- `src/kb/ingest/pipeline.py:252` — `_check_and_reserve_manifest` EXISTS.
- `src/kb/ingest/pipeline.py:641` — `_update_sources_mapping` EXISTS.
- `src/kb/ingest/pipeline.py:681` — `_update_index_batch` EXISTS.
- `src/kb/utils/wiki_log.py:13` — `LOG_SIZE_WARNING_BYTES` EXISTS.
- `src/kb/utils/wiki_log.py:16` — `_rotate_log_if_oversized` EXISTS.
- `src/kb/utils/wiki_log.py` — `rotate_if_oversized` MISSING as expected; plan marks it NEW at plan:62.
- `src/kb/utils/sanitize.py:11` — `_ABS_PATH_PATTERNS` EXISTS.
- `src/kb/utils/sanitize.py:30` — `sanitize_error_text` EXISTS.
- `src/kb/utils/sanitize.py` — `sanitize_text` MISSING as expected; plan marks it NEW at plan:117-127.
- `src/kb/utils/io.py:226` — `file_lock(path: Path, timeout: float | None = None)` EXISTS. Timeout kwarg name is `timeout`; default is `LOCK_TIMEOUT_SECONDS` when `None` at `src/kb/utils/io.py:252`. Timeout exception type is `TimeoutError` at `src/kb/utils/io.py:338` and `src/kb/utils/io.py:343`.
- `src/kb/compile/linker.py:166` — `inject_wikilinks` EXISTS.
- Plan NEW symbols explicitly marked or introduced: `_emit_ingest_jsonl` at plan:255-310, `_write_index_files` at plan:379-403, `_INJECT_LOCK_TIMEOUT` at plan:159.

## Gaps (if any)
- TASK 1 implementability gap: plan:39 adds `HASH_MANIFEST` to the `patched` dict, but current `tests/conftest.py:185` computes `getattr(config, name)` for every `patched` key and `tests/conftest.py:217-218` patches `kb.config`. Since `HASH_MANIFEST` is not in `kb.config`, this would fail before the explicit compiler patch.
- TASK 5 T1 allowlist gap: plan:288 copies `safe_outcome = dict(outcome)`, which allows arbitrary extra keys. AC11/design-gate requires field allowlist enforcement and T1 excludes raw source content and free-form fields.
- TASK 5 `test_jsonl_field_allowlist` at plan:448 only tests invalid `stage`; it does not fail if extra `outcome` fields are serialized.

## Amendments (if any)
### TASK 1 replacement text
Replace TASK 1 Change bullets 2-3 with:

```text
2. In `tmp_kb_env`, keep the existing `patched` dict limited to `kb.config` attributes. Define `hash_manifest_path = data / "hashes.json"` separately and import `kb.compile.compiler as compiler`.
3. Build a combined mirror map without sending `HASH_MANIFEST` through the config loop:
   - `original_values = {name: getattr(config, name) for name in patched}`
   - `original_values["HASH_MANIFEST"] = compiler.HASH_MANIFEST`
   - `mirror_patched = dict(patched)`
   - `mirror_patched["HASH_MANIFEST"] = hash_manifest_path`
   - run `for name, value in patched.items(): monkeypatch.setattr(config, name, value)` for config attributes only
   - then `monkeypatch.setattr(compiler, "HASH_MANIFEST", hash_manifest_path)`
   - update the mirror-rebind loop to iterate `mirror_patched.items()` and compare against `original_values[name]`, so already-imported `kb.*.HASH_MANIFEST` bindings are rebound.
```

### TASK 5 replacement text
Replace the `_emit_ingest_jsonl` outcome-copy block at plan:288-290 with:

```text
    allowed_outcome_keys = {
        "pages_created",
        "pages_updated",
        "pages_skipped",
        "error_summary",
    }
    unexpected = set(outcome) - allowed_outcome_keys
    if unexpected:
        logger.warning(
            "Dropping unexpected ingest_log outcome fields: %s",
            ", ".join(sorted(unexpected)),
        )
    safe_outcome = {}
    for key in ("pages_created", "pages_updated", "pages_skipped"):
        if key in outcome:
            safe_outcome[key] = int(outcome[key])
    err = outcome.get("error_summary")
    if isinstance(err, str) and err:
        safe_outcome["error_summary"] = sanitize_text(err)[:_INGEST_JSONL_ERROR_SUMMARY_MAX]
```

Replace TASK 5 test 8 with:

```text
8. `test_jsonl_field_allowlist` — call `_emit_ingest_jsonl("bogus_stage", ...)` and assert `ValueError` at writer boundary. Then call `_emit_ingest_jsonl("failure", ..., outcome={"error_summary": "x", "raw_content": "SECRET"})`; parse the row and assert `"raw_content" not in row["outcome"]` and `"SECRET" not in json.dumps(row)`.
```

## PLAN-AMENDS-DESIGN check
PLAN-AMENDS-DESIGN-DISMISSED: no Step 5 re-run needed. TASK 5's source-order migration is not a plan amendment; it follows final design AC14 by changing current source order from index-then-sources (`src/kb/ingest/pipeline.py:1066` then `:1070`) to sources-before-index and documents that migration at plan:428. TASK 5's `_write_index_files(created_entries, source_ref, all_pages, wiki_dir=None)` signature at plan:381 differs from the shorthand design-gate text `_write_index_files(wiki_dir, created_entries, source_ref)` at design-gate:630 only to pass `all_pages` to existing `_update_sources_mapping(source_ref, wiki_pages, wiki_dir=None)` at `src/kb/ingest/pipeline.py:641-643`; it does not change AC14 behavior.

## Final verdict summary
APPROVE-WITH-AMENDMENTS. The plan covers all ACs and threats, uses real source symbols or marks NEW helpers, specifies pre-lock and under-lock reads for AC7, and respects batch-by-file clusters. Apply the two exact amendments above before coding so TASK 1 is executable and AC11/T1 field allowlisting is actually enforced.
