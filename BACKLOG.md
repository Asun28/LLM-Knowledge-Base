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

## Phase 6 R2 — Wider mimo-v2.5-pro audit (2026-05-04)

<!-- 6 parallel mimo-v2.5-pro CLI calls (arch / tests / docs / security-wide / env / deps).
     Items already covered by SECURITY.md or earlier BACKLOG entries OMITTED.
     Source tag: (mimo r{N}). -->

### HIGH

- `requirements.txt` `GitPython>=3.1.47` — only unpinned dependency in the file (every other line uses `==`); GitPython has carried RCE-class CVEs (2022-24439, 2023-40267, 2023-40590, 2024-22190), and a future 3.1.48+ release can pull in a regression with no PR-time signal. (mimo r6 Q1)
  (fix: `GitPython==3.1.47` (or latest verified-safe) with explicit ceiling, e.g. `>=3.1.47,<3.2`.)

- `ingest/pipeline.py` URL → external CLI — bare URL passed to `trafilatura` / `crawl4ai` / `yt-dlp` argv with no scheme allowlist (`file://`, `gopher://`, `data://` accepted) and no RFC1918 / loopback / link-local filter. Enables SSRF and local-file exfiltration via `file:///etc/passwd` or `http://169.254.169.254/...`. (mimo r4 B)
  (fix: enforce `urlparse(url).scheme in {"http","https"}` + DNS-resolve hostname + reject when `ipaddress.ip_address(addr).is_private or .is_loopback or .is_link_local` BEFORE the subprocess spawn.)

- `config.py:17` `KB_PROJECT_ROOT` — env var read at MODULE IMPORT TIME, inconsistent with the cycle-19 L2 call-time rule that the kill-switches and `KB_LLM_BACKEND` follow. Tests setting `KB_PROJECT_ROOT` after `import kb.config` get the stale resolved value. (mimo r5 Q1)
  (fix: replace module-level `_PROJECT_ROOT = ...` with a `get_project_root()` accessor that re-reads `os.environ["KB_PROJECT_ROOT"]` at call time; expose `_reset_project_root()` for tests.)

- `tests/conftest.py` `_autouse_kb_path_sandbox` no-drop guard — silent breakage if `autouse=True` is ever removed. Sandbox failure cascades into 200 test files writing to the real `wiki/` and `raw/` dirs. (mimo r2 Q1)
  (fix: meta-test that `ast.parse`s `tests/conftest.py`, locates the `_autouse_kb_path_sandbox` `FunctionDef`, and asserts its decorator list includes `pytest.fixture(autouse=True)`.)

- `tests/conftest.py` hardcoded lru_cache clear list — `load_purpose` + `_load_template_cached` + `_build_schema_cached` only. Production adding a 4th `@lru_cache` on a path-sensitive callable silently leaks across tests. (mimo r2 Q2)
  (fix: at sandbox teardown, walk every `kb.*` module in `sys.modules`, introspect attributes for `cache_clear`, and call all of them; remove the hardcoded list.)

### MEDIUM

- `lint/fetcher.py:31` trafilatura + diskcache transitive RCE chain — project's own robots cache is in-memory `dict`, NOT diskcache, so direct attack path is mitigated. Trafilatura's internal `fetch_url` + extraction code paths NOT audited for diskcache pickle reads on attacker-supplied URLs. (mimo r6 Q5)
  (fix: confirm `trafilatura.fetch_url(...)` is invoked with caching disabled (`TRAFILATURA_DOWNLOAD_NO_CACHE=1`); OR pin diskcache to a patched version once one ships.)

- `config.py:161-163` `_DEFAULT_MODEL_TIERS` dual mechanism — captures `os.environ.get(CLAUDE_*_MODEL)` at IMPORT TIME, while the canonical `MODEL_TIERS` accessor re-reads at call time per cycle-7 AC24. Any caller referencing `_DEFAULT_MODEL_TIERS` directly bypasses the call-time fix. (mimo r5 Q1, Q2)
  (fix: delete `_DEFAULT_MODEL_TIERS`; the accessor returns `os.environ.get(env_key, "").strip() or "<hardcoded-default>"` directly.)

- `config.py:480` `AUGMENT_ALLOWED_DOMAINS` — read + comma-split at IMPORT TIME with default `"en.wikipedia.org,arxiv.org"`. Same hazard class as `KB_PROJECT_ROOT` above. (mimo r5 Q5)
  (fix: replace with `get_allowed_domains()` accessor reading at call time.)

