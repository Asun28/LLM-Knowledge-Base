# Cycle 9 Design Eval — Round 1 (Opus)

**Date:** 2026-04-18
**Reviewer:** Opus 4.7 (Design Eval R1)
**Inputs:** `2026-04-18-cycle9-requirements.md`, `2026-04-18-cycle9-threat-model.md`, `2026-04-18-cycle8-self-review.md`, `CLAUDE.md`, `BACKLOG.md`.
**Scope:** 31 AC across 16 files (batch-by-file; AC27 first, then AC1-3/28 query/engine.py, then remaining 12 files).

## Analysis

Cycle 9 is a classic cleanup cycle with a single structural theme — **finish the `wiki_dir` override migration** — wrapped around a grab-bag of naming/observability/test-hygiene items. Six ACs (AC1, AC2, AC3, AC4, AC5, AC28) collectively complete the `wiki_dir` threading that cycles 6/7/8 started in `kb_lint`, `kb_evolve`, `kb_stats`, `kb_graph_viz`, etc. The remaining 25 ACs are either (a) boundary-guard additions that cycle 8's audit explicitly deferred (AC7/8 oversize-reject, AC9 ambiguity error, AC10 OSError widening), (b) capture-module polish (7 ACs), or (c) doc/rename/test-hygiene surface (AC15, AC17, AC20, AC22, AC23, AC25, AC26, AC30, AC31). The one item with real defensive weight is AC24 (LLM error redaction), and per the threat model it is strictly additive to the existing `_sanitize_error_str` path-redactor — different axis, no duplicate logic.

The largest correctness blast radius lives in the **four ACs touching `src/kb/query/engine.py` hot path (AC1-3, AC28)**. I verified that line 131 still hardcodes `Path(PROJECT_ROOT) / VECTOR_INDEX_PATH_SUFFIX`, so the fix is real and load-bearing. AC2 (stale-flag root threading) is the subtlest of the four because `_flag_stale_results` is called inline at line 214 with no explicit root argument today — the fix must plumb `project_root=(wiki_dir.parent if wiki_dir else PROJECT_ROOT)` through one call site, which is mechanically small but has to agree with the cycle-4 `_flag_stale_results(root=...)` signature. AC14 (`_normalize_for_scan` bare `except Exception`) is the second-highest blast-radius item because it sits upstream of the secret scanner: broadening without an accompanying `logger.debug` trade loud narrow-except crashes for silent pass-through that reports clean on a decoder failure. The threat model correctly flags this — **the implementation plan MUST require the log line at Step 9**, not leave it as a nice-to-have. AC27 (lazy `__getattr__` in `src/kb/ingest/__init__.py`) is the cycle-8-lesson follow-up; I verified `src/kb/ingest/__init__.py` still has the eager `from kb.ingest.pipeline import ingest_source` on line 3, and the `src/kb/__init__.py` parent already implements the PEP 562 pattern correctly on lines 17-43 — so AC27 is a literal copy-paste of an already-proven pattern and the test shape is already shipped for cycle 8 AC30.

The file-sequenced execution order is sound and I endorse it: AC27 first buys the fast-path guarantee before any later commit can accidentally reinstate eager loading; the four engine.py ACs (AC1-3, AC28) as a single atomic commit keeps vec_path + stale + hybrid gate + raw-fallback wiki_dir threading in one reviewable diff; capture.py's 7 ACs (AC14-19, AC29) naturally cluster in one commit. My two non-blocking conditions are scoped narrowly: (1) AC14's `logger.debug` must be elevated from threat-model mitigation to AC acceptance criterion, and (2) AC23's `RAW_SUBDIRS` derivation needs an explicit per-subdir-created-empty behavior spec so new source types don't silently change test fixture semantics — currently the requirements just say "derive dynamically" without stating the invariant.

## Per-AC verdicts (terse)

