# Cycle 61 — Design decision gate (Step 5)

**Reviewer:** Opus 4.7 design-decision gate (synthesizes R1 + R2 + cycle-62 context)
**Date:** 2026-05-03
**Inputs:** design (8c6eed7), threat-model (ed87e07), brainstorm (c13d3e8), R1 review (Opus 4.7), R2 review (DeepSeek V4 Pro)
**Worktree:** `.claude/worktrees/cycle-61` @ `c13d3e8` (base `d7a98b7`)

---

## Analysis

I replicated R1's grep evidence against the cycle-61 worktree HEAD and confirm every BLOCKER. I also checked the candidate non-gitignored allowlist paths, replicated the BACKLOG.md:374 mandate, and inspected the cycle-62 worktree. R1's findings are accepted as written; R2's are accepted with minor scope adjustments (F2 lru_cache shape and F5 divergence specificity tighten the design without rework). One R1 sub-claim (about `builder.py` not binding `FRONTMATTER_RE`) is partially wrong — `builder.py:20` DOES import `FRONTMATTER_RE as _FRONTMATTER_RE`. The `WIKI_SUBDIRS` claim (R1 #9) is correct: `builder.py:24` is a comment-only stub; `WIKI_SUBDIRS` is not bound to the `builder` namespace. AC16 must therefore drop the builder identity check.

### Replicated grep evidence

1. **R1-B1 (AC10 wrong site).** `grep "hybrid_search\(" src/kb/` returns ONE hit only: `src/kb/query/hybrid.py:54` (the definition). No production caller. The production search path is `kb.query.engine.search_pages` (engine.py:47–219) which defines its OWN inline closures `bm25_search` (line 123) and `vector_search` (line 135) and dispatches at line 205 (`vector_results = vector_search(question, candidate_limit)`). RRF fusion uses `kb.query.hybrid.rrf_fusion` (engine.py imports it on line 38), but the wrapper `hybrid_search()` is unused in prod. **Confirmed.**

2. **R1-B2 (AC6/AC7 gitignore).** `git check-ignore -v` against the cycle-61 worktree returned:
   - `wiki/_lint.yml` → matched by `.gitignore:21:wiki/`
   - `.data/lint_allowlist.json` → matched by `.gitignore:17:.data/`
   - `config/lint_allowlist.json` → NO MATCH (tracked-eligible; `config/` is not gitignored)
   - `templates/lint_allowlist.json` → NO MATCH (tracked-eligible)
   - `lint_allowlist.json` → NO MATCH (tracked-eligible)
   Both brainstorm D2-A and D2-B paths are gitignored. **Confirmed.**

3. **R1-B3 (BACKLOG mandate).** `BACKLOG.md:374` reads verbatim: *"Audit entry should tag the invoker (CLI vs MCP) per cycle-20 L3 MCP-projection peer scan."* This is the entry that AC12 is RESOLVING. Per CLAUDE.md "BACKLOG.md lifecycle" — resolved items are deleted only when ALL clauses are met. Deferring caller-tag means the entry can't be deleted at AC19. Brainstorm D4-B is therefore self-defeating. **Confirmed.**

4. **R2-F3 (AC9/AC10 snapshot).** `KB_DEBUG` is NOT a config.py constant — it lives at `cli.py:34-47` as `_is_debug_mode()` (a function reading `os.environ.get(...)` at every call). `config.py` has no module-top env-var-boolean precedent that survives monkeypatch. R2 is correct that "attribute lookup at call time" alone doesn't fix T13: the value is still computed once at `kb.config` import. The robust fix is a `_kb_disable_vectors() -> bool` runtime helper paralleling `_is_debug_mode`, or explicit acceptance that env reads at process start. **Confirmed; runtime helper preferred.**

5. **R2-F10 (D1+D2 unreconciled).** Brainstorm picked D1=A (loader in config.py) and D2=B (file at `wiki/_lint.yml`). These are independent — loader location and on-disk location don't conflict. R2 says "if D2 chosen, D1 is moot" — that's wrong (the loader function exists in config.py regardless of where the file lives). **Adjusting:** keep D1=A (loader in config.py per minimal-churn), pick a NEW D2 path that's tracked-eligible.

6. **Cycle-62 audit.** `git worktree list` shows cycle-62 at the same base `d7a98b7` as cycle-61. `git status` in cycle-62 shows 16 modified files + 19 deleted versioned test files + 4 uncommitted design docs (`2026-05-03-cycle-62-{design,plan,requirements,self-review}.md`). The deleted test files are the SAME 19+ that cycle-59 already folded in committed form (`tests/test_v01002_*` through `test_v5_*`). Cycle-62 is doing duplicate work to cycle-59. No remote branch (`git branch -r --list feat/cycle-62` returned empty in prior session). **State: ABANDONED-LOOKING.** Cycle-61 file overlap with cycle-62: tests/test_lint.py, test_query.py, test_compile.py, test_cli.py, test_config.py, test_ingest.py, test_mcp_core.py (cycle-62 receivers); BACKLOG.md, CHANGELOG.md, CHANGELOG-history.md, CLAUDE.md, docs/reference/implementation-status.md, docs/reference/testing.md, README.md (doc updates). Mechanical-rebase risk only — cycle-61 appends to EOF under cycle-61-named dividers per cycle-56 pattern; cycle-62 (if it commits) appends to EOF under different markers.

7. **Cycle-59 EOF marker style.** `grep -nE "^# ──.*cycle.59" tests/test_query.py tests/test_lint.py` in the cycle-59 worktree returns 11 hits, all `# ── <description> (cycle 59 fold) ─` (em-dashes flanking, parenthetical "fold" tag). Cycle-61 must align: `# ── <description> (cycle 61) ─`.

