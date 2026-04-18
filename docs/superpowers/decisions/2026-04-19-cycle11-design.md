# Cycle 11 — Final Design (Step 5 decision gate)

**Date:** 2026-04-19
**Decision-gate evaluator:** Opus 4.7 (1M ctx)
**Inputs:** requirements.md (14 ACs), brainstorm.md (Approach C), threat-model.md (T1-T10), design-eval-R1, design-eval-R2
**Conventions:** batch-by-file commits, behavioural tests exercising production path, no `inspect.getsource` proxies, fail-fast over permissive coerce, match existing `_coerce_str_field` policy

## Analysis

I read the cycle-11 inputs end-to-end plus `CLAUDE.md`, then grep-verified the specific facts both design evals called out. The grep-verifications confirmed:

- `src/kb/compile/compiler.py:242-243` DOES have function-local `from kb.graph.builder import page_id as get_page_id` and `from kb.graph.builder import scan_wiki_pages` inside `detect_source_drift` — the AC5 "5 callers" count is wrong by one.
- `tests/` has 3 live imports of `_page_id` from `kb.utils.pages` (`test_v0915_task01.py:344` + `:352`, `test_v0914_phase395.py:732`). Deleting `_page_id` without migrating or aliasing breaks the suite.
- Current `_coerce_str_field` at `src/kb/ingest/pipeline.py:72-79` is **fail-fast** — returns `""` for None, returns str unchanged, **raises ValueError** on any other type. AC3 as written (permissive: `int→str(int)`, `list→comma-join`, `bool→str(bool)`) **contradicts production code**.
- `tmp_project` fixture in `tests/conftest.py:61-71` creates wiki+raw subdirs and `log.md` only — it does NOT create `wiki/index.md` or `wiki/_sources.md`. The current `tests/test_ingest.py::test_ingest_source` writes canonical frontmatter into both files before calling `ingest_source` and reads them back after.
- `_extract_entity_context` in `src/kb/ingest/pipeline.py:439-468` has two unlisted `.get()` sites with string-consuming callees: `val = extraction.get(field)` followed by `val.lower()` at line 450 (for `core_argument`, `abstract`, `description`, `problem_solved`). Today these four fields ARE covered by `_pre_validate_extraction` (`_SUMMARY_STRING_FIELDS` at line 64-69), so the unchecked `.lower()` is only reachable if the validator is bypassed — but AC1 should not leave a secondary read site dependent on validator parity.
- `kb.mcp.core.kb_ingest` and `kb_ingest_content` both reject unknown source types BEFORE `ingest_source` runs (lines 299-301 and 541-544): `source_type not in SOURCE_TYPE_DIRS` returns `"Error: Unknown source_type '...'"`. Since `SOURCE_TYPE_DIRS` does NOT contain `comparison`/`synthesis`, the MCP layer already rejects — but with a generic "Unknown" message rather than naming `kb_create_page`. CLI uses `click.Choice(SOURCE_TYPE_DIRS.keys())` so `kb ingest --type comparison` errors at argument parse.

Given these facts, the design eval R1 (3 blocking conditions) and R2 (4 `PLAN-AMENDS-DESIGN` amendments plus 10+ edge cases) converge on a consistent picture: the requirements are directionally sound, but several ACs need concrete amendments before a Step 7 plan can consume them. In particular, AC3 must be brought into line with the live `_coerce_str_field` policy (fail-fast, not permissive), AC5 must expand from 5 to 6 caller modules, AC4 must handle the 3 `_page_id` test callers, AC7 must use a mechanism that actually exercises CLI callback function-local imports (because `--help` does not run callbacks), AC8 must use a subprocess that sets `sys.argv` BEFORE importing `kb.cli` (in-process post-import tests are vacuous once pytest has already loaded `kb.config`), AC12 must either enhance `tmp_project` or retain explicit index/source file writes, and AC13 must keep the write-count instrumentation as the primary signal (content equality cannot distinguish 1-write from 2-writes of the same value). On all open questions the project principle (fail-fast over permissive coerce; behavioural tests over signature-only; lowest-blast-radius change) points in one direction, so I am resolving each autonomously without escalation.

## VERDICT

APPROVE-WITH-AMENDMENTS

The 14-AC shape and the Approach-C sequencing are approved. Ten concrete amendments (one per Q below) are required before Step 7 plan writes the execution checklist. No work blocks on external input.

## DECISIONS

### Q1 — AC3 policy: fail-fast vs permissive coerce
OPTIONS: (a) keep current fail-fast `ValueError` on non-str; rewrite AC3 test to assert raises. (b) switch to permissive coerce per requirements doc; update `_pre_validate_extraction` contract.

