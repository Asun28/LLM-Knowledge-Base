# Cycle 18 — Brainstorming (Step 3)

**Date:** 2026-04-20
**Mode:** autonomous (feature-dev zero-gate per `feedback_auto_approve`)
**Companion:** `2026-04-20-cycle18-requirements.md`, `2026-04-20-cycle18-threat-model.md`

## Scope recap

16 ACs across 5 files. Major design decisions to brainstorm:

1. Where does the generic `rotate_if_oversized` helper live?
2. How does `_emit_ingest_jsonl` get called — inline at 4 call sites or via a wrapper?
3. `sanitize_text` string-form extraction strategy.
4. `inject_wikilinks` lock granularity (per-page vs wiki-wide).
5. `request_id` generation location.
6. `tmp_kb_env HASH_MANIFEST` patch strategy (fixture-only vs migration of 10 test files).
7. Integration test mock boundary (module attribute vs boundary call).

Per decision, enumerate 2-3 approaches with trade-offs. The recommended option is promoted to the "Open Questions" list for Step 5 decision-gate resolution.

---

## D1 — Location of `rotate_if_oversized` helper

**Context:** AC5 + AC12 share a rotation helper. `kb.utils.wiki_log.py` currently owns `_rotate_log_if_oversized`.

**Option A — Keep in `kb.utils.wiki_log.py`.** Rename `_rotate_log_if_oversized` to `rotate_if_oversized(path, max_bytes, archive_stem_prefix)`; the existing private function becomes a one-line wrapper. `pipeline.py` imports `from kb.utils.wiki_log import rotate_if_oversized`.
- Pros: smallest diff (~10 lines); no new module; test file `test_cycle18_wiki_log.py` naturally covers both call-sites.
- Cons: `wiki_log` module name now carries a function whose use extends beyond wiki_log.md; mild name-drift but acceptable.

**Option B — New `kb.utils.rotation.py` module.** Extract `rotate_if_oversized` to a fresh sibling; both `wiki_log.py` and `pipeline.py` import from it. Move `LOG_SIZE_WARNING_BYTES` → `kb.config.LOG_SIZE_WARNING_BYTES` for global sharing.
- Pros: clean separation; no name drift.
- Cons: new module + new config constant = 3 file-level edits for one helper; adds import cycle risk if `wiki_log` → `rotation` → ... ; violates YAGNI for one caller.

**Option C — Inline rotation logic at each call site.** No helper; duplicate ~15 lines of rotation logic in `wiki_log.py` and `pipeline.py`.
- Pros: no abstraction cost.
- Cons: duplicate archive-ordinal logic; cycle-4 L4 lesson against duplication; any future rotation change needs two edits.

**Recommendation:** Option A. Minimal diff, no new module, single test file coverage. Open question for Step 5: is the name `rotate_if_oversized` acceptable at `kb.utils.wiki_log` scope, or does the naming mismatch warrant Option B?

---

## D2 — `_emit_ingest_jsonl` integration pattern

**Context:** AC11 requires JSONL emission at 4 stages: `start`, `duplicate_skip`, `success`, `failure`. `ingest_source` body is ~280 lines.

**Option A — Inline calls at each stage.** Four `_emit_ingest_jsonl(...)` calls inside `ingest_source` body, one per stage.
- Pros: explicit; reads like a narrative; easy to grep for all emission points.
- Cons: 4 invocations means 4 places to forget to pass `request_id` correctly; duplicate field-marshalling boilerplate.

**Option B — Context-manager wrapper.** `with _IngestLog(source_ref, source_hash, request_id) as log:` at function top; `log.duplicate_skip()`, `log.success(**counts)`, `log.failure(err)` methods. Emits `start` on `__enter__`, records but doesn't emit on intermediate calls, emits final row on `__exit__`.
- Pros: guarantees paired `start`/`end` emission; one place to forget field marshalling; reads cleanly.
- Cons: more code (~40 lines of wrapper); harder for reviewers to audit emission invariants; must still be called at the right points.

**Option C — Hybrid.** Helper `_emit_ingest_jsonl(stage, request_id, source_ref, source_hash, counts, error_summary)` plus inline calls; no context manager.
- Pros: reuses Option A's clarity; field marshalling centralized in the helper.
- Cons: still 4 call sites but each is a one-liner.

**Recommendation:** Option C. Centralizes field allowlist in one helper (so redaction/schema live in one place) while keeping the call graph explicit. Open question for Step 5: any objection to inline calls over context manager?

---

## D3 — `sanitize_text` string-form extraction strategy

**Context:** threat-model action item 2 requires a `sanitize_text(s: str) -> str` sibling to `sanitize_error_text(exc, *paths)` that shares `_ABS_PATH_PATTERNS`.

