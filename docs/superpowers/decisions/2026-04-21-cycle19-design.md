# Cycle 19 — Design Decision Gate

**Date:** 2026-04-21
**Reviewer:** Opus 4.7 Step-5 gate
**Upstream:** requirements.md + threat-model.md + brainstorm.md + r1-opus.md + r2-codex.md
**Verdict:** APPROVE-WITH-AMENDMENTS

## Summary

- **1 BLOCKER resolved:** R1 AC10 (lock-order flip) → WITHDRAW, reframe as "document existing order + add behavioural test"
- **9 R1 MAJORs resolved:** AC2 (read budget), AC6 (failure granularity), AC8 (flip correlation), AC9 (lock span), AC12 (traversal hardening), AC13 (test construction), AC14 (problem may not exist — DROP), AC16 (vacuous test), AC17 (count mismatch)
- **5 R2 MAJORs resolved:** M1 (dual manifest writes), M2 (pending recovery), M3 (under-lock re-derive), M4 (platform-neutral canon test), M5 (per-title length cap)
- **2 R2 NITs resolved:** N1 (signature placement after `*`), N2 (vacuity test coverage)
- **15 brainstorm open questions resolved:** Q1-Q15
- **11 requirements open questions resolved:** Q1-Q11

**ACs finalised:** 20 original − 1 (AC14 dropped with test-anchor retained) + 4 added (AC1b, AC4b, AC8b, AC12-revised) = **23 production ACs** (AC10 revised in place, not dropped).

---

## Decisions

### AC10 — R1 BLOCKER: lock-order flip

**Options:**
- (a) **WITHDRAW** the flip. Keep existing order `page_path FIRST, history_path SECOND`. AC10 becomes "document the existing order in the docstring + add behavioural test for acquisition order".
- (b) **REVISE-FLIP**. Proceed with history-first, accepting the T4 liveness cost, on the theory that AC8's pending-write simplifies when history is outer.

## Analysis
The current code at `review/refiner.py:85` explicitly documents `page_path FIRST; history_path SECOND`. That order was chosen during the Phase-4.5 HIGH fix cycle 1 precisely because the page lifecycle (read frontmatter → validate → diff → write) must serialize under page_path; history-second was the cross-process audit trail that cannot deadlock because no other caller holds history-lock before asking for page-lock. R1 verification against the live source confirms this. The threat model T4 says directly: "N/A — self-inflicted liveness risk", meaning the flip is not motivated by any concrete deadlock in the current call graph. So the only justification for flipping would have been "it simplifies AC8's pending write to have history as the outer lock" — but that is false. AC8 can nest a history-lock span INSIDE the page-lock span just as easily as it can nest in the other direction, and doing so preserves the already-shipped crash-safety contract (page fully under page_lock) at zero cost.

