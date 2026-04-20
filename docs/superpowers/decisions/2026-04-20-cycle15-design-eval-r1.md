# Cycle 15 — R1 Opus Design-Eval (Step 4)

**Date:** 2026-04-20
**Reviewer:** R1 Opus (design-eval; assumptions/scope/framing focus)
**Inputs:** requirements.md (32 AC), threat-model.md (T1–T10 + 8 amendments), brainstorm.md (Approach A chosen), cycle-14 design-gate as format model.
**Method:** Grep-verified every cited symbol before scoring (feature-dev Red Flag compliance).

## Symbol verification (Step-1 red-flag gate)

All symbols cited by the 32 ACs exist at the claimed locations:

| Symbol | Location | Status |
|---|---|---|
| `decay_days_for` | `src/kb/config.py:382` | EXISTS (ref-only, no topics kwarg yet) |
| `tier1_budget_for` | `src/kb/config.py:350` | EXISTS |
| `_apply_status_boost` | `src/kb/query/engine.py:277` | EXISTS (validate_frontmatter-gated) |
| `_flag_stale_results` | `src/kb/query/engine.py:366` | EXISTS (uses newest-source-mtime; no per-source decay) |
| `_build_query_context` | `src/kb/query/engine.py:636` | EXISTS (imports CONTEXT_TIER1_BUDGET at line 650) |
| `check_staleness` | `src/kb/lint/checks.py:299` | EXISTS (flat `max_days=STALENESS_MAX_DAYS`) |
| `run_all_checks` | `src/kb/lint/runner.py:25` | EXISTS |
| `suggest_new_pages` | `src/kb/evolve/analyzer.py:195` | EXISTS (sorts by referenced_by count; no status key) |
| `analyze_coverage` | `src/kb/evolve/analyzer.py:30` | EXISTS |
| `build_llms_txt` | `src/kb/compile/publish.py:93` | EXISTS (uses `out_path.write_text` at :136) |
| `build_llms_full_txt` | `src/kb/compile/publish.py:140` | EXISTS (uses `out_path.write_text` at :212) |
| `build_graph_jsonld` | `src/kb/compile/publish.py:216` | EXISTS (uses `json.dump`) |
| `_post_ingest_quality` | `src/kb/lint/augment.py:1108` | EXISTS (intentionally uses `frontmatter.load(str(...))` at :1133, cycle-13 AC2 comment preserved) |
| `_mark_page_augmented` | `src/kb/lint/augment.py:1059` | EXISTS |
| `_record_verdict_gap_callout` | `src/kb/lint/augment.py:1036` | EXISTS |
| `load_all_pages` | `src/kb/utils/pages.py:113` | EXISTS **— already returns `status`, `belief_state`, `authored_by` as of cycle 14 (lines 162–164)** |
| `load_page_frontmatter` | `src/kb/utils/pages.py:65` | EXISTS (LRU-cached with `cache_clear()` surfaced at :91) |
| `save_page_frontmatter` | `src/kb/utils/pages.py:240` | EXISTS (cycle-14 AC16 wrapper) |
| `atomic_text_write` | `src/kb/utils/io.py:93` | EXISTS |
| `atomic_json_write` | `src/kb/utils/io.py:58` | EXISTS |
| `SOURCE_DECAY_DAYS` | `src/kb/config.py:371` | EXISTS |
| `SOURCE_DECAY_DEFAULT_DAYS` | `src/kb/config.py:379` | EXISTS (= STALENESS_MAX_DAYS) |
| `CONTEXT_TIER1_SPLIT` | `src/kb/config.py:342` | EXISTS |
| `STATUS_RANKING_BOOST` | `src/kb/config.py:425` | EXISTS (`= 0.05`) |

One **critical discrepancy** surfaced: `load_all_pages` already returns `authored_by` (line 164) and `belief_state` (line 163) as additive keys. The cycle-14 AC23 comment block explicitly states "optional epistemic-integrity frontmatter fields surfaced as additive keys." This invalidates the framing of AC18/AC19 as work to do. See AC18/AC19 cluster below.

## Cluster 1 — Query engine wiring (AC1–AC3)

### ## Analysis

AC1 is a textbook helper-substitution: `_flag_stale_results` currently computes freshness as `newest_source_mtime > page_date` (engine.py:397) — a wiki-vs-source comparison with no `STALENESS_MAX_DAYS` input. The AC text claims "flat `STALENESS_MAX_DAYS`" is being replaced, but grep shows the current function does **not** use `STALENESS_MAX_DAYS` at all — it uses `date` from the source mtime directly. This is a framing error: the AC as written doesn't describe the actual current code path. What the AC probably intends is: "introduce a per-source decay-days gate so that source_refs on long-decay platforms (arxiv=1095d) only flag as stale when the gap exceeds the decay window, rather than the current behaviour of flagging whenever source mtime > page mtime by any amount." That's a behavioural CHANGE, not a helper substitution — and the AC as written is untestable because the pass/fail assertion ("identical for sources matching default 90d") doesn't match the present semantics. This needs a rewrite before Step 7 can plan against it.

