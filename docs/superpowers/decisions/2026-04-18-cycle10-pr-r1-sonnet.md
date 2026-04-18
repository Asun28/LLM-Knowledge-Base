# Cycle 10 PR #24 — Round 1 Code Review (Sonnet, edge-cases / concurrency / security / test gaps)

**Date:** 2026-04-18
**Branch:** `feat/backlog-by-file-cycle10`
**Reviewer:** Sonnet R1 (edge-cases / concurrency / security / test-gap focus)
**Prior art:** Codex R1 (`2026-04-18-cycle10-pr-r1-codex.md`); security-verify (`2026-04-18-cycle10-security-verify.md`)

---

## Verdict

APPROVE-WITH-REVISIONS

Two majors (one is a confirmed security blocker that the security-verify step itself flagged as T3 PARTIAL — it must be resolved before merge). Zero blockers from the concurrency / UUID / symlink angles after reading the actual code.

---

## Blockers

None new (both prior R1/security-verify blockers below are reclassified as Majors because they do not enable a new attack surface; they are hardening-consistency gaps, not open vulnerabilities).

---

## Majors

### M1 — `_validate_health_wiki_dir` is a threading-class concurrency hazard with a deterministic production bypass

`src/kb/mcp/health.py:13-22` implements `_validate_health_wiki_dir` by temporarily mutating `mcp_app.PROJECT_ROOT`, calling `_validate_wiki_dir`, then restoring it via `try/finally`. The identical pattern appears in `browse.py:325-331` for `kb_stats`. This is the only place in the codebase that mutates a module-global for correctness. Under the MCP server's default threading model (FastMCP uses `anyio` with a thread-pool worker), two concurrent `kb_graph_viz` / `kb_verdict_trends` / `kb_detect_drift` calls from separate MCP sessions will observe the mutated `PROJECT_ROOT` between the assignment and the `finally` restore — producing `(None, "wiki_dir must be inside project root")` false-positives for whichever caller reads after the mutation lands. This is not a theoretical race: FastMCP dispatches tool calls concurrently when `anyio` runs them on separate threads.

The security-verify step (T3 PARTIAL) independently flagged this. The root cause is that `_validate_wiki_dir` reads `PROJECT_ROOT` from the `mcp_app` module namespace (line 201: `root = PROJECT_ROOT.resolve()`), so callers in `health.py` and `browse.py` who imported their own `PROJECT_ROOT` from `kb.config` end up with a stale reference inside the shared helper.

**Fix:** Pass `project_root: Path` as an explicit parameter to `_validate_wiki_dir` rather than reading the module global. `health.py` and `browse.py` pass their locally-imported `PROJECT_ROOT` directly; no mutation needed, race eliminated, the `_validate_health_wiki_dir` wrapper becomes unnecessary. Four-line change in `app.py`, three-line removal in `health.py`.

Alternatively (smaller blast-radius): protect the critical section with a module-level `threading.Lock`. This is weaker but unambiguously correct; document the locking purpose.

**Must fix before merge.**

### M2 — AC9 docstring test is a `.__doc__` assertion, which is the allowed class but needs one more check

`tests/test_cycle10_linker.py:4-5` asserts two substrings in `detect_source_drift.__doc__`. This is explicitly the "docstring test" class permitted by the project conventions and correctly noted in the design. The design doc says this is "acceptable" per R2. However, the strings asserted (`"deletion-pruning"` and `"save_hashes=False"`) are present in the docstring and would fail if the docstring were removed — so revert-resistance is adequate. No action required beyond noting it passes the Red Flag check. *(Downgraded to non-blocking; included here so the PR trail is complete.)*

---

## Majors (security-class, confirmed)

### M3 — `_safe_call` import of `_sanitize_error_str` at call-time creates a latent circular-import risk if `kb.mcp.app` ever imports from `kb.lint`

`src/kb/lint/_safe_call.py:45` does `from kb.mcp.app import _sanitize_error_str` inside the `except` block. This deferred import avoids a circular import today (`lint` → `mcp.app`), but the pairing is fragile: if any future `mcp.app` import path pulls in `kb.lint` (e.g., a quality tool import at module level), Python will raise `ImportError` at runtime inside the exception handler — exactly when error surfacing is most needed. The deferred import silences the error rather than propagating it, so operators would see an unhandled `ImportError` from `_safe_call` itself instead of the original exception.

