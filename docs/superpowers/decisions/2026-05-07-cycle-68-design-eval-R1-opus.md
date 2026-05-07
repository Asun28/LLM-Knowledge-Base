# Cycle 68 — Step 4 Design Evaluation R1 (Opus)

**Date:** 2026-05-07/08 (NZT)
**Reviewer:** Opus 4.7 subagent
**Inputs read:**
- `docs/superpowers/decisions/2026-05-07-cycle-68-requirements.md` (15 ACs)
- `docs/superpowers/decisions/2026-05-07-cycle-68-brainstorm.md` (alternatives for AC07-AC10 + AC14-AC15)
- `docs/superpowers/decisions/2026-05-07-cycle-67-design.md` (19 binding CONDITIONS for carry-overs)
- `docs/superpowers/decisions/2026-05-07-cycle-67-threat-model.md` (cycle-68 threat-model.md NOT YET PRESENT — using cycle-67 as prior)
- `src/kb/graph/cache.py` (canonical `get_graph(wiki_dir, *, pages=None)` at lines 108-127)
- `src/kb/evolve/analyzer.py` (3 sites: lines 28, 127, 358)
- `src/kb/graph/export.py` (1 site: line 83)
- `src/kb/mcp/browse.py` (1 site: line 345)
- `src/kb/query/engine.py` (1 site: line 408)
- `src/kb/lint/checks/duplicate_slug.py` + `src/kb/config.py:808` (DUPLICATE_SLUG_ALLOWLIST baseline)
- `pyproject.toml:29` (`httpx>=0.27`) + `requirements.txt:91` (`httpx==0.28.1`) + `src/kb/lint/fetcher.py:51` (`_HTTPX_SUPPORTED_PREFIX = "0.28."`)
- `BACKLOG.md` lines 1-130 (cleanup target list + cycle-67 audit comment block)
- `CHANGELOG.md` lines 1-80 (cycle-67 ship verification)

## Verdict

**APPROVE-WITH-AMENDMENTS** — 0 BLOCKER, 4 MAJOR, 3 MINOR. All resolvable inline; Step 5 binds 5 new conditions on top of cycle-67's 19 carry-over conditions.

## Carry-over acknowledgment

- **AC01** (Popen refactor) — carry-over from cycle-67 design.md C-AC03-{stdin,platform,stderr,error-kinds} + FW-1; inherited verbatim.
- **AC02** (`MAX_CLI_STDERR_BYTES` constant) — carry-over from cycle-67 design.md C-AC03-stderr; inherited verbatim.
- **AC03** (`_lint_yaml.py` lazy loader) — carry-over from cycle-67 design.md C-AC07-{safe,fallback,schema} + FW-2; inherited verbatim.
- **AC04** (externalize `DUPLICATE_SLUG_ALLOWLIST`) — carry-over from cycle-67 design.md C-AC07-fallback; inherited verbatim.
- **AC05** (`audit_docstrings.py`) — carry-over from cycle-67 design.md C-AC12-generator + FW-4 + R1-F4 transition; inherited verbatim.
- **AC06** (CI docstring-audit step) — carry-over from cycle-67 design.md R1-F4; inherited verbatim.
- **AC11** (`tests/test_cycle68_cli_backend_popen.py`) — carry-over from cycle-67 C-AC03-{stdin,platform,stderr,error-kinds}; inherited verbatim.
- **AC12** (`tests/test_cycle68_lint_yaml.py`) — carry-over from cycle-67 C-AC07-{safe,fallback,schema}; inherited verbatim.
- **AC13** (`tests/test_cycle68_audit_docstrings.py`) — carry-over from cycle-67 C-AC12-generator; inherited verbatim.

## Findings — NEW items (AC07-AC10 + AC14-AC15)

### F1 — AC07/AC08 [MAJOR] Site-count discrepancy: requirements says "5 sites across 4 files", actual is 6 sites across 4 files

