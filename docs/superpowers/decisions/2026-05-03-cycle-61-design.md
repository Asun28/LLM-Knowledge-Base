# Cycle 61 — Design (backlog batch fix, 20 ACs)

**Date:** 2026-05-03
**Branch:** `feat/cycle-61` (worktree at `.claude/worktrees/cycle-61`)
**Base:** `main` @ `d7a98b7` (already includes codex backend upgrade — see Inherited Commits)
**Pipeline:** dev-mimo-opus
**Parallel cycles:** `feat/cycle-59` (20-fold batch, 3 commits ahead of `8f8a7e8`) · `worktree-cycle-53` (4 folds)

## Tier

**Tier 2 — standard feature.** Full pipeline (1–24). No mandatory human gates. Auto-merge after Step 21.

Justification:
- Touches MCP boundary (new `kb_rebuild_indexes` tool) — Tier 2 minimum.
- Touches subprocess invocation pattern (`d7a98b7` codex sandbox flag — already shipped, Step 14 verifies).
- Loads runtime data file (`.data/lint_allowlist.json`) — boundary parsing, Tier 2.
- Adds env-var-driven feature flag (`KB_DISABLE_VECTORS`) — Tier 1 in isolation but bundled with Tier 2 work.
- No auth, no crypto, no PII, no irreversible migration → not Tier 3.

Strict-audit denominator (per C59-L4 tier-aware ratio): full-pipeline binding-owner steps that ARE in this tier = Steps 7, 8, 9 (impl + DeepSeek bg reviewer), 14, 17, 18, 20-R1, 20-R2, 24. Denominator = 9 binding-owner dispatches.

## Goal

Land a 20-AC batch closing 5 BACKLOG-deferred items + 6 test-quality upgrades + 4 doc-sync items. Strictly file-grouped per `feedback_batch_by_file` ("HIGH+MED+LOW together by file"). Avoid collision with cycle-59 fold receivers and worktree-cycle-53.

## Inherited commits (already on `feat/cycle-61` via branch span from `main` HEAD)

| SHA | Message | Cycle-61 treatment |
|---|---|---|
| `d7a98b7` | `fix(cli): support codex exec json backend` | **Verify only** — Step 14 covers sandbox flag + JSONL parser + Windows shim. Step 17 docs cover it. AC1-AC5 below are verification ACs (not implementation). |

The d7a98b7 commit landed via direct push to local main during this session's dev-mimo-opus skill simplification work. It is in the cycle-61 PR diff against `origin/main` (`8f8a7e8`) and therefore in scope for cycle-61's review pipeline.

## Acceptance criteria

