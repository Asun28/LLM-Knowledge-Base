# Backlog

<!-- FORMAT GUIDE
- BACKLOG = open work only, ranked by severity per phase.
- Resolve lifecycle: delete the item here → brief entry in CHANGELOG.md `[Unreleased]` → full detail in CHANGELOG-history.md.
- Severity: CRITICAL (data loss / security exploit) · HIGH (silent wrong results / unhandled exceptions) · MEDIUM (quality gaps, dead code, coverage) · LOW (style, docs, naming).
- Item format: `- module/file.py symbol — short description (fix: optional remedy)`.
- One bullet = one issue. Don't combine unrelated problems.
- When a phase empties out, collapse to a one-liner under "Resolved Phases".
- Per-cycle running narrative does NOT belong here — it belongs in CHANGELOG-history.md.
-->

---

## Cross-reference

| File | Role | Update rule |
|------|------|-------------|
| **BACKLOG.md** ← you are here | Open work only | Add on discovery; **delete** on resolve |
| [CHANGELOG.md](CHANGELOG.md) | Brief shipped-change index, newest first | Compact Items / Tests / Scope / Detail per cycle |
| [CHANGELOG-history.md](CHANGELOG-history.md) | Detailed shipped-change archive, newest first | Full per-cycle bullet detail |

If an entry says _"see CHANGELOG"_, it is resolved and can be safely deleted from this file.

---

## Phase 4.5 — Multi-agent post-v0.10.0 audit (2026-04-13)

<!-- Discovered by 5 specialist reviewers (Python, security, code-review, architecture, performance)
     running 3 sequential rounds against v0.10.0. Round tag in parens (R1/R2/R3/R5). -->

### HIGH

- `compile/compiler.py` naming inversion (~16-17) — `compile_wiki` is a thin orchestration shell over `ingest_source` + a manifest; real compilation primitives (`linker.py`) live in `compile/` but are consumed by `ingest/`. Dependency arrows invert the directory names; every new feature placement becomes a coin-flip. (R1)
  (fix: rename to `pipeline/orchestrator.py` and treat `compile/` as wikilink primitives only; or collapse `compile/compiler.py` into `kb.ingest.batch`)

- `ingest/pipeline.py` state-store fan-out — a single `ingest_source` mutates summary page, N entity pages, N concept pages, `index.md`, `_sources.md`, `.data/hashes.json`, `wiki/log.md`, `wiki/contradictions.md`, plus N `inject_wikilinks` writes. Every step is independently atomic, none reversible. A crash between manifest-write and log-append leaves the manifest claiming "already ingested" while the log shows nothing. (R2)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests)

- `tests/` coverage-visibility — 20 test files remain named `test_v0NNN_taskNN.py` / `test_v0NNN_phaseNNN.py` / `test_phase4_audit_*.py` (cycle 80 folded the v0915 task02/04/05/07 batch; 24 → 20). Verifying canonical-module coverage requires grepping versioned files. Freeze-and-fold cadence in progress; remaining files still to fold across future cycles. Per-cycle progress is in CHANGELOG-history.md, not here. (R3)
  (fix: freeze-and-fold rule — once a version ships, fold its tests INTO the canonical module file; enable `coverage` in CI and surface per-module % in PR comments)
  Concrete remaining set (recovered 2026-07-23 from the abandoned `feat/cycle-59` / `-62` / `-63` branches before they were deleted — those branches had folded these away, but cycles 77/78/80 redid only part of that work, so these 12 never landed):
  `tests/test_ingest_fixes_v092.py`, `test_phase4_audit_ingest.py`, `test_phase4_audit_query.py`, `test_stub_detection_v094.py`, `test_v4_11_cli.py`, `test_v4_11_markdown.py`, `test_v4_11_mcp.py`, `test_v5_augment_config.py`, `test_v5_autogen_prefixes.py`, `test_v5_lint_augment_manifest.py`, `test_v5_lint_augment_rate.py`, `test_v5_verdict_augment_type.py`.
  Don't redo this from scratch: the cycle-59/61/62 work survives on origin as tags `archive/cycle-59` (aa5bacf), `archive/cycle-61` (5396424) and `archive/cycle-62` (290ff0a) — the original branch commits, so the fold diffs can be replayed with `git diff main...archive/cycle-59`. Only cycle-63's branch (was 21a8604) has no surviving ref; the list above is the sole record of what it covered.

- `mcp/core.py` + `browse.py` + `health.py` + `quality.py` — all 25 MCP tools are sync `def`. FastMCP runs them via `anyio.to_thread.run_sync` on a default 40-thread pool. Long tools (`kb_query(use_api=True)` 30s+, `kb_lint()` multi-second, `kb_compile()` minutes, `kb_ingest_content(use_api=True)` 10+s) each hold a thread; under concurrent tool calls the pool saturates. (R3)
  (fix: make long-I/O tools `async def` and `await anyio.to_thread.run_sync(...)` around the SDK call; or document / tune `FastMCP(num_threads=N)`; at minimum surface the concurrency model in the `app.py` instructions block)

### MEDIUM

- `config.py` god-module — 35+ unrelated constants (paths, model IDs, BM25 hyperparameters, dedup thresholds, retries, ingest/evolve/lint limits, retention caps, query budgets, RRF, embeddings). Single-file churn invalidates import cache for the whole package in tests. (R1)
  (fix: split into `config/paths.py` / `config/models.py` / `config/limits.py` / `config/search.py` / `config/lint.py`; or a `Settings` dataclass with grouped subfields; keep `from kb.config import *` shim)

- `compile/compiler.py` `compile_wiki` per-source rollback — observability variant shipped (cycle 25 AC6/AC7/AC8: `in_progress:{pre_hash}` marker + stale-marker warning + full-mode prune exemption). Remaining: (a) rollback of wiki writes on manifest-save failure (requires receipt-file design or transaction-like helper); (b) escalating manifest-write failure to CRITICAL. (R1)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests.)

