# Cycle 18 — Step 5 Design Decision Gate

**Date:** 2026-04-20
**Gate:** feature-dev Step 5
**Scope:** 16 ACs across 5 files; 21 open questions consolidated from brainstorm + R1 Opus + R2 Codex evaluations.

## Verdict

APPROVE-WITH-AMENDMENTS

Rationale: R1 surfaced 2 blockers (AC7 TOCTOU, AC11 failure-emission insertion) and R2 surfaced 5 blockers (JSONL fsync policy, `_write_index_files` per-call try/except, AC7 lock scope, UNC regex, rotation-in-lock symmetry). All are addressable via inline AC amendments; no AC is deferred. Total: 9 ACs receive text updates; 7 ACs unchanged.

## Decisions (Q1-Q21)

### Q1: `rotate_if_oversized` location

#### Options
- Option A: Keep in `kb.utils.wiki_log` as a public helper; `_rotate_log_if_oversized` becomes a thin wrapper.
- Option B: New `kb.utils.rotation` module.
- Option C: Inline rotation at both call sites.

#### Analysis
Option A produces the smallest diff (~10 lines): rename the existing private helper to a public generic helper with the three parameters (path, max_bytes, archive_stem_prefix), and the private wrapper survives as a one-liner that passes `LOG_SIZE_WARNING_BYTES` and `"log"` as the stem prefix. No new module, no new config constant, no import cycle risk. The brainstorm, R1, and R2 all converge on this. The counter-argument is that the `kb.utils.wiki_log` module name carries a helper whose scope now reaches beyond wiki-log — a mild name-drift but acceptable because `kb.utils.wiki_log` already hosts generic helpers (`_escape_markdown_prefix`). The audit-log (`logger.info("Rotating ...")` at `wiki_log.py:40-45`) belongs inside the generic helper per R2 MINOR — it is a property of rotation, and AC12 needs the same pre-rename audit chain for `.data/ingest_log.jsonl`.

Option B is YAGNI with one out-of-module caller. Creating `kb.utils.rotation` + moving `LOG_SIZE_WARNING_BYTES` to `kb.config` is 3 edits for one helper, plus it splits the rotation concern from its primary consumer. Option C re-duplicates the archive-ordinal loop at `wiki_log.py:35-39` in `pipeline.py`, which is exactly the pattern cycle-4 L4 rejects. The rotation helper is too small to deserve a module, but too non-trivial to duplicate.

#### Decide
Option A

#### Rationale
Smallest diff, single test file covers both call sites, no import-cycle risk. The audit `logger.info` moves INTO the generic helper (R2 MINOR) so both call sites inherit the audit chain.

#### Confidence
High

---

### Q2: JSONL integration pattern

#### Options
- Option A: Inline `_emit_ingest_jsonl(...)` calls at 4 stages.
- Option B: Context manager wrapper (`with _IngestLog(...) as log:`) — R1 recommends.
- Option C: Helper + inline calls + explicit try/except in `ingest_source` (brainstorm recommended).

#### Analysis
The core design invariant is that `stage="failure"` must fire even when the ingest body raises an exception. `ingest_source` has no outer try/except today — exceptions propagate from `raise ValueError` at lines 857/873/885/895 and downstream helpers. Option A cannot fire on exception without adding a try/except. Option C (brainstorm) accepts that cost and centralizes the field marshalling in a helper that is called 4 times, including once inside an explicit try/except around the body. Option B embeds the try/except in `__exit__` of a context manager. Both Option B and Option C are correct; the choice reduces to "is the try/except boundary clearer in the function body or in the context manager?"

R1 argues Option B buys compile-time correctness of the "every start has an end" invariant — the `__exit__` hook guarantees emission on exception without the reader needing to verify that every call site is inside the same try block. Option C requires reviewers to visually confirm that `_emit_ingest_jsonl(stage="start")` and all three terminal calls are inside the same try/except scope; a future refactor that moves a terminal call out of the try scope would silently regress. However, Option B adds ~40 lines of wrapper code, an `__exit__` method that must correctly distinguish success/duplicate_skip/failure (requires explicit state-tracking methods `log.success(**counts)`, `log.duplicate_skip()`, etc.), and obscures the emission sites from grep. Context managers with branching terminal states are known to be easy to misuse — if the body calls `log.success()` then raises, `__exit__` must not re-emit `stage="failure"`. This is the classic "commit vs rollback" dance and the code-review burden is meaningful.

Weighing: the KISS win for Option C is real (one helper + explicit try/except is ~15 lines total and grep-auditable), whereas Option B's invariant guarantee is paid for in wrapper complexity. Project principles "prefer positive phrasing" and "minimal formatting" favor the explicit inline pattern. The risk Option C introduces (forgetting a try/except) is mitigated by a single regression test that asserts `stage="failure"` fires on a synthetic exception — AC15 already plans to test this.

#### Decide
Option C

#### Rationale
Helper + inline calls + explicit try/except in `ingest_source`. The function body becomes: generate request_id → emit start → duplicate check (emit duplicate_skip + return) → try: (body) + emit success; except BaseException as exc: emit failure + re-raise. Four explicit, grep-able emission sites; one try/except scope; regression test pins the failure path.

#### Confidence
Medium

---

### Q3: `sanitize_text` shape

#### Options
- Option A: Extract `sanitize_text(s: str) -> str` + shared regex; `sanitize_error_text` calls it.
- Option B: Pure duplicate of the regex loop.
- Passthrough: should `sanitize_text` accept `*paths`?

#### Analysis
Option A is behaviour-preserving DRY. The existing `sanitize_error_text` ordered operations are (1) exception-attribute sweep (filename/filename2), (2) string regex sub on `str(exc)`. The extraction preserves operation (2) in `sanitize_text` and keeps (1) in `sanitize_error_text` before it calls `sanitize_text`. Cycle-10 L2 warns about order reversal; a regression test asserting the substitution order (exception-attrs first) pins this. Option B creates two copies of the regex loop; a future CVE patch on one misses the other — DRY violation.

On the `*paths` passthrough: `sanitize_error_text` accepts `*paths` to redact caller-supplied Path instances beyond what the regex catches. The JSONL writer has no Path arguments to redact (source_ref is already a relative path, source_hash is 64 hex). R1 Q3 pre-answer recommends string-only — keeps the helper conceptually simple and avoids Path semantics at the JSONL caller. If a future caller needs Path redaction, add `sanitize_text_with_paths` then.