| AC | Restatement | Risk | Assumptions / notes | Scope-creep flag | Open Q |
|----|-------------|------|---------------------|------------------|--------|
| AC1 | `search_pages` vec_path via `_vec_db_path(effective_wiki_dir)` | MEDIUM | Assumes `_vec_db_path` already accepts `wiki_dir` arg; verify in embeddings.py. Effective_wiki_dir derivation matches cycle-6 pattern. | None | None |
| AC2 | `_flag_stale_results(project_root=wiki_dir.parent)` threaded | MEDIUM | Assumes cycle-4 signature accepts `project_root` or `root`; AC wording is `project_root` but threat model uses `root` — resolve in Step 5. | None | Q1: does `_flag_stale_results` accept `root` or `project_root` kwarg? |
| AC3 | `kb_query` `_hybrid_configured` branch uses `_vec_db_path(WIKI_DIR)` | MEDIUM | Shares path source with AC1. Hot path at line ~756. | None | None |
| AC28 | `search_raw_sources` threads `project_root=wiki_dir.parent` | MEDIUM | Assumes `search_raw_sources` signature already accepts a root arg; if not, AC28 is one call site + one signature change. | None | Q2: existing signature? |
| AC4 | `kb_lint(wiki_dir)` derives feedback_path | LOW | Narrow scope (only `get_flagged_pages`); sibling MCP feedback sites remain OPEN. | Intentionally scoped. | None |
| AC5 | `kb_evolve(wiki_dir)` derives feedback_path | LOW | Mirrors AC4. | Intentionally scoped. | None |
| AC6 | `kb_compile_scan(wiki_dir)` plumbing | LOW | Mirrors cycle 6/8 pattern; additive param only. | None | None |
| AC7 | `kb_ingest` rejects oversize at MCP boundary | LOW | Behaviour change: silent-truncate → Error. Consistent with sibling tools. Breaking for any user who previously relied on silent truncation, but cycle-8 audit explicitly flagged as HIGH. | Intentional behaviour change; not scope creep. | None |
| AC8 | `kb_ingest_content` pre-write validate | LOW | Pre-write check matches `kb_save_source` pattern. | None | None |
| AC9 | `kb_read_page` ambiguous page_id Error | LOW | Existing fallback already warns; AC9 promotes to Error when >1 match. | None | Q3: what does test_cycle3/4 already assert on single-match case? Don't regress. |
| AC10 | `load_manifest` widens to OSError | LOW | Mirrors cycles 3/5/7 precedent. | None | None |
| AC11 | `run_augment` summary collapses to per-stub outcome | MEDIUM | Semantic fix. Per-URL detail in manifest MUST be preserved. | None | Q4: does `result["summary"]` consumer assume the current count semantics? Verify tests. |
| AC12 | `check_source_coverage` single YAML parse | LOW | Shared-corpus pattern. Assumes `load_all_pages()` already returns pre-parsed frontmatter (`content_lower` docs confirm). | None | None |
| AC13 | `analyze_coverage` orphan resolver parity | MEDIUM | Correctness-class fix: bare-slug resolution must match `build_graph`'s `slug_index` fallback. Test: A bare-links B, B no longer orphan. | None | Q5: what helper does `build_graph` use? Extract shared resolver or duplicate the lookup? |
| AC14 | `_normalize_for_scan` broaden to `except Exception` | MEDIUM | **Requires `logger.debug` at the continue** or silent-failure risk. Threat model names this. AC wording does NOT mandate the log — must upgrade. | **FLAG: must add log requirement** | Q6: is `logger.debug` a Step 9 acceptance criterion? |
| AC15 | `_check_rate_limit` docstring + TODO(v2) | LOW | Doc-only; zero behavior. | None | None |
| AC16 | Bounded collision loop with `RuntimeError` | LOW | New `_SLUG_COLLISION_CEILING` const default 10000. Reasonable ceiling. | None | None |
| AC17 | Rename `_path_within_captures` → `_is_path_within_captures` | LOW | Internal helper; no external callers. Test import must update. | None | None |
| AC18 | Label base64 vs URL-encoded in scan | LOW | Split `_normalize_for_scan` to return tuples; changes return signature. | Requires a co-change in `_scan_for_secrets`. | None |
| AC19 | `_CAPTURE_SECRET_PATTERNS` → NamedTuple | LOW | Internal refactor; grep-confirmed zero external consumers. | None | None |
| AC29 | `_verify_body_is_verbatim` strips body | LOW | Trimming preserves "verbatim-relative-to-input" semantics; threat model confirms audit risk zero. | None | None |
| AC20 | Import `CAPTURE_KINDS` from `kb.config` | LOW | Test hygiene; zero production impact. | None | None |
| AC21 | 2 new round-trip tests (backslash, quote titles) | LOW | Characterization tests for `yaml_escape`. | None | None |
| AC30 | Remove duplicate `import re as _test_re` + fix comment | LOW | Ruff F811 + comment accuracy. | None | None |
| AC22 | `tmp_captures_dir` PROJECT_ROOT-relative assert | LOW | Guards future fixture drift. | None | None |
| AC23 | `RAW_SUBDIRS` derived from `SOURCE_TYPE_DIRS.keys()` | LOW | Currently hardcoded 5/10. **Ambiguity**: does the fixture create all 10 empty dirs, or only those tests need? Behaviour spec missing. | **FLAG: clarify fixture-creation invariant** | Q7: does fixture eagerly mkdir all 10 subdirs? If yes, test startup cost rises (10 mkdir per test). |
| AC24 | `_make_api_call` redacts secrets BEFORE truncation | MEDIUM | Additive to `_sanitize_error_str` (different axis). Pattern list: `sk-ant-`, `sk-`, `Bearer [...]`, 32-char hex, 40-char base64. Hex-false-positive on UUIDs/session IDs; threat model notes output still useful (`[REDACTED:HEX]`). | None | Q8: confirm `[REDACTED:HEX]` 32-char threshold is NOT too aggressive — may redact git SHAs in error messages (40 hex chars common). Not a blocker but worth noting. |
| AC25 | FastMCP `instructions` block alpha-sort per group | LOW | Zero runtime impact. Line-by-line snapshot test is brittle on future adds; consider sorted-list assert instead. | None | Q9: snapshot test vs sorted-list assert — prefer the latter for maintainability. |
| AC26 | CLI function-local imports → top-level | LOW | Click startup is lazy so no cold-import penalty. `python -c "import kb.cli"` smoke test required. Threat model notes `kb.mcp_server` and `kb.mcp.*` also have function-local imports but those are INTENTIONAL (MCP startup) — scoped-out correctly. | None | None |
| AC27 | `src/kb/ingest/__init__.py` lazy `__getattr__` | LOW | **Verified**: current file has eager `from kb.ingest.pipeline import ingest_source` on line 3. Parent `src/kb/__init__.py` already ships the pattern to copy. Test shape exists from cycle 8 AC30. | None | None |
| AC31 | `.env.example` ANTHROPIC_API_KEY wording | LOW | Doc-only. README parity check. | None | Q10: should README.md parity be a Step 12 verify condition? |

