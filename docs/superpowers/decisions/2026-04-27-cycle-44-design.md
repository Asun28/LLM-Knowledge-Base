# Cycle 44 Design Decision Gate

**Date:** 2026-04-27
**Branch:** cycle-44-batch
**Inputs:** requirements.md (30 ACs) · threat-model.md (T1-T9) · brainstorm.md (10 Qs) · r1-deepseek-design.txt (PROCEED-WITH-AMENDS) · r2-codex-design-eval.md (PROCEED-WITH-AMENDS, 13 amendments)

## VERDICT
**PROCEED-WITH-AMENDS**

R1 + R2 both converge on PROCEED-WITH-AMENDS. R2's deeper grep enumeration surfaces material patch-site drift that R1 missed (~24 `call_llm_json` patches across 3 files; `kb_compile_scan`/`kb_ingest_content` reference-form patches in `test_cycle32_cli_parity_and_fair_queue.py`; `Manifest`/`RateLimiter` import sites in `test_backlog_by_file_cycle1.py` and `test_v5_lint_augment_*`). The amendments are all reversible / scoped to additional re-export shims and targeted patch migrations — no AC must be dropped, but **the cycle must be split** to keep blast radius safe (Q14 option c).

---

## DECISIONS (Q1-Q14)

### Q1 — AC8 patch-target preservation (`kb.lint.checks.WIKI_DIR`)

**OPTIONS:**
(a) Module-level `WIKI_DIR` constant in package `__init__.py`; submodules read via `from kb.lint import checks; checks.WIKI_DIR` (lazy lookup via package binding).
(b) Migrate `tests/test_cli.py:88-89` to patch the canonical submodule (e.g. `kb.lint.checks.frontmatter.WIKI_DIR`).
(c) Keep `WIKI_DIR` only in `__init__.py` and submodules read from `kb.config.WIKI_DIR` directly — patch becomes ineffective for submodule globals (REJECT).

#### ## Analysis

The test at `tests/test_cli.py:88-89` is `patch("kb.lint.checks.WIKI_DIR", wiki_dir)`. Today, `src/kb/lint/checks.py:18,23` does `from kb.config import RAW_DIR, WIKI_DIR`, which binds those names as module-level attributes. The patch works because monkeypatch mutates `kb.lint.checks.__dict__["WIKI_DIR"]` and the rule functions in the same module read `WIKI_DIR` via their module globals — same dict. After the package split, if every submodule does `from kb.config import WIKI_DIR`, then the package-level `kb.lint.checks.WIKI_DIR` and the submodule-level `kb.lint.checks.frontmatter.WIKI_DIR` point at the same value but are *different bindings*. Patching the package-level name does not propagate to the submodule's globals — exactly the C42-L3 hazard (re-exports do not make patches transparent).

R2's amendment is principled: the test must keep working **without** modification (AC8 is explicit). Option (a) achieves this by making submodules read `WIKI_DIR` through the package object — `from kb.lint import checks; ...; effective_dir = checks.WIKI_DIR`. When monkeypatch flips `kb.lint.checks.WIKI_DIR`, the submodule's call-time lookup sees the mutated value because it goes through the package's `__dict__`. Option (b) violates the AC8 "without modification" requirement and would force migrating `test_cli.py` (an in-scope file). Option (c) is rejected by the prompt itself. Option (a) is also consistent with cycle-19 L2's lazy-accessor pattern (read at call time, not at import time) and with cycle-18 L1's snapshot-bind hazard (`from X import Y` captures Y's identity at import time, but mutable container attribute reads don't).

**DECIDE:** **(a)** — package-level `WIKI_DIR` / `RAW_DIR` re-export + submodules read via `checks.WIKI_DIR` indirection (or `from kb.lint import checks` then `checks.WIKI_DIR` at call-time).

**RATIONALE:** Preserves `tests/test_cli.py` unchanged (AC8 invariant). Option (b) would force a test edit that AC8 forbids. Option (c) is the explicit anti-pattern called out by both R1 and R2. R2's regression-test addition (Step 9 must assert `patch("kb.lint.checks.WIKI_DIR", X)` actually changes the directory `check_source_coverage` reads) is a load-bearing CONDITION (cycle-22 L5).

**CONFIDENCE:** HIGH — explicit AC + R1+R2 both agree + grounded in three documented learnings (C42-L3, cycle-18 L1, cycle-19 L2).

---

### Q2 — AC11 private-module compatibility shims (`_augment_manifest.py`, `_augment_rate.py`)

**OPTIONS:**
(a) Keep `_augment_manifest.py` and `_augment_rate.py` as compatibility shims re-exporting from `kb.lint.augment.manifest` and `kb.lint.augment.rate`.
(b) Migrate ALL ~25 test patch sites to the new package paths in cycle 44.
(c) Defer M2 to cycle 45 (DROP from this cycle).

#### ## Analysis

R2's enumeration is exhaustive: `Manifest` is imported at `tests/test_backlog_by_file_cycle1.py:157`, `tests/test_cycle17_resume.py:19`, `tests/test_v5_lint_augment_manifest.py:9,63,88`. `RateLimiter` is imported at `tests/test_backlog_by_file_cycle1.py:166`, `tests/test_v5_lint_augment_rate.py:9,73,90`. `MANIFEST_DIR` and `RATE_PATH` constants are referenced in 14+ patch sites across `test_v5_lint_augment_orchestrator.py`. AC16 explicitly requires `tests/test_backlog_by_file_cycle1.py` and `tests/test_cycle9_lint_augment.py` "pass without modification" — but those files import from the private modules. Option (b) violates AC16, requires touching 25+ patch sites in a single cycle (blast-radius spike per cycle-22 L4 conservative posture), and risks late-cycle test-migration churn that historically eats Step 9 budget.

Option (a) is the BACKLOG-suggested idiom: a 5-line shim file (`from kb.lint.augment.manifest import *  # noqa: F401, F403` or explicit re-exports with `# noqa: F401  # re-exported for backward compat (cycle-23 L5)` per C42-L5) preserves all test imports unchanged AND lets the new canonical package own the implementation. The shim files are deletable in cycle 45 once tests migrate — that's a clean two-cycle path. Option (c) loses the M2 close-out and pushes Phase 4.6 into cycle 45 unnecessarily; the package conversion itself is straightforward and the shim cost is minimal. Per CLAUDE.md "Goal-Driven Execution" + "Two tests before declaring done", option (a) keeps the change minimal and reversible.

