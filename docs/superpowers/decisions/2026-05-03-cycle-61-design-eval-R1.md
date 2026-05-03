# Cycle 61 — Design eval R1 (Opus 4.7)

**Reviewer:** Opus 4.7 R1 design-eval (independent audit, replicating grep evidence — not trusting the design doc)
**Date:** 2026-05-03
**Inputs:** `2026-05-03-cycle-61-design.md` (21 ACs), `2026-05-03-cycle-61-threat-model.md` (14 STRIDE), `2026-05-03-cycle-61-brainstorm.md` (D1-D6)

## Analysis

I replicated the grep evidence cited by the design doc against the cycle-61 worktree HEAD (`c13d3e8`, base `d7a98b7`). Findings below are anchored to file:line.

### AC1-AC5 (inherited d7a98b7 verification)

- AC1 codex argv constants: `src/kb/config.py:197-211` — confirmed exactly `["codex","exec","--json","--ephemeral","--sandbox","read-only","--skip-git-repo-check"]` inside `MappingProxyType`. ✓
- AC2 Windows `.cmd` shim: `src/kb/utils/cli_backend.py:64-69` — confirmed `os.name == "nt"` returns `"codex.cmd"`. ✓
- AC3 JSONL parser: `src/kb/utils/cli_backend.py:89-107` — confirmed `last_agent_text` walk, JSONDecodeError-`continue`, item.completed/agent_message gating. ✓
- AC4 model append: `src/kb/utils/cli_backend.py:84-86` — confirmed gate `if backend == "codex" and model:` before `cmd.extend(["--model", model])`. ✓
- AC5 existing test: `tests/test_cycle21_cli_backend.py:87-116` — `test_call_cli_codex_exec_jsonl_path` exists. The existing assertions are: `cmd[1:4] == ["exec", "--json", "--ephemeral"]` (line 111), `"-q" not in cmd` (112), `"--model" in cmd` (113), `"gpt-5.4-mini" in cmd` (114), `input == b"Reply..."` (115), `shell is False` (116). ✓ (positions confirmed)

### AC6-AC8 (allowlist file load) — **MULTIPLE GAPS FOUND**

- **`src/kb/config.py:690-696`** confirmed: `DUPLICATE_SLUG_ALLOWLIST: frozenset[frozenset[str]]` with the 3 pairs (concepts/bot↔llm, entities/openai↔openclaw, entities/logql↔promql). ✓
- **`src/kb/lint/checks/duplicate_slug.py:5,61`** confirmed: imports the constant at line 5; `_is_allowlisted_pair` consumes at line 61. ✓
- **CRITICAL — `wiki/_lint.yml` AND `.data/lint_allowlist.json` are BOTH gitignored.** Replicated `git check-ignore` (verbatim from this run):
  - `wiki/_lint.yml` → matched by `.gitignore:21:wiki/`
  - `.data/lint_allowlist.json` → matched by `.gitignore:17:.data/`
  - Brainstorm D2 says "`.data/` is gitignored — file would NOT be checked in" (correct), then says "Recommendation: B (`wiki/_lint.yml`)" — but `wiki/` is gitignored too. **D2's recommendation is BROKEN regardless of A or B; both candidate paths force the file out of git.**
- **PyYAML availability:** `requirements.txt:223` pins `PyYAML==6.0.3`; runtime `import yaml` works in `.venv` (confirmed `yaml.__version__ == 6.0.3`). So D2's "PyYAML stays a transitive dep" is correct, but the gitignore problem is the binding constraint, not the format.
- **No existing tests reference the constant by name:** `grep "DUPLICATE_SLUG_ALLOWLIST\|lint_allowlist" tests/` returns zero hits. This means migrating from a frozenset constant to a lazy accessor will not break legacy tests by name (no negative-assert hazard per `feedback_migration_breaks_negatives`).

### AC9 (KB_DISABLE_VECTORS env-var) — **PATTERN CLAIM IS WRONG**

