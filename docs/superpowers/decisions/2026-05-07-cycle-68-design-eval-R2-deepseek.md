# Cycle 68 — Step 4 Design Evaluation R2 (DeepSeek V4 Pro)

**Date:** 2026-05-07/08  
**Reviewer:** DeepSeek V4 Pro (cross-family adversarial)

## Verdict

**APPROVE-WITH-AMENDMENTS**

All 6 new ACs (AC07-AC10, AC14-AC15) are sound in intent. However, 3 BLOCKERs and 5 MAJORs require design amendments.

## Findings

### F1 — AC08 completely unexamined (BLOCKER)

Requirements include AC08 (graph/cache migrations in export.py, mcp/browse.py, query/engine.py) but zero test plan. AC14 rolls both AC07+AC08 into one AST guard without per-file breakdown. Step-7 must split AC08 into 3 sub-tasks (one per file) with explicit AST validation per call site.

### F2 — AC09 transitive httpx constraint may become unreachable (BLOCKER)

Setting `httpx>=0.28,<0.29` must be compatible with ALL transitive deps. If ANY (anthropic, openai, fastmcp, firecrawl-py) pins `httpx<0.28` or `>=0.29`, pip install fails. AC15 only parses the string; no `pip install --dry-run` test. Resolution: AC15 must include install compatibility check and Step 11 must run `pip-audit --format=json` post-implementation.

### F3 — AC14 cache-hit spy test is vacuous without negative-control and cache-store mock (BLOCKER)

Spy on `build_graph` and assert call_count==1 after two get_graph calls. But: (a) If get_graph has `@functools.lru_cache`, spy fires once via function-level caching (not the custom global dict). (b) No negative-control: reverting get_graph to `return build_graph(wiki_dir)` should cause test to FAIL. Resolution: AC14 must include (i) cache-store mock asserting _GLOBAL_CACHE receives 1 write + 1 read, (ii) negative-control fixture that reverts get_graph and proves test fails.

### F4 — AC15 httpx constraint test uses substring match, not exact parse (MAJOR)

Test asserts `">=0.28" in constraint and "<0.29" in constraint`. But substring matching allows `httpx>=0.28,<0.30` (contains both, allows 0.29+). Resolution: Parse via tomllib and assert exact string `httpx>=0.28,<0.29`.

### F5 — AC10 BACKLOG cleanup test doesn't verify source issues fixed (MAJOR)

Test checks "GitPython unpinned" absent from BACKLOG, but doesn't verify requirements.txt actually has `GitPython>=X,<Y` with ceiling. Same for KB_PROJECT_ROOT: doesn't verify old module-level binding is gone (only new accessor exists). Resolution: AC15 must include source verification: grep requirements.txt for GitPython ceiling, parse config.py AST to confirm old KB_PROJECT_ROOT binding deleted.

### F6 — AC09 fetcher.py error message outdated after constraint (MAJOR)

Error message says "pin httpx in requirements.txt", but httpx IS pinned in both requirements.txt (0.28.1) and pyproject.toml (>=0.28,<0.29). Resolution: Update message to indicate actual issue (version mismatch). AC15 must test error message text.

### F7 — AC14 does not enforce attribute-lookup form in AST walk (MAJOR)

AC02 forbids `from kb.graph.cache import get_graph`. After AC07-AC08, code calls get_graph. Test must verify EVERY call uses `kb.graph.cache.get_graph(...)` (attribute form). Current spec only checks zero `func.attr == "build_graph"` calls. Resolution: AC14 must walk Call nodes and assert every get_graph call has shape: `func.value.attr=="cache" and func.value.value.attr=="graph" and func.value.value.value.id=="kb"`.

### F8 — AC07 generate_evolution_report likely double-builds (MAJOR, ACCEPT)