**DECIDE:** **(a)** — keep `_augment_manifest.py` and `_augment_rate.py` as compatibility shims that re-export from `kb.lint.augment.manifest` / `kb.lint.augment.rate` with explicit `# noqa: F401  # re-exported for backward compat (cycle-23 L5)` comments per C42-L5.

**RATIONALE:** Satisfies AC11 (the new package files exist with full content) AND AC16 (tests pass unchanged) without forcing 25+ patch-site migrations into cycle 44. The shims are tagged for cycle-45 deletion as part of the AC11 follow-up work. Option (b) violates AC16. Option (c) drops Phase 4.6 close progress.

**CONFIDENCE:** HIGH — R2's exhaustive enumeration provides the evidence base; AC16 wording locks the choice.

---

### Q3 — AC14 scope: `call_llm_json` patch sites

**OPTIONS:**
(a) Migrate ALL ~24 sites to new canonical submodule (whichever submodule of `augment/` owns the call).
(b) Migrate only the 2 named files in original AC14 + leave others patched against `kb.lint.augment.call_llm_json` re-export with documentation note.
(c) Widen AC14 to require ALL sites migrated (matches R2 amendment).

#### ## Analysis

`call_llm_json` is imported into `augment.py` from `kb.utils.llm_util` (or similar) and used as `call_llm_json(...)`. Today, patches against `kb.lint.augment.call_llm_json` work because the name is bound in the augment module's namespace. After the split, if `proposer.py` does `from kb.utils.llm_util import call_llm_json` and uses it locally, the canonical patch target becomes `kb.lint.augment.proposer.call_llm_json`. If we leave the package `__init__.py` re-exporting `call_llm_json` for backward compat, an old `patch("kb.lint.augment.call_llm_json")` will mutate the package's binding but **not** the proposer submodule's binding (C42-L3 again).