ARGUE: The project's stated operating principle is "prefer fail-fast over permissive coercion" (confirmed in the task prompt and in the broader `CLAUDE.md` convention "Distinguish stated facts from inferences"). The live production helper at `src/kb/ingest/pipeline.py:72-79` implements option (a): returns `""` for None, returns str unchanged, raises `ValueError` on anything else. AC3 as written in the requirements document contradicts this — it describes permissive coercion (`int → str(int)`, `list → comma-join`, `bool → str(bool)`). Adopting (b) would require rewriting `_coerce_str_field`, migrating the existing 8-field pre-validate pass to tolerate those inputs, and reopening the cycle-10 AC13a/b reasoning that explicitly chose fail-fast. It also broadens the attacker-controlled write surface: a caller passing `title=["harmless", "<script>"]` would now get comma-joined into the wiki, whereas today it raises cleanly at the boundary (threat model T1 concern in R2's "Integration/security" section).

The cost of option (a) is a 3-line edit to the AC3 acceptance text, swapping the permissive examples for fail-fast assertions. The cost of option (b) is a re-evaluation of the full ingest-extraction security model, a rewrite of `_coerce_str_field`, a migration of AC1's 6 call sites to handle mixed list/str, and re-opening cycle-10 closure. Option (a) is strictly lower blast radius, matches the "lower blast radius wins" bias, and aligns with the existing code.

DECIDE: (a) keep fail-fast. AC3 test asserts `pytest.raises(ValueError)` for `int`, `list`, `bool`, `dict` and assert `""` for None, assert identity for str.
RATIONALE: Matches live policy; preserves fail-closed semantics at the ingest boundary; avoids broadening the attacker write surface.
CONFIDENCE: HIGH

### Q2 — AC5 scope: 5 callers or 6?
OPTIONS: (a) add `src/kb/compile/compiler.py` to the cluster so 6 caller modules migrate atomically. (b) keep as 5, justify `compile/compiler.py` as out-of-scope same-class miss.

ARGUE: `grep -n "from kb.graph.builder" src/kb/compile/compiler.py` returns two hits inside `detect_source_drift`: line 242 `from kb.graph.builder import page_id as get_page_id` and line 243 `from kb.graph.builder import scan_wiki_pages`. These are function-local imports (to avoid import-cycle at module load), but they are semantically identical to the 5 top-of-module imports listed in AC5. Leaving them behind means the internal migration is incomplete and any test that patches `kb.graph.builder.page_id` behaves differently for compiler.py than for the 5 migrated modules. This is precisely the "same-class completeness" RedFlag pattern from cycle 7/8 (`_validate_notes@kb_save_lint_verdict` case) — missing one site of the same class produces a latent drift bug.

Counter: one could argue function-local imports don't block the migration because the re-export shim preserves them, and deferring compiler.py reduces the atomic-cluster size. But the re-export shim is explicitly back-compat for tests pinning the old location — INTERNAL callers should migrate in the same pass so we don't ship a half-migrated state where `graph.builder.page_id` is a re-export everywhere except inside compiler.py.

DECIDE: (a) include `compile/compiler.py` in the atomic cluster — migrate to 6 caller modules.
RATIONALE: Same-class completeness per cycle-7/8 RedFlag; preserves function-local import placement inside `detect_source_drift` (do not promote to top-of-module — import-cycle risk acknowledged in R1 Q2); atomic cluster size grows by 1 file but rationale already documents multi-file-as-cluster.
CONFIDENCE: HIGH

### Q3 — AC4 `_page_id` disposition given existing test imports
OPTIONS: (a) migrate 3 test-import sites to use `page_id` in the same atomic cluster commit, then delete `_page_id`. (b) keep `_page_id = page_id` as a deprecated alias; delete after a grace cycle. (c) leave `_page_id` + `page_id` as separate but identical (no migration of tests).

ARGUE: Three test files import `_page_id` today: `tests/test_v0915_task01.py:344`, `:352`, and `tests/test_v0914_phase395.py:732`. Option (c) violates same-class completeness — two functions with identical semantics but different names guarantee drift. Option (a) cleanly consolidates but churns 3 test files in the same commit that does the source relocation, making the blast radius larger and mixing test migration with source migration. Option (b) is strictly lower blast radius: add `_page_id = page_id` at the end of `kb.utils.pages`, keep tests working, delete the alias one cycle from now. The aliasing line is a single statement, costs zero semantic drift (identity equality), and lets us land a pure source migration in cycle 11.

However, option (a) has the benefit of "delete the dead symbol now, don't defer cleanup." Design eval R1 explicitly recommends option (b) as "lowest blast radius"; R2 lists option (a) as acceptable only if tests are migrated in the same atomic commit. Given the batch-by-file convention (R1/R2 both note this) and the "reversible > irreversible" bias, a deprecated alias is reversible (delete any time) while a test-file churn in the same atomic commit is irreversible after merge.

