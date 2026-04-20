# Cycle 18 — R1 Opus Design Review

**Date:** 2026-04-20
**Reviewer:** R1 Opus (design eval, Step 1 criteria)
**Scope:** 16 ACs across 5 files, 7 design decisions (D1-D7), 12 open questions (Q1-Q12), threat-model items T1-T10.

## Analysis

The cycle 18 spec is well-scoped (16 ACs, 5 files) and directly closes cycle-17 deferrals (AC15, AC19-AC21, fixture HASH_MANIFEST). Threat model quality is strong — it caught the AC14/AC15 symbol-name drift (`_update_sources_md` vs real `_update_sources_mapping`), correctly flagged the `atomic_text_write` anti-pattern for JSONL, and called out the rotate-in-lock anti-pattern symmetry between AC4 and AC12. My independent symbol verification confirms the threat-model table entries except one off-by-one: I count 19 HASH_MANIFEST occurrences across 10 test files, not 20 — well above the 5-site scope threshold but fully additive-compatible, as the threat model argues. The scope is also correctly gated (MCP owner-module migration deferred to cycle 19, `inject_wikilinks_batch` deferred per D4 Option A).

Two substantive design gaps jumped out that should become amendments rather than blockers. First, AC7's fast-path contract is under-specified: the existing `inject_wikilinks` loop reads `page_path.read_text` at line 211 BEFORE the no-match decision — if the lock is taken only "per modified page," two concurrent readers can both read pre-link state, both decide to write, and the lock merely serializes the now-doomed second write (last-writer-wins preserved, nothing won). The proper contract is "acquire lock IF the title pattern matches an unlocked read, then re-read under lock, then decide". Second, AC11's stage=failure emission has no insertion point: `ingest_source` has no outer `try/except` today; exceptions propagate from `raise ValueError` at lines 857/873/885/895/etc. AC11 says "Called at start, on duplicate-skip, on success, and on failure" but the body never catches — a caller-level try/finally or an explicit top-level wrapper is needed. D2 Option C (hybrid helper + inline calls) amplifies this gap because the inline calls cannot fire on exception without an additional try/except block. Either D2 must shift to Option B (context manager guarantees paired emission via `__exit__`) or AC11 must explicitly add a try/except wrapper in `ingest_source`.

---

## Symbol verification

