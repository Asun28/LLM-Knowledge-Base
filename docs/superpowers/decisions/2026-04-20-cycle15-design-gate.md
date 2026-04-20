# Cycle 15 — Design Decision Gate (Step 5)

**Date:** 2026-04-20
**Gate runner:** Opus 4.7 (1M-ctx)
**Inputs:** requirements.md (32 AC), threat-model.md (T1–T10), brainstorm.md (Approach A + Q1–Q8), design-eval R1 (6 REJECTs + 18 amendments), design-eval R2 (2 blockers + 19 amendments + 11 approvals).
**Scope:** Resolve 8 open questions + 6 R1 REJECTs + 8 threat-model amendments into the final AC list that Step 7 can plan against.

## VERDICT

**APPROVED WITH AMENDMENTS.** Final scope: **28 ACs** survive the gate (4 drop; 4 rewrite; 20 amendment-in-place; 4 approve-as-is). 28 ACs still clears the 15-AC floor, so a REJECT is not warranted. All 8 threat-model amendments land on the correct AC (T10c promoted to docs deliverable). No scope-explosion from the gate.

---

## DECISIONS (per question + per reject)

Each block follows OPTIONS → ARGUE → DECIDE → RATIONALE → CONFIDENCE. ARGUE blocks carry the `## Analysis` scaffold so reasoning precedes the verdict.

### Q1 — AC3 `_apply_authored_by_boost` gate shape

**OPTIONS.**
- (a) Full `validate_frontmatter` gate mirroring `_apply_status_boost` (reconstruct `_PostLike`, call validator, no-op on any error) — R1/R2/T7 recommend.
- (b) Lighter gate — just membership check `authored_by in AUTHORED_BY_VALUES` + empty-string guard.

**ARGUE.**

## Analysis

`_apply_status_boost` already embodies the cycle-14 T9 mitigation: a poisoned page whose frontmatter fails validation cannot capture the +5% ranking multiplier even if it lists the magic `status: mature` token. Ship `_apply_authored_by_boost` without the same gate and an attacker-planted `authored_by: human` line — on a page whose `source` is missing or `type` is bogus — gets +2%. Combine with `_apply_status_boost` and the stacking multiplier reaches ~7% on invalid-otherwise pages. That is exactly the ranking-manipulation cost cycle 14 priced in. The structural pattern is already audited; the cost of calling `validate_frontmatter` is a dict copy per boost application, which the cycle-14 pipeline already absorbed. Option (b) is strictly weaker: a page with valid `authored_by: human` but no `source:` field would still pass a membership check, so (b) does not close the T7 gap.

Blast-radius framing also favours (a). Option (a) is opt-in at the page level (only pages that both declare `authored_by: human|hybrid` AND pass the full schema receive the boost), matches a reversible implementation (delete the helper and callers revert), and leaves no public API exposure. Option (b) widens attack surface without any implementation-cost win because both helpers have to construct a `_PostLike` anyway to feed `validate_frontmatter`. The project principles section of CLAUDE.md explicitly flags "Lower blast radius wins" — (a) is dominant.

**DECIDE.** Option (a) — full `validate_frontmatter` gate, literal copy of `_apply_status_boost` structure (reconstruct `_PostLike` with metadata dict, call `validate_frontmatter(post)`, return `page` unchanged if errors list is non-empty).

**RATIONALE.** T7 closure; identical to shipped `_apply_status_boost` contract; additive in scope with zero new public surface.

**CONFIDENCE.** High — both reviewers agree, matches the project's "lower blast radius wins" principle.

---

### Q2 — AC12 incremental-publish default

**OPTIONS.**
- (a) Default ON at AC12 helper level (`incremental: bool = True`) + CLI default `--incremental`.
- (b) Default OFF at AC12 helper level (`incremental: bool = False`) + CLI default `--incremental` (flag flip at CLI).
- (c) Default OFF everywhere (`incremental: bool = False`) + CLI default `--no-incremental`.

**ARGUE.**

## Analysis

The requirements doc's existing AC12 text declares `incremental: bool = False` ("default False preserves existing test contract"), and existing publish tests call the builders as positional-only. Flipping the helper default to True would break the cycle-14 regression tests that assert full regeneration on every call — the T2 epistemic filter tests in `test_cycle14_publish.py` all assert byte-level output equality after the filter is applied, and a silent short-circuit would make those tests non-deterministic. So (a) is a library-level API break with hidden test fallout.

CLI-level default separately: T10c explicitly warns that the first post-cycle-15-upgrade run should be `--no-incremental` so pre-cycle-14 outputs (which may carry retracted content written before the epistemic filter shipped) are regenerated. If the CLI default is `--incremental`, operators need to be taught to run once with `--no-incremental` at upgrade. If the CLI default is `--no-incremental`, the T10c risk is closed automatically but we burn a regen on every `kb publish` invocation going forward — a ~5s cost on large wikis. That's an ongoing tax vs a one-time operator action. Option (b) — library defaults OFF, CLI defaults ON — matches the "opt-in > always-on" principle while still giving operators the fast path after a documented first-run workflow, and it preserves the cycle-14 test contract at the library layer.

**DECIDE.** Option (b). AC12 helper keeps `incremental: bool = False` default (zero test breakage). AC13 CLI adds `--incremental/--no-incremental` with default `--incremental` (fast steady-state). T10c closes via Step-12 docs bullet telling operators to run `kb publish --no-incremental` once at upgrade.