DECIDE: (b) keep `_page_id = page_id` as a module-level alias with a `# noqa: N816` comment + docstring "Deprecated — use `page_id`. Scheduled for removal cycle 12."
RATIONALE: Lowest blast radius; preserves existing 3 test imports; reversible at any future cycle; aligns with R1 Decision 2b recommendation and R2's alias-preferred guidance. Follow-up cycle 12 deletes the alias + migrates the 3 tests as a focused single-commit change.
CONFIDENCE: HIGH

### Q4 — AC7 strategy: subprocess smoke test what exactly?
OPTIONS: (a) `click.testing.CliRunner` to invoke each command with a stubbed deep implementation, ensuring function-local imports execute. (b) subprocess `python -m kb.cli <cmd> --nonexistent-arg` — Click callback still doesn't run. (c) subprocess with a MINIMAL valid invocation per command (e.g. `kb ingest /nonexistent-file --type article` — command callback runs but fails fast). (d) split: CliRunner in-process to exercise callbacks with stubbed deep functions.

ARGUE: R2's E8 finding is decisive: `python -m kb.cli <cmd> --help` does NOT execute the callback function, so function-local imports inside each callback are never exercised. The R1-original AC7 formulation (`--help`) fails to meet the stated intent. Option (a) directly executes the callback via `CliRunner.invoke(cli, ["ingest", "x", "--type", "article"])` with heavy paths monkeypatched (`ingest_source` → no-op; `compile_wiki` → no-op; `query_wiki` → returns canned dict; `run_all_checks` → empty list; `generate_evolution_report` → canned; `mcp_main` → no-op). This guarantees the function-local imports resolve at test time. Option (c) via subprocess is slower (6x `subprocess.run` boots the interpreter 6 times, loads torch optional paths, etc.) and requires fragile "fails fast" timing. Option (d) is the same as (a) with extra complexity.