R2 found 22 sites: `test_cycle13_frontmatter_migration.py:531,551,643,663` (4); `test_cycle9_lint_augment.py:70` (1); `test_v5_lint_augment_orchestrator.py:16,167,190,213,251,286,297,326,353,372,434,495,548,734,790,907,946` (17). Option (b) leaves 22 patches patching the wrong target — every test in `test_v5_lint_augment_orchestrator.py` would see the un-mocked `call_llm_json` and either fail (if the real function makes a network call) or silently behave wrong. The "documentation note" alternative is the cycle-19 L1 antipattern: documented hazards still bite. Option (a)/(c) (they're the same effect — migrate all) prevents that. Cost is 22 mechanical string edits, all `s/kb.lint.augment.call_llm_json/kb.lint.augment.proposer.call_llm_json/g` once we pin proposer as the owner. Tracker: this is a Step 7 plan task with grep + sed-style verification, not a Step 9 cleanup.

**DECIDE:** **(c)** — widen AC14 to require ALL `call_llm_json` patch sites migrated to the canonical owner submodule (which is `kb.lint.augment.proposer` per Q4 below).

**RATIONALE:** C42-L3 is unambiguous: re-exports do not make patches transparent. R2's enumeration shows the silent-fail scope. The migration is mechanical — 22 line edits with one canonical target. Option (b) is the documented hazard.

**CONFIDENCE:** HIGH — C42-L3 + cycle-19 L1 both apply; R2 evidence is exhaustive.

---

### Q4 — AC15: `run_augment` canonical owner module

**OPTIONS:**
(a) Create `orchestrator.py` containing `run_augment` (R2's choice).
(b) `run_augment` lives in `__init__.py` (no submodule).
(c) `run_augment` lives in `quality.py` (closest functional match per brainstorm).
(d) `run_augment` lives in `proposer.py` (it kicks off proposer phase).

#### ## Analysis

`run_augment` at `src/kb/lint/augment.py:530` is the top-level orchestration entry point — it calls collector, proposer, fetcher, persister, and quality phases in sequence. Forcing it into one of those phase-named modules would create a circular-import-shaped problem: `quality.py` would import `collector.py`, `proposer.py`, etc., conflating "I am the quality phase" with "I orchestrate all phases". Option (b) — putting it in `__init__.py` — is technically possible but pollutes the package init with 200+ LOC of orchestration logic, defeating the M2 split's "small focused submodules" goal. Option (c) is conceptually wrong: the "quality" phase is a single phase among many, not the orchestrator.

`orchestrator.py` is the standard naming for "drives multiple subsystems" — it's the same pattern used by `kb.lint.runner` (which orchestrates `checks/`). R2's amendment to AC15 makes the patch target `kb.lint.augment.orchestrator.run_augment`, which is descriptive and stable. The new package layout becomes 9 files: `__init__.py`, `collector.py`, `proposer.py`, `fetcher.py`, `persister.py`, `quality.py`, `manifest.py`, `rate.py`, `orchestrator.py` — this is what AC11 must be amended to require.

**DECIDE:** **(a)** — create `orchestrator.py` containing `run_augment` and any cross-phase glue (resume bookkeeping, top-level error handling). AC11 must be amended to require 9 files (add `orchestrator.py`).

**RATIONALE:** Matches R2's amendment + brainstorm's open question 8 + the existing `kb.lint.runner` precedent. Option (b) bloats `__init__.py`. Options (c)/(d) are categorically wrong. AC15's patch target becomes `kb.lint.augment.orchestrator.run_augment`.

**CONFIDENCE:** HIGH — naming follows project precedent; R2 explicitly named it.

---

### Q5 — AC16 compat shims

Linked to Q2 — same decision applies. **DECIDE:** **(a) shims kept**, see Q2.

**CONFIDENCE:** HIGH (tied to Q2).

---

### Q6 — AC19: MCP tool registration after M3 split

**OPTIONS:**
(a) Update `_register_all_tools()` to import 6 modules (`browse, core, ingest, compile, health, quality`) — matches existing pattern.
(b) Move `mcp` instance to `kb/mcp/app.py` only; `ingest`/`compile`/`core` all import from there (more standard FastMCP pattern, but bigger churn).
(c) Defer M3 to cycle 45 (DROP from this cycle).

#### ## Analysis

Today, `src/kb/mcp/__init__.py:37` does `from kb.mcp import browse, core, health, quality`. The `mcp` FastMCP instance lives in `kb.mcp.app:mcp` (already separated per cycle 23). Each of `browse.py`, `core.py`, `health.py`, `quality.py` does `from kb.mcp.app import mcp` and registers tools with `@mcp.tool()`. Option (a) just adds two more module imports — `ingest` and `compile` — to the same `_register_all_tools()` function. This is exactly the cycle-4-13 + cycle-23 pattern continuing forward. It is the lowest-risk option and what R2 explicitly amends AC19 toward.

Option (b) is technically the standard FastMCP pattern but `kb.mcp.app` already serves that role — `mcp` is created in `app.py` and every tool module imports it from there. Cycle 23 already did the heavy lift. Option (c) drops M3, which is one of the four headline items; we have a way to ship it safely (Q8/Q13 lazy-lookup + targeted test migration). T4 (threat model) requires `len(mcp._tool_manager._tools) == 29` post-split — this is verifiable in Step 9 with one test.

**DECIDE:** **(a)** — extend `_register_all_tools()` to import 6 modules: `browse, core, ingest, compile, health, quality`. Add a Step 9 test asserting `len(mcp._tool_manager._tools) == 29` after `from kb.mcp import mcp` (T4 invariant).

**RATIONALE:** Continues the cycle-4-13 + cycle-23 split pattern. Lowest churn. The 29-tool count test pins the contract. Option (b) is unnecessary churn given `app.py` already exists.

**CONFIDENCE:** HIGH — existing pattern; one-line `_register_all_tools` edit; one test for T4.

---

### Q7 — AC21 sanitize test count

**OPTIONS:**
(a) Add 2 new tests (empty list, list-over-limit truncation, content passthrough) to reach ≥5.
(b) Reduce AC21 to ≥3 tests.
(c) Drop AC21 entirely.

#### ## Analysis

R2's grep shows `tests/test_cycle12_sanitize_context.py` has tests at `:35` and `:105`. The first is parametrized with 2 branches (so it contributes 2 collected cases); the second is standalone (1 case). Total = 3 collected cases. AC21 requires ≥5 collected `-k sanitize` cases in `test_mcp_core.py` after the fold. Option (a) requires adding empty-list, list-over-limit truncation, and content-passthrough as 3 explicit tests (matching R2's amendment text: "for empty input, list-over-limit truncation, and content passthrough"). 3 fold cases + 3 new behavioral cases = 6, comfortably ≥5. The new cases align with cycle-16 L2 (behavioral coverage, not docstring-only): each one reverts to FAIL if `_sanitize_conversation_context` is mutated to a no-op.

Option (b) lowers the bar — it's the wrong direction. AC21 is the AC10-from-cycle-43 carry-over and the whole point is to upgrade the coverage during the fold. Option (c) drops the carry-over entirely; that's not appropriate when the merge surface is now clear (per requirements §1 cycle-43 carry-over note).

**DECIDE:** **(a)** — add 3 new behavioral tests (empty list input, list-over-limit truncation, content passthrough) to `test_mcp_core.py` during the fold; total ≥6 collected cases. Each new test must FAIL when `_sanitize_conversation_context` is mutated to `lambda x: x` (cycle-16 L2 self-check).

**RATIONALE:** Matches R2's amendment text exactly + brainstorm's option A. Behavioral coverage + dedup-clean fold + clear self-check methodology.

**CONFIDENCE:** HIGH — R2 enumeration confirmed no dedup risk; cycle-16 L2 self-check is well-rehearsed.

---

### Q8 — AC23: cycle11/cycle32 patch migration after M3

**OPTIONS:**
(a) `ingest.py` uses `import kb.mcp.core as core; core.RAW_DIR` (lazy lookup, patch-transparent).
(b) Migrate all test patches to `kb.mcp.ingest.RAW_DIR`.
(c) Keep constants in `core.py` and tests target core; `ingest.py` also reads via lazy lookup.

#### ## Analysis

R2 enumerated the patch sites: `tests/test_cycle11_task6_mcp_ingest_type.py:13,14,24,25,35,48` patch `kb.mcp.core.PROJECT_ROOT`, `kb.mcp.core.RAW_DIR`, `kb.mcp.core.SOURCE_TYPE_DIRS`. `tests/test_cycle32_cli_parity_and_fair_queue.py:430,473,508,545,591` references `kb_ingest_content`. `tests/test_fixes_v050.py`, `tests/test_v098_fixes.py`, `tests/test_v4_11_mcp.py`, etc. all patch `kb.mcp.core.*` constants. The total is ~40+ reference-form and string-form patch sites.

Cycle-18 L1 hazard: if `ingest.py` does `from kb.mcp.core import RAW_DIR`, it captures a snapshot of `RAW_DIR` at import time. When a test patches `kb.mcp.core.RAW_DIR`, the snapshot inside `ingest.py` is unaffected → ingest tools read the original value → test invariant violated. The fix per cycle-18 L1 + cycle-19 L2 is lazy lookup: `ingest.py` does `from kb.mcp import core` at module top, then references `core.RAW_DIR` *at call time* inside each function. The `core` module is mutable (just a reference to the package's `core` submodule object), so `monkeypatch.setattr("kb.mcp.core.RAW_DIR", new)` flips `core.RAW_DIR` and `ingest.py`'s next call sees the new value.

Option (a) and (c) describe the same mechanism. Option (b) requires migrating 40+ patches and creates a divergence: tests patch `kb.mcp.ingest.RAW_DIR` but the truth-of-the-value still lives in `kb.config` via `kb.mcp.core` import. Two patch targets for one constant is exactly the brittleness C42-L3 flags. Option (c)'s phrasing "constants in core.py" matches reality — `core.py` already has `from kb.config import PROJECT_ROOT, RAW_DIR, SOURCE_TYPE_DIRS` as module-level imports; we keep that, and `ingest.py` does `from kb.mcp import core` and reads `core.PROJECT_ROOT` at call time. This requires zero test migrations (AC23 "without modification" preserved).

**DECIDE:** **(c)** — keep `PROJECT_ROOT`, `RAW_DIR`, `SOURCE_TYPE_DIRS` defined as module-level imports in `kb.mcp.core`; `ingest.py` imports `kb.mcp.core as core` at module top and reads `core.PROJECT_ROOT` / `core.RAW_DIR` / `core.SOURCE_TYPE_DIRS` *at call time* inside each tool function. Add a Step 9 regression test asserting `monkeypatch.setattr("kb.mcp.core.RAW_DIR", X)` causes `kb_ingest_content` (in `ingest.py`) to write under X, not the original.

**RATIONALE:** Preserves AC23 "without modification" by making the patch target work transparently across the split. Lazy lookup is the canonical fix for snapshot-bind (cycle-18 L1). Option (b) violates AC23. Option (a) ≡ (c); option (c) is more explicit about the constant-residency.

**CONFIDENCE:** HIGH — cycle-18 L1 + cycle-19 L2 are textbook applicable; R2 evidence is comprehensive.

---

### Q9 — AC25: `atomic_text_write` final signature

**OPTIONS:** R1 + R2 agree: `def atomic_text_write(content: str, path: Path | str, *, exclusive: bool = False) -> None`.

#### ## Analysis

R2's grep enumerates 24 source-side and 10 test-side direct call sites all using `(content, path)`. The current signature at `src/kb/utils/io.py:144` is `def atomic_text_write(content: str, path: Path) -> None`. Reversing to `(path, content)` would silently swap arguments at every call site — a non-recoverable change in the same commit. R1 caught this; R2 enumerated it. The only question is whether to widen `path: Path` to `path: Path | str` for compatibility with callers passing strings (none currently exist per the grep, but it's free type-widening). Both R1 and R2 propose the widening. Both contracts are preserved (cycle-15 L1) by branching on `exclusive`: `True` → `os.open(O_CREAT|O_EXCL|O_WRONLY)` for slug-collision detection; `False` → existing tempfile + `os.replace` crash-atomicity path with `_flush_and_fsync` (preserves cycle-21 L4 fsync semantics).

The pre-amendment in the prompt explicitly demands the current `(content, path)` order be preserved.

**DECIDE:** **CONFIRM** — `def atomic_text_write(content: str, path: Path | str, *, exclusive: bool = False) -> None`. Both contracts preserved per cycle-15 L1.

**RATIONALE:** R1 + R2 + pre-amendment all align. 24 callers stay unchanged. `Path | str` type widening is free.

**CONFIDENCE:** HIGH — unanimous across R1, R2, and pre-amendment.

---

### Q10 — AC26 + AC27 capture.py import pattern

**OPTIONS:**
(a) R2's pattern: `import kb.utils.io as io_utils` + call `io_utils.atomic_text_write(...)` so single-site `monkeypatch.setattr("kb.utils.io.atomic_text_write", ...)` works.
(b) Leave `from kb.utils.io import atomic_text_write` and require dual-site patches (regress AC27).
(c) Provide a thin module-level helper in capture.py that always reads from `kb.utils.io`.

#### ## Analysis

The C42-L3 hazard returns: `from kb.utils.io import atomic_text_write` in `capture.py` binds the name in `capture.py`'s namespace at import time. After that, `monkeypatch.setattr("kb.utils.io.atomic_text_write", X)` changes the binding in `kb.utils.io`'s namespace but `capture.atomic_text_write` is a *separate* binding pointing at the original function — patches don't propagate. That's why today's `tests/test_capture.py:805,806,819,820` patches BOTH sites. AC27 requires collapsing to a single site; the only way to make a single `kb.utils.io.atomic_text_write` patch work is to make `capture.py` look up the function on the module *at call time*. Option (a) — `import kb.utils.io as io_utils` then `io_utils.atomic_text_write(content, path, exclusive=True)` — does exactly that: each call dereferences `io_utils.atomic_text_write` against the (mutated) `kb.utils.io` module's `__dict__`. Option (c) is just option (a) with extra ceremony.

Option (b) defeats AC27's whole purpose — it asks to keep dual-site patches, which means AC27 becomes a no-op. R2's amendment is correct: `capture.py` must do `import kb.utils.io as io_utils` (not `from kb.utils.io import atomic_text_write`) for the AC27 collapse to actually intercept.

**DECIDE:** **(a)** — `src/kb/capture.py` does `import kb.utils.io as io_utils` at module top and calls `io_utils.atomic_text_write(content, path, exclusive=True)` at every call site. AC27 dual-site patch collapses to a single `monkeypatch.setattr("kb.utils.io.atomic_text_write", X)` and the patch intercepts because capture's call goes through the (mutated) module object.

**RATIONALE:** Only mechanism that makes AC27 actually work. Aligns with R2's amendment. Option (b) breaks AC27. Option (c) is unnecessary.

**CONFIDENCE:** HIGH — C42-L3 is unambiguous; R2's pattern is the standard fix.

---

### Q11 — AC29 cache-key behavior change

**OPTIONS:**
(a) Accept the production change (now AC29 is a behavior change, not just a test upgrade — affects T6 and ToCheck CI).
(b) DROP AC29 entirely (delete the docstring test since the behavior is documented as intentional, no replacement).
(c) Replace with a different behavioral test that pins the EXISTING behavior (e.g. assert that two writes within the same mtime tick return cached content — pinning the documented stale-read).

#### ## Analysis

R2's finding is critical: `src/kb/utils/pages.py:78-83` documents stale mtime reads as **acceptable** ("Acceptable for lint/query hot-paths because each CLI invocation starts with a fresh cache and mid-run edits are rare"). AC29 as written would assert the OPPOSITE behavior — that fresh content IS returned after an mtime collision. That's a production behavior change masquerading as a test upgrade. It would invalidate the documented contract, change cache memory profile (st_size or content fingerprint added to the cache key), and risk breaking the lint/query hot-path performance assumption ("4 lint/checks call sites" cache full-run retention).

This cycle is non-functional refactor (requirements §2: "NO functional or behavior changes"). AC29 as written breaks that invariant. The brainstorm flagged this as Q10 — vacuous-test upgrade self-check. Option (a) violates the cycle's non-goal #1. Option (b) leaves the vacuous test in place — drops a C43-L1 carry-over without replacement; not aligned with C40-L3 + C41-L1 lessons. Option (c) is the right move: delete the docstring test (it's signature-only per cycle-43 L4 inspect-source guidance) and replace with a behavioral test that **pins the documented stale-read behavior** — i.e., assert that two writes within the same coarse mtime tick return the SAME (cached) content. That preserves the existing contract, satisfies cycle-16 L2 (the test fails if the cache key mechanism is broken), and is consistent with cycle-44's "no behavior changes" non-goal.