| Symbol | file:line | Status | Notes |
|---|---|---|---|
| `_rotate_log_if_oversized` | `kb/utils/wiki_log.py:16` | EXISTS | Called at line 109 OUTSIDE `file_lock` (line 126). Confirmed AC4 target. |
| `append_wiki_log` | `kb/utils/wiki_log.py:52` | EXISTS | `_escape_markdown_prefix` at 72-81 does NOT match `[req=`. Signature unchanged by AC10. |
| `file_lock` | `kb/utils/io.py:226` | EXISTS | `@contextmanager`. |
| `atomic_text_write` | `kb/utils/io.py:93` | EXISTS | temp+rename; correctly flagged unsafe for JSONL append. |
| `atomic_json_write` | `kb/utils/io.py:58` | EXISTS | Unused by cycle 18. |
| `inject_wikilinks` | `kb/compile/linker.py:166` | EXISTS | Loop 203-263. `read_text` at 211 happens BEFORE match check at 236 — fast-path semantics depend on this ordering, flagged in AC7 amendment. |
| `_update_sources_mapping` | `kb/ingest/pipeline.py:641` | EXISTS | Called at pipeline.py:1070. |
| `_update_index_batch` | `kb/ingest/pipeline.py:681` | EXISTS | Called at pipeline.py:1066. |
| `_update_sources_md` | N/A | **MISSING** | AC15 test name references this; real symbol is `_update_sources_mapping`. SEMANTIC-MISMATCH (also flagged in threat model §9 AI-1). |
| `_update_index_md` | N/A | **MISSING** | Same; real symbol is `_update_index_batch`. |
| `ingest_source` | `kb/ingest/pipeline.py:819` | EXISTS | No outer try/except — see Analysis para 2. Manifest write at 1075-1086; log.md append at 1091-1096; duplicate return at 935. |
| `HASH_MANIFEST` | `kb/compile/compiler.py:25` | EXISTS | `PROJECT_ROOT / ".data" / "hashes.json"`. |
| `_TMP_KB_ENV_PATCHED_NAMES` | `tests/conftest.py:14` | EXISTS | 22-entry tuple. `HASH_MANIFEST` absent (AC1 target). |
| `tmp_kb_env` | `tests/conftest.py:127` | EXISTS | Mirror-rebind loop at 224-231 as documented. |
| `sanitize_error_text` | `kb/utils/sanitize.py:30` | EXISTS | Signature `(exc: BaseException, *paths: Path \| None) -> str`. |
| `_ABS_PATH_PATTERNS` | `kb/utils/sanitize.py:11` | EXISTS | Matches Windows `A-Za-z:[\\/]`, UNC `\\?\`, POSIX `/home|Users|opt|var|srv|tmp|mnt|root`. **Gap**: `/root/` and `/srv/` NOT explicitly enumerated in AC13 spec text but ARE in the regex — AC13 is accurate. |
| `LOG_SIZE_WARNING_BYTES` | `kb/utils/wiki_log.py:13` | EXISTS | 500_000. |

Additional context: `_is_duplicate_content` at pipeline.py:223 (unused by new code) + `_check_and_reserve_manifest` at pipeline.py:252 (the real duplicate-check entry point, line 933) exist as documented.

---

## Monkeypatch enumeration

| Symbol | Sites (from `tests/` files via grep) | Flag |
|---|---|---|
| `HASH_MANIFEST` | **10 files** (test_backlog_by_file_cycle4=1, test_cycle10_extraction_validation=2, test_cycle10_validate_wiki_dir=1, test_cycle11_ingest_coerce=2, test_cycle13_frontmatter_migration=1, test_cycle17_mcp_tool_coverage=2, test_ingest=1, test_v0915_task03=3, test_v099_phase39=6, test_v5_lint_augment_orchestrator=1). Total ≈ 20 occurrences. | **> 5 sites — scope-risk flagged, MITIGATED by additive-compatible fixture bundling (D6 Option A).** |
| `_rotate_log_if_oversized` | 0 monkeypatch sites | OK |
| `_update_sources_mapping` | 1 site (`test_v01008_ingest_pipeline_fixes.py:99`) | OK — under 5 |
| `_update_index_batch` | 1 site (`test_v01008_ingest_pipeline_fixes.py:98`) | OK — under 5 |
| `inject_wikilinks` | 2 sites (`test_review_fixes_v099b.py:59, :161`) | OK — both whole-function replacements; unaffected by internal `file_lock` addition |
| `append_wiki_log` | Found 61 occurrences across 14 test files via grep, but most are call-site asserts, not monkeypatches. No direct `monkeypatch.setattr` or `patch("kb.utils.wiki_log.append_wiki_log")` surfaces in the diff. | OK — prefix is caller-side per AC10 |

**Scope-risk assessment:** Only `HASH_MANIFEST` exceeds the 5-site threshold. D6 Option A (fixture-only + leave 20 explicit patches) is correct given `feedback_batch_by_file`. Cycle 19 cleanup recommended.

---

## AC-level scoring

**AC1**: `_TMP_KB_ENV_PATCHED_NAMES` includes `HASH_MANIFEST` — **SCORE: OK**. Clear, testable via tuple-membership assertion, bounded (1 file), correct scope, no drift.

**AC2**: `tmp_kb_env` patches `kb.compile.compiler.HASH_MANIFEST` — **SCORE: OK**. Clear, testable, bounded. Mirror-loop rebinding is correctly specified.

**AC3**: Regression test `test_hash_manifest_redirected` — **SCORE: NEEDS-AMENDMENT** (minor). The AC asserts both "HASH_MANIFEST equals tmp path" AND "`kb_compile_scan`-style code path writes there". The second clause is vague ("`kb_compile_scan`-style"). Proposed text:

> **AC3**: Regression test `tests/test_cycle18_conftest.py::test_hash_manifest_redirected` asserts under `tmp_kb_env`: (i) `kb.compile.compiler.HASH_MANIFEST == tmp_path / ".data" / "hashes.json"`; (ii) after calling `ingest_source(<small fixture>, extraction=<stub>)`, `(tmp_path / ".data" / "hashes.json").exists()` is True and `PROJECT_ROOT / ".data" / "hashes.json"` is NOT written by the test (mtime unchanged or file pre-verified absent via `tmp_kb_env` scope).

**AC4**: Move `_rotate_log_if_oversized` INSIDE `file_lock` in `append_wiki_log._write` — **SCORE: OK**. Clear, testable via call-order spy, bounded (1 function), semantically consistent with T2.

**AC5**: Extract `rotate_if_oversized(path, max_bytes, archive_stem_prefix)` public helper — **SCORE: OK**. Clear helper contract; D1 Option A placement confirmed.

**AC6**: Call-order spy test on `file_lock.__enter__` + `log_path.rename` — **SCORE: OK**. Matches cycle-17 L2 non-concurrency pattern; vacuous-test risk mitigated.

**AC7**: Wrap RMW triple with `file_lock(page_path)` in `inject_wikilinks` scalar loop — **SCORE: NEEDS-AMENDMENT** (blocking — ambiguous fast-path + TOCTOU). Current text says "Pages that get no modification (no match, already-linked, self) MUST NOT acquire the lock (fast-path)" but the code reads the file BEFORE it can know "no match". A pre-lock cheap read decides "does title regex match the body?" but the final decision to write depends on a post-lock re-read to avoid TOCTOU. Proposed text:

> **AC7**: In the scalar `inject_wikilinks` loop body (linker.py:203-263), keep the existing pre-lock cheap read + no-match / already-linked / self fast-paths (lines 207-237). When the cheap read indicates a modification is warranted, wrap the write path in `with file_lock(page_path):` as follows — (1) acquire lock, (2) RE-READ `page_path.read_text` under lock, (3) re-run the frontmatter/body split + existing-link guard + code-block mask + pattern search (defensive; detects concurrent injector winning the race), (4) if still a match, `atomic_text_write`, (5) release lock. Skipped pages (no match, already-linked, self) MUST NOT acquire the lock. The re-read under lock is mandatory — without it, the lock serializes two equally-stale writes. Write regression test asserts (a) zero lock acquisitions on no-match pages and (b) exactly one lock acquisition per modified page.

**AC8**: Regression test — **SCORE: NEEDS-AMENDMENT** (follows AC7 amendment). Proposed text:

> **AC8**: Regression test `tests/test_cycle18_linker_lock.py::test_inject_wikilinks_per_page_lock` asserts via a call-order spy on `file_lock` + `read_text` + `atomic_text_write` that the per-modified-page sequence is `read_text (pre-lock) → file_lock.__enter__ → read_text (under lock) → atomic_text_write → file_lock.__exit__`. Also asserts no-match page acquires ZERO locks and performs exactly one `read_text` call (pre-lock cheap read). Plus a TOCTOU scenario: when the under-lock re-read shows a prior injector has already linked the page, the second injector MUST skip `atomic_text_write` (no double-inject).

**AC9**: Generate `request_id = uuid.uuid4().hex[:16]` at `ingest_source` entry — **SCORE: OK**. Clear, testable, bounded, D5 Option A rationale sound.

**AC10**: Prefix `append_wiki_log` calls with `[req={request_id}]` on caller side — **SCORE: OK**. Clear, testable via log-line regex, no signature drift, no T9 injection risk (hex-only prefix).

**AC11**: `_emit_ingest_jsonl` helper + 4 call sites — **SCORE: NEEDS-AMENDMENT** (blocking — missing failure insertion point). `ingest_source` has no outer `try/except`; raise paths on lines 857, 873, 885, 895, and downstream (`_write_wiki_page` raises, `_update_index_batch` never raises but `append_wiki_log` does retry-and-raise). D2 Option C inline calls cannot fire `stage="failure"` without a new try/finally wrapper. Proposed text:

> **AC11**: Add `_emit_ingest_jsonl(stage, request_id, source_ref, source_hash, outcome)` that appends one JSON object per line to `<PROJECT_ROOT>/.data/ingest_log.jsonl`. Writer mechanics: `file_lock(jsonl_path)` + `open("a", encoding="utf-8", newline="\n")` + `f.write(json.dumps(row, ensure_ascii=False) + "\n")` + `f.flush()` + `os.fsync(f.fileno())`. MUST NOT use `atomic_text_write`. Fields: `ts` (ISO-8601 UTC Z-suffix), `request_id`, `source_ref`, `source_hash`, `stage` (enum `start` | `duplicate_skip` | `success` | `failure`), `outcome` (dict with counts + redacted `error_summary`). **Insertion points in `ingest_source`**: emit `stage="start"` immediately after `request_id` is generated (after line 855); emit `stage="duplicate_skip"` at the duplicate return block (line 933-946); wrap the remainder of the function body in `try: ... except BaseException as exc: _emit_ingest_jsonl("failure", ..., outcome={"error_summary": sanitize_text(str(exc))}); raise` (the try-except sits inside `ingest_source`, NOT in `_emit_ingest_jsonl`); emit `stage="success"` just before `return result` at the tail (line 1187). Best-effort swallow (`try/except OSError` within the helper) prevents JSONL write failure from masking the real ingest outcome.

**AC12**: `rotate_if_oversized` INSIDE `file_lock(jsonl_path)` — **SCORE: OK**. Correct symmetry with AC4; threat-model T6 residual risk noted.

**AC13**: `sanitize_text(s: str) -> str` in `kb.utils.sanitize`; `sanitize_error_text` calls it internally — **SCORE: OK**. Correctly extracts shared regex. The brainstorm D3 Option A pseudocode keeps the substitution order (exception-attrs first, then regex sub) preserved — critical per cycle-10 L2. Minor note: the current `sanitize_error_text` at line 42-50 also handles `filename`/`filename2` exception attrs. The new `sanitize_text(s)` is string-only; it must NOT try to replicate the exception-attr handling. D3 pseudocode is correct.

**AC14**: Extract `_write_index_files(wiki_dir, created_entries, source_ref)` helper — **SCORE: OK**. Clear contract ("sources before index"). Threat-model T10 correctly flags the symbol-name drift to use `_update_sources_mapping` + `_update_index_batch` (real names). AC14 text itself uses the real names — no amendment needed there.

**AC15**: Regression tests in `test_cycle18_ingest_observability.py` — **SCORE: NEEDS-AMENDMENT** (symbol-name drift). The bullet `test_write_index_files_ordering — spy on _update_sources_md + _update_index_md` uses fictional symbol names. Proposed text:

> - `test_write_index_files_ordering` — spy on `kb.ingest.pipeline._update_sources_mapping` + `kb.ingest.pipeline._update_index_batch`; assert sources mapping called BEFORE index batch; both called exactly once per `_write_index_files(...)` invocation.

Also, the 6 sub-tests are reasonable but the `test_jsonl_rotation` scenario needs a size-threshold hint: "pre-populate `.data/ingest_log.jsonl` with >500_000 bytes of synthetic content before the test call".

**AC16**: 3-scenario E2E test — **SCORE: NEEDS-AMENDMENT** (minor — mock boundary specificity). Current text says "Mock ONLY the boundary LLM calls (`kb.utils.llm.call_llm`, `kb.utils.llm.call_llm_json`, `kb.query.engine.call_llm`)". Per Q7 self-check, the `kb.query.engine.call_llm` patch may be a function-local import (grep confirms it IS imported at `engine` module top-level — OK), but the threat model deserves an explicit invariant: no patch should rely on a deferred import. Proposed:

> - Mock LLM boundaries at `kb.utils.llm.call_llm` AND `kb.utils.llm.call_llm_json`. The test MUST verify (via a `raise AssertionError` stub) that mocked functions are reached — a test scenario that triggers zero LLM calls would pass silently under mock and miss the integration intent. Each scenario asserts at least one stub invocation.

---

## Design-decision verdicts

| Decision | Verdict | Rationale |
|---|---|---|
| **D1** — `rotate_if_oversized` in `kb.utils.wiki_log` | **AGREE** (Option A) | YAGNI; one caller outside wiki_log; new module = 3 edits vs. 1. Name carries mild drift but `kb.utils.wiki_log` already has generic helpers (`_escape_markdown_prefix`). |
| **D2** — JSONL integration pattern (hybrid Option C) | **DISAGREE — prefer Option B (context manager)** | Option C cannot guarantee `stage="failure"` emission under propagating exceptions without an additional try/finally wrapper in `ingest_source`, which AC11 does not currently specify. Option B's `__exit__` guarantees paired start/end emission and consolidates the `try/except` boundary. The "~40 lines of wrapper" cost buys compile-time correctness of the "every start has an end" invariant. If Option C is kept, AC11 MUST be amended with the explicit try/except wrapper (see AC11 amendment above). |
| **D3** — `sanitize_text` shape (Option A, shared regex) | **AGREE** (Option A) | DRY; preserves substitution order. Behaviour-preserving refactor. Test must pin the order (cycle-10 L2). |
| **D4** — `inject_wikilinks` per-page lock (Option A) | **AGREE with amendment** | Per-page lock is correct, but AC7 fast-path must re-read under lock (TOCTOU). See AC7 amendment. |
| **D5** — `request_id` local in `ingest_source` (Option A) | **AGREE** | YAGNI. Caller-passing can be added later without API break. |
| **D6** — fixture-only HASH_MANIFEST patch (Option A) | **AGREE** | `feedback_batch_by_file` rule. Migration is cycle-19 cleanup. |
| **D7** — integration test module-attr patches (Option A) | **AGREE** | Matches existing pattern; SDK-boundary patching (Option B) is brittle across versions. |

---

## Open-question pre-answers

**Q1** (D1 name-drift): Keep `rotate_if_oversized` in `kb.utils.wiki_log`. Rationale: one out-of-module caller is insufficient to justify a new module; `kb.utils.wiki_log` already hosts other general helpers.

**Q2** (D2 inline vs context manager): **Option B — context manager**. Overrides D2 recommendation. Rationale: guarantees paired emission on exception; consolidates failure-path try/except in one place; avoids the AC11 amendment complexity. If Option C is retained, AC11 needs the explicit try/except wrapper.

**Q3** (D3 `*paths` passthrough): No — `sanitize_text` should be string-only. `sanitize_error_text` handles the Path substitution before calling `sanitize_text`. Rationale: string-only helper is easier to reason about; reusability for non-exception callers (JSONL writer) doesn't need Path semantics.

**Q4** (D4 lock scope): Lock MUST encompass the RE-READ + frontmatter split + pattern search + `atomic_text_write` (the full RMW under lock). The pre-lock cheap read gates the fast-path; the under-lock re-read is the authoritative decision. See AC7 amendment.

**Q5** (D5 local vs kwarg): No objection — local-only. Confirmed.

**Q6** (D6 lint check): Rely on AC3. Rationale: a lint check for "test uses tmp_kb_env + explicit HASH_MANIFEST patch" is defense-in-depth with ambiguous pass/fail (how does the lint know the patch is redundant?). Add it as a cycle-19 cleanup pass that also removes the 20 redundant patches.

**Q7** (D7 boundary completeness): Yes — confirm via test that mocked functions are reached (assert stub invocation count ≥ 1 per scenario). See AC16 amendment.

**Q8** (JSONL disk-full handling): Wrap `_emit_ingest_jsonl` body in `try/except OSError: logger.warning(...)`. Do NOT let JSONL write failure propagate — it would mask the real ingest result. The existing `pipeline.py:1097` `OSError` swallow for `wiki/log.md` is precedent.

**Q9** (fsync per-append vs rotation-only): fsync per-append. Rationale: cycle 18 JSONL is low-volume (1 row per ingest, ~300 bytes). Write amplification is negligible at human-scale ingest rates; crash durability matters more for audit.

**Q10** (`_write_index_files` return value): No return value. Rationale: existing `_update_sources_mapping` + `_update_index_batch` are void; caller relies on `logger.warning` pass-through. Adding `(bool, bool)` tuple increases surface area for one non-critical observability gain.

**Q11** (refine_page + query mtime cache): `query_wiki` uses `scan_wiki_pages` which stats mtime fresh on each call (no cache at that layer). `refine_page` writes via `atomic_text_write` which updates mtime. No explicit sleep needed in AC16 scenario (b). Recommend adding an explicit assertion that `query_wiki`'s returned `context_pages` contains the refined page with the new content.

**Q12** (AC4 rotation-lock can ship alone?): No — ship AC4 and AC11-AC13 together as a paired contract. Rationale: AC12 reuses the rotate-in-lock pattern; shipping AC4 in isolation creates an inconsistency window where the JSONL rotation would be modeled on the OLD wiki-log behavior if AC11-AC13 slipped.

---

## Red-flag scan

1. **Dead double-call of pure helper (cycle-15 L1)**: **CLEAR**. No `_partition_pages`-style dead call found in the design.

2. **Loop-variable mutation inside enumerate (cycle-14 L3)**: **CLEAR**. No enumerate patterns in the AC body.

3. **Inspect-source / Path.read_text / splitlines source-scan tests (cycle-11 L2, cycle-16 L2)**: **CLEAR**. All regression tests in AC6/AC8/AC15/AC16 use behavioural assertions (call-order spy, file-content inspection of ACTUAL output paths), not source-scan. Confirmed by reading AC6 ("spy on `file_lock.__enter__` + `log_path.rename`") and AC8 ("spy on `file_lock` + `read_text` + `atomic_text_write`").

4. **If-gated regression assertion (cycle-9 L1)**: **CLEAR**. AC3/AC6/AC8/AC15 assertions are unconditional.

5. **Dual-mechanism collapse (cycle-9 L2)**: **FLAG — MINOR**. AC1+AC2 are two separate ACs for one concept ("add HASH_MANIFEST to fixture"). This is actually correct — tuple membership and the `monkeypatch.setattr` action are independent mechanisms with independent failure modes. OK as split.

6. **Test accommodation in production code (cycle-10 L1)**: **CLEAR**. No test-only hook in production paths. `request_id` is a genuine production feature.

7. **Helper orphan (cycle-3 L4)**: **FLAG — MINOR**. AC5's `rotate_if_oversized` public helper is consumed by both `_rotate_log_if_oversized` (via thin wrapper) and AC11's `_emit_ingest_jsonl`. Both call sites are explicit. NOT orphan. Confirmed.

8. **Signature drift without caller-grep (cycle-7 M3)**: **FLAG — minor**. AC14's `_write_index_files` is a NEW function (no drift on existing callers). However, AC11's addition of `request_id` local to `ingest_source` is NOT a signature drift (kwarg-free per D5). AC10's caller-side prefix does NOT change `append_wiki_log` signature. Confirmed safe. Threat-model T10 already flagged `_update_sources_md`/`_update_index_md` drift in AC15.

9. **Frontmatter sort_keys=False missing**: **N/A**. Cycle 18 does not touch frontmatter.

10. **Multi-file task bundling (cycle-4 plan-gate)**: **CLEAR**. Each AC is single-file scoped. AC15's 6 sub-tests all land in one file. AC16 is one new file. The 5-file total aligns with `feedback_batch_by_file`.

**Additional red flag found in close reading**:

11. **MISSING stage="failure" emission path (new flag)**: `ingest_source` has no outer try/except. AC11 inline emission (D2 Option C) cannot fire on exception. See AC11 amendment and Q2 recommendation.

12. **AC7 TOCTOU gap (new flag)**: Fast-path pre-lock read allows two injectors to decide-and-write stale state. See AC7 amendment — re-read under lock is mandatory.

13. **Order-of-operations ambiguity in AC11 insertion (new flag)**: `_check_and_reserve_manifest` at line 933 MUTATES the manifest BEFORE `stage="start"` is emitted in the current spec. Recommend: emit `stage="start"` at line 856 (after `source_path = Path(source_path).resolve()` succeeds) so the JSONL records an attempt even if the manifest reservation path raises. See AC11 amendment.

---

## Summary

**2 blockers, 3 majors, 2 minors.**

**Blockers** (must resolve at Step 5):
- **B1 (AC7)**: Fast-path TOCTOU — lock contract must re-read under lock. Amendment provided.
- **B2 (AC11)**: `stage="failure"` has no emission insertion point in `ingest_source`. Either adopt D2 Option B (context manager, recommended per Q2) or amend AC11 with explicit try/except wrapper.

**Majors** (resolve at Step 5):
- **M1 (AC3)**: Vague "kb_compile_scan-style code path writes there". Amendment provided.
- **M2 (AC15)**: Symbol-name drift — `_update_sources_md` / `_update_index_md` → `_update_sources_mapping` / `_update_index_batch`. Amendment provided (also in threat model §9 AI-1).
- **M3 (AC16)**: Mock-reach invariant missing. Amendment provided.

**Minors** (can defer):
- **m1 (AC8)**: Should include TOCTOU scenario test (follows AC7 amendment).
- **m2 (Q9)**: fsync per-append is recommended but threshold for changing policy not specified in cycle 18.

**R3 mandatory at Step 14**: confirmed (new FS write surface + vacuous-test regression risk + new security enforcement point — three of four triggers fire).

**Recommendation for Step 5 decision gate:** adopt D2 Option B (context manager) to close B2 without adding an AC11 try/except clause, apply the AC3/AC7/AC15/AC16 amendments, and proceed to Step 4 planning. Re-verify the threat model's T10 action-item resolution once AC14/AC15 text is updated.
