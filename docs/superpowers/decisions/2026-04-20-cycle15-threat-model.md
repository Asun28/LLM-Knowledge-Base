# Cycle 15 — Threat Model

**Date:** 2026-04-20
**Source:** Opus subagent (Step 2)
**Cycle type:** Backlog-batch wiring of cycle-14 helpers into call sites + small lint/evolve/publish/config features
**Baseline:** Cycle 14 shipped `decay_days_for`, `tier1_budget_for`, publish module, `save_page_frontmatter` wrapper. Cycle 15 moves flat constants to helper calls at call-sites, adds `volatility_multiplier_for`, two new lint checks (AC5/AC6), publish atomic writes (AC9/AC10/AC11), publish incremental short-circuit (AC12), CLI `--incremental/--no-incremental` flag (AC13), augment cache-clear invalidation (AC17), and additive `authored_by`/`belief_state` keys on `load_all_pages` (AC18/AC19). Dependabot 0 open alerts; no new third-party dependencies.

## Analysis

**Trust-boundary crossings this cycle.** Cycle 15 is predominantly a call-site wiring cycle — existing helpers (`decay_days_for`, `tier1_budget_for`, `atomic_text_write`, `save_page_frontmatter`, `load_page_frontmatter`) were audited last cycle, so the primary novel surface area is (a) the new per-topic volatility multiplier (`volatility_multiplier_for` + `decay_days_for(topics=…)` kwarg), (b) the new incremental-publish skip branch that reads output-file mtime and compares against wiki-page mtimes, (c) two new lint checks that regex-scan page bodies for the Evidence Trail section, and (d) the additive `authored_by`/`belief_state` keys leaking into any downstream consumer that does `**page` spread. No new filesystem/network ingress is opened; no new MCP tool surface is added; the CLI gains one Boolean flag (`--incremental/--no-incremental`) but does not take new path or URL input.

**Data flowing through the changed surfaces.** Page frontmatter values (`title`, `tags`, `source`, `authored_by`, `status`, `belief_state`, `updated`), page body text (for Evidence Trail regex scan), wiki-page `stat().st_mtime_ns` (for incremental publish), output-file `stat().st_mtime` (for incremental publish), and user-controlled Click flag values (`--incremental`). All of these are either operator-local (filesystem mtimes) or already-classified-as-attacker-plantable (frontmatter, which crossed the LLM boundary on ingest and was addressed by cycle-14 T9 via the `validate_frontmatter` gate). The one materially new data path is the `topics` string passed to `volatility_multiplier_for`, which in the AC16 default call-site composition is `page.get("tags", "") + " " + page.get("title", "")` — an LLM-extracted-then-operator-unreviewed value that feeds a regex search.

**Novel attack vectors worth modelling.** ReDoS against the volatility regex (T1), integer overflow of the multiplied decay window (T2), TOCTOU race between publish-mtime read and wiki-page write (T3), non-atomic JSON-LD fall-back if the temp+rename pattern isn't colocated (T4), attacker-planted `action: ingest` string outside the Evidence Trail section on a human-authored page triggering the `check_authored_by_drift` false positive (T5), over-aggressive `load_page_frontmatter.cache_clear()` globally invalidating entries for unrelated callers in the same process (T6), the new `_apply_authored_by_boost` applying multiplicatively before the `validate_frontmatter` gate the way `_apply_status_boost` does (T7), CLI flag combination bypassing the cycle-14 T1 `--out-dir` path containment (T8), downstream `**kwargs`/`dict.update` consumers silently inheriting the new additive frontmatter keys into models that don't expect them (T9), and any residual injection / path-traversal / secret-handling surface from the Tn analysis above (T10).