- `utils/io.py` `atomic_json_write` + `file_lock` pair — 6+ Windows filesystem syscalls per small write. Cycle 24 AC9 added exponential backoff to `file_lock`; the JSONL-migration part remains open. (R1)
  (fix: append-only JSONL with `msvcrt.locking` / `fcntl` locking; compact on read or via explicit `kb_verdicts_compact`)

- `compile/linker.py` cross-reference auto-linking — when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` on A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`.

- `ingest/pipeline.py` `IndexWriter` consolidation refactor — cycle 35 closed the immediate RMW concurrency hazard via `file_lock(target_path)`. Open: code-quality refactor — `IndexWriter` helper wrapping all four index-file writes (`_sources.md`, `index.md`, `_categories.md`, `log.md`) with documented lock-acquire order. Defer until a cycle adds a 4th caller.

- `ingest/pipeline.py` `_update_existing_page` body-write + evidence-append two-write consolidation — cycle 24 AC1 shipped single-atomic-write inline rendering for `_write_wiki_page` (new-page path). Update path remains: existing body must be preserved across ingests, so pre-rendering the trail with all historical entries is infeasible without a broader refactor.
  (fix: `_update_existing_page` RMW could buffer existing trail bytes in memory, append the new entry, write both body and trail under a single lock — requires the cycle-19 `file_lock` discipline.)

- CLI ↔ MCP parity — `cli.py` exposes 24 commands; MCP exposes 28 tools. Remaining gap = 7 write-path tools deferred to a write-path input-validation cycle: `kb_review_page` / `kb_refine_page` / `kb_query_feedback` / `kb_save_source` / `kb_save_lint_verdict` / `kb_create_page` / `kb_capture`. Structured `--format=json` output across both surfaces also still open. (R2)
  (fix: auto-generate CLI subcommands from the FastMCP tool registry; or collapse MCP + CLI onto a shared `kb.api` service module)

- `compile/compiler.py` `compile_wiki` (~279-393) — a 50-line `for source in changed: ingest_source(source)` loop + manifest save. CLAUDE.md describes compile as "LLM builds/updates interlinked wiki pages, proposes diffs, not full rewrites" — no second pass, no cross-source reconciliation, no diff proposal exists in code. (R2)
  (fix: make `compile_wiki` a real two-phase pipeline (collect extractions → reconcile cross-source → write); or rename to `batch_ingest` and stop pretending compile is distinct)

- `tests/` snapshot tests — cycle 64 shipped foundation: `syrupy>=4.6.0` dev dep + 3 snapshot subjects (evidence-trail / Mermaid export / lint-report-structure). Cycles 69-73 shipped 6 of 6 originally-deferred subjects: `build_extraction_prompt` (cycle 69 AC13), `_render_sources` (cycle 69 AC15), `_build_summary_content` (cycle 70 AC06), `build_llms_full_txt` (cycle 70 AC07), `build_graph_jsonld` (cycle 70 AC08), `_persist_contradictions` (cycle 73 AC05). All originally-listed subjects now pinned. (R3)
  (cycle-74+: identify NEW snapshot candidates as the diff surface evolves; `mutmut` mutation-coverage analysis below tracks the regression-strength side.)

- `tests/` N=40 FastMCP-realistic dim-mismatch concurrency stress (cycle-65+) — cycle 64 AC8's `test_concurrent_query_during_rebuild_idempotent` exercises N=4 threads and proves idempotency via embeddings.py:302+307 double-checked locking. N=40 deferred per R2-F6 (test-harness infrastructure complexity without proportional cycle-64 win).

- `ingest/pipeline.py` real PDF text extraction (cycle-N+1 if requested) — cycle 34 AC24 removed `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS`; user-facing message points at `markitdown` / `docling` for conversion. If in-process extraction is requested: integrate `pypdf` or `pdfplumber` as a `[pdf]` extra with size + page caps; or add a `kb convert <pdf>` CLI subcommand wrapping markitdown.

- `tests/` windows-latest CI matrix re-enable (cycle-53+) — local Windows full suite passes. GHA `windows-latest` runner hangs at `threading.py:355` after cycle-23 multiprocessing test was skipif'd (cycle 36 AC2). Top-3 candidate culprits (grep-ranked by Thread/multiprocessing usage): (1) `tests/test_cycle25_dim_mismatch.py:180-184` N-thread parallel sqlite write; (2) `tests/test_cycle23_rebuild_indexes.py:213-248` long-lock holder; (3) `tests/test_cycle24_lock_backoff.py:222-228` exponential-backoff thread. Cycle-53+ should reproduce on a self-hosted Windows runner, fix or skipif the culprit, then re-enable matrix `[ubuntu-latest, windows-latest]` with `strategy.fail-fast: false`. Note: `docs/reference/testing.md:27` still asserts the Windows matrix is active; update that file at the same time to reflect the deferred status and avoid production-confidence confusion for external readers.

- `tests/` GHA-Windows multiprocessing spawn investigation (cycle-53+) — cycle 23's `test_cross_process_file_lock_timeout_then_recovery` hangs on GHA `windows-latest` at `popen_spawn_win32.py:112` (parent's `child.start()` blocks waiting on the spawn-bootstrap pipe). Local Windows pass time is 1.03s. Cycle 36 AC2 skipif'd. Reproduce on a self-hosted Windows runner; instrument the child-spawn pipe; identify the divergence (likely editable-install pth resolution / `PYTHONNOUSERSITE` / `kb.config` PROJECT_ROOT heuristic in spawned child). Once fixed, narrow the skipif to `GITHUB_ACTIONS` only or remove.