## Top-level assessment

### SPLIT candidates — none

All 31 ACs are appropriately granular. AC14 tempts a split (broaden-except + add-log) but the two are tightly coupled and should stay atomic.

### DROP candidates — none

All 31 ACs have a clear traceback to either a cycle-8 Red Flag (AC27), a cycle-7/8 backlog item (AC7, AC10, AC11, AC13), or a user-reported issue (AC31). No item is purely cosmetic without a defensible origin.

### DEFER candidates — none

AC16's 10000-collision ceiling is cosmetic in the sense that real collisions never reach that count, but the fix is small and closes a theoretical infinite-loop, so no defer.

### MISSING coverage

**M1 — `_sanitize_error_str` double-sanitize ordering not verified.** The threat model claims AC24 runs FIRST so downstream `_sanitize_error_str(e)` inherits redacted strings. But if an `LLMError` is caught in `mcp/core.py` and then re-stringified via `_sanitize_error_str(e)`, the path-sanitizer operates on the ALREADY-redacted string. Verify order in Step 11: does `[REDACTED:ANTHROPIC_KEY]` survive the path-sanitizer's regex pass? (It should — the path-sanitizer only rewrites `/abs/path` patterns — but add a grep checkpoint.)

**M2 — cycle-8 follow-up gap in quality.py not addressed.** Cycle 8 self-review (L3 follow-up) explicitly flagged `src/kb/mcp/quality.py:85, 193, 426` as having inline `len(X) > MAX_Y` checks not yet migrated to `_validate_*` helpers. This is NOT in cycle 9's AC list. It is a known Class C item (validator pattern consolidation). Either add a 32nd AC for `_validate_content(size, field)` + `_validate_question(q)` OR explicitly defer in the requirements "Non-goals" section. Today it sits in limbo.

**M3 — cycle-8 R3 follow-up on `kb_save_lint_verdict` not re-verified.** Cycle 8 shipped `_validate_notes` to `kb_save_lint_verdict` via fix commit 825c8d8, but cycle 9 has no regression test guarding against future reverts. Consider a one-line test addition to AC21's batch: `test_kb_save_lint_verdict_rejects_oversize_notes`.