**RATIONALE.** Preserves cycle-14 library-level test contract; gives operators the steady-state speed wins; closes T10c via docs rather than a permanent regen tax.

**CONFIDENCE.** High — the split matches what existing AC12/AC13 text already specifies and what both R1/R2 tacitly assume.

---

### Q3 — AC17 cache invalidation strategy

**OPTIONS.**
- (a) Process-wide `cache_clear()` — simple, T6 perf hit documented.
- (b) Targeted per-key invalidation — surgical, requires new helper variant.
- (c) Reframe AC17 as route-through-helper-but-still-uncached (new `load_page_frontmatter_fresh` variant that bypasses cache).
- (d) DROP AC17 entirely — preserve cycle-13 AC2 deliberate decision.

**ARGUE.**

## Analysis

R1's rejection is load-bearing: cycle-13 AC2 intentionally uses uncached `frontmatter.load` precisely because same-process writes from `_mark_page_augmented` and `_record_verdict_gap_callout` happen milliseconds before the read, and FAT32/OneDrive/SMB coarse mtime resolution defeats the `(path, mtime_ns)` cache key. Switching to `load_page_frontmatter` + `cache_clear()` reintroduces the same-process-coarse-mtime hole under a different cover: after `cache_clear()`, the next call re-populates the cache with whatever the kernel reports, and if mtime has not advanced past the coarse quantum, two processes reading simultaneously can both populate with the stale payload. The cycle-13 uncached-load path sidesteps that class of bug entirely. Option (a) therefore fails on correctness, not just perf.

Option (b) — targeted invalidation — requires building a public `load_page_frontmatter.cache_pop(key)` surface, which means a new public helper in `kb.utils.pages` and an extra test suite for the invalidation semantics. That is out of scope for a batch cycle and violates "Goal-Driven Execution" from CLAUDE.md (no observable bug is being fixed). Option (c) has the same problem — it spawns a new helper variant to solve a problem cycle-13 already solved with `frontmatter.load`. Option (d) preserves the cycle-13 decision with zero net code change and is the minimum-regret path. R1 explicitly flagged (d) as the preferred disposition; R2 called AC17 an amendment-candidate but also agreed the cycle-13 uncached-load comment must stay. Dropping AC17 closes the question without regression. AC31 (the test for AC17) becomes moot and also drops.

**DECIDE.** Option (d) — DROP AC17 entirely. Also DROP AC31 (moot).

**RATIONALE.** Cycle-13 AC2 intentionally chose uncached read to avoid the same-process coarse-mtime hole; AC17 would regress that. No observable failure case justifies the change. Lower blast radius: delete the AC, preserve the working comment at augment.py:1128.

**CONFIDENCE.** High — both reviewers independently flagged this as regression-shaped.

---

### Q4 — AC16 decay clamp ceiling

**OPTIONS.**
- (a) `SOURCE_DECAY_DEFAULT_DAYS * 50` (~12 years).
- (b) Lower ceiling — e.g. `SOURCE_DECAY_DEFAULT_DAYS * 20` (~5 years) or a fixed constant like `3650` (~10 years).

**ARGUE.**

## Analysis

The ceiling exists to defend against a hostile or typo-inflated multiplier running away the decay window (T2). The longest legitimate decay we ship today is arxiv at 1095 days (3 years); a 1.1× boost takes it to 1204 days. Even if a future contributor adds a 5.0× multiplier keyed on a rare topic, the product with arxiv (1095 × 5 = 5475 days, ~15 years) already exceeds (b)'s tighter ceiling — that would silently clamp and confuse the contributor, who'd wonder why their explicit 5× didn't land. Option (a)'s ceiling (SOURCE_DECAY_DEFAULT_DAYS * 50 = 90 × 50 = 4500 days, ~12 years) is looser than (b)'s ~5-year ceiling and tight enough to catch `float("inf")` or `1e10` without masking realistic inputs.

The wider principle: the clamp is a safety net, not a policy. Picking the tightest possible ceiling that still accommodates plausible future topic additions is the right call. (a) allows arxiv × 4× expansion (4380 days, under 4500) without clamping — room for a hypothetical "foundational research" topic with 4× multiplier — while still guarding against `nan`/`inf`/hostile multiplier regressions. (b) would actively clamp that future use case and force a config change. Neither choice is irreversible, but (a) is the less restrictive of two safe options and matches T2's original recommendation.

**DECIDE.** Option (a) — `SOURCE_DECAY_DEFAULT_DAYS * 50` (=4500 days ≈ 12 years).

**RATIONALE.** Matches T2 mitigation exactly; leaves room for realistic future multipliers (up to 4× arxiv); still catches `inf`/`nan`/hostile regression.

**CONFIDENCE.** High — T2 mitigation recommendation stands; no review flag.

---

### Q5 — AC6 Evidence Trail anchor

**OPTIONS.**
- (a) `^## Evidence Trail` line-anchored (re.MULTILINE) — matches `kb.ingest.evidence:96`.
- (b) Body-anywhere `## Evidence Trail` — fires on any occurrence, including code fences.

**ARGUE.**

## Analysis