AC2 is clean: `_build_query_context` at engine.py:650 does `from kb.config import CONTEXT_TIER1_BUDGET, CONTEXT_TIER1_BUDGET` and the tier-1 loop at :652 computes `effective_max = min(max_chars, CONTEXT_TIER1_BUDGET + CONTEXT_TIER2_BUDGET)`. The AC's assertion that `tier1_budget_for("summaries") == (CONTEXT_TIER1_BUDGET * 60) // 100` is mathematically correct per config.py:363 and is atomically testable via monkeypatch on `CONTEXT_TIER1_SPLIT`. Note however that the function currently uses `CONTEXT_TIER1_BUDGET` (not `CONTEXT_TIER1_SPLIT["summaries"]`), so the test assertion in AC21 (monkeypatching `CONTEXT_TIER1_SPLIT["summaries"]` to 10 and expecting budget shrink) only works if the migration routes through `tier1_budget_for("summaries")`. That requirement is clear — ship it.

AC3 introduces `_apply_authored_by_boost` modelled on `_apply_status_boost`. The AC text says "ungated on `validate_frontmatter` pass (same as `_apply_status_boost`)" — ambiguous phrasing: "ungated" could read as "no gate", but the parenthetical makes clear the intent is "same gating as `_apply_status_boost`". Threat T7 correctly flags this and recommends the explicit clarification. The AC also introduces a new config constant `AUTHORED_BY_BOOST = 0.02` — but there is **no dedicated AC for adding the constant to `config.py`**. Cycle 14's pattern added `STATUS_RANKING_BOOST = 0.05` (AC23's decided-at-gate Q10 answer) as an explicit requirement. Cycle 15 AC3 embeds the constant requirement inside the boost-helper AC; future readers of the requirements doc will miss the config surface. This wants either a split (AC3a = helper, AC3b = config constant) OR an amendment making the constant requirement explicit inside AC3.

### Verdicts

- **AC1 — REJECT.** Current `_flag_stale_results` does not use `STALENESS_MAX_DAYS`; it compares page `updated` date against the newest source file's mtime. AC text mis-describes the present code path and the assertion "identical for pages whose source matches default (90d)" is not testable against the actual semantics. **Required:** rewrite AC1 to state the new behaviour in terms of the current code: "replace the `newest_source_mtime > page_date` check at engine.py:397 with `(today - page_date).days > decay_days_for(source_ref)` for each result, where `source_ref` is the first entry of the page's `sources` list. A page with source on arxiv.org (1095-day decay) updated 1000 days ago: NOT stale. A page with source on github.com (180-day decay) updated 200 days ago: stale. A page with no sources: falls back to `SOURCE_DECAY_DEFAULT_DAYS=90` comparison against `today`." The test in AC20 must be rewritten to match.

- **AC2 — APPROVE.** Clean helper substitution with atomic monkeypatch test in AC21.

- **AC3 — APPROVE WITH AMENDMENT:** Split the config requirement out: add the text "introduces `AUTHORED_BY_BOOST = 0.02` in `src/kb/config.py` adjacent to `STATUS_RANKING_BOOST`" as an explicit second bullet in AC3 (or promote to its own AC3a). Also per Threat T7: replace "Ungated on `validate_frontmatter` pass" with "Gated identically to `_apply_status_boost`: reconstructs a `_PostLike` with the full metadata dict and returns the page unchanged if `validate_frontmatter(post)` reports any errors." Literal copy of the status-boost structure.

## Cluster 2 — Lint checks (AC4–AC7)

### ## Analysis