- `tests/test_utils_text.py` `tests/test_utils_io.py` Windows pyreadline3 pytest crash (cycle-57+) — local Windows pytest crashes with STATUS_ACCESS_VIOLATION (-1073741819) during/after `test_sanitize_strips_control_chars` and `test_sweep_orphan_tmp_logs_warning_and_continues_on_unlink_error`. Workaround: `pytest -p no:capture -p no:debugging`. CI on ubuntu-latest unaffected. Investigate `kb.utils.text.yaml_sanitize` and `kb.utils.io.sweep_orphan_tmp` logging paths — pyreadline3 import-time interference suspected.

- `tests/test_capture.py::TestWriteItemFiles` POSIX off-by-one + creates_dir investigation (cycle-53+) — cycle 36 ubuntu-probe surfaced 2 test failures: `test_creates_dir_if_missing`, `test_pre_existing_file_collision`. The latter expected slug `decision-foo-2` becomes `decision-foo-3` on POSIX. Currently `@_WINDOWS_ONLY` skipif'd. Root cause needs direct POSIX shell access to instrument `_scan_existing_slugs` / `_build_slug` / `_reserve_hidden_temp`.

### LOW

- `tests/` mutmut mutation-coverage analysis on cycle-64 regression suite (cycle-65+) — run `mutmut` (or `cosmic-ray`) over the 6 new cycle-64 test files (`test_cycle64_conftest_leak.py`, `test_cycle64_dim_mismatch_autorebuild.py`, `test_cycle64_graph_cache.py`, `test_cycle64_auto_publish.py`, `test_cycle64_publish_manifest.py`, `test_cycle64_snapshots.py`) to identify mutants that survive — i.e., production-code mutations no test catches.

---

## Phase 5 — Community followup proposals (2026-04-12)

<!-- Feature proposals sourced from Karpathy X post (Apr 2, 2026), gist thread, and 12+ community fork repos.
     Full rationale, attribution, and sources: research/karpathy-community-followup-2026-04-12.md
     These are FEATURE items, not bugs — severity buckets here = LEVERAGE (High / Medium / Low).
     "effort" in the parenthetical replaces "fix" in the bug format. -->

### RECOMMENDED NEXT SPRINT — Karpathy gist re-evaluation (2026-04-13, cycle-64 refresh)

Ranked priority derived from re-reading Karpathy's gist against current state. Items below already exist as entries in the leverage-grouped subsections — this block only SEQUENCES them. Resolved entries removed: auto-publish `llms.txt`/`graph.jsonld` (cycle 64 AC14), `belief_state` frontmatter (cycle 14), `kb_query` coverage-confidence refusal (cycle 14 AC5).

**Tier 1 — Karpathy-verbatim behaviors the project can't yet reproduce:**
1. `wiki/_schema.md` vendor-neutral schema + `AGENTS.md` thin shim — enables Codex / Cursor / Gemini CLI / Droid portability.

**Tier 2 — Epistemic integrity (unsolved-gap closers):**
2. `kb_merge <a> <b>` + duplicate-slug lint check — catches `attention` vs `attention-mechanism` drift.
3. Inline `[EXTRACTED]` / `[INFERRED]` / `[AMBIGUOUS]` claim tags with `kb_lint_deep` sample verification.

**Tier 3 — Ambient capture + security rail:**
4. `.llmwikiignore` + pre-ingest secret/PII scanner — missing safety rail given every ingest sends full content to the API.
5. `SessionStart` hook + `raw/` file watcher + `_raw/` staging directory — eliminates the "remember to ingest" step.

**Recommended next target:** #1 (`wiki/_schema.md` + `AGENTS.md` thin shim). Low effort, opens portability to non-Claude coding agents. Contained blast radius in `kb.schema.load()` + `kb_lint` integration.

### HIGH LEVERAGE — OpenWiki-inspired automation (2026-07-16)

<!-- Sourced from a comparative review of langchain-ai/openwiki (TypeScript, LangChain/DeepAgents, ~11.7k stars).
     Openwiki validates the compile-not-retrieve bet; these two items port its automation plumbing.
     Deliberately NOT adopted: frontmatter-less pages (loses provenance), prompt-only quality rules
     (flywheel mechanizes these via lint/verdicts), unfenced connector→LLM content flow (injection surface). -->

- `.github/workflows/` scheduled wiki-maintenance PR workflow — cron GHA workflow that runs drift detection (`kb_detect_drift`) → refine sweep (`kb_refine_sweep`) → `kb lint` and opens a reviewable PR with the resulting page updates. Adopt openwiki's update contract in the maintenance prompt: build a docs-impact plan before editing; only touch pages made inaccurate by source changes; no formatting-only edits; a no-op run ends without a PR. Operationalizes the flywheel; low-risk subset of the deferred "autonomous research loop". Source: langchain-ai/openwiki CI workflow templates.
  (effort: Medium — headless `kb maintain` CLI entrypoint wrapping drift-detect/refine-sweep + GHA workflow + PR body formatter with per-page change summary)

- `ingest/connectors/` pluggable connector framework — deterministic per-source fetchers (local git repo, web search, Hacker News; RSS/mail later) each writing raw content + a fetch manifest under `raw/connectors/<name>/`, with multi-instance config (`web-search-1`, `web-search-2`) and selective runs (`kb ingest-connector <name>|all`). Synthesis stays in the existing ingest pipeline — connectors only fetch. Supersets the URL-aware `kb_ingest` adapter entry under "Ingest & Query Convenience" below. Hard requirement: all connector output passes the `wrap_wiki_context` fence + `.llmwikiignore`/secret-scanner rail before any LLM call — openwiki itself ships no such boundary and this is flywheel's differentiator. Source: langchain-ai/openwiki connector architecture.
  (effort: High — connector ABC + manifest schema + 2 reference connectors + config plumbing + secret-scanner integration)

### HIGH LEVERAGE — Epistemic Integrity 2.0