T5 directly names the attack vector: a naive body-wide regex for `action: ingest` fires on code fences, comment blocks, or meta-documentation that mentions the ingest pipeline. The CLAUDE.md Evidence Trail convention enforces "sentinel discipline" — the sentinel `## Evidence Trail` line is machine-maintained and singular per page. `kb.ingest.evidence.py:96` already uses `re.search(r"^## Evidence Trail\r?\n", content, re.MULTILINE)` — the line-anchored form is the authoritative match. R1's T5 mitigation recommends reusing this anchor verbatim.

Option (b) would fire on any page whose body contains the literal string `## Evidence Trail` (e.g., a concept page about the Evidence Trail convention itself, a code fence quoting the regex, a test fixture documenting the schema). False positives noise the warning output and undermine trust in the `check_authored_by_drift` signal. The only marginal benefit of (b) is matching a section whose header has trailing whitespace or non-canonical spacing — but cycle-14's evidence.py already rejects those cases at write time, so (a) catches every production-written trail. R2 separately flagged CRLF handling: `\r?\n` in the existing anchor covers that. CRLF + line anchor + scope-until-next-`^## ` is the right composite.

**DECIDE.** Option (a) — `^## Evidence Trail` line-anchored via `re.MULTILINE`; scope regex to span between this anchor and the next `^## ` header (or EOF). Reuse the exact anchor from `kb.ingest.evidence:96`.

**RATIONALE.** Matches the machine-maintained sentinel discipline; closes T5 false-positive surface; reuses existing anchor for consistency.

**CONFIDENCE.** High — both reviewers agree; CLAUDE.md evidence-trail convention is directly cited.

---

### Q6 — AC7 new checks wiring

**OPTIONS.**
- (a) Wire AC5 and AC6 unconditionally into `run_all_checks`.
- (b) Gate behind a `--checks=cycle15` include flag.

**ARGUE.**

## Analysis

Both new checks are `warning`-level, not `error` or `info`. The lint pipeline already emits warnings the operator may ignore (stale_pages, orphan_pages, frontmatter anomalies); one more per-page regex scan and one more status-date arithmetic check cost ~2ms per page on a 5000-page wiki (10s total), well under the full-lint runtime (~90s). Blast radius is additive warnings, which are trivially ignorable in the report output. A new flag is permanent config debt — cycle-16 would have to remove it once the checks prove themselves. That flip-flop violates the project's "batch cycles are mechanical" principle from brainstorm.md.

Option (b) is the kind of flag-guarding that feedback_batch_by_file memory rejects as over-engineering. Warnings are already opt-in to act on; flag-guarding them adds user-visible config surface without actually reducing risk. R1 marks AC7 as "APPROVE. Trivial wiring"; that's the right call. R2 doesn't contest. The cycle-14 precedent for new lint checks (`check_frontmatter_staleness` in cycle 14) shipped unconditionally and the pattern held.

**DECIDE.** Option (a) — unconditional wiring in `run_all_checks`.

**RATIONALE.** Warning-level output is additive and ignorable; no correctness or security impact; follows cycle-14 precedent; avoids flag-as-config-debt.

**CONFIDENCE.** High — reviewers agree; project principle explicitly rejects flag-guarding for warning-tier additions.

---

### Q7 — AC18/AC19 retroactive docstring update

**OPTIONS.**
- (a) DROP AC18+AC19 production ACs (no-ops); KEEP AC32 as a cycle-14 regression contract test.
- (b) Keep AC18+AC19 reframed as "add docstring to `load_all_pages` clarifying the additive-keys contract shipped in cycle 14."

**ARGUE.**

## Analysis

Grep of `src/kb/utils/pages.py:157-164` shows all three vocabulary fields (`status`, `belief_state`, `authored_by`) shipped in cycle-14 AC23 as a single dict-construction block. R1 and R2 independently verified this. The production code change AC18 and AC19 propose is already in main — shipping them would be a no-op. The cycle-14 L3 atomicity lesson ("vocabulary loader keys ship together") is already satisfied by the cycle-14 work.

Option (b) — docstring addition — is worth considering. The current source comment at lines 157-161 already explains the additive-keys pattern in five lines; it's self-documenting. A docstring on `load_all_pages` could surface the contract at the function signature level (IDE hover, autocomplete), which has mild discoverability value. But: the function docstring at current line 113 is inherited from before cycle 14, and editing it now to reference cycle-14 AC23 adds docs debt — future cycles also add additive keys (e.g., hypothetical `provenance_score`) and the docstring would need to re-update or go stale. Better keep the contract documented at the cycle-14 comment block adjacent to the keys themselves (where the code actually lives), and let AC32's regression test serve as the machine-checked anchor.

AC32 is the right survivor: it asserts both `authored_by` and `belief_state` keys are present with empty-string defaults, so any future refactor that accidentally drops them fails the test. That's strictly more useful than a docstring.

**DECIDE.** Option (a). DROP AC18 and AC19 as duplicates-already-shipped. KEEP AC32 as a cycle-14 contract regression test (no amendment to production code; test serves as anchor).

**RATIONALE.** Production code already shipped in cycle 14; re-shipping is a no-op. AC32 provides the machine-checked contract anchor. Avoids docs debt.

**CONFIDENCE.** High — grep confirms; both reviewers agree on the duplicate-drop.

---

### Q8 — AC14 `SOURCE_VOLATILITY_TOPICS` shape

**OPTIONS.**
- (a) `dict[str, float]` per-topic multiplier (AC text as written).
- (b) `tuple[str, ...]` + single global multiplier.