ACs are grouped by file. Each AC includes a grep-evidence line proving the symbol/feature exists (or doesn't yet) at the cycle-61 base commit. Per cycle-3 R1 lesson, BACKLOG entries are verified against current source before being included.

### Already-shipped (verify only at Step 14)

**AC1** — `src/kb/config.py`: codex CLI command is `["codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check"]`.
> Evidence: `git show d7a98b7 -- src/kb/config.py` lines 197-205.

**AC2** — `src/kb/utils/cli_backend.py`: `_backend_executable(backend)` returns `codex.cmd` on `os.name == "nt"`, else `binary`.
> Evidence: `git show d7a98b7 -- src/kb/utils/cli_backend.py` lines 64-69.

**AC3** — `src/kb/utils/cli_backend.py`: `_postprocess_stdout(backend, stdout_text)` extracts the LAST `agent_message` text from JSONL when backend is `codex`; falls through to `.strip()` for other backends.
> Evidence: `git show d7a98b7 -- src/kb/utils/cli_backend.py` lines 90-107.

**AC4** — `src/kb/utils/cli_backend.py`: `_build_cmd(backend, model)` appends `["--model", model]` when `backend == "codex" and model`.
> Evidence: `git show d7a98b7 -- src/kb/utils/cli_backend.py` lines 84-86.

**AC5** — `tests/test_cycle21_cli_backend.py::test_call_cli_codex_exec_jsonl_path` exists and exercises the full Codex JSON path (cmd shape, agent_message extraction, no `-q`).
> Evidence: `git show d7a98b7 -- tests/test_cycle21_cli_backend.py` lines 87-115.

### New implementation (Step 9 work)

**AC6** — `src/kb/lint/checks/duplicate_slug.py` (or `src/kb/config.py`): runtime allowlist load from `.data/lint_allowlist.json`. JSON shape: `{"duplicate_slugs": [["concepts/bot", "concepts/llm"], ...]}`. File-missing fallback uses the current `DUPLICATE_SLUG_ALLOWLIST` constant. Schema-mismatch (non-list, non-2-tuple entries) logs `WARNING` and falls back. Failure-open: NEVER raise on parse failure (lint must keep running).
> Current state: `src/kb/config.py:690-696` defines `DUPLICATE_SLUG_ALLOWLIST` as a hardcoded `frozenset[frozenset[str]]` of 3 pairs. `src/kb/lint/checks/duplicate_slug.py:5,61` already CONSUMES the constant via `_is_allowlisted_pair`. Cycle 61 must replace the hardcoded source with a runtime file load that returns the same shape.
> Implementation site: introduce `_load_duplicate_slug_allowlist()` in `kb/config.py` (or new `kb/lint/allowlist.py`); call once at module import, cache result; fall back to existing in-code constant when file absent. Per cycle-19 L2 reload-leak hazard: lazy `_get_duplicate_slug_allowlist()` accessor preferred over module-top read.

**AC7** — `.data/lint_allowlist.json` (new file): initial payload mirroring the current in-code constant. JSON-comment workaround: top-level `"_comment"` field documenting format. File is checked into git (curated allowlist, not a runtime artifact).
> Verification: `ls .data/lint_allowlist.json` returns success after Step 9.

**AC8** — `tests/test_lint.py`: regression test class `TestDuplicateSlugAllowlistFileLoad` with three cases — (a) file-present custom allowlist takes precedence over in-code default, (b) file-missing falls back to in-code default, (c) malformed JSON logs WARNING and falls back. Uses `tmp_kb_env` + `monkeypatch.setattr(config, "_DUPLICATE_SLUG_ALLOWLIST_PATH", tmp_path / "..")` to sandbox the file lookup. Per cycle-16 L2: must reach the production call site (`check_duplicate_slugs`) — NO `inspect.getsource` checks.
> Current state: `tests/test_lint.py` exists; no allowlist-file-load tests yet (`grep -n "lint_allowlist" tests/test_lint.py` returns zero hits).

**AC9** — `src/kb/config.py`: add `KB_DISABLE_VECTORS: bool = os.environ.get("KB_DISABLE_VECTORS", "0") in {"1", "true", "True", "yes"}` near the other env-var booleans (pattern follows existing `KB_DEBUG` / similar). Document in module docstring.
> Current state: `grep -n "KB_DISABLE_VECTORS" src/kb/config.py` returns zero hits (only docs/BACKLOG mention).

**AC10** — `src/kb/query/hybrid.py::hybrid_search`: when `kb.config.KB_DISABLE_VECTORS` is True, short-circuit to BM25-only path (skip vector_fn entirely, return `bm25_fn(question, limit)`). Logs `INFO` at first call: `"hybrid_search: KB_DISABLE_VECTORS=1 — vector layer skipped"`. Read the env-var via attribute lookup at CALL time (`kb.config.KB_DISABLE_VECTORS`), NOT module-top snapshot — per cycle-18 L1 snapshot-binding hazard.
> Current state: `src/kb/query/hybrid.py:54` defines `hybrid_search(question, bm25_fn, vector_fn, expand_fn=None, *, limit=10)`. No env-var short-circuit yet.

**AC11** — `tests/test_query.py` (or new section): regression test `test_hybrid_search_skips_vector_when_KB_DISABLE_VECTORS_set` using `monkeypatch.setattr(kb.config, "KB_DISABLE_VECTORS", True)` + spy on vector_fn. Assert vector_fn was NOT called. Second test `test_hybrid_search_calls_vector_when_KB_DISABLE_VECTORS_unset` for divergent-fail (per cycle-24 L4: regression tests need POSITION/RELATIONSHIP assertions, not just presence).
> Current state: `tests/test_query.py` exists with 600+ lines after cycle-59 fold; no KB_DISABLE_VECTORS tests yet.

**AC12** — `src/kb/mcp/health.py`: new MCP tool `kb_rebuild_indexes(wiki_dir: str | None = None)` — thin wrapper over `kb.compile.compiler.rebuild_indexes(wiki_dir=...)`. Validates `wiki_dir` via `_validate_health_wiki_dir` (existing pattern at `health.py:18-19`). Returns the same dict shape `rebuild_indexes` produces, JSON-serialisable. Audit-tag invocation as MCP per cycle-20 L3 (caller field in audit row).
> Current state: `src/kb/compile/compiler.py:642` defines `rebuild_indexes(...)`. `src/kb/mcp/health.py:12` already imports `_validate_wiki_dir`. No `kb_rebuild_indexes` MCP tool yet.

**AC13** — `tests/test_mcp_browse_health.py`: regression test `TestKbRebuildIndexes` with three cases — (a) happy path returns the rebuild dict, (b) invalid `wiki_dir` returns the validator's error response (no traceback), (c) underlying `rebuild_indexes` exception is wrapped in MCP error response (no leaked stack). Per cycle-7 L1 same-class peer scan (cycle-16 L1 inheritance): asserts that the caller of `_validate_health_wiki_dir` honours the same path-safety contract as the existing tools (`kb_stats`, etc.).

### Test-quality upgrades (per cycle-56+ BACKLOG marker — `inspect.getsource` C11-L1 batch)

**AC14** — `tests/test_lint_query_fixes_v092.py:279,286`: replace 2 `inspect.getsource(kb_lint)` / `inspect.getsource(kb_evolve)` substring assertions ("logger.error" present, "logger.exception" absent) with behavioral spies on the `logger.error` and `logger.exception` methods of the `kb.mcp.health` / `kb.mcp.quality` modules — invoke the production tool with a forced internal exception (e.g., monkeypatched `compute_trust_scores` raising) and assert the spy on `logger.error` was called and the spy on `logger.exception` was NOT. Per cycle-11 L1 / cycle-23 L2 / cycle-24 L4: revert-tolerant assertions are the bug; behavioral spy must reach the production call site.
> Current state: `tests/test_lint_query_fixes_v092.py:279` reads `source = inspect.getsource(kb_lint)`; line 286 same for `kb_evolve`. Both pure source-string asserts.

**AC15** — `tests/test_v0911_phase392.py:245`: replace `inspect.getsource(trends_module)` substring check ("VERDICT_TREND_THRESHOLD" present) with attribute-existence + value-stability assertion — `assert hasattr(trends_module, "VERDICT_TREND_THRESHOLD")` AND `trends_module.VERDICT_TREND_THRESHOLD == config.VERDICT_TREND_THRESHOLD` (re-export integrity). If the assertion is genuinely about source code (no hardcoded `0.1`), keep ONE positive behavioral test that calls the trends function with a monkeypatched threshold value and confirms the threshold flows through.
> Current state: `tests/test_v0911_phase392.py:245` reads `source = inspect.getsource(trends_module); assert "VERDICT_TREND_THRESHOLD" in source`.

**AC16** — `tests/test_v0915_task01.py:320,331`: replace 2 `inspect.getsource(builder)` / `inspect.getsource(analyzer)` checks ("WIKI_SUBDIRS" or "WIKI_SUBDIR_TO_TYPE" present) with attribute-import behavioural assertion — `from kb.graph import builder; assert builder.WIKI_SUBDIRS is config.WIKI_SUBDIRS` (identity check forces the production import to actually occur). Add a divergent-fail test that calls a builder/analyzer function with monkeypatched `config.WIKI_SUBDIRS` and verifies the new value flows through.
> Current state: lines 320, 331 confirmed.

**AC17** — `tests/test_v0915_task08.py:363`: replace `inspect.getsource(analyzer)` regex-absence assertion (`r"\A\s*---" not in source`) with behavioral test — call the frontmatter-detection helper with a multi-line input where the OLD inlined `\A\s*---` regex would fail but the new shared `FRONTMATTER_RE` succeeds (or vice-versa); assert the production code uses the shared regex. Per C24-L4: divergent-fail position assertion.
> Current state: line 363 confirmed.

**AC18** — `tests/test_compile.py::test_prune_base_uses_canonical_rel_path_at_both_sites` (line 217): C41-L1 behavioral upgrade per cycle-52 R1 DeepSeek NIT (BACKLOG-filed cycle-53+). Replace `inspect.getsource(compiler)` dual-site lint with stub — `monkeypatch.setattr(compiler, "_canonical_rel_path", spy)`, invoke BOTH `compile_wiki(mode="full")` (with a pre-stale manifest entry triggering `_prune_stale_manifest_entries`) AND `detect_source_drift` (which is the second prune site), assert `spy.call_count >= 2`. Test divergence: re-set `_canonical_rel_path` to a no-op lambda; both code paths produce different prune outcomes (the test must demonstrate the helper is load-bearing, not just present).
> Current state: line 217 confirmed; existing test uses `inspect.getsource` per cycle-52 R1 NIT.

### Documentation (Step 17 work)

**AC19** — `BACKLOG.md`: (a) DELETE `wiki/purpose.md KB focus document` entry — already shipped (verified `kb.utils.pages.load_purpose` wired in `kb.ingest.extractors:357` and `kb.query.engine:1066`); (b) re-confirm pip / litellm / diskcache / ragas CVE state at 2026-05-03 + cycle-61 timestamp; (c) DELETE the C11-L1 `inspect.getsource` batch entry once AC14-AC17 land (4 of 5 sites cleared; entry retained if any sites remain in unfolded versioned files).

**AC20** — `CHANGELOG.md` + `CHANGELOG-history.md`: cycle-61 entry — Items / Tests / Scope / Detail format. Brief entry under `[Unreleased]` Quick Reference; full per-cycle archive in `CHANGELOG-history.md`. Lists all 20 ACs with PR # placeholder.

**AC21** — `docs/reference/implementation-status.md` + `CLAUDE.md` Quick Reference: sync test count + file count + cycle pointer. Pre-cycle baseline: 3022 tests / 200 files (3022 from d7a98b7 +1 codex test). Post-cycle expected delta: +5 to +9 new tests (allowlist file load × 3, KB_DISABLE_VECTORS × 2, kb_rebuild_indexes × 3, plus C41-L1 behavioral upgrade ± 1) less the test-quality upgrades that CONVERT existing inspect.getsource asserts (no count change). Update `[Unreleased]` line in CLAUDE.md to point to cycle-61.

## Files touched

| # | File | Type | AC(s) |
|---|---|---|---|
| 1 | `.gitignore` | inherited (verify only) | (covered by d7a98b7) |
| 2 | `src/kb/config.py` | modify | AC6 (allowlist loader), AC9 (KB_DISABLE_VECTORS) |
| 3 | `src/kb/utils/cli_backend.py` | inherited (verify only) | AC1-AC4 |
| 4 | `src/kb/lint/checks/duplicate_slug.py` | modify | AC6 (consumer if loader lives in lint/) |
| 5 | `src/kb/query/hybrid.py` | modify | AC10 |
| 6 | `src/kb/mcp/health.py` | modify | AC12 |
| 7 | `.data/lint_allowlist.json` | new | AC7 |
| 8 | `tests/test_cycle21_cli_backend.py` | inherited (verify only) | AC5 |
| 9 | `tests/test_lint.py` | modify | AC8 |
| 10 | `tests/test_query.py` | modify | AC11 |
| 11 | `tests/test_mcp_browse_health.py` | modify | AC13 |
| 12 | `tests/test_compile.py` | modify | AC18 |
| 13 | `tests/test_lint_query_fixes_v092.py` | modify | AC14 |
| 14 | `tests/test_v0911_phase392.py` | modify | AC15 |
| 15 | `tests/test_v0915_task01.py` | modify | AC16 |
| 16 | `tests/test_v0915_task08.py` | modify | AC17 |
| 17 | `BACKLOG.md` | modify | AC19 |
| 18 | `CHANGELOG.md` | modify | AC20 |
| 19 | `CHANGELOG-history.md` | modify | AC20 |
| 20 | `docs/reference/implementation-status.md` | modify | AC21 |
| 21 | `CLAUDE.md` | modify | AC21 |

**Total:** 21 files (16 implementation + 5 documentation; 4 of those 16 are already in the inherited d7a98b7 commit).

## Parallel-cycle collision audit

| Cycle | Branch | Files claimed | Cycle-61 collision |
|---|---|---|---|
| 59 | `feat/cycle-59` | tests/test_lint.py, test_query.py, test_compile.py, test_cli.py, test_config.py, test_ingest.py, test_mcp_core.py (20-fold receivers) | **OVERLAP**: cycle-61 also appends to test_lint.py + test_query.py + test_compile.py. Resolution: cycle-61 appends EOF sections under cycle-61-named comment dividers; cycle-59 already merged sections preserved; on rebase, conflict is mechanical (both append to EOF). |
| 53 | `worktree-cycle-53` | tests/test_compile.py, test_config.py, test_query.py (4 fold receivers per `git log worktree-cycle-53`) | **OVERLAP**: same files. Same resolution. |

**Mitigation per cycle-56 pattern:** push a picks marker commit (Step 08b) before Step 9 implementation announcing the AC files claimed. This signals to in-flight cycles 53/59 that cycle-61 is using these files.

## Open questions for Step 5 design gate

1. **AC6 location** — Should the allowlist loader live in `kb/config.py` (current `DUPLICATE_SLUG_ALLOWLIST` site, simpler) or `kb/lint/allowlist.py` (separation-of-concerns, future-proof for other lint allowlists)? Default: `kb/config.py` for cycle-61; defer extraction if a 2nd allowlist arrives.
2. **AC7 file format** — JSON (matches BACKLOG suggestion `.data/lint_allowlist.json`) or YAML (matches BACKLOG alt `wiki/_lint.yml`)? Default: JSON in `.data/` — stdlib parser, no PyYAML pull, matches existing `.data/hashes.json` pattern.
3. **AC9 env-var truthiness** — `"1"` strict, or `{"1", "true", "True", "yes"}` permissive? Default: permissive (covers user typos in `.envrc`); cycle-19 L3 `or`-chain pitfall does not apply (this is a `set membership`, not a chained validator on the same input).
4. **AC10 placement** — short-circuit at the top of `hybrid_search` (skip both backend calls), or inside the BM25 branch with vector_fn defaulting to a no-op stub? Default: top-of-function early return; clearer call-graph for Step 14 audit.
5. **AC12 security** — does `kb_rebuild_indexes` need a same-class peer scan against `kb_compile`, `kb_ingest`, `kb_save_source`? They all call into compiler-internal helpers. Default: yes, list as Step 14 verify item; cycle-20 L3 MCP-projection rule applies.
6. **AC13 same-class peers** — list `kb_stats`, `kb_compile_scan`, `kb_detect_drift`, `kb_reliability_map` as same-class peers (all in `kb/mcp/health.py`); each must continue to reject invalid wiki_dir. Step 14 spot-checks one peer's existing test still passes.
7. **AC14-AC17 scope** — convert all 6 sites OR delete redundant assertions? Default: convert all to behavioral; delete only if Step 5 finds the assertion is fully covered by an existing behavioral test in another file.
8. **AC18 stub-test reproducer** — does `test_compile.py` have an existing fixture that creates a stale manifest entry to trigger `_prune_stale_manifest_entries`? If yes, reuse; if no, build a minimal one in the test (per cycle-52 R1 NIT context).

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| AC6 file-load + reload-leak (cycle-19 L2) | medium | Lazy `_get_duplicate_slug_allowlist()` accessor; tests use `monkeypatch.setattr` on the function, not the constant. |
| AC10 env-var snapshot (cycle-18 L1) | medium | Read via `kb.config.KB_DISABLE_VECTORS` at call time, not module-top `from kb.config import KB_DISABLE_VECTORS`. |
| AC11 test interferes with cycle-59's test_query.py append | medium | Place the test in a cycle-61-named EOF section (`# ── KB_DISABLE_VECTORS short-circuit (cycle 61) ─`). |
| AC12 MCP wrapper missing audit tag | medium | Step 14 checklist row: invocation logs `caller="mcp"` per cycle-20 L3. |
| AC14-AC17 behavioral test passes under revert | high (cycle-11/16/23/24 cluster) | Each new test must be revert-verified per cycle-40 L3: comment out the production fix line, run pytest -x, expect FAIL; restore. |
| AC18 fixture not reachable through `compile_wiki(mode="full")` | low | Step 5 Q8 explicitly resolves; if reachable only through `detect_source_drift`, scope-down the test. |

## Step 24 trial telemetry

Track for the 2026-05-31 trial writeup:
- Step 7 plan size + MiMo wall-clock (mimo-v2.5-pro)
- Step 8 plan-gate REJECT count + inline-resolution count (mimo-v2.5-pro)
- Step 9 background reviewer divergence — did `deepseek-rescue --model deepseek-v4-pro` flag anything `mimocoding-rescue` impl missed? (cross-family adversarial per C59 patch)
- Step 14 security verify — did MiMo find any threats Step 2 didn't enumerate?
- Step 17 doc-update fidelity (DeepSeek vs primary-session expected baseline; cycle-54-pickup C58-L1 was a DeepSeek wrong-cwd write — re-watch)
- Step 18 PR-finalize MiMo behaviour
- Step 20 R1 DeepSeek vs Sonnet edge-case divergence; R2 Codex vs Sonnet
- Step 24 governance gate (cross-family DeepSeek+Codex per C59-L3) on any skill-patch lessons emitted

Strict-audit ratio target (per C59-L4 tier-aware): 9/9 = 100% binding-owner dispatches honoured. Document in Step 24 scorecard.