**Fix:** Move `_sanitize_error_str` (or a simpler `_redact_abs_paths(s: str) -> str` shim using the `_ABS_PATH_PATTERNS` regex) into a third module — e.g., `kb.utils.sanitize` — that neither `lint` nor `mcp.app` imports at module level. Both modules then import from the utils shim without risk of circularity. Alternatively, duplicate the regex sweep (6 lines) directly in `_safe_call.py`. The deferred-import approach is a time-bomb.

**Should fix before merge.** Not a current crash because `mcp.app` does not import `lint` today, but cycle 11 already considers pulling `_safe_call` into more lint paths.

---

## Nits

### N1 — UUID boundary collision check is over-specified

`src/kb/capture.py:360-364` checks three conditions: `boundary not in safe_content`, `boundary_start not in safe_content`, and `boundary_end not in safe_content`. Because `boundary_start = f"<<<INPUT-{boundary}>>>"` and `boundary_end = f"<<<END-INPUT-{boundary}>>>"`, both contain `boundary` as a substring. The third condition is strictly implied by the first (if `boundary` is not in content, `boundary_start`/`boundary_end` cannot be either). The redundant checks are harmless but will silently become wrong if the fence format changes so that `boundary` is not a substring of the fence. Replace with: check only the two full fence strings (not the bare hex), which is the actually relevant invariant.

### N2 — `captured_at` test has a latent false-pass risk in CI at second boundaries

`tests/test_cycle10_capture.py:84` asserts `captured_at_dt - pre_llm <= timedelta(seconds=1)`. If the wall clock happens to tick to a new second between the `pre_llm = datetime.now(UTC)` sample and the `captured_at` assignment (which is seconds-granular), the delta can be exactly 1 second, making the `<=` hold. But if CI is slow and `pre_llm` is sampled just before a second boundary while `captured_at` is rounded down to the same second as the LLM call starts, the test could falsely FAIL rather than falsely pass. The design (Q7 Option C) called for a monotonic-clock ordering test; the implementation uses wall-clock `datetime.now(UTC)` instead. The practical risk is low (2s sleep mock makes the ordering obvious) but the design rationale was specifically to avoid second-boundary brittleness. *(Non-blocking.)*

### N3 — `_validate_health_wiki_dir` wrapper is dead code if M1 fix is applied

If M1 is fixed by adding a `project_root` parameter to `_validate_wiki_dir`, the `_validate_health_wiki_dir` wrapper in `health.py` is removed entirely. If M1 is fixed via locking instead, the wrapper still exists but the mutation pattern persists — worth a comment explaining the lock scope.

### N4 — Commit `70b5e49` spans two unrelated files

`compiler.py` docstring change (AC9) + `utils/text.py` pipe-escape (AC28.5) are bundled with tests for both. The design's commit plan (commit 6) explicitly groups these two under "same file cluster as AC9 (compile/compiler.py)". `utils/text.py` is NOT in the compile cluster. Per `feedback_batch_by_file`, these should have been separate commits. Non-blocking since both changes are correct.

---

## Security edge-case analysis

**`_sanitize_error_str` handles `OSError.filename2` and Windows UNC:** Confirmed. `app.py:173-181` iterates both `filename` and `filename2` attributes and separately runs `_ABS_PATH_PATTERNS` regex which includes `\\\\?\\[^\s'"]+` for UNC long-path. Traceback text is not sanitized (the regex only strips isolated path literals from `str(exc)`, not full tracebacks), but `_safe_call` only surfaces `str(exc)`, not tracebacks, so this is acceptable.

**UUID boundary partial-collision (`<<<INPUT-abc>>>` when token is `abc`):** The retry loop uses `boundary not in safe_content` as the primary check where `boundary` is the 32-char hex value. A user supplying content containing `<<<INPUT-abc>>>` where `abc` is NOT the generated token would NOT trigger the collision check (the check looks for the token value `boundary`, not arbitrary `<<<INPUT-X>>>`-shaped strings). This is correct behavior — the check is intentionally exact, not pattern-matching all fence-shaped strings. No issue.

**Symlink-inside-PROJECT_ROOT pointing outside:** `_validate_wiki_dir` calls `path.resolve()` at line 200 before the containment check. `Path.resolve()` follows symlinks, so a symlink inside PROJECT_ROOT pointing outside resolves to the external target, which fails `is_relative_to(root)`. Correctly rejected. The test at `tests/test_cycle10_validate_wiki_dir.py:48-59` verifies this on non-Windows (symlinks require elevated privileges on Windows, hence the skip).

**Concurrency of `_secrets.token_hex`:** `secrets.token_hex` is backed by `os.urandom` which is thread-safe at the OS level. No global state shared between threads.