**Existing invariants that must be preserved.**
1. Cycle-14 T1 — `kb publish --out-dir` containment check (resolve + `is_relative_to(PROJECT_ROOT)` OR pre-existing dir); AC13's new `--incremental` flag must not reorder the branches around it.
2. Cycle-14 T2 — publish epistemic filter (`belief_state in {retracted, contradicted}` OR `confidence == speculative`) applied inside each builder BEFORE any skip-if-unchanged early return.
3. Cycle-14 T3 — JSON-LD `json.dump` contract; AC11 temp+rename must not replace `json.dump` with f-string assembly.
4. Cycle-14 T4 — `save_page_frontmatter` atomic + `sort_keys=False` contract; cycle-15 introduces no new write-back sites.
5. Cycle-14 T6 — `decay_days_for` hostname match via `urlparse(ref).hostname`; AC16 `topics=…` kwarg must not regress the URL-parse path when `topics is None`.
6. Cycle-14 T9 — `_apply_status_boost` `validate_frontmatter` gate; AC3's `_apply_authored_by_boost` MUST be gated identically.

## Threat items

### T1: `volatility_multiplier_for` regex ReDoS / unbounded input

- **Surface:** `src/kb/config.py::volatility_multiplier_for` (AC15).
- **Vector:** AC15 specifies `re.search(r"\b<key>\b", text, re.IGNORECASE)` over each key in `SOURCE_VOLATILITY_TOPICS`. The keys themselves are developer-controlled literals (`"llm"`, `"react"`, `"docker"`, `"claude"`, `"agent"`, `"mcp"`) — no regex metacharacters. But `text` is attacker-plantable via frontmatter `tags` / `title`. Two risks: (a) pathological input length (`tags: "llm " * 10_000_000`) pushes the 6 × `re.search` calls into multi-second wall time; (b) if a future contributor adds a key with regex metacharacters (e.g. `"c++"`), the naked `\b<key>\b` interpolation becomes a format-string injection.
- **Impact:** query-path CPU exhaustion on any single page with a pathological `tags` field; downstream `decay_days_for` stall; single-process DoS.
- **Mitigation:** (a) hard-cap `text` length inside the helper (`text[:4096]` is sufficient — no legitimate tags+title is larger); (b) compile keys with `re.escape(key)` so future metachar keys cannot corrupt the pattern; (c) because `\b` is a zero-width anchor and the alternation-free pattern has no backreference or nested quantifier, classic exponential ReDoS is not reachable — the primary mitigation is the length cap.
- **Status:** `verify-at-step11` — `tests/test_cycle15_config_volatility.py` asserts `volatility_multiplier_for("a" * 10_000_000)` returns in under 200 ms AND returns `1.0`; grep `config.py::volatility_multiplier_for` for `re.escape(` around the key interpolation AND for a length guard (`text[:N]` or `len(text) >` check).

### T2: AC16 `decay_days_for(topics=…)` integer overflow / negative multiplier

- **Surface:** `src/kb/config.py::decay_days_for` (cycle-14 helper, cycle-15 gains `topics` kwarg in AC16).
- **Vector:** `int(base_days * volatility_multiplier_for(topics))` — if `SOURCE_VOLATILITY_TOPICS` someday contains a hostile multiplier (negative, zero, `float("inf")`, or `nan`) the returned decay days become nonsense: negative decays flag every page as fresh, zero decays flag every page as stale, `nan` coerces to a Python negative int via `int()` OverflowError or returns a platform-dependent value. Attacker surface is thin (requires a PR that edits the config dict), but T2 defends against accidental-typo regressions too.
- **Impact:** staleness gate defeated (every page either always fresh or always stale) OR `int(nan)` raises ValueError and every caller along the staleness pipeline crashes.
- **Mitigation:** clamp the result: `return max(1, min(base_days * multiplier, SOURCE_DECAY_DEFAULT_DAYS * 50))` — 50× the default ceiling (~12 years) is a generous but finite upper bound; a floor of 1 day prevents zero/negative. `volatility_multiplier_for` returns type-`float` by contract; reject non-finite multipliers at helper boundary (`math.isfinite(mult)` or `1.0` fallback).
- **Status:** `verify-at-step11` — `tests/test_cycle15_config_volatility.py::test_decay_days_for_topics_clamp` asserts result is in `[1, SOURCE_DECAY_DEFAULT_DAYS * 50]` for every multiplier in `SOURCE_VOLATILITY_TOPICS`; additional negative/NaN/inf fixture drops multiplier to `1.0` and returns base days unchanged.

