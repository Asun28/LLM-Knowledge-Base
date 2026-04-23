# Cycle 24 — Design Decision Gate (Step 5)

**Date:** 2026-04-23
**Gate:** Opus 4.7 (decision-gate mode)
**Input artifacts:**
- `docs/superpowers/decisions/2026-04-23-cycle24-requirements.md` (15 ACs)
- `docs/superpowers/decisions/2026-04-23-cycle24-threat-model.md` (T1..T10 + 7 deferred tags)
- `docs/superpowers/decisions/2026-04-23-cycle24-brainstorm.md` (A1/V1/L1/M1/E1)
- `docs/superpowers/decisions/2026-04-23-cycle24-r1-opus.md` (symbol grep-verification + 7 Q-R1 questions)
- `docs/superpowers/decisions/2026-04-23-cycle24-r2-codex.md` (edge-case + 3 top open questions)

## Analysis

The cycle-24 design surface is a "closing bounded gaps" cleanup spanning five clusters, with one cluster (Cluster E, sentinel-anchor hardening) retro-fitted after the Step-2 threat model. The five clusters sort by blast radius: doc-only (Cluster D) < lock-poll internals (Cluster C) < new-page inline evidence (Cluster A, two branches) < vector-index atomic rename (Cluster B, Windows-specific edge cases) < sentinel-anchor hardening (Cluster E, regex on user-controlled content). R1 and R2 converge on identical structural observations: (a) AC1 MUST apply to both `_write_wiki_page` branches or the exclusive-branch ingest path keeps the two-write race; (b) AC5 `_index_cache.pop` must run BEFORE `os.replace` on Windows or the target is held by a cached `sqlite3.Connection`; (c) AC9 `LOCK_POLL_INTERVAL` semantics must be pinned or two existing cycle-2 monkeypatches silently stop enforcing their contract. R2 adds three surfaces R1 missed: (d) the AC5 atomic-rename must cover BOTH the empty-pages branch and the populated branch (R2 §1 Cluster B bullet 4); (e) the AC9 backoff must cover ALL three polling sites in `file_lock` — the normal `FileExistsError` branch AND both stale-lock steal paths at io.py:322/336 (R2 §1 Cluster C bullet 2); (f) AC14 sentinel anchoring needs SPAN-limited search, not just "tail after header," or a planted sentinel elsewhere-in-tail still wins (R2 §1 Cluster E bullet 2).

The decision principles I apply below derive from the feedback-memory set and CLAUDE.md: lower blast radius wins; reversible > irreversible; internal > public API; opt-in > always-on; test behaviour > signature; divergent-fail tests are load-bearing (cycle-22 L5); deferred-promise tags must anchor to matching BACKLOG entries (cycle-23 L3). Where R1 and R2 disagree with brainstorm (e.g., R2 flagging AC13 as same-day-stale), I defer to R2's empirical check because the date assertion is verifiable. Where a decision opens a new failure mode, I add a CONDITION that Step 9 must satisfy — this keeps the load-bearing part of the design in the CONDITIONS section rather than buried in AC prose.

## VERDICT

**PROCEED** with the 15 ACs as scoped, with these amendments folded into the FINAL DECIDED DESIGN below:

- **AC1 is AMENDED** to explicitly scope to BOTH branches of `_write_wiki_page` (exclusive + non-exclusive). The single-atomic-write contract is branch-specific: non-exclusive uses `atomic_text_write(rendered_with_trail, effective_path)`; exclusive uses a single `os.write(fd, rendered_with_trail.encode("utf-8"))` + `fsync` inside the `os.open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW)` span. No `append_evidence_trail` call in either branch's new-page tail.
- **AC3 is AMENDED** (Q4) to REQUIRE a spy on `atomic_text_write` with `call_count == 1` AND a content-read assertion AND a parameterized test over `exclusive ∈ {False, True}`.
- **AC5 is AMENDED** (Q2, Q14) to require `_index_cache.pop` BEFORE `os.replace` AND apply the tmp-then-replace pattern to BOTH the empty-pages and populated-pages branches.
- **AC7 is AMENDED** (Q15) to make `db_path` keyword-only via an explicit `*` separator in the signature and use `is not None` override semantics.
- **AC8 is AMENDED** (Q5) to require `tmp_path.unlink(missing_ok=True)` inside an outer `try/except` in `rebuild_vector_index` (clean-slate on crash).
- **AC9 is AMENDED** (Q3, Q13) to pin CAP semantics for `LOCK_POLL_INTERVAL`, apply exponential backoff to ALL three polling sites (normal retry + both stale-lock steal recovery paths), and introduce `LOCK_INITIAL_POLL_INTERVAL = 0.01` as the floor.
- **AC13 is DOWNGRADED** (Q6) from date-bump to "verify-only": Step-11.5 re-audit of `pip-audit --format=json` is the load-bearing action; the BACKLOG.md 2026-04-23 stamp is a pass-through (already current, no edit needed unless re-audit shows change).
- **AC14 is AMENDED** (Q8, Q9, Q10) to SPAN-limit the sentinel search within the `## Evidence Trail` section (until the next `^## ` heading or EOF), handle CRLF/trailing-whitespace header variants, treat header-only-no-sentinel as sentinel-migration (insert sentinel at header end), and treat sentinel-only-no-header as "ignore the body sentinel, create a fresh section at EOF."
- **AC6 placement** (Q7) pinned FIRST statement inside `rebuild_vector_index` (BEFORE `_hybrid_available` gate, BEFORE `_is_rebuild_needed` gate, BEFORE `_rebuild_lock` acquire) — stale tmp cleaned even when the gates say "skip this invocation."
- **New Condition 4 to Condition 10** added (see CONDITIONS section) to pin design-gate-resolved behaviours the Step-9 plan drafter MUST map to specific Step-9 tasks.

All 15 ACs survive; none are DROPPED. Test delta revised from +13..+18 to **+16..+20** (the AC1-exclusive-branch parameterization adds 1-2 tests; AC14 span-limit adds 1-2; AC5 empty-branch adds 1).

---

## DECISIONS

## Analysis