Grep of `build_graph` in `src/kb/` confirms 6 call sites: `evolve/analyzer.py` lines 28, 127, 358 (3 sites — requirements doc and brainstorm both count this file as 3); `graph/export.py:83`; `mcp/browse.py:345`; `query/engine.py:408`. **Sum = 6, not 5.** Requirements doc line 51 ("Total cycle-68 migration: 5 sites across 4 files") is off-by-one. Brainstorm line 36 is internally consistent ("5 sites" but enumerates `evolve/analyzer.py ×3`, totalling 6 with the other three files — also off-by-one).

The actual migration set is 3 of 6 (the pages=None ones): `analyzer.py:127`, `export.py:83`, `browse.py:345`. The other 3 (`analyzer.py:28`, `analyzer.py:358`, `engine.py:408`) supply `pages=` and per cache.py:125-127 BYPASS the cache; they MUST stay on `build_graph` per the cycle-64 contract. Brainstorm Pick A explicitly says this; requirements doc AC07/AC08 wording ("migrate 3 build_graph call sites" / "migrate remaining build_graph call sites") is consistent only if interpreted as "migrate THE PAGES-NONE call sites in those files" — not all sites.

**Resolution:** MODIFY — Step 7 plan must explicitly enumerate the 3 migratable sites by `(file, line, current-arg-shape)` and the 3 pages-supplying sites that MUST remain on `build_graph`. Step 9 implementer needs an unambiguous to-touch list to avoid touching pages-supplying sites (which would silently alter cycle-64 cache-bypass semantics). Step 5 binds C-AC07-sites enumerating exactly: `evolve/analyzer.py:127` (pages-None), `graph/export.py:83` (pages-None), `mcp/browse.py:345` (pages-None) → migrate; the other 3 stay.

### F2 — AC07/AC08 [MAJOR] AC14 AST guard cannot blanket-forbid `build_graph` in migrated files

The requirements doc AC14 wording ("zero `ast.Call` with `func.attr == 'build_graph'` outside `kb.graph.cache` module") would FAIL on `evolve/analyzer.py:28` and `analyzer.py:358` (pages-supplying call sites that must STAY on `build_graph`). The brainstorm (lines 144-155) correctly distinguishes by `pages=` kwarg presence: `pages_supplied = pages_kw is not None and not (...None constant...)` — assert pages_supplied for any surviving `build_graph` call. The requirements doc wording is over-broad; brainstorm's AST guard formulation is correct.

**Resolution:** MODIFY — Step 5 binds the AST guard formulation from brainstorm lines 144-155 verbatim (pages-supplied predicate, not blanket forbid). The guard tolerates `build_graph(wiki_dir, pages=...)` where `pages` is anything other than the literal `None` constant; flags any `build_graph(...)` lacking `pages=` or with `pages=None`. Cycle-67 AC02 AST guard (forbid `from kb.graph.cache import get_graph`) protects a DIFFERENT invariant (cache-module import shape) and does not conflict — confirmed.

### F3 — AC07/AC08 [MINOR] Cache invalidation responsibility — confirmed read-only

Brainstorm Open Question #1 asks whether any of the 4 migrated files mutates the wiki and therefore needs `kb.graph.cache.invalidate(wiki_dir)`. Reviewed:
- `evolve/analyzer.py` — read-only (`analyze_coverage`, `find_connection_opportunities`, `suggest_new_pages`, `generate_evolution_report`, `format_evolution_report`). No filesystem writes.
- `graph/export.py:83` — read-only Mermaid export.
- `mcp/browse.py:345` — read-only `wiki_stats`.
- `query/engine.py:408` — read-only PageRank computation.

**Confirmed:** all 4 are read-only consumers; no `invalidate(wiki_dir)` call needed post-`get_graph`. Per CLAUDE.md mutator list (`ingest_source`, `refine_page`, `compile_wiki`), invalidation responsibility stays with those modules.

**Resolution:** ACCEPT — no further action. Step 5 documents this as a verified non-issue.

### F4 — AC09 [MINOR] httpx pin upper bound — verify no transitive `httpx<0.28` constraint