- `ingest/pipeline.py` subsection-level provenance — allow `source: raw/file.md#heading` or `raw/file.md:L42-L58` deep-links in frontmatter; ingest extractor captures heading context. Source: Agent-Wiki (kkollsga, gist).
  (effort: Medium — extractor update + citation renderer + backlink resolver)

- `lint/drift.py` `kb_drift_audit` — cold re-ingest a random sample of raw sources with no prior wiki context, diff against current wiki pages, surface divergence as "potential LLM drift". Different from existing `kb_detect_drift` (which checks source mtime). Source: Memory Drift Prevention (asakin, gist; ETH Zurich study).
  (effort: Medium — new module; reuse existing `ingest_source` with `wiki_dir=tmp` then diff)

- `compile/merge.py` `kb_merge <a> <b>` — MCP tool merges two pages, updates all backlinks, archives absorbed page to `wiki/archive/` with a redirect stub, one git commit per merge. Source: Louis Wang.
  (effort: Medium — duplicate-slug detection tracked separately in Phase 4.5 MEDIUM)

- `ingest/pipeline.py` `lint/semantic.py` inline claim-level confidence tags — emit `[EXTRACTED]`, `[INFERRED]`, `[AMBIGUOUS]` markers in wiki page bodies during ingest; `kb_lint_deep` spot-verifies a random sample of EXTRACTED-tagged claims against the raw source file. Complements page-level `confidence` frontmatter.
  (effort: Medium — ingest prompt update + regex claim parser + lint spot-check against raw source text)

- `lint/checks.py` `lint/semantic.py` claim-to-source grounding verification — sample N claims from each wiki page and verify they have supporting text in the cited `raw/` source via BM25 search. Pages where sampled claims score below threshold get `belief_state: uncertain` written back.
  (effort: High — BM25 scorer over raw-source text; sample selector; frontmatter write-back; tunable N and threshold)

- `models/frontmatter.py` `lint/checks.py` multi-source confirmation gate — `belief_state: confirmed` currently requires no corroboration. Add a `source_count` field (auto-incremented by `ingest_source`) and a lint rule that flags `belief_state: confirmed` on pages with `source_count < 2` as `belief_state: uncertain`.
  (effort: Medium — `source_count` tracking + lint check + frontmatter validator update + migration)

### MEDIUM LEVERAGE — Synthesis & Exploration

- `lint/consolidate.py` `kb_consolidate` — scheduled async background pass: NREM (new events → concepts), REM (contradiction detection → mark old edges `superseded`), Pre-Wake (graph health audit). Nightly cron at scan tier. Source: Anda Hippocampus (ICPandaDAO).
  (effort: High — three sub-passes; "superseded" edge state as new primitive)

- `query/synthesize.py` `kb_synthesize [t1, t2, t3]` — k-topic combinatorial synthesis: walks paths through the wiki graph across a k-tuple of topics. Source: Elvis Saravia.
  (effort: Medium — graph traversal + synthesis prompt; budget-gate k≥3)

- `export/subset.py` `kb_export_subset <topic> --format=voice` — emit a topic-scoped wiki slice loadable into voice-mode LLMs or mobile clients.
  (effort: Low — topic-anchored BFS + single-file markdown bundle)

### HIGH LEVERAGE — Ambient Capture & Session Integration

- `ingest/session.py` — auto-ingest Claude Code / Codex CLI / Cursor / Gemini CLI session JSONLs as raw sources. Distinct from `kb_capture` (user-triggered) and deferred "conversation→KB promotion".
  (effort: Medium — JSONL parsers per agent + dedup against existing `raw/conversations/`)

- `hooks/` `SessionStart` hook + `raw/` file watcher — auto-sync on every Claude Code launch; debounced file watcher triggers ingestion on new files in `raw/` without explicit CLI invocation.
  (effort: Low — Claude Code hook + `watchdog` file observer)

- `ingest/filter.py` `.llmwikiignore` + secret scanner — pre-ingest regex-based secret/PII filter; rejects or redacts before content leaves local. Missing safety rail. Source: rohitg00 LLM Wiki v2 + Louis Wang security note.
  (effort: Low — `detect-secrets`-style regex list + glob-pattern ignore)

- `_raw/` staging directory — vault-internal drop-and-forget directory for clipboard pastes; next `kb_ingest` promotes to `raw/`. Source: Ar9av/obsidian-wiki.
  (effort: Low — directory convention + promotion step in ingest)

### MEDIUM LEVERAGE — Refinements to existing Phase 5 deferred items

- Deferred "multi-signal graph retrieval" — empirical weights 3 (direct link) / 4 (source-overlap) / 1.5 (Adamic-Adar) / 1 (type-affinity). Source: nashsu/llm_wiki.
- Deferred "community-aware retrieval boost" — Louvain intra-edge density <0.15 = "sparse/weak" threshold. Source: nashsu.
- Deferred "graph topology gap analysis" — expose card types: "Isolated (degree ≤ 1)", "Bridge (connects ≥ 3 clusters)", "Sparse community (cohesion < 0.15)" — each with `kb_evolve --research` trigger.

### LOW LEVERAGE — Testing Infrastructure

- `tests/test_e2e_demo_pipeline.py` hermetic end-to-end pipeline test — single test driving `ingest_source` → `query_wiki` → `run_all_checks` over committed `demo/raw/karpathy-x-post.md` and `demo/raw/karpathy-llm-wiki-gist.md` sources. Catches cross-module integration regressions. Layer 1 of three-layer e2e strategy.
  (effort: Low — ~100-line single test file, no new fixtures)

### DEFERRED — API-level LLM provider integration (Cycle 21 explicit deferral)

> Cycle 21 delivered **CLI subprocess** integration for 8 backends. REST API / SDK integration is explicitly deferred.