#### Decide
Option A, string-only (no `*paths` passthrough on `sanitize_text`).

#### Rationale
DRY + preserves substitution order + string-only keeps the helper single-purpose. `sanitize_error_text` retains its `*paths` kwarg and calls `sanitize_text` internally after the exception-attribute sweep.

#### Confidence
High

---

### Q4: `inject_wikilinks` lock scope (TOCTOU)

#### Options
- Option A: Lock wraps ONLY the `atomic_text_write` call (lock-on-write).
- Option B: Lock wraps RE-READ + split + existing-link check + code-block mask + finditer + `_unmask_code_blocks` + final comparison + `atomic_text_write` (full RMW under lock).

#### Analysis
R1 and R2 BOTH flag this as blocker. The current code reads `page_path.read_text` at linker.py:211 BEFORE any lock decision. If the lock wraps only the write, two concurrent injectors can both read pre-link content, both decide to write, and the lock merely serializes the now-doomed second write — last-writer-wins preserved, no TOCTOU protection gained. The only safe contract is: (1) pre-lock cheap read decides whether to enter the lock at all (fast-path preservation for 5000-page wikis), (2) under-lock re-read is the authoritative decision, (3) re-run frontmatter split + existing-link check + code-block mask + finditer + `_unmask_code_blocks` + final body-comparison under the lock, (4) `atomic_text_write` under the lock. Without the re-read step, concurrent injectors targeting the same page produce last-writer-wins output — wikilink loss is the exact bug AC7 is meant to fix.

The fast-path (no-match pages acquire ZERO locks) is preserved because the pre-lock cheap read is idempotent: if the title pattern doesn't match, return without acquiring the lock. The under-lock re-read catches the case where the cheap read saw pre-link content but the target has been updated between the cheap read and the lock acquire. If the under-lock re-read shows already-linked or no-match, the injector skips `atomic_text_write`. The AC8 test covers this TOCTOU scenario.

On AC7a vs AC7 amendment: introducing AC7a as a sibling would split the lock contract into two ACs that must be read together. The full contract fits in one AC body if worded explicitly. Keep as AC7 amendment.

#### Decide
Option B (full RMW under lock), amend AC7 in place (no AC7a).

#### Rationale
Pre-lock cheap read gates the fast-path; under-lock re-read is the authoritative decision. Re-read + split + existing-link check + code-block mask + finditer + `_unmask_code_blocks` + final comparison + `atomic_text_write` all inside the lock. No TOCTOU window.

#### Confidence
High

---

### Q5: `request_id` location

#### Options
- Option A: Local in `ingest_source` (generate `uuid.uuid4().hex[:16]` at function entry).
- Option B: Add `request_id: str | None = None` kwarg for external allocation.

#### Analysis
YAGNI. No caller today needs external allocation. 7 runtime callers of `ingest_source` (CLI, MCP core, compiler batch, lint augment) all benefit equally from an internally-generated ID. R1 Q5 pre-answer confirms local-only. Adding a kwarg now widens the signature for a hypothetical cycle-19 receipt feature that has not been specified. If/when receipts land, add the kwarg with the existing uuid4 as the default — no breaking change.

The alternative concern is thread-safety: `uuid.uuid4()` draws from `os.urandom` which is thread-safe; two threads calling `ingest_source` concurrently each get independent IDs with 2^-64 collision probability per call. Not a real risk.

#### Decide
Option A

#### Rationale
YAGNI; single-line `request_id = uuid.uuid4().hex[:16]` at function entry. Threads through the body as a local variable.

#### Confidence
High

---

### Q6: HASH_MANIFEST fixture migration

#### Options
- Option A: Fixture-only addition; leave 20 explicit test patches in place.
- Option B: Fixture + migrate all 20 sites.
- Option C: Fixture + migrate only cycle-18 touched tests.

#### Analysis
R1 and R2 both agree on Option A. User memory `feedback_batch_by_file` explicitly rejects sweep-by-concept: the rule is "group backlog fixes by file (HIGH+MED+LOW together), not by severity. Target 30-40 items across ~15-20 files per cycle." Migrating 20 sites across 10 test files in cycle 18 violates the batch-by-file guardrail and creates signal-loss risk: a test that currently asserts `HASH_MANIFEST == tmp_path / ...` as its primary correctness check loses that assertion if the fixture patch silently takes over. The additive-compatible approach keeps existing explicit patches valid (both patches resolve to the same tmp path), and a cycle-19 cleanup PR can migrate in one dedicated pass with the caller-grep discipline required by `feedback_signature_drift_verify`.

R2 notes a subtle edge case: the mirror-rebind loop at conftest.py:227 only rebinds `kb.*` modules. A `tests.*` module that top-imports `from kb.compile.compiler import HASH_MANIFEST as _hm` BEFORE `tmp_kb_env` runs holds the pre-patch value. Grep confirms no current test module does this (all patches are via `monkeypatch.setattr` or `patch()`), but this is a residual risk worth documenting in AC3.

#### Decide
Option A

#### Rationale
Fixture-level patch + leave 20 explicit patches; honor `feedback_batch_by_file`. Cycle-19 cleanup removes the redundant explicit patches.

#### Confidence
High

---

### Q7: AC16 integration-test mock boundary

#### Options
- Option A: Module-attribute patches on `kb.utils.llm.call_llm`, `kb.utils.llm.call_llm_json`, `kb.query.engine.call_llm`.
- Option B: Patch `anthropic.Anthropic.messages.create` at the SDK boundary.

#### Analysis
R1 and R2 both support Option A. The cycle-17 L1 risk (function-local imports bypass attribute patches) applies to deferred imports; grep confirms `kb.query.engine` imports `call_llm` at module top-level, so module-attribute patches reach it. Option B is brittle across SDK versions (Anthropic SDK refactors) and requires shaping the retry logic in `call_llm` that would still execute. Option A matches existing test patterns.

R2 MAJOR flags the vacuous-test defense: a test scenario that triggers zero LLM calls would pass silently under mock and miss the integration intent. The mock must track invocation count and each scenario must assert `>= 1` stub hit. This is the only way to distinguish "integration path exercised" from "integration path accidentally bypassed." Also, scenario (c) must assert wikilink-injection behavior specifically (not just that a query returns non-empty) — otherwise the scenario degenerates to scenario (a) under incidental page creation.