Requirements doc AC09 tightens `pyproject.toml` from `httpx>=0.27` to `httpx>=0.28,<0.29`. Verification:
- `requirements.txt` already pins `httpx==0.28.1` (lockfile-style); upgrade compatible.
- `lint/fetcher.py:51` runtime guard `_HTTPX_SUPPORTED_PREFIX = "0.28."` matches the proposed pin EXACTLY.
- `pytest-httpx>=0.30` (pyproject.toml:49) — pytest-httpx 0.30+ supports httpx 0.28 (per its release notes; the dev-extra pin is loose).
- `pyproject.toml [project.dependencies]` does not pin any transitive consumer of httpx. The only direct httpx clamps are `httpx>=0.27` (augment extra, line 29) and `pytest-httpx>=0.30` (dev extra, line 49). No `httpx<0.28` clamp exists anywhere.

The pin is safe. fetcher.py:53-59 actually raises `RuntimeError` (NOT `AssertionError` — minor brainstorm inaccuracy at line 64) on version mismatch — the brainstorm Pick A is correct, the side-comment about "raise AssertionError" is wrong but doesn't affect the design decision (a runtime guard either way).

**Resolution:** ACCEPT pin formulation `httpx>=0.28,<0.29`. Step 5 notes the brainstorm's `AssertionError` typo and confirms `RuntimeError` is the actual guard at fetcher.py:54.

### F5 — AC10 [MAJOR] BACKLOG cleanup — verify each entry is genuinely shipped + cycle-68-self-reference defer

Cross-referenced the 18 enumerated cleanup targets (requirements doc line 55) against `BACKLOG.md` lines 33-118 (cycle-67 audit comment block) AND `CHANGELOG.md` cycle-67 entry (line 32):

| Target | Audit-claim status | Verified shipped? | Notes |
|--------|-------------------|-------------------|-------|
| GitPython unpinned | shipped cycle 67 Step 15 | YES | CHANGELOG line 32 lists `GitPython 3.1.47 → 3.1.49 (CVE-2026-44244)` |
| SSRF on URL → external CLI | VERIFIED STALE | YES | Audit comment line 35; cycle-67 OOS-1 |
| KB_PROJECT_ROOT call-time | shipped cycle 65 AC1 | YES | OOS-2 |
| _autouse_kb_path_sandbox no-drop | shipped cycle 67 AC08 | YES | CHANGELOG line 32 |
| hardcoded lru_cache list | shipped cycle 17 AC16 | YES | Audit comment line 39 |
| trafilatura+diskcache | shipped cycle 65 (TRAFILATURA_DOWNLOAD_NO_CACHE=1) | YES | OOS-12 |
| `_DEFAULT_MODEL_TIERS` dual mechanism | shipped cycle 67 AC01 | YES | CHANGELOG line 32 — actual surface was MODEL_TIERS |
| AUGMENT_ALLOWED_DOMAINS | shipped cycle 65 AC3 | YES | OOS-3 |
| MCP error responses raw tracebacks | shipped cycle 65 AC21 | YES | OOS-5 |
| `_check_no_secrets_on_argv` self-DoS | VERIFIED INCORRECT | YES | Cycle 67 AC15 added 6 lock-in tests |
| graph/cache.py 6th-caller drift | shipped cycle 67 AC02 | YES | CHANGELOG line 32 |
| `tests/test_cycle64_snapshots.py` tautology | shipped cycle 67 AC09 | YES | CHANGELOG line 32 |
| CI sk-ant-dummy grep | shipped cycle 67 AC11 | YES | CHANGELOG line 32 |
| docs/reference INDEX.md | shipped cycle 65 AC20 + cycle 67 AC14 | YES | CHANGELOG line 32 |
| 3 cycle-68 carry-over entries (AC03/AC07/AC12) | becomes AC01-AC06+AC11-AC13 in cycle 68 | DEFER | BACKLOG lines 55-59 — DELETE only at Step 17 of THIS cycle, NOT in AC10 |
| `auto_publish_after_compile` exceptions swallowed | shipped cycle 67 AC04 | YES | CHANGELOG line 32 (`KB_STRICT_PUBLISH=1`) |
| `kb.query.hybrid` `KB_DISABLE_VECTORS=1` | shipped cycle 67 AC06 | YES | CHANGELOG line 32 |
| README `KB_PROJECT_ROOT` bootstrap | shipped cycle 67 AC13 | YES | CHANGELOG line 32 (Non-clone install section) |
| `compile/compiler.py:645` validator drift | shipped cycle 66 AC5 | NEEDS VERIFICATION | Not explicitly in cycle-67 audit comment; check cycle-66 changelog |
| `mcp/app.py:230` Windows trailing-dot | shipped cycle 65 AC6 | YES | OOS-6 |