### T3: AC12 incremental-publish mtime TOCTOU race

- **Surface:** `src/kb/compile/publish.py::_publish_skip_if_unchanged` helper (AC12); `build_llms_txt` / `build_llms_full_txt` / `build_graph_jsonld` skip branch when `incremental=True`.
- **Vector:** Between the `out_path.stat().st_mtime` read and the skip-return, another process (`kb ingest` in a separate shell, or the MCP server under concurrent load) writes a new wiki page. The skip branch returns the stale output path without regenerating, and the caller reports `wrote …/llms.txt` — but the wiki content is now newer than the on-disk output. This is a consistency bug, not a security bug at single-user scale, but cycle-15 non-goals explicitly list concurrency as deferred so the acceptable mitigation is documentation + single-writer assumption.
- **Impact:** downstream LLM crawler reads stale `llms.txt` until next `--no-incremental` run; belief_state: retracted content published at N-1 may survive into N's read because the skip was computed from N-1's output mtime.
- **Mitigation:** (a) compute `max(page.stat().st_mtime_ns for page in iter)` THEN compare against `out_path.stat().st_mtime_ns`, so the comparison is nanosecond-granular and uses the same clock source; (b) document in `_publish_skip_if_unchanged` docstring that single-writer is assumed; (c) provide `--no-incremental` escape hatch for operators who suspect drift (AC13 hard-override); (d) the skip branch MUST NOT early-return before the AC9/AC10/AC11 atomic-write ordering — skip returns the existing `out_path`, full writes go through `atomic_text_write` / `os.replace`.
- **Status:** `verify-at-step11` — `tests/test_cycle15_publish_incremental.py` asserts: (a) mtime-freshening ANY wiki page between calls re-triggers write; (b) docstring contains "single-writer" assumption note; (c) `incremental=False` bypasses the mtime check entirely and regenerates.

### T4: AC11 `build_graph_jsonld` temp+rename atomicity on Windows/network mounts

- **Surface:** `src/kb/compile/publish.py::build_graph_jsonld` (AC11 replaces `json.dump` direct-to-path with temp-file + `os.replace` pattern).
- **Vector:** `os.replace` is atomic ONLY when source and destination are on the same filesystem. If AC11's implementation uses `tempfile.mkstemp()` without a `dir=` argument, the temp file lands in the system temp dir (often a different volume from the output path on Windows — C: vs D: — or across a OneDrive mount boundary), and `os.replace` falls back to copy+delete, losing atomicity. A crash between the copy and delete leaves the destination corrupt. This same pattern is why `atomic_text_write` in `kb.utils.io` already uses `tempfile.mkstemp(dir=path.parent, …)` (confirmed via grep).
- **Impact:** partial-write corruption of `graph.jsonld` on SIGINT / AV-hold / power-loss across drive boundaries; broken JSON breaks every downstream consumer silently.
- **Mitigation:** reuse the existing `atomic_text_write` pattern — the implementation should `json.dumps` the document first, then call `atomic_text_write(json_str + "\n", out_path)`. This colocates the temp file with the destination AND reuses the audited cleanup path. If AC11 prefers a hand-rolled pattern, it MUST pass `dir=out_path.parent` to `tempfile.mkstemp` and wrap the mkstemp→dump→replace in try/except with temp-file cleanup on failure.
- **Status:** `verify-at-step11` — grep `build_graph_jsonld` must show either `atomic_text_write(` OR both `tempfile.mkstemp(dir=out_path.parent` AND `os.replace(`; grep must NOT show bare `tempfile.mkstemp()` without `dir=`. `tests/test_cycle15_publish_atomic.py` asserts no `.tmp` sibling remains after a simulated `os.replace` raise.

### T5: AC6 `check_authored_by_drift` regex false positive on adversarial body