8. **`FRONTMATTER_RE` divergence.** `kb.utils.markdown.FRONTMATTER_RE = re.compile(r"\A(---[ \t]*\r?\n.{0,10000}?\r?\n---[ \t]*\r?\n?)(.*)", re.DOTALL)`. Old inlined regex per AC17 was `\A\s*---`. Divergence: old `\s*` accepts ANY whitespace before `---` (including newlines); new requires `---` at column 0 followed by `[ \t]*\r?\n`. Reproducer input: `"\n---\nfoo: bar\n---\nbody"` — old matches (leading `\n`), new does NOT match (the `\A` then `---` requires zero leading whitespace). AC17 divergent-fail test is feasible.

9. **`builder.WIKI_SUBDIRS` (R1 #9, AC16).** `builder.py:24` is `# WIKI_SUBDIRS is consumed by the re-exported kb.utils.pages.scan_wiki_pages.` — comment only. No `from kb.config import WIKI_SUBDIRS` in builder.py. **`builder.WIKI_SUBDIRS` raises AttributeError at runtime.** R1 #9 is correct; AC16 must drop the builder identity check or replace with behavioral test. (`evolve.analyzer:20` does `from kb.config import WIKI_SUBDIRS` — identity check works there.)

10. **MCP wrapper landing site (D5 sandbox-flag pin tautological?).** `CLI_TOOL_COMMANDS["codex"]` is wrapped in `MappingProxyType` (config.py uses `types.MappingProxyType` per the threat-model citation at line 192-211). `MappingProxyType` makes the OUTER mapping read-only; the inner `list[str]` is NOT frozen — `list.append`, `list.pop`, etc., still mutate. So a future refactor that mutates the inner list IS possible. R2-F9's "tautological" claim is therefore wrong; D5-A is cheap defense in depth.

### Disputed R1/R2 claims

- **R2-F10 ("D1 moot if D2-B chosen").** Wrong as stated. Loader location and file path are independent. Accepting the spirit (reconcile the two), not the letter.
- **R1's casual mention of "AC15 already has a positive test."** Verified at `test_v0911_phase392.py:233` in earlier reads — confirmed; AC15 retains the divergent-fail half only.
- **R2-F9 ("D5 tautological because MappingProxyType").** Wrong. `MappingProxyType` is a read-only VIEW over the dict; it doesn't recursively freeze contained lists. D5-A is cheap and load-bearing.
- **R2-F2 (AC6 lazy-accessor underspecified).** Accepted; the design says "lazy" but doesn't enforce `@lru_cache`. Tighten AC6 wording.

---

## Resolved decisions

### BLOCKERS (R1 / R2)

| # | Finding | Decision | Source | Resolution |
|---|---------|----------|--------|------------|
| 1 | R1-B1 / AC10 wrong site | **Move kill-switch to `kb.query.engine.search_pages`**, immediately before line 205 (`vector_results = vector_search(question, candidate_limit)`). Wrap with `if _kb_disable_vectors(): vector_results = []; logger.info("hybrid_search: KB_DISABLE_VECTORS=1 — vector layer skipped")`. **Mirror in `kb.query.hybrid.hybrid_search`** at the top so the test-only API also benefits. Prod effect comes from engine.py. | R1-B1, R1 contradiction #1 | AC10 rewrites; AC11 must invoke `search_pages` (or `query_wiki`) and spy on `kb.query.embeddings.get_vector_index` (the closure's actual entry point at engine.py:144) to catch production reverts. |
| 2 | R1-B2 / AC6+AC7 gitignore | **Pick `config/lint_allowlist.json`** (new top-level dir; tracked-eligible per replicated `git check-ignore` no-match). JSON format (stdlib `json.load`, no PyYAML hard dep). Schema: `{"version": 1, "duplicate_slugs": [["a","b"],...], "_meta": {"description": "..."}}`. Loader path: `PROJECT_ROOT / "config" / "lint_allowlist.json"`. | R1-B2, R1 patch #5, R2-F1 | AC7 path changes; `.data/` and `wiki/` rejected; new top-level `config/` dir created (vs cluttering repo root with `lint_allowlist.json`). |
| 3 | R1-B3 / AC12 caller="mcp" mandate | **Implement caller=mcp in cycle 61.** Extend `kb.utils.wiki_log.append_wiki_log(operation, message, log_path, *, caller: str = "cli")` with backward-compatible default. `kb_rebuild_indexes` MCP wrapper passes `caller="mcp"`; existing CLI sites unchanged. Audit message format: `"- YYYY-MM-DD | rebuild-indexes | caller=mcp | <existing message>"`. | R1-B3, R1 contradiction #3, R2-F4, BACKLOG.md:374 | AC count rises 21 → 22; **flip D4 from B to A**. New AC22 for caller-tag pin test. AC19 BACKLOG-deletion now valid. |
| 4 | R2-F3 / AC9 snapshot semantics | **Use runtime helper `_kb_disable_vectors() -> bool` in `kb.config`** paralleling `cli._is_debug_mode`. Reads `os.environ.get("KB_DISABLE_VECTORS", "").strip() in {"1","true","True","yes"}` at every call. Consumers call `kb.config._kb_disable_vectors()` (function call), NOT `kb.config.KB_DISABLE_VECTORS` (attribute lookup of a frozen module-top bool). Tests use `monkeypatch.setenv("KB_DISABLE_VECTORS", "1")` (the env-var) OR `monkeypatch.setattr(kb.config, "_kb_disable_vectors", lambda: True)` (the function). | R2-F3, R1 patch #3 | AC9 rewords from constant-set to function-define; AC10 calls the function; AC11 monkeypatches via setenv (preferred — exercises the actual production path). |
| 5 | R2-F10 / D1+D2 reconciliation | **D1=A (loader in `kb.config`), D2=NEW (`config/lint_allowlist.json`).** Loader and file are independent. | R2-F10 | Documented as separate decisions below. |

### Patch-level findings (R1 / R2)

| # | Finding | Decision | Source |
|---|---------|----------|--------|
| 6 | AC9 KB_DEBUG pattern claim wrong | Reword AC9 to "function `_kb_disable_vectors()` paralleling `cli._is_debug_mode`; module docstring updated; no module-top constant" | R1-B/3, R2-F3 |
| 7 | AC11 missing INFO-log capture + divergent twin | Add `caplog.at_level(logging.INFO)` capture; assert exactly ONE `INFO` record matching `"KB_DISABLE_VECTORS=1"`. Divergent twin (env unset) asserts ZERO matching records AND `vector_search` IS reached. | R1 patch #2, T8 |
| 8 | AC14 wrong patch target | Replace "monkeypatched `compute_trust_scores`" with "monkeypatched `kb.lint.runner.run_all_checks`" (for kb_lint at health.py:84 → except at line 86) and "monkeypatched `kb.evolve.analyzer.generate_evolution_report`" (for kb_evolve at health.py:150 → except at line 152). Both call sites verified. | R1 patch #8 |
| 9 | AC16 builder.WIKI_SUBDIRS AttributeError | Drop builder identity check (builder.py:24 is comment-only — no `WIKI_SUBDIRS` import). Keep `analyzer.WIKI_SUBDIRS is config.WIKI_SUBDIRS` (analyzer.py imports it directly). For builder, add a behavioral test on `build_graph` with monkeypatched `kb.utils.pages.WIKI_SUBDIRS` (where `scan_wiki_pages` actually consumes it). | R1 patch #9 |
| 10 | AC17 FRONTMATTER_RE divergence reproducer | Use input `"\n---\nfoo: bar\n---\nbody"`: old `\A\s*---` matches (greedy whitespace); new `\A(---[ \t]*\r?\n...` does NOT (requires `---` at column 0). Test asserts `analyzer._FRONTMATTER_RE.match(input) is None` proving the new regex is in use. | R1 patch #10, F8 reproducer |
| 11 | AC18 dual fixture clarification | (a) Reuse `tests/test_compile.py:152-204` `test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted` fixture for the drift-site spy. (b) Build a NEW minimal fixture for the `compile_wiki(mode="full")` prune site (compiler.py:540 + 549-560 stale-key loop): write manifest entry `articles/x.md` with no on-disk file, call `compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)`, assert post-call manifest has no `articles/x.md` key. Both fixtures required for `spy.call_count >= 2` to be load-bearing. | R1 patch #8 (re-numbered), R2-F5 |
| 12 | AC18 vague "different prune outcomes" | Specify divergent-fail explicitly: re-set `_canonical_rel_path` to lambda returning `"FROZEN"`; assert that the stale `articles/x.md` is NOT pruned (the no-op helper produces a different rel-path key, so the prune lookup misses). Test fails if the helper is bypassed in either site. | R2-F5 |
| 13 | AC21 [Unreleased] not in CLAUDE.md | Reword AC21 to "update CLAUDE.md State bullet test/file counts; add cycle-61 pointer". `[Unreleased]` lives in CHANGELOG.md (covered by AC20). | R1 patch (item 13) |
| 14 | R2-F2 AC6 lazy-accessor shape | Amend AC6: "Loader is a `@lru_cache(maxsize=1)`-decorated function `_get_duplicate_slug_allowlist()` in `kb.config`. Module-top file read is FORBIDDEN. Cache invalidation in tests via `_get_duplicate_slug_allowlist.cache_clear()`." | R2-F2 |
| 15 | R2-F6 versioned-file fold timing | Cycle-59 already folded `test_v01002_*` through `test_v5_*` (19 files). Cycle-61's AC14-AC17 targets are `test_lint_query_fixes_v092.py`, `test_v0911_phase392.py`, `test_v0915_task01.py`, `test_v0915_task08.py` — these are NOT in cycle-59's fold set (they're cycle-9.x not v01x/v4_/v5/v01x). No fold conflict. AC14-AC17 ship in cycle 61. | R2-F6, cycle-59 git log replicated |
| 16 | R2-F7 cycle-59 EOF marker style | Confirmed format: `# ── <description> (cycle 59 fold) ─`. Cycle-61 aligns to `# ── <description> (cycle 61) ─` (em-dashes, parenthetical cycle tag, no "fold" since cycle-61 is appending fresh sections, not folding). | R2-F7 |
| 17 | R2-F9 D5 tautological | **Wrong claim.** `MappingProxyType` is a shallow read-only view; inner `list[str]` is mutable. D5-A is cheap defense in depth (~3 lines), keeps the regression window closed against future refactors that mutate `CLI_TOOL_COMMANDS["codex"]` in place. **Keep D5=A.** | R2-F9 (rejected), brainstorm D5 |

### D-decisions

| # | Brainstorm | Final | Reason |
|---|------------|-------|--------|
| D1 | A (loader in config.py) | **A** — keep | Minimal churn; one allowlist exists; defer extraction to future cycle when a 2nd allowlist arrives |
| D2 | B (`wiki/_lint.yml`) | **NEW: `config/lint_allowlist.json` (JSON, new top-level dir)** | Both A and B were gitignored; `config/` is tracked-eligible (`git check-ignore` no-match); JSON keeps stdlib-only parser; new dir avoids cluttering repo root |
| D3 | A (top-of-function early return in `hybrid_search`) | **NEW: env-var check at `kb.query.engine.search_pages` line 205 (production), MIRRORED in `hybrid.py::hybrid_search` (test-only API)** | `hybrid_search` is not in production call graph (R1-B1) |
| D4 | B (defer to BACKLOG) | **A — implement now** | BACKLOG.md:374 mandates the audit-tag clause; deferral blocks BACKLOG-deletion at AC19 (R1-B3) |
| D5 | A (extend test) | **A — keep** | R2-F9's "tautological" claim wrong; `MappingProxyType` is shallow; ~3 lines is cheap defense in depth |
| D6 | A (in-cycle size cap) | **A — keep** | ~3 lines; failure-open is design-mandate; no gating finding |

---

## Revised AC list (22 ACs)

### Already-shipped (verify only at Step 14)

**AC1** — `src/kb/config.py:197-211`: codex CLI argv = `["codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check"]` inside `MappingProxyType`. Verify present.

**AC2** — `src/kb/utils/cli_backend.py:64-69`: `_backend_executable("codex")` returns `"codex.cmd"` on `os.name == "nt"`, else `binary`. Verify present.

**AC3** — `src/kb/utils/cli_backend.py:89-107`: `_postprocess_stdout("codex", stdout_text)` walks JSONL via `splitlines()`, calls `json.loads(line)` per line, captures last `{type:"item.completed", item:{type:"agent_message"}}` text; falls through to `.strip()` for other backends; silently drops malformed lines via `JSONDecodeError continue`. Verify present.

**AC4** — `src/kb/utils/cli_backend.py:84-86`: `_build_cmd("codex", model)` extends `["--model", model]` only when `backend == "codex" and model`. Verify present.

**AC5** — `tests/test_cycle21_cli_backend.py:87-116`: `test_call_cli_codex_exec_jsonl_path` exists. **EXTEND** at Step 9 with 2 lines (D5 sandbox-flag pin per cycle-22 L5 — this is a test-coverage requirement):
```python
# T2 sandbox-flag pin (cycle 61 D5 / threat-model T2)
assert "--sandbox" in cmd and cmd[cmd.index("--sandbox") + 1] == "read-only"
assert "--skip-git-repo-check" in cmd
```

### New implementation (Step 9 work)

**AC6** — `src/kb/config.py`: introduce `@lru_cache(maxsize=1)`-decorated `_get_duplicate_slug_allowlist() -> frozenset[frozenset[str]]`. Reads from `PROJECT_ROOT / "config" / "lint_allowlist.json"` (D2). Returns `frozenset(frozenset(pair) for pair in payload["duplicate_slugs"])`. **MUST NOT** raise on parse failure (failure-open per design Risk row). Schema validation: payload must be `dict`, `payload["duplicate_slugs"]` must be `list[list[str]]` of length-2 entries — anything else → `logger.warning(...)` + return existing `DUPLICATE_SLUG_ALLOWLIST` (the in-code default kept as fallback). **Size cap:** `if path.stat().st_size > 64_000: log warning + return default` (D6). **Module-top file read is FORBIDDEN** (R2-F2). Tests use `_get_duplicate_slug_allowlist.cache_clear()` between cases.
> Current state: `config.py:690-696` `DUPLICATE_SLUG_ALLOWLIST` hardcoded. `lint/checks/duplicate_slug.py:5,61` consumer.
> Migration: `lint/checks/duplicate_slug.py:5` rewrites to `from kb.config import _get_duplicate_slug_allowlist`; line 61 calls `_get_duplicate_slug_allowlist()` instead of referencing the constant. The constant itself stays as the in-code default (failure-open fallback).

**AC7** — `config/lint_allowlist.json` (new file, new dir, tracked): initial payload mirroring the in-code constant. Schema:
```json
{
  "version": 1,
  "_meta": {
    "description": "Duplicate-slug allowlist — pairs of slugs known to represent distinct concepts despite small edit distance. Failure-open: if this file is missing/malformed, kb lint falls back to the in-code default in src/kb/config.py."
  },
  "duplicate_slugs": [
    ["concepts/bot", "concepts/llm"],
    ["entities/openai", "entities/openclaw"],
    ["entities/logql", "entities/promql"]
  ]
}
```
> Verification: `git ls-files config/lint_allowlist.json` returns the path after Step 9 commit.

**AC8** — `tests/test_lint.py`: append `# ── Duplicate-slug allowlist file load (cycle 61) ─` divider then class `TestDuplicateSlugAllowlistFileLoad` with three cases:
   - (a) **file-present custom takes precedence** — write `tmp_kb_env / "config" / "lint_allowlist.json"` with a fake pair `[["a/x", "a/y"]]`; monkeypatch `kb.config.PROJECT_ROOT = tmp_kb_env`; `_get_duplicate_slug_allowlist.cache_clear()`; call `check_duplicate_slugs` on slugs `a/x` and `a/y`; assert pair is allowlisted (no issue returned).
   - (b) **file-missing fallback** — no file written; assert `_get_duplicate_slug_allowlist() == DUPLICATE_SLUG_ALLOWLIST` (the in-code default).
   - (c) **malformed JSON** — write `"{not valid json"` at the path; `caplog.at_level(logging.WARNING)`; assert `_get_duplicate_slug_allowlist() == DUPLICATE_SLUG_ALLOWLIST` AND a WARNING record was emitted; the kb lint run completes (failure-open). Per cycle-16 L2: must reach the production call site (`check_duplicate_slugs`).

**AC9** — `src/kb/config.py`: introduce `_kb_disable_vectors() -> bool` paralleling `cli._is_debug_mode`. Reads env at every call:
```python
def _kb_disable_vectors() -> bool:
    """Return True when KB_DISABLE_VECTORS env-var is truthy.
    Runtime helper (no module-top snapshot) so tests can monkeypatch.setenv
    and the change takes effect mid-test. Pattern: cli._is_debug_mode.
    """
    return os.environ.get("KB_DISABLE_VECTORS", "").strip() in {"1", "true", "True", "yes"}
```
Document in module docstring.
> Current state: zero hits for `KB_DISABLE_VECTORS` in src/kb.

**AC10** — Two-site short-circuit per D3 (production + test API):
   - **PRIMARY (production):** `src/kb/query/engine.py` immediately before line 205 `vector_results = vector_search(question, candidate_limit)`:
     ```python
     if kb.config._kb_disable_vectors():
         vector_results = []
         logger.info("hybrid_search: KB_DISABLE_VECTORS=1 — vector layer skipped")
     else:
         try:
             vector_results = vector_search(question, candidate_limit)
         except Exception as exc:
             logger.warning(...)
             vector_results = []
     ```
     (Refactors the existing try/except into the else branch.) Logs INFO ONCE per `search_pages` call.
   - **MIRROR (test API):** `src/kb/query/hybrid.py::hybrid_search` top-of-function early return:
     ```python
     if kb.config._kb_disable_vectors():
         logger.info("hybrid_search: KB_DISABLE_VECTORS=1 — vector layer skipped")
         return bm25_fn(question, limit)
     ```
> Module-top `from kb.config import _kb_disable_vectors` is acceptable (the function is the binding, not a value). Step 14 verifies via grep.

**AC11** — `tests/test_query.py`: append `# ── KB_DISABLE_VECTORS short-circuit (cycle 61) ─` divider; two tests targeting the **PRODUCTION path** (R1 condition #1):
   - `test_search_pages_skips_vector_when_KB_DISABLE_VECTORS_set`: `monkeypatch.setenv("KB_DISABLE_VECTORS", "1")`; `caplog.at_level(logging.INFO)`; `monkeypatch.setattr(kb.query.embeddings, "get_vector_index", spy)` (or comparable closure entry point); call `search_pages(question="foo", wiki_dir=tmp_wiki, ...)`; assert `spy.call_count == 0` AND `sum(1 for r in caplog.records if "KB_DISABLE_VECTORS=1" in r.getMessage()) == 1`.
   - `test_search_pages_calls_vector_when_KB_DISABLE_VECTORS_unset`: divergent twin — `monkeypatch.delenv("KB_DISABLE_VECTORS", raising=False)`; same caplog setup; assert `spy.call_count >= 1` AND ZERO records matching `"KB_DISABLE_VECTORS=1"`. Per cycle-24 L4 POSITION assertion + cycle-40 L3 revert verification.

**AC12** — `src/kb/mcp/health.py`: new `kb_rebuild_indexes(wiki_dir: str | None = None)` MCP tool:
   - Validates `wiki_dir` via `_validate_wiki_dir(wiki_dir, project_root=PROJECT_ROOT)` (existing pattern at health.py:76).
   - Calls `kb.compile.compiler.rebuild_indexes(wiki_dir=wiki_path, caller="mcp")` (NEW caller= kwarg, threaded to `append_wiki_log`).
   - Wraps OSError / RuntimeError in `f"Error: kb_rebuild_indexes failed: {type(e).__name__}: {sanitize_error_text(e)}"` (no leaked stack — pattern from health.py:88).
   - Returns the rebuild dict verbatim (JSON-serialisable per `compiler.py:642-814`).
   - Does NOT expose `hash_manifest=` / `vector_db=` overrides (thin wrapper per BACKLOG.md:374 Prerequisite).

**AC12.5 / NEW AC22** — `src/kb/utils/wiki_log.py::append_wiki_log` signature extension (R1-B3, BACKLOG.md:374):
   - Add keyword-only `caller: str = "cli"` parameter.
   - When `caller != "cli"`, prepend `caller=<caller> | ` to the audit message.
   - Existing call sites unchanged (default `"cli"`).
   - `kb.compile.compiler.rebuild_indexes` accepts `caller="cli"` default and threads to `append_wiki_log(operation, message, log_path, caller=caller)`.

**AC13** — `tests/test_mcp_browse_health.py`: append divider; class `TestKbRebuildIndexes` with FOUR cases:
   - (a) **happy path** — invoke with valid `wiki_dir`; monkeypatch `rebuild_indexes` to return `{"manifest": "deleted", "vector": "deleted"}`; assert MCP wrapper returns the dict (or string repr per existing tool convention) verbatim, no error wrapping.
   - (b) **invalid wiki_dir** — invoke with `wiki_dir="../../../etc"`; assert response is `"Error: ..."` string (no traceback). Repeat with `"/tmp"` (POSIX) and `"C:\\Windows"` (Windows) per T9.
   - (c) **underlying exception wrapped** — monkeypatch `rebuild_indexes` to raise `OSError("perm denied")`; assert response is `"Error: kb_rebuild_indexes failed: OSError: perm denied"` (no traceback frames).
   - (d) **caller=mcp audit-tag** (NEW per AC22) — invoke happy path; assert the wiki_log entry written contains the literal substring `"caller=mcp"`. Pin against the audit message format.

### Test-quality upgrades (Step 9 work)

**AC14** — `tests/test_lint_query_fixes_v092.py:279,286`: replace 2 `inspect.getsource` substring asserts with behavioral spies on `kb.mcp.health.logger.error` / `.exception`:
   - For `kb_lint`: `monkeypatch.setattr(kb.lint.runner, "run_all_checks", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("forced")))`; spy on `kb.mcp.health.logger.error` and `.exception`; invoke `kb_lint(...)`; assert `error.call_count == 1` AND `exception.call_count == 0`. (R1 patch #8 — `compute_trust_scores` is NOT in `kb_lint`'s try/except; `run_all_checks` IS.)
   - For `kb_evolve`: `monkeypatch.setattr(kb.evolve.analyzer, "generate_evolution_report", ...)`; same spy assertion at health.py:152. (R1 patch #8.)

**AC15** — `tests/test_v0911_phase392.py:245`: replace `inspect.getsource` substring with:
   ```python
   from kb.lint import trends as trends_module
   from kb import config
   assert hasattr(trends_module, "VERDICT_TREND_THRESHOLD")
   assert trends_module.VERDICT_TREND_THRESHOLD == config.VERDICT_TREND_THRESHOLD
   ```
   Add a divergent-fail behavioral test: monkeypatch `trends_module.VERDICT_TREND_THRESHOLD = 0.99`; call the trends function with data that crosses the OLD threshold but NOT the new one; assert the trend signal does NOT fire (the new threshold flowed through). Existing positive test at line 233 retained.

**AC16** — `tests/test_v0915_task01.py:320,331`: 
   - **DROP** the `builder.WIKI_SUBDIRS` identity check (line 320 — `builder.py` does NOT bind `WIKI_SUBDIRS`; the assertion would AttributeError. R1 patch #9). Replace with behavioral test:
     ```python
     def test_build_graph_consumes_shared_WIKI_SUBDIRS(monkeypatch, tmp_wiki):
         from kb.graph import builder
         from kb.utils import pages
         monkeypatch.setattr(pages, "WIKI_SUBDIRS", ("custom_dir",))
         (tmp_wiki / "custom_dir").mkdir()
         (tmp_wiki / "custom_dir" / "page.md").write_text("---\ntitle: t\n---\nbody")
         g = builder.build_graph(wiki_dir=tmp_wiki)
         assert any("custom_dir/page" in str(n) for n in g.nodes)
     ```
   - **KEEP** the analyzer identity check (line 331 — `analyzer.py:20` does `from kb.config import WIKI_SUBDIRS`):
     ```python
     from kb.evolve import analyzer
     from kb import config
     assert analyzer.WIKI_SUBDIRS is config.WIKI_SUBDIRS
     ```

**AC17** — `tests/test_v0915_task08.py:363`: replace `inspect.getsource` regex-absence assertion with divergent-fail behavioral test:
   ```python
   from kb.evolve.analyzer import _FRONTMATTER_RE
   # Old inlined regex was r"\A\s*---" — would match leading whitespace.
   # New shared regex requires `---` at column 0 (no leading whitespace).
   leading_ws_input = "\n---\nfoo: bar\n---\nbody"
   # New shared regex: does NOT match (leading \n violates \A---).
   assert _FRONTMATTER_RE.match(leading_ws_input) is None, (
       "FRONTMATTER_RE should reject leading whitespace; the old inlined "
       r"\A\s*--- regex would have matched. If this assertion fails, the "
       "Phase 4.5 HIGH P3 consolidation has been regressed."
   )
   # Verify shared regex works on canonical input.
   canonical = "---\nfoo: bar\n---\nbody"
   assert _FRONTMATTER_RE.match(canonical) is not None
   ```

**AC18** — `tests/test_compile.py:217` (`test_prune_base_uses_canonical_rel_path_at_both_sites`): C41-L1 behavioral upgrade. **TWO fixtures required:**
   - **Fixture 1 (drift site, REUSE):** the existing `test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted` fixture at line 152-204 builds a stale manifest entry. Reuse this for the drift-site spy.
   - **Fixture 2 (compile_wiki full-mode site, NEW):** write `manifest_path` JSON containing `{"sources": {"articles/x.md": {"sha256": "...", ...}}}` with NO `articles/x.md` on disk; call `compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path, ...)`; assert post-call manifest has no `articles/x.md` key.
   - **Spy assertion:** `monkeypatch.setattr(compiler, "_canonical_rel_path", spy)`; invoke BOTH `compile_wiki(mode="full")` AND `detect_source_drift`; assert `spy.call_count >= 2`.
   - **Divergent-fail (R2-F5):** re-set `_canonical_rel_path` to `lambda s, raw_dir: "FROZEN"` (no-op); assert `articles/x.md` is NOT pruned (the no-op rel-path key misses the prune lookup; original stale entry survives). Test fails if either site bypasses the helper.

### Documentation (Step 17 work)

**AC19** — `BACKLOG.md`:
   - (a) **DELETE** the `wiki/purpose.md KB focus document` entry (already shipped — `kb.utils.pages.load_purpose` wired in `kb.ingest.extractors:357` and `kb.query.engine:1066` per R1).
   - (b) **DELETE** the `mcp/health.py kb_rebuild_indexes MCP tool` entry at line 374 (resolved by AC12 + AC22; caller-tag clause now satisfied).
   - (c) Re-confirm pip / litellm / diskcache / ragas CVE state at 2026-05-03 (per cycle-46+ pattern); update timestamp + cycle-61 marker.
   - (d) **DELETE** the C11-L1 `inspect.getsource` batch entry — AC14-AC17 clear 4 of 5 sites; if any remain (e.g., test_compile.py site is in scope via AC18), keep the entry with the remaining site listed.

**AC20** — `CHANGELOG.md` + `CHANGELOG-history.md`:
   - `CHANGELOG.md` — brief Items / Tests / Scope / Detail entry under `[Unreleased]` Quick Reference (newest first). Items: 22; tests delta: +6 to +10; scope: BACKLOG batch + test-quality + doc-sync; detail: cycle-61 PR placeholder.
   - `CHANGELOG-history.md` — full per-cycle bullet-level archive (newest first), all 22 ACs.

**AC21** — `docs/reference/implementation-status.md` + `CLAUDE.md`:
   - `docs/reference/implementation-status.md` — append cycle-61 section (latest-cycle notes).
   - `CLAUDE.md` — update **State bullet** test/file counts (3022 baseline post d7a98b7 +1 → +6 to +10 from cycle-61 net; 200 → 201 if `config/lint_allowlist.json` counts as a tracked file unit). Add cycle-61 pointer in the Quick Reference. **Note:** `[Unreleased]` is in CHANGELOG.md, not CLAUDE.md (R1 patch #13).

### NEW: AC22 — caller=mcp audit tag pin (R1-B3, BACKLOG.md:374, D4=A)

**AC22** — `src/kb/utils/wiki_log.py::append_wiki_log`:
   - Add keyword-only `caller: str = "cli"` parameter. When `caller != "cli"`, prepend `caller=<caller> | ` to the audit message field. Existing call sites unchanged.
   - `src/kb/compile/compiler.py::rebuild_indexes` accepts `caller: str = "cli"` kwarg, threads to `append_wiki_log(...)` at line 809.
   - `src/kb/mcp/health.py::kb_rebuild_indexes` (AC12) passes `caller="mcp"` to `rebuild_indexes`.
   - `tests/test_mcp_browse_health.py::TestKbRebuildIndexes::test_caller_mcp_audit_tag` (AC13(d)): pin the literal substring `"caller=mcp"` in the wiki_log entry.
   - `tests/test_cli.py` or similar: divergent-fail twin — invoke `kb rebuild-indexes` from CLI (no `caller=` override → default `"cli"`); assert `"caller=mcp"` does NOT appear in the audit message.

---

## Files touched (revised)

| # | File | Type | AC(s) |
|---|---|---|---|
| 1 | `.gitignore` | inherited (verify only) | (covered by d7a98b7) |
| 2 | `src/kb/config.py` | modify | AC6 (allowlist loader + lru_cache), AC9 (_kb_disable_vectors helper) |
| 3 | `src/kb/utils/cli_backend.py` | inherited (verify only) | AC1-AC4 |
| 4 | `src/kb/lint/checks/duplicate_slug.py` | modify | AC6 (consumer call site) |
| 5 | `src/kb/query/engine.py` | modify | AC10 PRIMARY (production short-circuit) |
| 6 | `src/kb/query/hybrid.py` | modify | AC10 MIRROR (test API short-circuit) |
| 7 | `src/kb/mcp/health.py` | modify | AC12 (kb_rebuild_indexes tool) |
| 8 | `src/kb/utils/wiki_log.py` | modify | AC22 (caller= kwarg) |
| 9 | `src/kb/compile/compiler.py` | modify | AC22 (thread caller= to append_wiki_log) |
| 10 | `config/lint_allowlist.json` | new | AC7 |
| 11 | `tests/test_cycle21_cli_backend.py` | modify | AC5 extension (D5 sandbox-flag pin) |
| 12 | `tests/test_lint.py` | modify | AC8 |
| 13 | `tests/test_query.py` | modify | AC11 |
| 14 | `tests/test_mcp_browse_health.py` | modify | AC13 + AC22 audit-tag pin |
| 15 | `tests/test_compile.py` | modify | AC18 |
| 16 | `tests/test_lint_query_fixes_v092.py` | modify | AC14 |
| 17 | `tests/test_v0911_phase392.py` | modify | AC15 |
| 18 | `tests/test_v0915_task01.py` | modify | AC16 |
| 19 | `tests/test_v0915_task08.py` | modify | AC17 |
| 20 | `tests/test_cli.py` (or `test_compile_cli.py`) | modify | AC22 CLI-default caller divergent twin |
| 21 | `BACKLOG.md` | modify | AC19 |
| 22 | `CHANGELOG.md` | modify | AC20 |
| 23 | `CHANGELOG-history.md` | modify | AC20 |
| 24 | `docs/reference/implementation-status.md` | modify | AC21 |
| 25 | `CLAUDE.md` | modify | AC21 |

**Total:** 25 file slots (4 inherited verify-only, 9 source modify, 1 source new, 9 test modify, 5 doc modify). 22 ACs.

---

## Cycle-62 parallel-cycle audit

`git worktree list` confirms cycle-62 is at the same base commit `d7a98b7` as cycle-61. Cycle-62's `git status` shows 16 modified files + 19 deleted versioned test files (the SAME 19+ that cycle-59 already folded in committed form: `test_v01002_consolidated_constants.py`, `test_v01004_query_correctness.py`, `test_v01005_query_perf_docs.py`, `test_v01006_compile_fixes.py`, `test_v01010_lint_fixes.py`, `test_v0917_*` family, `test_v4_11_*` family, `test_v5_*` family) + 4 uncommitted design docs (`2026-05-03-cycle-62-{design,plan,requirements,self-review}.md`). Cycle-62 has no remote branch (per the briefing context). **State: ABANDONED-LOOKING — duplicate work to cycle-59, no commits, no PR.**

**Cycle-61 file overlap with cycle-62:** `tests/test_lint.py`, `test_query.py`, `test_compile.py` (all cycle-62 receivers AND cycle-61 AC8 / AC11 / AC18 sites); `BACKLOG.md`, `CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md`, `docs/reference/implementation-status.md` (all cycle-62 doc updates AND cycle-61 AC19 / AC20 / AC21 sites). **Mechanical-rebase risk only — no logical collision.** Cycle-61 EOF-section appends use `# ── <description> (cycle 61) ─` dividers per R2-F7 alignment; cycle-62 (if it ever commits) would use a different marker. If cycle-62 commits before cycle-61's PR lands, conflicts on the test files are EOF-section appends (resolve via `git rebase` choosing both); BACKLOG/CHANGELOG/CHANGELOG-history conflicts are section-append shapes (resolve via merge tool with chronological ordering). **Cycle-61 proceeds.** Document the awareness in CHANGELOG-history.md per AC20 (one-line note: "Parallel cycle-62 worktree present at d7a98b7 base; abandoned-looking; no rebase coordination needed").

Parallel-cycle audit (full):

| Cycle | Branch | HEAD | State | Cycle-61 collision |
|---|---|---|---|---|
| 53 | `worktree-cycle-53` | `6e1eace` | 4 fold commits ahead of main | Mechanical-rebase risk on test_compile.py / test_config.py / test_query.py (EOF-only per R1 verification of cycle-59 fold pattern) |
| 59 | `feat/cycle-59` | `aa5bacf` | 3 commits ahead, doc-update tail | Mechanical-rebase risk on test_lint.py / test_query.py / test_compile.py + others (EOF appends with `(cycle 59 fold)` markers) |
| 62 | `feat/cycle-62` | `d7a98b7` | uncommitted, abandoned-looking | Mechanical-rebase risk on test_lint.py / test_query.py / test_compile.py + BACKLOG / CHANGELOG / CHANGELOG-history / CLAUDE / docs/reference/implementation-status (no remote branch; no commits to coordinate against) |

---

## CONDITIONS for plan-gate approval

Per cycle-22 L5: each numbered bullet below is a **test-coverage requirement**, not a nice-to-have. Step-9 self-check must verify each.

1. **AC10 PRIMARY production short-circuit at `kb.query.engine.search_pages` line 205.** AC11 must invoke `search_pages` (or `query_wiki`) and spy on `kb.query.embeddings.get_vector_index` (the actual closure entry point at engine.py:144). Cycle-16 L2 + cycle-18 L1 + cycle-40 L3 revert verification mandatory (comment out the short-circuit, run pytest -x, expect FAIL; restore).

2. **AC10 MIRROR at `hybrid.py::hybrid_search` top-of-function.** A second test (under same divider) targeting the test-only API surface: invoke `hybrid_search(question, bm25_fn=spy_bm25, vector_fn=spy_vec)` with env set; assert `spy_vec.call_count == 0` AND `spy_bm25.call_count == 1`.

3. **AC11 INFO-log capture + divergent twin.** Two tests: env-set asserts ONE `KB_DISABLE_VECTORS=1` INFO record AND `get_vector_index.call_count == 0`; env-unset asserts ZERO matching records AND `get_vector_index.call_count >= 1`. Per cycle-24 L4 POSITION assertions.

4. **AC6/AC7 path = `config/lint_allowlist.json`.** Plan must NOT propose any path under `wiki/` or `.data/`. Verify via `git check-ignore -v config/lint_allowlist.json` (should return empty/no-match) before Step 9.

5. **AC9 implementer note.** Use `_kb_disable_vectors() -> bool` helper (function call) in `kb.config`. NO module-top constant. Tests use `monkeypatch.setenv("KB_DISABLE_VECTORS", "1")` (preferred — exercises real env) OR `monkeypatch.setattr(kb.config, "_kb_disable_vectors", lambda: True)` (function patch). Step 14 grep guard: `grep -rnE "^\s*KB_DISABLE_VECTORS\s*[:=]" src/kb/config.py` should match ONLY the function definition line, not a module-top assignment.

6. **AC22 caller=mcp implementation.** Plan must include: `append_wiki_log(operation, message, log_path, *, caller: str = "cli")` signature extension; `rebuild_indexes(..., caller="cli")` thread; `kb_rebuild_indexes(...)` passes `caller="mcp"`; AC13(d) test pins `"caller=mcp"` substring in wiki_log entry; AC22 CLI-default twin pins `"caller=mcp"` does NOT appear when invoked from CLI.

7. **AC14 patch target correction.** Use `kb.lint.runner.run_all_checks` (NOT `compute_trust_scores`) for kb_lint; `kb.evolve.analyzer.generate_evolution_report` for kb_evolve. Both call sites: health.py:84 (kb_lint) → except line 86; health.py:150 (kb_evolve) → except line 152. Verified.

8. **AC16 builder behavioral test.** Plan must DROP the `builder.WIKI_SUBDIRS` identity check (line 320 — `builder.py:24` is comment-only; AttributeError) and replace with `build_graph` behavioral test using `monkeypatch.setattr(kb.utils.pages, "WIKI_SUBDIRS", ...)`. Keep analyzer identity check (line 331 — `analyzer.py:20` does import).

9. **AC17 divergence reproducer concrete.** Plan uses input `"\n---\nfoo: bar\n---\nbody"`: assert old `\A\s*---` regex would match (sanity check on a literal string), new shared `_FRONTMATTER_RE.match(input) is None` proves the shared regex is in use.

10. **AC18 dual fixture concrete.** Plan must explicitly build (a) drift-site reuse from line 152-204 AND (b) NEW compile_wiki(mode="full") fixture (manifest entry `articles/x.md` without on-disk file). Spy `_canonical_rel_path`; assert `call_count >= 2`. Divergent-fail twin (no-op lambda → stale entry NOT pruned).

11. **AC5 D5 sandbox-flag pin.** Add 2 lines to existing test (`# T2 sandbox-flag pin (cycle 61 D5)`).

12. **AC6 D6 size cap.** Add `if path.stat().st_size > 64_000: log warning + return default` to loader.

13. **Cycle-59 / 53 / 62 collision protection.** EOF-section appends use `# ── <description> (cycle 61) ─` dividers (R2-F7 aligned). Test files: test_lint.py (AC8), test_query.py (AC11), test_compile.py (AC18). Doc files (BACKLOG / CHANGELOG / CHANGELOG-history / CLAUDE / docs/reference/implementation-status): section-append shape; cycle-61 entries dated 2026-05-03 and tagged `cycle 61`.

14. **Step 14 verification rows (10 per threat-model + 1 per AC22).** T1 model-name regex test, T2 sandbox-flag pin (D5), T5 size cap (D6), T7 lru_cache identity (`_get_duplicate_slug_allowlist.cache_info().hits >= 1` after 2 calls), T8 INFO log capture (AC11), T9 path-traversal triplet (`../`, `/tmp`, `C:\\`), T10 wrapped-exception no-stack (AC13(c)), T12 caller=mcp audit-tag (AC22), T13 grep guard for module-top KB_DISABLE_VECTORS, AC22 CLI-default twin. **Ten rows.**

15. **Test count delta accounting.** AC21 expected delta: +6 to +10 from new tests (AC8 ×3, AC11 ×2, AC13 ×4, AC22 ×1) less 0 from upgrades (AC14-AC17 CONVERT in place, no count change) + 1 from AC18 divergent-fail twin = **+10 maximum, +6 minimum**. Update CLAUDE.md State bullet accordingly.

16. **Step 24 trial telemetry rows.** Document per cycle-61 design Step 24 telemetry section (mimo wall-clock, R2 DeepSeek divergence on the BLOCKER set, etc.). No new conditions; carry forward.

---

## Verdict

**APPROVE.** All 3 R1 BLOCKERS and 6 R2 HIGH gaps have concrete decisions baked into the revised 22-AC list with file:line targets. AC count rises 21 → 22 (caller=mcp audit-tag absorbed as AC22). D-decisions reconciled: D2 → `config/lint_allowlist.json`, D4 → flip to A. Cycle-62 awareness documented; rebase risk is mechanical-only. Step 7 plan can read this document standalone without re-reading R1/R2.