**Subtle issue:** the "3 cycle-68 carry-over entries" listed at requirements doc line 55 SHOULD NOT be deleted during AC10 cleanup — they are the CURRENT cycle's tracking entries (BACKLOG.md lines 55-59 "CYCLE 68 carry-over"). Their deletion happens at cycle-68 Step 17 after AC01-AC06+AC11-AC13 SHIP. Including them in AC10 risks a documentation gap (BACKLOG would say "nothing in flight" while cycle-68 is mid-flight).

**Resolution:** MODIFY — Step 5 binds C-AC10-current-cycle-deferred: AC10 deletes the 18 OTHER entries during early Step-7 ordering (per FW-6: AC10 → AC07 → AC08 → ...). The 3 cycle-68 carry-over entries (BACKLOG lines 55-59) are deleted at Step 17 doc-update by the doc subagent, AFTER AC01/03/05 + AC11/12/13 ship. Document this split in the AC10 task plan. Also: verify `compile/compiler.py:645` validator drift entry is actually in BACKLOG before listing it for deletion (one entry not corroborated in the cycle-67 audit comment).

### F6 — AC14 [MAJOR] AST guard divergent-fail must be revert-tolerant + test name precision

Brainstorm AST guard (lines 129-155) is well-designed (pages-supplied predicate per F2). Cycle-11 L2 + cycle-23 L2 + cycle-24 L4 vacuous-test rules require: re-introducing `build_graph(wiki_dir)` (without `pages=...`) into ANY of the 3 migrated files MUST make the test FAIL with file:line of the regression. Verified the brainstorm's `assert pages_supplied` formulation does this.

But: the brainstorm test scopes to `migrated = [evolve/analyzer.py, graph/export.py, mcp/browse.py, query/engine.py]`. Per F1, `analyzer.py:28` and `analyzer.py:358` are pages-supplying and MUST stay on `build_graph`. The AST guard's `assert pages_supplied` correctly tolerates these (they'd pass) — verified. But the test name `test_no_direct_build_graph_pages_none_calls_in_migrated_files` (brainstorm line 129) is more precise than the requirements doc name `test_no_direct_build_graph_calls_in_migrated_files` (line 80) — the latter could mislead a future maintainer into thinking the assertion is "no `build_graph` at all".

**Resolution:** MODIFY — Step 5 binds the test name from brainstorm (`test_no_direct_build_graph_pages_none_calls_in_migrated_files`), NOT the requirements doc name. The behavioural test (`test_get_graph_cache_hit_on_repeat_call` at brainstorm lines 111-124) is correctly designed and revert-tolerant per cycle-23 L2.

### F7 — AC15 [MINOR] Test parsing rigor

Both AC15 sub-tests must use parsed structure, not substring grep, per cycle-11 L2 + cycle-24 L4:

- **`test_pyproject_httpx_pin_has_explicit_ceiling`** — must use `tomllib.loads(Path("pyproject.toml").read_text())` and walk `data["project"]["optional-dependencies"]["augment"]` to find the httpx entry, then assert the constraint string contains `>=0.28` AND `<0.29`. Raw substring grep on the file would also match comments / unrelated `httpx` mentions.
- **`test_backlog_does_not_contain_shipped_phase_4_5_high_entries`** — must parse BACKLOG.md by section (`## Phase 6 R2 ...` headers + `### HIGH/MEDIUM/LOW` subheaders) and assert each shipped-entry's bullet text is ABSENT from the open-work bullets (NOT from comment blocks like the audit-comment block at lines 33-53 which legitimately mentions them by name as ship-receipts). A naive `"GitPython unpinned" in BACKLOG.read_text()` would FAIL because the audit comment cites it as the receipt; the parsed-structure test must scope to `<bullets in HIGH/MEDIUM/LOW sections>`, NOT the HTML-comment receipts block.