- **Surface:** `src/kb/lint/checks.py::check_authored_by_drift` (AC6).
- **Vector:** AC6 specifies regex match (not YAML parse) for `action: ingest` inside the Evidence Trail section. A naive implementation that scans the FULL body with `re.search(r"action:\s*ingest", body)` fires on any page that mentions the literal string outside the Evidence Trail — e.g. a concept page explaining the ingest pipeline, a review comment quoting `action: ingest`, a code fence documenting the evidence-trail schema. Plus: cycle-14 evidence-trail discipline already warns "sentinel-less pages defeat append-ordering", so an attacker who strips the `## Evidence Trail` header also strips the legitimate signal.
- **Impact:** noisy false positives on legitimate human-authored pages that discuss ingestion (meta-documentation, research notes); possible missed positives if the sentinel is removed.
- **Mitigation:** restrict regex scope to the span BETWEEN the `## Evidence Trail` header and the next `##`-level header (or EOF). Existing `src/kb/ingest/evidence.py` already uses `re.search(r"^## Evidence Trail\r?\n", content, re.MULTILINE)` to locate the section start — reuse the same anchor. For the scope end, use `re.search(r"\n## ", content[start:])` or body-end. Ingest-style `action: ingest` markers before the Evidence Trail section MUST NOT be considered.
- **Status:** `verify-at-step11` — `tests/test_cycle15_lint_authored_drift.py::test_action_ingest_outside_trail_not_flagged` seeds a human page whose body text mentions `action: ingest` in a code fence ABOVE the Evidence Trail section and asserts no warning is emitted. Second assertion: page without any Evidence Trail section is NOT flagged (absence of signal is not a drift event).

### T6: AC17 `load_page_frontmatter.cache_clear()` over-aggressive invalidation

- **Surface:** `src/kb/lint/augment.py::_post_ingest_quality` (AC17).
- **Vector:** AC17 replaces direct `frontmatter.load(str(page_path))` with `load_page_frontmatter(page_path)` preceded by `load_page_frontmatter.cache_clear()`. The cache is process-global (8192-entry LRU keyed on `(path_str, mtime_ns)`), so clearing it wipes entries for EVERY page in the process — not just the augmented one. Same-process lint callers (`check_staleness`, `check_stub_pages`, `check_front_matter_ids`) pay the slow-path re-read cost for every subsequent call within the same `run_augment` invocation. This is a performance degradation, not a correctness bug, but on a 5000-page wiki the slow-path fallback is ~5× slower.
- **Impact:** augment runs slow down linearly with wiki size after the first augmented page; no correctness or security impact.
- **Mitigation:** prefer targeted invalidation — the helper already keys on `(str(page_path), mtime_ns)`, so mtime_ns advancing on write naturally bypasses the stale entry on the NEXT read without clearing. Only call `cache_clear()` if the FAT32/OneDrive/SMB coarse-mtime edge case fires (mtime does not advance). Alternatively: document the choice explicitly in the AC17 code comment + a unit test that proves the slow-path fallback cost is acceptable. The cycle-13 comment at line 1128-1133 already captures the filesystem-coarseness rationale — preserve it and add a "cache_clear() is process-wide; acceptable cost" note.
- **Status:** `verify-at-step11` — grep `_post_ingest_quality` for `cache_clear()` MUST appear adjacent to a comment explaining the process-wide-clear decision; `tests/test_cycle15_augment_cache_clear.py::test_cache_clear_scope_documented` asserts the code comment mentions "process-wide" OR "all callers" OR equivalent. Functional test: same-process `check_staleness` call AFTER `_post_ingest_quality` succeeds without raising (no KeyError on evicted key).

### T7: AC3 `_apply_authored_by_boost` must be gated on `validate_frontmatter`

