# Cycle 18 Design Evaluation — R2

Date: 2026-04-20
Reviewer: R2
Lens: edge cases, failure modes, integration, security, performance

## Symbol greps (confirmed)

- `rg -n "def inject_wikilinks" src`:
  - `src/kb/compile/linker.py:166` is the only definition. It is scalar today; no batch form exists.
- `rg -n "_update_sources_mapping|_update_index_batch" src`:
  - `src/kb/ingest/pipeline.py:641` defines `_update_sources_mapping`.
  - `src/kb/ingest/pipeline.py:681` defines `_update_index_batch`.
  - `src/kb/ingest/pipeline.py:1066` calls `_update_index_batch`.
  - `src/kb/ingest/pipeline.py:1070` calls `_update_sources_mapping`.
  - No out-of-pipeline callers were found.
- `rg -n "append_wiki_log" src`:
  - Writer definition: `src/kb/utils/wiki_log.py:52`.
  - `ingest_source` caller in AC10 scope: `src/kb/ingest/pipeline.py:1091`.
  - Other callers outside AC10 scope: `src/kb/compile/compiler.py:481`, `src/kb/lint/checks.py:151`, `src/kb/mcp/quality.py:559`, `src/kb/review/refiner.py:247`.
  - `src/kb/utils/__init__.py:9` only re-exports.
- `rg -n "ingest_source" src`:
  - Definition: `src/kb/ingest/pipeline.py:819`.
  - Runtime callers needing request-id behavior transitively: `src/kb/cli.py:143`, `src/kb/compile/compiler.py:414`, `src/kb/lint/augment.py:905`, `src/kb/mcp/core.py:489`, `src/kb/mcp/core.py:526`, `src/kb/mcp/core.py:687`, `src/kb/mcp/core.py:689`.
  - Since request ID is generated inside `ingest_source`, these callers do not need signature plumbing in cycle 18.
- `rg -n "from kb\\.utils\\.sanitize import|from kb\\.mcp\\.app import _sanitize_error_str" src`:
  - `src/kb/mcp/app.py:11` imports `sanitize_error_text`.
  - `src/kb/lint/_safe_call.py:17` imports `sanitize_error_text`.
  - `src/kb/mcp/browse.py:15`, `src/kb/mcp/health.py:12`, `src/kb/mcp/quality.py:22` import `_sanitize_error_str` from `kb.mcp.app`.
  - `pipeline.py` imports neither sanitizer today.
- `rg -n "fsync|atomic_text_write" src/kb/utils`:
  - `src/kb/utils/io.py:55` is the only `os.fsync` call, via `_flush_and_fsync`.
  - `atomic_json_write` fsync path: `src/kb/utils/io.py:79`.
  - `atomic_text_write` fsync path: `src/kb/utils/io.py:114`.
  - `atomic_text_write` definition: `src/kb/utils/io.py:93`.

## AC-level edge cases and verdicts

- AC1/AC2/AC3 HASH_MANIFEST mirror: **MAJOR**.
  `tests/conftest.py:224-231` only mirrors already-imported bindings in `kb` modules. It will not catch `from kb.compile.compiler import HASH_MANIFEST` performed at module top in `tests.*` modules before `tmp_kb_env` runs. This is explicitly visible from the `module_name == "kb" or module_name.startswith("kb.")` guard at `tests/conftest.py:227`.
  `tests/test_ingest.py:581` uses `patch("kb.compile.compiler.HASH_MANIFEST", manifest_path)`, not a top-level direct import, so that specific file is not a risk from the grep output. The residual risk is future or hidden test modules that bind the constant into their own namespace.
  Verdict: AC3 should include a negative/educational assertion or a note that top-level test-module direct imports remain unsupported.

- AC4 rotate-in-lock: **BLOCKER**.
  Current code rotates outside the lock at `src/kb/utils/wiki_log.py:107-109`, then opens under lock at `src/kb/utils/wiki_log.py:126-128`.
  If two cooperating processes both use `file_lock(log_path)`, the lock file itself prevents double-rotation while held. However, `file_lock` deletes the lock with `missing_ok=True` at `src/kb/utils/io.py:350-351`; if an external stale-cleanup process removes the lock file while a holder is active, two holders can exist and the guarantee collapses. This is an advisory-lock residual risk, not fixable by AC4 alone.
  Rotation must happen before the `[req=]` message write, inside the lock. Otherwise the append can still land in the file that is about to be archived.

- AC5 generic rotate helper: **MINOR**.
  The existing `logger.info("Rotating %s...")` at `src/kb/utils/wiki_log.py:40-45` belongs in the generic `rotate_if_oversized` helper, not in the wiki-log wrapper. The audit event is a property of rotation, and AC12 needs the same pre-rename audit chain for `.data/ingest_log.jsonl`.

