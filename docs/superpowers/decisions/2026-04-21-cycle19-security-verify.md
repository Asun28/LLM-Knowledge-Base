# Cycle 19 Security Verify

**Date:** 2026-04-21
**Role:** Step 11 security-verify subagent
**Verdict:** APPROVE

## Scope

Reviewed cycle-19 diff `20ec881..HEAD` and final design conditions in
`2026-04-21-cycle19-design.md`. Note: final AC10 withdrew the originally
proposed history-first lock flip; verification therefore checks the final
required order: `page_path FIRST, history_path SECOND`.

Targeted tests run:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_cycle19_inject_wikilinks_batch.py tests/test_cycle19_inject_batch_e2e.py tests/test_cycle19_manifest_key_consistency.py tests/test_cycle19_refiner_two_phase.py tests/test_cycle19_lint_redundant_patches.py tests/test_cycle19_prune_base_consistency_anchor.py
37 passed, 1 skipped
```

## Threat Verification

### T1 - HIGH ReDoS via batch alternation

**IMPLEMENTED.** `MAX_INJECT_TITLES_PER_BATCH = 200` and
`MAX_INJECT_TITLE_LEN = 500` are defined in `src/kb/config.py` and imported in
`src/kb/compile/linker.py`. `inject_wikilinks_batch` sanitizes and length-filters
titles before regex construction, chunks with
`sanitized_pages[chunk_idx * chunk_size : ...]`, and catches failures per chunk.
Title regex construction uses `re.escape(title)` in `_build_title_pattern` and
retains the existing word-boundary semantics.

### T2 - MEDIUM null-byte title smuggling

**IMPLEMENTED.** `inject_wikilinks_batch` strips null bytes at function entry via
`clean_title = title.replace("\x00", "")` before length checks, regex
compilation, matching, or log-visible output. `_mask_code_blocks` /
`_unmask_code_blocks` remain unchanged with per-call UUID placeholder prefixes.

### T3 - MEDIUM manifest_key dict-key injection

**IMPLEMENTED.** `ingest_source` places `manifest_key` after the `*` sentinel, so
it is keyword-only. The docstring describes it as an opaque `.data/hashes.json`
dict key produced by `manifest_key_for`, explicitly not a filesystem path.
Validation rejects any key containing `..`, leading `/` or `\`, `\x00`, or length
over 512. `manifest_ref = manifest_key if manifest_key is not None else
source_ref` is derived once and used for both `_check_and_reserve_manifest` and
the tail manifest confirmation write. `compile_wiki` derives `rel_path =
_canonical_rel_path(source, raw_dir)` once and passes it as `manifest_key=rel_path`.
`manifest_key_for` is a public alias for `_canonical_rel_path`.

### T4 - MEDIUM refine two-phase write liveness

**IMPLEMENTED.** Final design AC10 requires preserving the cycle-1 H1 lock order:
`page_path FIRST, history_path SECOND`. `refiner.py` documents this order in the
module docstring and implementation comments. The page lock is acquired before
the single `with file_lock(resolved_history_path):` span. Within that one
history-lock span, `refine_page` appends `status="pending"` with a fresh
`attempt_id`, performs the page `atomic_text_write`, and flips the matching
`attempt_id` row to `applied` or `failed`. This satisfies AC8/AC9/AC10 as
finalized and avoids the withdrawn history-first liveness regression.

### T5 - LOW log injection via batch wiki_log entry

**IMPLEMENTED.** The batch wiki-log entry in `src/kb/ingest/pipeline.py` routes
through `append_wiki_log("inject_wikilinks_batch", ...)`; no raw
`log_path.write_text` or direct log file append is used for the batch log line.
It therefore inherits the existing markdown-prefix, newline, pipe, and wikilink
neutralization in `kb.utils.wiki_log`.

## Same-Class Peer Scan

**Path-traversal style (`..`, leading `/`, `\x00`):** no peer production site
found outside the T3 `manifest_key` validation. Added occurrences elsewhere are
tests or documentation.

**Snapshot-binding pattern (`from kb.config import X`):** one production diff
site found: `src/kb/compile/linker.py` now imports
`MAX_INJECT_TITLE_LEN` and `MAX_INJECT_TITLES_PER_BATCH` alongside the preexisting
`WIKI_DIR` import. Reviewed as non-blocking: the new imports are immutable
numeric limits, not path values read at call time. No new module introduces a
fresh path snapshot-binding pattern.

**Single-derivation pattern:** no peer duplicate-key production pattern found.
The only new manifest/dict-key derivation is `manifest_ref`, derived once and
threaded to both writes. Other added dict writes are local result/history/test
state and do not duplicate a security-sensitive key derivation.

## Residual Notes

Full repository test suite was not run in this verification pass; the
cycle-19-focused security/regression set passed under the repo virtualenv.