**Resolution:** MODIFY — Step 5 binds C-AC15-parsed-structure: both AC15 tests parse via `tomllib` and markdown structure-aware iteration (skip HTML comments, scope to bullet lists under specific section headers). Step 7 task wording must include this constraint to avoid mimo-implementer regressing to substring grep.

## Conditions for Step 05 to bind (5 NEW)

| # | ID | AC | Source | Test pin |
|---|-----|-----|--------|----------|
| 1 | C-AC07-sites | AC07/AC08 | F1 | Step 7 enumerates exactly: `evolve/analyzer.py:127`, `graph/export.py:83`, `mcp/browse.py:345` for migration; `evolve/analyzer.py:28`, `evolve/analyzer.py:358`, `query/engine.py:408` STAY on `build_graph` (pages-supplying) |
| 2 | C-AC07-ast-guard-shape | AC14 | F2, F6 | AST guard uses `assert pages_supplied` (brainstorm 144-155); test name `test_no_direct_build_graph_pages_none_calls_in_migrated_files` |
| 3 | C-AC07-no-invalidate | AC07/AC08 | F3 | Confirmed read-only — no `kb.graph.cache.invalidate(wiki_dir)` call needed; documented in Step 5 |
| 4 | C-AC10-current-cycle-deferred | AC10 | F5 | The 3 cycle-68 carry-over entries (BACKLOG lines 55-59) deferred to Step 17 doc-update; the 18 OTHER entries deleted in Step-7 AC10 task. Verify `compile/compiler.py:645` entry exists before listing |
| 5 | C-AC15-parsed-structure | AC15 | F7 | `test_pyproject_httpx_pin_has_explicit_ceiling` uses `tomllib.loads`; `test_backlog_does_not_contain_shipped_phase_4_5_high_entries` parses markdown structure (skip HTML comments, scope to `### HIGH/MEDIUM/LOW` bullets only) |

## Analysis (extended thinking — required for Opus 4.7)

### Step 1 — Carry-over verification

Carry-over ACs (cycle-68 AC01-AC06, AC11-AC13) inherit cycle-67 design.md verbatim with 19 binding CONDITIONS. No re-evaluation needed per the Step-04 dispatch instructions (cycle-68 brainstorm lines 8-10). Acknowledged in carry-over section above. Cycle-67 AC02 AST guard (forbid `from kb.graph.cache import get_graph`) shipped successfully — its protected invariant is the IMPORT SHAPE for the cache module, and is independent from cycle-68 AC14's NEW AST guard which protects the CALL SITE form for `build_graph` in 4 specific files. No conflict.

### Step 2 — AC07/AC08 — graph cache caller migration

Read cache.py:108-127 carefully. The contract is:
- `pages is not None`: bypass cache, call `build_graph(wiki_dir, pages=pages)` directly.
- `pages is None`: lookup by `(wiki_dir.resolve().as_posix(), max_mtime_of_wiki_subdirs)`; cache-hit returns; cache-miss builds, stores, evicts, returns.

So `get_graph(wiki_dir)` (positional, no `pages=` kwarg) is the cache-using entry. Migrating `build_graph(wiki_dir)` → `kb.graph.cache.get_graph(wiki_dir)` preserves the pages-None semantics with the cache benefit.

But callers like `evolve/analyzer.py:28` use `build_graph(wiki_dir, pages=pages)` — these supply `pages=` and MUST stay on `build_graph` per the cache-bypass contract. Migrating them to `get_graph(wiki_dir, pages=pages)` would also bypass the cache (per cache.py:125-127), so the migration would be functionally equivalent but ADDS an unnecessary indirection. YAGNI: leave them on `build_graph`.