- MCP tool error responses propagate raw tracebacks — exception handlers across `mcp/core.py`, `mcp/ingest.py`, `mcp/quality.py` surface absolute filesystem paths (`/home/<user>/...`, `D:\Projects\...`) and subprocess stderr to the MCP client. Information disclosure on a typically-trusted local boundary. (mimo r4 E)
  (fix: wrap each MCP tool body with a boundary handler that catches `Exception`, logs the full traceback locally, and returns `f"Error: {sanitize_error_text(e)}"`.)

- `utils/cli_backend.py` `_check_no_secrets_on_argv` self-DoS — token-shape regex match on full argv refuses to spawn if ANY element matches a token pattern. A user prompt that legitimately discusses API-key formats silently fails. (mimo r4 A)
  (fix: replace generic regex with value-based scrub — only refuse if an argv element equals the literal value of a listed env-var key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, ...).)

- `graph/cache.py` 6th-caller drift — cycle 64 added the cache with 5 known callers using attribute-lookup form per cycle-18 L1. No `__all__ = []`, no ruff rule, no AST guard prevents a 6th caller doing `from kb.graph.cache import get_graph` and silently bypassing the test-spy hook. (mimo r1 Q4)
  (fix: set `__all__ = []` in `cache.py`, plus AST-grep test that asserts zero `from kb.graph.cache import get_graph` in `src/kb/**/*.py`.)

- `kb/__init__.py` public API docstring audit — `__init__.py` is a 67-line lazy `__getattr__` shim; the real Args/Returns/Raises must live on the underlying functions in `kb/ingest/pipeline.py`, `kb/compile/__init__.py`, `kb/query/__init__.py`, `kb/graph/__init__.py`. Whether those four targets actually carry Google-style sections is unverified. (mimo r3 Q7)
  (fix: `scripts/audit_docstrings.py` imports each `__all__` entry, parses `__doc__` via `docstring_parser`, fails CI if any lacks `Args:` + `Returns:` + (`Raises:` when applicable).)

### LOW

- `mcp_server.py` shim + `mcp/__init__.py` PEP-562 lazy loader — two bootstrap paths for the same `mcp.app:main`. Redundancy with split test responsibility. (mimo r1 Q5)
  (fix: delete `mcp_server.py`, point `pyproject.toml [project.scripts]` at `kb.mcp.app:main` directly; preserve legacy import path via `kb/__init__.py.__getattr__` if external consumers depend on it.)

- `tests/test_cycle64_snapshots.py` tautology risk — syrupy snapshots were captured FROM the same code path under test. No committed proof that mutating an input field causes the snapshot to diverge. (mimo r2 Q4)
  (fix: per snapshot, commit a paired negative-control test that mutates one input field and asserts the snapshot does NOT match; AND reject `--snapshot-update` in CI pytest invocation.)

- CI `ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only` — dummy key in `.github/workflows/ci.yml`. If any test mocks HTTP at the `httpx` layer but not the SDK client constructor, the dummy could leak into a recorded cassette / VCR / pytest snapshot file. (mimo r5 Q7)
  (fix: CI grep step that fails if `sk-ant-dummy` appears anywhere in tracked files except `.github/workflows/ci.yml`.)

- `docs/reference/` lacks an INDEX.md — directory holds 10+ files but no single manifest mapping each to its scope. CLAUDE.md's "Detailed Documentation" table partially serves this role but is hand-maintained. (mimo r3 NEW)
  (fix: generate `docs/reference/INDEX.md` from each file's frontmatter / first H1 + CI script asserting every `*.md` appears in the index AND in CLAUDE.md's table.)

---

## Phase 6 — Cross-LLM cycle-64 audit (mimo-v2.5-pro, 2026-05-04)

<!-- f-string-in-SQL concern was REJECTED by both runs (fully closed by integer
     validation, query/embeddings.py:651). Underlying weights behind the
     mimo-v2.5-pro endpoint self-identify as GLM-4 / Zhipu AI; Token Plan
     billing is genuinely mimo-v2.5-pro at 2x credits. -->

### HIGH

- `mcp/app.py:230` `_validate_page_id` — Windows trailing-dot / trailing-space filename confusion. A page_id like `"secret."` or `"secret "` passes every check, but `Path.resolve()` on Windows silently strips trailing dots and spaces, opening a *different* file than requested. Containment is preserved, so this is filename-confusion / target-substitution, not directory traversal. (mimo r2)
  (fix: before the reserved-name check, reject any segment where `segment != segment.rstrip(". ")`.)

