# Backlog

<!-- FORMAT GUIDE — read before adding items
Each phase section groups items by severity, then by module area.
Resolved phases collapse to a one-liner; active phases list every item.

## Severity Levels

| Level      | Meaning                                                        |
|------------|----------------------------------------------------------------|
| CRITICAL   | Data loss, crash with no recovery, or security exploit — blocks release |
| HIGH       | Silent wrong results, unhandled exceptions reaching users, reliability risk |
| MEDIUM     | Quality gaps, missing test coverage, misleading APIs, dead code |
| LOW        | Style, docs, naming, minor inconsistencies — fix opportunistically |

## Item Format

```
- `module/file.py` `function_or_symbol` — description of the issue
  (fix: suggested remedy if non-obvious)
```

Rules:
- Lead with the file path (relative to `src/kb/`), then the function/symbol.
- Include line numbers only when they add precision (e.g. `file.py:273`).
- End with `(fix: ...)` when the remedy is non-obvious or involves a design choice.
- One bullet = one issue. Don't combine unrelated problems.
- When resolving an item, delete it (don't strikethrough). Record a brief newest-first summary in CHANGELOG.md and put implementation detail in CHANGELOG-history.md.
- Move resolved phases under "## Resolved Phases" with a one-line summary.
- Changelog order rule: all changelog entries are newest first by date. CHANGELOG.md stays brief; CHANGELOG-history.md carries the detail.
-->

---

## Cross-reference

| File | Role | Update rule |
|------|------|-------------|
| **BACKLOG.md** ← you are here | Open work only, ranked by severity | Add on discovery; **delete** on resolve |
| [CHANGELOG.md](CHANGELOG.md) | Brief shipped-change index, newest first | Add compact Items / Tests / Scope / Detail entry for every shipped cycle |
| [CHANGELOG-history.md](CHANGELOG-history.md) | Detailed shipped-change archive, newest first | Add or move full per-cycle details here; keep CHANGELOG.md brief |

**Resolve lifecycle:** Delete item here → add brief entry in `CHANGELOG.md [Unreleased]` → add detail in `CHANGELOG-history.md` → done.

> **For all LLMs (Sonnet 4.6 · Opus 4.7 · Codex/GPT-5.4):** BACKLOG = open work; CHANGELOG = shipped fixes. If an item says _"see CHANGELOG"_, it is resolved and can be safely deleted from this file.

---

## Phase 4 (v0.10.0) — Post-release audit

_All items resolved — see `CHANGELOG.md` `[Unreleased]`._

---

## Phase 4.5 — Multi-agent post-v0.10.0 audit (2026-04-13)

<!-- Discovered by 5 specialist reviewers (Python, security, code-review, architecture, performance)
     running 3 sequential rounds against v0.10.0 after the Phase 4 HIGH/MEDIUM/LOW audit shipped.
     Items grouped by severity, keyed by file. Round tag in parens (R1/R2/R3). -->

### CRITICAL

_All items resolved — see CHANGELOG `[Unreleased]` Phase 4.5 cycle 1, cycle 1-docs-sync, and Backlog-by-file cycle 4._

<!-- Cycle 4 closed (2026-04-17): #1 _rel() error-string sweep, #2 <prior_turn> sentinel +
     fullwidth angle-bracket fold + control-char strip, #5 Error[partial] on post-create
     OSError in kb_ingest_content/kb_save_source, #7 kb_read_page body cap with [Truncated:]
     footer, #11 kb_affected_pages check_exists=True, #12 add_verdict per-issue cap,
     #13 _validate_page_id Windows-reserved + 255-char cap, #14 kb_detect_drift source-deleted
     category, #15 query/rewriter CJK short-query gate, #16+#18 BM25 cache-invalidation,
     #17 type-diversity quota in dedup, #18 STOPWORDS prune, #19 yaml_sanitize BOM +
     U+2028/9 strip, #20 wiki_log monthly rotation, #22 detect_contradictions_with_metadata
     caller migration, #23 export_mermaid Path-shim, #24 BM25Index postings precompute,
     #25 _template_hashes VALID_SOURCE_TYPES whitelist, #28 load_purpose(wiki_dir) required,
     #29 inject_wikilinks caller-side sorted().
     Deferred: #3 [source: X] → [[X]] citation migration (tracked as dedicated atomic migration). -->

### HIGH

- `compile/compiler.py` naming inversion (~16-17) — `compile_wiki` is a thin orchestration shell over `ingest_source` + a manifest; real compilation primitives (`linker.py`) live in `compile/` but are consumed by `ingest/`. Dependency arrows invert the directory names; every new feature placement becomes a coin-flip. (R1)
  (fix: rename to `pipeline/orchestrator.py` and treat `compile/` as wikilink primitives only; or collapse `compile/compiler.py` into `kb.ingest.batch`)

- `ingest/pipeline.py` state-store fan-out — a single `ingest_source` mutates summary page, N entity pages, N concept pages, `index.md`, `_sources.md`, `.data/hashes.json`, `wiki/log.md`, `wiki/contradictions.md`, plus N `inject_wikilinks` writes across existing pages. Every step is independently atomic, none reversible. A crash between manifest-write (step 6) and log-append (step 7) leaves the manifest claiming "already ingested" while the log shows nothing; a mid-wikilink-injection failure leaves partial retroactive backlinks. (R2)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests; retries idempotent at step granularity)

- `graph/builder.py` no shared caching policy — cycle 6 added a query-side PageRank cache and preloaded-page threading for `kb_query`, and cycle 7 threaded page bundles through several callers, but the graph layer itself still has no reusable cache/invalidation contract. `lint/runner.py` and `lint/checks.py` can still rebuild graphs independently in one lint pass, and no policy doc defines when graph-derived caches are invalidated after ingest/refine. (R2; query hot-path portion resolved in CHANGELOG `[Unreleased]` "Backlog-by-file cycle 6")
  (fix: `kb.graph.cache` keyed on `(wiki_dir, max_mtime_of_wiki_subdirs)`; share within lint/evolve/query call stacks; invalidate at end of `ingest_source` + `refine_page`; document in CLAUDE.md alongside the manifest contract)

- `tests/` coverage-visibility — ~50 of 94 files are named `test_v0NNN_taskNN.py` / `test_v0NNN_phaseNNN.py` / `test_phase4_audit_*.py`. To verify `evolve/analyzer.py` has tier-budget coverage you must grep ~50 versioned files because canonical `test_evolve.py` has only 11 tests (none touch numeric tokens, redundant scans, or three-level break — all open in Phase 4.5 MEDIUM). `_compute_pagerank_scores` is searched across 25 files. (R3)
  (fix: freeze-and-fold rule — once a version ships, fold its tests INTO the canonical module file (`test_v0917_dedup.py` → `test_query.py::class TestDedup`); enable `coverage` in CI and surface per-module % in PR comments)

