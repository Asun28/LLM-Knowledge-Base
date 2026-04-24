# Cycle 27 PR #41 — R1 Sonnet Review

**Reviewer:** R1 Sonnet (edge-case, concurrency, security, test gaps)
**Date:** 2026-04-24
**Verdict:** APPROVE-WITH-NITS

---

## Blockers

None.

---

## Majors

**[MAJOR] Test vacuity: `--help` smoke tests pass on misrouted subcommands**

File: `tests/test_cycle27_cli_parity.py:19-53`

All four `--help` tests (`test_cli_search_help_exits_zero`, etc.) only verify exit code 0 and help-text substrings. Confirmed via live mutation: replacing the `search` callback body with a no-op lambda gives `exit_code == 0` — the empty-query test then returns `exit_code == 0` instead of `1`, confirming the functional test DOES exercise the body. So the empty-query test at line 56 is the only genuine wiring check for `search`. No equivalent body-exercising test exists for `stats`, `list-pages`, or `list-sources`. A misrouted `stats` subcommand (pointing at `kb_list_pages` instead of `kb_stats`) would pass all 7 tests undetected. Recommend adding one mock-based functional test per AC2-AC4 command (stub out the underlying MCP call, verify it was invoked once with the right arguments), or at minimum a test that distinguishes the three commands' output shapes.

**[MAJOR] Missing non-stale marker test (AC1b revert-tolerance gap)**

File: `tests/test_cycle27_cli_parity.py:84-105`

`test_format_search_results_preserves_stale_marker` pins `stale=True` emitting `[STALE]`. No test pins that `stale=False` or an absent `stale` key suppresses the marker. The implementation is correct (`r.get("stale")` with falsy default), but a refactor that changed `if r.get("stale")` to an unconditional emit would pass both existing tests. Verified manually: `stale=False` and absent key both correctly suppress `[STALE]` today. Add a single parameterized assertion for the false/absent case alongside the stale=True test.

---

## Minors / Nits

**[MINOR] `kb search --wiki-dir` bypasses `_validate_wiki_dir` containment check**

File: `src/kb/cli.py:596-604`

`search` passes `wiki_dir` directly to `search_pages(wiki_dir=wiki_path)` without calling `_validate_wiki_dir`. The `stats` command routes through `kb_stats(wiki_dir=wiki_dir)` which calls `_validate_wiki_dir` internally — so it has the dual-anchor containment check. The `search` CLI path has `click.Path(exists=True, resolve_path=True)` but no `is_relative_to(PROJECT_ROOT)` guard. `search_pages` is read-only (it calls `load_all_pages` and BM25-indexes markdown files), so the practical risk is an operator reading wiki files outside the project directory — not a write surface and not a confidentiality breach in a single-user local setup. The threat model (T1-T3) does not enumerate this gap. For consistency with the cycle-23 dual-anchor pattern and to prevent a future write-capable refactor from accidentally inheriting the unvalidated path, consider calling `_validate_wiki_dir` (imported from `kb.mcp.app`) at the top of the `search` handler before constructing `wiki_path`.

**[NIT] Boot-lean contract confirmed clean**

`kb.mcp.browse` has module-level `from kb.config import ...` but the `search` handler only imports it function-locally, so `browse.py` (and its transitive `search_pages` / `kb.query.embeddings` chain) is NOT loaded at `import kb.cli` time. Verified: `kb --help` loads zero heavy modules. Function-local import pattern is correctly applied (lines 588-590). No action needed.

**[NIT] `_format_search_results` call-site count is 3, not 1**

Definition in `browse.py:30`, call in `kb_search` at `browse.py:79`, call in CLI `search` at `cli.py:605`, and two test-direct calls in `test_cycle27_cli_parity.py:81,102`. This is the expected outcome of an extraction refactor — 2 production call sites (MCP + CLI). There is no "single-caller invariant" violated; the helper was extracted precisely to support multiple callers.

---

## Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0     | pass   |
| HIGH     | 0     | pass   |
| MAJOR    | 2     | warn   |
| MINOR    | 1     | info   |
| NIT      | 2     | note   |

**Verdict: APPROVE-WITH-NITS** — Both MAJORs are test-gap issues (no runtime bugs), and the MINOR is a defence-in-depth consistency nit with no active exploit vector. Safe to merge; add the two missing tests in the next cycle's test-hardening pass.