- AC6 call-order test: **MAJOR**.
  `file_lock` is a contextmanager that yields no value at `src/kb/utils/io.py:226` and `src/kb/utils/io.py:348`. A spy that records only in `__enter__` can be vacuous if the mocked `file_lock` never enforces acquisition or if the implementation calls the spy context without actually wrapping the rotate. The test must assert a total order across `lock_enter`, `rename`, `open/write`, and `lock_exit`, and must fail if `_rotate_log_if_oversized` is invoked before `lock_enter`.

- AC7 inject_wikilinks lock: **BLOCKER**.
  Current code reads before any lock at `src/kb/compile/linker.py:210-212` and writes at `src/kb/compile/linker.py:259-260`.
  The lock should be acquired once per page that is known to be a modification candidate, not inside the inner `for match in pattern.finditer(body)` loop at `src/kb/compile/linker.py:246`.
  To preserve correctness, the lock must wrap the post-lock read, frontmatter split, existing-link check, masking, finditer replacement, `_unmask_code_blocks`, final comparison, and `atomic_text_write`. If `_unmask_code_blocks` or `new_body != original_body` is outside the lock, the decision is based on stale body state.
  The no-op fast path should do a cheap pre-read/search outside the lock, but then must re-read and re-check under lock before writing.

- AC8 no-op fast-path test: **MAJOR**.
  A test that appends page paths via a spy and mocks `file_lock` to raise can confuse "the page did not match" with "the page matched but lock failed before recording." The fast-path assertion needs a page whose body definitely contains no candidate match and a separate page that definitely contains a candidate match, with distinct assertions: zero lock calls for the no-match page, and a lock attempt for the match page.

- AC9 uuid.uuid4: ok.
  `uuid.uuid4().hex[:16]` is sufficient for per-ingest correlation.

- AC10 `[req=]` prefix: **MINOR**.
  The prefix should be inside the message string passed to `append_wiki_log`, per AC10, not a separate operation field. Current message is built at `src/kb/ingest/pipeline.py:1092-1094`.
  It survives `_escape_markdown_prefix` because `[req=` does not trigger the leading marker guard at `src/kb/utils/wiki_log.py:72-80`, and it contains no `|`, newline, tab, `[[`, or `]]`.

- AC11 JSONL writer: **BLOCKER**.
  The directive "not atomic_text_write" is correct. `atomic_text_write` uses temp+replace at `src/kb/utils/io.py:106-115`, which would replace the whole log on every append.
  The implementation must use `file_lock(jsonl_path)` plus `open("a", encoding="utf-8", newline="\n")`, `write`, `flush`, and `os.fsync`.
  It must create the parent `.data/` directory before `file_lock(jsonl_path)` or rely on `file_lock` creating the lock parent at `src/kb/utils/io.py:253-254`; still, the data file parent should be explicitly created for clarity and future non-lock refactors.
  It must enforce a writer-side field allowlist. Documentation alone is insufficient; `_emit_ingest_jsonl` should construct the row from scalar arguments and reject/normalize free-form `stage`.

- AC12 rotation call-site inside lock: **BLOCKER**.
  Same order requirement as AC4. `_emit_ingest_jsonl` must acquire `file_lock(jsonl_path)`, rotate under that lock, then append and fsync under the same lock.