- Design says: "add `KB_DISABLE_VECTORS: bool = ...` near the other env-var booleans (pattern follows existing `KB_DEBUG`)".
- **`KB_DEBUG` is NOT in `src/kb/config.py`.** It lives in `src/kb/cli.py:34-47` as `_is_debug_mode()` — a runtime-call lookup via `os.environ.get("KB_DEBUG", "").strip() in {"1","true","yes","on"}`. This is the OPPOSITE of a module-top boolean snapshot.
- `grep -nE "= os\.environ" src/kb/config.py` returns lines 17, 301, 328 — all are inside FUNCTIONS (`_resolve_project_root`, `get_cli_backend`, `get_cli_model`). **`config.py` has no module-top env-var boolean precedent.**
- The single existing `_DEFAULT_MODEL_TIERS` snapshot at `config.py:160-164` reads env at import (`os.environ.get(...).strip() or default`), and cycle-7 AC24 (commented at `config.py:142-146`) explicitly added the helper `get_model_tier()` to escape that staleness.

### AC10 (hybrid_search short-circuit) — **MAJOR LOAD-BEARING FLAW**

This is the most serious finding. **`kb.query.hybrid.hybrid_search()` is NOT called from production code.**

- `grep -rnE "hybrid_search" src/kb/`:
  - `src/kb/query/hybrid.py:54` — definition
  - `src/kb/query/hybrid.py:112,127` — log strings (BM25/vector backend WARNINGs, internal)
  - `src/kb/query/engine.py:197,208` — log strings only — string content `"hybrid_search backend=..."`, NOT a function call
- `grep -rnE "from kb.query.hybrid import hybrid_search" src/kb/` returns ZERO. Tests use it (`test_backlog_by_file_cycle2.py:763,772,787,796`, `test_backlog_by_file_cycle3.py:520`, `test_phase4_audit_query.py:112,126`), but the production search path in `engine.py::search_pages` (line 47) defines its OWN inline closures `bm25_search` (line 123) and `vector_search` (line 135), then dispatches at lines 194 and 205. RRF fusion uses `kb.query.hybrid.rrf_fusion` (line 38 import) — but the upstream `hybrid_search()` wrapper is unused in prod.
- **Implication:** the AC10 short-circuit at the top of `hybrid_search()` will not skip the vector path when `KB_DISABLE_VECTORS=1` during a real `kb_query` invocation. The flag becomes effective only inside the test suite (which is where `hybrid_search` is exercised). Production `vector_search` at `engine.py:135-187` keeps running — and that is the closure that opens `vec_path`, calls `embed_texts`, calls `idx.query`, etc.
- T8 in the threat model says "operator footgun ... vector layer silently disabled, query recall degrades, no obvious symptom." This describes the IMPLEMENTATION the design proposes; in reality, query recall would NOT degrade because the production vector layer would still run. The "silence" is even worse — the flag does nothing.

This is the single biggest blocker. The implementation site needs to be **`engine.py::vector_search` (the closure inside `search_pages`) OR `engine.py::search_pages` itself**. The hybrid.py site is a stub that no one calls.

### AC11 (regression test) — **DOES NOT CATCH PRODUCTION REVERT**

Even if AC10 is moved to the right site, the proposed assertion `vector_fn.call_count == 0` only catches reverts at the wrapped `hybrid_search()` boundary. Per cycle-16 L2 / cycle-24 L4: the test must reach the production call site. The proposed assertion targets the test-only call path. Two corollary gaps:
1. **No `caplog.at_level(logging.INFO)` capture for the "vector layer skipped" log line.** T8 explicitly says "Without (b) [INFO log assert], a future refactor that drops the log line is invisible." Design AC11 mentions `caplog` only implicitly via "spy on vector_fn".
2. **No divergent-fail position assertion.** `test_hybrid_search_calls_vector_when_KB_DISABLE_VECTORS_unset` covers branch B, but neither test verifies the SAME log line absence/presence. Per cycle-24 L4, a position assertion (e.g., "exactly one INFO record matching ...") is required.

