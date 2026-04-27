# Cycle 45 Design Decision Gate

**Date:** 2026-04-27
**Branch:** cycle-45-batch
**Worktree:** D:/Projects/llm-wiki-flywheel-c45
**Inputs:** requirements (30 ACs), threat-model (9 invariants), brainstorm (4 design choices, 10 Q), R1 DeepSeek (verdict AMEND), R2 Codex with grep (verdict AMEND, 17 amendments)

## VERDICT

**PROCEED-WITH-AMENDS.** The cycle-45 batch refactor is the right shape and scope, but R2's grep-driven review surfaced 17 concrete amendments that must land in the requirements doc before Step 7 (TaskList) and Step 9 (TDD) begin. The dominant failure modes are (a) package-level monkeypatch propagation (AC3/AC8/AC9/AC20), (b) "tests pass unchanged" colliding with private-module deletion (AC11/AC16), (c) AC25 reversed signature, (d) AC29/AC30 testing nonexistent behavior, and (e) M3 LOC cap unrealistic. Each is fixable inline with the strategies decided below. Two ACs (AC29, AC30) are dropped because they require behavior changes that violate the cycle's pure-refactor non-goal.

---

## DECISIONS

### Q-A — Cycle scope

OPTIONS:
- **Option 1:** Full 30-AC scope; resolve all 17 amendments inline.
- **Option 2:** Drop AC29/AC30 (require behavior changes); proceed with 28 ACs.
- **Option 3:** Drop M3 entirely to a follow-up; ship M1+M2+M4+AC21+AC28 only.

## Analysis

The blast-radius bias says smaller is safer. But Option 3 is the wrong reduction: M3 (mcp/core split) is the largest LOC monolith (1149 LOC) and the one with the most dangerous coupling growth (any new write-path tool would land there by default). Deferring M3 means cycle 46 will start under exactly the same pressure with zero learning compounded — and the R2 grep already enumerates the moveable functions and test surface, so the work is well-bounded. The legitimate concern with M3 is the LOC cap (Q-C), not the scope.