- AC13 sanitize_text: **MAJOR**.
  Current regex at `src/kb/utils/sanitize.py:11-15` covers drive-letter Windows paths, `\\?\...`, and selected POSIX roots. It does not cover ordinary UNC paths like `\\server\share\file` unless they use the `\\?\` long-path prefix, even though the requirements explicitly list UNC.
  Do not lowercase or slash-collapse the input before redaction unless tests prove both `C:/Users/...` and `C:\Users\...` survive. The current regex already handles both slash shapes for drive-letter paths.
  `sanitize_text` should call the same regex without normalizing away evidence needed by T1.

- AC14 `_write_index_files`: **BLOCKER**.
  Current implementation updates `index.md` first at `src/kb/ingest/pipeline.py:1066`, then `_sources.md` at `src/kb/ingest/pipeline.py:1070`.
  AC14 requires `_sources.md` before `index.md`, which is a real behavior change. The design must explicitly accept this migration and test the new order.
  Preserve independent attempts and warning pass-through: if `_update_sources_mapping` fails and `_update_index_batch` would succeed, `_write_index_files` must still attempt `_update_index_batch` and the log must reflect the sources failure. A naive helper that calls both sequentially without per-call exception handling would regress this failure mode.

- AC15 regression tests: **MAJOR**.
  Vacuous-test risk is real for all call-order tests that only spy on mocked context managers. Tests must include broken-implementation controls or total-order assertions.
  `test_jsonl_emitted_on_success` must account for AC11 saying start plus terminal rows are emitted; if it asserts exactly one line per ingest while AC11 also says called at start, it is internally inconsistent.
  `test_jsonl_rotation` must prove rotation is inside the lock, not merely that an archive appears.

- AC16 e2e test: **MAJOR**.
  The three scenarios exercise partly different code paths, but (a) and (c) can become degenerate if the extraction payload in (a) already creates entity/concept pages and triggers wikilink injection. Scenario (c) must assert that the second ingest injects into first-ingest pages for a shared entity, not merely that the query returns something.
  Scenario (b) should clear or naturally invalidate query caches. `load_page_frontmatter` is mtime-keyed at `src/kb/utils/pages.py:59-88`; wiki BM25 cache keys include `max_mtime_ns` at `src/kb/query/engine.py:638-661`. On coarse filesystems, immediate refine and re-query can reuse stale cache keys. The test should call cache clear hooks or force a distinct mtime.

## Security and performance

- **BLOCKER** JSONL failure policy for `os.fsync` is underspecified.
  `os.fsync` can raise at `src/kb/utils/io.py:55`, and AC11's new writer will call it directly. Decide whether `_emit_ingest_jsonl` is best-effort or hard-fail. For ingest observability, recommended behavior is best-effort: catch `OSError`, log `WARNING`, and never hide a successful ingest. For `stage="failure"`, also avoid raising from the telemetry path and masking the original exception.

- **MAJOR** fsync-per-append has a measurable write-amplification cost.
  Recommended cycle-18 policy: strict mode by default for now, meaning fsync every JSONL append, because the field set is small and the feature is an audit trail. Add a module constant or comment naming the durability policy. Revisit relaxed batching only if measurement shows the cycle SLO is missed. Relaxed mode would fsync on rotation and process exit, but process-exit hooks are unreliable in crashes and test runners.

- **MAJOR** lock timeout can multiply across `inject_wikilinks`.
  `file_lock` defaults to 5 seconds at `src/kb/utils/io.py:252`. If a lock is stuck, a per-page implementation can block 5 seconds for each candidate page. On 20 hot pages, that is about 100 seconds.
  Recommended bounded behavior: use a shorter timeout for wikilink injection, e.g. `file_lock(page_path, timeout=0.25)`, log a warning, skip that page, and continue. Accepting default 5 seconds is tolerable only if the design explicitly states that ingest may stall and eventually continue/fail.

- **MAJOR** Windows rename collision is safe only under cooperative locking.
  `Path.rename` over an existing destination raises on Windows; POSIX may replace. The ordinal loop at `src/kb/utils/wiki_log.py:35-39` is safe when called under a single cooperative lock. If non-cooperative processes or stale-cleanup double-holders bypass the lock, ordinal collision remains possible.

- **MAJOR** sanitizer UNC coverage misses a required path shape.
  The requirements name UNC paths. Current regex only catches `\\?\...` long-path UNC-ish forms at `src/kb/utils/sanitize.py:13`, not `\\server\share\...`.

- **MINOR** JSONL row size should remain bounded.
  Keep `error_summary` truncated to a conservative length after redaction. This preserves append atomicity assumptions and prevents large exception strings from making the audit log a new large-write path.

## Blockers (must fix before Step 5 gate)

- **BLOCKER** `src/kb/ingest/pipeline.py:1066` / `src/kb/ingest/pipeline.py:1070`: AC14 changes index/source write order, but the design must preserve independent-attempt failure behavior. Add explicit per-call try/except in `_write_index_files`, with `_sources.md` attempted first and `index.md` attempted second even if sources fails.

- **BLOCKER** `src/kb/compile/linker.py:210-260`: AC7 must specify double-check under lock. Fast-path pre-scan can skip locks for no-match pages, but any page that might change must be re-read and fully processed under `file_lock(page_path)` through `_unmask_code_blocks` and `atomic_text_write`.

- **BLOCKER** `src/kb/ingest/pipeline.py:819`: AC11/AC12 need an explicit JSONL telemetry failure policy. `_emit_ingest_jsonl` should be best-effort from `ingest_source`, should not mask success/failure return paths, and should log warnings on append, rotation, or fsync errors.

- **BLOCKER** `src/kb/utils/sanitize.py:11-15`: AC13 must add ordinary UNC redaction before claiming threat-model T1 coverage.

- **BLOCKER** `src/kb/utils/wiki_log.py:107-109` and future `_emit_ingest_jsonl`: rotation must occur inside the corresponding `file_lock` and before the append.

## Majors (fix recommended)

- **MAJOR** `tests/conftest.py:224-231`: mirror-rebind does not patch top-level `tests.*` imports of `HASH_MANIFEST`. Add a note/test guard so authors do not assume this is solved for test-module globals.

- **MAJOR** `src/kb/utils/io.py:252`: default 5s lock timeout is too high for per-page wikilink injection loops. Use a bounded timeout and skip/warn policy or explicitly accept the stall.

- **MAJOR** `tests/test_cycle18_ingest_observability.py` planned AC15: "one line per ingest" conflicts with AC11's start plus terminal emission. Specify either two rows per non-duplicate ingest (`start`, `success`) or one terminal row only.

- **MAJOR** `tests/test_cycle18_linker_lock.py` planned AC8: zero-lock fast-path tests must use a guaranteed no-match page and a separate guaranteed-match page.

- **MAJOR** `tests/test_cycle18_wiki_log.py` planned AC6: call-order tests must assert `lock_enter < rotate/rename < append < lock_exit`, not just that all events happened.

- **MAJOR** `tests/test_workflow_e2e.py` planned AC16: clear mtime-keyed/cached query state or force mtime separation before asserting refined body appears.

- **MAJOR** `src/kb/ingest/pipeline.py:1091`: request ID is generated inside `ingest_source`, but only the successful wiki-log call exists today. If duplicate/failure paths are expected to correlate in `wiki/log.md`, the design must add log calls there or state JSONL is the only duplicate/failure correlation surface.

## Minors (nit)

- **MINOR** `src/kb/utils/wiki_log.py:40-45`: keep the rotation audit log in the generic helper.

- **MINOR** `src/kb/ingest/pipeline.py:1092`: put `[req=<hex>]` inside the message string. Do not change `append_wiki_log` signature or operation field.

- **MINOR** `src/kb/ingest/pipeline.py:819`: truncate `error_summary` after `sanitize_text`; a 1-2KB cap is enough for debugging without turning JSONL into content storage.

- **MINOR** `src/kb/utils/sanitize.py:30-51`: add direct `sanitize_text` tests for Windows drive paths with both `\` and `/`, long-path prefix, ordinary UNC, POSIX roots, and adjacent punctuation.

## Suggested amendments (exact text replacements)

1. Replace AC11 test wording:

```text
test_jsonl_emitted_on_success — assert JSONL emits the expected stage sequence for one successful ingest: start followed by success. Both rows contain the same request_id and the terminal row has outcome counts.
```

2. Add to AC11 writer mechanics:

```text
Before acquiring file_lock(jsonl_path), ensure jsonl_path.parent exists with mkdir(parents=True, exist_ok=True). _emit_ingest_jsonl constructs the row itself from an explicit field allowlist and validates stage is one of {"start", "duplicate_skip", "success", "failure"}.
```

3. Add to AC11/AC12 failure policy:

```text
_emit_ingest_jsonl is best-effort from ingest_source. OSError from rotation, append, flush, or os.fsync is logged at WARNING and must not mask an otherwise successful ingest or replace the original exception on failure paths.
```

4. Replace AC7 lock wording:

```text
Pages may be pre-scanned outside the lock to preserve the no-op fast path. For any page that may be modified, acquire file_lock(page_path), re-read the file, re-run the existing-link/self/match checks on the fresh content, perform masking, replacement, _unmask_code_blocks, final comparison, and atomic_text_write inside that lock.
```

5. Add to AC8:

```text
The fast-path assertion uses a guaranteed no-match page and separately asserts a guaranteed-match page attempts to acquire the lock, so the test distinguishes "no match" from "lock failed before write."
```

6. Replace AC14 failure-mode wording:

```text
_write_index_files attempts _update_sources_mapping first and _update_index_batch second. Each call has its own try/except that logs WARNING and allows the second call to run if the first fails. The helper does not retry or roll back.
```

7. Add to AC13:

```text
_ABS_PATH_PATTERNS must cover ordinary UNC paths of the form \\server\share\path in addition to \\?\... long paths. Tests must cover both slash directions for drive-letter paths and must not rely on lowercasing or slash-collapsing before redaction.
```

8. Add to AC16:

```text
Scenario (b) must invalidate query/page caches or force a distinct page mtime before re-querying after refine_page. Scenario (c) must assert that the second ingest injects links into pages created by the first ingest, not only that a query returns a non-empty answer.
```