- **Surface:** `src/kb/query/engine.py::_apply_authored_by_boost` helper (AC3) applied after `_apply_status_boost` in the score pipeline.
- **Vector:** AC3 says "ungated on `validate_frontmatter` pass (same as `_apply_status_boost`)" — i.e. the boost SHOULD be gated the same way. If the implementer forgets the gate, attacker-controlled frontmatter with `authored_by: human` (but otherwise invalid — missing `source`, wrong date format, unknown `type`) receives a +2% ranking boost. Combined with the cycle-14 T9 `status: mature` 5% boost (already gated), an attacker could stack two boosts on poisoned pages for a 7%+ ranking lift.
- **Impact:** ranking manipulation via one frontmatter line on invalid-otherwise pages; pollutes query-synthesis context.
- **Mitigation:** implement `_apply_authored_by_boost` as a literal copy of `_apply_status_boost` structure — reconstruct `_PostLike` with `metadata` dict, call `validate_frontmatter(post)`, return `page` unchanged if errors list is non-empty. Pipeline order should be: `_apply_status_boost` → `_apply_authored_by_boost` → `dedup_results`, so both boosts share the SAME validate call (or each call it independently — cost is negligible).
- **Status:** `verify-at-step11` — grep `_apply_authored_by_boost` for `validate_frontmatter(` (required); `tests/test_cycle15_authored_by_boost.py::test_invalid_frontmatter_no_boost` seeds a page with `authored_by: human` + missing `source` field (triggers validate error) and asserts no score multiplication. Second assertion: page with `authored_by: robot` (not in `AUTHORED_BY_VALUES`) returns unchanged score.

### T8: AC13 CLI `--no-incremental` flag combination bypassing T1 path containment

- **Surface:** `src/kb/cli.py::publish` subcommand (AC13 adds `--incremental/--no-incremental` flag).
- **Vector:** Cycle-14 T1 mitigation places the `--out-dir` containment check (resolve + is_relative_to(PROJECT_ROOT) OR pre-existing dir) BEFORE the build-function calls. AC13 adds a new Click option; a naive implementation could intersperse flag handling with path validation, or pass `incremental=flag` to the builders BEFORE the `UsageError` raise. If the refactor moves the `resolved.mkdir(parents=True, exist_ok=True)` call before the containment check, `--out-dir=/etc --no-incremental` still creates `/etc` as a side effect even when the UsageError fires a moment later. Less dramatic but relevant: forcing `incremental=False` on a non-existent-yet-created-by-us directory could interact with a race between `mkdir` and the `is_relative_to` check.
- **Impact:** arbitrary directory creation outside PROJECT_ROOT if the cycle-14 T1 ordering is regressed; otherwise a no-op.
- **Mitigation:** AC13 implementation MUST preserve the existing source-order: (1) normalize `out_dir`, (2) validate `..` parts, (3) resolve, (4) reject UNC, (5) check `is_relative_to(PROJECT_ROOT) or resolved.is_dir()` — THEN (6) `resolved.mkdir(…)`, THEN (7) call builders with `incremental=flag`. The flag is a pure Boolean plumbed into builder kwargs; it cannot affect path validation. Add a regression test for the cycle-14 T1 path + the new flag.
- **Status:** `verify-at-step11` — `tests/test_cycle15_cli_incremental.py::test_out_dir_containment_preserved` runs `kb publish --out-dir /etc --no-incremental` via CliRunner and asserts `UsageError` is raised AND `/etc` was not created (or, since we can't guarantee /etc doesn't exist, uses a tmp_path sibling outside PROJECT_ROOT). Grep `cli.py::publish` shows the containment check block unchanged in source order relative to `mkdir`.

### T9: AC18/AC19 additive `authored_by`/`belief_state` keys leaking into `**kwargs` consumers