#### Decide
Option A + assert stub invocation count `>= 1` per scenario + explicit wikilink-inject assertion in scenario (c).

#### Rationale
Matches existing patterns; vacuous-test defense is explicit; wikilink-inject assertion prevents scenario-degeneracy.

#### Confidence
High

---

### Q8: JSONL disk-full / fsync failure policy

#### Options
- Option A: Best-effort — catch `OSError` in `_emit_ingest_jsonl`, log WARNING, do NOT mask ingest outcome.
- Option B: Hard-fail — let OSError propagate from the telemetry path.

#### Analysis
JSONL telemetry failure must never mask the real ingest outcome. If disk is full and the audit log cannot be written, the ingest itself may or may not have succeeded — the operator needs the ingest result (success/failure/duplicate) to decide recovery. Masking with an OSError from the telemetry path turns a successful ingest into an apparent failure. The existing `pipeline.py:1097` `OSError` swallow for `wiki/log.md` is precedent. R1 Q8 and R2 BLOCKER both converge on Option A.

The cost of Option A: audit trail gaps on disk-full. The operator sees a WARNING in logs ("Failed to write ingest_log.jsonl: ...") but the JSONL is missing that row. This is acceptable because (1) the situation is rare and recoverable, (2) the ingest completed and left its other traces (wiki/log.md, affected pages, hash manifest), (3) the JSONL is a supplementary audit trail, not the source of truth. Hard-fail would invert this trade-off and fail ingests that actually succeeded.

On `stage="failure"` telemetry specifically: if the body raised and then the `stage="failure"` emission also raises, we must swallow the telemetry error (NOT the original exception). The explicit try/except in `ingest_source` re-raises the original `exc` after the best-effort emission.

#### Decide
Option A

#### Rationale
Best-effort from `ingest_source`; `_emit_ingest_jsonl` wraps its body in `try/except OSError: logger.warning(...)`. For `stage="failure"`, the original exception is the source of truth — telemetry errors are swallowed, original raises.

#### Confidence
High

---

### Q9: fsync per-append vs rotation-only

#### Options
- Option A: fsync every JSONL append (strict durability).
- Option B: fsync on rotation only; flush-only per append.

#### Analysis
Cycle 18 JSONL is low-volume (one row per ingest, ~300 bytes). A typical daily ingest rate is 10-50 sources; fsync write amplification is negligible at this scale. The audit trail's primary use is crash recovery — a crash between `write()` and fsync can lose the last N rows; fsync per append bounds this loss to at most one row. Option B would lose all un-rotated rows since the last rotation event on crash, which defeats the audit-trail purpose.

R1 Q9 and R2 MAJOR both recommend Option A. R2 notes adding a module constant or comment naming the durability policy ("strict: fsync every append") so a future cycle can downgrade to relaxed mode with evidence that SLO is impacted. Write-amplification cost is measurable on SSD (~1ms per fsync) but human-scale ingest rates make this invisible.

#### Decide
Option A (fsync per append)

#### Rationale
Strict durability for the audit trail; low-volume write pattern makes write-amplification cost negligible. Module constant `INGEST_JSONL_DURABILITY = "strict"` (comment-only) documents the policy.

#### Confidence
High

---

### Q10: `_write_index_files` per-call try/except

#### Options
- Option A: Helper wraps both calls in a SHARED try/except (fail-fast; if sources fails, skip index).
- Option B: Each call has INDEPENDENT try/except; index attempted even if sources fails (preserves existing warn-pass-through).

#### Analysis
R2 BLOCKER: the existing callers at `pipeline.py:1066` (index) and `pipeline.py:1070` (sources) do NOT share a try/except; each failure path today is independently swallowed with a `logger.warning`. A naive sequential helper that throws on the first failure regresses this behavior — a sources-mapping write failure would skip the index update even though the index update might succeed. The helper must preserve the "independent best-effort" contract.

The ordering contract from AC14 (sources BEFORE index) is semantic: the index is the human-facing catalog and references sources that the map already knows about. If sources fails and we skip index, the catalog stays stale; if we retry index even after sources fails, the catalog might reference a page whose source-mapping entry is missing. The latter is the existing failure mode (both writes are best-effort today), and AC14 explicitly preserves warn-pass-through. Option B is correct: each call has its own try/except and logs a WARNING on failure; the second call proceeds regardless. This is the AC14 amendment wording R2 provides.

On AC numbering: amend AC14 text in place rather than splitting into AC14a. The "failure-mode preservation" wording fits in the AC14 body.

#### Decide
Option B (independent per-call try/except), amend AC14 in place.

#### Rationale
Preserves existing warn-pass-through; each call attempts independently; sources BEFORE index ordering retained; helper does not retry or roll back.

#### Confidence
High

---

### Q11: AC16 scenario (b) mtime/cache invalidation

#### Options
- Option A: Explicit cache clear hook in the test.
- Option B: Force mtime bump via `os.utime` after `refine_page`.
- Option C: Accept coarse-mtime risk; no intervention.

#### Analysis
R2 MAJOR flags the mtime-coarseness risk: `load_page_frontmatter` at `pages.py:59-88` is mtime-keyed; BM25 cache uses `max_mtime_ns` at `engine.py:638-661`. On coarse filesystems (FAT32, some network mounts, macOS HFS+), mtime granularity is 1-2 seconds; an immediate refine+re-query within that window reuses the stale cache. Option C is a flake risk. Option A requires the test to know cache-internal APIs (brittle if cache implementation changes). Option B is explicit, no cache-internal knowledge needed, and survives cache refactors.

`os.utime(page_path, (now, now + 1))` bumps mtime by one full second past the refine write, forcing any mtime-keyed cache to invalidate. This is a standard test technique. The test asserts post-utime that `query_wiki` returns the refined body in context, proving the cache invalidation path works as expected.

#### Decide
Option B (`os.utime` forced mtime bump)

#### Rationale
Explicit, no cache-internal knowledge, robust to cache refactors, standard test technique. One line in scenario (b) between `refine_page` and `query_wiki`.

#### Confidence
High

---

### Q12: AC4 can ship alone