- `utils/api_backend.py` (new) — add API-level integration via LiteLLM or per-provider SDK. Route `KB_LLM_BACKEND=litellm` (or `openai`) through `call_api(...)`. `"anthropic"` stays on the existing SDK path; CLI tool backends remain on subprocess.
  (effort: Medium — new `api_backend.py` module + config additions + routing gate update + tests)

- `utils/api_backend.py` (new) — first-class vLLM support through its OpenAI-compatible HTTP server. Route `KB_LLM_BACKEND=vllm` with `KB_VLLM_BASE_URL` defaulting to `http://localhost:8000/v1`. Preserve safety contract: timeout + retry, redacted errors, bounded response size, JSON schema validation.
  (effort: Medium — config additions + routing + OpenAI-compatible client + mocked HTTP tests)

### LOW LEVERAGE — Operational

- `wiki/_schema.md` vendor-neutral single source of truth — move project schema (page types, frontmatter fields, wikilink syntax, operation contracts) out of tool-convention files into `wiki/_schema.md`. `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` stay thin (~10-line) vendor shims pointing at `_schema.md`. Schema machine-parseable and validated by lint on every ingest.
  (effort: Medium — `wiki/_schema.md` + `kb.schema.load()` + `kb_lint` integration + `schema_version` + `kb migrate` CLI)

- `cli.py` `kb search --serve` localhost UI — `kb search <query>` subcommand already shipped (cli.py:622-624 — BM25 + optional vector fusion); remaining is `--serve` flag exposing a minimal localhost web UI. Source: Karpathy tweet.
  (effort: Low — Flask/FastAPI localhost UI wrapping existing search command)

- Git commit receipts on ingest — emit `"four new articles appeared: ..."` style summary with commit hash and changed files per source. Source: Fabian Williams.
  (effort: Low — wrap existing ingest return dict with a formatter)

### HIGH LEVERAGE — Ingest & Query Convenience

- `mcp/core.py` `kb_ingest` URL-aware 5-state adapter — accept URLs alongside file paths; URL routing table maps patterns to source type + `raw/` subdir + adapter; checks 5 states (`not_installed`, `env_unavailable`, `runtime_failed`, `empty_result`, `unsupported`) each with specific recovery hint.
  (effort: Medium — URL routing table + per-state error handling + adapter dispatcher)

- `mcp/core.py` `kb_delete_source` MCP tool — remove raw source file and cascade: delete source summary wiki page, strip source from `source:` field on shared entity/concept pages, clean dead wikilinks, update `index.md` and `_sources.md`.
  (effort: Medium — cascade deletion + backlink cleanup + atomic index/sources update)

- `mcp/health.py` `kb_rebuild_indexes` MCP tool — wrap `kb.compile.compiler.rebuild_indexes` so MCP clients can trigger the clean-slate rebuild without shelling out to the CLI.
  (effort: Low — thin wrapper + regression test + same-class peer scan)

- `evolve/analyzer.py` `kb_evolve mode=research` — for each gap, decompose into 2–3 web search queries, fetch top results, save to `raw/articles/`, return paths. Capped at 5 sources per gap, max 3 rounds. Source: claude-obsidian autoresearch skill.
  (effort: Medium — gap decomposition prompt + fetch MCP integration + 3-round loop)

### MEDIUM LEVERAGE — Search & Indexing

- `query/bm25.py` `query/embeddings.py` chunk-level sub-page indexing — split pages into topically coherent chunks via Savitzky-Golay boundary detection; each chunk indexed as `<page_id>:c<n>`; query engine scores chunks then dedups to best chunk per page. Source: garrytan/gbrain semantic.ts + sage-wiki.
  (effort: High — SG chunking module + BM25 index schema change + chunk-to-page dedup aggregation)

- `lint/checks.py` `query/engine.py` PageRank-prioritized semantic lint sampling — when `kb_lint_deep` must limit its page budget, select pages by PageRank descending. High-authority pages with quality issues have outsized downstream impact.
  (effort: Low — sort by graph_stats PageRank before sampling)

### MEDIUM LEVERAGE — Page Lifecycle & Quality Signals

- `wiki/hot.md` wake-up context snapshot — ~500-word compressed context updated at session end; read at session start via `SessionStart` hook; survives context compaction. Source: MemPalace + claude-obsidian hot cache.
  (effort: Low — append-on-ingest + SessionStart hook reads + one markdown file)

- `wiki/overview.md` living overview page — auto-revised on every ingest as final pipeline step; always-current executive summary. Source: llm-wiki-agent.
  (effort: Low — scan-tier LLM over index.md + top pages; one file auto-updated per ingest)

### MEDIUM LEVERAGE — Knowledge Promotion & Ingest Quality

- `query/engine.py` `feedback/store.py` conversation→KB promotion — positively-rated query answers (rating ≥ 4) auto-promote to `wiki/synthesis/{slug}.md` pages with citations. Source: garrytan/gbrain maintain skill.
  (effort: Medium — feedback store hook + synthesis page writer + conflict check)

- `ingest/pipeline.py` two-step CoT ingest — split ingest into (1) analysis call (entities + connections + contradictions + structure recommendations); (2) generation call using analysis as context. Source: nashsu/llm_wiki.
  (effort: Medium — split single ingest LLM call into two sequential calls)

### Phase 6 candidates (larger scope, not yet scheduled)