### MEDIUM

- `mcp/app.py:230` `_validate_page_id` — `:` is not in the blocked character set; on Windows, `"page:hidden"` produces NTFS Alternate Data Stream syntax. POSIX accepts the literal filename, creating cross-platform divergence. (mimo r2)
  (fix: extend `_CTRL_CHARS_RE` (or add `_WINDOWS_ILLEGAL_CHARS_RE`) to reject `:` plus `< > " | ? *` at the same gate as the control-char check.)

- `compile/compiler.py:645` `_validate_path_under_project_root` + downstream `rebuild_indexes` unlink — TOCTOU window between containment validation and filesystem mutation. Local attacker with write access inside the project tree can replace the validated path with a junction/symlink. (mimo r1, r2)
  (fix: re-resolve and re-validate immediately before `unlink`/write, OR open with `os.O_NOFOLLOW` (POSIX) / `FILE_FLAG_OPEN_REPARSE_POINT` (Windows) so symlink-following is rejected at the kernel.)

- `mcp/app.py:121,230` + `compile/compiler.py:645` validator-contract drift — three sibling validators with three different contracts: `_validate_wiki_dir` (absolute + exists + dir + single resolved-anchor); `_validate_path_under_project_root` (no exists check, dual literal+resolved anchor); `_validate_page_id` (substring-based + resolved-anchor). A future fourth call site can quietly adopt the weakest contract. (mimo r1, r2)
  (fix: extract one canonical `_assert_under_project_root(path, *, require_exists=False, dual_anchor=True)`, migrate all three current sites, document in `docs/reference/error-handling.md`.)

### LOW

- `mcp/app.py:254` `_validate_page_id` — `".." in page_id` is a substring match that rejects legitimate IDs like `"notes..draft"` or `"c++..faq"`. The final `resolve().relative_to()` is the actual safety net. Cosmetic. (mimo r1)
  (fix: replace with `any(seg == ".." for seg in page_id.replace("\\", "/").split("/"))`.)

- `query/embeddings.py:619` `VectorIndex.build` — multi-PROCESS race on the same `db_path`. Module-level `_rebuild_lock` is a `threading.Lock`, so it serialises threads within one process but does NOT block two concurrent `kb` invocations from running DROP → CREATE → bulk INSERT against the same DB. (mimo r1)
  (fix: take a `file_lock(db_path.with_suffix(".db.lock"))` around the DROP → CREATE → INSERT → COMMIT block.)

- `query/embeddings.py:660` `VectorIndex.build` — `sqlite_vec.load(conn)` raises `sqlite3.OperationalError` whose message includes the absolute filesystem path of the .so/.dll that failed to load; can leak into MCP error responses. (mimo r2)
  (fix: wrap the `sqlite_vec.load(conn)` call in `try/except sqlite3.OperationalError` and re-raise `RuntimeError("sqlite-vec extension failed to load; reinstall the sqlite-vec wheel")` with no path detail.)

---

## Phase 4.5 — Multi-agent post-v0.10.0 audit (2026-04-13)

<!-- Discovered by 5 specialist reviewers (Python, security, code-review, architecture, performance)
     running 3 sequential rounds against v0.10.0. Round tag in parens (R1/R2/R3/R5). -->

### HIGH

- `compile/compiler.py` naming inversion (~16-17) — `compile_wiki` is a thin orchestration shell over `ingest_source` + a manifest; real compilation primitives (`linker.py`) live in `compile/` but are consumed by `ingest/`. Dependency arrows invert the directory names; every new feature placement becomes a coin-flip. (R1)
  (fix: rename to `pipeline/orchestrator.py` and treat `compile/` as wikilink primitives only; or collapse `compile/compiler.py` into `kb.ingest.batch`)

- `ingest/pipeline.py` state-store fan-out — a single `ingest_source` mutates summary page, N entity pages, N concept pages, `index.md`, `_sources.md`, `.data/hashes.json`, `wiki/log.md`, `wiki/contradictions.md`, plus N `inject_wikilinks` writes. Every step is independently atomic, none reversible. A crash between manifest-write and log-append leaves the manifest claiming "already ingested" while the log shows nothing. (R2)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests)