This means the 6 sites split:
- 3 migratable (pages-None): `analyzer.py:127`, `export.py:83`, `browse.py:345`
- 3 stay on build_graph (pages-supplying): `analyzer.py:28`, `analyzer.py:358`, `engine.py:408`

The requirements doc and brainstorm both say "5 sites across 4 files" but the file-line evidence shows 6 sites across 4 files. That's F1 (MAJOR — Step 7 needs explicit enumeration to avoid implementer confusion).

### Step 3 — AC09 httpx pin

Read fetcher.py:51 carefully: `_HTTPX_SUPPORTED_PREFIX = "0.28."`. The runtime guard at lines 53-59 raises `RuntimeError` (not `AssertionError` as brainstorm claims at line 64) on version mismatch. The proposed pin `httpx>=0.28,<0.29` matches the prefix exactly. requirements.txt:91 already locks `httpx==0.28.1` (compatible). pytest-httpx>=0.30 (dev) compatible. No transitive `httpx<0.28` clamp anywhere.

The brainstorm correctly REJECTS the suggestion to soften the runtime guard to a logged warning (per BACKLOG.md suggested fix). Keeping the hard guard preserves the loud failure mode that motivated the pin. APPROVE Pick A.

### Step 4 — AC10 BACKLOG cleanup

Cross-referenced the 18 enumerated entries against cycle-67 changelog and BACKLOG audit comment block. 17 of 18 are verifiable shipped (cited in CHANGELOG.md cycle-67 line 32 OR cycle-67 OOS list). The 18th (`compile/compiler.py:645` validator drift) is mentioned in requirements doc but not corroborated in the cycle-67 audit comment block — needs explicit verification at Step 7.

The most subtle issue: requirements doc lists "the 3 cycle-68 carry-over entries" for deletion in AC10. But these entries (BACKLOG.md lines 55-59) are the cycle-68 cycle's OWN tracking entries — deleting them BEFORE cycle-68 ships its AC01-AC06+AC11-AC13 work creates a documentation gap (BACKLOG would say "nothing in flight" while cycle-68 is mid-flight). Defer their deletion to Step 17 doc-update, after the carry-over work ships. F5 (MAJOR).

### Step 5 — AC14/AC15 vacuous-test prevention

Applied cycle-11 L2 + cycle-16 L2 + cycle-23 L2 + cycle-24 L4 + user memories `feedback_inspect_source_tests`, `feedback_test_behavior_over_signature`:

- AC14 AST guard: brainstorm formulation correct (pages-supplied predicate); revert-tolerant. Test name in requirements doc is over-broad and would mislead — bind brainstorm's more precise name. F6 (MAJOR).
- AC14 behavioural spy test: brainstorm formulation (lines 111-124) correctly uses `monkeypatch.setattr(kb.graph.builder, "build_graph", spy)` (owner-module form per cycle-18 L1). Reverting `get_graph` body to bypass cache makes this test FAIL — verified.
- AC15 httpx pin test: must use `tomllib`, not raw substring. F7 (MINOR).
- AC15 BACKLOG cleanup test: must use parsed markdown structure, scope to bullets under `### HIGH/MEDIUM/LOW` headers (NOT HTML comments which legitimately reference shipped items). F7 (MINOR).

### Step 6 — Verdict synthesis

0 BLOCKER (no choice that fails at Step 09 or Step 14). 4 MAJOR (F1 site count, F2 AST guard formulation, F5 BACKLOG cleanup completeness + cycle-68-self-reference defer, F6 AST guard test naming). 3 MINOR (F3 verified read-only, F4 httpx pin verified, F7 parsed-structure tests). All resolvable inline via 5 new conditions on top of cycle-67's 19 carry-over conditions.

**Final verdict:** APPROVE-WITH-AMENDMENTS. Step 5 binds the 5 new conditions; Step 7 plan dispatch must quote C-AC07-sites + C-AC07-ast-guard-shape + C-AC15-parsed-structure verbatim per FW pattern (cycle-67 design.md FW-1 through FW-6 precedent).
