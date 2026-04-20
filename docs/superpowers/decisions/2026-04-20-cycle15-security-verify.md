# Cycle 15 — Security Verify (Step 11)

**Date:** 2026-04-20
**Branch:** `feat/backlog-by-file-cycle15`
**Reviewer:** Step-11 security-verify

## Branch Evidence

- `git log --oneline main..HEAD` shows 5 commits, not the expected 6:
  - `20341b9` TASK 5+6 CLI flag + cycle-14 contract regression
  - `205bf2e` TASK 4 publish atomic writes + incremental skip
  - `6c41452` TASK 3 lint decay/status/authored drift
  - `d544365` TASK 2 query decay/tier1/authored boost
  - `00f1380` TASK 1 config volatility/decay topics
- `git diff main..HEAD --stat`: 28 files changed, 3433 insertions, 42 deletions. Source files changed: `src/kb/cli.py`, `src/kb/compile/publish.py`, `src/kb/config.py`, `src/kb/lint/checks.py`, `src/kb/lint/runner.py`, `src/kb/query/engine.py`.
- No dependency manifest files changed in `main..HEAD`.

## Per-Threat Verdicts

### T1 — `volatility_multiplier_for` ReDoS / metachar

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/config.py:407` defines `volatility_multiplier_for`.
- `src/kb/config.py:431` applies `text = text[:4096]`.
- `src/kb/config.py:434` builds the regex with `re.escape(key)`.

### T2 — `decay_days_for` overflow / non-finite multiplier

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/config.py:440` defines `decay_days_for(ref, topics=None)`.
- `src/kb/config.py:474` falls back before `int()` when `not math.isfinite(mult) or mult <= 0`.
- `src/kb/config.py:476` clamps with `min(int(base_days * mult), SOURCE_DECAY_DEFAULT_DAYS * 50)` and floors at `1`.

### T3 — incremental TOCTOU

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/compile/publish.py:35` defines `_publish_skip_if_unchanged`.
- `src/kb/compile/publish.py:40-41` documents nanosecond `st_mtime_ns` comparison.
- `src/kb/compile/publish.py:48-51` documents the single-writer assumption and `--no-incremental` escape hatch.
- `src/kb/compile/publish.py:56-60` compares page and output mtimes using `st_mtime_ns`.

### T4 — JSON-LD cross-volume atomicity

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/compile/publish.py:268` defines `build_graph_jsonld`.
- `src/kb/compile/publish.py:340-344` uses `atomic_text_write(json.dumps(...), out_path)` and documents colocated temp-file atomicity.
- Source-only diff removes the prior direct `json.dump(document, fh, ...)`; no bare `tempfile.mkstemp` was introduced.

### T5 — Evidence Trail false positive

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/lint/checks.py:553` anchors Evidence Trail with `^## Evidence Trail\r?\n`.
- `src/kb/lint/checks.py:554` defines the next-`^## ` terminator.
- `src/kb/lint/checks.py:589-597` slices only the Evidence Trail body span before scanning for `action:\s*ingest`.
- `src/kb/lint/checks.py:591-592` treats missing Evidence Trail as no signal, not a warning.

### T6 — augment cache-clear residual

**Verdict:** IMPLEMENTED.

Evidence:
- AC17 was dropped by design gate, so no new `load_page_frontmatter.cache_clear()` path was introduced for cycle 15.
- `git diff main..HEAD -- src/kb/lint/augment.py` is empty.

### T7 — `_apply_authored_by_boost` validation gate

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/query/engine.py:335` defines `_apply_authored_by_boost`.
- `src/kb/query/engine.py:353-362` reconstructs `_PostLike` metadata.
- `src/kb/query/engine.py:363-365` calls `validate_frontmatter(post)` and returns unchanged on errors before applying the boost.

### T8 — CLI flag bypass of output containment

**Verdict:** IMPLEMENTED.

Evidence:
- `src/kb/cli.py:381-386` normalizes target and rejects `..` before resolving.
- `src/kb/cli.py:388-393` resolves then rejects UNC paths.
- `src/kb/cli.py:396-401` checks `resolved.is_relative_to(PROJECT_ROOT)` or pre-existing directory before side effects.
- `src/kb/cli.py:402` runs `resolved.mkdir(...)` only after the containment checks.
- `src/kb/cli.py:404-412` calls builders with `incremental=incremental` only after validation and mkdir.

### T9 — additive keys leak

**Verdict:** IMPLEMENTED.

Evidence:
- AC18/AC19 were dropped in the design gate as already shipped in cycle 14.
- `src/kb/utils/pages.py:163-164` still emits `belief_state` and `authored_by`.
- `tests/test_cycle15_load_all_pages_fields.py:38-86` machine-checks `authored_by`, `belief_state`, and `status` presence, empty-string defaults, and string types.

### T10 — residual surfaces

**Verdict:** IMPLEMENTED.

Evidence:
- Source-only diff grep for newly introduced `write_text`, `json.dump`, `os.popen`, `subprocess.run`, `eval(`, `exec(`, and `tempfile.mkstemp` found no new risky source usage. The only source hits are removed direct publish writes / removed direct `json.dump` plus the new `json.dumps(...)+atomic_text_write` path.
- `src/kb/compile/publish.py:159-162`, `209-212`, and `290-293` run `_partition_pages(pages)` before the incremental skip in all three builders.
- `src/kb/compile/publish.py:75-83` excludes `belief_state in {retracted, contradicted}` and `confidence == speculative`.

## Class A Dependabot Baseline

Step 2 baseline was 0 open Dependabot alerts. Cycle 15 adds no new third-party dependencies and no dependency manifests changed in `main..HEAD`.

## Class B pip-audit Diff

**Verdict:** PARTIAL process gap.

The requested `/tmp/cycle-15-cve-baseline.json` and `/tmp/cycle-15-cve-branch.json` were not present in this Windows environment. Matching files existed under `%TEMP%`, but `%TEMP%\cycle-15-cve-baseline.json` was 0 bytes while `%TEMP%\cycle-15-cve-branch.json` contained a full pip-audit JSON report, so `git diff --no-index` was non-empty.

Branch audit content shows the known pre-existing `diskcache 5.6.3` / `CVE-2025-69872` finding documented in the threat model. Because no dependency manifests changed, there is no evidence of a branch-introduced dependency CVE, but the saved baseline/branch audit-file diff itself cannot be verified as empty from the available artifacts.

## Cycle-15 Non-Goals

No HIGH concurrency non-goal changes were introduced:
- No `src/kb/compile/compiler.py` manifest race changes.
- No `src/kb/compile/linker.py` / `inject_wikilinks` lock changes.
- No slug-collision algorithm changes.

## Cycle-14 Invariant Preservation

- T1 out-dir containment preserved: `src/kb/cli.py:381-402` keeps traversal/resolve/UNC/containment checks before `mkdir` and builder calls.
- T2 publish epistemic filter preserved: `src/kb/compile/publish.py:75-83` excludes retracted/contradicted/speculative pages, and `src/kb/compile/publish.py:159-162`, `209-212`, `290-293` run partitioning before incremental skip.
- T4 `save_page_frontmatter` `sort_keys=False` contract preserved: `src/kb/utils/pages.py:240-252` remains the wrapper with `frontmatter.dumps(post, sort_keys=False)` and no cycle-15 diff touches it.

## Overall Verdict

**PARTIAL** — implementation threat items T1-T10 are implemented, no dependency manifests changed, and cycle-14 invariants are preserved; gap list: saved Class B pip-audit diff artifact is not empty/comparable because the baseline file is empty, and branch commit count is 5 rather than the expected 6 due TASK 5+6 being combined.