- Hermes-style independent quality-gate supervisor — different-model-family validator before page promotion. Source: Secondmate (@jumperz).
- Mesh sync for multi-agent writes — last-write-wins with timestamp resolution; private-vs-shared scoping. Source: rohitg00.
- Hosted MCP HTTP/SSE variant — multi-device access (phone Claude app, ChatGPT, Cursor, Claude Code). Source: Hjarni/dev.to.
- Personal-life-corpus templates — Google Takeout / Apple Health / AI session exports / bank statements. Privacy-aware ingest layered on `.llmwikiignore`.
- Multi-signal graph retrieval — BM25 seed → 4-signal graph expansion (direct ×3 + source-overlap ×4 + Adamic-Adar ×1.5 + type-affinity ×1). Prerequisite: typed semantic relations. Source: nashsu.
- Typed semantic relations on graph edges — 6 types (`implements`, `extends`, `optimizes`, `contradicts`, `prerequisite_of`, `trades_off`) stored as edge attributes. Source: sage-wiki.
- Temporal claim tracking — `valid_from`/`ended` date windows on individual claims; staleness/contradiction at claim granularity. Requires SQLite KG schema. Source: MemPalace.
- Semantic edge inference in graph — two-pass build: wikilink edges as EXTRACTED + LLM-inferred implicit relationships as INFERRED/AMBIGUOUS. Source: llm-wiki-agent.
- Answer trace enforcement — synthesizer tags every factual claim with `[wiki/page]` or `[raw/source]` citation; post-process flags uncited claims as gaps.
- Multi-mode search depth toggle (`depth=fast|deep`) — `depth=deep` uses Monte Carlo evidence sampling; `depth=fast` is current BM25 hybrid. Source: Sirchmunk.
- **Hybrid RAG + Wiki compiler architecture** — two-tier retrieval: RAG layer (pgvector) for high-volume raw corpus; compiled wiki layer for curated authoritative pages. Query router scores wiki hits first, falls back to RAG chunks (flagged `[unverified]`). Enables enterprise-scale corpora (100k+ docs) without sacrificing auditability. Prerequisite: multi-user storage migration.
- Semantic deduplication pre-ingest — embedding similarity check before ingestion; flag if cosine >0.85 to any existing raw source.
- Interactive knowledge graph HTML viewer — vis.js HTML export from `kb_graph_viz` with `format=html`; dark theme, search, click-to-inspect, Louvain clustering, edge type legend.
- Two-phase compile pipeline + pre-publish validation gate — phase 1: batch cross-source merging; phase 2: validation gate rejects pages with unresolved contradictions or missing citations.
- Actionable gap-fill source suggestions — enhance `kb_evolve` to suggest specific real-world sources for each gap. Mostly superseded by `kb_evolve mode=research`; keep as offline fallback.

### Phase 7 candidates — Enterprise source integrations (not yet scheduled)

> Prerequisite: Phase 6 multi-user storage migration + Hybrid RAG layer must land first.
> Core design change: `raw/` becomes a logical namespace, not a single folder. Each source root is registered with a connector type, credentials, and sync policy.

- **Multi-root raw directory support** — `KB_RAW_ROOTS` env var (colon-separated paths) or `sources.yaml` registry so a single wiki can compile from multiple raw directories. Threads `raw_roots: list[Path]` through `ingest_source` / `compile_wiki` / `kb_detect_drift` and merges hash manifests per-root. Prerequisite for all connectors below.
- **SharePoint / OneDrive connector** — Microsoft Graph API delta sync; markitdown for `.docx`/`.pptx`/`.pdf`/`.xlsx`; permission-aware.
- **Google Drive / Google Shared Drives connector** — Drive API v3 with `driveId` + `includeItemsFromAllDrives`; Google Docs → markdown via export API; change-token polling.
- **Confluence connector** — REST API v2 storage-format HTML → markdown; respects space/page permissions; attachments downloaded as sibling raw files.
- **Notion connector** — Notion API v1 blocks/databases → markdown; handles inline databases, toggles, callouts; `last_edited_time` cursor.
- **GitHub / GitLab repo connector** — markdown docs, READMEs, wiki pages from repos. Extends existing `repos/` source type. Webhook-triggered for live orgs.
- **Credential & secret store integration** — connector tokens stored in system keychain (Windows Credential Manager / macOS Keychain / Linux Secret Service) or HashiCorp Vault / AWS Secrets Manager. `.env` fallback for dev. Prerequisite for any connector shipping to production.
- **Sync policy & scheduling** — per-source-root sync schedule (cron-style or `on_change` webhook) with last-sync timestamp, retry backoff, `dry_run`. Surfaces as `kb sync` CLI and `kb_sync` MCP tool.

### Phase 8 candidates — Strategic rewrite / Rust core (not yet scheduled)

> Trigger: Phase 6 + Phase 7 are shipped and production load reveals bottlenecks, OR codebase legacy decisions block enterprise path. "Revisit annually" decision.

**Recommended architecture (decided 2026-04-21):** TypeScript / Next.js view layer (Phase 8A) calls into Python AI brain (current stack) which optionally calls Rust hot-path extension (Phase 8B). Python orchestration layer unchanged.

- **Phase 8A — TypeScript view layer (Next.js)** — ships as `kb serve` command. UI calls existing MCP tools via thin HTTP adapter. No Python changes. (effort: Medium)
- **Phase 8B — Rust hot-path extension via maturin/PyO3** — optional `pip install kb[fast]` extra replacing Python BM25 indexer + file scanner with Rust equivalents (tantivy). 5–20× scan-tier throughput on large corpora. (effort: Medium)
- **Cloud wiki storage backends** — `WikiStorage` protocol abstracting `atomic_text_write` / `file_lock`; opt-in via `KB_WIKI_STORAGE=s3|azure|gcs`. Object storage has no atomic rename — must use conditional PUT (`If-None-Match: *` for create, ETag for update). `file_lock` becomes distributed (Redis `SET NX PX`, DynamoDB conditional, Azure Blob lease). Prerequisite: Phase 6 multi-user storage migration. (effort: High)

**Decision criteria (revisit when):**
- Compile time for 10k sources exceeds 30 min → Phase 8B Rust spike
- Concurrent users > 20 with write contention → async job queue (Python, pre-Phase 8)
- Deployment friction blocks enterprise sales → Phase 8A Next.js wrapper first
- Team spans multiple machines / cloud deploy needed → cloud wiki storage backend