AC4 rewires `check_staleness` to per-page decay via `decay_days_for(source_ref)`. The AC's "callers can still override via `max_days` kwarg (takes precedence)" is the right shape for backward compat — `run_all_checks` calls `check_staleness(wiki_dir, pages=shared_pages)` without `max_days`, so the default-path migration is clean. Per-page override is only invoked through direct library calls (e.g. tests that fix `max_days=30`). One subtle question the AC doesn't answer: WHICH source is used when a page has multiple sources? `check_staleness` should iterate all sources and use the MAX decay window (be lenient — if any source platform tolerates 1095d, don't flag as stale at 200d). AC4 is silent on this. Recommend amendment.

AC5 introduces `check_status_mature_stale` — a NEW check that fires on `status: mature` + `updated` more than 90 days old. This is behaviour, not a substitution. The AC text is atomic and testable. But: 90d is a hardcoded literal inside the AC. If cycle-15 rolls out per-topic volatility (AC14–AC16), the mature-page freshness window should plausibly ALSO feed through `decay_days_for(source, topics=…)` rather than a flat 90. The AC's choice to hardcode 90d is defensible for scope control, but it's inconsistent with the concurrent per-topic wiring being introduced in the same cycle. Not a blocker — flag as a follow-up. The severity level `warning` (not `error`/`info`) is consistent with cycle-14's `check_frontmatter_staleness` warning.

AC6 is the most interesting check. The intent ("human-authored pages shouldn't have ingest-action evidence entries") is sound. Threat T5 correctly flags the false-positive surface: naive body-wide regex fires on any page discussing ingest. The fix is scoping the regex to the span between `## Evidence Trail` header and the next `##` header. The `src/kb/ingest/evidence.py:96` anchor `re.search(r"^## Evidence Trail\r?\n", content, re.MULTILINE)` exists and is reusable — good. One T5-adjacent gap the threat model misses: Evidence Trail entries are **reverse-chronological**, and a migrated page could have `action: ingest` entries AT THE TOP of the trail while the page is authored_by: human via a later manual override. The AC doesn't specify whether this case is flagged or not. Present AC wording ("at least one entry with `action: ingest`") fires; the operator's expected remediation in that case is "drop authored_by or change to hybrid" per the message template — which is correct semantics. Ship the amendment, flag for a potential AC27-follow-up in docs.

AC7 is a one-liner wiring both new checks into `run_all_checks`. Reading `lint/runner.py`: `run_all_checks` already threads `shared_pages = scan_wiki_pages(wiki_dir)` through every downstream check. AC5 and AC6 will plug in exactly the same way (`stale_mature = check_status_mature_stale(shared_pages); all_issues.extend(stale_mature)` + `checks_run.append(…)`). Trivial. Zero review risk.

### Verdicts

- **AC4 — APPROVE WITH AMENDMENT:** Add a tie-breaker clause: "When a page has multiple sources, use the maximum `decay_days_for` across all sources (lenient — longest-decay platform wins)." Rationale: a page citing both arxiv.org and github.com should not be flagged stale at day 200 just because one of its sources is on the 180d decay list.

- **AC5 — APPROVE.** Hardcoded 90d is acceptable scope control. Flag follow-up: future cycles may route this through `decay_days_for(…, topics=…)` for consistency.

- **AC6 — APPROVE WITH AMENDMENT (T5):** Add explicit scope-bounding: "scan only the body span between the `## Evidence Trail` header and the next `##`-level header (or EOF). Pages lacking an Evidence Trail section emit no warning (absence of signal ≠ drift event). Reuse the header anchor from `src/kb/ingest/evidence.py:96`." Matches the threat-model T5 mitigation verbatim.

- **AC7 — APPROVE.** Trivial wiring.

## Cluster 3 — Evolve seed-priority (AC8)

### ## Analysis

AC8 stable-sorts `suggest_new_pages` so `status: seed` pages come first. Reading `evolve/analyzer.py:195`: the function returns dicts with shape `{target, referenced_by, suggestion}` — each `target` is a dead-link target (i.e., a page ID that does NOT yet exist in the wiki). `status` is a frontmatter field on EXISTING pages. **There's a category error here.** A suggestion's "target" is by definition NOT yet a page in the wiki, so it has no frontmatter and no `status` value. The AC's "feed 4 pages (seed / developing / mature / missing) → seed emerges first" test description implies the function takes existing pages as inputs and sorts them — but that's `suggest_connections` or `analyze_coverage`, not `suggest_new_pages`.

This suggests the AC meant a DIFFERENT function, OR means "when sorting the `referenced_by` list within each suggestion, sort pages with `status: seed` first" (but that's a secondary sort on a display-only field). OR the AC is conflating `suggest_new_pages` with the `evolve/analyzer.py::find_connection_opportunities` or stub-enrichment suggestion path. The BACKLOG entry "status frontmatter: kb_evolve should target seed pages" (cycle-14 AC26 follow-up) suggests the intent is "when enumerating existing pages as enrichment candidates, prioritise seed ones" — that's a different function entirely.

Either the AC targets the wrong function, or the pass/fail assertion is ambiguous. Cannot ship as written.

### Verdicts

- **AC8 — REJECT.** Function-target mismatch. `suggest_new_pages(analyzer.py:195)` returns dead-link targets (pages that don't exist yet), which cannot have a `status` frontmatter value. The AC test description implies existing-page sorting. **Required:** either (a) retarget the AC to `find_connection_opportunities` / a new `suggest_enrichment_targets` helper that iterates existing pages with `status in {seed, developing}`, or (b) re-scope AC8 to secondary-sort the `referenced_by` list within each suggestion (pages that reference this missing target) by status. Recommend (a) — matches the cycle-14 BACKLOG follow-up intent. If (a), the new function needs its own grep-verification at Step 1.

## Cluster 4 — Publish atomicity + incremental (AC9–AC12)

### ## Analysis

AC9 and AC10 are clean atomic-write migrations. Current code (`publish.py:136` and `publish.py:212`) uses `out_path.write_text(..., encoding="utf-8")` — direct write without temp+rename. Switching to `atomic_text_write(content, out_path)` reuses the audited cycle-14 helper at `utils/io.py:93`. The existing UTF-8 byte-cap loop in `build_llms_full_txt` is preserved. Atomic write is a strict improvement. Ship.

AC11 for `build_graph_jsonld` is subtler. Current code uses `json.dump(obj, f, ...)` (cycle-14 T3 requirement to avoid f-string assembly). Threat T4 correctly identifies that a naive `tempfile.mkstemp()` without `dir=out_path.parent` lands the temp file on the system temp volume, potentially a different filesystem from the output, which breaks atomicity of `os.replace`. The mitigation says "reuse `atomic_text_write`" — but `atomic_text_write` takes a `content: str`, and `build_graph_jsonld` currently streams via `json.dump(obj, f, ...)` to preserve indent-2 pretty formatting plus `ensure_ascii=False` semantics. Calling `atomic_text_write(json.dumps(obj, ensure_ascii=False, indent=2), out_path)` achieves the same result and is cleaner than hand-rolling `tempfile.mkstemp(dir=out_path.parent)`. The AC is silent on WHICH approach to take — it says "temp-file + os.replace pattern" without mandating colocation. Per T4 this needs to be explicit.

AC12 introduces `_publish_skip_if_unchanged` and threads `incremental: bool = False` through all three builders. Default `False` preserves cycle-14 test contracts. The threat-model T3 + T10c flags surface the right concerns: mtime TOCTOU (single-writer documented), and the pre-cycle-14 epistemic-filter-miss edge case. The AC text already specifies "when True + `out_path.exists()` + `max(page.stat().st_mtime for page in wiki_dir iterator) <= out_path.stat().st_mtime`, the function short-circuits." One implementation nuance not in the AC: the mtime iterator needs to walk `scan_wiki_pages(wiki_dir)` (the same streaming path the builders use); a naive `wiki_dir.rglob("*.md")` would pick up `log.md`, `_sources.md`, `_categories.md`, `contradictions.md`, `index.md` — files that legitimately mutate without needing a publish regen. Amendment required.

Also: the "T2 epistemic filter runs before skip" invariant is listed in T10c as verify-at-step11, but the AC12 text does NOT enforce ordering. This should be in the AC so Step 7 planners don't re-order.

### Verdicts

- **AC9 — APPROVE.** Clean atomic-write migration.

- **AC10 — APPROVE.** Same shape as AC9.

- **AC11 — APPROVE WITH AMENDMENT (T4):** Mandate the `atomic_text_write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", out_path)` form OR explicitly require `tempfile.mkstemp(dir=out_path.parent, ...)`. Bare `tempfile.mkstemp()` (system-temp-dir default) is unacceptable on Windows/OneDrive cross-volume scenarios. Prefer the `atomic_text_write` form — it reuses the audited cleanup path.

- **AC12 — APPROVE WITH AMENDMENT:** (a) specify the mtime iterator explicitly: "`max(page.stat().st_mtime_ns for page in scan_wiki_pages(wiki_dir))`" — use `st_mtime_ns` for nanosecond granularity (per threat T3) and restrict to the canonical wiki-page scan (excludes auto-maintained index files whose mutations should not trigger republish). (b) Add to the AC docstring requirement: "docstring MUST note single-writer assumption (threat T3)." (c) Add an ordering invariant: "the cycle-14 T2 epistemic filter (belief_state / confidence) and T1 out-dir containment run BEFORE the skip branch." This makes T10c a testable AC clause rather than a Step-11-verify-only item.

## Cluster 5 — CLI flag (AC13)

### ## Analysis

Reading `cli.py:340–403`: the `publish` subcommand already has `--out-dir` and `--format` options, with `fmt` as the Python kwarg bound to `--format`. The cycle-14 T1 containment check is at lines 369–388 (resolve + `..` reject + UNC reject + `is_relative_to(PROJECT_ROOT)` OR `is_dir()` pre-exist). Flow order is: (1) compute `target_dir`, (2) reject `..`, (3) `resolve`, (4) reject UNC, (5) containment-or-pre-exist check, (6) `mkdir`, (7) call builders. AC13 adds a Click flag and plumbs it into builder kwargs — it does NOT interact with path validation. Threat T8 correctly flags the risk of regressing the check order during refactor; the mitigation is a regression test + source-order grep.

One gap: the AC text says "All three builders called with `incremental=<flag>`" — but doesn't say WHERE in the existing flow (after `mkdir`, per the above order). Should be explicit that plumbing happens inside the `try:` block at lines 391–402, NOT by reordering the containment check.

Default `--incremental` (default on) vs `--no-incremental` (opt-out regen) is the correct choice per the threat-model T10c recommendation to run a `--no-incremental` on first upgrade — that's a one-time operator action, not a steady-state default.

### Verdicts

- **AC13 — APPROVE WITH AMENDMENT (T8):** Add to AC text: "flag plumbing into builder kwargs happens inside the existing `try:` block at `cli.py:391`, AFTER the cycle-14 T1 containment check at lines 369–388; `mkdir(parents=True, exist_ok=True)` stays at line 389. Click-flag addition must not reorder these steps. Regression test `test_out_dir_containment_preserved` asserts `kb publish --out-dir=<outside-project> --no-incremental` still raises `UsageError` before any mkdir." Ship the first-run `--no-incremental` guidance as AC26 doc content (see Scope gaps below).

## Cluster 6 — Config: volatility multiplier (AC14–AC16)

### ## Analysis

AC14 introduces `SOURCE_VOLATILITY_TOPICS: dict[str, float]` with six keys. The dict-of-multiplier choice (vs. tuple-of-strings + flat 1.1) is per-topic flexible and matches cycle-14's `SOURCE_DECAY_DAYS` precedent. Ship.

AC15 defines `volatility_multiplier_for`. Threat T1 correctly flags two risks: (a) attacker-plantable `tags`/`title` into regex loop → length cap at 4096 chars; (b) future contributor adds a key with regex metacharacters → `re.escape(key)` the substring before interpolation. The AC text mentions neither. Must amend.

One additional T1 concern the threat model DOESN'T fully nail: `re.IGNORECASE` plus Unicode case-folding can have locale surprises for non-ASCII matches. The current key set is all ASCII, so low risk, but a `re.ASCII` flag would be defensive. Recommend adding as a documentation note, not a blocker.

AC16 extends `decay_days_for` with a `topics` kwarg. Threat T2 correctly flags arithmetic risks: negative / zero / NaN / inf multipliers produce nonsense decay windows. The proposed clamp `max(1, min(base_days * mult, SOURCE_DECAY_DEFAULT_DAYS * 50))` + `math.isfinite(mult) or 1.0` fallback is sound. The AC text should embed the clamp requirement verbatim. Also: the AC currently says "result = `int(base_days * volatility_multiplier_for(topics))`" — the `int()` coercion on a `nan` raises `ValueError: cannot convert float NaN to integer` on CPython, so the fallback must happen BEFORE the `int()` call. Explicit amendment required.

Additional nuance AC16 punts on: `volatility_multiplier_for` returns `max` across matched keys per AC15. Is this the right semantics? If a page tag list contains "llm" AND "docker" (both 1.1), the max is still 1.1. If a future key set has `"llm": 1.1, "rust": 1.5`, a page tagged both would take 1.5. This is implicitly correct ("most volatile topic wins, extends decay"). But the AC should state this explicitly so a future contributor doesn't "fix" it to min or mean.

### Verdicts

- **AC14 — APPROVE.** Dict-of-float matches existing per-platform pattern.

- **AC15 — APPROVE WITH AMENDMENT (T1):** Add implementation-detail clauses: "(a) truncate `text` to `text[:4096]` before the regex loop to prevent pathological-length DoS; (b) compile each key with `re.escape(key)` so future metachar keys cannot corrupt the pattern; (c) document in docstring that `max()` across matched keys is intentional (most-volatile-wins semantics)." Test `test_volatility_multiplier_for_pathological_input` asserts `volatility_multiplier_for("a" * 10_000_000)` returns in <200 ms.

- **AC16 — APPROVE WITH AMENDMENT (T2):** Replace "result = `int(base_days * volatility_multiplier_for(topics))`" with: "let `mult = volatility_multiplier_for(topics)`; if `not math.isfinite(mult)` or `mult <= 0`: `mult = 1.0`; return `max(1, min(int(base_days * mult), SOURCE_DECAY_DEFAULT_DAYS * 50))`." The fallback must precede the `int()` call to avoid `ValueError` on NaN. Default `topics=None` preserves backward-compat (no multiplier applied).

## Cluster 7 — Augment cache invalidation (AC17)

### ## Analysis

AC17 flips `_post_ingest_quality` from `frontmatter.load(str(path))` (currently at augment.py:1133) to `load_page_frontmatter(page_path)` preceded by `load_page_frontmatter.cache_clear()`. The claim is that same-process writes via `_mark_page_augmented` / `_record_verdict_gap_callout` happen seconds before and the cache needs invalidation.

Reading the current augment.py:1128–1133 comment: "Cycle 13 AC2 (scope): Intentionally uses uncached frontmatter.load. This read may immediately follow same-process writes from _mark_page_augmented / _record_verdict_gap_callout. On FAT32 / OneDrive / SMB (coarse mtime resolution), the cached helper could return stale metadata. Design gate Q11."

This is **a cycle-13 deliberate decision** that AC17 is reversing. Why? The claim in the AC header is "Rationale: same-process writes from `_mark_page_augmented` / `_record_verdict_gap_callout` happen seconds before; cache must be invalidated explicitly." But that's exactly the concern cycle-13 solved by using uncached `frontmatter.load`! Uncached load is already stale-free. Switching to cached+cache_clear is MORE fragile:

1. `cache_clear()` is process-wide (threat T6), so every other page's cached entry is evicted every time `_post_ingest_quality` runs, causing slow-path re-reads across the whole lint pipeline.
2. On coarse-mtime filesystems, `cache_clear` still leaves the mtime-coalescence hole: if the in-cache entry is evicted but the file mtime hasn't advanced, the NEXT reader re-caches the same stale payload.

The current uncached-load approach sidesteps both issues. AC17 changes the mechanism to a more complex one that solves no observable bug and adds new perf/correctness risks. **This looks like a regression disguised as a feature.**

If the real goal is "route every frontmatter read through the single helper for consistency," that's an architectural preference, not a bug fix. The cycle-13 comment's rationale remains valid; the cache_clear approach doesn't improve on it.

Unless the requirements author has a specific observed failure from the current uncached-load path that AC17 is meant to address, this AC should be DROPPED (like cycle-14 dropped AC13/AC14/AC15 as no-op).

### Verdicts

- **AC17 — REJECT.** No observable bug is being fixed; cycle-13 AC2 intentionally uses uncached `frontmatter.load` to avoid exactly this cache-invalidation problem. Switching to `load_page_frontmatter` + `cache_clear()` introduces process-wide cache eviction (T6) and leaves the coarse-mtime hole that cycle-13's uncached approach already closed. **Required:** either (a) drop the AC entirely and keep the cycle-13 behaviour, or (b) provide a concrete failure case (test that fails under uncached-load) that AC17 is meant to fix — then amend the AC to document that failure mode. Absent (b), prefer (a).

## Cluster 8 — Loader additive keys (AC18–AC19)

### ## Analysis

Grep of `src/kb/utils/pages.py:162–164` shows:
```python
"status": str(metadata.get("status", "")),
"belief_state": str(metadata.get("belief_state", "")),
"authored_by": str(metadata.get("authored_by", "")),
```

The cycle-14 AC23 comment block (lines 157–161) explicitly states: "Cycle 14 AC23 + AC1 — optional epistemic-integrity frontmatter fields surfaced as additive keys. Existing consumers ignore; publish builders and the status ranking boost read directly. Empty string when absent so downstream membership checks are safe."

**AC18 and AC19 describe work that is already shipped.** This is cycle-14 AC13/AC14/AC15-class duplicate work. The cycle-14 design gate explicitly noted that AC23 added all three keys at once. Cycle-15 requirements cite "Closes cycle-14 L3 loader-side atomicity gap for the remaining two vocabulary fields" — but the fields were already atomic with `status` in cycle 14 because the loader added all three simultaneously, not piecemeal.

Checking the AC text against threat T9: T9 says "Cycle-14 AC23 already added the `status` key as additive; cycle-15 repeats the pattern for the remaining two vocabulary fields." That framing accepts the AC-18/19 premise. But the CODE shows all three fields added in the same dict-construction block. The T9 threat is real (if you add new keys, downstream strict-schema consumers may break) — but the threat landed in CYCLE 14, not cycle 15. A T9-addressing test is valuable regardless (document contract that these keys exist), but the production code change is a no-op.

AC32 test (`test_cycle15_load_all_pages_fields`) still has value as a regression test documenting the cycle-14 contract — keep the test, drop the production ACs.

### Verdicts

- **AC18 — REJECT (DROP AS DUPLICATE):** `load_all_pages` already emits `authored_by` at `utils/pages.py:164` as of cycle 14 AC23. Production code change is a no-op. Mirror cycle-14's AC13/14/15 drop pattern.

- **AC19 — REJECT (DROP AS DUPLICATE):** `load_all_pages` already emits `belief_state` at `utils/pages.py:163` as of cycle 14 AC23. Production code change is a no-op.

- **Recommended:** keep AC32 as a regression test that asserts both keys are present and default to `""`. The test is a useful contract anchor even when the production work is already done.

## Cluster 9 — Tests (AC20–AC32)

### ## Analysis

AC20 — depends on AC1. If AC1 is rewritten (as required above), AC20 test must track. Current AC20 text "seeds pages with `source: arxiv.org/...` (decay=1095d) vs `github.com/...` (decay=180d); asserts `_flag_stale_results` respects per-source decay" is the right SHAPE; the pass/fail assertion must match the rewritten AC1 semantics.

AC21 — clean monkeypatch test for AC2. Ship.

AC22 — AC3 test. Should exercise T7 mitigation (invalid frontmatter → no boost). Current text covers "invalid `authored_by: robot` → no boost, no raise" — good, but doesn't exercise the validate_frontmatter path where `authored_by: human` + missing `source` triggers no-boost. Threat T7 specifically calls for that test. Amend.

AC23 — AC4 test. Scope: per-platform decay. If AC4 amendment adds max-over-sources semantics, the test must include a multi-source page fixture. Ship with matching amendment.

AC24 — AC5 test. Clean; "mature + 91d → flag, mature + 89d → no flag, seed/developing ignored" is atomic.

AC25 — AC6 test. Must exercise T5 mitigation (action: ingest outside Evidence Trail does NOT fire). Current text covers "human page with ingest evidence entry flagged; hybrid page with ingest entry not flagged; human page with only `action: edit` entries not flagged" — good but doesn't cover the T5 false-positive case (action: ingest in a code fence above the Evidence Trail). Amend to include T5 assertion.

AC26 — AC8 test. Blocked on AC8 rewrite (see Cluster 3). Cannot ship as written.

AC27 — AC9/AC10/AC11 test. Spy via monkeypatch on `kb.compile.publish.atomic_text_write` is the right approach. For AC11/JSON-LD, also need to exercise the cross-volume fallback (T4) — simulate `tempfile.mkstemp` returning a path on a different volume and assert no partial write. Current AC text doesn't include this. Amend.

AC28 — AC12 test. Text is atomic and covers the three cases (skip, force-regen, mtime-freshen re-trigger). Should also cover the T10c case: "page freshened with `belief_state: retracted` re-triggers write and is filtered from output." Include.

AC29 — AC13 CLI test. Should also exercise T8 (containment preserved under `--no-incremental`). Amend.

AC30 — AC14/AC15/AC16 combined test. Covers boundary match (llm fires, reactor does not — exact T1 edge case) + arithmetic (`int(1095 * 1.1) = 1204`). Should also cover T2 (NaN/inf/negative multiplier clamp). Amend.

AC31 — AC17 test. Blocked on AC17 disposition; if AC17 is dropped, this test is moot.

AC32 — AC18/AC19 test. As noted above, still valuable as a regression test documenting the cycle-14 contract. Keep it even if AC18/AC19 are dropped.

### Verdicts

- **AC20 — APPROVE WITH AMENDMENT:** Track the rewritten AC1 semantics.
- **AC21 — APPROVE.**
- **AC22 — APPROVE WITH AMENDMENT:** Add the T7 invalid-frontmatter case (authored_by: human + missing source → no boost).
- **AC23 — APPROVE WITH AMENDMENT:** Add multi-source max-decay fixture per AC4 amendment.
- **AC24 — APPROVE.**
- **AC25 — APPROVE WITH AMENDMENT:** Add T5 case (action: ingest in code fence outside Evidence Trail → not flagged; page without Evidence Trail → not flagged).
- **AC26 — REJECT:** Blocked on AC8 rewrite.
- **AC27 — APPROVE WITH AMENDMENT:** Add T4 cross-volume fallback assertion for build_graph_jsonld.
- **AC28 — APPROVE WITH AMENDMENT:** Add T10c retracted-page-freshen test.
- **AC29 — APPROVE WITH AMENDMENT:** Add T8 containment-preserved case.
- **AC30 — APPROVE WITH AMENDMENT:** Add T2 NaN/inf/negative-multiplier clamp cases.
- **AC31 — REJECT (MOOT):** Drop with AC17.
- **AC32 — APPROVE WITH AMENDMENT:** Reframe as a regression test documenting cycle-14 contract; keep as a contract anchor even with AC18/AC19 dropped.

## Scope gaps (threat model items that want new ACs)

### ## Analysis

Two threat items surfaced needs that aren't captured in the 32 ACs and arguably want new ACs or explicit scope items:

**T10c operator guidance.** The threat model recommends: "document that the first post-cycle-14 publish run should be `--no-incremental`" — because pre-cycle-14 outputs were written without the T2 epistemic filter, and the mtime-based skip could retain retracted content if operators don't force regen once. The cycle-15 requirements doc's "Docs" section mentions CHANGELOG + BACKLOG + CLAUDE.md updates but does NOT include an explicit first-run-no-incremental guidance bullet. This should be a **new explicit line** in the "Docs (Step 12 outputs)" section. Not a new AC (behavior isn't testable in CI) but a Step-12 documentation deliverable.

**T6 code-comment discipline.** Per T6 mitigation, the AC17 cache_clear call (if it ships) needs an adjacent code comment explaining the process-wide scope. Since AC17 is recommended for REJECT above, this becomes moot. But if the design-gate keeps AC17 in some form, the code-comment requirement must be explicit in the AC text, not just in the threat model.

**Config constant AUTHORED_BY_BOOST.** As noted in AC3 analysis, there's no AC for adding the constant to `config.py`. Cycle 14 surfaced this for `STATUS_RANKING_BOOST` via design-gate Q10. Recommend splitting AC3 or adding an explicit line.

**8 threat-model amendments correctly scoped?** Checking each:

| Amendment | Target AC | Fit |
|---|---|---|
| T1 → AC15 (re.escape + length cap) | AC15 | CORRECT AC — implementation detail fits inside the helper definition |
| T2 → AC16 (clamp + isfinite) | AC16 | CORRECT AC — arithmetic correctness inside the helper |
| T3 → AC12 (single-writer docstring + st_mtime_ns) | AC12 | CORRECT AC — behavior of the skip branch |
| T4 → AC11 (colocated temp file OR atomic_text_write) | AC11 | CORRECT AC — implementation surface |
| T5 → AC6 (scope regex to Evidence Trail span) | AC6 | CORRECT AC — check semantics |
| T6 → AC17 (comment for cache_clear) | AC17 | AC17 recommended REJECT; moot |
| T7 → AC3 (validate_frontmatter gate) | AC3 | CORRECT AC — helper gating |
| T8 → AC13 (preserve containment order) | AC13 | CORRECT AC — flag plumbing |
| T10c → Step 12 docs | (no AC) | Needs explicit line in "Docs (Step 12 outputs)" section |

Seven of eight amendments land on the correct AC. The eighth (T10c) belongs as a docs deliverable not a production AC — correctly framed by the threat model, just needs to be pulled into the requirements doc's Docs section.

### Verdicts

- **Scope gap 1 — AMEND requirements doc:** Add to "Docs (Step 12 outputs)" section: "CHANGELOG.md notes that the first post-upgrade `kb publish` run should use `--no-incremental` to ensure pre-cycle-14 outputs are regenerated under the current epistemic filter (threat T10c)."

- **Scope gap 2 — AMEND AC3:** Explicit config-constant addition (see AC3 verdict above).

- **Threat-model amendments scoping — APPROVED** (7 of 8 correctly scoped; T10c needs docs-section pull-in per Gap 1).

## Cross-cycle consistency check

### ## Analysis

**Cycle-14 L3 loader-atomicity rule.** Cycle 14's L3 lesson is that vocabulary-adjacent loader keys should ship together, not piecemeal, to avoid partial-vocabulary bugs. Cycle 14 AC23 already shipped ALL THREE (`status`, `belief_state`, `authored_by`) simultaneously — so the L3 rule is already satisfied. AC18/AC19 framing that "closes cycle-14 L3 loader-side atomicity gap for the remaining two vocabulary fields" is inaccurate: there is no gap. (Verdict on AC18/AC19 already reflects this — drop as duplicates.)

**Approach A rationale check.** The brainstorm doc argues Approach A matches cycle-14's batch-by-file shape. Verified: cycle 14 shipped 21 ACs across ~15 files, cycle 15 targets ~32 ACs across 9 source files + 13 test files. Shape is comparable. The < 30 LoC per task heuristic holds for AC2/AC4/AC9/AC10/AC11/AC13 (substitutions) and AC5/AC6/AC14/AC15/AC16 (new helpers/checks under 30 LoC each). AC12 is borderline — incremental skip branch + 3-builder plumbing might be 40-50 LoC. Acceptable for a batch cycle. Shipping inline-in-primary per cycle-13 L2 is reasonable.

**Nongoals check.** The non-goals list includes "HIGH concurrency cluster (manifest races, inject_wikilinks locks, slug collisions)" as explicit non-goal. Good — avoids cycle-14-style scope creep. The T3 (TOCTOU race on incremental publish) threat landed squarely against this non-goal; the chosen mitigation is "document single-writer assumption + provide --no-incremental escape hatch" which is the correct scope-controlled response.

### Verdict

- **Cross-cycle consistency — APPROVE.** Approach A framing is sound; non-goals correctly constrain scope; single significant mis-framing (AC18/AC19 as needing work) is addressed above.

## Summary of amendments

| AC | Verdict | Amendment |
|---|---|---|
| AC1 | REJECT | Rewrite against actual `_flag_stale_results` semantics (today-minus-page-date > decay_days_for(source_ref)), not "flat STALENESS_MAX_DAYS" which the function doesn't use |
| AC2 | APPROVE | — |
| AC3 | APPROVE WITH AMENDMENT | Add `AUTHORED_BY_BOOST = 0.02` to config.py as explicit second bullet; replace "ungated on validate_frontmatter pass" with literal "same gating as _apply_status_boost: reconstructs _PostLike, calls validate_frontmatter, no-op on errors" |
| AC4 | APPROVE WITH AMENDMENT | Add max-over-sources clause for multi-source pages (longest-decay wins) |
| AC5 | APPROVE | — |
| AC6 | APPROVE WITH AMENDMENT | Scope regex to span between `## Evidence Trail` header and next `##` header; reuse anchor from ingest/evidence.py:96 (T5) |
| AC7 | APPROVE | — |
| AC8 | REJECT | Function-target mismatch; `suggest_new_pages` returns dead-link targets which have no frontmatter. Either retarget to a new enrichment-suggester that iterates existing pages, or re-scope to secondary-sort of referenced_by lists |
| AC9 | APPROVE | — |
| AC10 | APPROVE | — |
| AC11 | APPROVE WITH AMENDMENT | Mandate `atomic_text_write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", out_path)` OR explicitly require `tempfile.mkstemp(dir=out_path.parent, ...)`; bare mkstemp() unacceptable (T4) |
| AC12 | APPROVE WITH AMENDMENT | (a) mtime iterator uses `scan_wiki_pages(wiki_dir)` not bare rglob; (b) use `st_mtime_ns` both sides (T3); (c) docstring must note single-writer assumption; (d) T2 epistemic filter and T1 containment ordering enforced BEFORE skip branch |
| AC13 | APPROVE WITH AMENDMENT | Flag plumbing happens inside existing try-block at cli.py:391 AFTER T1 containment check at 369-388; regression test asserts containment preserved under --no-incremental (T8) |
| AC14 | APPROVE | — |
| AC15 | APPROVE WITH AMENDMENT | Add: (a) `text[:4096]` cap; (b) `re.escape(key)` compile; (c) docstring notes `max()` across matched keys is intentional (T1) |
| AC16 | APPROVE WITH AMENDMENT | Fallback BEFORE int(): `if not math.isfinite(mult) or mult <= 0: mult = 1.0`; return clamp `max(1, min(int(base_days * mult), SOURCE_DECAY_DEFAULT_DAYS * 50))` (T2) |
| AC17 | REJECT | No observable bug; cycle-13 AC2 intentionally uses uncached frontmatter.load. Either drop, or provide concrete failure case |
| AC18 | REJECT (DROP DUPLICATE) | Already shipped in cycle-14 AC23 (utils/pages.py:164) |
| AC19 | REJECT (DROP DUPLICATE) | Already shipped in cycle-14 AC23 (utils/pages.py:163) |
| AC20 | APPROVE WITH AMENDMENT | Track AC1 rewrite |
| AC21 | APPROVE | — |
| AC22 | APPROVE WITH AMENDMENT | Add T7 invalid-frontmatter case (authored_by: human + missing source → no boost) |
| AC23 | APPROVE WITH AMENDMENT | Add multi-source max-decay fixture per AC4 amendment |
| AC24 | APPROVE | — |
| AC25 | APPROVE WITH AMENDMENT | Add T5 cases (action: ingest in code fence outside trail → not flagged; no-trail page → not flagged) |
| AC26 | REJECT | Blocked on AC8 rewrite |
| AC27 | APPROVE WITH AMENDMENT | Add T4 cross-volume fallback assertion for build_graph_jsonld |
| AC28 | APPROVE WITH AMENDMENT | Add T10c retracted-page-freshen test |
| AC29 | APPROVE WITH AMENDMENT | Add T8 containment-preserved case |
| AC30 | APPROVE WITH AMENDMENT | Add T2 NaN/inf/negative-multiplier clamp cases |
| AC31 | REJECT (MOOT) | Drops with AC17 |
| AC32 | APPROVE WITH AMENDMENT | Reframe as cycle-14 contract regression test (production change already shipped) |

**Plus scope gap amendments:**
- Requirements "Docs (Step 12 outputs)" section gains an explicit T10c first-run-no-incremental guidance bullet.

## VERDICT

**APPROVE WITH AMENDMENTS.** 18 amendments, 6 rejects (AC1, AC8, AC17, AC18, AC19, AC26 and AC31 tie-moots; counting AC18/AC19 drops as one duplicate-drop pattern plus AC1+AC8+AC17 rewrites plus AC26+AC31 moots). Effective post-Step-5 scope: 26 ACs (AC2, AC3, AC4, AC5, AC6, AC7, AC9–AC16, AC20–AC25, AC27–AC30, AC32) pending amendments; 3 ACs need rewrite (AC1, AC8, AC17-or-drop); 2 ACs drop-as-duplicate (AC18, AC19); 2 tests moot pending rewrite resolution (AC26, AC31). Step 5 decision gate should resolve the 3 rewrites + 8 threat-model amendments + 1 docs gap.