Step 9 self-check: mutate `_load_page_frontmatter_cached` to bypass the cache → test fails (because the second read would return the new content, not the stale cached version). That confirms behavioral coverage of the documented contract.

**DECIDE:** **(c)** — replace the docstring test with `test_load_page_frontmatter_caches_within_same_mtime_tick`: warm cache, force same `mtime_ns` via `os.utime`, overwrite file, call `load_page_frontmatter` again, assert STALE (cached) content is returned. Self-check: mutate `_load_page_frontmatter_cached` to bypass cache → confirm test fails.

**RATIONALE:** Preserves the documented contract (no behavior change — non-goal #1). Replaces a vacuous test with a behavioral test that genuinely covers the cache-key mechanism. Option (a) is a behavior change in a refactor cycle. Option (b) leaves the vacuous test or deletes it without replacement (loses coverage).

**CONFIDENCE:** HIGH — explicit non-goal #1 forbids option (a); option (c) inverts AC29's assertion to match the documented contract.

---

### Q12 — AC30 target API

**OPTIONS:** R2: `file_lock` uses `os.kill` not `psutil.pid_exists`. Test target should be `monkeypatch.setattr(kb.utils.io.os, "kill", lambda pid, sig: ProcessLookupError raised)`. Confirm.

#### ## Analysis

I verified at `src/kb/utils/io.py:412` — the actual code uses `os.kill(stale_pid, 0)` and catches `ProcessLookupError` to unlink the stale lock. There is no `psutil` import anywhere in the module. AC30 as written says "monkeypatches `psutil.pid_exists` to return `False`" — but `psutil.pid_exists` is never called. A patch on a never-called function is a vacuous test (defeats the entire purpose of the upgrade and triggers the cycle-43 inspect-source-tests warning).

R2's amendment is correct: monkeypatch `kb.utils.io.os.kill` to raise `ProcessLookupError` for the fake stale PID, then assert `file_lock` acquires successfully (proving the stale-lock-reaping path at line 413-415 was exercised). Self-check (cycle-16 L2): mutate the `lock_path.unlink(missing_ok=True)` line to a no-op → test should fail with TimeoutError because the stale lock isn't reaped. This is genuine behavioral coverage of the documented PID-recycling fix.

The amendment also requires renaming the test from `test_file_lock_reaps_stale_lock_with_recycled_pid` → `test_file_lock_reaps_stale_lock_with_dead_pid` because we're testing dead-PID detection, not PID-recycling specifically (recycling is a *consequence*, not the test target).

**DECIDE:** **CONFIRM R2's amendment** — monkeypatch target is `kb.utils.io.os.kill` (made to raise `ProcessLookupError` for the fake stale PID). Test name: `test_file_lock_reaps_stale_lock_with_dead_pid`. Step 9 self-check: mutate `lock_path.unlink(missing_ok=True)` at `src/kb/utils/io.py:415` to a no-op → confirm test fails.

**RATIONALE:** AC30 as originally written patches a function that never executes — vacuous (cycle-43 L4). R2's grep confirms `os.kill` is the actual call. Self-check is well-defined and reverts cleanly.

**CONFIDENCE:** HIGH — directly verified the source at line 412; no `psutil` import exists.

---

### Q13 — M3 scope risk

**OPTIONS:**
(a) Include M3 with lazy-lookup pattern (Q8 option a/c) + targeted test migrations only.
(b) Defer M3 to cycle 45 — ship M1, M2, M4 + tests in cycle 44.
(c) Include M3 with full patch migration (≥30 ACs added).

#### ## Analysis

R2's enumeration shows M3 has the highest patch-site footprint: 6 sites in `test_cycle11_task6_mcp_ingest_type.py`, 5 in `test_cycle32_cli_parity_and_fair_queue.py` (kb_compile_scan + kb_ingest_content reference-form), plus `test_fixes_v050.py:285,286,302,303` (4), `test_cycle19_mcp_monkeypatch_migration.py:159` + `:57,61,62` (4), `test_cycle33_mcp_core_path_leak.py:106,170` (2), `test_mcp_core.py:33,35,296,316` (4), `test_v0914_phase395.py:801` (1), `test_v098_fixes.py:19,20` (2), `test_v4_11_mcp.py:34` (1), `test_cycle9_mcp_core.py:46,47,86,87` (4), `test_ingest.py:795,796,797` (3), `test_backlog_by_file_cycle1.py:338,339` (2), `test_cycle12_sanitize_context.py:72,128` (2), `test_cycle16_kb_query_save_as.py:99,108,118,126,135,145,157,179,215,232,248,255` (12). Total ≈ 50+ patch sites.

Option (c) — full migration — would add ≥30 ACs and trigger the cycle-22 L4 conservative posture. Option (b) — defer M3 — is safe but loses Phase 4.6 close-out for M3. Option (a) — lazy-lookup pattern from Q8 — keeps `core.py` as the single residency for `PROJECT_ROOT`, `RAW_DIR`, `SOURCE_TYPE_DIRS`, plus tool function names re-exported from `core.py` (e.g., `from kb.mcp.ingest import kb_ingest_content` then `core.kb_ingest_content = kb_ingest_content` for backward compat). Tests patching `kb.mcp.core.kb_compile_scan` mutate the re-exported binding; the test's *own caller* (a CLI test) calls `kb_compile_scan` either directly or via `core.kb_compile_scan` — if via the latter, the patch works.

The risk-vs-value tradeoff: option (a) ships M3 in cycle 44 with lazy lookups, ~5 targeted regression tests for the patch-transparency invariant (Q8 condition), and the existing 50+ test sites unchanged. Option (b) saves complexity but pushes M3 to cycle 45. Given R2's explicit AC23 amendment is option (a)/(c) shaped (lazy lookup makes patches transparent), and given Q14's split-cycle option (Q14 option c) — which DEFERS M3 — gives us the cleanest story, I lean toward **deferring M3 to cycle 45** for safety. Cycle 44 has 4 monolith items; M3 is the highest-risk one and the deferment loss is one cycle. The split-cycle option also lets us complete M2's compatibility-shim cleanup in cycle 45 alongside M3, which is naturally batched.

**DECIDE:** **(b)** — defer M3 to cycle 45. Cycle 44 ships M1, M2, M4 + AC10 fold + AC28 + amended AC29/AC30. Cycle 45 ships M3 with lazy-lookup pattern (Q8 option c) + targeted patch-transparency regression tests + M2 compat-shim removal.

**RATIONALE:** R2's enumeration shows M3 is the highest-risk split with ≥50 patch sites, and threat-model T4 (29-tool registration) plus cycle-23 L5 (FastMCP boot order) compound the risk. CLAUDE.md's "Two tests before declaring done" + "Bias toward caution over speed on non-trivial work" + cycle-22 L4 (conservative posture for cross-cycle exposure) all point toward deferment. Cycle 44 still ships 3 of 4 monoliths + all carry-overs — substantial Phase 4.6 progress without bunching the riskiest split with three other splits in one cycle.

**CONFIDENCE:** MEDIUM — option (a) is also defensible if implementation discipline is strong; option (b) is the conservative choice. R2 didn't explicitly defer; this is a scope-management call. The decision can be revisited in Step 7 plan if M1+M2+M4 prove cleaner than expected (with the corollary that adding M3 would require re-running design eval).

---

### Q14 — Cycle scope cap

**OPTIONS:**
(a) Cap cycle 44 at 30 ACs (current scope) — keep amendments but DON'T add new test-migration ACs (rely on compatibility shims).
(b) Widen cycle 44 to ~45 ACs to include all amendments and migrations.
(c) Split: cycle 44 = M1 + M4 + AC10 fold + AC28 + amended AC29/AC30 (~15 ACs); cycle 45 = M2 + M3 + M2/M3 patch migrations.

#### ## Analysis

The original 30 ACs assumed 4 monoliths + 3 vacuous-test upgrades. R2's amendments add: regression test for AC8 patch transparency, regression test for AC23 patch transparency, regression test for T4 29-tool count, AC11 9-file requirement (was 8), AC14 widened scope (1→3 file migrations), AC15 patch-target migration, AC21 +3 behavioral tests, AC25 type widening, AC26+AC27 import-pattern change, AC29 inversion to pin documented behavior, AC30 target API correction. Net: ~6 new ACs (regression tests + amendment-induced test-fold work). Total post-amendment: 30 base + 6 new = 36 ACs.

Q13 deferred M3 to cycle 45. M3 contributes AC19-AC24 (6 ACs). With M3 deferred, cycle 44 = 36 - 6 = 30 ACs. That fits the 30-AC scope cap naturally without forcing option (a)'s "drop the new tests" tradeoff. AC10 fold (AC21) + AC28 + AC29 + AC30 are independent of M3 and ship in cycle 44.

Option (a) would keep all 4 monoliths but drop the regression tests and force compatibility-shim-only paths — that's exactly the C42-L3 + cycle-19 L1 antipattern (documented hazard, untested). Option (b) widens to 45 ACs and pushes Step 9 budget. Option (c) is the natural Q13 follow-on: cycle 44 = M1 + M2 + M4 + AC10 fold + AC28-30 ≈ 30 ACs (M2 keeps shims per Q2, no patch-migration ACs needed); cycle 45 = M3 + M2 shim removal + M3 patch migration + cycle-44 carry-overs ≈ 25-30 ACs.

Since Q13 chose option (b) (defer M3), Q14 must align — **option (c)** with the M2 reframing. Cycle 44 keeps the original 4 monoliths' worth of work modulo M3.

**DECIDE:** **(c)** — split cycle scope per Q13: cycle 44 = M1 (AC1-AC10) + M2 with compat shims (AC11-AC18) + M4 (AC25-AC27) + AC21 fold (renumbered) + AC28-AC30 amended. Total = 30 ACs (4 fewer than 36 because M3's 6 ACs deferred, and the M3 regression test from Q6 is folded into cycle 45). Cycle 45 = M3 (AC19-AC24 from current cycle, renumbered) + M2 compat-shim removal (renumbered ACs migrating ~25 patch sites) + M3 lazy-lookup pattern (Q8 condition C) + Q6 29-tool registration test.

**RATIONALE:** Aligns with Q13. Keeps cycle 44 at 30 ACs (no scope creep). Cycle 45 has a clear, focused agenda (M3 + M2 shim removal — both touch the test-patch-target migration boundary, naturally batched). No regression-test deferrals required in cycle 44 because the M3 regression is also deferred.

**CONFIDENCE:** HIGH — direct consequence of Q13; the split is clean and narratively coherent.

---

## CONDITIONS (Step 9 must satisfy)

Per cycle-22 L5, these are load-bearing test-coverage requirements derived from Q1-Q14:

1. **Q1 / AC8 patch transparency.** Add `tests/test_cli.py::test_check_source_coverage_uses_patched_wiki_dir` (or similar in `test_lint.py` if test_cli.py is not the right home) — patches `kb.lint.checks.WIKI_DIR` to a tmp wiki, asserts `check_source_coverage()` reads from the tmp wiki. Self-check: revert the package-level binding so submodules re-bind from `kb.config` directly → confirm test fails.

2. **Q2 / AC11+AC16 compat shims.** Add `tests/test_lint_augment_shims.py` (or fold into existing) asserting `from kb.lint._augment_manifest import Manifest` and `from kb.lint._augment_rate import RateLimiter` succeed and resolve to the same objects as the new package paths.

3. **Q3 / AC14 patch migration completeness.** Add a Step-9 grep gate: `grep -rnE "patch.*\(.*kb\.lint\.augment\.call_llm_json" tests/` returns 0 hits after migration. Fail Step 9 if any sites remain.

4. **Q4 / AC15 orchestrator location.** `kb.lint.augment.orchestrator` module exists; `from kb.lint.augment.orchestrator import run_augment` resolves; package `__init__.py` re-exports `run_augment` for backward compat with explicit `# noqa: F401` per C42-L5.

5. **Q7 / AC21 sanitize ≥6 cases.** `python -m pytest tests/test_mcp_core.py -x -k sanitize --collect-only` reports ≥6 collected cases. Each new test must FAIL when `_sanitize_conversation_context` is mutated to `lambda x: x` (cycle-16 L2 self-check).

6. **Q9 / AC25 signature.** `inspect.signature(atomic_text_write)` returns `(content: str, path: Path | str, *, exclusive: bool = False) -> None`. Direct test: `atomic_text_write("x", existing_path, exclusive=True)` raises `FileExistsError`; `atomic_text_write("x", new_path)` succeeds.

7. **Q10 / AC27 single-site patch interception.** Test `tests/test_capture.py::test_capture_atomic_write_single_site_patch_intercepts` — sets `monkeypatch.setattr("kb.utils.io.atomic_text_write", capture_recorder)`, invokes capture's write path, asserts `capture_recorder.called`. Self-check: revert `capture.py` to `from kb.utils.io import atomic_text_write` → test fails.

8. **Q11 / AC29 cache-stability behavioral test.** `tests/test_utils_io.py::test_load_page_frontmatter_caches_within_same_mtime_tick` — warms cache, forces same `mtime_ns` via `os.utime`, overwrites file, asserts STALE (cached) content is returned. Self-check: mutate `_load_page_frontmatter_cached` to bypass cache → confirm test fails.

9. **Q12 / AC30 stale-PID-reaping behavioral test.** `tests/test_utils_io.py::test_file_lock_reaps_stale_lock_with_dead_pid` — creates stale `.lock` with fake PID, monkeypatches `kb.utils.io.os.kill` to raise `ProcessLookupError`, acquires `file_lock`, asserts success. Self-check: mutate `lock_path.unlink(missing_ok=True)` at `src/kb/utils/io.py:415` to a no-op → confirm test fails.

10. **C42-L5 ruff-stripping discipline.** Every re-export line in `kb/lint/checks/__init__.py`, `kb/lint/augment/__init__.py`, `kb/lint/_augment_manifest.py` (shim), `kb/lint/_augment_rate.py` (shim) carries `# noqa: F401  # re-exported for backward compat (cycle-23 L5)` plus a one-line nearby comment explaining ruff must not strip compatibility exports.

11. **Cycle-15 L1 contract preservation (M4).** `atomic_text_write(content, path, exclusive=False)` preserves crash-atomicity (tempfile + `os.replace` + `_flush_and_fsync`). `atomic_text_write(content, path, exclusive=True)` uses `os.open(O_CREAT|O_EXCL|O_WRONLY)` and raises `FileExistsError` on conflict. Both contracts have a behavioral test.

12. **Cycle-19 L2 lazy accessors (M2).** `import kb.lint.augment.manifest` and `import kb.lint.augment.rate` succeed with no `WIKI_DIR` configured (no module-top disk reads). Add a Step 9 test that patches `WIKI_DIR` to a non-existent path and confirms import succeeds without `FileNotFoundError`.

13. **Cycle-22 L5 plan-time grep gate (M2).** Step 7 plan must enumerate every monkeypatch/patch site for moved augment symbols (`call_llm_json`, `run_augment`, `MANIFEST_DIR`, `RATE_PATH`, `RateLimiter`, `Manifest`, `RAW_DIR`, `_resolve_raw_dir`, `_relevance_score`, `_propose_urls`, `_post_ingest_quality`, `_record_verdict_gap_callout`) BEFORE moving any symbol. R2's enumeration is the starting point.

14. **Test hygiene (cycle 34 L4).** No scratch files (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`) at PR-time per cycle-34 hygiene test.

---

## FINAL DECIDED DESIGN

The amended AC list with all changes from Q1-Q14 applied. **Cycle 44 ships 23 ACs** (M1 + M2 with shims + M4 + carry-overs) + **7 condition tests** = 30 deliverables. M3 deferred to cycle 45 (Q13/Q14).

### M1 — `lint/checks.py` split (AC1-AC10) [unchanged from requirements]

**AC1.** `src/kb/lint/checks/` package directory exists containing an `__init__.py` registry file. The original `src/kb/lint/checks.py` flat file is removed. Importing `kb.lint.checks` succeeds without error.

**AC2.** Each lint rule group has its own sub-module file: `frontmatter.py`, `dead_links.py`, `orphan.py`, `cycles.py`, `staleness.py`, `duplicate_slug.py`, `consistency.py`, `inline_callouts.py`. Assertion: each file exists and contains at least one function definition.

**AC3.** `src/kb/lint/checks/__init__.py` re-exports every function importable from the original flat module (`check_source_coverage`, `check_dead_links`, `check_orphan_pages`, `check_cycles`, `check_staleness`, `check_status_mature_stale`, `check_authored_by_drift`, `fix_dead_links`, plus any other top-level callable). Each re-export line carries `# noqa: F401  # re-exported for backward compat (cycle-23 L5)` per C42-L5.

**AC4-AC7, AC9-AC10.** Listed test files pass without modification.

**AC8 [AMENDED per Q1].** `tests/test_cli.py` passes without modification. The package `__init__.py` re-exports `WIKI_DIR` and `RAW_DIR` from `kb.config`. Submodules MUST read these constants via the package binding (e.g., `from kb.lint import checks; ... checks.WIKI_DIR`), NOT via direct `from kb.config import WIKI_DIR`. Add regression test asserting `patch("kb.lint.checks.WIKI_DIR", wiki_dir)` causes `check_source_coverage` to read from `wiki_dir` (CONDITION 1).

### M2 — `lint/augment.py` package conversion (AC11-AC18) [amended per Q2-Q4]

**AC11 [AMENDED per Q2+Q4].** `src/kb/lint/augment/` package directory exists containing: `__init__.py`, `collector.py`, `proposer.py`, `fetcher.py`, `persister.py`, `quality.py`, `manifest.py`, `rate.py`, **`orchestrator.py`** (9 files). The original `src/kb/lint/augment.py` flat file is removed. **`src/kb/lint/_augment_manifest.py` and `src/kb/lint/_augment_rate.py` are kept as compatibility shims** that re-export from `kb.lint.augment.manifest` / `kb.lint.augment.rate` with explicit `# noqa: F401` + comment per C42-L5. Tagged for cycle-45 deletion.

**AC12 [unchanged].** Re-exports preserve `from kb.lint.augment import run_augment` etc. — `save_page_frontmatter` is re-exported via `from kb.utils.pages import save_page_frontmatter` in `__init__.py` (mirrors current flat module behavior at `augment.py:33`).

**AC13 [unchanged].** `manifest.py` and `rate.py` use lazy `_get_X()` accessors per cycle-19 L2.

**AC14 [AMENDED per Q3].** All `tests/` patch sites targeting `kb.lint.augment.call_llm_json` are migrated to `kb.lint.augment.proposer.call_llm_json`. Required migration set includes: `test_cycle13_frontmatter_migration.py:531,551,643,663` (4) + `test_cycle9_lint_augment.py:70` (1) + `test_v5_lint_augment_orchestrator.py:16,167,190,213,251,286,297,326,353,372,434,495,548,734,790,907,946` (17). Step 9 grep gate (CONDITION 3) verifies completeness.

**AC15 [AMENDED per Q4].** `tests/test_cycle17_resume.py:123,168` updated from `patch("kb.lint.augment.run_augment", ...)` to `patch("kb.lint.augment.orchestrator.run_augment", ...)`. `kb.lint.augment.__init__` re-exports `run_augment` only for import compatibility.

**AC16 [AMENDED per Q2].** Listed tests pass without modification BECAUSE `_augment_manifest.py` and `_augment_rate.py` shims are kept (per AC11 amendment).

**AC17, AC18.** Unchanged.

### M3 — DEFERRED to cycle 45 (AC19-AC24 removed from this cycle per Q13/Q14)

`src/kb/mcp/core.py` split into `core.py` + `ingest.py` + `compile.py` is deferred to cycle 45. Cycle 45 will adopt the lazy-lookup pattern (`import kb.mcp.core as core; core.RAW_DIR`) per Q8 option (c) and add a 29-tool-registration regression test per Q6 / T4.

### M4 — `atomic_text_write` consolidation (AC25-AC27) [amended per Q9-Q10]

**AC25 [AMENDED per Q9].** Final signature: `def atomic_text_write(content: str, path: Path | str, *, exclusive: bool = False) -> None`. `(content, path)` order preserved. `Path | str` type-widened. Cycle-15 L1: `exclusive=True` uses `os.open(O_CREAT|O_EXCL|O_WRONLY)` (raises `FileExistsError`); `exclusive=False` uses tempfile + `os.replace` (preserves crash-atomicity + `_flush_and_fsync`). Assertion: `atomic_text_write("x", existing_path, exclusive=True)` raises `FileExistsError`; `atomic_text_write("x", new_path)` succeeds.

**AC26 [AMENDED per Q10].** `src/kb/capture.py` removes `_exclusive_atomic_write` and does:
```python
import kb.utils.io as io_utils
...
io_utils.atomic_text_write(content, path, exclusive=True)
```

**AC27 [AMENDED per Q10].** `tests/test_capture.py:805-806,819-820` collapse to a single patch of `kb.utils.io.atomic_text_write`. The single-site patch intercepts because capture.py reaches the function via `io_utils.atomic_text_write` at call time.

### Vacuous-test upgrades (AC28-AC30) [AC29 / AC30 amended]

**AC28 [unchanged].** `tests/test_models.py::test_graph_builder_documents_case_sensitivity_caveat` is DELETED.

**AC29 [AMENDED per Q11].** `test_load_page_frontmatter_docstring_documents_mtime_caveat` is REPLACED by a behavioral test `test_load_page_frontmatter_caches_within_same_mtime_tick` that asserts STALE (cached) content is returned within the same coarse mtime tick — pinning the documented contract. Production cache key is NOT changed (cycle 44 is non-functional). Self-check: mutate `_load_page_frontmatter_cached` to bypass cache → test fails.

**AC30 [AMENDED per Q12].** `test_cycle12_io_doc_caveats_are_present` atomic_*_write portions DELETED. PID portion REPLACED by `test_file_lock_reaps_stale_lock_with_dead_pid` — creates stale `.lock` with fake PID, monkeypatches `kb.utils.io.os.kill` to raise `ProcessLookupError`, acquires `file_lock`, asserts success. Self-check: mutate `lock_path.unlink(missing_ok=True)` at `src/kb/utils/io.py:415` to a no-op → test fails.

### AC10 fold (renumbered as part of M3 deferment cleanup)

**AC21 [AMENDED per Q7] — renumbered AC-fold-1.** `tests/test_cycle12_sanitize_context.py` deleted. Its 3 collected cases moved into `tests/test_mcp_core.py`. ADD 3 new behavioral tests for `_sanitize_conversation_context`: empty-list input, list-over-limit truncation, content passthrough. Total ≥6 collected cases per `pytest -k sanitize`. Each new test must FAIL when `_sanitize_conversation_context` is mutated to `lambda x: x` (cycle-16 L2 self-check).

---

## REVISED CYCLE COUNT

**Cycle 44 final AC count: 23 ACs + 7 condition tests = 30 deliverables.**

Breakdown:
- M1 = 10 ACs (AC1-AC10)
- M2 = 8 ACs (AC11-AC18 with shims)
- M4 = 3 ACs (AC25-AC27)
- AC10 fold = 1 AC (renumbered from AC21)
- Vacuous upgrades = 1 AC (AC28; AC29 + AC30 are CONDITIONS not ACs because they include self-check methodology)
- Conditions (Step 9 load-bearing) = 7 (CONDITIONS 1, 3, 5, 7, 8, 9 + ruff/lazy-accessor/grep-gate gates)

**Cycle 45 staged scope (informational, ~25 ACs):**
- M3 = 6 ACs (former AC19-AC24)
- M2 compat-shim removal = ~25 patch-site migration ACs (one per file with patch sites)
- Q6 29-tool count regression test = 1 AC
- Q8 lazy-lookup regression tests = ~3 ACs
- Total cycle 45 ≈ 35 ACs

---

## Citations

- **C42-L3** (Function moves invalidate monkeypatch even with re-exports) → Q1, Q3, Q8, Q10, Q14
- **C42-L5** (`# noqa: F401` for re-exports to prevent ruff stripping) → Q1, Q2, Q4, CONDITIONS 10
- **Cycle-23 L5** (Package `__init__` MUST preserve `from <package> import <symbol>` semantics; FastMCP tool registration on import) → Q1, Q2, Q4, Q6
- **Cycle-19 L2** (Module-top file reads must become lazy `_get_X()` accessors) → Q11, AC13, CONDITIONS 12
- **Cycle-19 L1** (Plan must run THREE greps: string-form + reference-form + broader) → Q3, Q8, CONDITIONS 13
- **Cycle-18 L1** (`from X import Y` snapshot-bind hazard) → Q8
- **Cycle-16 L2** (Behavioral test self-check: revert production → confirm test fails) → Q7, Q11, Q12, CONDITIONS 5, 8, 9
- **Cycle-15 L1** (Replace X with Y must preserve full contract — both crash-atomicity AND O_EXCL) → Q9, AC25, CONDITIONS 11
- **Cycle-22 L4** (Conservative posture for cross-cycle CVE/refactor exposure) → Q13
- **Cycle-22 L5** (Conditions are load-bearing) → throughout CONDITIONS section
- **Cycle-43 L4** (Inspect-source / docstring tests are signature-only — pass after revert; need behavioral replacement) → Q11, Q12
- **Cycle-7 L4** (Path validators / signature changes must touch all callers in same commit) → Q9
- **Threat model T4** (29-tool MCP registration count) → Q6 (deferred), Q14
- **Cycle 44 non-goal #1** ("NO functional or behavior changes") → Q11