- **Surface:** `src/kb/utils/pages.py::load_all_pages` (AC18 adds `authored_by`; AC19 adds `belief_state`).
- **Vector:** Cycle-14 AC23 already added the `status` key as additive; cycle-15 repeats the pattern for the remaining two vocabulary fields. Risk: any downstream caller that does `frontmatter.Post(**page)` or `SomeModel(**page)` or `existing_dict.update(page)` now receives the extra keys. If the target schema uses strict validation (pydantic, dataclass with `extra="forbid"`, or SQL ORM with fixed columns), the injection raises; if lax, the keys silently propagate into places they shouldn't (e.g. a serializer that emits frontmatter back — mixing the new fields into pages that never had them on disk).
- **Impact:** runtime `TypeError`/`ValidationError` on strict consumers; silent frontmatter pollution on lax consumers; test fixtures that `assert page.keys() == {…fixed set…}` break.
- **Mitigation:** (a) document the additive contract in the `load_all_pages` docstring and the AC18/AC19 comments in source — mirror the existing cycle-14 AC23 comment block (confirmed at lines 157-165 of `pages.py`); (b) grep existing callers for `**kwargs`-style spreads on `load_all_pages` output before shipping — the relevant call-sites are `query.engine`, `lint.checks`, `lint.augment`, `compile.publish`, `evolve.analyzer`, `mcp.browse`; (c) the empty-string-when-absent default ensures membership/truthiness checks continue to work (`if page["authored_by"] == "human":` is safe, `if page.get("authored_by"):` is safe).
- **Status:** `verify-at-step11` — `tests/test_cycle15_load_all_pages_fields.py` asserts every returned dict contains both keys (empty string when frontmatter absent, matching value when present); grep-based audit commit-message entry listing every `**page` / `dict(page, …)` spread in the codebase and confirming no strict-schema consumer; keys remain namespaced under frontmatter vocabulary so no collision with existing page dict keys (`id`, `path`, `title`, `type`, `confidence`, `sources`, `created`, `updated`, `content`, `content_lower`).

### T10: Residual surfaces — augment write-back, publish filter, config fallthrough

- **Surface:** Multiple — scan of the full diff for path-traversal / injection / secret-handling surfaces not covered by T1–T9.
  - **T10a** (closed-via-design) — no new filesystem path input. AC13's CLI flag takes a Boolean; AC16's `topics` kwarg is a plain string used only for regex match; AC17 reuses `page_path` from an already-validated augment flow; AC12 reads `out_path` from the cycle-14-T1-validated CLI branch.
  - **T10b** (closed-via-design) — no new secrets-adjacent surface. `volatility_multiplier_for` returns a float; `check_authored_by_drift` emits a `pid` string; incremental-publish emits an mtime. Nothing logs or echoes user-supplied content verbatim.
  - **T10c** (verify-at-step11) — publish epistemic filter (cycle-14 T2) MUST run BEFORE the AC12 skip-if-unchanged check. If the skip branch short-circuits on an output that was written BEFORE cycle-14 T2 was shipped, the stale output carries retracted/contradicted content and the skip never regenerates it. Mitigation: the skip branch computes BOTH the newest-wiki-mtime AND the output-mtime; an output file written before cycle-14-ship-date (detectable via a file header marker OR operator-driven `--no-incremental` run at cycle-14 upgrade time) is treated as dirty. Practical mitigation: document that the first post-cycle-14 publish run should be `--no-incremental`.
  - **T10d** (closed-via-design) — no new prompt-injection surface. Cycle-15 does not add to `call_llm`/`call_llm_json` call sites; the new lint checks are pure-Python regex + YAML-via-load_page_frontmatter.
- **Status:** T10a/T10b/T10d `closed-via-design`. T10c `verify-at-step11` — `tests/test_cycle15_publish_incremental.py::test_epistemic_filter_survives_incremental` seeds an output that was generated BEFORE a `belief_state: retracted` page was tagged; re-running with `incremental=True` after the retraction MUST regenerate (because the page mtime advanced on frontmatter edit), proving the mtime-based skip correctly invalidates on frontmatter change alone.

## AC amendments required (for Step 5 decision gate)