Option 2 — dropping AC29/AC30 — passes the "pure refactor" non-goal test cleanly. R2 grep confirms (i) `load_page_frontmatter` cache is already a pure `(path_str, mtime_ns)` lru_cache with no content-hash fallback, so the AC29 "mtime-collision returns FRESH content" assertion is testing logic that does not exist (the test would either pass on the current pure-mtime cache OR require a behavior change to add a content-hash fallback — both violate cycle non-goal #1); (ii) production uses `os.kill(stale_pid, 0)` raising `ProcessLookupError`, while AC30 mocks `psutil.pid_exists` (zero hits in `src/kb/`), so the test is testing nonexistent code. Both ACs are vacuous-test upgrades that, on close inspection, were proposed for behavior that doesn't exist in production. The honest answer is to delete the original vacuous tests (the docstring assertions are still bad) and document the deletion + the rationale. AC28 stays because behavior IS already covered by `test_page_id_*`. Therefore: **Option 2** — proceed with 28 ACs, drop AC29 and AC30 with documented rationale, retain AC28.

DECIDE: **Option 2** (28 ACs; drop AC29 + AC30 with rationale recorded as a new sub-AC inside AC30 / AC29 NOTE block — the original vacuous tests are still deleted, but no replacement test is added since there is no behavioral divergence to test).

RATIONALE: Vacuous-test upgrades that turn out to require behavior changes violate the cycle's pure-refactor non-goal. Deleting the original docstring assertions still removes the cycle-16 L2 vacuity flag — the goal of C40-L3/C41-L1 was "stop tests that pass after revert," and a delete satisfies that as cleanly as a replacement does. We document the rationale inline so cycle 46 doesn't re-propose the same vacuous upgrade.

CONFIDENCE: HIGH

### Q-B — `_augment_manifest.py` / `_augment_rate.py` compat

OPTIONS:
- **Option 1:** Keep old files as 1-line re-export shims (`from kb.lint.augment.manifest import *  # noqa: F401  # cycle-23 L5 compat shim`); tests pass unchanged.
- **Option 2:** Migrate all 6+ test files to import from new package paths in same cycle.

## Analysis

R2 grep found 6 test files importing or monkeypatching the old `kb.lint._augment_manifest` / `kb.lint._augment_rate` paths: `test_backlog_by_file_cycle1.py:157,166`, `test_cycle13_frontmatter_migration.py:459,461`, `test_cycle17_resume.py:19`, `test_cycle9_lint_augment.py:12,14`, `test_v5_kb_lint_signature.py:52`, `test_v5_lint_augment_manifest.py` (entire file), `test_v5_lint_augment_orchestrator.py` (~14 lines), `test_v5_lint_augment_rate.py` (entire file). The "tests pass unchanged" promise in AC16 directly conflicts with the AC11 promise to delete those files. Whichever way we resolve it, the requirements doc is internally inconsistent and must change.

Option 1 (compat shims) preserves the AC16 contract and minimises test churn (≥30 patch-target string updates would be required for Option 2). The downside is that the shims persist as tech debt — `from kb.lint._augment_manifest import Manifest` would keep working, masking the canonical new path. But cycle-23 L5 already established this pattern (3 prior compat shims from cycle 23-24 still exist in `src/kb/`); the explicit `# cycle-23 L5 compat shim` comment marks them for tracking. Cycle 46 or 47 can sweep them in a "remove cycle-23 L5 compat shims" cycle. Option 2 is also riskier per C42-L3: each migrated patch site is a new error surface. Lower blast radius wins → Option 1.

DECIDE: **Option 1** — keep `src/kb/lint/_augment_manifest.py` and `src/kb/lint/_augment_rate.py` as 1-line re-export shims. Each shim file: a docstring explaining the compat purpose + cycle reference, then `from kb.lint.augment.manifest import *  # noqa: F401  # cycle-23 L5 compat shim — cycle 45` (and equivalent for `rate`). Add `__all__` mirroring the canonical module so `import *` is well-defined. AC11 wording AMENDED: instead of "the original files are removed," say "the original files are converted to 1-line re-export shims." AC11 still drops the legacy 213+110 LOC content; the 5-line shim files do not count against the LOC reduction goal.

RATIONALE: AC16's "pass without modification" guarantee outweighs the shim-debt cost. Cycle-23 L5 already normalises this pattern. Lower test-churn → lower regression risk in this batch cycle.

CONFIDENCE: HIGH

### Q-C — M3 LOC cap for `core.py`

OPTIONS:
- **Option 1:** ≤500 LOC with documented justification.
- **Option 2:** ≤450 LOC; move `_save_synthesis` and save-as helpers too.
- **Option 3:** ≤350 LOC; move `kb_query` to `mcp/query.py` (broader scope).
- **Option 4:** ≤300 LOC; move EVERYTHING that isn't FastMCP app + cross-cutting (broadest scope).

## Analysis

Verified facts: `mcp/core.py` is 1149 LOC. R2 Codex computed the residue precisely: moving `kb_ingest` (557→727), `kb_ingest_content` (727→874), `kb_save_source` (874→973), `kb_compile_scan` (973→1041), `kb_compile` (1041→1095), `kb_capture` + `_format_capture_result` (1095→end) leaves ~573 LOC. Including `_validate_file_inputs` / `_validate_filename_slug` validators in the move drops it to ~513 LOC. Achieving ≤300 LOC requires moving `kb_query` (which is ~200 LOC), `_save_synthesis`, save-as validators, and possibly the `_LAZY_MODULES` lazy-loader scaffold. That is a much broader scope than the requirements doc described.

The cycle-45 brainstorm explicitly anticipated this (Q6: "is this realistic given cross-cutting helpers? Plan must size before committing to the cap; if 350 LOC is required, document the deviation"). The orig requirements wording "≤350 with explicit justification" already authorises the deviation. Option 3 (move `kb_query` to a new `mcp/query.py`) is appealing — it would close the cycle-44 brainstorm Q2 question about query placement — but it expands AC scope (additional file, additional re-exports, additional test surface). Option 1 (≤500) is too loose: it doesn't force the helper extraction that's the entire point of the split. Option 2 (≤450 with `_save_synthesis` + save-as helpers moved) hits the sweet spot: residue stays within the cycle-23 L5 "FastMCP app + cross-cutting helpers" scope, validators consolidate into `mcp/ingest.py` (where they belong semantically), and the LOC budget remains tight enough to prevent regression growth.

DECIDE: **Option 2** — `core.py` ≤ 450 LOC after split. AC19 AMENDED to: "core.py retains the FastMCP app instance (or re-export thereof), `_LAZY_MODULES`/`__getattr__` lazy-loader scaffold, `_sanitize_conversation_context`, and helpers genuinely shared by both query and ingest paths. Target ≤450 LOC. Validators (`_validate_file_inputs`, `_validate_filename_slug`, `_validate_save_as_slug`) move with their owning tool — file/filename validators to `ingest.py`; save-as validator stays with `kb_query` in `core.py` because `kb_query` is NOT moved this cycle (cycle 46 candidate)."

RATIONALE: Honest sizing avoids late-cycle scope creep. ≤450 is verifiable, leaves headroom for cross-cutting helpers, and matches the cycle-4-13 split shape (browse / health / quality each are 200-400 LOC).

CONFIDENCE: HIGH

### Q-D — AC29 fate

OPTIONS:
- **Option 1:** DROP AC29 entirely. Document rationale.
- **Option 2:** REDESIGN as a `cache_clear()` test.
- **Option 3:** Add content-hash fallback to cache key (BEHAVIOR CHANGE, REJECT).

## Analysis

Production code at `src/kb/utils/pages.py:60` is `@functools.lru_cache(maxsize=8192) def _load_page_frontmatter_cached(path_str: str, mtime_ns: int)`. The cache key is pure `(path_str, mtime_ns)`. If `os.utime` forces identical mtime_ns on two writes, the cache returns the OLD cached value — not the FRESH content. So the AC29 assertion ("Asserts the FRESH content is returned") would FAIL on the current production code. The only way to make the test pass is to add a content-hash fallback (Option 3, behavior change) — explicitly violating cycle non-goal #1.

Option 2 (cache_clear test) would test a different invariant ("explicit cache_clear flushes stale entries") which is trivially true and provides no real coverage gain. The mtime-resolution caveat in the docstring (`pages.py:78-79`) is a documentation note about FILESYSTEM behavior, not a CONTRACT promise of fresh-content-on-collision. The cycle-16 L2 self-check rule says new behavioral tests MUST fail on production revert — but if there is no production behavior to revert, the rule cannot be satisfied. Therefore: drop AC29 and document the rationale inline so cycle 46 doesn't re-propose it.

The original vacuous test (`test_load_page_frontmatter_docstring_documents_mtime_caveat`) is still deleted (its docstring assertion was the cycle-16 L2 vacuity flag). Net delta: 1 test deleted, 0 added. The C41-L1 vacuity flag is closed by deletion, not replacement.

DECIDE: **Option 1** — DROP AC29. Inside `tests/test_utils_io.py`, delete `test_load_page_frontmatter_docstring_documents_mtime_caveat` (still satisfies the C41-L1 vacuity-removal goal). Add a comment block in the test file explaining "AC29 was dropped in cycle 45 design gate because the production cache key is pure `(path_str, mtime_ns)` by intentional contract; no behavioral test would distinguish the docstring caveat from the actual logic without a behavior change."

RATIONALE: Pure-refactor cycle. Adding content-hash fallback is out of scope. Deletion alone closes the vacuity flag.

CONFIDENCE: HIGH

### Q-E — AC30 fate

OPTIONS:
- **Option 1:** REDESIGN to mock `os.kill` raising `ProcessLookupError`, asserting stale lock is reaped.
- **Option 2:** DROP AC30 entirely.
- **Option 3:** Add `psutil.pid_exists` (BEHAVIOR CHANGE, REJECT).

## Analysis

Production at `src/kb/utils/io.py:412`: `os.kill(stale_pid, 0)` then `except ProcessLookupError` reaps the lock. R2 Codex confirmed `psutil.pid_exists` has zero hits in `src/kb/`. Option 3 (add psutil) is a behavior change — REJECT.

Option 1 (redesign with `os.kill` mock) is achievable AND tests real production logic. Compared to AC29, AC30 has a real behavioral path to test: the `ProcessLookupError → unlink → continue` branch on `io.py:413-416`. A test that:
1. Creates a stale `.lock` file with a fake PID inside.
2. Monkeypatches `os.kill` to raise `ProcessLookupError`.
3. Acquires `file_lock` for the same path.
4. Asserts successful acquisition (stale lock reaped, new lock written with current PID).

…would FAIL if the production reaping logic is reverted to `raise TimeoutError` (or removed entirely), satisfying cycle-16 L2 self-check. This is in-scope: testing existing behavior, no production change. The R2 critique was that AC30 mocked the WRONG symbol; the FIX is "mock the right symbol," not "drop the AC."

DECIDE: **Option 1** — REDESIGN AC30. AMENDED text: "In `tests/test_utils_io.py`, delete the docstring `atomic_*_write` portion of `test_cycle12_io_doc_caveats_are_present` (redundant vs `test_sweep_orphan_tmp_*`). REPLACE the `file_lock` PID-recycling portion with a behavioral test `test_file_lock_reaps_stale_lock_with_dead_pid` that: (1) creates a stale `.lock` file with a fake PID written into it; (2) monkeypatches `os.kill` to raise `ProcessLookupError` for that PID (using `monkeypatch.setattr('kb.utils.io.os.kill', lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))` or a clean wrapper); (3) acquires `file_lock` for the same target path; (4) asserts successful acquisition (stale lock reaped → fresh lock written with current PID); the test must FAIL when the `except ProcessLookupError: lock_path.unlink(...)` branch is mutated to `raise TimeoutError(...)`."

RATIONALE: Real behavior exists at `io.py:412-416`; test it. Deletion would lose coverage of a real cycle-2 reaping path. Cycle-16 L2 self-check is satisfiable.

CONFIDENCE: HIGH

### Q-F — Re-export strategy for `__init__.py`

OPTIONS:
- **Option 1:** Explicit per-symbol re-export `from .submod import sym1, sym2  # noqa: F401  # cycle-23 L5`. Enumerate ALL top-level callables (private `_helper` ones too).
- **Option 2:** `from .submod import *` star imports (ruff-rejected).
- **Option 3:** Hybrid — explicit public + star private.

## Analysis

R2 grep confirms tests import private helpers across modules: `_bounded_edit_distance`, `_slug_for_duplicate`, `_collect_eligible_stubs`, `_propose_urls`, `_relevance_score`, `_post_ingest_quality`, `parse_inline_callouts`, `_CALLOUT_RE`, `_CALLOUT_MARKER_PATTERN`, `_validate_save_as_slug`, `_validate_file_inputs`, `_validate_filename_slug`, `_save_synthesis`, etc. The "at minimum" lists in AC3 / AC12 / AC20 do NOT name these — and the C42-L5 lesson explicitly says re-exports must enumerate every importable symbol or `ruff --fix` will strip them.

Option 2 (star imports) is rejected because (a) C42-L5 specifically warns against implicit re-exports being stripped by ruff; (b) `from .X import *` requires `__all__` definitions in every submodule, which is more total work than explicit re-export. Option 3 (hybrid) is also rejected — it inherits Option 2's downsides without adding clarity. Option 1 forces an exhaustive enumeration upfront, which is exactly what R2 demanded ("Require an explicit old-symbol to new-module map for every callable listed above"). The Step-7 plan must produce that map BEFORE any source code moves.

DECIDE: **Option 1** — explicit per-symbol re-export. AMEND AC2 / AC3 / AC11 / AC12 / AC19 / AC20: replace "at minimum" with "every top-level callable, every private `_helper`-prefixed helper imported by tests, every module-level constant imported or patched by tests." Step 7 (TaskList) must produce a complete old→new symbol map BEFORE any source moves. Step 9 (TDD) must include a parametrised `test_init_reexports_match_legacy_surface` test that for each `__init__.py` asserts `dir(new_pkg)` is a SUPERSET of `dir(legacy_module_snapshot)` (the snapshot is captured by a one-shot helper that imports the legacy file directly).

RATIONALE: C42-L5 warns about ruff stripping; Option 1 is the only non-fragile option. The exhaustive map is one-time work that prevents recurring "AC said minimum, test imported a private helper" failures.

CONFIDENCE: HIGH

### Q-G — Module-level constants propagation

OPTIONS:
- **Option 1:** Cycle-18 L1 dynamic lookup. Submodules read `kb.config.WIKI_DIR` at call time (`def check_X(...): wiki_dir = kb.config.WIKI_DIR`). Test patches of `kb.config.WIKI_DIR` propagate naturally.
- **Option 2:** Re-export constants at package level AND in submodule via `WIKI_DIR = kb.config.WIKI_DIR`; PEP 562 lazy `__getattr__`.
- **Option 3:** Migrate `tests/test_cli.py` patches to target `kb.config.WIKI_DIR` directly (most invasive).

## Analysis

Critical verified fact: `lint/checks.py:14-25` already does `from kb.config import WIKI_DIR, RAW_DIR, ...`. Each function then uses `wiki_dir = wiki_dir or WIKI_DIR` (the imported name in the module's globals). So `monkeypatch.setattr("kb.lint.checks.WIKI_DIR", tmp_path)` rebinds the imported reference IN `kb.lint.checks` only. After the split, each new submodule (`frontmatter.py`, `dead_links.py`, etc.) will have ITS OWN `from kb.config import WIKI_DIR`, and the package-level `kb.lint.checks.WIKI_DIR` patch will NOT propagate to those submodules' globals.

Option 1 (dynamic lookup at call time) is the cycle-18 L1 pattern. Each submodule's lint function changes from `wiki_dir = wiki_dir or WIKI_DIR` to `wiki_dir = wiki_dir or kb.config.WIKI_DIR` (via `from kb import config`). When `tests/test_cli.py` patches `kb.lint.checks.WIKI_DIR`, the patch happens but the submodule reads `kb.config.WIKI_DIR` directly — so the test patch is NO LONGER EFFECTIVE. To preserve test behavior, EITHER (a) tests migrate their patch target to `kb.config.WIKI_DIR` (Option 3, invasive), OR (b) the package-level `__init__.py` rebinds the package-level constant AND submodules read from the package via `from kb.lint import checks` and then `checks.WIKI_DIR`.

The simplest correct approach is a hybrid: the new `kb/lint/checks/__init__.py` re-exports `WIKI_DIR`/`RAW_DIR`/`SOURCE_TYPE_DIRS`/`atomic_text_write`/`resolve_wikilinks` (R2 grep confirms tests patch all five at the package level: `test_cli.py:88-89`, `test_v0916_task01.py:26`, `test_v0911_phase392.py:126`). Each submodule does `from kb.lint import checks as _checks_pkg` and reads `_checks_pkg.WIKI_DIR` at call time. Then `monkeypatch.setattr("kb.lint.checks.WIKI_DIR", tmp_path)` propagates, because submodules look up the value via the package object dynamically.

Wait — there's a subtlety. `from kb.lint import checks as _checks_pkg` loads the package once; subsequent `_checks_pkg.WIKI_DIR` reads use Python's normal attribute lookup, which DOES see runtime patches to `_checks_pkg`. This works. But it does require renaming local `WIKI_DIR` references inside each submodule from bare `WIKI_DIR` to `_checks_pkg.WIKI_DIR` — a search-and-replace risk. The alternative — keeping each submodule's bare `from kb.config import WIKI_DIR` and migrating tests — is also a search-and-replace, but on the test side.

Option 1 (cycle-18 L1 dynamic lookup via `kb.config.WIKI_DIR`) plus migrating test patches to `kb.config.WIKI_DIR` is the cleanest LONG-TERM solution but the MOST INVASIVE for cycle 45. Option 2 (PEP 562 + dynamic lookup via package) preserves test patches BUT requires rewriting all submodule lint functions to read via the package import. Both are real work.

The decision driver: how many test patch sites point at `kb.lint.checks.X`? R2 grep showed 4 (test_cli.py:88-89 for WIKI_DIR/RAW_DIR; test_v0911_phase392.py:126 for resolve_wikilinks; test_v0916_task01.py:26 for atomic_text_write). That's a manageable migration. Migrating the 4 test patches to `kb.config.WIKI_DIR` / `kb.compile.linker.resolve_wikilinks` / `kb.utils.io.atomic_text_write` is low-risk and cleaner than per-submodule package-level lookups.

But — non-goal #5 says "NO renames of tested public functions" and AC8 explicitly requires "those module-level attributes MUST remain accessible at `kb.lint.checks.WIKI_DIR` / `RAW_DIR` after the package split." So we can't migrate tests; we MUST preserve the patch targets. That forces Option 2 (package-level lookup).

DECIDE: **Option 2 (modified)** — package-level re-export + submodule reads via package. New `kb/lint/checks/__init__.py` re-exports `WIKI_DIR`, `RAW_DIR`, `SOURCE_TYPE_DIRS`, `atomic_text_write`, `resolve_wikilinks` at the package level. Each submodule (`frontmatter.py`, `dead_links.py`, etc.) imports `from kb.lint import checks as _checks_pkg` (avoiding a naming collision) and reads `_checks_pkg.WIKI_DIR` at CALL TIME inside each function (NOT at module import). This preserves the four existing patch targets. Tests stay unchanged. Required new test: `test_cycle45_package_patch_propagates_to_submodules` — `monkeypatch.setattr("kb.lint.checks.WIKI_DIR", tmp_dir)`, then call `check_dead_links()` (which lives in `dead_links.py`), assert it scans `tmp_dir`, not the original.

RATIONALE: AC8 requires the patch path to keep working; non-goal #5 forbids test-side rename. Option 2 is the only path that satisfies both. Cycle-23 L5 already uses this pattern for FastMCP tool registration.

CONFIDENCE: MEDIUM (the implementation is mechanical but the cyclic-import risk between `__init__.py` and submodules needs a Step 9 boot-import test).

### Q-H — `atomic_text_write` signature

DECIDE (confirm): `def atomic_text_write(content: str, path: Path | str, *, exclusive: bool = False) -> None`. Preserve existing `(content, path)` order; add `exclusive` as keyword-only. AC25 AMENDED inline.

RATIONALE: 20+ existing positional callers across `src/` and tests use `(content, path)`. Reversing the order is a 100% breakage. Codex R2's "REJECT" is the correct call; the original requirements doc had the signature backwards.

CONFIDENCE: HIGH

### Q-I — capture import strategy

DECIDE (confirm): `import kb.utils.io as io_utils` at top of `src/kb/capture.py`. The replacement for `_exclusive_atomic_write` calls `io_utils.atomic_text_write(content, path, exclusive=True)` (NOT `from kb.utils.io import atomic_text_write` rebinding). This makes `monkeypatch.setattr("kb.utils.io.atomic_text_write", ...)` effective from `capture.py` because attribute lookup goes through the module reference at call time.

RATIONALE: AC27 collapsing dual-site patches to a single site requires the call site to dynamically dispatch through `kb.utils.io`. Module-reference imports satisfy this; `from X import` rebinds do not.

CONFIDENCE: HIGH

### Q-J — `run_augment` location in new `lint/augment/` package

OPTIONS:
- **Option 1:** `lint/augment/orchestrator.py` (new module).
- **Option 2:** `lint/augment/__init__.py`.
- **Option 3:** `lint/augment/persister.py`.

## Analysis

`run_augment` is THE orchestrator — it sequences collector → proposer → fetcher → persister → quality. It is 530 LOC alone (per R2 verification: defined at `augment.py:530`, with `_resolve_raw_dir`, `_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`, `_post_ingest_quality` all under it through line 1189). Putting it in `__init__.py` (Option 2) recreates the exact "second monolith" risk that motivated M2 in the first place. Putting it in `persister.py` (Option 3) is a semantic mismatch — persister handles file writes, not orchestration.

Option 1 (`orchestrator.py`) is the cohesive choice. It matches the cycle-23 L5 split shape and keeps `__init__.py` lean (just re-exports). The R2 review explicitly recommended this: "Add `orchestrator.py` for `run_augment`."

DECIDE: **Option 1** — `lint/augment/orchestrator.py` houses `run_augment`, `_resolve_raw_dir`, `_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`, `_post_ingest_quality`. AC11 AMENDED: file list becomes `__init__.py`, `collector.py`, `proposer.py`, `fetcher.py`, `persister.py`, `quality.py`, `manifest.py`, `rate.py`, `orchestrator.py` (9 files, was 8).

RATIONALE: One responsibility per file; `__init__.py` stays at re-export-only; matches BACKLOG fix shape.

CONFIDENCE: HIGH

### Q-K — Tool registration after M3 split

DECIDE (confirm): `kb/mcp/__init__.py:_register_all_tools()` MUST be amended from `from kb.mcp import browse, core, health, quality` to `from kb.mcp import browse, core, compile, health, ingest, quality`. The existing `__getattr__("mcp")` lazy-loader path is preserved. Add CONDITION (Step 9): `tests/test_cycle23_mcp_boot_lean.py` and `tests/test_v070.py::test_mcp_all_tools_registered` MUST continue to pass; tool count assertion `len(mcp._tool_manager._tools) == 28` (cycle-20 L2 corrected count) MUST hold.

RATIONALE: Without updating the registrar, the new `ingest` and `compile` modules' `@mcp.tool()` decorators won't fire, silently dropping tools. Cycle-23 L5 lazy-registration test pins this contract.

CONFIDENCE: HIGH

### Q-L — AC14 scope

DECIDE (confirm with verified count): All 25 grep-confirmed `kb.lint.augment.call_llm_json` patch sites must be enumerated in the Step 7 plan and migrated atomically with the M2 package conversion. Verified breakdown:
- `tests/test_cycle13_frontmatter_migration.py`: 4 sites (lines 531, 551, 643, 663)
- `tests/test_cycle9_lint_augment.py`: 1 site (line 70)
- `tests/test_v5_lint_augment_orchestrator.py`: ~18 sites (lines 16, 167, 190, 213, 251, 286, 297, 326, 353, 372, 434, 495, 548, 734, 790, 907, 946 — a few may be on follow-up lines; full count via grep)

AC14 AMENDED: replace single-file scope with full enumeration. Step 7 produces a list of (file, line, current_target, new_target) tuples; Step 9 runs them all. The new canonical target is `kb.lint.augment.proposer.call_llm_json` (assuming `call_llm_json` lives in `proposer.py` in the new package — Step 7 to confirm placement; if it's a shared helper used by both `proposer.py` and `quality.py`, its canonical home is whichever submodule actually defines it, not `__init__.py`).

RATIONALE: Per C42-L3, function moves invalidate `monkeypatch.setattr` even when re-exported. Patches that are not migrated will silently no-op against the old `__init__.py` re-export, leaving production unmocked.

CONFIDENCE: HIGH

### Q-M — Lazy accessor for manifest.py / rate.py

OPTIONS:
- **Option 1:** Wrap `MANIFEST_DIR = PROJECT_ROOT / ".data"` in `_get_manifest_dir()` accessor; tests' `monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", ...)` migrates to monkeypatching `_get_manifest_dir` or the equivalent.
- **Option 2:** Keep `MANIFEST_DIR = _get_manifest_dir()` as a module-top assignment that re-evaluates on import; tests' direct attribute patches still work.

## Analysis

Verified facts: `_augment_manifest.py:25` is `MANIFEST_DIR = PROJECT_ROOT / ".data"` (module-top, evaluated once at import). 7 test sites monkeypatch `kb.lint._augment_manifest.MANIFEST_DIR` directly (test_cycle9_lint_augment.py:12, test_cycle13_frontmatter_migration.py:459, test_v5_lint_augment_manifest.py:8/62/87, test_v5_lint_augment_orchestrator.py:393/456/511/562/674/978/1035, test_v5_kb_lint_signature.py:52). Each test rebinds `MANIFEST_DIR` to a tmp path AFTER the module has been imported.

Cycle-19 L2 says module-top file reads should become lazy. The current `MANIFEST_DIR` is a Path object derived from `PROJECT_ROOT`, NOT a disk read — it's a path computation. The actual disk reads happen later inside `Manifest.__init__()`, `Manifest.write()`, etc. So strictly, `MANIFEST_DIR = PROJECT_ROOT / ".data"` does NOT violate cycle-19 L2 — the violation would be `manifest_data = json.loads(open(MANIFEST_DIR / "x.json").read())` at module top, which doesn't exist.

The real issue is reload contamination: if a test does `importlib.reload(kb.config)` to swap `PROJECT_ROOT`, the legacy `MANIFEST_DIR` snapshot in `_augment_manifest` becomes stale. The `_resolve_data_dir(data_dir)` helper at line 38-43 already addresses this by accepting an explicit `data_dir` override at runtime (per the B2 fix). So tests that use the override don't need the module-top patch; tests that use the patch don't go through `_resolve_data_dir`.

Conclusion: cycle-19 L2 strictly does not require a refactor here, and the test patches DO work currently. The brainstorm's tentative "yes, apply lazy accessors" is a pre-emptive conservative call. But adding lazy accessors WHILE preserving the `MANIFEST_DIR` module-attribute (so test patches still work) is achievable: keep `MANIFEST_DIR = PROJECT_ROOT / ".data"` as the module-top default; ALSO add a `_get_manifest_dir()` helper that returns `kb.config.PROJECT_ROOT / ".data"` (dynamic) for use by NEW code. Existing code paths reading `MANIFEST_DIR` directly continue to work. Existing test patches continue to work. Cycle-19 L2 is honored for new code.

DECIDE: **Hybrid.** AC13 AMENDED: "manifest.py and rate.py inside the package preserve the existing `MANIFEST_DIR = PROJECT_ROOT / ".data"` and `RATE_PATH = PROJECT_ROOT / ".data" / "augment_rate.json"` module-top constants AS-IS so that 7 test sites monkeypatching them at the old `kb.lint._augment_manifest.MANIFEST_DIR` / `kb.lint._augment_rate.RATE_PATH` paths (via the cycle-23 L5 compat shims from Q-B) continue to work. Cycle-19 L2 lazy accessors `_get_manifest_dir()` / `_get_rate_path()` are added as helpers but are NOT mandatory for first-cycle wiring; production code may keep reading the module-top constant. The shim files (`_augment_manifest.py`, `_augment_rate.py` per Q-B Option 1) `from kb.lint.augment.manifest import MANIFEST_DIR  # noqa: F401  # cycle-23 L5 compat shim`."

RATIONALE: 7 active test patches must keep working. Cycle-19 L2 is pre-emptive in this case and not required by any reload-failure observed in current main. Add the lazy helpers for FUTURE code, don't break the current contract.

CONFIDENCE: MEDIUM (this softens the brainstorm's earlier "Choice C: lazy load JSON state in manifest.py and rate.py" — but the verification showed the current code does NOT load JSON state at module top, so the lesson is not strictly violated).

### Q-N — T1 threat-model amendment

## Analysis

T1 invariant: "Public import contract preserved (cycle-23 L5)." After Q-G's decision, T1 must verify two distinct contracts: (a) `from kb.lint.checks import X` resolves to the function (or the patched version when tests patch the package level), (b) submodule functions correctly read package-level constants at call time so test patches propagate.

Step-11 verification is a triple of (i) every legacy `from kb.lint.checks import <symbol>` import resolves; (ii) every legacy `monkeypatch.setattr("kb.lint.checks.WIKI_DIR", ...)` (and the 4 sister attrs) takes effect on at least one per-rule submodule's behavior; (iii) the cycle-23 L5 lazy-registration test still passes for `kb.mcp` after M3 split.

DECIDE: T1 AMENDED to require all three sub-checks. New Step 11 test: `test_cycle45_package_constants_propagate_to_submodules` — parametrise over (`WIKI_DIR`, `RAW_DIR`, `SOURCE_TYPE_DIRS`, `atomic_text_write`, `resolve_wikilinks`) × (every per-rule submodule that uses the constant); assert `monkeypatch.setattr("kb.lint.checks.<X>", sentinel)` is observed inside the submodule's call.

RATIONALE: Q-G's chosen strategy (Option 2 modified — package re-export + submodule package-lookup) is cycle-novel; it deserves a dedicated test fold rather than relying on incidental coverage.

CONFIDENCE: HIGH

### Q-O — T2 threat-model amendment

DECIDE: T2 AMENDED. Step 11 verification: enumerate all 25 `kb.lint.augment.call_llm_json` patch sites (Q-L), 2 `kb.lint.augment.run_augment` patch sites (R2 grep), and the dual `tests/test_capture.py` sites (`kb.utils.io.atomic_text_write` + `kb.capture.atomic_text_write` at lines 805-806, 819-820). Each must be migrated to the new canonical module string before the cycle ships. Step 11 also includes a regression grep — `rg "kb.lint.augment.call_llm_json|kb.lint.augment.run_augment|kb.capture.atomic_text_write" tests/` MUST return zero hits after migration (because patches that survived would silently no-op against the new canonical module).

RATIONALE: C42-L3 is the controlling lesson; the lesson explicitly says "Patch sites must be migrated to target the NEW canonical module" and "the implementation plan must grep all current monkeypatch/patch sites BEFORE moving any module-global symbol — three greps (string-form, reference-form via module variable, broader) per cycle-19 L1."

CONFIDENCE: HIGH

### Q-P — T6 threat-model amendment

## Analysis

T6 invariant: "Vacuous-test behavioral coverage (cycle-16 L2 + C40-L3 + C41-L1). New behavioral tests for AC29 (mtime-collision) and AC30 (file_lock PID recycling) MUST exercise the production code path such that a revert of the underlying logic FAILS the test."

Per Q-D, AC29 is DROPPED. Per Q-E, AC30 is REDESIGNED to mock `os.kill`. So T6 reduces to: "The redesigned AC30 test (`test_file_lock_reaps_stale_lock_with_dead_pid`) MUST FAIL when the `except ProcessLookupError: lock_path.unlink(missing_ok=True); attempt_count += 1; continue` branch at `src/kb/utils/io.py:413-416` is mutated to `raise TimeoutError(...)`. Self-check: temporarily replace those 4 lines with `raise TimeoutError("mutated")`, run the test, confirm it fails."

DECIDE: T6 AMENDED to "AC30-only: behavioral test must fail on production revert." AC29 dropped → T6 has no AC29 sub-clause.

RATIONALE: Cycle-16 L2 self-check is satisfiable for AC30 (real production logic exists), unsatisfiable for AC29 (logic doesn't exist). Drop the unsatisfiable half.

CONFIDENCE: HIGH

---

## CONDITIONS (Step 9 must satisfy)

These are binding test/assertion requirements that follow from the decisions above. Each maps to one or more ACs and provides a concrete checkable invariant.

1. **C1 [from Q-F, AC2/AC3/AC11/AC12/AC19/AC20]:** Step 7 produces a complete old-symbol → new-module map for all top-level callables (including private `_helper`-prefixed) and module-level constants importable from the legacy `kb.lint.checks`, `kb.lint.augment`, `kb.lint._augment_manifest`, `kb.lint._augment_rate`, `kb.mcp.core` modules. Step 9 adds `tests/test_cycle45_init_reexports_match_legacy_surface.py` parametrised over (legacy_module, new_pkg) pairs that asserts `dir(new_pkg)` ⊇ `dir(legacy_module_snapshot)` for the public+private surface.

2. **C2 [from Q-G, AC8 + new]:** Step 9 adds `tests/test_cycle45_package_constants_propagate_to_submodules.py` — for each pair (`kb.lint.checks.<X>`, submodule-function-using-X) where X ∈ {WIKI_DIR, RAW_DIR, SOURCE_TYPE_DIRS, atomic_text_write, resolve_wikilinks}, a parametrised test patches `kb.lint.checks.<X>` and asserts the submodule's behavior reflects the patch.

3. **C3 [from Q-K, T4]:** Step 9 verifies `len(mcp._tool_manager._tools) == 28` after `from kb.mcp import mcp`. The existing `tests/test_cycle9_mcp_app.py::test_instructions_tool_names_sorted_within_groups` and `tests/test_v070.py::test_mcp_all_tools_registered` MUST pass without modification. Adding `tests/test_cycle45_mcp_split_tool_registration.py` is OPTIONAL but recommended — explicit assertion that the new `compile`/`ingest` modules' `@mcp.tool()` decorators registered.

4. **C4 [from Q-H/Q-I/AC25/AC26/AC27]:** Step 9 verifies (a) `atomic_text_write(content, path)` (positional, no `exclusive`) preserves crash-atomicity AND OneDrive-tmp-cleanup contract per cycle-15 L1; (b) `atomic_text_write(content, path, exclusive=True)` raises `FileExistsError` on conflict AND on success leaves the file with the written content (no half-written reservation); (c) `tests/test_capture.py` collapses dual-site patch to single-site `monkeypatch.setattr("kb.utils.io.atomic_text_write", ...)` and the test still drives the `_exclusive_atomic_write` cleanup-on-failure code path.

5. **C5 [from Q-E, AC30]:** Step 9 adds `test_file_lock_reaps_stale_lock_with_dead_pid` mocking `os.kill` to raise `ProcessLookupError`. Self-check: `git stash` the production reaping branch, run test, confirm FAIL; restore, confirm PASS.

6. **C6 [from Q-L, AC14]:** Step 7 plan enumerates ALL 25+ `kb.lint.augment.call_llm_json` patch sites (file:line:current_target) and the canonical new target string. Step 11 grep `rg "kb.lint.augment.call_llm_json" tests/` returns zero hits (all migrated to canonical submodule).

7. **C7 [from Q-J/AC11]:** `src/kb/lint/augment/orchestrator.py` exists and contains `run_augment`, `_resolve_raw_dir`, `_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`, `_post_ingest_quality`. The package `__init__.py` is ≤30 LOC (re-exports only, NOT orchestration logic).

8. **C8 [from Q-B/AC11/AC16]:** `src/kb/lint/_augment_manifest.py` and `src/kb/lint/_augment_rate.py` exist as ≤5 LOC re-export shims with explicit `# cycle-23 L5 compat shim — cycle 45` comments. Tests at `test_backlog_by_file_cycle1.py:157,166`, `test_cycle9_lint_augment.py:12,14`, `test_cycle13_frontmatter_migration.py:459,461`, `test_cycle17_resume.py:19`, `test_v5_kb_lint_signature.py:52`, `test_v5_lint_augment_manifest.py`, `test_v5_lint_augment_orchestrator.py` (~14 lines), `test_v5_lint_augment_rate.py` PASS without modification.

9. **C9 [from Q-A/Q-D/AC29]:** `tests/test_utils_io.py::test_load_page_frontmatter_docstring_documents_mtime_caveat` is DELETED. NO replacement test is added. A comment block in the test file explains the AC29 deletion rationale (pure-mtime cache key is intentional contract; behavior change out of cycle scope).

10. **C10 [from Q-A/Q-E/AC30]:** `tests/test_utils_io.py::test_cycle12_io_doc_caveats_are_present` has its `atomic_*_write` portion DELETED (redundant). Its `file_lock` PID portion REPLACED with `test_file_lock_reaps_stale_lock_with_dead_pid` per C5.

11. **C11 [from Q-C/AC19]:** `src/kb/mcp/core.py` ≤450 LOC after split. `_save_synthesis`, save-as helpers, `kb_query`, `_validate_save_as_slug` STAY in core.py (kb_query is not moved this cycle). `kb_ingest`, `kb_ingest_content`, `kb_save_source`, `kb_capture`, `_format_capture_result`, `_validate_file_inputs`, `_validate_filename_slug` MOVE to `mcp/ingest.py`. `kb_compile`, `kb_compile_scan` MOVE to `mcp/compile.py`. The `_LAZY_MODULES` dict and `__getattr__` lazy-loader scaffold STAY in core.py.

12. **C12 [from Q-N/T1, AC10]:** `tests/test_lint_runner.py` enumeration order MUST be preserved. Step 9 runs `python -m pytest tests/test_lint_runner.py -x` and asserts `runner.run_all_checks()` produces the same `checks_run` ordered list as on `main` baseline.

13. **C13 [from AC21, R2 R-21]:** AC21 AMENDED: drop the "list input / over-limit / passthrough" wording. Replace with "fold `tests/test_cycle12_sanitize_context.py` (the use_api parametrised + spy-on-sanitiser tests) verbatim into `tests/test_mcp_core.py`; delete the source file; assert at least 2 fold tests collected via `pytest tests/test_mcp_core.py -k 'sanitize or sanitiser'`." Per cycle-17 L3, if the dedup detects existing duplicates, drop redundants with inline `DESIGN-AMEND` note.

14. **C14 [from new, T-prereg]:** Before any source moves in Step 9, Step 7 emits a Step-9-blocking `step-7-symbol-map.md` artifact under `D:/Projects/llm-wiki-flywheel-c45/.data/cycle-45/` listing every (legacy_module:line, symbol, new_module:expected_line) for the M1+M2+M3 splits. Step 8 review (primary session or Codex) inspects this artifact for completeness against the C1 surface enumeration.

15. **C15 [from Q-O/T2]:** Step 11 regression grep `rg "kb.lint.augment.(call_llm_json|run_augment)|kb.capture.atomic_text_write" tests/` returns zero hits.

---

## FINAL DECIDED DESIGN

### M1 — `lint/checks.py` split (10 ACs)

- **AC1** APPROVE — `src/kb/lint/checks/` package created; flat file removed.
- **AC2** AMENDED — file list expanded to: `__init__.py`, `frontmatter.py`, `dead_links.py`, `orphan.py`, `cycles.py`, `staleness.py`, `duplicate_slug.py`, `consistency.py`, `inline_callouts.py`, `stub_pages.py` (separate module for `check_stub_pages`, `_compose_page_topics`, `_effective_max_days`). The "at minimum" clause becomes "every top-level callable, every private helper imported by tests, every module-level constant imported or patched by tests, per the C1 symbol map."
- **AC3** AMENDED — re-export ALL of: `check_source_coverage`, `check_dead_links`, `check_orphan_pages`, `check_cycles`, `check_staleness`, `check_frontmatter_staleness`, `check_status_mature_stale`, `check_authored_by_drift`, `check_frontmatter`, `check_stub_pages`, `check_duplicate_slugs`, `check_inline_callouts`, `parse_inline_callouts`, `fix_dead_links`, `_bounded_edit_distance`, `_slug_for_duplicate`, `_compose_page_topics`, `_effective_max_days`, `_CALLOUT_RE`, `_CALLOUT_MARKER_PATTERN`, `_INDEX_FILES`, `_STATUS_MATURE_STALE_DAYS`, `_EVIDENCE_TRAIL_ANCHOR`, `_ACTION_INGEST_RE`, plus constants `WIKI_DIR`, `RAW_DIR`, `SOURCE_TYPE_DIRS`, `atomic_text_write`, `resolve_wikilinks`. All re-exports use `# noqa: F401  # re-exported for backward compat (cycle-23 L5)`.
- **AC4** APPROVE.
- **AC5** APPROVE.
- **AC6** APPROVE.
- **AC7** AMENDED — re-export must include `_bounded_edit_distance`, `_slug_for_duplicate`, `_CALLOUT_RE`, `_CALLOUT_MARKER_PATTERN`, `parse_inline_callouts` (private helpers imported by `test_cycle16_*` per R2 grep).
- **AC8** AMENDED — combine with C2: not only is `kb.lint.checks.WIKI_DIR` patchable, but the patch propagates to per-rule submodules via the package-lookup pattern from Q-G.
- **AC9** AMENDED — also re-export `atomic_text_write` and `resolve_wikilinks` at the package level (test_v0916_task01.py:26 patches `kb.lint.checks.atomic_text_write`; test_v0911_phase392.py:126 patches `kb.lint.checks.resolve_wikilinks`).
- **AC10** AMENDED — preserve `runner.run_all_checks` ordering exactly (C12).

### M2 — `lint/augment.py` package conversion (8 ACs)

- **AC11** AMENDED — `lint/augment/` package files: `__init__.py`, `orchestrator.py` (per Q-J), `collector.py`, `proposer.py`, `fetcher.py`, `persister.py`, `quality.py`, `manifest.py`, `rate.py` (9 files). `_augment_manifest.py` and `_augment_rate.py` BECOME 1-line re-export shims (per Q-B Option 1). Original `augment.py` REMOVED.
- **AC12** AMENDED — re-export every callable + import attr per C1: `run_augment`, `save_page_frontmatter`, `_build_proposer_prompt`, `_format_proposals_md`, `_collect_eligible_stubs`, `_propose_urls`, `_wikipedia_fallback`, `_relevance_score`, `_load_purpose_text`, `_parse_proposals_md`, `_count_final_stub_outcomes`, `_save_raw_file`, `_resolve_raw_dir`, `_record_verdict_gap_callout`, `_mark_page_augmented`, `_record_attempt`, `_post_ingest_quality`, `call_llm_json`. Each line `# noqa: F401  # re-exported for backward compat (cycle-23 L5)`.
- **AC13** AMENDED — `manifest.py` and `rate.py` preserve module-top `MANIFEST_DIR = PROJECT_ROOT / ".data"` and `RATE_PATH = PROJECT_ROOT / ".data" / "augment_rate.json"` to keep 7 active test patches working (per Q-M). Optional `_get_manifest_dir()` / `_get_rate_path()` lazy helpers may be added for future code; no production code needs to migrate this cycle.
- **AC14** AMENDED (per Q-L) — full enumeration of all ~25 patch sites; migrate to canonical submodule.
- **AC15** APPROVE.
- **AC16** APPROVE — works because of Q-B compat shims.
- **AC17** APPROVE.
- **AC18** APPROVE.

### M3 — `mcp/core.py` split (6 ACs)

- **AC19** AMENDED — LOC cap ≤450 (per Q-C). `kb_query` stays in core.py for cycle 45 (cycle 46 candidate to extract to `mcp/query.py`). Validators move with their owning tools.
- **AC20** AMENDED — re-export every test-imported symbol per C1: `kb_query`, `kb_ingest`, `kb_ingest_content`, `kb_save_source`, `kb_capture`, `kb_compile_scan`, `kb_compile`, `_sanitize_conversation_context`, `_validate_file_inputs`, `_validate_filename_slug`, `_validate_save_as_slug`, `_save_synthesis`, `_format_capture_result`, plus constants `PROJECT_ROOT`, `RAW_DIR`, `SOURCE_TYPE_DIRS`, `atomic_text_write`, `_LAZY_MODULES`, `__getattr__`, `__dir__`.
- **AC21** AMENDED (per C13) — verbatim fold of cycle-12 sanitize_context tests; drop "list input / over-limit" wording.
- **AC22** APPROVE.
- **AC23** AMENDED — `kb/mcp/__init__.py:_register_all_tools()` updated to `from kb.mcp import browse, core, compile, health, ingest, quality` (per Q-K).
- **AC24** AMENDED — `_LAZY_MODULES` and `__getattr__`/`__dir__` preserved in core (per AC20 amendment).

### M4 — `atomic_text_write` consolidation (3 ACs)

- **AC25** AMENDED — signature `def atomic_text_write(content: str, path: Path | str, *, exclusive: bool = False) -> None` (per Q-H). Both contracts (crash-atomicity for `exclusive=False`; O_EXCL for `exclusive=True`) preserved per cycle-15 L1.
- **AC26** AMENDED — `capture.py` uses `import kb.utils.io as io_utils` then `io_utils.atomic_text_write(..., exclusive=True)` (per Q-I).
- **AC27** AMENDED — single-site patch via `monkeypatch.setattr("kb.utils.io.atomic_text_write", boom)`. Capture's call site dispatches through the module reference, so the patch intercepts.

### Test folds + vacuity (3 ACs)

- **AC21** see M3 above.
- **AC28** APPROVE — delete `test_graph_builder_documents_case_sensitivity_caveat`.
- **AC29** DROPPED (per Q-D). Original vacuous test deleted; no replacement.
- **AC30** AMENDED (per Q-E) — atomic_*_write portion deleted; PID-recycling portion replaced with `test_file_lock_reaps_stale_lock_with_dead_pid` mocking `os.kill`.

### New ACs

- **AC31 (NEW, from Q-B):** `src/kb/lint/_augment_manifest.py` and `src/kb/lint/_augment_rate.py` exist as ≤5-LOC re-export shims with explicit `# cycle-23 L5 compat shim — cycle 45` comments. Verified via `wc -l` and `grep "cycle-23 L5 compat shim"`.
- **AC32 (NEW, from C1/C14):** Step 7 emits `step-7-symbol-map.md` listing every legacy → new symbol mapping for the M1+M2+M3 splits. Step 8 review verifies completeness.
- **AC33 (NEW, from Q-G/C2):** `tests/test_cycle45_package_constants_propagate_to_submodules.py` parametrises over (constant, submodule) pairs and verifies `monkeypatch.setattr("kb.lint.checks.<X>", sentinel)` is observed inside the submodule's behavior.
- **AC34 (NEW, from C12):** `tests/test_lint_runner.py` enumeration order is bit-identical to baseline. Step 9 captures `runner.run_all_checks()` `checks_run` list on baseline before splits and asserts identity post-split.

Final AC count: 28 from original (30 − AC29 − AC30) + 4 new (AC31-AC34) = **32 ACs** to be enumerated in Step 7's TaskList.

---

## OPEN ISSUES

None. All Q-A through Q-P resolved autonomously.