### Phase 9 candidates — Personal Context Layer (prompt ⇄ knowledge compounding loop) (2026-07-22)

> Source: re-read of *"What an Enterprise Context Layer Actually Is"* mapped onto the "5-folder method".
> Framing: the product is not a prompt store — it turns every human edit into **reviewable, reusable, propagating personal context**. The enterprise version serves hundreds of agents and dozens of teams; this one serves one person and one AI. Same skeleton.
> Substrate mapping: folders 1–2 (who I am + product/service) → **Knowledge** (map of the business); folders 3–4 (customer voice + cases) → **Expertise** (how work actually gets done); folder 5 (output rules) → **Norms** (rules of acceptable action).
> Sequencing rule: ship W1 → W5 in order. Do **not** start with RAG, knowledge graph, or full-text search — the corpus is currently empty (0 records) and the loop must be proven before scale features.

**W1 — Prompt Learning Loop** *(first: proves prompts actually get reused and get better)*
- Prompt usage record — log every copy / "add to Codex draft" event with timestamp, target model, and the context versions referenced at that moment. (effort: Small)
- Review-result capture — after a run, store the AI draft and the user's final edited version as a pair. The **diff** is the asset, not the output. (effort: Medium)
- Before/after diff view + prompt version history with rollback. (effort: Medium)

**W2 — Context Pack (the substrate)**
- Space isolation — per person / client / product, so contexts never bleed into each other. (effort: Medium)
- Three context types — Knowledge / Expertise / Norms as first-class records. One schema, three types — **not** five parallel storage structures. (effort: Medium)
- Five-folder cold-start wizard — the 5-folder method is an onboarding template layered over the 3 types. (effort: Small)
- Explicit context references from a prompt, pinned to a specific context version. (effort: Medium)

**W3 — Learning Inbox** *(the system must never silently infer a permanent rule)*
- Learning Candidate extraction from a human edit, carrying source, evidence (the diff), scope, and proposed target. (effort: Medium)
- Human review with exactly five outcomes: this-prompt-only / → Knowledge / → Expertise / → Norms / don't learn. **Hard invariant:** one correction never becomes a standing rule without explicit approval. (effort: Small)

**W4 — Change Propagation**
- Impacted-prompt list surfaced whenever a context record is updated. (effort: Medium)
- Three propagation modes — **Follow** (auto; low-risk, explicitly-referenced only) / **Review** (default; queued for approval) / **Pinned** (keeps a certified older version). (effort: High)

**W5 — Model adaptation** *(one knowledge base, many models)*
- Base Prompt + Model Adapter split — Knowledge stays single-source; the adapter holds model-specific instruction shape, example format, tool constraints, token budget. **Never fork the knowledge base per model.** (effort: Medium)
- Model Profile registry — model id, family, capability version. (effort: Small)
- Adapter resolution order — exact model → model family → base prompt fallback. (effort: Small)
- Certification state per (prompt, model) — verified / limited / untested / incompatible / needs-recheck. (effort: Medium)
- Review triage gains a 4th axis — knowledge wrong / base prompt wrong / this model only / don't learn. A model-only failure updates that adapter alone. (effort: Small)
- Invalidation rules — a Knowledge or Base Prompt change marks dependent certifications `needs-recheck`; a model version bump marks `needs-recheck` only and **never** auto-rewrites prompt content. (effort: Medium)

**Deferred until the loop is proven** — full-text search, conflict detection, published/versioned Context Packs, import/export, sync + team review, RAG, knowledge graph.

**First shippable slice** (current state = 0 records): first-content wizard → prompt gets used → review result recorded → new version saved → reused next time.

### Design tensions to document in README (not items to implement)

- **Container boundary / atomic notes tension (WenHao Yu)** — `kb_ingest` forces a "which page does this merge into?" decision; document that our model merges aggressively and that atomic-note alternatives exist.
- **Model collapse (Shumailov 2024, Nature)** — cite in "known limitations": LLM-written pages feeding next LLM ingest degrade across generations; counter is evidence-trail provenance + two-vault promotion gate.
- **Enterprise ceiling (Epsilla)** — document explicit scope: personal-scale research KB, not multi-user enterprise; no RBAC, no compliance audit log, file-I/O limits at millions-of-docs scale.
- **Vibe-thinking critique (HN)** — *"Deep writing means coming up with things through the process of producing"*; defend with mandatory human-review gates on promotion.

---

## Phase 6 R2 — Wider mimo-v2.5-pro audit (2026-05-04)