- `graph/builder.py` non-lint `build_graph` callers (cycle-65+) — cycle 64 shipped `kb.graph.cache` and migrated the 5 lint callers to attribute-lookup form per cycle-18 L1. The 5 remaining `build_graph` callers in `evolve/analyzer.py` (3 sites) / `graph/export.py` / `mcp/browse.py` / `query/engine.py` were narrow-scope deferred and still bypass the cache.
  (fix: migrate each caller to `kb.graph.cache.get_graph(wiki_dir)`; emit invalidation hooks on any new mutator path.)

- `tests/` coverage-visibility — ~50 test files are named `test_v0NNN_taskNN.py` / `test_v0NNN_phaseNNN.py` / `test_phase4_audit_*.py`. Verifying canonical-module coverage requires grepping versioned files. Freeze-and-fold cadence in progress; cumulative ~190+ versioned files still to fold across future cycles. Per-cycle progress is in CHANGELOG-history.md, not here. (R3)
  (fix: freeze-and-fold rule — once a version ships, fold its tests INTO the canonical module file; enable `coverage` in CI and surface per-module % in PR comments)

- `mcp/core.py` + `browse.py` + `health.py` + `quality.py` — all 25 MCP tools are sync `def`. FastMCP runs them via `anyio.to_thread.run_sync` on a default 40-thread pool. Long tools (`kb_query(use_api=True)` 30s+, `kb_lint()` multi-second, `kb_compile()` minutes, `kb_ingest_content(use_api=True)` 10+s) each hold a thread; under concurrent tool calls the pool saturates. (R3)
  (fix: make long-I/O tools `async def` and `await anyio.to_thread.run_sync(...)` around the SDK call; or document / tune `FastMCP(num_threads=N)`; at minimum surface the concurrency model in the `app.py` instructions block)

- `ingest/pipeline.py:603,715-721,729-754` lock acquisition order risk between same-ingest stages — within one `ingest_source`: stage 1 writes summary page → `append_evidence_trail` to SAME page; stage 2 calls `_update_existing_page` on each entity (re-reads + re-writes); stage 9 `inject_wikilinks` re-reads + re-writes pages it just wrote in stages 1-3; stage 11 writes `wiki/contradictions.md`. None use `file_lock`. Under concurrent ingest A + B, read-then-write windows in different stages overlap non-deterministically. (R5)
  (fix: per-page write-lock helper `with page_lock(page_path):` wrapping `read_text → modify → atomic_text_write` consistently across `_write_wiki_page`, `_update_existing_page`, `append_evidence_trail`, `inject_wikilinks`; OR coarse wiki-wide ingest mutex)

### MEDIUM

- `config.py` god-module — 35+ unrelated constants (paths, model IDs, BM25 hyperparameters, dedup thresholds, retries, ingest/evolve/lint limits, retention caps, query budgets, RRF, embeddings). Single-file churn invalidates import cache for the whole package in tests. (R1)
  (fix: split into `config/paths.py` / `config/models.py` / `config/limits.py` / `config/search.py` / `config/lint.py`; or a `Settings` dataclass with grouped subfields; keep `from kb.config import *` shim)

- `lint/checks/duplicate_slug.py` `check_duplicate_slugs` — known-distinct near-slug pairs need an operator-managed allowlist instead of code edits. Current examples: `concepts/bot` vs `concepts/llm`, `entities/openai` vs `entities/openclaw`, `entities/logql` vs `entities/promql`.
  (fix: move duplicate-slug allowlist to `wiki/_lint.yml` or `.data/lint_allowlist.json`, document the format, have `kb lint` load it before reporting duplicate-slug warnings)

- `compile/compiler.py` `compile_wiki` per-source rollback — observability variant shipped (cycle 25 AC6/AC7/AC8: `in_progress:{pre_hash}` marker + stale-marker warning + full-mode prune exemption). Remaining: (a) rollback of wiki writes on manifest-save failure (requires receipt-file design or transaction-like helper); (b) escalating manifest-write failure to CRITICAL. (R1)
  (fix: per-ingest receipt file `.data/ingest_locks/<hash>.json` enumerating completed steps, written first and deleted last; recovery pass detects and completes partial ingests.)

- `utils/io.py` `atomic_json_write` + `file_lock` pair — 6+ Windows filesystem syscalls per small write. Cycle 24 AC9 added exponential backoff to `file_lock`; the JSONL-migration part remains open. (R1)
  (fix: append-only JSONL with `msvcrt.locking` / `fcntl` locking; compact on read or via explicit `kb_verdicts_compact`)