**`_safe_call` re-entrancy:** The helper is a pure function with no module state; fully re-entrant. `kb_refine_page` and `kb_query_feedback` sharing the same `_safe_call` import path introduces no contention.

**Double-exception from AC13a + AC13b (dual validation):** `_pre_validate_extraction` at `pipeline.py:918` runs before manifest reservation; `_coerce_str_field` in `_build_summary_content` runs after reservation. If `_pre_validate_extraction` raises, `_build_summary_content` is never called — the two cannot both fire on the same call. If somehow the extraction dict is mutated between the two (not possible in CPython single-threaded ingest), only AC13b fires and the reservation would be left in place (stale). This is the same pre-existing manifest-leak risk that the pre-validation was added to prevent — the design explicitly accepted that risk is now gone for the AC13 fields.

---

## Test gap analysis

**AC22/AC23 (`search_pages` vector filter):** Tests target the production `search_pages` function via `_enable_fake_vector_index` which monkeypatches `kb.query.embeddings.get_vector_index`. This correctly exercises `engine.py:131-154` (the `vector_search` nested function) rather than the dead `hybrid.py` path. The filter at line 145 (`kept = [r for r in results if r.get("score", 0.0) >= VECTOR_MIN_SIMILARITY]`) is tested with distance values `1.0` → score `0.5` (above 0.3, kept) and `3.0` → score `0.25` (below 0.3, dropped). The test would fail correctly if the filter line were removed. Revert-resistant.

**AC15 (`_validate_wiki_dir` outside-root rejection):** Tests cover: absolute outside path (T1), relative path rejection via `is_absolute()` check (T2 — the `"../../evil"` test fails at `is_absolute()` before reaching containment, which is correct behavior since relative paths are rejected first), valid subdirectory (T3), and symlink-pointing-outside on non-Windows (T4). **Gaps:** no test for `wiki_dir="/"` (root, absolute and exists but is not a project subdir), no test for `wiki_dir="~"` (tilde expansion via `expanduser()`). The root `/` case would correctly fail containment but is not pinned. Low severity; add as future tests.

**AC25 (`captured_at` timing):** The test uses `time.sleep(2)` inside the monkeypatched extractor, then asserts `captured_at_dt - pre_llm <= timedelta(seconds=1)`. Because `captured_at` is sampled before `_extract_items_via_llm` is called and `pre_llm` is also a `datetime.now(UTC)` sample taken immediately before `kb_capture`, both samples are in the same wall-clock second unless the test runner is extremely slow. The assertion is correct but the `timedelta(seconds=1)` tolerance is tight for a seconds-granular format. See N2.

**AC9 docstring test:** `detect_source_drift.__doc__` is a runtime attribute — removing or renaming the docstring would fail the test. No `inspect.getsource` anti-pattern. Passes the revert-resistance check.

**`test_claude_md_documents_raw_captures_exception`:** Asserts `"except raw/captures/"` and `"deletion-pruning"` in `CLAUDE.md`. This is a docs-consistency test, not a source-grep against production code. Appropriate for its scope.

---

## Edge cases to add as future tests

1. `_validate_wiki_dir(wiki_dir="/")` — root dir: absolute, exists, is-dir, but NOT inside PROJECT_ROOT. Should return `(None, "wiki_dir must be inside project root ...")`. Not currently pinned.
2. `_validate_wiki_dir(wiki_dir="~/foo")` — tilde expansion path that resolves outside PROJECT_ROOT. `expanduser()` is called, `is_absolute()` will pass after expansion; containment check should still reject it.
3. `_safe_call` with an `ImportError` inside `fn` — confirms the deferred `_sanitize_error_str` import itself doesn't mask an inner `ImportError` differently than other exception types.
4. `search_pages` with score exactly at threshold (`distance` such that `1/(1+d) == 0.3`): boundary-condition. Currently the filter is `>=` so threshold hits are kept. Pin this with a distance of `1/0.3 - 1 ≈ 2.333`.
5. Concurrent `kb_graph_viz` calls with different `wiki_dir` values — would expose the M1 race condition until it is fixed.

---

## PR trail quality

13 commits are broadly file-grouped. Commit `70b5e49` is the only multi-file violation (`compiler.py` + `utils/text.py`). The `1c3832e` security-fix commit spans `_safe_call.py`, `health.py`, and two test files — acceptable because all changes address the same security concern. Commit `a1c1f79` touches both `browse.py` and `health.py`; the design planned a 4a/4b split but they landed in one commit. Minor per `feedback_batch_by_file`.