**M4 — `kb_compile` wiki_dir missing from cycle 9.** AC6 adds `wiki_dir` to `kb_compile_scan` (sister tool), but the threat model explicitly scopes-out `kb_compile` itself ("remains in backlog"). This is a conscious decision but worth double-checking: `kb_compile_scan` passing a `wiki_dir` that `kb_compile` cannot accept is an inconsistent public surface. Not a blocker if deferred with a BACKLOG note.

**M5 — AC7/8 error wording consistency not enforced across the three sites.** AC7 says "consistent `Error: source too long (... max ...)`" — but `kb_save_source` already enforces this with different wording (grep suggests it uses `_validate_file_inputs` at core.py:68). Step 9 must align all three error strings byte-for-byte, or tests will assert partial-match and drift can reappear.

### Ordering concerns

The file-sequenced order is correct. My only tactical note: **AC14+AC18 should commit together**, not as two separate capture.py commits. AC18 changes `_normalize_for_scan`'s return type from `str` to `list[tuple[str, str]]`, and AC14 changes its exception semantics. Splitting them risks a broken intermediate state where AC14 ships first (broader except + still returns `str`) and a capture flow hits a decoder crash the narrow-except would have caught — with no log signal because AC18 hasn't landed to surface the encoding-label yet. Commit capture.py as ONE commit covering all 7 ACs (AC14-19, AC29), not sequential per-AC commits.

Second tactical note: **AC20/21/30 (tests/test_capture.py) must commit AFTER capture.py**, not before. If they land first, AC18's return-type change breaks the test fixture until capture.py catches up. Sequencing: `capture.py` → `tests/test_capture.py` → `tests/conftest.py`.

Third tactical note: **AC1-3+AC28 as a single engine.py commit**. Splitting AC1 from AC3 risks shipping a state where `search_pages` uses `_vec_db_path(effective_wiki_dir)` but the `kb_query` gate still uses `PROJECT_ROOT/VECTOR_INDEX_PATH_SUFFIX` — mid-commit the classifier says `"hybrid"` while the actual backend reads a different DB. Keep them atomic.

### Test-plan coverage — verified

Each of AC1, AC2, AC3, AC13, AC27, AC28 calls out a specific verified test in the AC text. AC11's "synthetic two-URL stub fail-then-success" is the right test shape. AC14 should add a test that monkeypatches `base64.b64decode` to raise `RuntimeError` and asserts the `logger.debug` call count. AC22 is a fixture-level assert, not a separate test — that's correct. AC30 is a static cleanup; ruff `check --select F811` is the verifier.

## Final summary

**APPROVE-WITH-CONDITIONS**

Three conditions (all ADD-ON, none blocking re-review):

1. **AC14 acceptance criterion upgrade**: explicitly add "`logger.debug(\"normalize-for-scan skipped %s: %s\", kind, e)` at the broadened except" to the AC wording. The threat model names this as mitigation; promote it to AC contract.

2. **AC23 invariant clarification**: state whether `RAW_SUBDIRS` derivation causes the fixture to mkdir all 10 subdirs (10× mkdir cost per test) or only those in `SOURCE_TYPE_DIRS`. Current AC text is silent.

3. **Commit grouping**: enforce three-file atomicity — (a) all 4 engine.py ACs in one commit, (b) all 7 capture.py ACs in one commit, (c) test_capture.py commit AFTER capture.py. Add to Step 9 plan.

Three non-blocking follow-ups for Step 5 decision gate:

- Resolve Q1 (`_flag_stale_results` kwarg name: `root` vs `project_root`) via grep of cycle-4 source.
- Decide M2 (cycle-8 L3 follow-up on `quality.py` inline validators): add as AC32 OR defer to cycle 10.
- Decide M4 (`kb_compile` wiki_dir parity with AC6's `kb_compile_scan`): leave open OR add to non-goals.

Risk scorecard: no HIGH-risk AC. Four MEDIUM-risk ACs (AC1/2/3/28 engine.py hot path + AC11 summary semantics + AC13 resolver parity + AC14 exception broadening + AC24 redaction). 23 LOW-risk ACs.

Net new attack surface: zero (threat model confirmed). Net correctness surface: four isolation bugs closed, one silent-truncation removed, one silent-failure risk mitigated (with log-line condition).

---

*End of Round 1 design eval. Proceed to Codex R2 parallel review.*