- `lint/fetcher.py` `diskcache==5.6.3` — CVE-2025-69872 (GHSA-w8v5-vhqr-4h9v): pickle-deserialization RCE. No patched upstream as of last re-check.
  (mitigation: diskcache used only by trafilatura's robots.txt cache; exploit requires local write access to the cache directory; `grep -rnE "diskcache|DiskCache|FanoutCache" src/kb` confirms zero direct imports; track upstream for patched release)

- `.venv` `pip==26.0.1` — CVE-2026-3219 (GHSA-58qw-9mgm-455v): pip handles concatenated tar+ZIP files as ZIP regardless of filename. No confirmed patched upstream.
  (mitigation: pip is TOOLING, not runtime; advisory affects `pip install` of adversarial payloads which requires local shell access. Production `kb` runtime never shells out to pip. Track upstream.)

- `compile/linker.py` cross-reference auto-linking — when ingesting a source mentioning entities A, B, C, add reciprocal wikilinks between co-mentioned entities (`[[B]]`/`[[C]]` on A's page and vice versa) as a post-ingest step after existing `inject_wikilinks`.

- `ingest/pipeline.py` `IndexWriter` consolidation refactor — cycle 35 closed the immediate RMW concurrency hazard via `file_lock(target_path)`. Open: code-quality refactor — `IndexWriter` helper wrapping all four index-file writes (`_sources.md`, `index.md`, `_categories.md`, `log.md`) with documented lock-acquire order. Defer until a cycle adds a 4th caller.

- `ingest/pipeline.py` `_update_existing_page` body-write + evidence-append two-write consolidation — cycle 24 AC1 shipped single-atomic-write inline rendering for `_write_wiki_page` (new-page path). Update path remains: existing body must be preserved across ingests, so pre-rendering the trail with all historical entries is infeasible without a broader refactor.
  (fix: `_update_existing_page` RMW could buffer existing trail bytes in memory, append the new entry, write both body and trail under a single lock — requires the cycle-19 `file_lock` discipline.)

- CLI ↔ MCP parity — `cli.py` exposes 24 commands; MCP exposes 28 tools. Remaining gap = 7 write-path tools deferred to a write-path input-validation cycle: `kb_review_page` / `kb_refine_page` / `kb_query_feedback` / `kb_save_source` / `kb_save_lint_verdict` / `kb_create_page` / `kb_capture`. Structured `--format=json` output across both surfaces also still open. (R2)
  (fix: auto-generate CLI subcommands from the FastMCP tool registry; or collapse MCP + CLI onto a shared `kb.api` service module)

- `compile/compiler.py` `compile_wiki` (~279-393) — a 50-line `for source in changed: ingest_source(source)` loop + manifest save. CLAUDE.md describes compile as "LLM builds/updates interlinked wiki pages, proposes diffs, not full rewrites" — no second pass, no cross-source reconciliation, no diff proposal exists in code. (R2)
  (fix: make `compile_wiki` a real two-phase pipeline (collect extractions → reconcile cross-source → write); or rename to `batch_ingest` and stop pretending compile is distinct)

- `tests/` snapshot tests — cycle 64 shipped foundation: `syrupy>=4.6.0` dev dep + 3 snapshot subjects (evidence-trail / Mermaid export / lint-report-structure). Remaining subjects deferred to cycle-65+: `_build_summary_content` page-rendering, `kb publish --format graph` JSON-LD output, `auto_publish_after_compile`'s `_publish/llms-full.txt` body, contradictions append, `build_extraction_prompt`, `_render_sources`. (R3)
  (fix: add the deferred subjects incrementally; commit `tests/__snapshots__/` for each.)

- `tests/` N=40 FastMCP-realistic dim-mismatch concurrency stress (cycle-65+) — cycle 64 AC8's `test_concurrent_query_during_rebuild_idempotent` exercises N=4 threads and proves idempotency via embeddings.py:302+307 double-checked locking. N=40 deferred per R2-F6 (test-harness infrastructure complexity without proportional cycle-64 win).

- `requirements.txt` resolver conflicts (cycle-34 AC52 follow-up) — `pip check` reports three known conflicts that CI accepts via `continue-on-error: true`: (a) `arxiv 2.4.1` requires `requests~=2.32.0` but installed `requests==2.33.0`; (b) `crawl4ai 0.8.6` requires `lxml~=5.3` but installed `lxml==6.1.0`; (c) `instructor 1.15.1` requires `rich<15.0.0,>=13.7.0` but installed `rich==15.0.0`. Each has a known runtime workaround (none of `arxiv`/`crawl4ai`/`instructor` is imported by `src/kb/`). When upstream packages relax these constraints, drop the `continue-on-error: true` directive.

- `ingest/pipeline.py` real PDF text extraction (cycle-N+1 if requested) — cycle 34 AC24 removed `.pdf` from `SUPPORTED_SOURCE_EXTENSIONS`; user-facing message points at `markitdown` / `docling` for conversion. If in-process extraction is requested: integrate `pypdf` or `pdfplumber` as a `[pdf]` extra with size + page caps; or add a `kb convert <pdf>` CLI subcommand wrapping markitdown.

- `kb.query.hybrid` `KB_DISABLE_VECTORS=1` runtime kill-switch (cycle-N+1 if requested) — cycle 34 AC19 documented hybrid as opt-in via the `[hybrid]` extra. Add a runtime env var to disable hybrid search WITHOUT uninstalling the extras (per-environment toggle).

- `tests/` windows-latest CI matrix re-enable (cycle-53+) — local Windows full suite passes. GHA `windows-latest` runner hangs at `threading.py:355` after cycle-23 multiprocessing test was skipif'd (cycle 36 AC2). Top-3 candidate culprits (grep-ranked by Thread/multiprocessing usage): (1) `tests/test_cycle25_dim_mismatch.py:180-184` N-thread parallel sqlite write; (2) `tests/test_cycle23_rebuild_indexes.py:213-248` long-lock holder; (3) `tests/test_cycle24_lock_backoff.py:222-228` exponential-backoff thread. Cycle-53+ should reproduce on a self-hosted Windows runner, fix or skipif the culprit, then re-enable matrix `[ubuntu-latest, windows-latest]` with `strategy.fail-fast: false`.

- `tests/` GHA-Windows multiprocessing spawn investigation (cycle-53+) — cycle 23's `test_cross_process_file_lock_timeout_then_recovery` hangs on GHA `windows-latest` at `popen_spawn_win32.py:112` (parent's `child.start()` blocks waiting on the spawn-bootstrap pipe). Local Windows pass time is 1.03s. Cycle 36 AC2 skipif'd. Reproduce on a self-hosted Windows runner; instrument the child-spawn pipe; identify the divergence (likely editable-install pth resolution / `PYTHONNOUSERSITE` / `kb.config` PROJECT_ROOT heuristic in spawned child). Once fixed, narrow the skipif to `GITHUB_ACTIONS` only or remove.

- `tests/test_compile.py::test_prune_base_uses_canonical_rel_path_at_both_sites` C41-L1 behavioral upgrade (cycle-53+) — uses `inspect.getsource(compiler)` to lint that two prune sites use `_canonical_rel_path`. Cycle-52 R1 NIT proposed a positive behavioral test that stubs `_canonical_rel_path` and asserts both `compile_wiki(mode="full")` and `detect_source_drift` route through the helper.

- `tests/` versioned-file `inspect.getsource` C11-L1 batch-filing (cycle-56+) — 5 `inspect.getsource` patterns in unchanged versioned files were flagged during cycle-55 same-class peer scan but not addressed (out of scope — files not being folded). Sites: `tests/test_lint_query_fixes_v092.py:279,286`; `tests/test_v0911_phase392.py:245`; `tests/test_v0915_task01.py:320,331`; `tests/test_v0915_task08.py:363`. These are vacuous source-string-read assertions that pass even when the production code path is reverted. Upgrade: behavioral assertion exercising the production call site, OR delete if covered elsewhere, OR in-fold C11-L1 upgrade when the host file's fold cycle arrives.

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

### Design tensions to document in README (not items to implement)

- **Container boundary / atomic notes tension (WenHao Yu)** — `kb_ingest` forces a "which page does this merge into?" decision; document that our model merges aggressively and that atomic-note alternatives exist.
- **Model collapse (Shumailov 2024, Nature)** — cite in "known limitations": LLM-written pages feeding next LLM ingest degrade across generations; counter is evidence-trail provenance + two-vault promotion gate.
- **Enterprise ceiling (Epsilla)** — document explicit scope: personal-scale research KB, not multi-user enterprise; no RBAC, no compliance audit log, file-I/O limits at millions-of-docs scale.
- **Vibe-thinking critique (HN)** — *"Deep writing means coming up with things through the process of producing"*; defend with mandatory human-review gates on promotion.

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