- **AC15** — add implementation detail: `re.escape(key)` around each substring key, and a length cap on `text` (suggest `text[:4096]`) before the regex loop (T1).
- **AC16** — document the return clamp: `max(1, min(base_days * mult, SOURCE_DECAY_DEFAULT_DAYS * 50))` and `math.isfinite(mult) or 1.0` fallback (T2).
- **AC11** — either reuse `atomic_text_write` (preferred) OR explicitly require `tempfile.mkstemp(dir=out_path.parent, …)` for the temp file placement (T4).
- **AC6** — scope the regex to the span between `## Evidence Trail` and the next `##`-level header / EOF; reuse the anchor from `kb.ingest.evidence` (T5).
- **AC17** — add a code comment justifying the process-wide `cache_clear()` decision and confirming the slow-path cost is acceptable (T6).
- **AC3** — make the `validate_frontmatter` gate explicit in the AC text (not just "same as `_apply_status_boost`"); this is the T9-class mitigation (T7).
- **AC12** — docstring must contain a "single-writer assumed" note and the comparison must use `st_mtime_ns` on both sides (T3).
- **Add to Step 12 docs** — recommend `kb publish --no-incremental` as the first post-cycle-15-upgrade invocation so any pre-cycle-14 outputs are regenerated under the current epistemic filter (T10c).

## Summary table

| # | Threat | Severity | Status | Verification anchor |
|---|---|---|---|---|
| T1 | `volatility_multiplier_for` ReDoS / metachar injection | Medium | verify-at-step11 | `test_cycle15_config_volatility.py`: `volatility_multiplier_for("a"*10M) < 200ms == 1.0`; grep for `re.escape` + length cap |
| T2 | `decay_days_for(topics=…)` overflow / non-finite multiplier | Medium | verify-at-step11 | `test_decay_days_for_topics_clamp`: result in `[1, SOURCE_DECAY_DEFAULT_DAYS*50]`; NaN/inf → fallback |
| T3 | AC12 incremental-publish mtime TOCTOU | Low (single-writer) | verify-at-step11 | `test_cycle15_publish_incremental.py`: mtime-freshen re-triggers write; docstring has "single-writer" note |
| T4 | AC11 JSON-LD temp+rename cross-volume | Medium | verify-at-step11 | Grep: `atomic_text_write(` OR `tempfile.mkstemp(dir=out_path.parent`; no bare `mkstemp()` |
| T5 | AC6 `check_authored_by_drift` body-wide false positive | Medium | verify-at-step11 | `test_action_ingest_outside_trail_not_flagged`; no-trail page not flagged |
| T6 | AC17 process-wide `cache_clear()` over-invalidation | Low (perf) | verify-at-step11 | Grep: `cache_clear()` adjacent to explaining comment |
| T7 | AC3 `_apply_authored_by_boost` missing validate gate | High | verify-at-step11 | Grep `_apply_authored_by_boost` for `validate_frontmatter(`; invalid-frontmatter test |
| T8 | AC13 flag bypassing cycle-14 T1 path containment | High | verify-at-step11 | `test_out_dir_containment_preserved`: `kb publish --out-dir /tmp/outside --no-incremental` → `UsageError` |
| T9 | AC18/AC19 additive keys leaking into `**kwargs` consumers | Low | verify-at-step11 | `test_cycle15_load_all_pages_fields`; grep audit of `**page` spreads |
| T10a | No new path/URL input surface | — | closed-via-design | No new surface — all paths flow through cycle-14 validation |
| T10b | No new secret-handling surface | — | closed-via-design | `volatility_multiplier_for` returns float; no content echo |
| T10c | AC12 skip of pre-filter outputs | Medium | verify-at-step11 | `test_epistemic_filter_survives_incremental`: retracted page re-publish |
| T10d | No new prompt-injection surface | — | closed-via-design | No new LLM call sites |

## Baseline summary

- **Dependabot:** 0 open alerts (carried from cycle-14 baseline; no new third-party dependencies added this cycle).
- **pip-audit:** 1 vuln (diskcache 5.6.3 CVE-2025-69872, no fix available, pre-existing BACKLOG MEDIUM informational — out of scope).
- Cycle 15 adds no new third-party dependencies → Class B PR-introduced CVE diff expected empty at Step 11.
- Cycle 15 adds no new MCP tools, no new CLI subcommands (only a flag on existing `kb publish`), and no new file-writing surface outside the existing `outputs/` directory and `wiki/` pages.