**Option A — Add `sanitize_text` and refactor `sanitize_error_text` to call it.**
```python
def sanitize_text(s: str, *paths: Path | None) -> str:
    for pattern in _ABS_PATH_PATTERNS:
        s = pattern.sub("<path>", s)
    for p in paths:
        if p:
            s = s.replace(str(p.resolve()), f"<{p.name}>")
    return s

def sanitize_error_text(exc: BaseException, *paths: Path | None) -> str:
    msg = str(exc)
    return sanitize_text(msg, *paths)
```
- Pros: DRY; tests both; no behaviour change for existing callers.
- Cons: tiny refactor of `sanitize_error_text`'s body (currently ~20 lines) — must preserve the original substitution sequence (`cycle-10 L1` warning on order-reversal).

**Option B — Add `sanitize_text` as a pure duplicate; leave `sanitize_error_text` untouched.**
- Pros: zero refactor; lowest regression risk.
- Cons: two copies of `_ABS_PATH_PATTERNS` loops — a future CVE patch on one misses the other; violates DRY.

**Recommendation:** Option A. `sanitize_error_text`'s ordered operations (exception-attr sweep → string sub) are preserved — `sanitize_text` takes only the string step. Must write a test asserting the substitution order inside `sanitize_error_text` (exception-attrs first, then regex — cycle-10 L2 lesson). Open question for Step 5: is the `*paths` kwarg passthrough necessary for `sanitize_text`, or is it exception-only?

---

## D4 — `inject_wikilinks` lock granularity

**Context:** AC7 requires per-page locks. Coarser alternative: a wiki-wide writer mutex during the inject phase.

**Option A — Per-page `file_lock(page_path)`.** One lock per page that will be modified. Fast-path skips lock for no-op pages.
- Pros: concurrent ingests on DIFFERENT pages proceed in parallel; only contention point is the exact page being dually-modified.
- Cons: 20+ lock acquire/release per ingest on large wikis (T8); lock overhead on SMB/OneDrive is visible.

**Option B — Wiki-wide writer mutex.** Single `file_lock(wiki_dir / ".inject.lock")` held for the entire `inject_wikilinks` call.
- Pros: simpler implementation; guaranteed ordering; matches `ingest/pipeline.py` coarse-lock precedent (HASH_MANIFEST is a wiki-wide lock).
- Cons: serializes two concurrent ingests even if they target disjoint pages; bad for future batch-ingest use case.

**Option C — Per-page lock, deferred to AC21 batch form.** Cycle 18 ships NO lock; cycle 19 AC21 lands the batch form with per-page locks bundled.
- Pros: no cycle-18 overhead.
- Cons: leaves T3 open for another cycle; goes against cycle-17 Q12 directive (defer scalar lock to cycle 18).

**Recommendation:** Option A. Aligns with the existing per-page `atomic_text_write` contract and the cycle-17 Q12 directive. Fast-path requirement keeps the 5k-page-wiki cost bounded. Open question for Step 5: should the lock encompass `_unmask_code_blocks` + the final `new_body != original_body` check (yes — the comparison must see the post-lock read), or can those happen outside?

---

## D5 — `request_id` generation location

**Context:** AC9 requires a 16-hex request_id at `ingest_source` entry.

**Option A — Generate at top of `ingest_source`.** Single line `request_id = uuid.uuid4().hex[:16]` after arg normalization.
- Pros: localized; easy to grep; threads through the body as a plain local variable.
- Cons: can't be overridden by caller (e.g., a future CLI flag that wants to pre-allocate an ID for receipt-style tracking).

**Option B — Add `request_id: str | None = None` kwarg to `ingest_source`.** Caller can pass an externally-allocated ID; `None` → `uuid.uuid4().hex[:16]`.
- Pros: future-proofs for receipt-style workflow.
- Cons: YAGNI; signature change; no caller today needs external allocation.

**Recommendation:** Option A. Per `feedback_batch_by_file` and YAGNI. If cycle 19 adds receipt support, add the kwarg then. Open question for Step 5: none.

---

## D6 — `tmp_kb_env HASH_MANIFEST` patch strategy

**Context:** 20 sites across 10 test files currently patch `HASH_MANIFEST` themselves. AC1/AC2 add fixture-level patching.

**Option A — Add fixture patch only; leave existing 20 sites untouched.** Additive-compatible: existing explicit patches are a no-op redirect to the same tmp path.
- Pros: zero risk to existing tests; smallest diff.
- Cons: 20 orphaned patches in the codebase; cycle-19 cleanup.

**Option B — Add fixture patch AND migrate all 20 sites.** Remove per-test `monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", ...)` calls.
- Pros: clean codebase; tests rely on the fixture contract.
- Cons: 20 file edits; violates batch-by-file (migrates across 10 test files in one cycle); risks signal-loss on the tests.

**Option C — Fixture patch + migrate only the 2 test files that exercise cycle-18 new code paths.** Minimal migration on the cycle-18 testing surface only.
- Pros: proves the fixture works on live code; bounded scope.
- Cons: still 2-file cross-cutting; slight inconsistency.

