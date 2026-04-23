# Cycle 24 — Self-Review + Skill Patch (Step 16)

**Date:** 2026-04-24
**Cycle:** 24 (Backlog-by-file; evidence-trail + vector-atomic + file_lock-backoff + sentinel-anchor)
**PR:** [#38](https://github.com/Asun28/llm-wiki-flywheel/pull/38) — MERGED as `9e5e8e7`
**Commits:** 9 on branch (7 feature/doc + 2 review-fix)
**Tests:** 2743 → 2768 (+25 across 5 new test files)
**Wall-clock duration:** ~3.5 hours (Step 1 start at 23:58 → Step 15 merge at 01:19)

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 Requirements + AC | yes | no — expanded by T5 | Scope grew from 13 → 15 ACs after Step-2 threat model surfaced Cluster E (T5 sentinel injection). AC14/AC15 added mid-cycle. Example of the scope-expansion-via-threat-model pattern. |
| 2 Threat model + CVE baseline | yes | yes | T5 (sentinel injection) was a NEW requirement, not present in Step 1. Opus subagent produced 10 threats + 11-item deferred-to-BACKLOG table. pip-audit confirmed 2 existing Class-A CVEs, no fix available. |
| 3 Brainstorming | yes | yes | — |
| 4 Design eval (R1 Opus + R2 Codex parallel) | yes | yes | R1 Opus took ~6 min (1M-context heavy reading) — 270s wake was barely enough. Both R1+R2 converged on identical structural observations (AC1 both-branches, AC5 cache-pop ordering, AC9 LOCK_POLL_INTERVAL semantic). Low discord. |
| 5 Decision gate | yes | yes | 15 questions resolved autonomously per `feedback_auto_approve`. 14 CONDITIONS pinned; 1 AC (AC13) downgraded to verify-only. |
| 6 Context7 | **SKIPPED** | — | Pure stdlib (os.replace, re, sqlite3, threading). No novel APIs. |
| 7 Plan (primary session draft) | yes | first draft REJECTed | Per cycle-14 L1: 15 ACs + full context → drafted in primary. Plan-gate REJECTed 2 gaps (AC12 pip-index check missing, CONDITION 13 marked "optional"). Fixed inline per cycle-21 L1. |
| 8 Plan gate (Codex) | yes | REJECT resolved inline | Codex dispatch succeeded first time (block-no-verify hook did NOT fire for this cycle's Codex calls — different from cycle 22). |
| 9 Implementation (primary session, 5 tasks) | yes | 1 missed inline formula | TASK 4 `Edit(replace_all=true)` replaced POSIX stale-steal + normal retry inline formulas with `_backoff_sleep_interval()` helper calls — but missed the Windows stale-steal branch (different indentation pattern). R1 Sonnet N1 caught it. |
| 10 CI hard gate | yes | yes | 2757 passed + 9 skipped first run. Zero failures. |
| 11 Security verify (Codex) | yes | CONDITIONAL PASS | All T1..T10 IMPLEMENTED. Zero anti-pattern hits. Zero PR-introduced CVEs. |
| 11.5 Existing-CVE patch | yes (no-op) | yes | Both diskcache CVE-2025-69872 and ragas CVE-2026-6587 have empty fix_versions; no action. |
| 12 Doc update | yes | yes | Primary-session (not Codex) — BACKLOG delete + update + 2 new entries, CHANGELOG + CHANGELOG-history + CLAUDE.md synced. |
| 13 Branch + PR | yes | yes | PR #38 opened. Comprehensive body with AC summary, test plan, review trail link. |
| 14 PR review (R1 + R2 + R3) | yes | 3 rounds with real findings | R1 Codex APPROVE; R1 Sonnet REQUEST_CHANGES (1 BLOCKER + 2 MAJOR + 2 NITs). R2 Codex VERIFIED all R1 fixes + found 1 NEW MAJOR (tilde fences). R3 Sonnet APPROVE-WITH-NIT (3 doc-count drifts). R3 triggered per cycle-17 L4 (≥15 ACs + ≥10 design-gate questions + new security enforcement point + new filesystem write surface). |
| 15 Merge + cleanup | yes | yes | `gh pr merge --merge --delete-branch` succeeded. Zero Dependabot late-arrivals (alert #12 = pre-existing ragas). |
| 16 Self-review + skill patch | this step | — | Five new lessons distilled below. |

## Skill-patch lessons (5)

### L1 — `Edit(replace_all=true)` partial-match footgun

**What happened:** In TASK 4 I used a single `Edit(replace_all=true)` with the `old_string` `"min(LOCK_INITIAL_POLL_INTERVAL * (2**attempt_count), LOCK_POLL_INTERVAL); attempt_count += 1"` to replace ALL 3 inline backoff-formula sites in `src/kb/utils/io.py`. Two matched and got replaced with `_backoff_sleep_interval(attempt_count)`; the Windows stale-steal branch (io.py:371-376 at the time) had the formula split across 4 lines with different whitespace so `replace_all` missed it silently. The site retained the inline formula, which R1 Sonnet PR review flagged as NIT N1.

**Why it matters:** `replace_all=true` is a silent match-or-miss tool. When the old_string is a multi-line code pattern and the target file has SIMILAR-BUT-NOT-IDENTICAL occurrences (different line breaks, different whitespace), the unchanged sites appear unmodified in the diff — no error message, no visible mismatch.

**Rule (new Red Flag row):** Before using `Edit(replace_all=true)` on a multi-line code pattern: (a) grep the target file for the pattern verbatim to count expected replacements; (b) after the Edit, re-grep for the old pattern — zero hits expected; (c) re-grep for the new pattern — count must equal expected replacements. A helper-extraction pattern (like mine's shared `_backoff_sleep_interval`) is especially prone because the ORIGINAL inline formula should survive in the helper body — the re-grep must exclude that one site. Easier: use `Edit(replace_all=false)` with separate old/new pairs per site (N Edits for N sites); any mismatch fails loudly.

### L2 — CommonMark fence variants (`~~~` + 4+ backticks) beat simple regex

**What happened:** AC14's `_mask_fenced_blocks` used regex `^```[^\n]*\n.*?^```[^\n]*$` which handled only 3-backtick fences. R2 Codex PR review found the gap: an attacker using `~~~markdown\n## Evidence Trail\n~~~` (tilde fence) OR `` ````text\n## Evidence Trail\n```` `` (4+ backtick fence) would evade masking, letting the header regex find the attacker-planted text first. Fix: rewrote `_mask_fenced_blocks` as a line-walk state machine tracking fence character type AND opening length, matching close lines that use the same character with at least the same length — conforms to the full CommonMark fence spec.

**Why it matters:** Markdown security defenses against attacker-planted content must handle the FULL CommonMark spec, not the common case. An attacker picks the least-familiar variant — tilde fences, 4-backtick fences, nested variants — precisely to evade defenses.

**Rule (new Red Flag row):** When writing regex-based masking for markdown input (fenced code, links, inline code, blockquotes, etc.), explicitly enumerate the CommonMark variants the pattern must handle:

- Fenced code: `` ```+ `` AND `~~~+`, closing fence must match opening char + length.
- Inline code: `` ` ``, `` `` ``, etc. (1+ backticks, matching close).
- Emphasis: `*` / `_` AND `**` / `__`.

Default to a line-walk / state-machine parser rather than regex when matching multi-line markdown constructs where closing tokens depend on opening tokens. Simple regex is for line-scoped patterns.

### L3 — Cache-eviction helpers must close under the same lock as the dict pop

**What happened:** My first `_evict_vector_index_cache_entry` did `with _index_cache_lock: popped = _index_cache.pop(...)` then — OUTSIDE the lock — `popped._conn.close()` + `popped._conn = None`. R1 Sonnet MAJOR M1 caught the race: a concurrent query thread that grabbed the cached instance BEFORE the pop can call `VectorIndex.query()`, which takes the fast-path check `if self._conn is not None: return self._conn`. If my helper's `_conn = None` lands after the fast-path check but before the query's subsequent `sqlite3.execute`, the query sees the closed handle.

**Why it matters:** `_index_cache_lock` serializes cache MUTATION. `_conn_lock` serializes per-instance lazy init. Between them, the eviction path crossed a lock boundary that the query path didn't anticipate. The query's fast-path design assumes once it reads `_conn is not None`, the handle stays open for the duration of the query.

**Rule (new Red Flag row):** When writing a cache-eviction helper that also cleans up the evicted instance, the cleanup operations MUST stay inside the SAME cache lock that performed the pop. `dict.pop` alone is necessary-but-not-sufficient for thread safety when the popped instance has its own lifecycle. Applies to: sqlite3 connections (close → ProgrammingError on in-flight queries), file handles (close → OSError), subprocess handles (terminate → race with poll), etc.

Self-check: any helper whose shape is `with lock: x = dict.pop(k); <cleanup on x>` is a candidate. Move the cleanup INSIDE the lock block. If the cleanup is expensive (network call, flush, etc.), either accept the lock hold OR refactor to a two-phase protocol (mark-invalid + lazy-close-on-next-acquire).

### L4 — Divergent-fail requires POSITION assertions, not content-only

**What happened:** `test_sentinel_only_no_header_creates_fresh_section` asserted (i) attacker sentinel still in body, (ii) fresh `## Evidence Trail` section exists, (iii) entry lands in fresh section, (iv) sentinel count == 2. R1 Sonnet MAJOR M2 caught that ALL four assertions passed under AC14 revert because the "no-header" branch predated cycle 24 — reverting the span-limiting regex didn't change that code path. Fix: added POSITION assertions (new entry BYTE-POSITION > real header BYTE-POSITION > attacker sentinel BYTE-POSITION).

**Why it matters:** Content-only assertions ("X is in the result") are conjunction-tolerant — revert can introduce a false "X" at the wrong position and the assertion still passes. Position assertions test the RELATIONSHIP between artifacts, which is where the vulnerability actually lives. This is a generalisation of cycle-11 L2 ("stdlib-helper-in-isolation") and cycle-16 L2 ("reach the production call site with diverging inputs").

**Rule (amend cycle-11 L2 / cycle-16 L2 Red Flag):** For regression tests of security-class anti-patterns (path-containment bypass, sentinel-injection, code-block escape), assertions MUST test the RELATIONSHIP between the attacker-controlled artifact and the legitimate artifact — not just their presence. Typical patterns: `attacker_pos = result.index(attacker_content); real_pos = result.index(real_content); new_pos = result.index(new_entry); assert new_pos > real_pos > attacker_pos` OR the inverse. Revert to the vulnerable code path flips at least one of these inequalities because the vulnerability shifts the new artifact's position.

Self-check: grep your new security-regression tests for `assert X in result` patterns; for each, ask "if the production code is reverted to insert at the wrong position, does this assertion still hold?" — if yes, add a position assertion.

### L5 — Design-eval wake budget: 1M-context Opus + Codex parallel → 360s minimum

**What happened:** I dispatched R1 Opus + R2 Codex in parallel at 00:00, then scheduled a 270s wake. R2 Codex returned at ~00:05 (~5 min); R1 Opus returned at ~00:05:21 (~5.3 min). The 270s wake fired at 00:04:30 — I had to poll for R1's output for ~1 minute. In cycle 24 this worked, but if either subagent had taken 7+ min (R1 Opus + grep-verify on 1M context is not unusual), the wake would have fired and I'd have to reschedule.

**Why it matters:** Per the skill's wake-delay comment: 270s stays cache-warm (TTL 300s). 360s would blow the cache. So the trade-off is real — pay one cache-miss for a safer wake budget OR stay inside cache and poll-loop on subagent lateness. Cycle-22 L4's hung-agent heuristic (10-min 0-byte fallback) is the emergency brake; for the common case of "subagent is close to done", a 270s wake + manual poll handles it.

**Rule (amend cycle-20 L4 Red Flag):** For parallel R1 Opus + R2 Codex dispatches on a cycle with ≥10 ACs or extensive artifact reading (design docs + source files + threat model + brainstorm), budget for 5-6 min subagent completion time. Options: (a) schedule 270s wake AND accept up to 60s of post-wake polling for the slower agent; (b) schedule 270s wake THEN a second 240s wake if only one agent returned (stays cache-warm with 2 wakes); (c) dispatch Codex first (typically faster) + wake 240s, then dispatch Opus + wake 270s. Option (a) is the simplest default; (b) provides a clean fallback; (c) reduces wall-clock time when the two reviews don't strictly need parallelism.

## Scope accountability

**Delivered:**
- 15 ACs across 5 clusters (all shipped). 14 CONDITIONS pinned. 25 new tests. 4 source files + 4 doc files touched. 9 commits.
- Closed Phase 4.5 HIGH-Deferred vector-index lifecycle sub-item 1 (atomic rebuild) + sub-item 4 (cross-thread cache symmetry).
- Narrowed Phase 4.5 MEDIUM `_update_existing_page` body+evidence entry (error-surfacing side shipped).
- Added 2 new BACKLOG entries (fair-queue lock + rebuild_indexes .tmp awareness) — per cycle-23 L3 deferred-promise rule.

**Deferred (carried to backlog):**
- Vector-index cold-load latency (sub-item 2).
- Vector-index dim-mismatch auto-rebuild (sub-item 3).
- `_update_existing_page` single-write consolidation (AC1 only covered new-page path).
- `utils/io.py` fair-queue lock (cycle-24 AC9 added backoff; fairness still open).
- `atomic_json_write` → JSONL migration (M3 full ask).
- `rebuild_indexes .tmp` awareness (belt-and-suspenders).

**Delta vs Step 1 estimate:** +25 tests (estimate +16..+20; slight over-run from AC15 + R1/R2 added-test follow-ups). +130..+180 source lines (estimate matched).

## Cycle termination

Per the skill's Cycle Termination clause: cycle 24 is complete. `/clear` before starting cycle 25 to avoid context pollution. Do NOT `ScheduleWakeup` to auto-start the next cycle — user must initiate.