**ARGUE.**

## Analysis

The current `SOURCE_DECAY_DAYS` config precedent is `dict[str, int]` — per-platform decay values. Matching that shape with `dict[str, float]` per-topic multiplier gives future contributors a consistent mental model ("look up per-key value"). Option (b) — tuple + flat multiplier — is simpler today but locks the design into uniform-multiplier-forever; the first real request for "AI topics get 1.3×, security topics get 1.1×" would require a dict migration later. Batch cycles reject flag-flips; they also reject shape-flips.

R2 separately flagged that whichever shape ships, the keys should be case-folded at definition so caller casefolding in `volatility_multiplier_for` doesn't drift (a `"LLM"` key drifting vs `"llm"` lookup would silently return 1.0). This is a tiny addition: either pre-casefold the dict at module load (`SOURCE_VOLATILITY_TOPICS = {k.casefold(): v for k, v in {...}.items()}`) or expose a read-only mapping (`types.MappingProxyType`) so callers can't mutate the source of truth. The MappingProxyType exposure closes one surface: a future caller can't accidentally append to the dict at runtime. Both are cheap.

**DECIDE.** Option (a) — keep `dict[str, float]`. Add two refinements per R2: (i) casefold keys at module-load definition (`{k.casefold(): v for k, v in {...}.items()}`); (ii) optionally wrap in `types.MappingProxyType` for read-only exposure (lower priority — add to AC14 as "should" not "must" if it ships cleanly).

**RATIONALE.** Preserves extensibility for per-topic tuning; matches `SOURCE_DECAY_DAYS` precedent; R2's casefold-at-definition closes case-drift gap.

**CONFIDENCE.** High — matches existing config pattern; both reviewers agree dict-shape is correct; R2's refinement is additive and cheap.

---

### REJECT-1 — AC1 (mis-describes current code)

**OPTIONS.**
- (a) Rewrite AC1 to ADD new "today-minus-page-date > decay_days_for(source)" check alongside existing mtime check (new behaviour + compatibility).
- (b) DROP AC1 entirely — wire `decay_days_for` only in AC4's `check_staleness`.
- (c) REPLACE existing mtime check with decay check (behaviour change; removes wiki-vs-source freshness semantic).

**ARGUE.**

## Analysis