- `tests/conftest.py` `project_root` / `raw_dir` / `wiki_dir` leak surface — fixtures point at REAL `PROJECT_ROOT` and are documented as "read-only use" but nothing enforces it. `test_cli.py:61-63` proves the global-escape paths exist (multi-global monkeypatch). Phase 4.5 already flagged `WIKI_CONTRADICTIONS` leaking, `load_purpose()` reading the real file, `append_wiki_log` defaulting to production. Phase 5 will add `wiki/hot.md`, `wiki/overview.md`, `wiki/_schema.md`, `raw/captures/` — one more leak surface each. (R3; cycle 7 only added autouse embeddings reset)
  (fix: make read-only fixtures fail loudly — return paths under a sandbox by default; provide explicit `real_project_root` fixture requiring `pytest --use-real-paths`; autouse monkeypatch of all `WIKI_*` constants to `tmp_path` for tests that don't explicitly opt out)

- `mcp/core.py` + `browse.py` + `health.py` + `quality.py` — all 25 MCP tools are sync `def`. FastMCP runs them via `anyio.to_thread.run_sync` on a default 40-thread pool. A `kb_query(use_api=True)` (30s+), `kb_lint()` (multi-second disk walk), `kb_compile()` (minutes), or `kb_ingest_content(use_api=True)` (10+s) each hold a thread; under concurrent tool calls the pool saturates and subsequent calls queue. Claude Code often fires multiple tool calls in parallel; this turns invisible latency spikes into observed user-facing stalls. (R3; cycle 7 did not address)
  (fix: make long-I/O tools `async def` and `await anyio.to_thread.run_sync(...)` around the SDK call; or document / tune `FastMCP(num_threads=N)`; at minimum surface the concurrency model in the `app.py` instructions block)


- `ingest/pipeline.py:603,715-721,729-754` lock acquisition order risk between same-ingest stages — within one `ingest_source`: stage 1 writes summary page (line 609) → `append_evidence_trail` to SAME page; stage 2 calls `_update_existing_page` on each entity (re-reads + re-writes); stage 9 `inject_wikilinks` re-reads + re-writes some of the SAME pages it just wrote in stages 1-3; stage 11 writes `wiki/contradictions.md`. None use `file_lock`. Within ONE process this is OK. Under concurrent ingest A + B, the read-then-write windows in different stages of A overlap with different stages of B in non-deterministic order; debugging becomes impossible because each `kb_ingest` run shows different conflict patterns. R5 highlights the **systemic absence of any locking discipline across the entire 11-stage ingest pipeline** — a problem that compounds with every Phase 5 feature. (R5)
  (fix: introduce a per-page write-lock helper `with page_lock(page_path):` wrapping `read_text → modify → atomic_text_write` and use consistently across `_write_wiki_page`, `_update_existing_page`, `append_evidence_trail`, and `inject_wikilinks`; OR adopt a coarse wiki-wide ingest mutex)

### HIGH — Deferred

> HIGH-severity items either surfaced after cycle-2 shipped or explicitly deferred from Phase 4.5 HIGH cycle-1 for a dedicated follow-up cycle.

- `query/embeddings.py` vector-index lifecycle — Phase 4.5 HIGH cycle 1 shipped H17 hybrid (mtime-gated rebuild + batch skip). Cycle-25 AC3/AC4/AC5 shipped the *observability* variant of sub-item (3 — dim-mismatch): `VectorIndex.query` logs operator-actionable remediation (`kb rebuild-indexes --wiki-dir <path>`) on mismatch + module-level `_dim_mismatches_seen` counter + `get_dim_mismatch_count()` getter. Cycle-26 AC1-AC5 shipped the *observability* variant of sub-item (2 — cold-load latency): `maybe_warm_load_vector_model(wiki_dir)` daemon-thread warm-load hook wired into `kb.mcp.__init__.main()`, `_get_model()` instrumented with `time.perf_counter` + INFO log on every load + WARNING above 0.3s threshold, and `get_vector_model_cold_load_count()` process-level counter. Cycle-28 AC1-AC5 shipped the *observability* variant of the remaining first-query latency sources: `VectorIndex._ensure_conn` sqlite-vec extension load instrumented with `time.perf_counter` + INFO + WARNING above `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS=0.3` + `_sqlite_vec_loads_seen` counter + `get_sqlite_vec_load_count()` getter (locked via `_conn_lock` for exact counts), AND `BM25Index.__init__` corpus-indexing instrumented with INFO log (no WARN threshold per Q1 — corpus-size variance defeats fixed threshold) + lock-free `_bm25_builds_seen` counter (approximate, cycle-25 Q8 precedent) + `get_bm25_build_count()` getter. Sub-item (1) atomic temp-DB-then-replace rebuild SHIPPED cycle 24 (AC5/AC6/AC8 — `os.replace` on `<vec_db>.tmp` with cache-pop+close before replace + crash-cleanup). Sub-item (4) `_index_cache` cross-thread lock symmetry shipped incrementally across cycles 3/6/24. Remaining true-deferred: (a) dim-mismatch AUTO-rebuild (needs `VectorIndex` to hold `wiki_dir` or callback + concurrent-rebuild idempotency design).

### MEDIUM

<!-- Cycle 1 closed (2026-04-17): D1 _build_schema_cached deepcopy, E1 ingest/contradiction.py
     logger placement + tokens hoist + single-char language names, F1 kb_create_page O_EXCL,
     G1 kb_list_sources cap, F2 kb_refine_page caps, C2 _TEXT_EXTENSIONS library enforcement,
     J1 query/rewriter length guard, I2 search_raw_sources BM25 cache, I1 _flag_stale_results
     UTC, K1 _dedup_by_text_similarity tokens, M1 lint/verdicts load_verdicts mtime cache. -->

- `config.py` god-module — 35+ unrelated constants (paths, model IDs, BM25 hyperparameters, dedup thresholds, retries, ingest/evolve/lint limits, retention caps, query budgets, RRF, embeddings). Single-file churn invalidates import cache for the whole package in tests. (R1)
  (fix: split into `config/paths.py` / `config/models.py` / `config/limits.py` / `config/search.py` / `config/lint.py`; or a `Settings` dataclass with grouped subfields; keep `from kb.config import *` shim)

- `compile/compiler.py` `compile_wiki` per-source rollback — Cycle-25 AC6/AC7/AC8 shipped the narrow observability variant: `in_progress:{pre_hash}` marker written before each `ingest_source`, overwritten on success (by ingest_source's own manifest write) or replaced with `failed:{pre_hash}` by the existing exception handler. AC7's entry-scan logs a warning for any stale `in_progress:` markers from prior hard-kills/power-loss. CONDITION 13 exempts `in_progress:` values from full-mode prune. Remaining deferred: (a) rollback of wiki writes on manifest-save failure (harder — requires receipt-file design or transaction-like helper), (b) escalating manifest-write failure to CRITICAL (cycle-25 keeps the `logger.warning` best-effort stance). (R1)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests.)

- `utils/io.py` `atomic_json_write` + `file_lock` pair — 6+ Windows filesystem syscalls per small write (acquire `.lock`, load full list, serialize, `mkstemp` + `fdopen` + `replace`, release). Cycle-24 AC9 added exponential backoff to `file_lock` (floor 10ms, cap 50ms), eliminating the fixed 50ms polling floor. The JSONL-migration part remains open. (R1)
  (fix: append-only JSONL with `msvcrt.locking` / `fcntl` locking; compact on read or via explicit `kb_verdicts_compact`)

- `lint/fetcher.py` `diskcache==5.6.3` — CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v): pickle-deserialization RCE in diskcache cache files. No patched upstream version as of 2026-04-24 (Re-checked 2026-04-24 per cycle-25 AC9: `pip index versions diskcache` shows 5.6.3 = LATEST INSTALLED; `pip-audit --format=json` reports empty `fix_versions` for the CVE).
  (mitigation: diskcache is only used by trafilatura's robots.txt cache; exploit requires local write access to the cache directory; `grep -rnE "diskcache|DiskCache|FanoutCache" src/kb` confirms zero direct imports in our code; track upstream for a patched release)

- `requirements.txt` `ragas==0.4.3` — CVE-2026-6587 (GHSA-95ww-475f-pr4f): server-side request forgery in `_try_process_local_file` / `_try_process_url` of `ragas.metrics.collections.multi_modal_faithfulness.util`. No patched upstream release as of 2026-04-25 (Re-confirmed per cycle-32 Step 11: `pip-audit` reports empty `fix_versions`; `pip index versions ragas` shows 0.4.3 = LATEST INSTALLED; vendor did not respond to disclosure — identical no-upstream-fix profile to diskcache). ragas is a dev-eval-only dep (used manually for evaluation harness work); `grep -rnE "ragas|Ragas" src/kb` confirms zero runtime imports. Re-check on the next cycle's Step-2 baseline.
  (mitigation: confirmed zero `src/kb/` imports; dev-eval-only usage means an attacker would need local Python access to run `python -c "from ragas..."` themselves — no remote reach. Track for patched release.)

- `requirements.txt` `litellm==1.83.0` — GHSA-xqmj-j6mv-4862 (high) + GHSA-r75f-5x8p-qvmc (critical): LiteLLM Proxy endpoints render user-supplied templates without sandboxing (arbitrary code execution inside proxy process). Fix available for both at `litellm==1.83.7`, but `litellm==1.83.7` pins `click<8.2` as a hard transitive constraint which ResolutionImpossible conflicts with our `click==8.3.2` pin (required for cycle 31 + cycle 32 CLI wrappers). *(Surfaced 2026-04-25 cycle 32 Step 11 PR-CVE diff + Step 11.5 Dependabot alerts #13/#14; advisory landed between Step 2 baseline and Step 11 per cycle-22 L4.)*
  (mitigation: narrow-role exception per feature-dev Step 11 — LiteLLM is a dev-eval-only dep (ragas evaluation harness); `grep -rnE "import litellm|from litellm" src/kb` confirms zero runtime imports in kb; we never start LiteLLM Proxy mode, so the vulnerable proxy endpoints are unreachable. Unblock path: wait for litellm to relax the click<8.2 transitive, or vendor a narrower pin; re-check next cycle.)

- `requirements.txt` `pip==26.0.1` — CVE-2026-3219 (GHSA-58qw-9mgm-455v): pip handles concatenated tar+ZIP files as ZIP regardless of filename, enabling confusing installation behavior. No patched upstream as of 2026-04-25 (`pip-audit` reports empty `fix_versions`). *(Surfaced 2026-04-25 cycle 32 Step 11 PR-CVE diff; cross-cycle advisory arrival per cycle-22 L4.)*
  (mitigation: narrow-role — pip is TOOLING, not runtime; advisory affects package installation (`pip install` of adversarial tar+zip payloads) which requires local shell access. Production kb runtime never shells out to pip. Track upstream for patched release.)

- `compile/linker.py` cross-reference auto-linking — deferred: when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` added to A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`.

- `compile/publish.py` compile-time auto-publish hook — deferred: hook `kb publish` into `compile_wiki` so every compile auto-emits the Tier-1 + sibling + sitemap outputs. Cycle 16 shipped the sibling + sitemap BUILDERS standalone; the auto-hook into compile remains deferred pending a dedicated cycle.

- `compile/publish.py` manifest-based incremental sibling cleanup — deferred from cycle 16 Q2/C3 resolution: cycle 16 cleanup is O(|excluded|) unconditional unlinks per publish. When N(retracted) exceeds ~1000 a `.data/publish-siblings-manifest.json` atomic-state approach becomes preferable; defer until retracted-page counts warrant.

- `ingest/pipeline.py` index-file write order (~653-700) — per ingest: `index.md` → `_sources.md` → manifest → `log.md` → `contradictions.md`. A crash between `_sources.md` and manifest writes can duplicate entries on re-ingest. (R2)
  (fix: introduce an `IndexWriter` helper wrapping all four writes with documented order and recovery)

- `mcp/core.py:762,881` — `kb_ingest_content` / `kb_save_source` post-create OSError path emits `Error[partial]: write to {_rel(file_path)} failed ({write_err}); retry ...` but `{write_err}` interpolation bypasses the `_rel()` path scrub. On Windows an `OSError.__str__()` typically includes the full absolute path (`[WinError 5] Access is denied: 'D:\\Projects\\...\\raw\\articles\\foo.md'`). Cycle-32 AC3 newly routes these strings to CLI stderr via `_is_mcp_error_response` widening, so the leak surfaces to operator terminals under write-failure conditions. *(Surfaced 2026-04-25 cycle 32 threat model T11.)*
  (fix: wrap `{write_err}` in `_sanitize_error_str(write_err, file_path)` — the same helper that the success-path log at `core.py:756-760` uses. One-line change per site.)

- `ingest/pipeline.py` `_update_existing_page` body-write + evidence-append two-write consolidation — Cycle-24 AC1 shipped single-atomic-write inline rendering for `_write_wiki_page` (new-page path), eliminating the two-write race there. Cycle-24 AC2 shipped typed error surfacing for `_update_existing_page` failures (`StorageError(kind="evidence_trail_append_failure")`). Remaining deferred: true single-write consolidation for the update path — the existing body must be preserved across ingests, so pre-rendering the trail with all historical entries is infeasible without a broader evidence-trail refactor. *(Narrowed 2026-04-23 cycle 24: previously combined entry covered both paths; AC1 + AC2 closed the new-page + error-surfacing portions.)*
  (fix: `_update_existing_page` RMW flow could buffer the existing trail bytes in memory, append the new entry, write both body and trail under a single lock — requires the cycle-19 `file_lock` discipline + sentinel-anchor search from AC14.)

- CLI ↔ MCP parity — `cli.py` exposes 24 commands (cycle-27 shipped `search` / `stats` / `list-pages` / `list-sources`; cycle-30 AC2-AC6 shipped `graph-viz` / `verdict-trends` / `detect-drift` / `reliability-map` / `lint-consistency`; cycle-31 AC1-AC3 shipped `read-page` / `affected-pages` / `lint-deep` via the same function-local-import thin-wrapper pattern, plus a shared `_is_mcp_error_response` discriminator retrofitted into `stats` / `reliability-map` / `lint-consistency` for non-colon MCP error shapes; cycle-32 AC1/AC4 shipped `compile-scan` / `ingest-content` closing category (b) and widened the discriminator with `"Error["` for the `Error[partial]:` tagged-error emitter). MCP exposes 28 tools. Remaining gap = 7: (a) write-path tools `kb_review_page` / `kb_refine_page` / `kb_query_feedback` / `kb_save_source` / `kb_save_lint_verdict` / `kb_create_page` / `kb_capture` — deferred to a write-path input-validation cycle. Note: `kb_save_synthesis` is NOT an MCP tool — it's the `save_as=` parameter on `kb_query` (cycle 16). Structured `--format=json` output across both surfaces still open. (R2)
  (fix: auto-generate CLI subcommands from the FastMCP tool registry; or collapse MCP + CLI onto a shared `kb.api` service module — also kills the function-local-import issue cleanly)

- `compile/compiler.py` `compile_wiki` (~279-393) — a 50-line `for source in changed: ingest_source(source)` loop + manifest save. CLAUDE.md describes compile as "LLM builds/updates interlinked wiki pages, proposes diffs, not full rewrites" — no second pass, no cross-source reconciliation, no diff proposal exists in code. MCP `kb_compile` and `kb compile` CLI are cosmetic wrappers. Phase 5's two-phase compile / pre-publish gate / cross-source merging would land in the wrong layer because `compile_wiki` has no batch context. (R2)
  (fix: make `compile_wiki` a real two-phase pipeline (collect extractions → reconcile cross-source → write) and document the contract; or rename to `batch_ingest` and stop pretending compile is distinct)

- `tests/` no golden-file / snapshot tests — grep for `snapshot`/`golden`/`syrupy`/`inline_snapshot`/`approvaltests` returns zero hits. Wiki rendering (`_build_summary_content`, `append_evidence_trail`, contradictions append, `build_extraction_prompt`, `_render_sources`, Mermaid export, lint report) is verified only by `assert "X" in output`. `test_v0917_evidence_trail.py` checks `"## Evidence Trail" in text` — the actual format (order of `date | source | action`, prepend direction, whitespace) is unverified. Phase 5's output-format polymorphism (`kb_query --format=marp|html|chart|jupyter`), `wiki/overview.md`, and `wiki/_schema.md` all produce structured output that LLM-prompt tweaks silently reformat. (R3)
  (fix: add `pytest-snapshot` or `syrupy`; start with frontmatter rendering, evidence-trail format, Mermaid output, lint report format; commit `tests/__snapshots__/`)

### LOW

_All items resolved — see CHANGELOG cycle 28._

<!-- Cycle 13 closed: AC7 sweep_orphan_tmp on kb.cli:cli boot ({.data, WIKI_DIR}); AC8 +
     _resolve_raw_dir helper derives run_augment raw_dir from wiki_dir.parent / "raw" when
     wiki_dir is overridden and raw_dir omitted.
     Cycle 28 closed (2026-04-24): CHANGELOG cycle-27 commit-tally rule documented
     in CHANGELOG.md format-guide (self-referential +1 per cycle-26 L1); entry
     deleted as resolved. -->

---

## Phase 5 pre-merge (feat/kb-capture, 2026-04-14)

<!-- Discovered by 6 specialist reviewers (security, logic, performance, reliability, maintainability, architecture)
     running Rounds 1 and 2 against feat/kb-capture. Primary scope: new kb.capture module + supporting changes.
     Items grouped by severity, keyed by file. Round tag in parens (R1/R2). -->

<!-- 2026-04-17 cleanup pass verified R1/R2/R3 HIGH, MEDIUM, and LOW items fixed in capture.py;
     remaining entries below are genuinely open. -->

### CRITICAL

- `capture.py:341-372, 428-460` two-pass write architecture needed — STRUCTURAL: `alongside_for[i]` is a frozen list built from Phase A slugs and never recomputed after a Phase C slug reassignment. Items 0..i-1 already written to disk retain `captured_alongside` entries pointing at item i's Phase A slug (which was never written) under cross-process collision. Only complete fix is two-pass: Pass 1 = `O_EXCL`-reserve all N slugs with retry; Pass 2 = compute `alongside_for` from finalized slugs, write all files. Documented as "v1 limitation" in `_write_item_files` docstring. (R3)
  (fix: implement two-pass `_write_item_files`; OR keep TODO(v2) marker and document explicitly in `CaptureResult` docstring)

### MEDIUM

---

## Phase 5 — Community followup proposals (2026-04-12)

<!-- Feature proposals sourced from Karpathy X post (Apr 2, 2026), gist thread, and 12+ community fork repos.
     Full rationale, attribution, and sources: research/karpathy-community-followup-2026-04-12.md
     These are FEATURE items, not bugs — severity buckets here = LEVERAGE (High / Medium / Low).
     "effort" in the parenthetical replaces "fix" in the bug format. -->

### RECOMMENDED NEXT SPRINT — Karpathy gist re-evaluation (2026-04-13)

<!-- Ranked priority derived from re-reading Karpathy's gist against current state.
     All items below already exist as entries in the leverage-grouped subsections — this block only SEQUENCES them.
     Rationale: research/karpathy-community-followup-2026-04-12.md §Prioritized roadmap additions + 2026-04-13 ranking pass.
     Ranking axes: (1) Karpathy-verbatim fidelity, (2) unsolved-gap coverage, (3) effort vs leverage. -->

**Tier 1 — Karpathy-verbatim behaviors the project can't yet reproduce:**
<!-- Tier 1 #1 (`kb_query --format=…` output adapters) SHIPPED in Phase 4.11 (2026-04-14). -->
<!-- Tier 1 #2 (`kb_lint --augment`) SHIPPED in Phase 5.0 (2026-04-15). -->
1. `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen — makes the wiki retrievable by other agents; renderers over existing frontmatter/graph. Cross-ref: HIGH LEVERAGE — Output-Format Polymorphism.
2. `wiki/_schema.md` vendor-neutral schema + `AGENTS.md` thin shim — Karpathy: *"schema is kept up to date in AGENTS.md"*; enables Codex / Cursor / Gemini CLI / Droid portability without forking schema per tool. Cross-ref: LOW LEVERAGE — Operational.

**Tier 2 — Epistemic integrity (unsolved-gap closers every community voice flagged):**
5. `belief_state: confirmed|uncertain|contradicted|stale|retracted` frontmatter — cross-source aggregate orthogonal to per-source `confidence`. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
6. `kb_merge <a> <b>` + duplicate-slug lint check — catches `attention` vs `attention-mechanism` drift; top-cited contamination failure mode in the thread. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
7. `kb_query` coverage-confidence refusal gate — refuses low-signal queries with rephrase suggestions instead of synthesizing mediocre answers. Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.
8. Inline `[EXTRACTED]` / `[INFERRED]` / `[AMBIGUOUS]` claim tags with `kb_lint_deep` sample verification — complements page-level `confidence` with claim-level provenance; directly answers "LLM stated this as sourced fact but it's not in the source." Cross-ref: HIGH LEVERAGE — Epistemic Integrity 2.0.

**Tier 3 — Ambient capture + security rail (distribution UX):**
9. `.llmwikiignore` + pre-ingest secret/PII scanner — missing safety rail given every ingest currently sends full content to the API. Cross-ref: HIGH LEVERAGE — Ambient Capture & Session Integration.
10. `SessionStart` hook + `raw/` file watcher + `_raw/` staging directory — ship as a three-item bundle that eliminates the "remember to ingest" step. Cross-ref: HIGH LEVERAGE — Ambient Capture & Session Integration.

**Recommended next target:** #1 (`/llms.txt` + `/llms-full.txt` + `/graph.jsonld` auto-gen). Reasons: with output adapters (Phase 4.11) and reactive gap-fill (Phase 5.0) shipped, the next-highest Karpathy-fidelity item is the machine-consumable publish format — renderers over existing frontmatter + graph, low effort, makes the wiki itself a retrievable source for other agents. Contained blast radius in `kb.compile.publish` (new module) + compile-pipeline hook.

**Already in flight (excluded from ranking):** `kb_capture` MCP tool (spec landed 2026-04-13 in `docs/superpowers/specs/2026-04-13-kb-capture-design.md`), `wiki/purpose.md` KB focus document (shipped 2026-04-13, commit `d505dca`).

**Explicit scope-out from this re-evaluation pass (keep deferred to Phase 6 or decline):**
- `kb_consolidate` sleep-cycle pass — high effort; overlaps with existing lint/evolve; defer until lint is load-bearing.
- Hermes-style independent cross-family supervisor — infra-heavy (second provider + fail-open policy); Phase 6.
- `kb_drift_audit` cold re-ingest diff — defer until `kb_merge` + `belief_state` land (surface overlap).
- `kb_synthesize [t1, t2, t3]` k-topic combinatorial synthesis — speculative; defer until everyday retrieval is saturated.
- `kb_export_subset --format=voice` for mobile/voice LLMs — niche; defer until a second-device use case emerges.
- Multi-agent swarm + YYYYMMDDNN naming + capability tokens (redmizt) — team-scale pattern; explicit single-user non-goal.
- RDF/OWL/SPARQL native storage — markdown + frontmatter + wikilinks cover the semantic surface.
- Ed25519-signed page receipts — git log is the audit log at single-user scale.
- Full RBAC / compliance audit log — known and acknowledged ceiling; document as a README limitation rather than fix.
- Hosted multiplayer KB over MCP HTTP/SSE — conflicts with local-first intent.
- `qmd` CLI external dependency — in-process BM25 + vector + RRF already ships.
- Artifact-only lightweight alternative (freakyfractal) — sacrifices the persistence that is the reason this project exists.
- FUNGI 5-stage rigid runtime framework — same quality gain expected from already-deferred two-step CoT ingest.
- Synthetic fine-tuning of a personal LLM on the compiled wiki — over the horizon.

### HIGH LEVERAGE — Epistemic Integrity 2.0

<!-- `belief_state` vocabulary + validate_frontmatter integration SHIPPED in cycle 14 AC1/AC2 (2026-04-20). Cross-source propagation rules in lint/checks.py remain deferred. -->

- `ingest/pipeline.py` `source` subsection-level provenance — allow `source: raw/file.md#heading` or `raw/file.md:L42-L58` deep-links in frontmatter; ingest extractor captures heading context so citations point at the actual section that grounds the claim. Source: Agent-Wiki (kkollsga, gist — two-hop citation traceability).
  (effort: Medium — extractor update + citation renderer + backlink resolver for the new form)

- `lint/drift.py` `kb_drift_audit` — cold re-ingest a random sample of raw sources with no prior wiki context, diff against current wiki pages, surface divergence as "potential LLM drift" warnings. Different from existing `kb_detect_drift` which checks source mtime changes; this catches *wiki-side* drift where compilation has diverged from source truth. Source: Memory Drift Prevention (asakin, gist — cites ETH Zurich study: auto-generated context degraded 5/8 cases).
  (effort: Medium — new module; reuse existing `ingest_source` with `wiki_dir=tmp` then diff)

- `compile/merge.py` `kb_merge <a> <b>` — MCP tool merges two pages, updates all backlinks across `wiki/` and `wiki/outputs/`, archives absorbed page to `wiki/archive/` with a redirect stub, one git commit per merge. Source: Louis Wang.
  (effort: Medium — duplicate-slug detection is tracked separately in Phase 4.5 MEDIUM)

<!-- `query/engine.py` coverage-confidence gate SHIPPED in cycle 14 AC5 (fixed refusal template). LLM-suggested rephrasings remain deferred — see "kb_query low-coverage advisory LLM-suggested rephrasings" above. -->

<!-- `models/` `authored_by` frontmatter vocabulary + validate_frontmatter SHIPPED in cycle 14 AC1/AC2. Query-weight boost + lint human-auto-edited flag SHIPPED in cycle 15. -->

- `ingest/pipeline.py` `lint/semantic.py` inline claim-level confidence tags — emit `[EXTRACTED]`, `[INFERRED]`, `[AMBIGUOUS]` inline markers in wiki page bodies during ingest; modify ingest LLM prompts to annotate individual claims at source; `kb_lint_deep` spot-verifies a random sample of EXTRACTED-tagged claims against the raw source file, flagging hallucinated attributions. Complements page-level `confidence` frontmatter without replacing it; directly answers "LLM stated this as sourced fact but it's not in the source." Source: llm-wiki-skill confidence annotation + lint verification model.
  (effort: Medium — ingest prompt update + regex claim parser + lint spot-check against raw source text)

- `lint/checks.py` `lint/semantic.py` claim-to-source grounding verification — after ingest, sample N claims from each wiki page and verify they have supporting text in the cited `raw/` source via BM25 search over the source file body. Pages where sampled claims score below a minimum BM25 match threshold get `belief_state: uncertain` written back and a lint warning emitted. Distinct from `kb_drift_audit` (which diffs wiki-side drift from re-ingest) and inline claim tags (which annotate at write time): this is a retroactive, probabilistic check that catches hallucinated citations in already-written pages. Addresses the central critique — an LLM can write plausible-sounding claims with valid source citations that never appear in the source. Source: cycle 21 epistemic hardening audit.
  (effort: High — BM25 scorer over raw-source text; sample selector; frontmatter write-back via `save_page_frontmatter`; lint integration; tunable N and threshold in `config.py`)

- `models/frontmatter.py` `lint/checks.py` multi-source confirmation gate — `belief_state: confirmed` currently requires no corroboration; a single source can produce `confidence: stated` which reviews to `confirmed`. Add a `source_count` field (auto-incremented by `ingest_source` each time an existing page gains a new source reference) and a lint rule that flags `belief_state: confirmed` on pages with `source_count < 2` as `belief_state: uncertain`. Makes "confirmed" mean "corroborated by ≥ 2 independent raw sources" — the minimum epistemic bar for high-confidence claims. Source: cycle 21 epistemic hardening audit.
  (effort: Medium — `source_count` tracking in `_update_existing_page`; lint check in `lint/checks.py`; frontmatter validator update; migration: existing pages without the field treated as `source_count: 1`)

### HIGH LEVERAGE — Output-Format Polymorphism

<!-- `query/formats/` `kb_query --format=…` adapters SHIPPED in Phase 4.11 (2026-04-14). -->

<!-- `compile/publish.py` `/llms.txt` + `/llms-full.txt` + `/graph.jsonld` SHIPPED in cycle 14 AC20-AC22 (2026-04-20) with `kb publish` CLI subcommand. Atomic writes + incremental publish SHIPPED in cycle 15. Auto-compile hook + per-page sibling `.txt`/`.json` files + `/sitemap.xml` remain deferred — see Phase 4.5 MEDIUM. -->

### MEDIUM LEVERAGE — Synthesis & Exploration

- `lint/consolidate.py` `kb_consolidate` — scheduled async background pass modeled on biological memory consolidation: NREM (new events → concepts, cross-event pattern extraction), REM (contradiction detection → mark old edges `superseded` rather than delete), Pre-Wake (graph health audit). Runs as nightly cron at scan tier. Source: Anda Hippocampus (ICPandaDAO).
  (effort: High — three distinct sub-passes; overlaps with existing lint/evolve but with "superseded" edge state as new primitive)

- `query/synthesize.py` `kb_synthesize [t1, t2, t3]` — k-topic combinatorial synthesis: walks paths through the wiki graph across a k-tuple of topics to surface cross-domain connections. New query mode beyond retrieval. Source: Elvis Saravia reply (*"O(n^k) synthesis across k domains — stoic philosophy × saas pricing × viral content × parenting"*).
  (effort: Medium — graph traversal + synthesis prompt; budget-gate k≥3 since path count explodes)

- `export/subset.py` `kb_export_subset <topic> --format=voice` — emit a topic-scoped wiki slice (standalone blob) loadable into voice-mode LLMs or mobile clients. Addresses *"interactive podcast while running"* use case. Source: Lex-style reply.
  (effort: Low — topic-anchored BFS + single-file markdown bundle)

### HIGH LEVERAGE — Ambient Capture & Session Integration

- `ingest/session.py` — auto-ingest Claude Code / Codex CLI / Cursor / Gemini CLI session JSONLs as raw sources. Distinct from `kb_capture` (user-triggered, any text) and deferred "conversation→KB promotion" (positive-rated query answers only): this is ambient, runs on every session. Source: Pratiyush/llm-wiki.
  (effort: Medium — JSONL parsers per agent + dedup against existing raw/conversations/)

- `hooks/` `SessionStart` hook + `raw/` file watcher — hooks auto-sync on every Claude Code launch; file watcher with debounce triggers ingestion on new files in `raw/` without explicit CLI invocation. Source: Pratiyush/llm-wiki + Memory-Toolkit (IlyaGorsky, gist).
  (effort: Low — Claude Code hook + `watchdog` file observer)

- `ingest/filter.py` `.llmwikiignore` + secret scanner — pre-ingest regex-based secret/PII filter (API keys, tokens, passwords, paths on `.llmwikiignore`); rejects or redacts before content leaves local. Missing safety rail given every ingest currently sends full content to the API. Source: rohitg00 LLM Wiki v2 + Louis Wang security note.
  (effort: Low — `detect-secrets`-style regex list + glob-pattern ignore)

- `_raw/` staging directory — vault-internal drop-and-forget directory for clipboard pastes / rough notes; next `kb_ingest` promotes to `raw/` and removes originals. Distinct from `raw/` (sourced documents) and deferred `kb_capture` (explicit tool). Source: Ar9av/obsidian-wiki.
  (effort: Low — directory convention + promotion step in ingest)

<!-- Per-subdir source_type inference already implemented as `detect_source_type` at src/kb/ingest/pipeline.py:288-301 (cycle 14 Step 5 confirmed: AC13-15 dropped as duplicates). -->


### MEDIUM LEVERAGE — Refinements to existing Phase 5 deferred items

- Deferred "multi-signal graph retrieval" — use empirical weights 3 (direct link) / 4 (source-overlap) / 1.5 (Adamic-Adar) / 1 (type-affinity). Source: nashsu/llm_wiki (concrete ratios from production use).
  (effort: N/A — parameter choice for the existing deferred item)

- Deferred "community-aware retrieval boost" — Louvain intra-edge density <0.15 = "sparse/weak" threshold; surface sparse communities in `kb_evolve`. Source: nashsu.
  (effort: N/A — threshold choice)

<!-- Per-platform `SOURCE_DECAY_DAYS` dict + `decay_days_for` helper SHIPPED in cycle 14 AC10/AC11. Cycle 15 wired call sites into `_flag_stale_results` and lint staleness scan, and shipped the topic volatility multiplier. -->

<!-- `CONTEXT_TIER1_SPLIT` 60/20/5/15 constants + `tier1_budget_for` helper SHIPPED in cycle 14 AC7/AC8. Cycle 15 wired `_build_query_context` to `tier1_budget_for("wiki_pages")`. -->

- Deferred "graph topology gap analysis" — expose as card types: "Isolated (degree ≤ 1)", "Bridge (connects ≥ 3 clusters)", "Sparse community (cohesion < 0.15)" — each with one-click trigger that dispatches `kb_evolve --research` on the specific gap. Source: nashsu.
  (effort: N/A — card-type taxonomy for existing deferred item)

### LOW LEVERAGE — Testing Infrastructure

- `tests/test_e2e_demo_pipeline.py` hermetic end-to-end pipeline test — single test driving `ingest_source` → `query_wiki` → `run_all_checks` over the committed `demo/raw/karpathy-x-post.md` and `demo/raw/karpathy-llm-wiki-gist.md` sources with the synthesis LLM stubbed. Catches cross-module integration regressions (ingest ↔ compile manifest ↔ query engine ↔ lint runner) that single-module unit tests miss. Uses `ingest_source(..., extraction=dict)` to skip LLM extraction entirely; only monkeypatches the synthesis `call_llm` at `kb.query.engine.call_llm`, plus the module-level constants `RAW_DIR`/`PROJECT_ROOT`/`WIKI_CONTRADICTIONS`/`HASH_MANIFEST` at both `kb.config.X` and each consuming module. Deferred in favor of the active Phase 4.5 bug-fix backlog. Design spec content was drafted in-session but not committed; rewrite from this bullet when picked up. Source: Layer 1 of the three-layer e2e strategy (Layer 2 = MCP contract test via `fastmcp.Client` in-process; Layer 3 = gated `@pytest.mark.live` smoke test against real Anthropic API).
  (effort: Low — ~100-line single test file, no new fixtures or dependencies; `tmp_project` in `tests/conftest.py` is sufficient. Asserts page IDs in `pages_created`/`pages_updated`, frontmatter source-list merge on shared entities, `wikilinks_injected` on second ingest, `[source: …]` citation round-trip, and `lint_report["summary"]["error"] == 0`. Run cadence: every CI, hermetic, ~1s.)

### DEFERRED — API-level LLM provider integration (Cycle 21 explicit deferral)

> Cycle 21 delivered **CLI subprocess** integration for 8 backends (Ollama, Gemini CLI, OpenCode, Codex CLI, Kimi, QWEN, DeepSeek, ZAI). REST API / SDK integration for these providers is explicitly deferred to a later cycle.

- `utils/llm.py` `utils/api_backend.py` (new) — add API-level integration for alternative LLM providers via LiteLLM or per-provider SDK. Deferred from cycle 21 per explicit user direction ("I want to support CLI tool not the API support please add API support at late roadmap"). LiteLLM (`==1.83.0`) and `openai` SDK (`==2.30.0`) are already in `requirements.txt`. When picked up: route `KB_LLM_BACKEND=litellm` (or `KB_LLM_BACKEND=openai`) through a provider-agnostic `call_api(...)` in a new `src/kb/utils/api_backend.py` module; reuse the routing gate and `get_cli_backend()` helper from cycle 21 — `"anthropic"` stays on the existing SDK path, `"litellm"` / `"openai"` go through `api_backend.call_api(...)`, CLI tool backends remain on the subprocess path. Requires: (a) LiteLLM provider config in `config.py` (`LITELLM_MODEL`, base_url overrides), (b) structured JSON output via `response_format={"type": "json_object"}` (replaces tool_use for non-Anthropic APIs), (c) same retry + redaction + timeout contract as the Anthropic path.
  (effort: Medium — new `api_backend.py` module + config additions + routing gate update + tests)

- `utils/llm.py` `utils/api_backend.py` (new) — add first-class vLLM support through its OpenAI-compatible HTTP server. Route `KB_LLM_BACKEND=vllm` to the same API backend abstraction as the deferred LiteLLM/OpenAI work, with `KB_VLLM_BASE_URL` defaulting to `http://localhost:8000/v1`, `KB_VLLM_MODEL` required or auto-read from `/v1/models`, and `KB_VLLM_API_KEY` optional for deployments that front vLLM with auth. Must preserve the existing safety contract: no shell invocation, request timeout + retry policy, redacted errors, bounded response size, JSON schema validation for `call_llm_json`, and clear failure messages when the local vLLM server is down or the selected model lacks reliable JSON output.
  (effort: Medium — config additions + `KB_LLM_BACKEND` routing + OpenAI-compatible client call path + mocked HTTP tests for text, JSON, timeout, auth header redaction, and unknown-model errors)

### LOW LEVERAGE — Operational

- `wiki/_schema.md` vendor-neutral single source of truth — move project schema (page types, frontmatter fields, wikilink syntax, operation contracts) out of tool-convention files and into `wiki/_schema.md` co-located with the data it describes. Existing `CLAUDE.md` / future `AGENTS.md` / `GEMINI.md` stay as thin (~10-line) vendor shims that point at `_schema.md` for project rules. Schema is machine-parseable (fenced YAML blocks under markdown headers) and validated by lint on every ingest. Innovation vs. the common "symlink AGENTS.md → CLAUDE.md" pattern: the schema lives WITH the wiki, portable across agent frameworks (Codex, Cursor, Gemini CLI, shell scripts). Follows the existing `_sources.md` / `_categories.md` convention. Source: Karpathy tweet (schema portability prompt) + project design.
  (effort: Medium — (a) write `wiki/_schema.md` starter as self-describing meta page; (b) `kb.schema.load()` parser; (c) `kb_lint` integration validates frontmatter against schema; (d) `schema_version` + `kb migrate` CLI; (e) optional multi-persona sections `### for ingest` / `### for query` / `### for review` so agents load scoped context. Defer vendor shim updates — keep `CLAUDE.md` unchanged until user chooses to slim it)

- `cli.py` `kb search <query>` subcommand — colorized terminal output over the existing hybrid search; `kb search --serve` exposes a minimal localhost web UI. Power-user CLI over the same engine the LLM already uses via MCP. Source: Karpathy tweet (*"small and naive search engine, web ui and CLI"*).
  (effort: Low — Click command + Flask/FastAPI localhost UI)

- Git commit receipts on ingest — emit `"four new articles appeared: Amol Avasari, Capability Overhang, CASH Framework, Success Disasters"` style summary with commit hash and changed files per source. Source: Fabian Williams.
  (effort: Low — wrap existing ingest return dict with a formatter)

### HIGH LEVERAGE — Ingest & Query Convenience

- `mcp/core.py` `kb_ingest` URL-aware 5-state adapter — upgrade `kb_ingest`/`kb_ingest_content` to accept URLs alongside file paths; URL routing table in `kb.config` maps patterns to source type + `raw/` subdir + preferred adapter; before executing, checks 5 explicit states: `not_installed`, `env_unavailable`, `runtime_failed`, `empty_result`, `unsupported` — each emits a specific recovery hint and offers manual-paste fallback. Eliminates the "run crwl, save file, then kb_ingest file" three-step friction. Source: llm-wiki-skill adapter-state.sh 5-state model.
  (effort: Medium — URL routing table in config + per-state error handling + adapter dispatcher)

- `mcp/core.py` `kb_delete_source` MCP tool — remove raw source file and cascade: delete source summary wiki page, strip source from `source:` field on shared entity/concept pages without deleting them, clean dead wikilinks from remaining wiki pages, update `index.md` and `_sources.md`. Fills the only major operational workflow gap not addressed by existing tooling.
  (effort: Medium — cascade deletion logic + backlink cleanup + atomic index/sources update)

- `mcp/health.py` `kb_rebuild_indexes` MCP tool — wrap `kb.compile.compiler.rebuild_indexes` so MCP clients can trigger the clean-slate rebuild without shelling out to the CLI. Scope-out from cycle 23 (threat T7): cycle 23 shipped the library helper + CLI subcommand only; MCP surface deferred so same-class peer review (cycle-16 L1) can confirm the I1 dual-anchor check also protects the MCP entry point. Prerequisite: reuse `_validate_wiki_dir` from `kb.mcp.app` for the `wiki_dir` argument; surface the return dict verbatim (already JSON-serialisable). Audit entry should tag the invoker (CLI vs MCP) per cycle-20 L3 MCP-projection peer scan.
  (effort: Low — thin wrapper + regression test + same-class peer scan)

<!-- `kb_query save_as` parameter remains deferred — see Phase 4.5 MEDIUM. -->

- `evolve/analyzer.py` `kb_evolve mode=research` — for each identified coverage gap, decompose into 2–3 web search queries, fetch top results via fetch MCP, save to `raw/articles/` via `kb_save_source`, return file paths for subsequent `kb_ingest`; capped at 5 sources per gap, max 3 rounds (broad → sub-gaps → contradictions). Turns evolve from advisory gap report into actionable source acquisition pipeline. Source: claude-obsidian autoresearch skill.
  (effort: Medium — gap decomposition prompt + fetch MCP integration + 3-round loop with source cap)

- `wiki/purpose.md` KB focus document — lightweight file defining KB goals, key questions, and research scope; included in `kb_query` context and ingest system prompt so the LLM biases extraction toward the KB's current direction. Source: nashsu/llm_wiki purpose.md.
  (effort: Low — one markdown file + read in query_wiki + prepend in ingest system prompt)

### MEDIUM LEVERAGE — Search & Indexing

- `query/bm25.py` `query/embeddings.py` chunk-level sub-page indexing — split wiki pages into topically coherent chunks using Savitzky-Golay boundary detection (embed sentences with model2vec, compute adjacent cosine similarities, SG smoothing 5-window 3rd-order polynomial, find zero-crossings as topic boundaries); each chunk indexed as `<page_id>:c<n>`; query engine scores chunks, deduplicates to best chunk per page, loads full pages for synthesis. Resolves the weakness where relevant content is buried in long pages. Source: garrytan/gbrain semantic.ts + sage-wiki FTS5 chunking.
  (effort: High — SG chunking module + BM25 index schema change + chunk-to-page dedup aggregation layer)

<!-- Cross-reference auto-linking remains deferred — see Phase 4.5 MEDIUM. -->

- `lint/checks.py` `query/engine.py` PageRank-prioritized semantic lint sampling — when `kb_lint_deep` must limit its page budget, select pages by PageRank descending rather than arbitrary order; high-authority pages with quality issues have outsized downstream impact on citing pages. Source: existing `graph_stats` PageRank scores.
  (effort: Low — sort by graph_stats PageRank before sampling; zero new infrastructure required)

### MEDIUM LEVERAGE — Page Lifecycle & Quality Signals

<!-- `models/` `status` frontmatter vocabulary + validate_frontmatter + query ranking boost SHIPPED in cycle 14 AC1/AC2/AC23. Cycle 15 shipped `kb_lint` mature-stale flagging; `kb_evolve` status-priority routing remains deferred — see Phase 4.5 MEDIUM AC8-carry. -->

<!-- Inline quality callout markers remain deferred — see Phase 4.5 MEDIUM. -->

- `wiki/hot.md` wake-up context snapshot — ~500-word compressed context updated at session end (recent facts, recent page changes, open questions); read at session start via `SessionStart` hook; survives context compaction and session boundaries; enables cross-session continuity without full wiki crawl. Source: MemPalace concept + claude-obsidian hot cache.
  (effort: Low — append-on-ingest + SessionStart hook reads + one markdown file)

- `wiki/overview.md` living overview page — auto-revised on every ingest as the final pipeline step; always-current executive summary across all sources; updated not replaced on each ingest. Source: llm-wiki-agent living overview.
  (effort: Low — scan-tier LLM over index.md + top pages; one file auto-updated per ingest)

### MEDIUM LEVERAGE — Knowledge Promotion & Ingest Quality

- `query/engine.py` `feedback/store.py` conversation→KB promotion — positively-rated query answers (rating ≥ 4) auto-promote to `wiki/synthesis/{slug}.md` pages with citations mapped to `source:` refs; coexists with `save_as` parameter (immediate, no gate) as the feedback-gated deferred path. Source: garrytan/gbrain maintain skill.
  (effort: Medium — feedback store hook + synthesis page writer + conflict check against existing pages)

- `ingest/pipeline.py` two-step CoT ingest analysis pass — split ingest into: (1) analysis call producing entity list + connections to existing wiki + contradictions + wiki structure recommendations; (2) generation call using analysis as context. Improves extraction quality and enables richer contradiction flagging; feeds Phase 4 auto-contradiction detection. Source: nashsu/llm_wiki two-step chain-of-thought.
  (effort: Medium — split single ingest LLM call into two sequential calls with analysis-as-context)

### Phase 6 candidates (larger scope, not yet scheduled)

- Hermes-style independent quality-gate supervisor — different-model-family validator (not same-family self-review) before page promotion. Source: Secondmate (@jumperz, via VentureBeat).
  (effort: High — adds a second provider; challenges fail-open defaults)

- Mesh sync for multi-agent writes — last-write-wins with timestamp conflict resolution; private-vs-shared scoping (personal preferences private, architecture decisions shared). Source: rohitg00.
  (effort: High — assumes multi-writer concurrency model)

- Hosted MCP HTTP/SSE variant — multi-device access (phone Claude app, ChatGPT, Cursor, Claude Code) reading/writing the same KB. Source: Hjarni/dev.to.
  (effort: High — MCP transport + auth; currently stdio-only)

- Personal-life-corpus templates — Google Takeout / Apple Health / AI session exports / bank statements as a domain starter kit. Privacy-aware ingest layered on `.llmwikiignore`. Source: anonymous personal-data-RAG reply.
  (effort: Medium — per-source-type extractor templates; depends on `.llmwikiignore` landing first)

- Multi-signal graph retrieval — BM25 seed → 4-signal graph expansion: direct wikilinks ×3 + source-overlap ×4 + Adamic-Adar shared-neighbor similarity ×1.5 + type-affinity ×1; nodes ranked by combined BM25 + graph score with budget-proportional context assembly. Prerequisite: typed semantic relations (below). Source: nashsu/llm_wiki relevance model.
  (effort: High — graph score combination layer + per-signal weight tuning + typed relations as prerequisite)

- Typed semantic relations on graph edges — extract 6 relation types via keyword matching: `implements`, `extends`, `optimizes`, `contradicts`, `prerequisite_of`, `trades_off`; stored as edge attribute in NetworkX + SQLite; enables typed graph traversal in `kb_query`. Prerequisite for multi-signal retrieval. Source: sage-wiki configurable ontology.
  (effort: Medium — relation extractor pass + NetworkX/SQLite graph schema update)

- Temporal claim tracking — `valid_from`/`ended` date windows on individual claims within pages; enables staleness/contradiction resolution at claim granularity rather than page granularity. Requires new SQLite KG schema. Source: MemPalace SQLite KG pattern.
  (effort: High — claim-level SQLite schema + ingest extractor update + query-time filtering)

- Semantic edge inference in graph — two-pass graph build: existing wikilink edges as EXTRACTED + LLM-inferred implicit relationships as INFERRED/AMBIGUOUS with confidence 0–1; re-infers only changed pages via content hash cache. Source: llm-wiki-agent.
  (effort: High — 2-pass build logic + confidence-weighted edges + per-page change detection)

- Answer trace enforcement — require synthesizer to tag every factual claim with `[wiki/page]` or `[raw/source]` citation at synthesis time; post-process strips or flags uncited claims as gaps. Source: epistemic integrity requirement.
  (effort: High — synthesis prompt rewrite + citation parser + enforcement pass + graceful fallback)

- Multi-mode search depth toggle (`depth=fast|deep`) — `depth=deep` uses Monte Carlo evidence sampling for complex multi-hop questions; `depth=fast` is current BM25 hybrid. Depends on MC sampling infrastructure. Source: Sirchmunk Monte Carlo evidence sampling.
  (effort: High — MC sampler architecture + budget allocation + fast/deep routing logic)

- **Hybrid RAG + Wiki compiler architecture** — two-tier retrieval: RAG layer (pgvector in Postgres) handles high-volume raw corpus at semantic search speed; compiled wiki layer holds curated authoritative pages. Query router scores wiki hits first (high trust), falls back to RAG chunks (flagged `[unverified]`). `kb_evolve` gap analysis scans RAG hit-frequency to surface topics ready for wiki promotion. Ingest pipeline gains an optional embedding step alongside existing BM25 indexing. Enables enterprise-scale corpora (100k+ docs) without sacrificing the auditability and contradiction-detection strengths of the wiki compiler. Source: internal architecture discussion 2026-04-21.
  (effort: High — pgvector schema + embedding step in ingest + query router blending wiki+RAG citations + evolve promotion heuristic; prerequisite: multi-user storage migration)

- Semantic deduplication pre-ingest — embedding similarity check before ingestion to catch same-topic-different-wording duplicates beyond content hash; flag if cosine similarity >0.85 to any existing raw source. Source: content deduplication research.
  (effort: Medium — embed new source + nearest-neighbor check vs existing vector store)

- Interactive knowledge graph HTML viewer — self-contained vis.js HTML export from `kb_graph_viz` with `format=html`; dark theme, search bar, click-to-inspect nodes, Louvain community clustering, edge type legend. Source: llm-wiki-agent graph.html.
  (effort: Medium — vis.js template + Louvain community IDs per node + edge type legend)

- Two-phase compile pipeline + pre-publish validation gate — phase 1: batch cross-source merging before writing; phase 2: validation gate rejects pages with unresolved contradictions or missing required citations. Architecture change to current single-pass compiler. Source: compilation best practices.
  (effort: High — compiler refactor into two phases + validation gate + publish/reject state machine)

- Actionable gap-fill source suggestions — enhance `kb_evolve` to suggest specific real-world sources for each gap ("no sources on MoE, consider the Mixtral paper"). Mostly superseded by `kb_evolve mode=research` (Phase 5) which fetches sources autonomously; keep as fallback for offline/no-fetch environments. Source: nashsu/llm_wiki.
  (effort: Low delta on evolve — add one LLM call per gap; ship only if mode=research is blocked)

### Phase 7 candidates — Enterprise source integrations (not yet scheduled)

> Prerequisite: Phase 6 multi-user storage migration + Hybrid RAG layer must land first.
> Core design change: `raw/` becomes a logical namespace, not a single folder. Each source root
> is registered with a connector type, credentials, and sync policy. The ingest pipeline treats
> them identically once normalized to local markdown.

- **Multi-root raw directory support** — allow `KB_RAW_ROOTS` env var (colon-separated paths) or a `sources.yaml` registry so a single wiki can compile from multiple raw directories (e.g. a personal folder + a shared team folder + a connector-synced cache). `ingest_source`, `compile_wiki`, and `kb_detect_drift` all scope to `raw_dir` today; the change threads an optional `raw_roots: list[Path]` through those APIs and merges hash manifests per-root. Prerequisite for all connector items below.
  (effort: Medium — config + API threading; no connector logic yet)

- **SharePoint / OneDrive connector** — poll or webhook-triggered sync of SharePoint document libraries and OneDrive shared folders into a designated `raw/sharepoint/<site>/` root. Uses Microsoft Graph API (`sites.read.all` scope). Supports `.docx`, `.pptx`, `.pdf`, `.xlsx` via `markitdown`. Delta-sync via Graph `$deltaToken` to avoid full re-crawl. Permission-aware: respects item-level read permissions so a user only ingests docs they can access.
  (effort: High — OAuth2 PKCE flow + Graph delta sync + markitdown conversion + permission mapping)

- **Google Drive / Google Shared Drives connector** — sync Google Drive folders and Shared Drives into `raw/gdrive/<drive-id>/`. Uses Drive API v3 `files.list` with `driveId` + `includeItemsFromAllDrives`. Exports Google Docs → markdown via Drive export API; native files (PDF, DOCX) via direct download + markitdown. Change-token polling (not full re-scan) for incremental sync.
  (effort: High — OAuth2 + Drive export API + change-token polling + markitdown pipeline)

- **Confluence connector** — crawl Confluence Cloud or Server spaces into `raw/confluence/<space-key>/`. Uses Confluence REST API v2 (`/wiki/api/v2/pages`). Exports page body as storage-format HTML → converts via `trafilatura` or `markitdown`. Respects space/page-level permissions via API token scoping. Attachments (PDF, DOCX) downloaded and ingested as sibling raw files.
  (effort: High — REST API pagination + HTML→markdown conversion + attachment handling + space permission scoping)

- **Notion connector** — sync Notion databases and pages into `raw/notion/<database-id>/`. Uses Notion API v1 (`/v1/blocks`, `/v1/databases/query`). Exports rich text blocks → markdown. Handles inline databases, toggles, callouts. Change detection via `last_edited_time` cursor.
  (effort: Medium — Notion API pagination + block→markdown renderer + cursor-based incremental sync)

- **GitHub / GitLab repo connector** — ingest markdown docs, READMEs, and wiki pages from repos directly into `raw/repos/<owner>/<repo>/`. Extends existing `repos/` source type. Uses GitHub Contents API or `git clone --depth 1`; respects `.llmwikiignore` patterns to skip source code and focus on docs. Auto-triggered on push webhook for live orgs.
  (effort: Medium — GitHub API or shallow clone + .llmwikiignore filtering + webhook trigger)

- **Credential & secret store integration** — connector OAuth tokens and API keys stored in system keychain (Windows Credential Manager, macOS Keychain, Linux Secret Service) or a secrets manager (HashiCorp Vault, AWS Secrets Manager) rather than `.env`. `get_connector_creds(service)` abstraction; `.env` fallback for local dev. Required before any connector ships to production.
  (effort: Medium — keychain adapter + secrets manager client + fallback chain; security prerequisite for all connectors)

- **Sync policy & scheduling** — per-source-root sync schedule (`cron`-style or `on_change` webhook) with last-sync timestamp, retry backoff, and `dry_run` mode. Surfaces as `kb sync [--source <root>] [--dry-run]` CLI command and `kb_sync` MCP tool. Sync state persisted in `.data/sync_state.json`.
  (effort: Medium — scheduler + state store + CLI/MCP surface; depends on multi-root support)

### Phase 8 candidates — Strategic rewrite / Rust core (not yet scheduled)

> Trigger condition: Phase 6 (multi-user) + Phase 7 (connectors) are shipped and production load
> reveals Python bottlenecks OR the codebase accumulates enough legacy decisions that greenfield
> is cheaper than continued patching. This is a "revisit annually" decision, not a scheduled one.

**The honest rewrite question**

The current Python stack has real strengths: 2710+ tests, 20 cycles of hardened edge-case coverage,
rapid LLM-call iteration, trafilatura/markitdown/playwright in the same ecosystem. A rewrite throws
all of that away. The question is whether the *architecture* is sound enough to keep extending, or
whether early single-user decisions (flat-file storage, single-process compile, synchronous LLM
calls) are now load-bearing walls that block the enterprise path.

- **Keep Python, refactor architecture** — most likely path. Swap storage (Postgres), add async
  job queue (Celery/ARQ), keep BM25+vector hybrid. Preserves test suite and iteration speed.
  Python is I/O-bound here — LLM calls dominate; Rust buys nothing for that workload.

- **Rust core for hot paths** — compile BM25 indexer, wikilink injection regex engine, and file
  scanner as a Rust extension (`PyO18` / `maturin`). Python orchestration layer unchanged.
  Realistic 5–20× speedup on the scan tier for large corpora (100k+ pages). Feasible without
  full rewrite — ship as optional `kb[fast]` extra.
  (effort: Medium — Rust BM25 + regex engine + PyO3 bindings; Python layer untouched)

- **Vibe-coding greenfield with AI agents** — use the current system as the *spec*
  (CLAUDE.md + CHANGELOG.md + test suite as acceptance criteria) and drive a targeted rewrite
  of performance-critical modules via Claude Code / Codex agents in parallel worktrees. Each
  module gets its own agent, outputs integration-tested against Python golden outputs.
  Worth a spike on one module (e.g. `kb.query.engine`) before committing to broader scope.
  (effort: Unknown — spike first; scoped to hot-path modules only, not full rewrite)

**Recommended architecture (decided 2026-04-21):**

```
┌─────────────────────────────────────────────┐
│  TypeScript / Next.js  (view + API layer)   │  ← Phase 8A
│  - Three-pane wiki browser                  │
│  - Graph visualization                      │
│  - Chat / query interface                   │
│  - REST / tRPC API → Python KB process      │
└────────────────────┬────────────────────────┘
                     │ HTTP / stdio
┌────────────────────▼────────────────────────┐
│  Python  (AI brain — keep as-is)            │  ← current stack
│  - All LLM calls (Anthropic SDK)            │
│  - ingest / compile / query / lint / evolve │
│  - MCP server (28 tools)                    │
│  - connector pipeline (Phase 7)             │
│  - AI ecosystem: trafilatura, markitdown,   │
│    playwright, sentence-transformers, etc.  │
└────────────────────┬────────────────────────┘
                     │ PyO3 / maturin bindings
┌────────────────────▼────────────────────────┐
│  Rust  (hot paths only — optional ext)      │  ← Phase 8B
│  - BM25 indexer (tantivy)                   │
│  - Wikilink injection regex engine          │
│  - File scanner / hash manifest             │
│  Shipped as kb[fast] optional extra         │
└─────────────────────────────────────────────┘
```

- **Phase 8A** — TypeScript view layer (Next.js). Ships as `kb serve` command that starts the
  Next.js dev server pointed at the local wiki directory. No Python changes required — the UI
  calls the existing MCP tools via a thin HTTP adapter. Effort: Medium.

- **Phase 8B** — Rust hot-path extension via `maturin`/PyO3. Optional `pip install kb[fast]`
  extra that replaces the Python BM25 indexer and file scanner with Rust equivalents. Python
  orchestration layer unchanged. 5–20× throughput on scan tier for large corpora. Effort: Medium.

- **Cloud wiki storage backends** — replace local `wiki/` filesystem with pluggable object storage
  so the compiled wiki survives beyond a single machine and multiple users/services can read it.
  Storage abstraction layer (`WikiStorage` protocol) wraps current `atomic_text_write` /
  `file_lock` calls; local filesystem remains the default, cloud backends are opt-in via
  `KB_WIKI_STORAGE=s3|azure|gcs` env var.

  | Backend | Use case | SDK |
  |---|---|---|
  | **AWS S3 / S3-compatible** (MinIO, R2) | AWS orgs, self-hosted, Cloudflare R2 free tier | `boto3` |
  | **Azure Blob Storage** | Microsoft 365 orgs (pairs with SharePoint connector) | `azure-storage-blob` |
  | **Google Cloud Storage** | GCP / Google Workspace orgs | `google-cloud-storage` |
  | **Local filesystem** | default, dev, Obsidian users | current impl |

  Key design constraints:
  - Object storage has no atomic rename — `atomic_text_write` must use conditional PUT
    (`If-None-Match: *` for create, ETag check for update) to preserve crash safety
  - `file_lock` becomes a distributed lock (Redis `SET NX PX`, DynamoDB conditional write,
    or Azure Blob lease) — required before any cloud backend ships
  - `wiki/` path references in MCP tools become storage-relative keys, not filesystem paths
  - Read path: stream page content; no local cache needed for query (BM25 index cached locally)
  - `kb publish` outputs (`/llms.txt`, `/graph.jsonld`, sitemap) write to a separate public
    bucket/container with CDN fronting for the view layer
  - Prerequisite: Phase 6 multi-user storage migration (distributed lock infra overlaps)

  (effort: High — storage abstraction layer + distributed locking + conditional PUT semantics +
  per-backend SDK integration; local filesystem fallback must stay zero-overhead)

**Decision criteria (revisit when):**
- Compile time for 10k sources exceeds 30 min → Phase 8B Rust hot-path spike
- Concurrent users > 20 with write contention → async job queue refactor (Python, pre-Phase 8)
- Deployment friction (Python env) blocks enterprise sales → Phase 8A Next.js wrapper first
- Team spans multiple machines / cloud deploy needed → cloud wiki storage backend

### Design tensions to document in README (not items to implement)

- **Container boundary / atomic notes tension (WenHao Yu)** — `kb_ingest` forces a "which page does this merge into?" decision, same failure mode as Evernote's "which folder" and Notion's "which tag". Document that our model merges aggressively and that atomic-note alternative exists.
- **Model collapse (Shumailov 2024, Nature)** — cite in "known limitations": LLM-written pages feeding next LLM ingest degrade across generations; our counter is evidence-trail provenance plus two-vault promotion gate.
- **Enterprise ceiling (Epsilla)** — document explicit scope: personal-scale research KB, not multi-user enterprise; no RBAC, no compliance audit log, file-I/O limits at millions-of-docs scale.
- **Vibe-thinking critique (HN)** — *"Deep writing means coming up with things through the process of producing"*; defend with mandatory human-review gates on promotion, not optional.

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM items deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
- **Phase 4 post-release audit** — all items resolved (23 HIGH + ~30 MEDIUM + ~30 LOW) in CHANGELOG.md [Unreleased]
- **Phase 5 three-round code review (2026-04-17)** — all items resolved in CHANGELOG `[Unreleased]` Backlog-by-file cycle 1 (3 HIGH: raw_dir threading, ingest raw_dir parameter, manifest failed-state advance; 4 MEDIUM: data_dir threading, max_gaps lower bound, proposal URL re-validation, summary-count semantics)
- **Phase 5 pre-merge lint augment (2026-04-15)** — all items resolved in CHANGELOG `[Unreleased]` Phase 4.5 cycle 17 (AC11/AC12/AC13)
- **Cycle 21/22 candidates** — all open candidate items resolved in CHANGELOG `[Unreleased]` cycle 22 (wiki-path guard, extraction grounding clause, inspect-source test rewrite)