#### Options
- Option A: Ship AC4 + AC11-AC13 together as a paired contract.
- Option B: Ship AC4 alone; AC11-AC13 in cycle 19.

#### Analysis
R1 Q12 pre-answer is explicit: AC12 reuses the rotate-in-lock pattern. Shipping AC4 alone creates a cycle-18 inconsistency window where JSONL rotation (cycle 19) would be modeled on the FIXED wiki-log behavior, but any reviewer reading the cycle-18 diff would see a standalone wiki-log fix without its downstream consumer. The paired landing also ensures the `rotate_if_oversized` public helper ships with exactly two call sites (AC5 wrapper + AC11 JSONL), proving the helper's generic contract in one cycle.

#### Decide
Option A (ship AC4 + AC11-AC13 together)

#### Rationale
Paired contract; generic helper lands with both call sites; no inconsistency window.

#### Confidence
High

---

### Q13: `_ABS_PATH_PATTERNS` UNC coverage

#### Options
- Option A: Current regex is sufficient.
- Option B: Extend to include ordinary UNC `\\server\share\path`.
- Option C: Rewrite the regex structure.

#### Analysis
R2 BLOCKER: the threat model explicitly lists UNC paths as a redaction target, but the current regex at `sanitize.py:11-15` only catches `\\?\...` long-path UNC-ish forms. Ordinary UNC `\\server\share\file` is missing. Requirements §T1 names UNC redaction as a mitigation; AC13 claims coverage. Without extending the regex, the threat-model T1 claim is false.

The extension pattern is `\\\\[^\\s\\\\]+\\\\[^\\s\\\\]+(\\\\[^\\s]*)?` — matches `\\`, one-or-more non-whitespace non-backslash chars (server), `\\`, one-or-more non-whitespace non-backslash chars (share), and optional `\\path/to/file`. R2 also requires re-verification of forward-slash Windows paths (`C:/Users/...`); R1 reports the current regex already covers drive-letter with both slash shapes. A test must pin both: `C:\Users\...` and `C:/Users/...` must be redacted identically.

On AC13 vs AC13a: the UNC extension fits in the AC13 body. Amend AC13 in place.

#### Decide
Option B (extend `_ABS_PATH_PATTERNS` to include ordinary UNC), amend AC13 in place.

#### Rationale
Closes threat-model T1 gap; preserves existing coverage; test pins both slash shapes for drive-letter paths and the new UNC shape.

#### Confidence
High

---

### Q14: AC10 `[req=]` prefix placement

#### Options
- Option A: Prefix inside the message string (before `_escape_markdown_prefix` runs).
- Option B: Prefix as a separate operation field or kwarg on `append_wiki_log`.

#### Analysis
R2 confirms `[req=` does NOT trigger the leading-marker guard at `wiki_log.py:72-80` (which neutralizes `#`/`-`/`>`/`!`); the `[` character is not in the guard list. The prefix contains no `|`/newline/tab/`[[`/`]]`, so it flows through `_escape_markdown_prefix` untouched. Placing it inside the message is safe.

Option B would require widening `append_wiki_log`'s signature — the threat model explicitly notes 6 existing caller sites across 5 test files. Widening breaks `feedback_signature_drift_verify` unless all callers are updated; AC10 is a narrow per-caller prefix, not an API change. Option A is the minimum-blast-radius choice.

A regression test asserts the log.md line format `[req=<16-hex>] | ingest | ...` — pins the safety. R2 MINOR recommends this explicitly.

#### Decide
Option A (inside message string)

#### Rationale
Safe by construction (guard-list analysis); no signature change; minimum blast radius. Regression test pins the `[req=<16-hex>]` format.

#### Confidence
High

---

### Q15: `append_wiki_log` at duplicate/failure paths

#### Options
- Option A: Add `append_wiki_log` calls at duplicate-skip and failure paths so wiki/log.md has the `[req=]` marker for all ingest events.
- Option B: JSONL is the only correlation surface for duplicate/failure; wiki/log.md remains success-only.