The three highest-stakes calls are Q1, Q2, and Q3. Q1 (AC1 branch scope) is structural — if the exclusive branch is left out, the production ingest path at `pipeline.py:1056,1419` passes `exclusive=True` and both of the load-bearing summary + item writes retain the two-write race. That's not a bug-narrowing cycle; that's a bug-moving cycle. Q2 (Windows cache ordering) is where R2's observation is decisive: `_index_cache.pop` removes the DICT KEY but does NOT close `VectorIndex._conn` — a reference held elsewhere (a concurrent query thread that grabbed `get_vector_index(vec_path)` before the pop) keeps the sqlite3 handle open. On Windows that alone blocks `os.replace`. So Q2's answer is not "pop is sufficient" but "pop + explicit close of the popped instance's `_conn`." Q3 (LOCK_POLL_INTERVAL semantic) must pin CAP semantics because the two existing cycle-2 monkeypatches set 0.01 and rely on the polling floor being no higher than 0.01; if cycle 24 seeds backoff from `LOCK_INITIAL_POLL_INTERVAL` without gating on `LOCK_POLL_INTERVAL` as the cap, those tests silently keep passing (they don't spy sleeps, they just assert non-crash) while the actual behaviour drifts.

Q12 (AC10 contention depth) and Q13 (stale-lock poll coverage) are secondary but load-bearing: R2 §1 Cluster C bullet 2 explicitly flags the stale-lock recovery paths at io.py:322 and :336 that currently sleep `LOCK_POLL_INTERVAL` after unlinking. If AC9's refactor covers only the ordinary `FileExistsError` retry path, those two stale-lock sleeps retain the 50ms floor and silently fail the "exponential backoff under contention" contract in a narrow subset. Q14 (empty-pages tmp-then-replace coverage) is R2 §1 Cluster B bullet 4 — the empty-pages fast path at `embeddings.py:116` creates a fresh DB at `vec_path`, which under AC5 must route through the same tmp-then-replace flow or the atomicity contract silently excludes empty-wiki operators.

### Q1 — AC1 scope: exclusive + non-exclusive branches?

**OPTIONS:**
- (a) AC1 inline render applies ONLY to `atomic_text_write` branch (`exclusive=False`); the `exclusive=True` raw `os.write` branch keeps its post-write `append_evidence_trail` call.
- (b) AC1 inline render applies to BOTH branches: non-exclusive concatenates trail into `rendered` then calls `atomic_text_write(rendered, effective_path)`; exclusive concatenates trail into `rendered` then `os.write(fd, rendered.encode("utf-8"))` inside the O_EXCL span.
- (c) Refactor exclusive branch to use `atomic_text_write` (dropping O_EXCL reservation) so a single write path covers both.

## Analysis

Option (a) is a non-starter. Grep at `pipeline.py:1056,1419` shows both production summary and item writes pass `exclusive=True`; option (a) would leave the ACTUAL ingest path exposed to the two-write race that AC1 was written to close. That's worse than not shipping AC1 at all — it's a false sense of coverage where a test against `exclusive=False` passes while production keeps the bug. Option (c) drops the cycle-20 O_EXCL + O_NOFOLLOW + poison-unlink hardening that closed the slug-collision race; the reservation semantics are load-bearing for concurrent ingest of two sources producing the same summary slug (cycle-20 AC8 test coverage). Dropping them would re-open the race for a problem AC1 doesn't touch.

Option (b) preserves the O_EXCL reservation AND closes the two-write race in both branches. Implementation cost is one concatenation pre-`os.write` and one concatenation pre-`atomic_text_write` — both trivial. The only subtle point is that `os.write` returns the number of bytes written and a short write could leave a truncated payload; the existing cleanup path (`os.unlink` on any exception after O_EXCL succeeded, `pipeline.py:378-386`) already handles this. The larger single payload raises the ENOSPC probability marginally, but ENOSPC on a few hundred added bytes is a disk-space problem not a correctness problem — the poison-unlink path fires and the slot is freed. Option (b) is clearly the lower-blast-radius choice that honours both AC1 and the cycle-20 invariant.

**DECIDE:** (b) — inline render applies to BOTH branches.
**RATIONALE:** Only option (b) closes the two-write race on the production ingest path without dropping cycle-20's O_EXCL reservation.
**CONFIDENCE:** high.

### Q2 — AC5 `_index_cache.pop` vs connection close: is pop-before-replace sufficient?

**OPTIONS:**
- (a) `_index_cache.pop(str(vec_path), None)` BEFORE `os.replace`. Rely on Python GC to close `_conn` when the popped `VectorIndex` becomes unreachable.
- (b) Pop the cache entry AND explicitly call `popped._conn.close()` (with `try/except` for `None` and already-closed) BEFORE `os.replace`.
- (c) Pop AFTER replace (current code); accept Windows failure mode as a known residual.

## Analysis

Option (c) is the status quo that AC5's Condition 2 explicitly rejects. On Windows NTFS, `os.replace` requires no concurrent handles on the target — any cached `_conn` blocks the rename with `PermissionError [WinError 5]`. The cycle-20 taxonomy would surface this as `OSError`, the compile-tail `log-and-continue` wrapper would swallow it, and the operator sees "Vector index rebuilt" log line never firing. Silent correctness regression.

Option (a) is what the requirements Condition 2 literally asks for, but R2 §2 Cluster B explicitly flags that `_index_cache.pop` removes the DICT REFERENCE but does NOT guarantee the `VectorIndex._conn` is closed — another live reference (a concurrent `get_vector_index(vec_path)` caller that grabbed the instance before the pop, then the query thread holds it while iterating results) keeps the sqlite3 handle open. Python GC runs ONLY when the last reference drops; under concurrent query load that's non-deterministic. So option (a) narrows but does not close the Windows failure mode.

Option (b) adds one explicit `.close()` call. `sqlite3.Connection.close()` is idempotent (calling twice is a no-op returning None); if `_conn is None` (never-ensured instance), we skip. The popped instance is no longer in the cache so future `get_vector_index` calls build a fresh instance with a fresh `_conn` against the newly-replaced DB — this is the exact lifecycle the cycle-20 cache invariant expects. Implementation cost: 4 lines of code including the None-check and try/except. Eliminates the Windows failure mode for the common case where `_index_cache` held exactly the instance being replaced. Residual: another thread holding its own strong reference can still pin the old fd, but that's a pre-existing concurrent-query-during-rebuild race not widened by cycle 24.

**DECIDE:** (b) — pop AND close `_conn` before `os.replace`, guarded for None and double-close.
**RATIONALE:** Only explicit close bounds the Windows handle-held failure mode to genuinely concurrent-query races, which are a separate backlog item.
**CONFIDENCE:** high.

### Q3 — AC9 `LOCK_POLL_INTERVAL` semantics: CAP, fallback, or separate constant?

**OPTIONS:**
- (a) `LOCK_POLL_INTERVAL` is the CAP on the exponential schedule. Monkeypatching to 0.001 clamps ALL sleeps to ≤ 0.001. `LOCK_INITIAL_POLL_INTERVAL = 0.01` is a separate floor.
- (b) `LOCK_POLL_INTERVAL` is a compatibility fallback that takes effect ONLY when exponential backoff would exceed it; otherwise backoff dominates.
- (c) Deprecate `LOCK_POLL_INTERVAL`; introduce a brand-new `LOCK_BACKOFF_CAP`; emit a DeprecationWarning.

## Analysis

Option (c) breaks the two existing cycle-2 tests (`test_backlog_by_file_cycle2.py:172,210`) that monkeypatch `LOCK_POLL_INTERVAL = 0.01`. Those tests don't assert sleep values directly — they rely on the monkeypatched attribute to shrink the polling floor so the test finishes fast. Under (c), the monkeypatch is silently ignored (it sets a deprecated attribute), the tests slow down to wall-clock retries, and CI times flap. Migration cost per feedback_migration_breaks_negatives and feedback_signature_drift_verify.

Option (b) is the narrower-behaviour variant — it only uses `LOCK_POLL_INTERVAL` in the tail of the schedule. But it creates a confusing mental model: the constant's meaning changes based on whether the backoff has "climbed above it" yet. Tests monkeypatching to 0.001 would see sleeps at 0.01 (the floor from `LOCK_INITIAL_POLL_INTERVAL`) and 0.02, which exceed 0.001 — so the cap never fires. This silently breaks the existing test intent. It also makes the contract hard to document ("it's the cap... except when the backoff hasn't reached it yet, in which case it's ignored") without confusing downstream implementers.

Option (a) preserves the existing test behaviour exactly: monkeypatch 0.01 → the cap is 0.01 → exponential climbs 0.01 → 0.02 → 0.04 → ... all clamped to ≤ 0.01 → effectively fixed 0.01 polls. That matches the behaviour cycle-2 tests depended on (fixed 0.01 polling under monkeypatch). The test `test_cycle24_lock_backoff::test_module_attribute_monkeypatch_honored` pins the CAP contract by monkeypatching 0.001 and asserting all observed `time.sleep` values are ≤ 0.001. Crystal-clear documentation: "`LOCK_POLL_INTERVAL` is the polling-interval ceiling; the actual interval is `min(LOCK_INITIAL_POLL_INTERVAL * 2**attempt, LOCK_POLL_INTERVAL)`."

**DECIDE:** (a) — `LOCK_POLL_INTERVAL` is the CAP.
**RATIONALE:** Only option (a) preserves existing cycle-2 test monkeypatch semantics AND provides an unambiguous mental model for the polling schedule.
**CONFIDENCE:** high.

### Q4 — AC3 spy-form mandate: spy + count vs content-read alone?

**OPTIONS:**
- (a) Content-read alone (AC3 as written): ingest new source, read page, assert `## Evidence Trail` + sentinel + initial entry present.
- (b) Spy on `atomic_text_write` with `call_count == 1` AND content-read, parameterized over `exclusive ∈ {False, True}`.
- (c) Spy alone with call-count and call-args assertion.

## Analysis

Option (a) has a known vacuous-fail mode: if AC1 is partially reverted (inline render kept but `append_evidence_trail` call also restored), the final page content still contains `## Evidence Trail + sentinel + entry` because the append_evidence_trail appends another entry — it doesn't remove the inline one. R1 §4 Q-R1-1 flags this exactly. Content-only AC3 would silently pass a partial revert.

Option (c) flips the other way: spy without content-read would pass if `atomic_text_write` is called once but the rendered payload is missing the trail section (e.g., implementer forgets the concatenation). Content-only or spy-only are each vacuous in one direction.

Option (b) combines both: `call_count == 1` fails the partial revert (two calls: one for body, one inside the nested `append_evidence_trail`), content-read fails the missing-concatenation bug. The parameterization over `exclusive` is MANDATORY per Q1's decision — AC3 must cover BOTH branches. For the `exclusive=True` branch, the spy target shifts from `atomic_text_write` to `os.write` (or equivalent), so the test helper needs a branch-specific spy. R1 §4 Q-R1-1 and the `feedback_inspect_source_tests` memory both argue for behaviour-test-not-signature-test; option (b) is the behavioural form.

**DECIDE:** (b) — spy on `atomic_text_write` with `call_count == 1` AND content-read, parameterized over `exclusive ∈ {False, True}` (with branch-specific spy target).
**RATIONALE:** Only the dual assertion + parameterization guarantees divergent-fail on both revert shapes and on both production code paths.
**CONFIDENCE:** high.

### Q5 — AC8 tmp disposition on crash: unlink on exception or defer to AC6?

**OPTIONS:**
- (a) Wrap the `.build()` + `os.replace` in a `try/except` inside `rebuild_vector_index`; on exception, `tmp_path.unlink(missing_ok=True)` then re-raise (clean-slate policy).
- (b) Leave `.tmp` on disk after crash; rely on AC6's next-invocation unconditional unlink to clean it.
- (c) Wrap in try/except; log-and-continue with `logger.error` without re-raise (swallow failure).

## Analysis

Option (c) is a no-go — it silently hides rebuild failures from callers (compile-tail, ingest-tail). The existing log-and-continue is at the CALLER level (`compile_wiki` wraps `rebuild_vector_index` in `try/except Exception: logger.warning`), which is the right layering. Swallowing inside `rebuild_vector_index` double-swallows.

Option (b) trusts the next run's AC6 cleanup. This works for the mainline case but has a two-run failure mode: if the first run's crash leaves `tmp_path` with a large partial DB, a disk-space-bounded operator could see ENOSPC errors on unrelated writes until the next `rebuild_vector_index` invocation fires the AC6 cleanup. On a CI or one-shot-ingest machine that may never happen. Leaving partial-state DBs on disk is also operationally ambiguous — is this tmp a valid newer build that didn't replace yet, or a partial crash? R2 §2 Cluster B bullet 4 calls this out.

Option (a) produces clean disk state after every `rebuild_vector_index` exit: either the production DB was replaced, or it wasn't and no tmp remains. The caller sees the exception surface via the existing log-and-continue. Implementation cost: 5 lines of try/except. The "re-raise" preserves the existing exception semantics for callers. AC6's unconditional unlink at entry becomes the belt-and-suspenders backup for the crash-between-log-and-raise window (SIGKILL mid-except), not the primary cleanup — which is a healthier layering.

**DECIDE:** (a) — try/except wraps `.build()` + `os.replace`; unlink tmp on exception + re-raise.
**RATIONALE:** Clean-slate-on-exit produces unambiguous disk state; AC6 remains as belt-and-suspenders, not the primary cleanup.
**CONFIDENCE:** high.

### Q6 — AC13 no-op verify: DROP-DOWNGRADE or full date-bump?

**OPTIONS:**
- (a) DROP-DOWNGRADE: AC13 becomes "Step-11.5 re-audit `pip-audit --strict --format=json`; if fix_versions empty and date already stamped 2026-04-23, no-op."
- (b) Full date-bump: edit BACKLOG.md line 133 to 2026-04-23 regardless; the edit is a textual no-op but documents "verified on cycle-24 date."
- (c) Keep AC13 as written (bump to 2026-04-23); treat as a real edit for audit traceability.

## Analysis

R1 §4 Q-R1-3 observed that BACKLOG.md line 133 already carries "No patched upstream release as of 2026-04-23"; grep confirms this at line 133 of the backlog. A textual bump (b) would be a diff with zero content change — confusing in `git log` and wasteful. Option (c) treats the AC as a real edit but, given the date is already current, produces an empty diff on BACKLOG.md for AC13's line.

Option (a) downgrades the AC to the load-bearing action (Step-11.5 `pip-audit` re-run) and drops the redundant textual edit. This matches the spirit of cycle-22 L4 ("advisories can arrive mid-cycle"): the re-audit IS the contract, the BACKLOG date is the record of the re-audit result. No-op-if-clean is the right shape.

**DECIDE:** (a) — AC13 downgrades to verify-only; Step-11.5 re-audit is the load-bearing action; no BACKLOG edit unless re-audit shows change.
**RATIONALE:** The textual bump is redundant with the existing date stamp; the load-bearing action is the re-audit.
**CONFIDENCE:** high.

### Q7 — AC6 placement: first statement in `rebuild_vector_index`, or inside `_rebuild_lock`?

**OPTIONS:**
- (a) FIRST statement, BEFORE `_hybrid_available` gate, BEFORE `_is_rebuild_needed` gate, BEFORE `_rebuild_lock` acquire.
- (b) Inside `_rebuild_lock`, AFTER the double-check mtime gate, BEFORE the `load_all_pages`.
- (c) Inside `_rebuild_lock`, AS FIRST statement inside the lock (before the double-check).

## Analysis

Option (b) misses the case where a crashed-prior-run tmp sits on disk and the current invocation's gates say "no rebuild needed." The tmp persists indefinitely. That's the exact class of bug T1 in the threat model is trying to close.

Option (c) acquires `_rebuild_lock` every time to perform the unlink, even when the mtime gate would skip the rebuild. On busy systems this adds un-needed lock contention to a no-op path. It also interleaves with the cross-process residual (two operators running `rebuild_vector_index(force=True)` concurrently each unlink the tmp — last-writer-wins on the unlink is a no-op, but combined with the subsequent build-to-tmp they collide on sqlite CREATE VIRTUAL TABLE).

Option (a) runs the unlink unconditionally, BEFORE any gate. A stale tmp from a prior crash is cleaned on the very next invocation of `rebuild_vector_index`, even if that invocation is a fast-path mtime-gated skip. Implementation cost: 2 lines at top of function. The unconditional unlink does not interact with `_rebuild_lock` because `Path.unlink(missing_ok=True)` is a single syscall on the tmp path which no other concurrent rebuild would be writing to yet (two concurrent rebuilders racing the unlink is a no-op tie). For the `_hybrid_available=False` case, cleaning a pre-existing tmp from a prior install with hybrid enabled is the right operator experience: the operator disabled hybrid, the stale tmp is gone, no surprise left.

**DECIDE:** (a) — FIRST statement, before all gates and lock.
**RATIONALE:** Only option (a) cleans stale tmp on every subsequent invocation regardless of whether the current call would rebuild.
**CONFIDENCE:** high.

### Q8 — AC14 span-limited search scope: section span or tail after header?

**OPTIONS:**
- (a) Section span only: find `^## Evidence Trail\s*\r?\n` header, then search for sentinel only until the NEXT `^## ` heading or EOF. Handles CRLF/trailing-space variants.
- (b) Tail after header: find header, search for sentinel in `content[header.end():]` (whole rest of file).
- (c) Header span plus lookahead: find header, search for sentinel in `content[header.end():header.end() + N]` for bounded N.

## Analysis

R2 §1 Cluster E bullet 2 is decisive: "Searching 'within the bytes following that header' can still find a planted sentinel in content after the real header but before the machine sentinel. The search should be limited to the actual Evidence Trail section span, not the entire tail of the document." Option (b) doesn't fully close T5 — an attacker who plants a sentinel AFTER `## Evidence Trail` but BEFORE the real machine sentinel still wins. Option (c) bounds by character count which is arbitrary and fragile (what if the section has 200 legitimate entries?).

Option (a) uses the markdown section structure: a `## Evidence Trail` section ends at the next `## ` heading or EOF. Within that span, search for the machine sentinel. Any sentinel-literal OUTSIDE the section (in body, in frontmatter, in later sections) is inert. The regex handles CRLF (`\r?\n`) and trailing whitespace (`[ \t]*` before the newline) per the existing lint convention. Implementation cost: one additional regex (`re.search(r"^##\s", ...)` from header end) and `content[header_end:next_section]`.

Residual: `## ` inside fenced-code blocks within the Evidence Trail section would falsely terminate the section span. R2 §1 Cluster E bullet 1 flags this. Mitigation: the Evidence Trail section is MACHINE-WRITTEN per CLAUDE.md's sentinel-discipline convention — it does not contain fenced-code blocks by construction. A hand-edit that adds a fenced block with `## ` inside would be a manual-auditor problem, not an attack surface, and the Evidence Trail Convention in CLAUDE.md already documents "sentinel is machine-maintained." Acceptable residual.

**DECIDE:** (a) — span-limited search, CRLF + trailing-whitespace tolerant.
**RATIONALE:** Only section-span bounding closes the T5 threat fully; fenced-code-in-evidence-trail is a manual-editor concern outside cycle-24 scope.
**CONFIDENCE:** high.

### Q9 — AC14 header-only-no-sentinel fallback: sentinel migration or anchor-only?

**OPTIONS:**
- (a) Sentinel migration: when legacy page has `## Evidence Trail` header but no sentinel inside the section, insert sentinel at header-end (preserves `append_evidence_trail` first-write contract of inserting new entries after sentinel).
- (b) Anchor-only: search within the section span without planting a sentinel; insert new entry at header-end with a newline.
- (c) Reject: raise an error to force operator migration.

## Analysis

Option (c) is a non-starter — legitimate pre-cycle-1 H12 pages may exist without sentinels (the H12 fix shipped in Phase 4.5 HIGH cycle 1 and predates sentinel emission at first write). Rejecting them breaks `_update_existing_page` ingest.

Option (b) works but creates an inconsistent on-disk shape: some pages have sentinels (post-cycle-24 first-writes plus migrated pages), some do not (pages that got appends before cycle 24's sentinel-at-header-end migration). Future readers of the file cannot tell which is which. Append-ordering drifts.

Option (a) is exactly what cycle-1 H12 already does in `append_evidence_trail` today (see `evidence.py:96-102`): when header present but no sentinel, place sentinel at `trail_match.end()`. Cycle 24's AC14 just needs to preserve this path while adding the span-limited search. The behaviour becomes deterministic: every append to a page without a sentinel ADDS one at header-end as a side effect. Subsequent appends find the sentinel and insert after it. One-shot migration on first append.

**DECIDE:** (a) — sentinel migration (insert at header end on first append to legacy page).
**RATIONALE:** Matches existing cycle-1 H12 behaviour; makes on-disk shape converge to sentinel-present after one append per page.
**CONFIDENCE:** high.

### Q10 — AC14 sentinel-only-no-header fallback: ignore body sentinel or preserve it?

**OPTIONS:**
- (a) Ignore the body sentinel; create a fresh `## Evidence Trail` section at EOF with its own sentinel.
- (b) Preserve the body sentinel; treat it as implicit section marker (current `append_evidence_trail` behaviour).
- (c) Emit lint warning: "page has sentinel without header — operator action required."

## Analysis

A page with a sentinel but no `## Evidence Trail` header is either (i) a cycle-1 H12 transitional artifact (unlikely — H12 plants header-then-sentinel atomically), or (ii) an attacker-planted body sentinel. There is no legitimate state where a sentinel exists in isolation. Under AC14's section-span search (Q8 option a), a sentinel outside any `## Evidence Trail` span is STRUCTURALLY IGNORED — the span-search never reaches it. So the fallback path triggered here is the `else` branch of the "no `## Evidence Trail` header" check.

Option (b) would treat the body sentinel as valid and inject new entries at the attacker-chosen location — exactly the T5 attack path AC14 exists to close. Dispositive against (b).

Option (c) is an improvement over (b) but defers the fix to a lint cycle. The ingest path at the moment of append cannot block indefinitely on operator action. Ingest must make forward progress.

Option (a) aligns with AC14's "attacker-planted body sentinel is ignored" contract. The ingest creates a fresh `## Evidence Trail` section at EOF with a new sentinel. The attacker-planted sentinel remains as dead markdown content in the body — a stray HTML comment, visually invisible in Obsidian rendering. Optional future lint check (deferred-to-backlog) can flag such pages for operator cleanup.

**DECIDE:** (a) — ignore the body sentinel; create a fresh section at EOF.
**RATIONALE:** Only option (a) aligns with AC14's attacker-ignore contract; lint-warning is a future-cycle improvement, not a blocker.
**CONFIDENCE:** high.

### Q11 — New BACKLOG entries from threat-model §6: tag-by-tag action?

**OPTIONS / Enumeration:**

| Tag | Action | Rationale |
|---|---|---|
| `§Phase 4.5 MEDIUM — utils/io.py fair-queue lock` (T3 residual) | **NEW BACKLOG entry** | Cycle-24 AC9 removes the 50ms floor but does not add fairness; starvation under N-waiter contention persists. |
| `§Phase 4.5 HIGH — ingest/evidence.py sentinel-anchor hardening` (T5) | **NO BACKLOG entry needed** | AC14 ships the full anchor hardening this cycle; there is nothing left to defer. |
| `§Phase 4.5 HIGH — ingest/pipeline.py _update_existing_page single-write consolidation` (T7 item 2) | **UPDATE existing** line 147 entry (narrowing scope: AC2 addressed the error-surfacing side; consolidation still deferred). |
| `§Phase 4.5 HIGH — _write_wiki_page exclusive-branch evidence collapse` (T7 item 3) | **NO BACKLOG entry needed** | Q1's decision scopes AC1 to BOTH branches, closing the exclusive-branch gap in-cycle. |
| `§Phase 4.5 HIGH-Deferred — vector-index lifecycle sub-items 2/3/4` (cold-load, dim-mismatch, cross-thread) | **KEEP existing** line 109 entry untouched. The cycle-24 atomic rebuild (sub-item 1) is shipped and can be stricken from the bundle description in a follow-up edit note. |
| `§Phase 4.5 HIGH — utils/io.py atomic_json_write` (M3 JSONL migration) | **KEEP existing** line ~127 entry untouched. |
| `§Phase 5 pre-merge` | **KEEP existing** lines 173+ untouched per user instruction. |
| `§Phase 4.5 MEDIUM M2 per-source rollback` | **KEEP existing** entry untouched. |
| `§Phase 4.5 MEDIUM M10 full IndexWriter` | **KEEP existing** entry untouched. |
| `§Phase 4.5 HIGH — rebuild_indexes .tmp awareness` (R2 §1 Cluster B bullet 8) | **NEW BACKLOG entry** | cycle-23 `rebuild_indexes` deletes the vector DB but not `.tmp`. Under cycle-24 AC5/AC6, the next rebuild cleans `.tmp`, but a belt-and-suspenders `rebuild_indexes` awareness would be cleaner. Low-severity follow-up. |
| HIGH structural items (naming inversion, state-store fan-out, shared graph cache, async MCP, tests freeze-and-fold, conftest leak surface) | **KEEP existing** entries untouched. |

## Analysis

The tag-by-tag action list above consolidates R1 §4 Q-R1-7 + threat-model §6 + R2 §2 Cluster B bullet 8. The net effect of cycle 24 is ONE net-new BACKLOG entry (fair-queue lock from T3 residual) plus ONE narrowing update (line 147 for `_update_existing_page` consolidation), plus one optional low-severity new entry for `rebuild_indexes` tmp-awareness. Everything else is already covered in BACKLOG or closed by the in-cycle ACs.

**DECIDE:** Execute the table above in Step 12 doc-update phase. AC11 handles the cycle-23-multiprocessing DELETE. Step 12 also adds the fair-queue-lock NEW entry, narrows line 147 per T7 item 2, and adds the `rebuild_indexes` tmp-awareness NEW entry.
**RATIONALE:** Cycle-23 L3 load-bearing contract requires every deferred tag have a matching BACKLOG entry; the table enumerates exactly which actions satisfy the grep-checklist.
**CONFIDENCE:** high.

### Q12 — AC10 contention depth: ≥2 sleeps AND exponential schedule pattern?

**OPTIONS:**
- (a) Assert `len(sleep_calls) >= 2` AND assert the sleep values match the exponential schedule (e.g., `[0.01, 0.02, 0.04, ...]` capped at `LOCK_POLL_INTERVAL`).
- (b) Assert `len(sleep_calls) >= 2` only (count without pattern).
- (c) Assert exponential pattern without count constraint (pattern must match observed values).

## Analysis

R1 §4 point about AC10 PARTIAL-form: "A single-thread test that never enters the retry loop would vacuously pass." Option (b) fails to pin the exponential schedule — a regression that reverts to fixed polling (all sleeps at 0.05) would pass the count check but fail the backoff contract silently. Option (c) without count constraint could technically pass with zero sleeps (empty list trivially matches empty pattern).

Option (a) is the dual assertion: `len(sleep_calls) >= 2` guarantees the retry loop actually executed, AND the pattern match guarantees the schedule is exponential. Implementation: capture sleeps via `monkeypatch.setattr("kb.utils.io.time.sleep", spy_sleep)` with `spy_sleep = MagicMock()`; after the contended acquire, assert `spy_sleep.call_count >= 2` and `[call.args[0] for call in spy_sleep.call_args_list] == [0.01, 0.02, 0.04, 0.05, 0.05, ...]` (truncated to actual observed length). The test must induce ACTUAL contention via a seeded `.lock` file trick (existing cycle-2 pattern) OR a second-thread lock holder.

**DECIDE:** (a) — ≥2 sleeps AND exponential schedule pattern match.
**RATIONALE:** Only the dual assertion divergent-fails both the "never retried" and "reverted to fixed" regression shapes.
**CONFIDENCE:** high.

### Q13 — Stale-lock poll-branch coverage: does AC9 apply to all polling sites?

**OPTIONS:**
- (a) AC9 exponential backoff applies to all three current sites: the normal `FileExistsError` retry at io.py:347, the stale-lock steal recovery at io.py:322 (ProcessLookupError path), AND the Windows stale-lock steal at io.py:336 (OSError path).
- (b) AC9 applies only to the normal retry path at io.py:347; stale-lock recovery retains fixed `LOCK_POLL_INTERVAL`.
- (c) AC9 applies only to the normal path; stale-lock recovery uses `LOCK_INITIAL_POLL_INTERVAL` (fixed at the floor).

## Analysis

Option (b) leaves the stale-lock recovery at 50ms fixed. Under a scenario where a process crashed with a stale lock AND multiple waiters are polling, the first waiter to time out performs the steal + sleeps 50ms + continues. During that 50ms, other waiters continue polling at backoff-schedule intervals. The stale-lock recovery path is cold (infrequent), but the 50ms floor on this path becomes the new lower bound on re-acquire latency for the specific "crashed-holder-recovery" case. Retaining 50ms here while reducing it elsewhere is inconsistent.

Option (c) uses the fixed floor (10ms) on the recovery path. Simpler than (a) but loses the backoff benefit if two recovery-waiters race a stale-steal in quick succession (`ProcessLookupError` fires twice consecutively — rare but possible).

Option (a) applies backoff uniformly to all three sites. `attempt_count` is tracked in the outer retry loop and consulted at every `time.sleep` call, whether normal-retry or stale-steal-recovery. Implementation: replace each `time.sleep(LOCK_POLL_INTERVAL)` with `time.sleep(_compute_backoff(attempt_count))` and increment `attempt_count` after each sleep. The three sites share the same retry-counter because they're inside the same outer `while not acquired` loop.

**DECIDE:** (a) — exponential backoff uniformly applies to all three polling sites.
**RATIONALE:** Consistency of the contract across paths; retaining 50ms fixed on stale-lock recovery creates a subtle performance asymmetry without correctness benefit.
**CONFIDENCE:** medium — the stale-lock paths are cold-path; R2's concern about them being under-covered is slightly overstated but erring on uniform is the simpler mental model.

### Q14 — AC5 empty-pages branch: tmp-then-replace coverage?

**OPTIONS:**
- (a) Both branches (empty-pages at embeddings.py:116 and populated-pages at embeddings.py:133) use the tmp-then-replace pattern.
- (b) Only populated-pages branch uses tmp-then-replace; empty-pages keeps direct `VectorIndex(vec_path).build([])`.
- (c) Empty-pages branch skips the build entirely (just unlink `vec_path` if pages is empty).

## Analysis

Option (b) creates an inconsistent failure mode: a crash mid-empty-rebuild (rare, but `build([])` still opens a sqlite3 connection, executes `CREATE VIRTUAL TABLE`, commits) leaves `vec_path` in a partial-table state. The empty-pages case is infrequent but not irrelevant — a fresh `wiki_dir` with no pages (e.g., after `kb rebuild-indexes`) triggers it. Retaining direct in-place write for the empty case leaves a small but real crash-safety gap.

Option (c) changes the semantics of `VectorIndex` for empty wikis: previously the file exists with empty virtual table; under (c) the file may not exist. Downstream `get_vector_index` + `query` must handle "file-absent" gracefully — currently they handle "file-present-with-empty-table." This is a downstream surface change not scoped by cycle 24.

Option (a) applies the same tmp-then-replace pattern uniformly. Both branches become: build to `tmp_path`, pop cache, close `_conn`, `os.replace(tmp_path, vec_path)`. Implementation cost: the existing 2 lines at line 116-117 become the same 4-line pattern as the populated branch. No semantics drift.

**DECIDE:** (a) — both branches use tmp-then-replace.
**RATIONALE:** Only uniform application closes the crash-safety gap in the empty-pages branch without introducing downstream semantics drift.
**CONFIDENCE:** high.

### Q15 — AC7 signature concern: positional-or-keyword vs keyword-only?

**OPTIONS:**
- (a) Keyword-only: `def build(self, entries, *, db_path: Path | None = None)`. The `*` separator forces callers to pass `db_path=<path>`.
- (b) Positional-or-keyword (default): `def build(self, entries, db_path: Path | None = None)`. Allows `obj.build(entries, Path("x.db"))`.
- (c) Positional-or-keyword with documentation only ("use `db_path=` keyword" in docstring).

## Analysis

Current `VectorIndex.build` has signature `(self, entries)`. Zero callers pass a second positional per the R1 monkeypatch enumeration. Migration is purely additive.

Option (b) admits future callers accidentally passing `build(entries, some_other_value)` that gets interpreted as `db_path` — a subtle typo that would become a path-redirect bug (sqlite3.connect succeeds on the typo path, wrong file replaced). The cost of keyword-only in migration-risk terms is zero (no existing caller passes positionally) and the hardening value is real.

Option (c) relies on docstring discipline. Future plugin authors who don't read the docstring positional their way into the bug.

Option (a) uses the `*` separator to enforce keyword-only at the Python level. `inspect.signature(VectorIndex.build).parameters['db_path'].kind == KEYWORD_ONLY` is a signature assertion the test can pin. The R1-recommended `db_path is not None` override check (not truthy-coalesce) is orthogonal and preserved.

**DECIDE:** (a) — keyword-only via `*` separator; `is not None` override semantics.
**RATIONALE:** Zero migration cost (no existing positional callers), defeats future-caller typo bugs.
**CONFIDENCE:** high.

---

## CONDITIONS (Step 09 must satisfy)

These are the load-bearing test-coverage requirements. Per cycle-22 L5, design-gate CONDITIONS are contracts, not footnotes. Each bullet is a test/implementation assertion that MUST survive into the Step-9 task breakdown.

1. **AC1 applies to BOTH branches of `_write_wiki_page`.** The `exclusive=True` branch (`os.open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW)` + `os.write(fd, rendered.encode("utf-8"))`) AND the `exclusive=False` branch (`atomic_text_write(rendered, effective_path)`) must both render body + evidence trail inline and MUST NOT call `append_evidence_trail` in the new-page tail.
2. **AC5 ordering: `_index_cache.pop(str(vec_path), None)` AND `popped._conn.close()` MUST happen BEFORE `os.replace(tmp, vec_path)`.** The close call is guarded with `if popped is not None and popped._conn is not None` and wrapped in `try/except` to handle already-closed connections. This covers the Windows-handle-held failure mode; POSIX tolerates the ordering but the code path is uniform cross-platform.
3. **AC9 `LOCK_POLL_INTERVAL` is the CAP.** Monkeypatching `kb.utils.io.LOCK_POLL_INTERVAL = 0.001` MUST clamp every observed `time.sleep` call within `file_lock` to `<= 0.001`. A new `LOCK_INITIAL_POLL_INTERVAL = 0.01` module constant controls the backoff floor. Both constants are read at CALL TIME (attribute access inside the retry loop), not snapshotted at function entry — preserves existing monkeypatch-at-module-attribute semantics.
4. **AC3 dual-assertion + parameterization.** The new-page regression test (`test_cycle24_evidence_inline_new_page.py` or equivalent) MUST parameterize over `exclusive ∈ {False, True}` and for EACH parameter assert (i) the appropriate spy target (`atomic_text_write` for non-exclusive, `os.write` wrapper for exclusive) was called exactly once, AND (ii) the on-disk content contains `## Evidence Trail\n<!-- evidence-trail:begin -->\n- YYYY-MM-DD | source | Initial extraction: <page_type> page created`.
5. **AC5 tmp-then-replace applies to both branches (empty-pages + populated-pages).** Both `embeddings.py:116` (empty) and `embeddings.py:133` (populated) go through: `tmp_path = vec_path.parent / (vec_path.name + ".tmp"); VectorIndex(vec_path).build(entries, db_path=tmp_path); <pop+close>; os.replace(tmp_path, vec_path)`.
6. **AC8 tmp cleanup on crash.** The `.build()` + `os.replace` sequence is wrapped in `try/except`; on exception `tmp_path.unlink(missing_ok=True)` executes BEFORE the re-raise. Test `test_cycle24_vector_atomic_rebuild.py::test_crash_during_build_leaves_no_tmp` monkeypatches `VectorIndex.build` to raise mid-insertion, calls `rebuild_vector_index(force=True)`, asserts `vec_path` is unchanged (or absent-if-was-absent) AND `tmp_path` does not exist post-exception.
7. **AC9 backoff applies to ALL THREE polling sites in `file_lock`.** The normal `FileExistsError` retry path (io.py:347), the `ProcessLookupError` stale-steal path (io.py:322), AND the `OSError` Windows stale-steal path (io.py:336) all use `time.sleep(min(LOCK_INITIAL_POLL_INTERVAL * (2 ** attempt_count), LOCK_POLL_INTERVAL))` and increment `attempt_count`.
8. **AC10 sleep-spy dual assertion.** The contention test asserts `spy.call_count >= 2` AND the observed sleep sequence matches `[0.01, 0.02, 0.04, 0.05, 0.05, ...]` (or the chosen exponential pattern capped at `LOCK_POLL_INTERVAL`). The test induces real contention via a seeded `.lock` file trick — NOT via `multiprocessing.Event` alone (which could pass without entering the retry loop).
9. **AC14 section-span-limited search.** The sentinel-search regex span is bounded by `^## Evidence Trail[ \t]*\r?\n` header on one side and `^## ` (or EOF) on the other. The header-only-no-sentinel case plants sentinel at header-end (migration). The sentinel-only-no-header case IGNORES the body sentinel and creates a fresh `## Evidence Trail` section at EOF with its own sentinel.
10. **AC15 regression test covers FOUR scenarios.** (i) body-planted sentinel BEFORE real `## Evidence Trail` section (T5 original); (ii) body-planted sentinel INSIDE a different section (e.g., under `## References`) BEFORE the real `## Evidence Trail`; (iii) CRLF-line-ending header with trailing whitespace; (iv) sentinel-only-no-header legacy page (expect fresh section created, body sentinel ignored).
11. **AC7 signature assertion.** Test asserts `inspect.signature(VectorIndex.build).parameters['db_path'].kind == inspect.Parameter.KEYWORD_ONLY` AND `.default is None`. Behavioral test passes explicit `db_path=<tmp_path>` and asserts the DB file appears at that path.
12. **AC2 late-bind + redaction assertion.** Test imports `kb.ingest.pipeline as pipeline_mod` and monkeypatches `pipeline_mod.append_evidence_trail` (NOT `kb.ingest.evidence.append_evidence_trail`) because `pipeline.py:31` imports the symbol at module load. The raised `StorageError` is asserted via `isinstance(err, pipeline_mod.StorageError)` (late-bound). Test also asserts `str(err) == "evidence_trail_append_failure: <path_hidden>"` to pin the redaction contract.
13. **BACKLOG-edit cross-reference (deferred-promise grep).** Step-12 doc update MUST result in BACKLOG.md containing: (a) deletion of line 111 cycle-23-multiprocessing entry; (b) NEW `§Phase 4.5 MEDIUM utils/io.py fair-queue lock` entry; (c) NEW `§Phase 4.5 HIGH rebuild_indexes .tmp awareness` entry; (d) narrowed line 147 (`_update_existing_page` consolidation still deferred, note AC2 landed). Step-11 Codex grep-checklist per threat-model §7 MUST pass on the post-edit BACKLOG.
14. **CVE re-audit (AC12 + AC13).** Step 11.5 MUST run `pip-audit --strict --format=json > /tmp/cycle-24-cve-post.json` and diff against a Step-2 baseline. Diskcache CVE AC12 bumps the BACKLOG.md date to 2026-04-23 (re-check is required; the BACKLOG edit on line 130 is real). Ragas CVE AC13 is VERIFY-ONLY: the 2026-04-23 date is already stamped at line 133; re-audit must confirm `fix_versions` empty and no BACKLOG edit is required unless re-audit shows change (in which case Step-11.5 fix(deps) commit bumps requirements.txt).

---

## FINAL DECIDED DESIGN (15 ACs with clarifications folded in)

### Cluster A — evidence-trail reliability

**AC1 (AMENDED)** — `_write_wiki_page` single-write inline render for BOTH branches. The `exclusive=False` branch renders `rendered = frontmatter.dumps(post, sort_keys=False) + "\n" + f"\n## Evidence Trail\n{SENTINEL}\n{format_evidence_entry(today, source_ref, f'Initial extraction: {page_type} page created')}\n"` and calls `atomic_text_write(rendered, effective_path)`. The `exclusive=True` branch uses the SAME rendered string and calls `os.write(fd, rendered.encode("utf-8"))` + `os.fsync(fd)` inside the existing `os.open(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW)` span. Neither branch calls `append_evidence_trail` in its new-page tail. Uses `SENTINEL` + `format_evidence_entry` from `kb.ingest.evidence` — NO inline sentinel-string literal duplication. Extract helper `render_initial_evidence_trail(source_ref, action, entry_date=None) -> str` in `evidence.py` if desirable for DRY, but not required.

**AC2 (unchanged)** — `_update_existing_page` wraps the `append_evidence_trail(page_path, source_ref, verb...)` call in `try/except OSError as e: raise StorageError("evidence_trail_append_failure", kind="evidence_trail_append_failure", path=page_path) from e`. `StorageError` is imported at `pipeline.py:27`. Non-`OSError` exceptions from `append_evidence_trail` (e.g., `UnicodeDecodeError`) propagate unchanged — cycle-20 taxonomy coverage for those kinds is a separate backlog item.

**AC3 (AMENDED)** — Regression test `test_cycle24_evidence_inline_new_page.py` parameterizes over `exclusive ∈ {False, True}`. For each parameter: (i) spy on the relevant write target (`atomic_text_write` for non-exclusive; `os.write` for exclusive — practical via `monkeypatch.setattr` on `kb.ingest.pipeline.os` with a wrapper); (ii) assert spy's `call_count == 1` for the write; (iii) read the written page and assert `## Evidence Trail\n<!-- evidence-trail:begin -->\n- YYYY-MM-DD | <source> | Initial extraction: <page_type> page created\n` appears in the content. Both assertions MUST divergent-fail on AC1 revert.

**AC4 (unchanged)** — Regression test `test_cycle24_evidence_error_redacted.py` imports `kb.ingest.pipeline as pipeline_mod`, monkeypatches `pipeline_mod.append_evidence_trail` to raise `OSError("disk full")`, calls `_update_existing_page(...)` with a valid tmp_wiki setup. Assert `StorageError` with `kind="evidence_trail_append_failure"` AND `str(err) == "evidence_trail_append_failure: <path_hidden>"`. Late-bind `StorageError` via `pipeline_mod.StorageError`.

### Cluster B — vector-index atomic rebuild

**AC5 (AMENDED)** — `rebuild_vector_index` uses tmp-then-replace for BOTH empty and populated branches. `tmp_path = vec_path.parent / (vec_path.name + ".tmp")`. Both branches: `tmp_path.unlink(missing_ok=True)` (AC6); `VectorIndex(vec_path).build(entries, db_path=tmp_path)` (entries may be `[]`); `with _index_cache_lock: popped = _index_cache.pop(str(vec_path), None); if popped is not None and popped._conn is not None: try: popped._conn.close() except Exception: pass; popped._conn = None`; `os.replace(str(tmp_path), str(vec_path))`. The `try/except` surrounds `.build()` + `os.replace` with `except Exception: tmp_path.unlink(missing_ok=True); raise` (AC8). Post-replace `logger.info` unchanged.

**AC6 (AMENDED)** — `Path(vec_path.parent / (vec_path.name + ".tmp")).unlink(missing_ok=True)` is the FIRST statement inside `rebuild_vector_index` — BEFORE `_hybrid_available` gate, BEFORE `_is_rebuild_needed` gate, BEFORE `_rebuild_lock` acquire. Optional `logger.debug` when a stale tmp was removed for operator visibility (NOT a requirement — covered by existing rebuild-completion log).

**AC7 (AMENDED)** — `VectorIndex.build(self, entries, *, db_path: Path | None = None) -> None`. Keyword-only via `*`. Body uses `target_path = db_path if db_path is not None else self.db_path` once at function entry; both empty-entries and populated paths connect via `sqlite3.connect(str(target_path))`. `self._stored_dim` is set only when `db_path is None` (building against own DB); when building to override path, `_stored_dim` is NOT mutated so the instance's state stays coherent with its self-described DB.

**AC8 (AMENDED)** — Regression test `test_cycle24_vector_atomic_rebuild.py` contains three sub-tests: (i) `test_stale_tmp_unlinked_at_entry` (seed `<vec_db>.tmp` dummy file, call `rebuild_vector_index(force=True)`, assert tmp was replaced + stale bytes do not appear); (ii) `test_os_replace_called_with_correct_paths` (spy on `os.replace`, assert called with `(str(tmp_path), str(vec_path))`); (iii) `test_crash_during_build_leaves_no_tmp` (monkeypatch `VectorIndex.build` to raise after partial insert, call `rebuild_vector_index(force=True)`, assert `vec_path` unchanged + `tmp_path` absent + exception propagated).

### Cluster C — `file_lock` exponential backoff

**AC9 (AMENDED)** — `file_lock` retry loop uses exponential backoff across ALL THREE polling sites (normal `FileExistsError` retry, `ProcessLookupError` stale-steal, Windows `OSError` stale-steal). Implementation:

```python
LOCK_INITIAL_POLL_INTERVAL = 0.01  # module-level, new

# inside file_lock, before the while loop:
attempt_count = 0

# at each of the three sleep sites, replace:
#   time.sleep(LOCK_POLL_INTERVAL)
# with:
#   time.sleep(min(LOCK_INITIAL_POLL_INTERVAL * (2 ** attempt_count), LOCK_POLL_INTERVAL))
#   attempt_count += 1
```

Both `LOCK_INITIAL_POLL_INTERVAL` and `LOCK_POLL_INTERVAL` are module-level attributes read at CALL TIME inside the retry loop (not snapshotted into locals). `LOCK_POLL_INTERVAL` is the CAP: monkeypatching it to `0.001` clamps all sleeps to `<= 0.001`.

**AC10 (AMENDED)** — Regression test `test_cycle24_lock_backoff.py::test_sleep_sequence_is_exponential` monkeypatches `kb.utils.io.time.sleep` with a `MagicMock()`, induces real contention via a seeded `<path>.lock` file containing a live PID (matching cycle-2 pattern), calls `file_lock(path)` under contention. Asserts `spy.call_count >= 2` AND the observed `[call.args[0] for call in spy.call_args_list]` matches `[0.01, 0.02, 0.04, 0.05, 0.05, ...]` truncated to observed length. Companion test `test_module_attribute_monkeypatch_honored` monkeypatches `LOCK_POLL_INTERVAL = 0.001` and asserts all observed sleeps are `<= 0.001` (CAP semantic pinned).

### Cluster D — BACKLOG maintenance

**AC11 (unchanged)** — Delete BACKLOG.md line 111 HIGH-Deferred multiprocessing entry. Add one-line `CHANGELOG.md [Unreleased]` Quick Reference entry: "Backlog cleanup: removed HIGH-Deferred `tests/ multiprocessing` (shipped cycle 23)."

**AC12 (unchanged)** — Step-11.5 runs `pip-audit --strict --format=json`; if `fix_versions` empty for diskcache CVE-2025-69872, update BACKLOG.md line 130 to "Re-checked 2026-04-23"; if non-empty, Step-11.5 `fix(deps)` commit bumps `requirements.txt` and moves BACKLOG entry to CHANGELOG.

**AC13 (DOWNGRADED)** — Step-11.5 runs same `pip-audit` for ragas CVE-2026-6587. If `fix_versions` empty, no-op (BACKLOG.md line 133 date already 2026-04-23). If non-empty, Step-11.5 `fix(deps)` commit bumps requirements and moves BACKLOG entry to CHANGELOG. NO textual bump in the empty-fix-versions case.

### Cluster E — sentinel-anchor hardening (new, T5)

**AC14 (AMENDED)** — `append_evidence_trail` sentinel search is SPAN-LIMITED within `## Evidence Trail` section:
- Find section header via `re.search(r"^## Evidence Trail[ \t]*\r?\n", content, re.MULTILINE)` (CRLF + trailing-whitespace tolerant).
- Section ends at next `re.search(r"^## ", tail, re.MULTILINE)` or EOF.
- Search for `SENTINEL` ONLY within `content[header_end:section_end]`.
- If header present + sentinel-in-span: insert new entry after sentinel (existing behavior).
- If header present + no-sentinel-in-span: plant sentinel at header end, then insert entry (migration).
- If no header at all: create fresh `## Evidence Trail\n<sentinel>\n<entry>\n` section at EOF — attacker-planted body sentinels outside any section span are IGNORED by construction.

**AC15 (AMENDED)** — Regression test `test_cycle24_evidence_sentinel_anchored.py` covers FOUR scenarios: (i) body-planted sentinel BEFORE real `## Evidence Trail` header → new entry lands in real section; (ii) body-planted sentinel UNDER a different heading (e.g., `## References`) → new entry lands in real `## Evidence Trail` section, not the references section; (iii) CRLF-line-ending header with trailing whitespace (`## Evidence Trail  \r\n`) → regex matches + entry lands correctly; (iv) sentinel-only-no-header legacy page (body contains `<!-- evidence-trail:begin -->` but no `## Evidence Trail` header) → fresh section created at EOF, body sentinel ignored and unchanged in content.

---

## Deferred-to-BACKLOG enumeration

This section feeds Step-11 security-verify's grep checklist per cycle-23 L3. Each row names the BACKLOG.md section + exact action.

| Tag (from threat-model §6 + Q11 resolution) | BACKLOG.md section | Action |
|---|---|---|
| `§Phase 4.5 MEDIUM — utils/io.py fair-queue lock` (T3 residual, AC9 does not add fairness) | §Phase 4.5 MEDIUM under `utils/io.py` grouping | **NEW ENTRY** (add during Step-12) |
| `§Phase 4.5 HIGH — ingest/evidence.py sentinel-anchor hardening` (T5) | n/a | **NO ACTION** — AC14 ships full hardening this cycle |
| `§Phase 4.5 HIGH — ingest/pipeline.py _update_existing_page single-write consolidation` (T7 item 2) | Existing entry at BACKLOG.md ~line 147 | **UPDATE** narrowing text: "AC2 shipped error-surfacing; single-write consolidation still deferred" |
| `§Phase 4.5 HIGH — _write_wiki_page exclusive-branch evidence collapse` (T7 item 3) | n/a | **NO ACTION** — Q1 scopes AC1 to both branches, closed in-cycle |
| `§Phase 4.5 HIGH-Deferred — vector-index lifecycle sub-items 2/3/4` (cold-load, dim-mismatch auto-rebuild, cross-thread lock symmetry) | Existing entry at BACKLOG.md line 109 | **UPDATE** strikeout sub-item 1 (atomic rebuild shipped cycle 24); sub-items 2/3/4 remain deferred |
| `§Phase 4.5 HIGH — utils/io.py atomic_json_write JSONL migration (M3)` | Existing entry ~line 127 | **NO ACTION** — keep untouched |
| `§Phase 4.5 HIGH — rebuild_indexes .tmp awareness` (R2 §1 Cluster B bullet 8) | §Phase 4.5 HIGH under `compile/compiler.py` grouping | **NEW ENTRY** (optional low-severity; add during Step-12 if room) |
| `§Phase 4.5 MEDIUM M2 per-source rollback receipt-file` | Existing entry | **NO ACTION** |
| `§Phase 4.5 MEDIUM M10 full IndexWriter` | Existing entry | **NO ACTION** |
| `§Phase 5 pre-merge items` (capture.py two-pass, `_PROMPT_TEMPLATE` relocation, `CAPTURES_DIR` contradiction) | §Phase 5 pre-merge | **NO ACTION** per user instruction |
| HIGH structural items (naming inversion, state-store fan-out, shared graph cache, async MCP, tests freeze-and-fold, conftest leak surface) | Existing entries | **NO ACTION** |
| `tests/ multiprocessing` (cycle-23 shipped) | BACKLOG.md line 111 | **DELETE** per AC11 |

**Step-11 grep-checklist (per threat-model §7):** Post-edit BACKLOG.md MUST contain regex matches for:
- `Phase 4.5 MEDIUM.*fair-queue` — satisfied by new entry
- `Phase 4.5 HIGH.*_update_existing_page.*single-write` — satisfied by narrowed existing entry
- `Phase 4.5 HIGH.*vector-index lifecycle` — satisfied by existing entry (sub-item 1 strikeout)
- `Phase 4.5 HIGH.*JSONL migration` — satisfied by existing entry
- `Phase 5 pre-merge` — satisfied by existing section

Post-edit BACKLOG.md MUST NOT contain:
- `tests/ multiprocessing.*cross-process` — deleted by AC11

---

## Cross-cutting notes

- **Lock-order discipline (CLAUDE.md + io.py:247-249).** No cycle-24 AC introduces a new lock or changes lock ordering. AC1's inline render stays inside the existing `_write_wiki_page` flow (no new lock acquisition). AC2 surfaces an exception at the existing sidecar-lock release boundary. AC5's `_index_cache.pop` + `_conn.close()` runs inside `_index_cache_lock` (existing). AC9's backoff tweaks retry interval only.
- **Test-ordering resilience (memory: feedback_inspect_source_tests, feedback_test_behavior_over_signature).** Cluster-A/B/C regression tests all behavioral — no `inspect.getsource(module) + "X" in src` vacuous-pass shapes. AC3 spy form explicitly guards against this.
- **Monkeypatch migration scope risk.** `file_lock` (13 reference-form monkeypatches) and `LOCK_POLL_INTERVAL` (2) are the migration-scope risks. Cycle-24 preserves call-time attribute semantics per CONDITION 3. No signature change; no symbol rename. Safe.
- **Blast radius.** Five source files (`src/kb/ingest/pipeline.py`, `src/kb/ingest/evidence.py`, `src/kb/query/embeddings.py`, `src/kb/utils/io.py`) plus BACKLOG.md, CHANGELOG.md, CHANGELOG-history.md, CLAUDE.md. Estimated line delta: +130 to +180 source lines, +300 to +450 test lines, +60 to +90 doc lines.
- **CVE late-arrival (T8).** Step-11.5 `pip-audit --strict --format=json` run is MANDATORY regardless of AC12/AC13 BACKLOG edits. Diff against Step-2 baseline; any new CVE → Step-11.5 `fix(deps)` commit before Step-12 docs.

**Verdict reiterated:** PROCEED with 15 ACs, all amendments listed above folded into the FINAL DECIDED DESIGN. Step-7 plan drafter should treat each numbered CONDITION above as a contract that must map to a specific Step-9 task.