### AC12 (kb_rebuild_indexes MCP wrapper) — **SAME-CLASS PEER SCAN INCOMPLETE**

- BACKLOG line at `BACKLOG.md:374` mandates: **"Audit entry should tag the invoker (CLI vs MCP) per cycle-20 L3 MCP-projection peer scan."** This is an EXPLICIT requirement in the BACKLOG entry that the design is fulfilling — not optional infrastructure.
- D4 in brainstorm picks "B (defer to BACKLOG)" — but BACKLOG.md ALREADY mandates the audit-tag work as part of THIS cycle's resolution. Deferring it means the BACKLOG entry cannot be deleted (per CLAUDE.md `BACKLOG.md lifecycle` — "Resolved items are deleted (...) When all items in a phase section are resolved...").
- Existing `kb.utils.wiki_log.append_wiki_log(operation, message, log_path)` has a 3-positional signature; no `caller=` kwarg. `grep -rnE "caller=" src/kb/` returns zero hits. So the audit-tag work is genuinely net-new.
- Same-class MCP tools (from `grep "@mcp\.tool\(\)" src/kb/mcp/*.py`):
  - `kb_compile`, `kb_compile_scan` (`mcp/compile.py`)
  - `kb_lint`, `kb_evolve`, `kb_graph_viz`, `kb_verdict_trends`, `kb_detect_drift` (`mcp/health.py`)
  - `kb_ingest`, `kb_ingest_content`, `kb_save_source`, `kb_capture` (`mcp/ingest.py`)
  - `kb_review_page`, `kb_refine_page`, `kb_lint_deep`, `kb_lint_consistency`, `kb_query_feedback`, `kb_reliability_map`, `kb_affected_pages`, `kb_save_lint_verdict`, `kb_create_page`, `kb_refine_sweep`, `kb_refine_list_stale` (`mcp/quality.py`)
  - `kb_query` (`mcp/core.py`)
  - `kb_search`, `kb_read_page`, `kb_list_pages`, `kb_list_sources`, `kb_stats` (`mcp/browse.py`)
- The design's same-class peer list (`kb_stats`, `kb_compile_scan`, `kb_detect_drift`, `kb_reliability_map`) is correct as far as it goes — these all wrap functions that may modify state or read sensitive paths. **MISSING from the peer scan:** `kb_compile`, `kb_ingest`, `kb_ingest_content`, `kb_save_source`, `kb_create_page` — these wrap destructive/mutating ops too. Cycle 20 L3 says "MCP-projection peer scan" — the rule is symmetric across same-tier tools. Of those, `kb_compile` is the most directly comparable to `kb_rebuild_indexes` (both call into `kb.compile.compiler`); should be on the list.

### AC13 (regression test) — **CONFIRMS T9, T10 BUT NOT T12**

The 3 cases (a/b/c) cover happy path + invalid wiki_dir + wrapped exception (T9, T10). Missing: a 4th case asserting the audit-tag (T12) — without it, the BACKLOG.md mandate is not regression-protected.

### AC14 (logger.error vs logger.exception) — **BEHAVIORAL UPGRADE WORKS**

- `tests/test_lint_query_fixes_v092.py:279,286` confirmed: pure `inspect.getsource(...)` substring asserts.
- Production code: `src/kb/mcp/health.py:87,129,153,211,235,259` use `logger.error(...)` — confirmed five sites. None use `logger.exception`.
- Proposed upgrade (monkeypatch `compute_trust_scores` to raise, spy on `logger.error` / `logger.exception`) is sound. The error path runs through `kb.mcp.health.kb_lint`'s outer `except Exception as e: logger.error(...)` at line 86-88. Spy on `kb.mcp.health.logger.error` (with `monkeypatch.setattr(kb.mcp.health, "logger", spy)`) reaches the production call site. ✓
- ONE caveat: AC14 says "monkeypatched `compute_trust_scores` raising" — but `compute_trust_scores` is in `kb.feedback.reliability`, not invoked by `kb_lint` directly. To force `kb_lint`'s error handler, monkeypatch `kb.lint.runner.run_all_checks` or `kb.lint.runner.format_report` to raise. The currently-named patch target is wrong. (For `kb_evolve`, monkeypatch `kb.evolve.analyzer.generate_evolution_report`.)