#### Analysis
Today only the success path at `pipeline.py:1091` writes to wiki/log.md. Duplicate-skip at line 935 returns without log.md write; failure paths raise without log.md write. Adding log.md writes at duplicate/failure would give the operator a single-surface audit trail (wiki/log.md covers all outcomes), but it also:
- Widens the behavior change in AC10 (currently caller-side prefix only).
- Creates risk of stale log.md entries on concurrent duplicate-skip (the rotate-in-lock fix from AC4 mitigates but doesn't eliminate).
- Couples two independent concerns (human-readable log vs machine-readable JSONL).

Option B keeps wiki/log.md as a success-only human-readable narrative (its existing role) and makes JSONL the complete correlation surface. The operator who wants "all ingest events correlated" consults `.data/ingest_log.jsonl`; the operator who wants "human-readable success timeline" reads `wiki/log.md`. Each surface has a clear role. Additionally, duplicate-skip is a no-op (no wiki changes); writing to log.md on no-op events turns the log into a chatty debug stream, which degrades its existing narrative value.

R2 MAJOR agrees: "make JSONL the only correlation surface for those paths." Document in AC10 amendment.

#### Decide
Option B

#### Rationale
Preserves wiki/log.md as success-only narrative; JSONL is the complete correlation surface for start/duplicate_skip/success/failure. AC10 amendment documents this explicitly.

#### Confidence
High

---

### Q16: AC8 test distinguishes no-match vs lock-failed

#### Options
- Option A: Single page + mock `file_lock` to raise universally.
- Option B: Two pages: one guaranteed no-match (asserts zero locks), one guaranteed match (asserts lock attempted).

#### Analysis
R2 MAJOR: mocking `file_lock` to raise universally conflates "page has no match" (fast-path hit, zero locks) with "page has a match but lock acquisition failed." Both produce zero completed lock entries but the test intent is different. Option B uses two distinct pages with distinct assertions:
- No-match page: asserts `file_lock` was NEVER called (zero acquire attempts).
- Match page: asserts `file_lock` was called (attempt happened, even if the test mocks the lock to succeed).

This separation is essential for the fast-path contract from AC7. The test fails informatively if a future refactor accidentally acquires the lock on no-match pages (SMB/OneDrive perf regression per T8).

#### Decide
Option B (two pages, distinct assertions)

#### Rationale
Distinguishes test intent; enforces fast-path contract; fails informatively on perf regression.

#### Confidence
High

---

### Q17: AC15 test count per ingest

#### Options
- Option A: Assert 1 row per successful ingest.
- Option B: Assert 2 rows per successful ingest (start + success).

#### Analysis
R2 MAJOR: AC11 specifies emission at start + terminal (success/duplicate_skip/failure). A successful ingest emits 2 rows; a duplicate-skip ingest emits 2 rows (start + duplicate_skip); a failure ingest emits 2 rows (start + failure). AC15 bullet `test_jsonl_emitted_on_success` as currently worded ("assert one line per ingest") is internally inconsistent with AC11. Amend AC15 to specify "2 rows per non-duplicate ingest: start + terminal; both rows contain the same request_id; terminal row has outcome counts."

#### Decide
Option B (2 rows per ingest: start + terminal)

#### Rationale
Internal consistency with AC11 emission contract; regression test asserts both rows + matching request_id + terminal-row counts.

#### Confidence
High

---

### Q18: AC11 parent-dir `mkdir` before `file_lock`

#### Options
- Option A: Call `jsonl_path.parent.mkdir(parents=True, exist_ok=True)` before `file_lock(jsonl_path)`.
- Option B: Rely on `file_lock` creating the lock parent as a side effect.

#### Analysis
R2 MINOR: `file_lock` at `io.py:253-254` creates its `.lock` sibling parent directory, but this is an implementation detail that could change. Explicit parent-dir creation for the data file makes the writer self-contained and survives refactors of `file_lock`. The cost is one extra line. This is defensive-by-default and matches the "explicit over implicit" principle.

#### Decide
Option A (explicit `mkdir` before `file_lock`)

#### Rationale
Explicit; robust to `file_lock` refactors; single line cost.

#### Confidence
High

---

### Q19: AC11 field allowlist enforcement

#### Options
- Option A: Writer constructs row from explicit scalar arguments; `stage` validated against enum.
- Option B: Writer accepts a dict and passes through.

#### Analysis
R2 MINOR: free-form field injection is a threat model concern (T1 — writer must not emit arbitrary fields from callers). Option A binds the schema at the writer: the helper signature is `_emit_ingest_jsonl(stage, request_id, source_ref, source_hash, outcome)` with scalar args, and `stage` is validated against `{"start", "duplicate_skip", "success", "failure"}` before row construction. A future caller that attempts to pass an unknown stage triggers `ValueError` at the writer boundary — fails loudly rather than silently emitting a malformed row. `outcome` is the one dict arg; it is constructed at the call site with known keys (pages_created, pages_updated, pages_skipped, error_summary).

Option B would allow a buggy caller to inject raw paths, PII, or secrets into the audit log under the guise of "extra fields." Unacceptable for T1.

#### Decide
Option A (scalar args + stage enum validation)

#### Rationale
Binds the schema at the writer; enforces T1 field allowlist; fails loudly on unknown stage.

#### Confidence
High

---

### Q20: `error_summary` truncation

#### Options
- Option A: Truncate to 2KB after `sanitize_text`.
- Option B: No truncation.

#### Analysis
R2 MINOR: large exception strings (e.g., LLM SDK errors with multi-KB prompts echoed back) can balloon JSONL row size beyond PIPE_BUF atomicity bounds. Truncation after sanitize preserves the head of the error message (most diagnostic value) while bounding row size. 2KB is generous — typical exception reprs are 100-500 bytes; LLM errors can reach 5-10KB; truncation at 2KB keeps most diagnostic signal without risking row atomicity.

Option B preserves full error detail but risks torn rows on crash (T7 residual risk). Truncation is cheap and aligns with the "append atomicity" design intent.

#### Decide
Option A (truncate to 2KB after sanitize)

#### Rationale
Preserves diagnostic head; bounds row size; keeps append atomicity under PIPE_BUF.

#### Confidence
High

---

### Q21: AC7 lock timeout bound

#### Options
- Option A: Bounded timeout (e.g. 0.25s) + skip + warn.
- Option B: Accept default 5s (100s worst-case on 20 stuck pages).

#### Analysis
R2 MAJOR: `file_lock` default 5s timeout × 20 candidate pages = 100s worst-case stall on stuck locks. For ingest, 100s is an unacceptable stall. Option A uses a short timeout (0.25s), logs a WARNING on timeout, skips that page, and continues. The ingest completes faster; the missed wikilink is a recoverable inconsistency (next ingest re-attempts).

The counter-argument: a 0.25s timeout may produce false skips on heavily-contended wikis (concurrent ingest batches). But wikilink injection is a best-effort enrichment; a skipped injection can be retried on the next ingest or caught by `kb_lint` cycle. Ingest correctness (page creation, source mapping, hash manifest) is unaffected by a skipped wikilink. Option A's trade-off (faster ingest, occasional re-attempt) dominates Option B's trade-off (slower ingest on contention, no retry needed).

R2 framing: "Stuck locks are pathological; ingest should not stall 100s." Agreed. Bounded timeout + skip + warn is the right contract. 0.25s is the recommended value; a future cycle can tune this if measurement shows false-skip rate is too high.

#### Decide
Option A (bounded 0.25s timeout + skip + warn)

#### Rationale
Bounds ingest stall; pathological stuck locks cannot block ingest for 100s; skipped wikilinks recover on next ingest or lint cycle.

#### Confidence
Medium

---

## Conditions

1. **AC7 amendment** MUST specify pre-lock cheap read + under-lock re-read + full RMW-under-lock contract (Q4 decision).
2. **AC11 amendment** MUST specify the explicit try/except boundary in `ingest_source` (Q2 decision) and the best-effort failure policy (Q8 decision).
3. **AC13 amendment** MUST extend `_ABS_PATH_PATTERNS` for ordinary UNC and pin both slash shapes for drive-letter paths (Q13 decision).
4. **AC14 amendment** MUST specify independent per-call try/except (Q10 decision).
5. **AC15 amendment** MUST use real symbol names `_update_sources_mapping` + `_update_index_batch` (not fictional `_update_sources_md` / `_update_index_md`) and correct expected row count (2 per ingest, Q17).
6. **AC16 amendment** MUST include `os.utime` mtime bump in scenario (b) and stub-invocation count assertion per scenario (Q11, Q7).
7. **Step 11 caller-grep** MUST verify `_update_sources_mapping` and `_update_index_batch` remain callable as module attributes (threat model T10).
8. **R3 review** remains mandatory per requirements §R3 triggers (a), (b), (c).

---

## Amended AC list

### AC1 (unchanged)

**AC1**: `_TMP_KB_ENV_PATCHED_NAMES` includes `"HASH_MANIFEST"`. Tuple ordering preserved for reviewability (append after `REVIEW_HISTORY_PATH` row, before wiki/raw subdir names).

### AC2 (unchanged)

**AC2**: `tmp_kb_env` patches `kb.compile.compiler.HASH_MANIFEST` to `tmp_path / ".data" / "hashes.json"`. The patch uses `monkeypatch.setattr` symmetric with the existing `WIKI_LOG`/`WIKI_CONTRADICTIONS` entries. Mirror-loop at `conftest.py:224-231` also rebinds already-imported `from kb.compile.compiler import HASH_MANIFEST` references on `kb.*` modules so in-process callers (`kb.ingest.pipeline.ingest_source`, `kb.mcp.core.kb_compile_scan`) see the tmp path.

### AC3 (AMENDED — R1 M1 + R2 MAJOR)

**AC3**: Regression test `tests/test_cycle18_conftest.py::test_hash_manifest_redirected` asserts under `tmp_kb_env`: (i) `kb.compile.compiler.HASH_MANIFEST == tmp_path / ".data" / "hashes.json"`; (ii) after calling `ingest_source(<small fixture>, extraction=<stub>)`, `(tmp_path / ".data" / "hashes.json").exists()` is True and `PROJECT_ROOT / ".data" / "hashes.json"` is NOT written by the test (mtime unchanged or file pre-verified absent via `tmp_kb_env` scope); (iii) the test docstring notes that `tests.*` modules importing `HASH_MANIFEST` at module top-level before `tmp_kb_env` runs are NOT covered by the mirror-rebind loop (grep-verified: no current test does this).

### AC4 (unchanged)

**AC4**: Move the `_rotate_log_if_oversized(log_path)` call from `append_wiki_log` (currently line 109, outside the lock) to INSIDE the `with file_lock(log_path):` block in the inner `_write` function (line 126). Comment at line 107-108 ("Runs outside the file_lock so the rename doesn't contend with readers") is removed; replace with a comment citing cycle-18 AC4 and Phase 4.5 HIGH R5 concurrency-race lesson.

### AC5 (AMENDED — R2 MINOR audit-log placement)

**AC5**: Extract a reusable `rotate_if_oversized(path: Path, max_bytes: int, archive_stem_prefix: str) -> None` public helper in `kb.utils.wiki_log`. The helper includes the pre-rename `logger.info("Rotating %s (%d bytes) → %s", ...)` audit line (moved from `wiki_log.py:40-45`). `_rotate_log_if_oversized` becomes a thin wrapper calling the helper with `max_bytes=LOG_SIZE_WARNING_BYTES` and `archive_stem_prefix="log"`. AC12's JSONL caller inherits the same audit chain automatically.

### AC6 (AMENDED — R2 MAJOR call-order total order)

**AC6**: Regression test `tests/test_cycle18_wiki_log.py::test_rotate_inside_lock` asserts via a spy on `file_lock.__enter__` + `log_path.rename` + `open`/`write` + `file_lock.__exit__` a TOTAL ORDER: `lock_enter < rotate/rename < append write < lock_exit`. Uses call-order spy (cycle-17 L2 pattern) — NOT simulated concurrency. A broken implementation (rotate before `lock_enter`) fails the total-order assertion. Plus `test_rotate_if_oversized_generic` covers the generic helper with a non-`log.md` path (asserts the audit `logger.info` fires before the rename).

### AC7 (AMENDED — R1 B1 + R2 BLOCKER: TOCTOU double-check under lock)

**AC7**: In the scalar `inject_wikilinks` loop body (`linker.py:203-263`), apply the following contract per page:

1. **Pre-lock cheap read** (preserves fast-path): `page_path.read_text` + frontmatter split + existing-link / self / no-match guards (lines 207-237 logic retained). If the page will NOT be modified, return WITHOUT acquiring any lock.
2. **Enter lock** ONLY for pages that the cheap read flagged as modification candidates: `with file_lock(page_path, timeout=0.25):` (bounded timeout per Q21). On timeout: `logger.warning("Skipping inject on %s: lock timeout", page_path)` and continue to next page.
3. **Under-lock re-read**: re-read the file, re-run frontmatter split, re-run existing-link / self / no-match guards on the fresh content (defensive; detects concurrent injector winning the race).
4. **Under-lock processing**: code-block mask, `pattern.finditer`, replacement, `_unmask_code_blocks`, final `new_body != original_body` comparison — all inside the lock.
5. **Under-lock write**: `atomic_text_write(new_content, page_path)` inside the lock. If the under-lock re-read shows no modification needed (race lost), skip the write.
6. **Exit lock**.

The pre-lock cheap read is the ONLY read for pages that skip the fast-path check; pages that pass the cheap read incur one additional (under-lock) read. No-match / already-linked / self pages incur zero locks.

### AC8 (AMENDED — R1 m1 + R2 MAJOR: two pages + TOCTOU scenario + bounded timeout)

**AC8**: Regression test `tests/test_cycle18_linker_lock.py::test_inject_wikilinks_per_page_lock` uses TWO distinct pages:

- **Page A (guaranteed no-match)**: body contains no candidate title pattern. Asserts `file_lock` was called ZERO times (fast-path pin).
- **Page B (guaranteed match)**: body contains the exact candidate title pattern. Asserts the per-modified-page sequence via call-order spy: `read_text (pre-lock) → file_lock.__enter__ → read_text (under lock) → atomic_text_write → file_lock.__exit__`.

Plus `test_inject_wikilinks_toctou_skip`: seed Page B with body content that matches pre-lock but NOT under lock (simulate via monkeypatched `read_text` returning fresh content on second call); assert `atomic_text_write` is NOT called (race-lost injector skips write).

Plus `test_inject_wikilinks_lock_timeout`: mock `file_lock` to raise `TimeoutError` on acquire; assert a WARNING log line fires and the loop continues to the next page (no exception propagates).

### AC9 (unchanged)

**AC9**: At the entry of `ingest_source`, generate `request_id = uuid.uuid4().hex[:16]` (16-hex characters, 64 bits of entropy — sufficient for per-ingest correlation). Thread it through the function body as a local variable; subsequent ACs consume it.

### AC10 (AMENDED — Q15 correlation surface clarification)

**AC10**: Prefix every `append_wiki_log(...)` call inside `ingest_source` with `[req={request_id}]` — mirrored in the entry body so the pipe-delimited format remains parseable. `append_wiki_log` signature is NOT changed; the prefix is emitted on the caller side so the helper remains a generic append (no cross-module dependency on request_id shape). Only the success path at `pipeline.py:1091` is updated; duplicate-skip and failure paths do NOT write to `wiki/log.md`. The complete correlation surface for start/duplicate_skip/success/failure is `.data/ingest_log.jsonl`; `wiki/log.md` remains a success-only human-readable narrative.

### AC11 (AMENDED — R1 B2 + R2 BLOCKER: explicit try/except + best-effort policy + field allowlist + mkdir)

**AC11**: Add `_emit_ingest_jsonl(stage: str, request_id: str, source_ref: str, source_hash: str, outcome: dict) -> None` that appends one JSON object per line to `<PROJECT_ROOT>/.data/ingest_log.jsonl`.

**Writer mechanics** (threat model action item 3):
- `jsonl_path.parent.mkdir(parents=True, exist_ok=True)` BEFORE `file_lock(jsonl_path)` (Q18).
- Wrap append in `file_lock(jsonl_path)` + `open("a", encoding="utf-8", newline="\n")` + `f.write(json.dumps(row, ensure_ascii=False) + "\n")` + `f.flush()` + `os.fsync(f.fileno())` (Q9: fsync every append).
- **MUST NOT use `atomic_text_write`** — its temp+rename semantics destroy append history.
- **Field allowlist enforcement** (Q19): writer constructs row from explicit scalar args; `stage` validated against `{"start", "duplicate_skip", "success", "failure"}` — unknown stage raises `ValueError` at the writer boundary.
- **error_summary truncation** (Q20): after `sanitize_text`, truncate `outcome["error_summary"]` to 2KB max.
- **Best-effort failure policy** (Q8): wrap the body in `try/except OSError as e: logger.warning("Failed to write ingest_log.jsonl: %s", e)`. Never mask ingest outcome; never replace original exception on `stage="failure"` path.

**Fields**:
- `ts` — ISO-8601 UTC with `Z` suffix.
- `request_id` — 16-hex.
- `source_ref` — relative path from `RAW_DIR`.
- `source_hash` — SHA-256 hex.
- `stage` — enum.
- `outcome` — dict with `pages_created`, `pages_updated`, `pages_skipped` (integers), and `error_summary` (redacted string, ≤2KB).

**Insertion points in `ingest_source`** (Q2 decision — explicit try/except pattern):
```python
request_id = uuid.uuid4().hex[:16]
_emit_ingest_jsonl("start", request_id, source_ref, source_hash, outcome={})
# ... duplicate check ...
if duplicate:
    _emit_ingest_jsonl("duplicate_skip", request_id, source_ref, source_hash, outcome={})
    return duplicate_result
try:
    # ... entire ingest body ...
    _emit_ingest_jsonl("success", request_id, source_ref, source_hash,
                        outcome={"pages_created": ..., "pages_updated": ..., "pages_skipped": ...})
    return success_result
except BaseException as exc:
    err_msg = sanitize_text(str(exc))[:2048]
    _emit_ingest_jsonl("failure", request_id, source_ref, source_hash,
                        outcome={"error_summary": err_msg})
    raise
```

### AC12 (AMENDED — rotation-in-lock explicit reference)

**AC12**: `_emit_ingest_jsonl` uses the `rotate_if_oversized` helper from AC5 to archive `.data/ingest_log.jsonl` when it exceeds 500KB (same threshold as `wiki_log.py` `LOG_SIZE_WARNING_BYTES`). Archive naming mirrors wiki log: `ingest_log.YYYY-MM.jsonl`, ordinal-collision fallback. **The `rotate_if_oversized` call MUST run INSIDE `file_lock(jsonl_path)`**, symmetric with AC4's wiki-log fix — the exact "rotate outside lock" anti-pattern AC4 removes. The rotation happens BEFORE the append write; the post-rotation file is the target of the append.

### AC13 (AMENDED — R2 BLOCKER: UNC coverage + slash-shape pin)

**AC13**: `_emit_ingest_jsonl` redacts absolute paths from free-text fields (error summaries, status messages). Extract a sibling `sanitize_text(s: str) -> str` in `kb.utils.sanitize` that shares the `_ABS_PATH_PATTERNS` regex. `_emit_ingest_jsonl` calls `sanitize_text`; `sanitize_error_text` internally calls `sanitize_text` after its exception-attribute sweep (no behaviour change for existing callers). Raw source content / page bodies are NEVER written to the JSONL. Only `source_ref` (relative path) + `source_hash` (SHA-256 hex) + counts.

**`_ABS_PATH_PATTERNS` coverage requirements** (Q13):
- Windows drive-letter with backslash: `C:\...`, `D:\...`, etc.
- Windows drive-letter with forward slash: `C:/...`, `D:/...`.
- Windows long-path UNC: `\\?\...`.
- **Ordinary UNC** (NEW): `\\server\share\path` — pattern `\\\\[^\\s\\\\]+\\\\[^\\s\\\\]+(\\\\[^\\s]*)?`.
- POSIX: `/home/...`, `/Users/...`, `/opt/...`, `/var/...`, `/srv/...`, `/tmp/...`, `/mnt/...`, `/root/...`.

**Do NOT normalize or slash-collapse input before redaction.** Redaction must operate on the original string so evidence-of-origin is preserved until substitution.

**Tests**: pin redaction on all shapes (backslash Windows drive, forward-slash Windows drive, long-path UNC, ordinary UNC, POSIX roots).

### AC14 (AMENDED — R2 BLOCKER: independent per-call try/except)

**AC14**: Extract `_write_index_files(wiki_dir, created_entries, source_ref)` helper in `pipeline.py` that wraps the existing `_update_sources_mapping(source_ref, wiki_dir, ...)` at `pipeline.py:641` + `_update_index_batch(created_entries, wiki_dir, ...)` at `pipeline.py:681` pair with a documented ordering contract (`_sources.md` update BEFORE `index.md` update — index references sources that the map already knows about).

**Failure-mode preservation** (Q10): each call has its OWN try/except that logs WARNING and allows the second call to run if the first fails. Sources is attempted FIRST; index is attempted regardless of sources outcome. The helper does NOT retry or roll back; preserves existing `logger.warning` pass-through.

**Symbol constraint** (threat model T10 / monkeypatch enumeration): `_update_sources_mapping` and `_update_index_batch` MUST remain callable as module attributes (`kb.ingest.pipeline._update_sources_mapping` / `_update_index_batch`) — 2 test monkeypatch sites in `test_v01008_ingest_pipeline_fixes.py` depend on it. Do NOT inline or rename.

### AC15 (AMENDED — R1 M2 symbol-name fix + Q17 row count)

**AC15**: Regression tests in `tests/test_cycle18_ingest_observability.py`:

- `test_request_id_prefix_in_log_md` — assert the log.md line for one successful ingest begins with `[req=<16-hex>]` and the hex EXACTLY matches the JSONL entry's `request_id` field.
- `test_jsonl_emitted_on_success` — assert the JSONL emits the expected stage sequence for one successful ingest: `start` followed by `success`. Both rows contain the same `request_id`; the `success` row has `outcome` counts. Total 2 rows per successful ingest.
- `test_jsonl_emitted_on_duplicate` — assert duplicate-skip path emits `start` followed by `duplicate_skip`. Total 2 rows.
- `test_jsonl_emitted_on_failure` — inject a synthetic ingest exception; assert JSONL emits `start` followed by `failure`; assert the original exception propagates (not masked by telemetry).
- `test_jsonl_rotation` — pre-populate `.data/ingest_log.jsonl` with >500,000 bytes of synthetic content, call `_emit_ingest_jsonl` once, assert archived file created with timestamp-ordinal name AND the new file exists with the new row.
- `test_jsonl_rotation_inside_lock` — spy on `file_lock.__enter__` + `rename` + `open`/`write` + `file_lock.__exit__`; assert total order `lock_enter < rotate/rename < append < lock_exit`.
- `test_jsonl_redacts_absolute_paths` — inject synthetic failures whose error messages contain `C:\Users\Admin\...`, `C:/Users/Admin/...`, `\\server\share\x`, `\\?\C:\x`, `/home/user/x`; assert all redacted to `<path>` in the JSONL entry.
- `test_jsonl_field_allowlist` — call `_emit_ingest_jsonl` with an invalid stage `"bogus"`; assert `ValueError` at writer boundary.
- `test_jsonl_error_summary_truncation` — inject a 10KB error message; assert the JSONL row's `outcome.error_summary` is ≤2048 bytes.
- `test_write_index_files_ordering` — spy on `kb.ingest.pipeline._update_sources_mapping` + `kb.ingest.pipeline._update_index_batch`; assert sources mapping called BEFORE index batch; both called exactly once per `_write_index_files(...)` invocation.
- `test_write_index_files_independent_failure` — monkeypatch `_update_sources_mapping` to raise; assert `_update_index_batch` still runs (WARNING logged for sources failure).

### AC16 (AMENDED — R1 M3 + R2 MAJOR: mtime bump + stub count + wikilink assertion)

**AC16**: Three scenarios driving `ingest_source` → `query_wiki` → `refine_page` over `tmp_project` (cycle-17 AC15 deferral). Mock ONLY the boundary LLM calls (`kb.utils.llm.call_llm`, `kb.utils.llm.call_llm_json`, and `kb.query.engine.call_llm`). The mocks track invocation count; each scenario asserts `stub_call_count >= 1` for the mocked functions actually exercised by that path (vacuous-test defense per R1/R2).

Scenarios:
- **(a)** Ingest one article with extraction payload → `query_wiki("What is X?")` returns a non-empty answer referencing the summary page; `citations` contains both `type='wiki'` and `type='raw'` entries. Asserts LLM mock was invoked ≥1 time during query synthesis.
- **(b)** After scenario (a), call `refine_page(<entity_page_id>, "refined body", notes="test")` → **force mtime bump via `os.utime(page_path, (now, now + 1))`** on the refined page → re-ingest the related article → `query_wiki` returns the refined body in context. Asserts LLM mock was invoked ≥1 time during re-query.
- **(c)** Ingest two articles sharing entity "Anthropic" → second ingest's result dict contains `wikilinks_injected` with `len(wikilinks_injected) >= 1` AND at least one entry references a page created by the FIRST ingest (explicit assertion; prevents scenario degeneracy per R2). Asserts LLM mock was invoked ≥1 time during each ingest's extraction.

Total test count: 3 tests. Marked `@pytest.mark.integration` to enable future slow-suite separation if needed.

---

## R3 trigger re-confirmation

R3 remains MANDATORY. Of the 4 triggers from cycle-17 L4:

- (a) **new FS write surface** — YES (`.data/ingest_log.jsonl`).
- (b) **vacuous-test regression risk** — YES (file_lock call-order tests per cycle-17 L2; AC6, AC8, AC15 lock-order tests).
- (c) **new security enforcement point** — YES (secret redaction in JSONL writer; field allowlist).
- (d) **design-gate resolved ≥10 open questions** — YES (21 questions resolved).

All four triggers fire. Per `feedback_3_round_pr_review`, plan 3 independent review rounds at PR time; round 3 typically APPROVES but catches regressions introduced by round-2 fixes. Round assignments: R1 (Opus sub-agent), R2 (Codex), R3 (independent Opus).

---

## Summary

- **Total amendments**: 9 ACs receive text updates (AC3, AC5, AC6, AC7, AC8, AC10, AC11, AC12, AC13, AC14, AC15, AC16 — actually 12 with updated text, net-new content in all).
- **ACs unchanged**: 4 (AC1, AC2, AC4, AC9).
- **ACs with text updates**: 12 (AC3, AC5, AC6, AC7, AC8, AC10, AC11, AC12, AC13, AC14, AC15, AC16).
- **ACs blocked / deferred**: 0.

Proceed to Step 4 planning.