Given the Karpathy-style two-test principle ("every changed line traces directly to the request" and "would a senior engineer say this is overcomplicated"), flipping a shipped lock order to satisfy a requirement that was itself arguably motivated by a misreading of the existing invariant is gold-plating. The lower-blast-radius path is (a) WITHDRAW. Document the existing order explicitly in the function docstring (so future readers don't re-raise the question), add a behavioural test that asserts acquisition order via mocked `file_lock` context managers (this protects against accidental reordering in a refactor), and nest AC8's pending write INSIDE page_lock's outer span with a nested `with file_lock(history_path):` inner span. This preserves the cycle-18 pattern (`with file_lock(log_path):` in `append_wiki_log`) and avoids amplifying history-lock contention across concurrent refines.

**Decide:** WITHDRAW — AC10 becomes "document existing order `page_path FIRST, history_path SECOND` in docstring + assert acquisition order in a behavioural test". AC8's pending-write nests INSIDE the existing `page_lock` + `history_lock` nest. No actual reordering of locks.
**Rationale:** No deadlock risk exists, no technical requirement forces the flip, T4 liveness regression is avoidable, principle "lower blast radius wins (reversible > irreversible)" applies directly.
**Confidence:** HIGH

### AC14 — R1 MAJOR: prune base consistency (problem may not exist)

**Options:**
- (a) **DROP** AC14 from cycle 19 scope (fix already shipped in cycle-17 AC1). Retain regression test as machine-enforced anchor.
- (b) **KEEP** and write a failing test to demonstrate current divergence.

## Analysis
R1 verified against compiler.py:270 + compiler.py:452 that both prune sites already consistently use `_canonical_rel_path` (line 270 directly, line 452 via `raw_dir.resolve().parent` — the canonicalizer encapsulates the same base resolution). The user's instruction states this was confirmed against the cycle-17 AC1 fix. Attempting to write a failing test under cycle 19 would produce a vacuously-passing test (cycle-11 L1 gate violation), because there's no bug to reproduce — the bug is already closed.

The cycle-15 L2 rule ("DROP-with-test-anchor-retention") explicitly addresses this shape: when a requirement is dropped because the fix is already shipped, retain a regression test as a machine-enforced anchor so that a future refactor cannot silently re-introduce the divergence. The test no longer reproduces a cycle-19 bug; it pins the cycle-17 shipped behavior. This is exactly the right move.

**Decide:** DROP AC14 from cycle 19 production scope. Retain `test_cycle19_prune_base_consistency_anchor.py` as a machine-enforced regression test anchoring cycle-17 AC1's fix: `_canonical_rel_path(source, raw_dir)` at both sites produces equal keys for the same source under the same `raw_dir`.
**Rationale:** No current bug; avoid vacuous-test gate violation; L2 rule mandates test-anchor retention on DROP; rationale documented in design doc for future auditors.
**Confidence:** HIGH

### AC12 — R2 M1: manifest_key covers both manifest writes

**Options:**
- (a) Derive `manifest_ref = manifest_key if manifest_key is not None else source_ref` once at the top of `ingest_source`; thread `manifest_ref` into BOTH `_check_and_reserve_manifest` (phase-1 dedup reservation) AND the tail confirmation write (phase-2).
- (b) Thread only into the tail confirmation (cycle-19 original AC12); accept the transient mismatch window between reservation and confirmation.

## Analysis
Codex M1 is correct that threading `manifest_key` only into the tail confirmation creates a real integrity hazard: the reservation at `pipeline.py:1062-1093` uses the legacy `source_ref` hash, and the confirmation at `pipeline.py:1301-1310` uses the caller-supplied `manifest_key`. A compile-driven ingest whose canonical key differs from `source_ref` (exact Windows case/symlink scenario §5 describes) will reserve under the old key and confirm under the new one, leaving the manifest with either a stale reservation that future compiles re-extract from, or two half-written entries if the process dies between reservation and confirmation. This is the same divergence the AC was supposed to fix, just moved one line.

Option (a) is the minimum-blast-radius correct answer: compute `manifest_ref` once; use it everywhere. `source_ref` remains the unchanged identity used for page frontmatter, log entries, and provenance. `manifest_ref` is the opaque dict-key string governed by the T3 contract (documented as "opaque string from `manifest_key_for`, not a path"). The two concepts are now distinct, each with one write path.

**Decide:** AC12 REVISED — `ingest_source` derives `manifest_ref = manifest_key if manifest_key is not None else source_ref` once at function entry. Both `_check_and_reserve_manifest` (phase-1) and the tail confirmation (phase-2) use `manifest_ref`. `source_ref` (unchanged) continues to drive page frontmatter, log entries, and provenance. Add explicit T-12b test: patch both write sites and assert they use the same key.
**Rationale:** Codex M1 correct; T3 threat model intent is single opaque key; single-derivation pattern eliminates divergence class entirely.
**Confidence:** HIGH

### AC1b — R2 M3: under-lock re-derive winning target

**Options:**
- (a) **Add AC1b**: pre-lock scan is candidate-gathering only; under the page-lock, re-read fresh body + re-scan for all batch titles + apply deterministic longest-first tie-break to CURRENT matches + inject at most one link.
- (b) Accept pre-lock snapshot decision (status quo proposed in AC1/AC2).

## Analysis
Codex M3 correctly identifies that a pre-lock snapshot of `all_wiki_pages` can go stale between scan and lock acquisition. If a concurrent ingest already linked title A on this page, the snapshot still shows A as a candidate, and the batch helper under-lock re-read would see the existing link and skip (current `inject_wikilinks` already re-validates). But if the concurrent ingest rewrote the page body in a way that makes title B the longer/preferred winner (or makes title A no longer appear in the fresh body), the pre-lock-selected winner could be wrong. The single-target `inject_wikilinks` handles this correctly because its pre-lock peek is per-title (only one candidate to validate); the batch helper's N-title peek concentrates the staleness risk.

The fix is straightforward and follows the pattern already in `inject_wikilinks`: under the page_lock, re-open the file via `save_page_frontmatter`-compatible read, re-run the combined alternation against the fresh body, re-apply the `-len, pid` sort to the CURRENT matches, and pick the winner from fresh data. The pre-lock snapshot becomes a pure performance optimization — it filters out pages with zero candidate matches (AC5's no-lock fast path), but never decides the winner for pages that will be written.

**Decide:** Add **AC1b — Under-lock target re-derivation**. `inject_wikilinks_batch`'s pre-lock scan is candidate-gathering only. Under each matched page's `file_lock`, re-read the fresh body, re-apply the combined-alternation scan, re-apply `(-len(title), pid)` tie-break to CURRENT matches, select the winning title from fresh data, inject at most one link. Test T-1b: seed a page mentioning A and B, monkeypatch under-lock re-read to inject a third title C into the body between pre-lock scan and under-lock acquisition, assert the batch helper picks the deterministic winner from fresh body (not from snapshot).
**Rationale:** M3 correct; matches single-target re-validate contract; preserves determinism under concurrent writes; low additional complexity.
**Confidence:** HIGH

### AC4b — R2 M5: per-title length cap

**Options:**
- (a) Add `MAX_INJECT_TITLE_LEN = 500` constant in `kb.config`. Titles longer than 500 chars → `log.warning` + skip THAT title (do not reject the whole batch).
- (b) Reject the whole batch on any overlength title.
- (c) Truncate titles to 500 chars silently.

## Analysis
M5 catches a real ReDoS hole: `MAX_INJECT_TITLES_PER_BATCH=200` bounds count but not individual title length. A single 100KB extracted title (prompt-injection or LLM hallucination) would balloon the alternation by 2× its length post-`re.escape`, slowing every page scan in that chunk. The fix must be belt-and-suspenders alongside the count cap.

Option (a) — skip with warning — is the lowest-blast-radius choice: one pathologically-long title does not poison the whole batch (which may contain 199 well-formed titles needed for linking), and the warning ensures observability so operators can trace the source. Option (b) (reject whole batch) weaponizes adversarial titles into a DoS vector. Option (c) (truncate) changes title semantics silently — a truncated wikilink target page would not exist, producing dead links.

**Decide:** Add **AC4b — Per-title length cap**. Add `MAX_INJECT_TITLE_LEN = 500` constant to `kb.config`. In `inject_wikilinks_batch`, before adding a title to the alternation regex, check `len(title) <= MAX_INJECT_TITLE_LEN`; if exceeded, emit `log.warning("skipping overlength title: len=%d, first 64 chars=%r", len(title), title[:64])` and skip that title. Batch continues with remaining titles. Test T-4b: batch of [short_title, 1_000_char_title, another_short_title] → warning logged, both short titles processed, long title absent from regex.
**Rationale:** M5 correct; per-title skip avoids DoS vector; warning preserves observability; 500-char ceiling is generous enough for any legitimate title.
**Confidence:** HIGH

### AC8b — R2 M2: list_stale_pending helper

**Options:**
- (a) Add minimal **AC8b** — `list_stale_pending(hours=24) -> list[dict]` reporter helper in `kb.review.refiner`. Defer full sweep/cleanup tool to future cycle.
- (b) Ship full sweep tool in cycle 19.
- (c) Document pending as terminal-forensic with no helper.

## Analysis
M2 correctly notes that the two-phase write introduces a state (`status="pending"`) that can outlive a crashed process with no operator signal. A stuck row doesn't corrupt anything, but it accumulates silently and erodes audit-trail signal. Shipping a full sweep tool (option b) is scope creep for cycle 19 — it needs a policy for "what counts as safe to garbage-collect", locking discipline for concurrent access, and an MCP surface or CLI command. Option (c) (no helper) leaves operators grepping JSON by hand.

Option (a) is the minimum viable visibility: a pure-read helper that takes a threshold, scans `load_review_history()`, filters to `status == "pending"` entries with `timestamp < (now - hours)`, returns them. No mutation, no lock contention, trivially unit-testable. This unblocks future sweep tooling without committing cycle 19 to shipping it. The requirement's Q4 default (no TTL filter) remains unchanged — the helper exposes visibility; it doesn't decide retention policy.

**Decide:** Add **AC8b — `list_stale_pending` reporter helper** in `kb.review.refiner`. Signature: `list_stale_pending(hours: int = 24, *, history_path: Path | None = None) -> list[dict]`. Returns list of pending entries older than threshold. Pure read, no locks (refiner load already file-locks). Test T-8b: seed 3 pending rows (2h, 25h, 48h old) + 1 applied row, call with `hours=24`, assert returns exactly the 25h and 48h pending rows. Full sweep tool explicitly deferred to future cycle with backlog entry.
**Rationale:** M2 correct; cycle-19 ships visibility only per user's mandatory treatment; unblocks operators without scope-bloating cycle 19.
**Confidence:** HIGH

### AC2 — R1 MAJOR: read budget undercount

**Options:**
- (a) Rewrite as `≤ U + 2M` where `U` = unmatched existing pages, `M` = matched pages (pre-lock peek + under-lock re-read).
- (b) Keep `≤ 10` and have T-2 construct pages that definitely have zero matches.

## Analysis
R1 math is right: peek is 1 read per page regardless of match, under-lock re-read adds 1 read per MATCHED page (skipped for unmatched pages by AC5's no-lock fast path). So the total is `U + 2M`. Asserting a blanket `≤ 10` fails when M > 0 in the T-2 fixture. Option (b) contorts the test; option (a) states the real invariant.

Keeping the test semantic honest matters because cycle-11 L1's vacuous-test gate requires reverting the batch loop to per-target calls to make T-2 fail. The revert-check semantics are `per_target_reads = len(titles) × len(existing_pages)`, which for 5 titles × 10 pages = 50 peeks + 2×M under-lock reads (each matched page locked once per matching title under per-target). The new budget is `U + 2M` which is ≤ 20 for 10 pages; the revert budget is ≥ 50 for 5×10. Divergence is ~2.5×, real and testable.

**Decide:** T-2 budget rewrites to `≤ len(existing_pages) + len(matched_pages)` (equivalent to `U + 2M` where `U = P - M`). Test constructs a controlled fixture with known M. Revert-check asserts reverting to per-target still gives ≥ 2× the batch budget.
**Rationale:** R1 math correct; honest invariant beats contrived fixture; vacuous-gate still clears.
**Confidence:** HIGH

### AC6 — R1 MAJOR: failure-granularity regression

**Options:**
- (a) Add inner try/except per chunk INSIDE `inject_wikilinks_batch`; one chunk failure doesn't abort remaining chunks.
- (b) All-or-nothing per batch (proposed status quo).
- (c) Per-title try/except inside the chunk (restores exact pre-batch semantics).

## Analysis
R1's concern is that the current `_run_ingest_body` wraps each `inject_wikilinks(ptitle, pid, ...)` call in its own try/except at DEBUG level. Moving to one batch call exposes the whole batch to a single exception. Option (c) restores exact semantics but defeats the batch-helper's purpose (it would need to chunk per title, losing the combined-alternation win).

Option (a) — chunk-level try/except — is the reasonable middle ground: 250 titles split into 2 chunks of 200 + 50, each chunk runs in its own try/except, log exception per failed chunk. One pathological title in chunk 1 doesn't silently block chunks 2-N. This preserves observability without undoing the N-page-scan win.

**Decide:** AC6 amended: `inject_wikilinks_batch` wraps each chunk (not each title) in its own `try/except Exception`; a chunk failure emits `log.warning("batch chunk %d/%d failed: %r", idx, total, exc)` and continues to next chunk. Batch result dict reports successful chunks' injections; failed chunks are absent. Test T-6b: 200+50 batch where chunk 1 raises mid-process; assert chunk 2's 50 titles still process and appear in return dict.
**Rationale:** R1 concern addressed without undoing batch perf win; chunk-granularity matches the chunking unit the helper already owns; observability preserved via chunk-level logging.
**Confidence:** HIGH

### AC8 — R1 MAJOR: flip correlation key

**Options:**
- (a) `attempt_id = uuid4().hex[:8]` new field; pending and applied share the same `attempt_id`.
- (b) Correlation tuple `(timestamp, page_id)` — brittle if two refines in same millisecond.
- (c) Correlation by list position (index into history array) — fragile under concurrent appends.

## Analysis
Correlation by `(timestamp, page_id)` tuple collides on the same-page-same-second case which is real in tests and possibly in concurrent CLI sessions. Correlation by index is fragile because the history file can grow between pending and applied writes (pending for refine A, then refine B runs and appends its own pending, then refine A's applied flip tries to locate by index — the index shifted). Neither survives adversarial timing.

`attempt_id` is a fresh 8-hex UUID prefix: 2^32 space, collision probability negligible for realistic history sizes, mechanically simple (one new field, generated once at pending-write time, echoed at flip time). Under the history_lock RMW the flip is `history[i]["attempt_id"] == attempt_id → history[i]["status"] = "applied"`. Existing readers that don't care about `attempt_id` ignore it (JSON extensibility). This pattern matches cycle-18 `placeholder_prefix = uuid.uuid4().hex[:8]` elsewhere in the codebase.

**Decide:** AC8 amended: pending row includes `attempt_id = uuid4().hex[:8]` alongside the existing fields. The pending → applied/failed flip locates the row by `attempt_id` equality under the history_lock. T-8 asserts flip finds the exact row by attempt_id even when a concurrent refine appended a second pending row between the flip's load and save.
**Rationale:** Attempt ID is the Pythonic correlation key (8-hex collision-free at realistic scale); index/timestamp brittleness avoided; field-extensibility backward-compatible.
**Confidence:** HIGH

### AC9 — R1 MAJOR: lock span ambiguity

**Options:**
- (a) **Hold** `file_lock(history_path)` across the page-write window (single span covers both writes — RMW).
- (b) **Release** after pending-write, re-acquire for flip (shorter critical section).

## Analysis
AC9's text reads ambiguously. Brainstorm D8 implies (a) hold-through. Threat T4 acknowledges (a) causes MEDIUM liveness regression but accepts it for crash-safety. Option (b) shortens the critical section but introduces a window where a second process could observe partial state between release and re-acquire.

The user's mandatory treatment states explicitly: "release and re-acquire NOT allowed for crash-safety". So (a) it is. The liveness cost is bounded because (i) refine is not a hot path (user-invoked, <1/second) and (ii) `atomic_text_write` inside the span is millisecond-range. The span is effectively "hold history_lock ≤ ~5ms while page writes". That is an acceptable cost for an unambiguous audit-trail contract.

**Decide:** AC9 spec locks semantic (a): `file_lock(history_path)` is acquired once at pending-write time and held across the entire page-write window, released only after the pending → applied/failed flip completes within the same lock span. Documented in `refine_page` docstring: "history_lock held across page-write window for crash-safety; refine is not a hot path, so liveness regression is bounded."
**Rationale:** User mandatory treatment forbids release/re-acquire; crash-safety requires single-span; T4 liveness cost is bounded and acceptable given refine call frequency.
**Confidence:** HIGH

### AC12 — R1 MAJOR: traversal hardening (incorporating R2 M1 + N1)

**Options:**
- (a) Reject `manifest_key` containing `..`, leading `/`, `\x00`, or exceeding 512 chars at `ingest_source` entry. Keyword-only placement AFTER existing `*` sentinel (per N1).
- (b) Document as opaque, no validation.

## Analysis
R1 correctly notes T3's mitigation is docstring-only, which is weak. Defense-in-depth is the project's stated principle. Even though manifest-key today is a dict key (never FS-resolved), the pattern protects future code paths — a later caller who does `Path(manifest_key).resolve()` won't reintroduce a traversal vector. This is the same pattern as `_validate_page_id` in `kb.mcp.core`. Cost is 4 lines of validation at `ingest_source` entry.

N1 (Codex) catches that signature placement must be AFTER the existing `*` sentinel to avoid breaking positional MCP callers. This is correct — `*, defer_small=False, wiki_dir=None, raw_dir=None, manifest_key=None, _skip_vector_rebuild=False` is the right shape. A regression test pinning legacy positional calls is cheap insurance.

Combining with M1 (above): `manifest_ref = manifest_key if manifest_key is not None else source_ref` derivation happens AFTER the validation check. If `manifest_key` is rejected, raise `ValueError` before entering any I/O path.

**Decide:** AC12 REVISED (final text): `ingest_source` accepts `manifest_key: str | None = None` as keyword-only AFTER existing `*` sentinel. At function entry, if `manifest_key is not None`: validate `".." not in manifest_key`, `not manifest_key.startswith(("/", "\\"))`, `"\x00" not in manifest_key`, `len(manifest_key) <= 512` → else raise `ValueError("invalid manifest_key: ...")`. Derive `manifest_ref = manifest_key or source_ref`. Use `manifest_ref` at BOTH phase-1 `_check_and_reserve_manifest` AND phase-2 tail confirmation. Test T-12: legacy positional call (`ingest_source(path)`) binds identically. Test T-12b: both write sites use `manifest_ref`. Test T-12c: `manifest_key="../etc/passwd"` → ValueError.
**Rationale:** R1 MAJOR (hardening) + R2 M1 (dual writes) + R2 N1 (signature placement) collapse into one coherent revised AC; defense-in-depth matches project convention; positional compatibility preserved.
**Confidence:** HIGH

### AC13 — R1 MAJOR: test construction + R2 M4 platform-neutral

**Options:**
- (a) Keep Windows tilde test (skipif non-Windows) PLUS add portable symlink test (skipif not symlink-capable).
- (b) Replace with pure unit test of `manifest_key_for(source, raw_dir_alt_case)` equality.

## Analysis
R1 says the tilde-test is hard to construct and suggests (b). R2 M4 says (b) misses the platform-neutral half of the bug (symlinked or relative raw_dir). Both are right. The portable sibling test that Codex proposes — create a tmpdir, `(tmp / "link").symlink_to(raw_dir)`, call `manifest_key_for(src, raw_dir)` and `manifest_key_for(src, tmp/"link")`, assert equal — exercises the real-world divergence path on POSIX and via Windows developer-mode symlinks.

Both tests together give us: Windows-specific case (tilde short-path) AND platform-neutral case (symlink / relative spelling). Skip decorators handle platform gaps. Total: two tests, both cheap.

**Decide:** AC13 test split:
- T-13a (Windows): `@pytest.mark.skipif(not sys.platform.startswith("win"))` — tilde short-path divergence.
- T-13b (portable): `@pytest.mark.skipif(not _can_create_symlink())` — symlinked raw_dir divergence. Uses `tmp_path` + `Path.symlink_to`.
- T-13c (pure unit): `manifest_key_for(source, raw_dir) == manifest_key_for(source, raw_dir_realpath)` — always runs.
**Rationale:** Combines R1's testability critique with R2's platform-coverage concern; T-13c is the no-regrets baseline that runs on all platforms.
**Confidence:** HIGH

### AC16 — R1 MAJOR: vacuous docstring-extraction test

**Options:**
- (a) Keep docstring-extraction test AND add behavioural test: import `kb.mcp.core`, patch `kb.config.PROJECT_ROOT`, call an MCP tool, assert pre-patch value was used.
- (b) Drop docstring test, keep only behavioural test.
- (c) Drop behavioural test, keep only docstring test (status quo).

## Analysis
R1 is correct that a docstring-extraction test only verifies the rationale text is present, not that the snapshot-binding behavior is preserved. The real invariant is "`from kb.config import X` at module import captures the value; post-import patches of `kb.config.X` don't propagate". The behavioural test proves this directly.

Dropping the docstring test (option b) loses the human-readable rationale — if someone refactors `kb.mcp.core` in the future, they see no documentation explaining the asymmetry. Keeping both (option a) is belt-and-suspenders at trivial cost (one extra test).

The user's mandatory treatment note says "snapshot-binding AC16 has behavioural test via `kb.config.PROJECT_ROOT` patch". So the behavioural test is non-negotiable. Keeping the docstring test alongside is a no-op.

**Decide:** AC16 amended: keep docstring-extraction test for rationale presence AND add behavioural test (per user mandate). Behavioural test: `import kb.mcp.core` first, then `monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)`, call an MCP tool that reads `PROJECT_ROOT`, assert it uses the ORIGINAL value (proves snapshot binding). Add a second flipping test: patch `kb.mcp.core.PROJECT_ROOT` directly → assert MCP tool uses the PATCHED value (proves `kb.mcp.core.X` is the correct patch target).
**Rationale:** R1 correct about docstring vacuity; behavioural test pins real invariant; user mandate explicit.
**Confidence:** HIGH

### AC17 — R1 MAJOR: count mismatch (12 claimed, 6 actual)

**Options:**
- (a) Correct the count in the AC text to "6 files" based on R1 cross-reference.
- (b) Re-grep at plan-gate time and reconcile.

## Analysis
R1's enumeration: 9 files with `HASH_MANIFEST` patches, 8 files using `tmp_kb_env`, intersection = 6 files. Requirements' "12 files" is wrong. The planner must use the accurate count or they'll budget test-refactor effort incorrectly.

Option (b) (re-grep at plan time) is always wise, but the design-gate deliverable should state the expected count for the planner to verify against. Plan time will confirm R1's number.

Also R1 correctly notes `tmp_kb_env` is NOT autouse; it's a declarative fixture. AC17's text and AC18's detection strategy both need that correction.

**Decide:** AC17 REVISED: scope is the 6 files at intersection of HASH_MANIFEST-patching AND `tmp_kb_env` declaring. Plan-gate re-greps and reconciles. AC18 detection strategy: grep test source files for `tmp_kb_env` as function parameter (correct as brainstorm D7 already had). Docstring corrections: `tmp_kb_env` described as "declarative fixture (must be declared as parameter)" not "autouse".
**Rationale:** R1 cross-reference is rigorous; count honesty matters for plan effort; autouse claim correction is cheap.
**Confidence:** HIGH

### N1 — R2 NIT: signature placement

Already folded into AC12 resolution above. Signature: `*, defer_small=False, wiki_dir=None, raw_dir=None, manifest_key=None, _skip_vector_rebuild=False`. Regression test pins legacy positional calls.

## Analysis
N1 is a minor-but-real backward-compat concern. Positional callers (MCP core, tests) pass `source_path, source_type` positionally. Adding `manifest_key` BEFORE `*` would silently shift all kwargs and break any caller using 3+ positional args. Placement AFTER `*` is a dead-simple syntactic guarantee.

The corresponding regression test is one line: `inspect.signature(ingest_source).parameters["manifest_key"].kind == inspect.Parameter.KEYWORD_ONLY`. Near-zero cost.

**Decide:** Folded into AC12 final text. Regression test added to T-12 suite.
**Rationale:** Cheap correctness guarantee; preserves positional binding for all existing callers.
**Confidence:** HIGH

### N2 — R2 NIT: MCP vacuity test coverage

**Options:**
- (a) Add parametrized vacuity test: for each of `query_wiki`, `search_pages`, `compute_trust_scores`, `ingest_source`, patch the owner module AND call the corresponding MCP tool; assert the patch intercepts.
- (b) One unified test per callable (4 tests).

## Analysis
N2 is correct that the real risk of AC15 is not the attribute-lookup perf (negligible) but incomplete migration leaving some MCP call sites still using `from … import name` style, which would silently fail to be patched. The vacuity test per callable closes this: reverting the `kb.mcp.core` import style for any one of them makes the test fail.

Parametrized vs 4 separate tests is pytest-style preference. Parametrized is slightly more compact but harder to debug when one fails. For 4 cases, 4 separate tests are readable enough.

**Decide:** Add 4 separate vacuity tests (one per migrated callable) in `test_cycle19_mcp_monkeypatch_migration.py`. Each test imports `kb.mcp.core`, monkeypatches the owner-module attribute (e.g., `kb.ingest.pipeline.ingest_source`), calls the corresponding MCP tool, asserts the patched callable was invoked. Revert check: changing `kb.mcp.core` back to `from kb.ingest.pipeline import ingest_source` style makes the test fail.
**Rationale:** R2 N2 correct; migration completeness is the actual risk; 4-test expansion is cheap and clearly per-symbol.
**Confidence:** HIGH

---

### Requirements Q1-Q11 resolutions

**Q1 (AC1 dict vs tuple list):** tuple list `list[tuple[str, str]]`. Preserves iteration order for AC3 tie-break. Confidence HIGH.
## Analysis
Tuple list mirrors `_sort_new_pages_by_title_length` output; dict loses ordering; iteration order matters for deterministic tie-break.

**Q2 (AC2 read budget):** `≤ len(existing_pages) + len(matched_pages)` (= U + 2M). Resolved in AC2 amendment above. Confidence HIGH.

**Q3 (AC4 ceiling 200):** Accept 200 as the cycle-19 default; revisit empirically in a future cycle. Brainstorm default stands. Confidence MEDIUM (arbitrary but defensible).
## Analysis
200 titles × ~25 avg chars = ~5KB alternation; `re.escape` keeps backtracking bounded. 500 would also be safe. 200 is a conservative starting point. Perf data after cycle 19 ship will inform the next tune.

**Q4 (AC8 pending TTL filter):** No filter; `list_stale_pending` (AC8b) is the visibility path. Brainstorm default stands, enhanced by AC8b. Confidence HIGH.

**Q5 (AC11 alias name):** `manifest_key_for`. Matches `decay_days_for` / `tier1_budget_for` / `volatility_multiplier_for` verb-first convention. Confidence HIGH.
## Analysis
Brainstorm Q6 default. Project-wide naming consistency is load-bearing for grep-ability; the verb-first pattern is established.

**Q6 (AC12 keyword-only):** Yes, keyword-only, placed AFTER existing `*` sentinel (N1). Confidence HIGH. Resolved in AC12 final text above.

**Q7 (AC13 Windows tilde test):** Keep as T-13a with skipif; add T-13b portable symlink; add T-13c pure unit. Resolved in AC13 amendment above. Confidence HIGH.

**Q8 (AC15 call-site enumeration):** 4 owner modules: `kb.ingest.pipeline` (`ingest_source`), `kb.query.engine` (`query_wiki`, `search_pages`), `kb.feedback.reliability` (`compute_trust_scores`). 13 patch sites / 7 test files (R1 verified). Confidence HIGH.

**Q9 (AC15 local-alias audit):** R1 audit found no intentional local-name bindings. All 13 patches are stylistic `patch("kb.mcp.core.X")` assumptions. Migration is safe. Confidence HIGH.
## Analysis
R1 verification is explicit: "No symbol exceeds 7 patch sites and none exhibit spooky-at-a-distance patterns."

**Q10 (AC17 scope — PROJECT_ROOT cleanup):** No scope creep. AC17 limited strictly to `HASH_MANIFEST`. Brainstorm default. Confidence HIGH.

**Q11 (AC18 tmp_kb_env detection):** Grep test source for `tmp_kb_env` as function parameter (D7 approach). R1 flagged that `tmp_kb_env` is NOT autouse; detection strategy unchanged because it already greps for parameter usage. Confidence HIGH.

### Brainstorm Q1-Q15 resolutions

**Q1 (AC2 read budget):** See Q2 above. `≤ len(existing_pages) + len(matched_pages)`. HIGH.

**Q2 (AC4 chunks parallel vs serial):** Serial. Preserves determinism, avoids multi-chunk lock contention. Brainstorm default. HIGH.
## Analysis
Parallel chunks would need a thread-safe log appender and deterministic merge of return dicts; serial cost is negligible for 200-title chunks.

**Q3 (AC7 pages= vs wiki_dir= precedence):** `pages=` wins when both provided; `wiki_dir` retained for log path default only. Brainstorm default. HIGH.

**Q4 (AC8 TTL filter):** No filter. AC8b provides visibility. Resolved above.

**Q5 (AC10 nested with-statements):** Use nested `with file_lock(page_path) as p: with file_lock(history_path) as h:` — aligned with cycle-18 `append_wiki_log` pattern. Given AC10 WITHDRAW decision, page is OUTER. HIGH.

**Q6 (AC11 alias name):** `manifest_key_for`. HIGH. Same as Req Q5.

**Q7 (AC13 validation of manifest_key):** No FORMAT validation beyond traversal reject. Resolved in AC12 final text. HIGH.
## Analysis
Format-level validation (e.g., "must match POSIX path regex") would couple ingest to compile's internal format and brittlen migrations. Traversal/null/length rejection is sufficient defense-in-depth.

**Q8 (AC15 MCP-local patch intent audit):** None found (R1 audit). HIGH. Same as Req Q9.

**Q9 (AC17 tmp_kb_env detection):** Grep for parameter usage. HIGH. Same as Req Q11.

**Q10 (AC19 lock-count spies):** Both spies — `file_lock` count AND `Path.read_text` count. Brainstorm default. HIGH.
## Analysis
Independent invariants: lock count pins AC5's fast-path behavior; read_text count pins AC2's amplification-reduction. Both matter; one spy obscures the other.

**Q11 (refine attempt counter):** No. Single-entry-per-refine model unchanged; AC8's `attempt_id` correlation key is internal, not a user-facing attempt counter. HIGH.

**Q12 (AC20 log format):** Count + page IDs comma-joined with 100-char cap. Brainstorm default. HIGH.
## Analysis
Inline list with cap preserves audit trail without flooding; truncation marker (`…` or `(+N more)`) at 100 chars is readable.

**Q13 (migration blast radius — kb.mcp.browse etc.):** Strictly scope AC15 to `kb.mcp.core.<callable>`. Any sibling-module discovery files a new backlog entry, not a scope expansion. HIGH.

**Q14 (manifest_key_for in `kb.__all__`):** No. Internal helper. HIGH.
## Analysis
Exposing in top-level `__all__` invites external-callers to rely on it; keep the surface minimal. Direct import from `kb.compile.compiler` is fine for internal modules.

**Q15 (keep vs deprecate single-target inject_wikilinks):** Keep. Tests and single-target callers continue working. Batch is the preferred path for new callers. No deprecation warning in cycle 19. HIGH.

---

## Final decided design (shippable ACs)

| AC | Cluster | Summary | Files |
|----|---------|---------|-------|
| AC1 | A | `inject_wikilinks_batch` signature (tuple list, `pages=` kwarg) | `compile/linker.py` |
| AC1b | A | Under-lock re-derive winning target from fresh body | `compile/linker.py` |
| AC2 | A | Read budget ≤ `len(existing_pages) + len(matched_pages)` | `compile/linker.py` (test) |
| AC3 | A | At-most-one wikilink per page per batch; longest-title tie-break | `compile/linker.py` |
| AC4 | A | `MAX_INJECT_TITLES_PER_BATCH=200` chunking | `config.py`, `compile/linker.py` |
| AC4b | A | `MAX_INJECT_TITLE_LEN=500` per-title skip + warn | `config.py`, `compile/linker.py` |
| AC5 | A | No-lock fast path for zero-match pages | `compile/linker.py` |
| AC6 | A | Pipeline switches to batch call; chunk-level try/except | `ingest/pipeline.py`, `compile/linker.py` |
| AC7 | A | `pages=` pre-loaded bundle threading | `compile/linker.py`, `ingest/pipeline.py` |
| AC8 | B | Two-phase pending → applied with `attempt_id` correlation | `review/refiner.py` |
| AC8b | B | `list_stale_pending(hours=24)` reporter helper | `review/refiner.py` |
| AC9 | B | history_lock held across page-write window (single span) | `review/refiner.py` |
| AC10 | B | Document existing `page_path FIRST, history_path SECOND` order + behavioural test | `review/refiner.py` |
| AC11 | C | `manifest_key_for` public alias for `_canonical_rel_path` | `compile/compiler.py` |
| AC12 | C | `manifest_key=` keyword-only after `*`; traversal-validated; dual-write (reservation + confirmation) | `ingest/pipeline.py` |
| AC13 | C | `compile_wiki` threads `manifest_key_for(source, raw_dir)` into `ingest_source` | `compile/compiler.py` |
| AC15 | D | MCP monkeypatch migration (13 sites, 7 files, 4 owner modules, atomic commit) | `mcp/core.py`, 7 test files |
| AC16 | D | Constant patches stay on `kb.mcp.core`; docstring + behavioural test | `mcp/core.py`, 1 test file |
| AC17 | D | Remove redundant `HASH_MANIFEST` patches at 6-file intersection | 6 test files |
| AC18 | D | Lint rule: `tmp_kb_env` + `HASH_MANIFEST` patch cohabitation fails | 1 new test file |
| AC19 | E | End-to-end batch test: lock count ≤ matched pages | 1 new test file |
| AC20 | E | Single `inject_wikilinks_batch` log line via `append_wiki_log` | `ingest/pipeline.py` |

Plus 1 retained test anchor (not a production AC):
- **AC14-anchor:** `test_cycle19_prune_base_consistency_anchor.py` — machine-enforced regression of cycle-17 AC1 shipped behavior.

**Total production ACs: 23** (20 original − AC14 dropped + AC1b + AC4b + AC8b + AC12-revised-counts-as-amendment-not-new).

---

## Dropped / amended from requirements

- **AC14 — DROP.** Fix already shipped in cycle-17 AC1 (`compiler.py:270` + `compiler.py:452` consistent). Retain `test_cycle19_prune_base_consistency_anchor.py` as machine-enforced anchor test per cycle-15 L2 DROP-with-test-anchor-retention rule.
- **AC10 — REVISED.** WITHDRAW the lock-order flip. AC10 becomes "document existing `page_path FIRST, history_path SECOND` order in docstring + add behavioural test asserting acquisition order". AC8 pending-write nests INSIDE `page_lock` + `history_lock` nest (no release/re-acquire).
- **AC12 — REVISED.** (a) keyword-only placement AFTER existing `*` sentinel (N1); (b) traversal-hardening (reject `..`, leading `/`, `\x00`, len > 512) at function entry (R1 MAJOR); (c) dual-write: `manifest_ref` threaded into BOTH `_check_and_reserve_manifest` (phase-1) AND tail confirmation (phase-2) (R2 M1).
- **AC2 — amended.** Budget rewrites to `≤ len(existing_pages) + len(matched_pages)` (was `≤ 10` blanket).
- **AC6 — amended.** Chunk-level try/except inside `inject_wikilinks_batch`; one chunk failure doesn't block remaining chunks.
- **AC8 — amended.** `attempt_id = uuid4().hex[:8]` correlation key for pending → applied/failed flip.
- **AC9 — amended.** Lock span semantic locked to (a) hold-through: single `file_lock(history_path)` span covers pending-write + page-write + applied-flip.
- **AC13 — amended.** Test split into T-13a (Windows tilde, skipif), T-13b (portable symlink, skipif), T-13c (pure unit, always runs).
- **AC16 — amended.** Keep docstring-extraction test AND add behavioural test (per user mandate).
- **AC17 — amended.** Scope is 6 files (intersection of HASH_MANIFEST + tmp_kb_env), not 12. Description correction: `tmp_kb_env` is declarative, NOT autouse.

---

## Conditions for Step 7 plan

- [ ] All 23 production ACs each map to one file-cluster task (cluster A/B/C/D/E per-file)
- [ ] ReDoS budget: ≤ 500-char titles × 200-title chunks = ~100KB alternation worst case; `re.escape` preserves linear scan
- [ ] `refiner.py` lock nest: `page_lock` (OUTER) → `history_lock` (INNER — single-span covering pending write + page write + applied flip under same lock span; release and re-acquire NOT allowed for crash-safety)
- [ ] Snapshot-binding AC16 has behavioural test via `kb.config.PROJECT_ROOT` patch (NOT docstring-only)
- [ ] AC12 dual-write: confirm `manifest_ref` threads into BOTH `_check_and_reserve_manifest` AND tail confirmation (R2 M1 fix)
- [ ] AC1b under-lock re-derive: pre-lock scan is candidate-gathering ONLY; winner picked under lock from fresh body (R2 M3)
- [ ] AC4b per-title length cap: `MAX_INJECT_TITLE_LEN=500` constant; overlength titles skipped with `log.warning`, batch continues (R2 M5)
- [ ] AC8 correlation: `attempt_id = uuid4().hex[:8]` field on pending row; flip matches by attempt_id equality
- [ ] AC13 test triplet: Windows tilde (skipif), portable symlink (skipif), pure unit (always)
- [ ] AC15 atomic commit: `kb.mcp.core` import-style refactor + 13 test patch migrations in ONE commit (D6 option c)
- [ ] AC15 drop `raising=False` from `test_v0913_phase394.py:430` during migration
- [ ] AC17 count reconciled at plan-gate grep: expected 6 files (R1 cross-reference); correct `tmp_kb_env` description from "autouse" to "declarative"
- [ ] AC19 e2e lock-count test asserts `not raised TimeoutError` to rule out stuck-lock flake
- [ ] Vacuous-gate revert-checks registered for T-2, T-4, T-6, T-12b, T-15 (all 4 callable families per R2 N2)
- [ ] All constants added to `kb.config`: `MAX_INJECT_TITLES_PER_BATCH=200`, `MAX_INJECT_TITLE_LEN=500`
- [ ] Evidence Trail sentinel discipline preserved (no changes to `save_page_frontmatter`)
- [ ] Dependabot four-gate: Step 2 baseline + Step 11 PR-diff + Step 12.5 existing-CVE patch + Step 15 late-arrival warn