Current `_flag_stale_results` compares page `updated` date against the newest source mtime (engine.py:397): `newest_source_mtime > page_date` → stale. This is a wiki-vs-source freshness semantic — the page is stale *relative to its sources* if the sources have been updated after the wiki. That semantic is orthogonal to absolute decay (arxiv papers at 3 years). The two checks answer different questions: "is my wiki behind its source?" vs "is this source itself old enough to distrust?" Both have value, and they compose: a page can be fresh relative to its source but still too old on an absolute decay clock (if the source hasn't moved in 3 years), OR stale relative to a recently-updated source but still within the absolute decay window.

Option (c) loses the wiki-vs-source signal entirely. That's a behaviour regression: cycle-3/4 invested in the mtime-vs-page-date check precisely to catch "I updated the arxiv paper but the wiki didn't track." Removing it would mask genuine drift. Option (b) leaves the absolute-decay gate missing at query time, which is exactly the original cycle-15 backlog item (wiring `decay_days_for` at call sites). Option (a) — both checks compose, stale if either fires — preserves the existing semantic AND adds the new decay gate. R2 independently approved AC1 with this framing: "already loops normalized sources; list-vs-string source frontmatter is mechanical via normalize_sources." R1 rejected the AC text framing but not the underlying intent; rewriting to compose both checks resolves both objections.

Multi-source max-decay applies here too: if a page has sources on both arxiv (1095d) and github (180d), the decay gate should use max() — lenient behaviour, same as AC4's multi-source rule (Q8/AC4 amendment).

**DECIDE.** Option (a) — REWRITE AC1 to compose both checks. New AC1 text: "`_flag_stale_results` adds a second staleness condition: in addition to the existing `newest_source_mtime > page_date` check at engine.py:397, iterate the page's `sources` list, compute `max(decay_days_for(src) for src in sources)` (lenient — longest-decay platform wins), and mark stale if `(today - page_date).days > max_decay`. Page is flagged stale if EITHER check fires. Pages with no `sources` skip the decay check (existing behaviour preserved). AC20 test asserts: (i) arxiv-sourced page 1000d old with synchronised source mtime NOT flagged; (ii) github-sourced page 200d old with synchronised source mtime flagged; (iii) existing mtime-vs-source test fixtures still pass."

**RATIONALE.** Composes the two orthogonal freshness signals; preserves existing behaviour; closes the original backlog item. R2-approved framing; R1's objection was textual, not conceptual.

**CONFIDENCE.** High — the two-signal composition is well-defined and testable.

---

### REJECT-2 — AC8 (function-target mismatch)

**OPTIONS.**
- (a) Retarget to iterate EXISTING pages — new function `suggest_enrichment_targets` in `evolve/analyzer.py` that returns pages with `status in {seed, developing}`, sorted seed-first.
- (b) Secondary-sort the `referenced_by` list within each `suggest_new_pages` suggestion by status.
- (c) DROP AC8 entirely; log as cycle-16 follow-up for status-aware enrichment routing.

**ARGUE.**

## Analysis

R1 nailed the category error: `suggest_new_pages` returns dead-link *targets* (page IDs that don't yet exist), so they have no frontmatter and no `status`. The AC test fixture ("feed 4 pages (seed/developing/mature/missing) → seed emerges first") implies an existing-page enumeration, which is a different function entirely. R2 independently said "cannot prove seed-first ordering without redefining status source." Both block the AC as written.

Option (a) — new `suggest_enrichment_targets` function — creates a new evolve API. It's the semantically correct target (the cycle-14 BACKLOG entry was "status frontmatter: kb_evolve should target seed pages" — and enrichment-targeting IS the right use case), but it spawns a new public helper that needs its own test suite, MCP surface consideration (does `kb_evolve` expose it?), and coverage in the evolution report. That's ~30-50 LoC + ~40 LoC tests + MCP integration — sliding toward a mini-feature rather than a batch-line item.

Option (b) — secondary sort within existing `suggest_new_pages` — is cheap: each suggestion has `referenced_by: list[str]`, and the list can be sorted by looking up each referrer's `status`. But the suggestion is about the NON-EXISTENT target; the referrer order only affects the display string ("referenced by 5 page(s): seed1, seed2, ..."). That's display-cosmetic, not routing behaviour. R1 flagged this as "secondary sort on a display-only field" — correct; it doesn't actually implement the cycle-14 BACKLOG intent.

Option (c) — DROP — defers the real work to cycle 16 where the enrichment-suggester can get a dedicated design. This matches the principle "atomic work; don't half-ship features." A new enrichment function deserves its own requirements+threat+brainstorm cycle. The current batch is already 28 ACs; pushing AC8 out doesn't shrink scope below the 15-AC floor.

**DECIDE.** Option (c) — DROP AC8 entirely. Record in BACKLOG.md as cycle-16 follow-up: "AC8-carry: kb_evolve status-priority enrichment routing — design a `suggest_enrichment_targets(status_priority=['seed','developing'])` function + test suite + MCP integration in a dedicated cycle." Also DROP AC26 (moot).

**RATIONALE.** Function-target mismatch can't ship as written. Option (a)'s correct target is a mini-feature that belongs in its own cycle. Dropping preserves batch shape and defers the real work cleanly. Option (b)'s cosmetic sort doesn't implement the intent.

**CONFIDENCE.** High — both reviewers independently blocked; scope discipline favours defer.

---

### REJECT-3 — AC17 cache invalidation (reverses cycle-13 decision)

Covered by Q3. **DECIDE.** DROP AC17. Also DROP AC31 (test moot).

---

### REJECT-4 / REJECT-5 — AC18 + AC19 (already shipped in cycle 14)

Covered by Q7. **DECIDE.** DROP AC18 and AC19 as production duplicates. KEEP AC32 as regression test.

---

### REJECT-6 — AC26 (blocked by AC8)

**DECIDE.** DROP AC26 alongside AC8.

**RATIONALE.** Test is moot when underlying AC drops.

**CONFIDENCE.** High — dependency-chained.

---

## CONDITIONS (new ACs / docs items required by gate decisions)

1. **Docs — Step 12 T10c guidance (new bullet, not an AC).** Add to the requirements doc's "Docs (Step 12 outputs)" section:
   > "CHANGELOG.md cycle-15 entry includes an operator note: the first post-upgrade `kb publish` run should use `--no-incremental` so any pre-cycle-14 outputs are regenerated under the current epistemic filter (threat T10c)."
   This does not become an AC (not CI-testable), but is mandatory Step-12 doc output.

2. **BACKLOG.md — new cycle-16 follow-up entry (AC8-carry).** Append under BACKLOG.md §"Phase 5 — Community followup proposals":
   > "AC8-carry (cycle-16): kb_evolve status-priority enrichment routing. Design a new `suggest_enrichment_targets(pages, status_priority=['seed','developing'])` function in `src/kb/evolve/analyzer.py` that iterates existing pages (not dead-link targets), sorts by status, and surfaces through `kb_evolve`. Requires dedicated requirements+threat+brainstorm cycle; current cycle-15 AC8 dropped due to function-target mismatch."

3. **Config constant promotion (part of AC3 amendment).** The gate mandates that `AUTHORED_BY_BOOST = 0.02` is added to `config.py` adjacent to `STATUS_RANKING_BOOST`. This is already folded into the amended AC3 text below; no new AC needed.

4. **AC14 refinement (casefold at definition).** Already folded into amended AC14 text.

---

## FINAL DECIDED DESIGN — 28 ACs

The following is the final AC list post-gate. Step 7 plans against this text. Line numbering preserves the original requirements.md numbering for traceability, with dropped ACs marked `[DROPPED]`.

### Query engine (AC1–AC3)

- **AC1 [REWRITTEN].** `_flag_stale_results` (engine.py:366) adds a second staleness condition alongside the existing `newest_source_mtime > page_date` check at engine.py:397. For each result: iterate the page's `sources` list (via `normalize_sources`), compute `max_decay = max(decay_days_for(src) for src in sources)` (lenient max-over-sources per Q8/AC4 rule), and mark stale if `(today - page_date).days > max_decay`. Final stale flag = (mtime-check fires OR decay-check fires). Pages with no `sources` skip the decay check (existing behaviour preserved). Import `date.today` via existing `datetime` symbols in the module. AC20 regression fixtures: (i) arxiv-sourced page 1000d old, source mtime synchronised → NOT flagged; (ii) github-sourced page 200d old, source mtime synchronised → flagged; (iii) existing mtime-vs-page-date fixtures still pass.

- **AC2 [APPROVED].** `_build_query_context` (engine.py:636) tier-1 loop uses `tier1_budget_for("summaries")` instead of reading `CONTEXT_TIER1_BUDGET` directly. Assertion: `tier1_budget_for("summaries") == (CONTEXT_TIER1_BUDGET * 60) // 100` given the 60/20/5/15 split; code path must call the helper.

- **AC3 [AMENDED].** New `_apply_authored_by_boost(page)` helper, applied after `_apply_status_boost` in the score pipeline (engine.py:248). Implementation: literal copy of `_apply_status_boost` structure — reconstruct `_PostLike` with full `metadata` dict, call `validate_frontmatter(post)`, return `page` unchanged if errors list is non-empty (T7 gate; matches cycle-14 pattern). Pages passing validation with `authored_by in {"human", "hybrid"}` receive `score *= (1 + AUTHORED_BY_BOOST)`. Invalid `authored_by` or absent field → no boost. **Second bullet:** introduces `AUTHORED_BY_BOOST = 0.02` in `src/kb/config.py` adjacent to `STATUS_RANKING_BOOST`.

### Lint checks (AC4–AC7)

- **AC4 [AMENDED].** `check_staleness` (checks.py:299) signature changes to `max_days: int | None = None` (R2 amendment — distinguishes omitted from override). When `max_days is None`, per-page max_days = `max(decay_days_for(src) for src in page_sources)` — lenient max-over-sources for multi-source pages (longest-decay platform wins). When `max_days is not None`, caller-provided value takes precedence for every page (existing test override path). Page with no sources falls back to `SOURCE_DECAY_DEFAULT_DAYS`.

- **AC5 [APPROVED].** New `check_status_mature_stale(pages, today=None)` — flags pages with `status: mature` whose `updated` date is more than 90 days older than `today`. Emits `level: "warning", check: "status_mature_stale", message: "mature page {pid} unchanged {N} days — consider re-review"`. Hardcoded 90d is intentional scope control; cycle-16 candidate to route through `decay_days_for` once topic signal proves out.

- **AC6 [AMENDED].** New `check_authored_by_drift(pages)`. Scan only the body span BETWEEN `^## Evidence Trail` (line-anchored, `re.MULTILINE`, `\r?\n` terminator — reuse anchor from `src/kb/ingest/evidence.py:96`) and the next `^## ` header (or EOF) for regex match `action:\s*ingest`. Pages lacking an Evidence Trail section emit no warning (absence of signal ≠ drift event — T5 mitigation). Flag pages where `authored_by == "human"` AND an in-scope `action: ingest` entry exists. Emits `level: "warning", check: "authored_by_drift", message: "human-authored {pid} auto-edited by ingest — drop authored_by or change to hybrid"`. AC25 regression fixtures: (a) `action: ingest` in code fence ABOVE Evidence Trail → NOT flagged; (b) page without Evidence Trail → NOT flagged; (c) hybrid page with in-scope `action: ingest` → NOT flagged; (d) human page with in-scope `action: ingest` → flagged.

- **AC7 [APPROVED].** `run_all_checks` in `lint/runner.py` wires AC5 + AC6 checks into its check list, unconditional (no feature flag per Q6). Same report format, same shared_pages threading.

### Evolve (AC8) — [DROPPED]

- **AC8 [DROPPED].** Function-target mismatch; deferred to cycle-16 as `suggest_enrichment_targets`. See CONDITIONS §2.
- **AC26 [DROPPED].** Test for dropped AC.

### Publish (AC9–AC12)

- **AC9 [APPROVED].** `build_llms_txt` replaces `out_path.write_text(...)` with `atomic_text_write(content, out_path)` import from `kb.utils.io`. Crash between temp + rename leaves no partial output.

- **AC10 [APPROVED].** `build_llms_full_txt` same change — `atomic_text_write` wrapping. The existing UTF-8 byte-cap loop is unchanged; only the final write is migrated.

- **AC11 [AMENDED].** `build_graph_jsonld` uses `atomic_text_write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", out_path)` — preferred form. Alternative (only if indent streaming matters later): `tempfile.mkstemp(dir=out_path.parent, ...)` + `json.dump` + `os.replace(tmp, out_path)` with try/finally temp cleanup on failure. Bare `tempfile.mkstemp()` (system-temp default) is **unacceptable** on Windows/OneDrive cross-volume scenarios (T4). AC27 regression fixture: simulate `os.replace` failure via monkeypatch and assert no `.tmp` sibling remains in `out_path.parent`.

- **AC12 [AMENDED].** New `_publish_skip_if_unchanged(wiki_dir, out_path)` helper. `build_llms_txt` / `build_llms_full_txt` / `build_graph_jsonld` each accept an `incremental: bool = False` kwarg (library-level default OFF per Q2; preserves cycle-14 test contracts). When `incremental=True` + `out_path.exists()` + `max(page.stat().st_mtime_ns for page in scan_wiki_pages(wiki_dir)) <= out_path.stat().st_mtime_ns`, the function short-circuits and returns `out_path`. **Ordering invariant:** the cycle-14 T2 epistemic filter and T1 out-dir containment (already inside each builder) run BEFORE the skip branch. **Docstring contract:** `_publish_skip_if_unchanged` docstring explicitly notes "assumes single-writer; concurrent `kb ingest` during `kb publish` may produce stale output — re-run with `--no-incremental` if drift suspected (threat T3)." Use `st_mtime_ns` on both sides for nanosecond granularity. Scan via `scan_wiki_pages(wiki_dir)` (NOT bare `rglob`) — excludes auto-maintained index files.

### CLI (AC13)

- **AC13 [AMENDED].** `kb publish` accepts `--incremental / --no-incremental` Click option, default `--incremental` (CLI-level default ON per Q2). Flag plumbing happens inside the existing `try:` block at `cli.py:391`, AFTER the cycle-14 T1 out-dir containment check at lines 369–388 (`..` reject + UNC reject + `is_relative_to(PROJECT_ROOT) or resolved.is_dir()`). `resolved.mkdir(parents=True, exist_ok=True)` stays at line 389. Click-flag addition **must not reorder** these steps. AC29 regression: `kb publish --out-dir=<outside-project> --no-incremental` still raises `UsageError` before any `mkdir`.

### Config (AC14–AC16)

- **AC14 [AMENDED].** `SOURCE_VOLATILITY_TOPICS: dict[str, float]` with keys casefolded at definition:
  ```python
  _RAW_VOLATILITY_TOPICS = {"llm": 1.1, "react": 1.1, "docker": 1.1, "claude": 1.1, "agent": 1.1, "mcp": 1.1}
  SOURCE_VOLATILITY_TOPICS: Mapping[str, float] = MappingProxyType(
      {k.casefold(): v for k, v in _RAW_VOLATILITY_TOPICS.items()}
  )
  ```
  Read-only exposure via `MappingProxyType` prevents caller mutation (R2). Keys are case-folded substrings matched against page tags/title.

- **AC15 [AMENDED].** `volatility_multiplier_for(text: str | None) -> float` helper. Returns `1.0` when `text is None` or empty. Truncate input: `text = text[:4096]` before the regex loop (T1 length cap). Compile each key with `re.escape(key)` for the `\b<key>\b` pattern (T1 metachar guard). Case-insensitive word-boundary search via `re.search(rf"\b{re.escape(key)}\b", text, re.IGNORECASE)` for each key. Return `max(matched multipliers)` or `1.0`. Docstring documents: "max across matched keys is intentional — most-volatile-topic-wins semantics." AC30 regression: `volatility_multiplier_for("a" * 10_000_000)` returns in <200ms and returns `1.0`.

- **AC16 [AMENDED].** `decay_days_for(ref: str, topics: str | None = None) -> int` accepts optional `topics` kwarg. When `topics` is provided, compute `mult = volatility_multiplier_for(topics)`. **Fallback BEFORE `int()` coercion:** `if not math.isfinite(mult) or mult <= 0: mult = 1.0`. Return `max(1, min(int(base_days * mult), SOURCE_DECAY_DEFAULT_DAYS * 50))` (clamp ceiling = 4500 days ~12 years per Q4). Default `topics=None` preserves backward-compat (no multiplier). Call sites (AC1, AC4) compose `topics` robustly — if `tags` is list, `" ".join(tags)`; if non-string, `str(tags)`; concatenate with title: `topics = f"{tags_str} {title}"` (R2 robustness).

### Augment (AC17) — [DROPPED]

- **AC17 [DROPPED].** Reverses cycle-13 AC2 deliberate decision; no observable failure case. Cycle-13 uncached `frontmatter.load` stays. See Q3.
- **AC31 [DROPPED].** Test for dropped AC.

### Loader (AC18–AC19) — [DROPPED]

- **AC18 [DROPPED].** Already shipped in cycle-14 AC23 at `utils/pages.py:164`. No production change needed.
- **AC19 [DROPPED].** Already shipped in cycle-14 AC23 at `utils/pages.py:163`. No production change needed.

### Tests (AC20–AC32)

- **AC20 [AMENDED].** `test_cycle15_query_decay_wiring.py` — matches rewritten AC1 (see AC1 fixtures above). Seeds multi-source page fixture for max-decay lenient-wins test.

- **AC21 [APPROVED].** `test_cycle15_query_tier1_wiring.py` — monkeypatches `CONTEXT_TIER1_SPLIT["summaries"]` to 10, asserts the tier-1 summaries budget in `_build_query_context` shrinks correspondingly (proves call-site uses the helper).

- **AC22 [AMENDED].** `test_cycle15_authored_by_boost.py` — asserts boost applied to human/hybrid, not applied to llm or absent. Invalid `authored_by: robot` → no boost, no raise. **T7 case:** seed a page with `authored_by: human` + MISSING `source` field (triggers `validate_frontmatter` error); assert no score multiplication (boost gate fires).

- **AC23 [AMENDED].** `test_cycle15_lint_decay_wiring.py` — `check_staleness` respects per-platform decay (arxiv page 1000d old NOT flagged; github page 200d old flagged). Add multi-source fixture: page with both arxiv and github sources, 300d old → NOT flagged (lenient max-over-sources).

- **AC24 [APPROVED].** `test_cycle15_lint_status_mature.py` — mature page 91d old flagged; mature page 89d not flagged; seed/developing pages ignored.

- **AC25 [AMENDED].** `test_cycle15_lint_authored_drift.py` — human page with in-scope ingest evidence entry flagged; hybrid page with same → not flagged; human page with only `action: edit` entries → not flagged. **T5 cases:** (a) `action: ingest` in code fence ABOVE `## Evidence Trail` → not flagged; (b) page with NO Evidence Trail section → not flagged. **CRLF case:** Evidence Trail with Windows line endings still matches the anchor.

- **AC26 [DROPPED].**

- **AC27 [AMENDED].** `test_cycle15_publish_atomic.py` — asserts the three builders call `atomic_text_write` via `monkeypatch.setattr("kb.compile.publish.atomic_text_write", spy)` and not `Path.write_text` directly. **T4 case:** simulate `os.replace` raising in AC11 path; assert no `.tmp` sibling remains in `out_path.parent` after failure.

- **AC28 [AMENDED].** `test_cycle15_publish_incremental.py` — second call with `incremental=True` short-circuits when all wiki pages older than output mtime; `incremental=False` regenerates; mtime-freshening a page re-triggers write. Use `os.utime(path, ns=(now_ns, now_ns))` for nanosecond-granular freshening (R2 flakiness guard). **T10c case:** seed output, then freshen a page AND tag it `belief_state: retracted`; re-run with `incremental=True` → regenerates AND filters the retracted page (proves mtime-based skip correctly invalidates on frontmatter edit AND epistemic filter runs before skip).

- **AC29 [AMENDED].** `test_cycle15_cli_incremental.py` — `kb publish --no-incremental` regenerates; `kb publish` (default) uses incremental. Use CliRunner.invoke; avoid `capsys` (R2 — use `result.output` instead). **T8 case:** `kb publish --out-dir=<tmp_path-outside-project> --no-incremental` → `UsageError`; containment-check path not regressed.

- **AC30 [AMENDED].** `test_cycle15_config_volatility.py` — `SOURCE_VOLATILITY_TOPICS` present as MappingProxyType (mutation raises); `volatility_multiplier_for` boundary match ("llm" fires; "reactor" does not); `decay_days_for("arxiv.org", topics="LLM agents")` returns `int(1095 * 1.1) = 1204`. **T1 case:** `volatility_multiplier_for("a" * 10_000_000)` returns <200ms, returns `1.0`. **T2 cases:** NaN / inf / negative / zero multipliers fall back to `1.0` before clamp; result stays in `[1, SOURCE_DECAY_DEFAULT_DAYS * 50]`.

- **AC31 [DROPPED].**

- **AC32 [AMENDED].** `test_cycle15_load_all_pages_fields.py` — regression test documenting cycle-14 contract. Asserts `load_all_pages` returns dicts with both `authored_by` and `belief_state` keys (empty-string default) for pages with and without those fields. Serves as the machine-checked anchor even though the production code shipped in cycle 14. Optional grep-audit in commit message listing `**page` spread consumers (R2).

### Docs (Step 12 outputs — NOT ACs)

- CHANGELOG.md cycle-15 entry under `[Unreleased]`. **Include T10c operator note:** "First post-upgrade `kb publish` run should use `--no-incremental` to regenerate any pre-cycle-14 outputs under the current epistemic filter."
- BACKLOG.md: delete closed entries (decay_days_for wiring, tier1_budget_for wiring, `authored_by` consumers, atomic publish writes, incremental publish, per-topic volatility multiplier). **New cycle-16 follow-up:** `AC8-carry` for status-aware enrichment routing (see CONDITIONS §2). Drop the AC17 backlog pointer entirely (cycle-13 decision holds). Drop the AC18/AC19 pointers (already shipped).
- CLAUDE.md: stats bump (tool count unchanged, test count updated); new cycle-15 notes under `## Implementation Status` for the wiring items.

---

## Scope tally (post-gate)

| Status | Count | ACs |
|---|---|---|
| Approved as-is | 4 | AC2, AC5, AC7, AC9, AC10, AC21, AC24 (7 — recounted) |
| Amended in place | 19 | AC1, AC3, AC4, AC6, AC11, AC12, AC13, AC14, AC15, AC16, AC20, AC22, AC23, AC25, AC27, AC28, AC29, AC30, AC32 |
| Dropped | 6 | AC8, AC17, AC18, AC19, AC26, AC31 |
| **Surviving total** | **26** | AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC9, AC10, AC11, AC12, AC13, AC14, AC15, AC16, AC20, AC21, AC22, AC23, AC24, AC25, AC27, AC28, AC29, AC30, AC32 |

**Recount:** approvals-as-is = {AC2, AC5, AC7, AC9, AC10, AC21, AC24} = 7. Amendments = 19. Dropped = 6. Total surviving = 7 + 19 = **26 ACs**. Minimum-viable-cycle floor (15 ACs) is comfortably cleared.

**Rewrite vs amendment disposition in Step 7:**
- Rewritten ACs (full re-spec required): AC1, AC14 (shape stable but textual rewrite needed)
- Pure-amendment ACs (localised text patch): AC3, AC4, AC6, AC11, AC12, AC13, AC15, AC16 + 10 test amendments (AC20, AC22, AC23, AC25, AC27, AC28, AC29, AC30, AC32)
- Untouched approvals: AC2, AC5, AC7, AC9, AC10, AC21, AC24

This is the Step 7 plan input.