### AC15 (VERDICT_TREND_THRESHOLD) — **UPGRADE WORKS BUT REDUNDANT**

- Verified: `src/kb/lint/trends.py:8` imports `VERDICT_TREND_THRESHOLD`; lines 118, 120 use it. So the proposed `assert trends_module.VERDICT_TREND_THRESHOLD == config.VERDICT_TREND_THRESHOLD` is true and the divergent-fail behavioral test (monkeypatch threshold + check it flows through) is feasible.
- **However**, there is already a positive test at `tests/test_v0911_phase392.py:233` asserting `VERDICT_TREND_THRESHOLD == 0.1`. Adding a `hasattr+identity` check is fine; the divergent-fail half is the load-bearing addition.

### AC16 (WIKI_SUBDIRS) — **UPGRADE WORKS**

- `src/kb/graph/builder.py:24` is a COMMENT only ("WIKI_SUBDIRS is consumed by the re-exported kb.utils.pages.scan_wiki_pages"). The constant itself is not imported into builder.py — it's used transitively via `scan_wiki_pages` re-export. **AC16's proposed identity check `builder.WIKI_SUBDIRS is config.WIKI_SUBDIRS` would FAIL** because `builder` does not bind `WIKI_SUBDIRS` to its namespace.
- `src/kb/evolve/analyzer.py:20` imports `WIKI_SUBDIRS` directly — identity check works there.
- AC16 needs to drop the builder.py identity assertion OR re-anchor it on `scan_wiki_pages` behavior (since that's what the comment says builder uses). Easier: a behavioral test calling `build_graph` with monkeypatched `kb.utils.pages.WIKI_SUBDIRS` and asserting the new dir is scanned.

### AC17 (FRONTMATTER_RE) — **UPGRADE NEEDS A REPRODUCER**

- `src/kb/evolve/analyzer.py:18` imports `FRONTMATTER_RE as _FRONTMATTER_RE`; line 140 uses it. ✓
- The proposed test "input where the OLD inlined `\A\s*---` regex would fail but the new shared `FRONTMATTER_RE` succeeds" requires checking whether the two regexes actually diverge. `kb.utils.markdown.FRONTMATTER_RE` source is needed to validate that. If the two patterns are equivalent on common inputs, the divergence test is vacuous.

### AC18 (prune sites) — **FIXTURE EXISTS**

- `tests/test_compile.py:152-204` (`test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted`) ALREADY builds a stale-manifest fixture (manifest entry `articles/deleted.md` with the file absent). This satisfies the design Q8 / brainstorm assumption.
- For `compile_wiki(mode="full")` site (compiler.py:540, the second prune site at `prune_base = raw_dir.resolve().parent` + lines 549-560 stale-key loop), no existing fixture exercises that prune. AC18 must build a minimal one: write manifest entry `articles/x.md` with no on-disk file, call `compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path, ...)`, assert post-call manifest has no `articles/x.md` key. The brainstorm says "If yes, reuse" — the answer is partial yes (drift site), partial no (compile_wiki site). Q8 should resolve "build the second fixture; reuse the first."

### AC19-AC21 (docs) — **SHIPPED-VERIFICATION CORRECT**

- `wiki/purpose.md KB focus document`: `kb.ingest.extractors:357` referenced — confirmed present. (Did not deep-verify, accept design's claim.)
- Test count (3022 → 3022+5..9) is reasonable. Cycle-58 HEAD says 3021 (per CLAUDE.md Quick Reference); design says 3022 baseline (post d7a98b7 +1). Either works post-rebase.
- **Doc note:** AC21 says "Update `[Unreleased]` line in CLAUDE.md to point to cycle-61." But CLAUDE.md Quick Reference does NOT have an `[Unreleased]` line — that's in `CHANGELOG.md`. CLAUDE.md just lists cycles in the State bullet. Restate AC21 to "Update CLAUDE.md State bullet test/file counts; add cycle-61 pointer".

### Parallel-cycle collision (cycle-59 / cycle-53)

`git show 154e41c -- tests/test_lint.py | head -50` shows cycle-59's fold appends EOF-only (after line 685) — confirmed. Cycle-59 test_query.py and test_compile.py also append EOF-only (confirmed via `git show 154e41c`). cycle-53 branch HEAD is `6e1eace` (4 fold commits ahead of main). Cycle-61 EOF-section append plan is mechanically clean.

## Gaps and ambiguities

1. **AC10 — wrong implementation site (BLOCKER).** `hybrid_search()` in `kb/query/hybrid.py` is not called from `engine.py::search_pages` (the production search path). The kill-switch must move to `kb.query.engine::vector_search` (closure inside `search_pages` at line 135) or be hoisted to `search_pages` itself. **Recommendation:** add the env-var check at `engine.py:204-205`, immediately before `vector_results = vector_search(question, candidate_limit)` — wrap with `if kb.config.KB_DISABLE_VECTORS: vector_results = []` and log INFO once. Keep an additional check inside `hybrid_search()` for the test-only API surface so callers using it directly also benefit, but the production effect comes from engine.py.

2. **AC11 — regression test does not catch production revert.** Once AC10 moves to engine.py, the test must also move to exercise `kb.query.engine.search_pages` (or `query_wiki`) with `monkeypatch.setattr(kb.config, "KB_DISABLE_VECTORS", True)` and assert the production `vector_search` closure is not entered. Current proposal targets the test-only `hybrid_search`. **Recommended resolution:** add 3 sub-assertions: (a) `monkeypatch.setattr(kb.query.embeddings, "get_vector_index", spy)` — assert `spy.call_count == 0`; (b) `caplog.at_level(logging.INFO); ...; assert sum(1 for r in caplog.records if "KB_DISABLE_VECTORS=1" in r.getMessage()) == 1`; (c) divergent-fail twin without env-var asserts spy.call_count >= 1.

3. **AC9 — module-top vs runtime-call lookup.** `KB_DEBUG` is a `_is_debug_mode()` function (cli.py:34-47), not a module-top constant. If `KB_DISABLE_VECTORS` is added as a module-top `bool`, monkeypatch in tests works ONLY if consumers access via `kb.config.KB_DISABLE_VECTORS` (attribute access). The design's AC10 directive is correct in spirit but needs to align with reality. **Recommendation:** either (a) document explicitly that AC9 sets a module-top constant deliberately diverging from `KB_DEBUG`'s pattern, OR (b) add a `_kb_disable_vectors() -> bool` helper that re-reads env every call (parallel to `_is_debug_mode`). Option (b) is more robust and matches the existing precedent. The brainstorm D3 default ("attribute lookup at call time") is compatible with EITHER if the implementer is careful.

4. **AC6 file format & gitignore (BLOCKER).** Both `wiki/_lint.yml` (D2-B) and `.data/lint_allowlist.json` (D2-A) are gitignored. The brainstorm cites `.data/` as the reason to reject D2-A but then picks D2-B without checking that `wiki/` is also gitignored. **Recommendation:** either (a) commit-and-curate path — pick a non-gitignored location like `config/lint_allowlist.json` or root-level `lint_allowlist.json`; OR (b) operator-curated path — keep the path under gitignored dirs but ship a `.example` file in a tracked location (e.g., `templates/lint_allowlist.example.json`) plus a one-time copy step in CLI/MCP setup. Option (a) is cleaner; commit a tracked file at `config/lint_allowlist.json` (new dir) OR `templates/lint_allowlist.json`. Document the choice in AC6.

5. **AC7 — JSON `_comment` workaround.** Top-level `_comment` field is a hack that AC8 schema validator must explicitly skip. Recommend a structured approach: `{"version": 1, "duplicate_slugs": [...], "_meta": {"description": "..."}}` so future allowlists can extend the same file. (Tracks D1 — if a 2nd allowlist arrives, the schema is already extensible.)

6. **AC12 — caller="mcp" audit-tag is BACKLOG-mandated, not optional.** Brainstorm D4 picks "defer to BACKLOG" but the BACKLOG entry at line 374 is the SOURCE that mandates it. Deferring it means the BACKLOG entry cannot be deleted at AC19. **Recommendation:** implement in cycle 61 — extend `append_wiki_log(operation, message, log_path, *, caller: str = "cli")` with backward-compatible default `"cli"`; have `kb_rebuild_indexes` MCP wrapper pass `caller="mcp"`; existing call sites unchanged. ~10 lines + 1 test. AC count goes 21 → 22.

7. **AC12 — same-class peer scan missing kb_compile / kb_ingest / kb_save_source.** Cycle 20 L3 says symmetric scan; design lists only health.py peers. Recommendation: at Step 14, explicitly verify that `kb_compile` (mcp/compile.py:97) and `kb_ingest` (mcp/ingest.py:138) also route their wiki_dir through `_validate_wiki_dir` or the equivalent; if not, file BACKLOG.

8. **AC14 — wrong patch target.** `compute_trust_scores` is not invoked by `kb_lint`'s try/except. To force the error handler, patch `kb.lint.runner.run_all_checks` or `kb.lint.runner.format_report` to raise. For `kb_evolve`, patch `kb.evolve.analyzer.generate_evolution_report`.

9. **AC16 — builder.py does not bind WIKI_SUBDIRS.** The proposed `assert builder.WIKI_SUBDIRS is config.WIKI_SUBDIRS` will fail with AttributeError. Need to either (a) drop the builder identity check and rely on `analyzer.py`'s existing import; or (b) replace with a behavioral test asserting `build_graph` discovers pages under each `WIKI_SUBDIRS` directory.

10. **AC17 — divergence test needs the OLD regex value.** Without comparing the inlined `\A\s*---` against the shared `FRONTMATTER_RE`, the divergence test risks being vacuous. Confirm at design time that the two patterns differ on at least ONE input (e.g., trailing whitespace handling, multiline-flag interaction, etc.).

11. **D5/T2 sandbox-flag pin — fine to extend AC5 inline.** The existing test pins `cmd[1:4] == ["exec", "--json", "--ephemeral"]` (line 111). Adding 2 lines (`assert "--sandbox" in cmd and cmd[cmd.index("--sandbox") + 1] == "read-only"`; `assert "--skip-git-repo-check" in cmd`) closes T2 trivially. Brainstorm D5-A is correct.

12. **D6/T5 size cap — fine to absorb into AC6.** ~3 lines (`if path.stat().st_size > 64_000: log.warning(...); return DEFAULT`) is good defense in depth.

## Contradictions across the 3 input docs

1. **AC10 placement vs T8 mitigation.** Design (line 70-71) implements the kill-switch at `hybrid_search()` (kb/query/hybrid.py:54). Threat model T8 says "INFO log fires" is the visibility signal, and recommends `caplog.at_level(logging.INFO)` capture. Brainstorm D3 picks "A: top-of-function early return" with caveat "ensure nothing observability-load-bearing runs after the short-circuit." All three TREAT `hybrid_search()` as the load-bearing site — **but `hybrid_search()` is not called in production** (per `engine.py:204-205` going to its own closure). All three docs collectively miss that the implementation site doesn't reach the production search path. **Resolution:** add to AC10 an explicit decision: which site (engine.py vs hybrid.py vs both) hosts the env-var check; design must reconcile.

2. **AC6 file location: brainstorm vs. .gitignore.** Brainstorm D2 says "**Reject A** because `.data/` is gitignored and the allowlist must be checked in" — but then picks B (`wiki/_lint.yml`), and `wiki/` is ALSO gitignored. Threat model T5 (line 27) says "Path is constructed from `PROJECT_ROOT / ".data" / "lint_allowlist.json"`" — that's option A; D2 thinks it picked B. Design AC7 says ".data/lint_allowlist.json (new file)... File is checked into git" — but `.data/` is gitignored, so it WON'T be in git. **Resolution:** all three docs disagree on the path; pick ONE non-gitignored location and update all three.

3. **AC12 audit-tag: brainstorm D4 vs BACKLOG.md mandate.** Brainstorm D4 recommends "B (defer to BACKLOG MED)". Threat model T12 is in the "Decide at Step 14: (a) extend `append_wiki_log` with `caller=` ... OR (b) defer with a one-line BACKLOG entry" state. **BUT:** BACKLOG.md:374 (the source entry that AC12 is RESOLVING) says "Audit entry should tag the invoker (CLI vs MCP) per cycle-20 L3 MCP-projection peer scan." So the deferral creates a state where the BACKLOG entry CAN'T be deleted at Step 17 because the audit-tag clause is still open. **Resolution:** implement caller= in cycle 61; brainstorm D4 should flip to A.

4. **AC9 pattern follows KB_DEBUG.** Design says "pattern follows existing `KB_DEBUG`" — but `KB_DEBUG` is a function-scoped lookup in cli.py, not a module-top constant in config.py. Brainstorm doesn't surface this. Threat model is silent. **Resolution:** decide at Step 5 whether to use module-top `bool` (matches design AC9 literal) or runtime helper (matches KB_DEBUG precedent and dodges the snapshot hazard entirely).

## Conditions for plan-gate approval

Step 7 implementation plan MUST include:

1. **AC10 must dispatch on the production path.** Plan must specify the kill-switch is added at `kb/query/engine.py::search_pages` (most likely between line 204's setup and line 205's `vector_search` call). Optionally mirror in `hybrid.py::hybrid_search` for the test-only API. Reference: cycle-16 L2 ("stdlib-helper-in-isolation tests don't catch production reverts") and cycle-18 L1 (snapshot-binding hazard). The AC11 test must invoke `search_pages` (or `query_wiki`), not `hybrid_search`.

2. **AC11 must include INFO-log capture and divergent twin.** Per cycle-24 L4 (POSITION/RELATIONSHIP assertions). Use `caplog.at_level(logging.INFO)` and assert exactly one matching record. Pair with a `KB_DISABLE_VECTORS` unset twin asserting log absence and `vector_search` reached. Per cycle-40 L3, revert-verify both tests against a commented-out short-circuit before ship.

3. **AC6/AC7 path resolution.** Plan must pick ONE of: (a) commit at `config/lint_allowlist.json` or `templates/lint_allowlist.json` (untracked dirs become tracked); (b) ship a `.example` companion in a tracked dir + a runtime fallback to in-code default. Either is fine; the plan must NOT propose a path under `wiki/` or `.data/` thinking it's tracked.

4. **AC9 implementer note.** Plan must explicitly say: "consumers MUST NOT do `from kb.config import KB_DISABLE_VECTORS`; they MUST do `kb.config.KB_DISABLE_VECTORS` (attribute lookup) so monkeypatch works." Per cycle-18 L1. Add a Step-14 grep verify: `grep -rnE "from kb.config import.*KB_DISABLE_VECTORS" src/kb/` must return zero.

5. **AC12 caller-tag implementation.** Plan must include: extend `kb.utils.wiki_log.append_wiki_log` signature with `*, caller: str = "cli"`; thread `caller="mcp"` from the MCP wrapper; one new test pinning the caller= field appears in the audit message. AC count rises 21 → 22 (or absorb into AC12 sub-bullet). Per cycle-20 L3 + BACKLOG.md:374 mandate.

6. **AC14 patch target correction.** Plan must replace "monkeypatched `compute_trust_scores`" with "monkeypatched `kb.lint.runner.run_all_checks`" (for kb_lint) and "monkeypatched `kb.evolve.analyzer.generate_evolution_report`" (for kb_evolve). Per `feedback_inspect_source_tests` — extract a helper and test it directly, OR force the actual error path.

7. **AC16 builder identity check correction.** Plan must drop the `builder.WIKI_SUBDIRS is config.WIKI_SUBDIRS` assertion (will AttributeError) and replace with a `build_graph` behavioral test using monkeypatch on `kb.utils.pages.WIKI_SUBDIRS`.

8. **AC18 dual fixture.** Plan must clarify Q8: reuse existing `test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted` fixture (test_compile.py:152) for the drift-site spy, AND build a minimal new fixture for the `compile_wiki(mode="full")` prune site. Both are required for `spy.call_count >= 2` to be load-bearing.

9. **D5 inline assertion in AC5 verification.** Add 2 lines to existing `test_call_cli_codex_exec_jsonl_path` (test_cycle21_cli_backend.py:111-114): `assert "--sandbox" in cmd and cmd[cmd.index("--sandbox") + 1] == "read-only"; assert "--skip-git-repo-check" in cmd`. Tag with `# T2 sandbox-flag pin` for grep-discoverability.

10. **D6 size cap absorbed into AC6.** Add `if path.stat().st_size > 64_000: log WARNING + fall back` ahead of `json.load`. ~3 lines.

11. **Cycle-59 / cycle-53 collision protection.** Plan must use `# ── KB_DISABLE_VECTORS short-circuit (cycle 61) ─` style EOF dividers for test_query.py / test_lint.py / test_compile.py appends (per cycle-56 pattern). Reference: brainstorm risk row.

12. **Step 14 verification rows.** Per threat model: T1 regex test, T2 sandbox-flag pin (D5), T5 size cap (D6), T7 lru_cache identity, T8 INFO log capture (above), T9 path-traversal triplet (../, /tmp, C:\\), T10 wrapped-exception no-stack, T12 caller=mcp audit-tag, T13 grep guard for `from kb.config import KB_DISABLE_VECTORS`. Nine rows.

13. **Test count delta accounting.** Per AC21: net delta is +5 to +9 from new tests minus 0 from upgrades (upgrades CONVERT inspect.getsource asserts in place, no count change) plus +1 if AC12 caller-tag test ships. Update AC21 expected delta to +6 to +10.

## Verdict

**NEEDS_REVISION** — three blocker-level findings (AC10 implementation site, AC6 gitignore conflict, AC12 BACKLOG-mandated caller-tag misclassified as deferrable) plus 8 patch-level findings (AC9 pattern claim, AC14 wrong target, AC16 AttributeError, AC18 fixture half-built, AC11 missing INFO assert, T12 same-class scope, D2 contradiction across docs, AC21 [Unreleased] doesn't exist in CLAUDE.md). Cycle 61 cannot proceed to Step 7 implementation as currently designed without rework on AC6, AC9, AC10, AC11, AC12, AC14, AC16, AC18.

The good news: every blocker has a concrete resolution path above. After the design + brainstorm rework that addresses points 1-13 in the conditions section, this batch is mechanically clean (cycle-59/cycle-53 collisions are EOF-only) and the 4 inherited-d7a98b7 ACs are verified clean. Re-run R1 after the design revision to clear NEEDS_REVISION → APPROVE.