Security/hygiene: `CliRunner` runs in-process, which means the `kb.config` import already happened via pytest's own import chain. That's fine for AC7 (we're testing callback imports, not module-load imports). AC8 separately tests the `--version` short-circuit via subprocess.

DECIDE: (a) `click.testing.CliRunner` + monkeypatch the deep workers (`ingest_source`, `compile_wiki`, `query_wiki`, `run_all_checks`, `generate_evolution_report`, `main` from `kb.mcp_server`) to no-op stubs. Assert `result.exit_code == 0` AND no `ImportError`/`ModuleNotFoundError` in the exception trace for each of the 6 commands (`ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`).
RATIONALE: Matches the stated intent (exercise function-local imports); fastest and most reliable; no subprocess-env-hygiene concerns; cleanly separates from AC8's `--version` test.
CONFIDENCE: HIGH

### Q5 — AC8 strategy: how to pin `--version` short-circuit against broken config
OPTIONS: (a) `python -c "import sys; sys.argv=['kb.cli','--version']; import kb.cli; assert 'kb.config' not in sys.modules"` — clean subprocess. (b) monkeypatch-based in-process test with `sys.modules["kb.config"] = None` before import (brittle per R2). (c) stub `kb/config.py` via `PYTHONPATH` (brittle per R2 — either shadows whole kb package or doesn't resolve). (d) two-part: option (a) PLUS a fresh subprocess with `KB_CONFIG_BROKEN=1` env triggering a poisoned config file at test-controlled path.

ARGUE: R2's E9 finding is decisive: a `PYTHONPATH` directory containing only `kb/config.py` either fails to shadow the regular package (because `kb/__init__.py` in the real install takes precedence) or shadows the whole kb package (breaking `kb.cli` resolution). Option (c) is thus unreliable. Option (b) is vacuous because pytest has already loaded `kb.config` before the test runs — `sys.modules["kb.config"] = None` only affects re-imports, not the already-bound `kb.cli.kb.config` reference. Option (a) is behavioral and subprocess-clean: fresh interpreter, fresh `sys.modules`, sets `sys.argv[1] = "--version"` BEFORE importing `kb.cli`, then asserts `kb.config` is absent from `sys.modules`. This directly verifies the cycle-7 AC30 contract ("version short-circuit runs before kb.config import").

Option (d) adds a second check via a poisoned-config subprocess but doubles the test's complexity and fragility. Option (a) alone is sufficient: if `kb.config` is NOT imported, then a broken `kb.config` cannot affect `--version`. That's a strictly stronger property than "broken config still exits 0" — it's "config is never even touched." R1 Decision 3b picks option (a); R2 amends-design picks option (a); I concur.

DECIDE: (a) — subprocess test via `python -c "..."` with `sys.argv` set before `import kb.cli`, assert exit 0 + `'kb.config' not in sys.modules` + stdout contains `kb, version`. Parametrize on `["--version", "-V"]` per R1 non-blocking item 5.
RATIONALE: Directly behavioral; avoids brittle stub layouts; strictly stronger than "broken-config-still-works" because proves config is never imported; aligns with R1 + R2 consensus.
CONFIDENCE: HIGH

### Q6 — AC12 `tmp_project` fixture gap: enhance fixture or keep partial manual scaffold
OPTIONS: (a) enhance `tmp_project` to create `wiki/index.md` + `wiki/_sources.md` with canonical frontmatter. (b) keep `tmp_project` minimal; retain explicit index.md + _sources.md writes in the test, remove only the subdir-creation block. (c) introduce a NEW fixture `tmp_project_with_index_files` to avoid touching `tmp_project`.

ARGUE: R2's E11 finding is decisive: `tmp_project` today creates wiki+raw subdirs and `log.md` only; it does NOT create `wiki/index.md` or `wiki/_sources.md`. The current `test_ingest_source` writes canonical frontmatter into both files before calling `ingest_source` and reads them back after (assertions at lines 157-161 of test_ingest.py). A straight replacement with `tmp_project` would either (i) fail because the files don't exist (ingest_source writes into a missing directory? or creates from scratch?) or (ii) silently stop testing the index/source-map update behavior. Option (a) enhances the fixture once, benefits 6+ other `test_ingest.py` tests that manually scaffold the same files (R1 scope-check flagged these as cycle-12 candidates), and is strictly additive — no existing test that uses `tmp_project` today expects those files to be absent. Option (b) leaves scaffolding duplicated; option (c) proliferates fixtures unnecessarily.

Blast radius check: enhancing `tmp_project` is a conftest.py edit in a separate commit (batch-by-file). It touches shared fixture code, but the addition is strictly additive (two new files created) and monotonic (any test previously expecting those files to be absent would have failed — none do, because no test asserts their absence).

DECIDE: (a) enhance `tmp_project` to also create `wiki/index.md` (with `# Wiki Index\n\n`) and `wiki/_sources.md` (with `# Sources Map\n\n`). Do this as a **separate commit** from the `test_ingest.py` scaffolding-cleanup commit, so fixture enhancement is reviewed on its own. Update AC12 to note the fixture enhancement is a prerequisite commit.
RATIONALE: Makes the fixture match its documented intent; reduces future scaffolding duplication (dividend for cycle-12 AC12 siblings); strictly additive; separate commit preserves batch-by-file reviewability.
CONFIDENCE: HIGH

### Q7 — AC13 manifest-content assertion adequacy
OPTIONS: (a) keep existing `monkeypatch.setattr(..., save_manifest, ...)` counter AND add manifest-content-stability final-state assertion (strictly additive). (b) replace counter with manifest-content-stability + explicit call-count via `atomic_json_write` spy on the manifest path. (c) instrument `os.stat(mtime_ns)` or write-inode count for file-system-level write coarse-counting.

ARGUE: R2's E13 finding is decisive: "loading the manifest before/after cannot distinguish a single write from a double write of the same key/value. It proves final state, not write cardinality." A pure content-equality assertion PASSES when save_manifest is called twice with identical data (which is exactly the bug we're guarding against — double-write). So the counter is load-bearing for the "does not double-write" contract. The counter is signature-sensitive (rename `save_manifest` → silent pass), which is why AC13 was written in the first place.

The right design: keep BOTH. The counter catches the double-write. The content-stability assertion is strictly additive — it catches a DIFFERENT regression (a refactor that writes the manifest once but with wrong/incomplete data). Option (b) replaces one with the other, losing coverage. Option (c) uses mtime which R2's performance section flags as flaky on Windows and CI filesystems.

To mitigate the signature-only risk of the counter (the `inspect.getsource` RedFlag pattern), one could additionally spy on `atomic_json_write` with `monkeypatch.setattr("kb.utils.atomic.atomic_json_write", spy)` filtered to the manifest path. But that's a second counter; the first counter already does the job, and if `save_manifest` is renamed the test WILL break (not silently pass) because `compiler_mod.save_manifest` as an attribute lookup will raise AttributeError at line 231 (`real_save = compiler_mod.save_manifest`). That's actually behavioural, not signature-only — the monkeypatch binds to the live module attribute and gets called when `compile_wiki` calls its local `save_manifest` (which is a top-of-module import, so the monkeypatch DOES reach it).

DECIDE: (a) keep the existing counter, additively assert manifest-content-stability after second `compile_wiki` run.
RATIONALE: Counter catches write-cardinality; content assertion catches data-integrity; strictly additive. The cited "signature-only" concern is partially mitigated by the fact that `monkeypatch.setattr(compiler_mod, "save_manifest", ...)` does reach the call site when `save_manifest` is imported at module top — but adding the content assertion provides a second independent failure mode.
CONFIDENCE: HIGH

### Q8 — AC1 scope: include `_extract_entity_context` or not?
OPTIONS: (a) add `_extract_entity_context` to AC1's migration list (same-class completeness per cycle-7/8 Red Flag). (b) keep AC1 focused on the 6 sites already listed; defer `_extract_entity_context` to a follow-up cycle.

ARGUE: R2's E1 finding identifies two unlisted `.get()` sites in `_extract_entity_context`: `val = extraction.get(field)` followed by `val.lower()` at line 450 (for `core_argument`, `abstract`, `description`, `problem_solved`). These four fields are all in `_SUMMARY_STRING_FIELDS` (line 64-69), which `_pre_validate_extraction` already validates at the boundary. So today, any non-str value for those four fields raises `ValueError` at the pre-validate pass BEFORE reaching `_extract_entity_context`. The secondary `val.lower()` is thus unreachable in production — but that's conditional on validator parity with `_extract_entity_context`'s field list.

The case for (a): same-class completeness. If a future refactor adds a field to `_extract_entity_context` but forgets to add it to `_SUMMARY_STRING_FIELDS`, the `val.lower()` becomes a reachable AttributeError path. Migrating the call sites to use `_coerce_str_field` is strictly additive (each `val = extraction.get(field)` becomes `val = _coerce_str_field(extraction, field)`) and does NOT change reachability today (validator still blocks non-str at the boundary). The cost is 4 additional lines changed in the same commit as the other 6 sites.

The case for (b): scope discipline. Requirements specify "6 sites", bringing the count to ~10+ grows the blast radius. But the 4 new sites are in the same file, same function class (str-consuming `.get()`), and the cleanup is trivial.

DECIDE: (a) include `_extract_entity_context`'s 4 string-field reads in AC1's migration list.
RATIONALE: Same-class completeness (cycle-7/8 RedFlag); strictly additive; zero reachability change today but bulletproof against future drift. Refactored AC1 migrates ~10 call sites instead of 6.
CONFIDENCE: HIGH

### Q9 — AC2 MCP surface: where does the new reject fire?
OPTIONS: (a) library-level `ingest_source` raises; CLI + MCP wrappers translate to user-facing error string unchanged. (b) explicit special-case in `kb.mcp.core.kb_ingest` + `kb_ingest_content` to name `kb_create_page` in the error message; library-level ALSO raises as defense-in-depth. (c) library-level only; MCP's existing "Unknown source_type" error is acceptable.

ARGUE: R2's E4 finding is decisive: MCP's `kb_ingest` and `kb_ingest_content` TODAY reject `source_type not in SOURCE_TYPE_DIRS` at `mcp/core.py:299-301` and `541-544` with "Error: Unknown source_type '...'". CLI uses `click.Choice(SOURCE_TYPE_DIRS.keys())` so `kb ingest --type comparison` errors at argument parse before ingest_source runs. The ONLY way to reach `ingest_source(source_type="comparison")` today is a direct Python call — which is the live dead path AC2 closes. Option (c) leaves the MCP surface emitting "Unknown source_type" for comparison/synthesis, which is misleading (those types are not unknown; they exist in `VALID_SOURCE_TYPES` and are handled by `kb_create_page`). Option (a) is defense-in-depth at the library but doesn't improve the MCP user experience — MCP's string-match check fires first.

Option (b) is the most user-friendly: adds an explicit short-circuit in `kb_ingest` and `kb_ingest_content` that checks `source_type in {"comparison", "synthesis"}` BEFORE the generic `not in SOURCE_TYPE_DIRS` check and returns `"Error: '{source_type}' pages are created via kb_create_page, not kb_ingest."`. Library-level raise is kept as defense-in-depth for direct Python callers. Sanitization: the error message only includes the source_type token (already validated against a small allowlist `{"comparison","synthesis"}`) plus the literal string `kb_create_page` — no paths, no extraction content. This meets threat-model T2's "does not interpolate paths or extraction content" criterion.

DECIDE: (b) library-level raise + MCP wrapper special-case naming `kb_create_page` for comparison/synthesis, before the generic "Unknown" check.
RATIONALE: Best UX (MCP error names the right tool); defense-in-depth (library raises for direct Python callers); sanitized (error only contains source_type token + literal tool name).
CONFIDENCE: HIGH

### Q10 — AC9 contract-defensive test: keep or drop the missing-`sources` case?
OPTIONS: (a) keep as defensive-contract coverage (R2 says production can't reach it but worth pinning). (b) drop AC9; focus on the reachable AC10/AC11 cases. (c) reframe AC9 to target `sources=[]` (reachable via legitimate page without `source:` frontmatter).

ARGUE: R2's E10 finding notes: "missing `sources` key is not reachable through production `search_pages`, because `load_all_pages` always emits `sources`; empty sources is reachable." So AC9 as written tests a defensive contract that the input normalization layer makes unreachable — but the `_flag_stale_results` function signature still accepts arbitrary dicts, so the contract is meaningful for any future caller that bypasses `load_all_pages`. Option (c) reframes to `sources=[]` which IS reachable and tests the same code path (`if not updated_str or not sources: continue`). Option (a) keeps the missing-key case as contract coverage (cheap, one line different from the `sources=[]` case). Option (b) drops coverage of a reachable branch.

The cleanest resolution: expand AC9 to have TWO sub-cases: (i) `sources` key missing entirely — defensive contract, (ii) `sources` key present but empty list — reachable. Both hit the same `if not updated_str or not sources` branch but document both contracts. Cost: one additional test function, 5 lines.

DECIDE: (c) reframe AC9 PRIMARY case to `sources=[]` (reachable) + keep a SECONDARY case asserting `sources` key missing also returns `stale=False` (defensive).
RATIONALE: Primary covers reachable production behavior (a page with no `source:` frontmatter entry); secondary pins the function-signature defensive contract. Both trivial to write.
CONFIDENCE: HIGH

## CONDITIONS

Before Step 7 plan writes the execution checklist, the following must be true of the amended AC list:

1. **AC3** test uses `pytest.raises(ValueError)` for `int`/`list`/`bool`/`dict` and asserts `""` for None, identity for str. No permissive-coerce assertions remain.
2. **AC5** lists 6 caller modules including `src/kb/compile/compiler.py` (function-local imports in `detect_source_drift` — do NOT promote to top-of-module).
3. **AC4** keeps `_page_id = page_id` as a module-level alias with `# noqa: N816` in `kb.utils.pages`. Three test imports remain unchanged.
4. **AC7** uses `click.testing.CliRunner` with monkeypatched deep workers. Each of 6 commands exercised. Assertion: `exit_code == 0` and no `ImportError`/`ModuleNotFoundError` in `result.exception`.
5. **AC8** uses subprocess `python -c "..."` with `sys.argv` set before `import kb.cli`. Asserts exit 0 + `'kb.config' not in sys.modules` + stdout contains `kb, version`. Parametrized on `["--version", "-V"]`.
6. **AC12** prerequisite commit enhances `tmp_project` fixture in `tests/conftest.py` to create `wiki/index.md` + `wiki/_sources.md` with canonical (non-empty) frontmatter-free headers. `tests/test_ingest.py::test_ingest_source` scaffolding cleanup is a separate commit.
7. **AC13** retains the existing `save_manifest` counter assertion AND adds a manifest-content-equality assertion after a second `compile_wiki` call.
8. **AC1** migration list expands to include 4 `_extract_entity_context` string-field reads (core_argument, abstract, description, problem_solved).
9. **AC2** MCP wrappers (`kb_ingest`, `kb_ingest_content`) add a special-case check for `source_type in {"comparison","synthesis"}` BEFORE the generic `SOURCE_TYPE_DIRS` check, returning a sanitized message naming `kb_create_page`. Library-level `ingest_source` raises `ValueError` with the same guidance.
10. **AC9** has two sub-cases: primary (`sources=[]` reachable); secondary (missing `sources` key — defensive contract).
11. Per-file commit plan updated to reflect: (a) 6-module atomic cluster (not 5); (b) `tests/conftest.py` fixture enhancement as a new commit before `tests/test_ingest.py` cleanup; (c) MCP-layer edits in `src/kb/mcp/core.py` as a new commit alongside the `src/kb/ingest/pipeline.py` edit.
12. **AC7/AC8 subprocess env hygiene** (non-blocking but recommended): AC8 subprocess uses minimal `env={"PYTHONPATH": str(repo/"src"), "PATH": os.environ.get("PATH",""), "SYSTEMROOT": os.environ.get("SYSTEMROOT","")}` on Windows; `PATH` alone on Unix.
13. **AC10** explicitly parametrizes `updated` test cases on `["yesterday", "04/19/2026", "", 20260101]` (the final item exercises the `except TypeError` branch).

## FINAL DECIDED DESIGN

### ingest/pipeline.py — defensive helper migration + dead-path closure (3 ACs)

- **AC1 (amended)** — `_coerce_str_field` is called at all `extraction.get("<field>")` read sites whose callee expects a str. Migrate **10** sites: title-merge path 947, key_claims 384/454, key_points 385/455, key_arguments 386, entities_mentioned 398/1001, concepts_mentioned 411/1017, authors 361, final-section key_claims 1115, **plus the 4 sites inside `_extract_entity_context` (core_argument, abstract, description, problem_solved at line 448-450)**. Test: inject `extraction = {"title": 42, "key_claims": 123}` via `ingest_source(..., extraction=...)` and assert `ValueError` raises cleanly at pre-validate pass. No site raises `AttributeError` or `TypeError`.

- **AC2 (amended)** — Two-layer closure:
  - Library: `ingest_source(source_type="comparison")` and `source_type="synthesis"` **raises `ValueError`** with message `"source_type '{source_type}' pages are created via kb_create_page, not kb_ingest"`. Guard lands before `source_path.read_bytes()`.
  - MCP wrappers: `kb.mcp.core.kb_ingest` and `kb_ingest_content` add an explicit check for `source_type in {"comparison","synthesis"}` BEFORE the generic `not in SOURCE_TYPE_DIRS` check, returning a sanitized error string naming `kb_create_page`.
  - Tests: 4 cases (library + MCP wrapper × comparison + synthesis) assert the error path fires and no files are written.

- **AC3 (amended to match live policy)** — Regression test pinning `_coerce_str_field` **fail-fast** contract:
  - `_coerce_str_field({"x": None}, "x") == ""`
  - `_coerce_str_field({"x": "str"}, "x") == "str"`
  - `_coerce_str_field({}, "missing") == ""` (missing key → None → "")
  - `pytest.raises(ValueError)` for each of `int`, `list`, `bool`, `dict`, `float`.

### Graph helper relocation (3 ACs)

- **AC4 (amended)** — `page_id(page_path, wiki_dir=None)` is defined in `src/kb/utils/pages.py` as the canonical location (absorbing the existing `_page_id` body + promoting `wiki_dir=None` default). The private `_page_id` helper is **retained as a module-level alias** `_page_id = page_id` with `# noqa: N816` and a docstring `"Deprecated — use page_id. Scheduled for removal cycle 12."`. `kb.graph.builder.page_id` becomes `from kb.utils.pages import page_id` re-export.

- **AC5 (amended to 6 callers)** — `scan_wiki_pages(wiki_dir=None)` moves to `src/kb/utils/pages.py`. `kb.graph.builder.scan_wiki_pages` re-exports. All **6** internal callers switch to `from kb.utils.pages import ...`:
  1. `src/kb/compile/linker.py` (top-of-module)
  2. `src/kb/evolve/analyzer.py` (top-of-module)
  3. `src/kb/lint/checks.py` (top-of-module)
  4. `src/kb/lint/runner.py` (top-of-module)
  5. `src/kb/lint/semantic.py` (top-of-module)
  6. `src/kb/compile/compiler.py:242-243` (function-local, preserve placement — do NOT promote to top-of-module; avoids import-cycle per R1 Q2).

- **AC6 (amended per R2 E7)** — Direct test coverage at canonical location (`tests/test_cycle11_utils_pages.py`):
  - (a) `page_id` lowercases (Windows `\\` and Unix `/` both normalize to `/`).
  - (b) `page_id` preserves subdir separator.
  - (c) `scan_wiki_pages` only returns files from `WIKI_SUBDIRS`; root-level sentinel files (`index.md`, `_sources.md`, etc.) are never enumerated because they live at wiki root, not in type subdirs. (Reframed as documentation test, not behavior-skip.)
  - (d) `scan_wiki_pages` returns deterministic sorted order.

### cli.py surface hardening (2 ACs)

- **AC7 (amended)** — `tests/test_cycle11_cli_imports.py` uses `click.testing.CliRunner` to invoke each of the 6 commands (`ingest`, `compile`, `query`, `lint`, `evolve`, `mcp`) with a minimal valid argument set and monkeypatched deep workers. Assertion: for each command, `result.exit_code == 0` AND no `ImportError`/`ModuleNotFoundError` in `result.exception`. Specific monkeypatches:
  - `ingest_source` → `lambda *a, **kw: {"pages_created": [], "source_type": "article", "content_hash": "x"*64, "duplicate": False}`
  - `compile_wiki` → `lambda *a, **kw: {"sources_processed": 0}`
  - `query_wiki` → `lambda *a, **kw: {"answer": "", "citations": [], "source_pages": [], "context_pages": []}`
  - `run_all_checks` → `lambda *a, **kw: []`
  - `generate_evolution_report` → `lambda *a, **kw: ""`
  - `main` from `kb.mcp_server` → `lambda: None`

- **AC8 (amended)** — `tests/test_cycle11_cli_imports.py` also runs a subprocess test per `["--version", "-V"]`:
  ```
  subprocess.run(
      [sys.executable, "-c",
       "import sys; sys.argv=['kb.cli','<flag>']; import kb.cli; "
       "assert 'kb.config' not in sys.modules, list(sys.modules)"],
      env={"PYTHONPATH": str(repo/"src"), "PATH": os.environ.get("PATH",""),
           "SYSTEMROOT": os.environ.get("SYSTEMROOT","")},
      capture_output=True, text=True, check=False,
  )
  ```
  Assert `returncode == 0` AND `"kb, version" in result.stdout`.

### Query engine edge-case test coverage (3 ACs)

- **AC9 (amended)** — Primary test: `_flag_stale_results` returns `stale=False` when result dict has `updated="2026-01-01"` and `sources=[]` (reachable). Secondary test: missing `sources` key returns `stale=False` (defensive contract).

- **AC10 (amended)** — Parametrize on `updated` values `["yesterday", "04/19/2026", "", 20260101]` (last exercises `except TypeError`). All return `stale=False`.

- **AC11** (unchanged) — mtime==page_date returns `stale=False` (strict `>` boundary).

### Test scaffolding cleanup (2 ACs)

- **AC12 (amended)** — Prerequisite commit: enhance `tmp_project` fixture in `tests/conftest.py` to create `wiki/index.md` and `wiki/_sources.md` with minimal headers (`"# Wiki Index\n\n"` and `"# Sources Map\n\n"`). Follow-on commit: `tests/test_ingest.py::test_ingest_source` replaces manual scaffolding + 5-way `patch()` block with `tmp_project` fixture + explicit `wiki_dir=tmp_project/"wiki"` + `raw_dir=tmp_project/"raw"` kwargs. Index/source assertions still read files from `tmp_project/"wiki"/"index.md"`.

- **AC13 (amended)** — Keep existing `save_manifest` counter. Additively, capture `manifest_path.read_text()` after first `compile_wiki` call and after a second (same-source) `compile_wiki` call; assert the parsed JSON dict is equal (single-source contract: re-running compile does NOT mutate manifest beyond the expected entries).

### Config / CHANGELOG alignment (1 AC)

- **AC14** (unchanged) — `CHANGELOG.md` `[Unreleased]` gains cycle-11 block. `BACKLOG.md` deletes resolved items.

## Per-file commit plan (updated)

1. `src/kb/utils/pages.py` — AC4 canonical absorb + `_page_id = page_id` alias + AC5 canonical absorb.
2. `src/kb/graph/builder.py` — convert `page_id` + `scan_wiki_pages` to re-exports.
3. **Atomic cluster (6 files, single commit)** — caller migrations:
   - `src/kb/compile/linker.py`
   - `src/kb/evolve/analyzer.py`
   - `src/kb/lint/checks.py`
   - `src/kb/lint/runner.py`
   - `src/kb/lint/semantic.py`
   - `src/kb/compile/compiler.py` (function-local imports inside `detect_source_drift`)
4. `src/kb/ingest/pipeline.py` — AC1 migration (10 sites) + AC2 library raise.
5. `src/kb/mcp/core.py` — AC2 MCP-wrapper special-case + error message.
6. `tests/conftest.py` — AC12 fixture enhancement (new commit).
7. `tests/test_ingest.py` — AC12 scaffolding cleanup (new commit).
8. `tests/test_compile.py` — AC13 behavioural content-equality assertion.
9. `tests/test_cycle11_utils_pages.py` — AC6.
10. `tests/test_cycle11_cli_imports.py` — AC7 + AC8.
11. `tests/test_cycle11_stale_results.py` — AC9 + AC10 + AC11.
12. `tests/test_cycle11_ingest_coerce.py` — AC1 + AC2 + AC3 regression tests.
13. `CHANGELOG.md` + `BACKLOG.md` — AC14.

## Scope-outs (same-class completeness)

- **AC1 scope-out** — list-consumer sites (`entities_mentioned`, `concepts_mentioned` list-branches at `or []`): tolerate non-str via `isinstance(x, list)` check; fail-closed drop but not migrated to a list-coerce helper. Defensible: requires a new list-coerce helper (`_coerce_list_field`) which is a separate feature; fail-closed behavior is already safe.
- **AC2 scope-out** — no new support for `comparison`/`synthesis` ingest; we CLOSE the dead path, not open it. Defensible: documented in requirements Non-goals; ingest semantics for these page types differ fundamentally from article/paper/etc.
- **AC4 scope-out** — `_page_id` alias deletion deferred to cycle 12 (lowest-blast-radius per Q3). Defensible: alias is a 1-line statement; delete any time; preserves 3 test imports.
- **AC12 scope-out** — 6+ OTHER `tests/test_ingest.py` tests that manually scaffold (lines 166+, 245+, etc.) NOT migrated. Defensible: requirements explicitly scope AC12 to one test; cycle-12 candidate; fixture enhancement in AC12 lowers the follow-up cycle's cost.
- **AC6 scope-out** — cross-platform lowercase rename (Windows `\\` vs Linux `/` case-sensitive filesystems) deferred. Defensible: documented in requirements Non-goals as "would force wiki-wide lowercase rename"; separate cycle.
- **AC13 scope-out** — other `tests/` files with `monkeypatch.setattr(..., save_manifest, ...)` not enumerated. Defensible: R1 scope check notes line 237 is the primary caller; Step 11 grep will verify.