Lines 356-360: build_graph(wiki_dir, pages=pages_dicts) then analyze_coverage calls line 28 build_graph(wiki_dir, pages=same_list). Both bypass cache per design (pages-supplied calls intentional per cycle-64 AC9). Resolution: ACCEPT design. Document in Step-5 that this is intentional; add inline comment in analyzer.py explaining the double-build overhead.

### F9 — AC15 BACKLOG test commit atomicity hazard (MAJOR)

If AC10 (BACKLOG delete) and AC15 (test) in same commit and reverted, test also reverts (false-negative). If different commits with AC10-first, revert of AC10 alone leaves test passing falsely. Resolution: Step-7 plan must commit AC15 FIRST (test file), THEN AC10 (BACKLOG delete). That way, AC10 revert leaves test in place, which now fails (entry re-appears).

### F10 — AC14 pages-supplied call path not tested (MINOR)

AC07 lines 28, 358 bypass cache. AC14 test only exercises pages=None. Doesn't verify pages-supplied calls don't pollute cache. Resolution: Add `test_pages_supplied_bypasses_cache_isolation`: call get_graph(wiki, pages=list_a), then get_graph(wiki, pages=None), assert cache miss (call_count==2), then repeat pages=None call, assert cache hit (call_count still 2).

### F11 — AC15 missing happy-path httpx version test (MINOR)

Error check raises on version mismatch. No test that it PASSES on 0.28.x. Resolution: Add `test_httpx_version_check_succeeds_on_0_28_x`: monkeypatch httpx.__version__ to "0.28.1", import fetcher, assert no RuntimeError.

### F12 — AC14 AST walk misses aliased imports (MINOR)

Test checks string "from kb.graph.cache import get_graph". But `from kb.graph.cache import get_graph as _get` would elude it. Resolution: AC14 must check ImportFrom statements and assert zero imports from kb.graph.cache (regardless of alias).

## Carry-over acknowledgment

AC01-AC06, AC11-AC13 inherit cycle-67 verdicts. All 19 cycle-67 CONDITIONS apply.

## Conditions for Step 05 (NEW)

| # | AC | Condition | Test pin |
|---|----|----|----------|
| 1 | AC08 | Per-file AST validation for 5 migrated sites | `test_no_direct_build_graph_in_all_migrated_files` |
| 2 | AC09 | Pip install succeeds with httpx>=0.28,<0.29 | `test_pyproject_httpx_compatible_install` |
| 3 | AC14 | Cache-store mock validates _GLOBAL_CACHE usage | `test_cache_store_mock_writes_and_reads` |
| 4 | AC14 | Negative-control: broken get_graph causes cache test to fail | `test_cache_hit_negative_control_fails` |
| 5 | AC15 | Exact httpx constraint via tomllib parse | `test_pyproject_httpx_exact_constraint` |
| 6 | AC15 | GitPython ceiling in requirements.txt + KB_PROJECT_ROOT old binding absent | `test_backlog_cleanup_source_verify` |
| 7 | AC09 | Fetcher error message accuracy test | `test_fetcher_error_message_guidance` |
| 8 | AC14 | Every get_graph call is attribute-lookup form | `test_get_graph_attribute_form_only` |
| 9 | AC15 | Commit AC15 test BEFORE AC10 BACKLOG delete (separate commits) | Step-7 plan note |
| 10 | AC14 | Pages-supplied calls don't pollute pages=None cache | `test_pages_supplied_cache_isolation` |
| 11 | AC15 | Version check passes on 0.28.x (happy path) | `test_httpx_version_pass_0_28` |
| 12 | AC14 | ImportFrom: zero imports from kb.graph.cache | `test_no_aliased_imports_from_cache` |

## Verdict summary

- **APPROVE-WITH-AMENDMENTS** — 3 BLOCKERs, 5 MAJORs, 4 MINORs
- All resolvable via test enhancements + Step-7 plan detail
- No architecture changes
- Carry-overs inherit cycle-67 CONDITIONS

**Proceed to Step 5** with updated CONDITIONS above.