<!-- 6 parallel mimo-v2.5-pro CLI calls (arch / tests / docs / security-wide / env / deps).
     Items already covered by SECURITY.md or earlier BACKLOG entries OMITTED.
     Source tag: (mimo r{N}).

     CYCLE 67 (2026-05-07) cleanup pass — many entries shipped or verified stale:
     - GitPython unpinned (mimo r6 Q1) → cycle 67 Step 15 bumped to >=3.1.49,<3.2 (CVE-2026-44244).
     - SSRF on URL → external CLI argv (mimo r4 B) → VERIFIED STALE: lint/fetcher.py has DNS-resolve + IP-allowlist + scheme-allowlist + per-hop redirect validation; crawl4ai/yt-dlp not imported in src/kb/.
     - KB_PROJECT_ROOT call-time (mimo r5 Q1) → SHIPPED cycle 65 AC1 as get_project_root().
     - AUGMENT_ALLOWED_DOMAINS call-time (mimo r5 Q5) → SHIPPED cycle 65 AC3 as get_allowed_domains().
     - _autouse_kb_path_sandbox no-drop guard (mimo r2 Q1) → SHIPPED cycle 67 AC08 (AST meta-test).
     - hardcoded lru_cache list (mimo r2 Q2) → SHIPPED cycle 17 AC16 (auto-discovery in conftest).
     - trafilatura cache disable (mimo r6 Q5) → SHIPPED cycle 65 (TRAFILATURA_DOWNLOAD_NO_CACHE=1).
     - _DEFAULT_MODEL_TIERS dual mechanism (mimo r5 Q1+Q2) → SHIPPED cycle 67 AC01 (actual surface was MODEL_TIERS, replaced with _ModelTiersView(Mapping)).
     - MCP error response raw tracebacks (mimo r4 E) → SHIPPED cycle 65 AC21 (_mcp_error_boundary).
     - _check_no_secrets_on_argv self-DoS (mimo r4 A) → VERIFIED INCORRECT: cycle 67 AC15 added 6 lock-in tests proving the substring scan is correct (no regex on argv).
     - graph/cache 6th-caller drift (mimo r1 Q4) → SHIPPED cycle 67 AC02 (AST guard test) on top of cycle 64 __all__=[].
     - tests/test_cycle64_snapshots.py tautology (mimo r2 Q4) → SHIPPED cycle 67 AC09 (non-vacuous paired negative-controls).
     - CI sk-ant-dummy grep (mimo r5 Q7) → SHIPPED cycle 67 AC11 (broadened cycle-65 src-only scan to all tracked files with allowlist).
     - docs/reference/ INDEX.md (mimo r3 NEW) → cycle-65 AC20 forward + cycle 67 AC14 inverse both shipped.


     CYCLE 67 CARRY-OVER to cycle 68 (design-locked, deferred for time/risk):
     - cli_backend.py:241 pre-cap stdout buffering → SHIPPED cycle 68 AC01 (Popen refactor + chunked stdout cap with platform-aware kill).
     - kb/__init__.py public API docstring audit (mimo r3 Q7) → SHIPPED cycle 68 AC05 (scripts/audit_docstrings.py with Args/Returns/Raises gate).
     - duplicate-slug allowlist externalization (Phase 4.5 MEDIUM) → SHIPPED cycle 68 AC04 (wiki/_lint.yml lazy YAML loader with safe_load).
     - mcp_server.py + mcp/__init__.py PEP-562 redundancy (mimo r1 Q5) → still LOW; deferred indefinitely (low-value churn). -->


### HIGH

### MEDIUM

### LOW


- `mcp_server.py` shim + `mcp/__init__.py` PEP-562 lazy loader — two bootstrap paths for the same `mcp.app:main`. Redundancy with split test responsibility. (mimo r1 Q5)
  (fix: delete `mcp_server.py`, point `pyproject.toml [project.scripts]` at `kb.mcp.app:main` directly; preserve legacy import path via `kb/__init__.py.__getattr__` if external consumers depend on it.)

---

## Phase 6 — Cross-LLM cycle-64 audit (mimo-v2.5-pro, 2026-05-04)

<!-- f-string-in-SQL concern was REJECTED by both runs (fully closed by integer
     validation, query/embeddings.py:651). Underlying weights behind the
     mimo-v2.5-pro endpoint self-identify as GLM-4 / Zhipu AI; Token Plan
     billing is genuinely mimo-v2.5-pro at 2x credits. -->

### LOW

---

## Resolved Phases

- **Phase 3.92** — all items resolved in v0.9.11
- **Phase 3.93** — all items resolved in v0.9.12 (2 MEDIUM deferred to Phase 3.94: extractors LRU cache, raw_content rename)
- **Phase 3.94** — all items resolved in v0.9.13
- **Phase 3.95** — all items resolved in v0.9.14
- **Phase 3.96** — all items resolved in v0.9.15
- **Phase 3.97** — all items resolved in v0.9.16
- **Phase 4 (v0.10.0) post-release audit** — all items resolved (23 HIGH + ~30 MEDIUM + ~30 LOW) per CHANGELOG.md `[Unreleased]`
- **Phase 4.5 CRITICAL (cycle 1)** — 16+ items resolved (#1 _rel(), #2 sentinel, #5 Error[partial], #7 read-cap, #11 affected_pages, #12 verdict cap, #13 page_id Windows-reserved, #14 source-deleted drift, #15 query rewriter CJK, #16/18 BM25 cache, #17 dedup quota, #19 yaml_sanitize, #20 wiki_log rotation, #22 contradictions caller, #23 export_mermaid, #24 BM25 postings, #25 template hashes, #28 load_purpose, #29 inject_wikilinks) per CHANGELOG cycle-1, cycle-1-docs-sync, Backlog-by-file cycle-4. #3 [source: X] → [[X]] migration deferred as a dedicated atomic migration.
- **Phase 4.5 HIGH-Deferred — `query/embeddings.py` vector-index lifecycle** — all sub-items resolved across cycles 24/25/26/28/64 (atomic temp-DB-then-replace, dim-mismatch observability, cold-load instrumentation, sqlite-vec instrumentation, BM25 build counter, `_index_cache` cross-thread lock, dim-mismatch AUTO-rebuild).
- **Phase 4.6 (DeepSeek V4 Pro full-repo audit)** — all items resolved across cycles 42/44/45/46.
- **Phase 5 three-round code review (2026-04-17)** — all items resolved per CHANGELOG `[Unreleased]` Backlog-by-file cycle 1.
- **Phase 5 pre-merge lint augment (2026-04-15)** — all items resolved per CHANGELOG cycle 17 (AC11/AC12/AC13).
- **Phase 5 pre-merge CRITICAL `feat/kb-capture` (2026-04-14)** — `capture.py` `_write_item_files` two-pass-write architecture shipped cycle 17 AC10 (Phase 1 `O_EXCL`-reserve → Phase 2 alongside-from-finalised-slugs → Phase 3 atomic-promote with all-or-nothing rollback). See `src/kb/capture.py:589-674` docstring.
- **Cycle 21/22 candidates** — all open items resolved per CHANGELOG cycle 22.