**Recommendation:** Option A. `feedback_batch_by_file` says group-by-file, not sweep-by-concept. Migration is cycle-19's job. Open question for Step 5: how do we prevent regressions — is AC3's single regression test sufficient, or do we need a lint check that flags "test uses `tmp_kb_env` AND explicitly patches `HASH_MANIFEST`"?

---

## D7 — Integration test mock boundary

**Context:** AC16 requires mocking LLM calls. The import graph has `call_llm` imported at module-level in several places.

**Option A — Patch `kb.utils.llm.call_llm` and `kb.utils.llm.call_llm_json` + `kb.query.engine.call_llm` in a single `monkeypatch.setattr` loop.** Three attribute patches.
- Pros: matches current test pattern; simple.
- Cons: per cycle-17 L1, function-local imports bypass module-attribute patches. Any `call_llm` imported function-locally in `kb.query.engine` would bypass.

**Option B — Replace `anthropic.Anthropic.messages.create` stub.** Low-level, single-boundary.
- Pros: only one patch; catches all code paths; matches threat-model boundary intent.
- Cons: brittle across SDK versions; `call_llm` has retry logic that would still execute and need shaping.

**Option C — Use `call_llm_json`'s forced tool_use pattern at the `Anthropic().messages.create(tools=..., tool_choice=...)` level via `anthropic.Anthropic.messages.create` monkeypatch, but only for this test.** One patch, targeted.

**Recommendation:** Option A. It's consistent with existing test patterns; the cycle-17 L1 risk applies to DEFERRING imports, not to tests picking a boundary to patch. A function-local `call_llm` import would still resolve to `kb.utils.llm.call_llm`, which is the patched symbol. Open question for Step 5: do we need to assert that AC16's 3-scenario test imports `call_llm` at the same sites `ingest_source` and `query_wiki` do? (Self-check.)

---

## Open questions consolidated

Moved into a single list for Step 5 decision-gate input:

- **Q1** (D1): `rotate_if_oversized` at `kb.utils.wiki_log` vs new `kb.utils.rotation` module?
- **Q2** (D2): Inline helper vs context-manager wrapper for JSONL emission?
- **Q3** (D3): Should `sanitize_text` accept the `*paths` kwarg passthrough, or only exception form does?
- **Q4** (D4): Should the per-page lock in `inject_wikilinks` encompass the full RMW including final comparison, or only the write?
- **Q5** (D5): Any objection to generating `request_id` locally inside `ingest_source` vs adding a kwarg? *(Recommended: no objection, local-only.)*
- **Q6** (D6): Add a lint check for "test uses `tmp_kb_env` + explicit HASH_MANIFEST patch" as defence-in-depth, or rely on AC3?
- **Q7** (D7): Confirm `call_llm` / `call_llm_json` module-attribute patches reach all `ingest_source` + `query_wiki` paths in AC16.
- **Q8** (new from threat-model §6): `_emit_ingest_jsonl(stage="failure")` best-effort when disk full — does the existing `OSError` swallow at `pipeline.py:1097` already cover the JSONL emission failure, or do we need an explicit try/except in the helper?
- **Q9** (new from threat-model T7): Should `.data/ingest_log.jsonl` writer emit `fsync` on EVERY append, or only on rotation + explicit flush on process exit? (fsync per-append = SSD write amplification.)
- **Q10** (new): Does `_write_index_files` need a return value (e.g., `(sources_ok, index_ok)` booleans) for caller observability, or is `logger.warning` pass-through sufficient?
- **Q11** (new): AC16 scenario (b) "ingest → refine → re-query" — does `refine_page` invalidate the wiki-page mtime cache that `query_wiki` uses, or does the test need to sleep / bump mtime explicitly?
- **Q12** (new): Cycle-17 Q11 deferral also mentioned pairing `wiki_log.py` rotation-lock fix with `.data/ingest_log.jsonl` introduction — are we committing to both in cycle 18 as a paired contract, or can AC4 (rotation-lock) ship alone if AC11-AC13 are deferred?

Total: 12 open questions. Per cycle-17 L4, R3 is mandatory IF design gate resolves ≥10 (currently YES — 12 questions). Combined with cycle-17 L4 triggers (a), (b), (c), R3 is confirmed mandatory.

---

## Recommended approaches summary (for Step 4 input)

| Decision | Pick | Rationale |
|---|---|---|
| D1 rotation helper location | Option A — `kb.utils.wiki_log` | smallest diff |
| D2 JSONL integration | Option C — hybrid helper + inline calls | explicit + DRY |
| D3 sanitize_text shape | Option A — refactor + share regex | DRY, preserve order |
| D4 lock granularity | Option A — per-page + fast-path | concurrent-ingest-friendly |
| D5 request_id location | Option A — local in `ingest_source` | YAGNI |
| D6 fixture migration | Option A — fixture-only, leave explicit patches | batch-by-file rule |
| D7 integration-test boundary | Option A — module-attr patches | matches existing pattern |
