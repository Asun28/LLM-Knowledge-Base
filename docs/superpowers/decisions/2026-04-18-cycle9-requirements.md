# Cycle 9 Requirements — backlog-by-file (2026-04-18)

## Problem

Cycle 8 shipped 30 AC but left a specific class of bugs unresolved: **custom `wiki_dir` isolation is still leaky** (query engine vector path, stale-flag root, health feedback paths all fall back to `PROJECT_ROOT`); several capture-module items (rate-limit doc scope, infinite slug retry loop, narrow exception in normalizer, naming inconsistency) are trivial to fix but remain open; and a few MCP-boundary guards (oversized `kb_ingest` sources, `kb_read_page` case-insensitive ambiguity, `kb_compile_scan` wiki_dir plumbing) are missing. Also one load-bearing cross-cutting fix: the eager `ingest_source` re-export in `src/kb/ingest/__init__.py` defeats the cycle 8 AC30 `kb --version` fast-path pattern — must be converted to PEP 562 lazy `__getattr__` per cycle 8 Red Flag.

This cycle groups fixes by file for commit-graph cleanliness (user's `feedback_batch_by_file` rule).

## Non-goals

- No structural refactors (compiler rename, config god-module split, CLI↔MCP parity, state-store fan-out lock). These remain in BACKLOG.
- No new features from Phase 5 Karpathy re-evaluation (llms.txt, kb_merge, belief_state, etc.).
- No re-architecture of `ingest_source`'s 11 stages or `compile_wiki`'s two-phase contract.
- No changes to wiki page layout or extraction prompts.

## Acceptance Criteria (31 AC across 16 files)

### File 1 — `src/kb/query/engine.py` (4 AC)

- **AC1**: `search_pages` (line 131) computes `vec_path` via `kb.query.embeddings._vec_db_path(effective_wiki_dir)` instead of `PROJECT_ROOT / VECTOR_INDEX_PATH_SUFFIX`. Verified test: custom `wiki_dir` with its own `.data/vector_index.db` is used; repo-default DB is NOT read when override present.
- **AC2**: `_flag_stale_results` receives `project_root=wiki_dir.parent` (or `PROJECT_ROOT` when `wiki_dir is None`) threaded from `search_pages`. Verified test: stale marking uses temp `raw/` mtime, not repo-root `raw/`, under custom wiki_dir.
- **AC3**: `kb_query` (~line 756) `_hybrid_configured` branch computes `_vec_path` via `_vec_db_path(WIKI_DIR)` — same source of truth as AC1. Classification stays correct when operator swaps wiki_dir mid-session.
- **AC28**: `search_raw_sources` threads `project_root` from `wiki_dir.parent` so raw-fallback searches the override's `raw/`, not `PROJECT_ROOT / "raw"`. Verified test: temp project's raw content reaches fallback; production raw does not.

### File 2 — `src/kb/mcp/health.py` (2 AC)

- **AC4**: `kb_lint(wiki_dir=...)` derives `feedback_path = wiki_path.parent / ".data" / "feedback.json"` and passes `path=feedback_path` to `get_flagged_pages(path=...)`. When `wiki_dir is None`, preserve current behavior (default `FEEDBACK_PATH`). Verified test: custom wiki_dir sees only its own feedback, not production.
- **AC5**: `kb_evolve(wiki_dir=...)` derives the same feedback_path and passes it to `get_coverage_gaps(path=...)`. Verified test: coverage gaps do not leak production feedback entries.

### File 3 — `src/kb/mcp/core.py` (3 AC)

- **AC6**: `kb_compile_scan(wiki_dir: str | None = None)` adds wiki_dir plumbing mirroring cycle 6/8's pattern; param converted to `Path` and forwarded to `detect_source_drift`/`find_changed_sources`. Verified test: custom wiki_dir's manifest drives the scan.
- **AC7**: `kb_ingest` rejects source files whose content exceeds `QUERY_CONTEXT_MAX_CHARS` at the MCP boundary with a consistent `Error: source too long (... max ...)` string. Sibling tools (`kb_ingest_content`, `kb_save_source`) already enforce this; `kb_ingest` currently silently truncates with a `logger.warning`. Verified test: 200KB source returns Error, NOT a partial ingest.
- **AC8**: `kb_ingest_content` validates content size BEFORE writing to `raw/` (pre-write check). Current behavior is unclear under the cycle 1/5 consolidation; enforce at boundary with the same limit and error wording as AC7.

### File 4 — `src/kb/mcp/browse.py` (1 AC)

- **AC9**: `kb_read_page` case-insensitive fallback returns `Error: ambiguous page_id — multiple files match '<id>' case-insensitively: <matches>` when `>1` case-insensitive match exists under the same subdir. Single match: preserve current warning + success behaviour. Verified test: two files `Foo.md` + `foo.md` under `wiki/concepts/` trigger the error.

### File 5 — `src/kb/compile/compiler.py` (1 AC)

- **AC10**: `load_manifest` widens exception handler to include `OSError` alongside `json.JSONDecodeError`/`UnicodeDecodeError`, logs a warning, and returns `{}`. Mirrors cycles 3/5/7 `load_feedback` / `load_verdicts` / `load_review_history` widening. Verified test: transient `OSError` from mid-rename on Windows does not crash `compile_wiki` / `detect_source_drift`.

### File 6 — `src/kb/lint/augment.py` (1 AC)

- **AC11**: `run_augment` summary (`Saved:/Skipped:/Failed:` line, ~line 912) computes counts from the FINAL per-stub state recorded in the manifest (one stub → one outcome), not from total URL-attempt entries. A stub whose first URL failed but whose fallback succeeded counts as `Saved: 1`, not `Saved: 1, Failed: 1`. Verified test: double-URL stub with first-fail second-success reports `Failed: 0`.

### File 7 — `src/kb/lint/checks.py` (1 AC)

- **AC12**: `check_source_coverage` uses pre-parsed frontmatter from the shared corpus (e.g., `load_all_pages()` output, or a `_FRONTMATTER_RE` + `yaml.safe_load` on captured fence) instead of calling `frontmatter.loads(content)` a second time after reading the raw file. Verified test: `check_source_coverage` invoked 5000 times does not perform 5000 extra `yaml.safe_load` calls (assert via mock spy or micro-benchmark).

### File 8 — `src/kb/evolve/analyzer.py` (1 AC)

- **AC13**: `analyze_coverage`'s orphan-concept report routes bare-slug resolution through the same resolver used by `build_graph` (NOT `build_backlinks`'s skipping behavior). An entity referenced only via `[[foo]]` no longer appears as "orphan" when `build_graph` would have resolved the edge. Verified test: two concept pages where A bare-links B; `analyze_coverage` no longer reports B as orphan.

### File 9 — `src/kb/capture.py` (7 AC)

- **AC14**: `_normalize_for_scan` except clause broadened to `except Exception: continue` (with comment explaining best-effort semantics). Catches `TypeError` and any future decode-path regressions without silent aborts.
- **AC15**: `_check_rate_limit` docstring explicitly notes per-process scope (MCP server and future CLI each own independent deques, effectively doubling the allowed rate). Add a `TODO(v2)` referencing `.data/capture_rate.json` for future system-wide limit.
- **AC16**: `_build_slug` collision while-loop bounded at `max(len(existing) + 2, _SLUG_COLLISION_CEILING)` (new module-level const, default 10000). On exhaustion, raise `RuntimeError("slug collision exhausted for <kind>/<base>")` with context. Verified test: synthetic test injects 10001 colliding slugs; function raises deterministically.
- **AC17**: `_path_within_captures` renamed to `_is_path_within_captures` (verb-first for predicate parity with module's other helpers). Both call sites in `_write_item_files` updated. Verified test: existing tests still pass.
- **AC18**: `_scan_for_secrets` emits `"via base64"` or `"via URL-encoded"` label (not the generic `"via encoded form"`). Split `_normalize_for_scan` to return `(text, encoding_label)` tuples. Verified test: base64 secret payload yields `"via base64"`; URL-encoded yields `"via URL-encoded"`.
- **AC19**: `_CAPTURE_SECRET_PATTERNS` refactored from `list[tuple[str, re.Pattern]]` to `list[_SecretPattern]` where `_SecretPattern` is a module-level `NamedTuple(label: str, pattern: re.Pattern[str])`. Call sites access `.label` / `.pattern` by name.
- **AC29**: `_verify_body_is_verbatim` sets `item["body"] = body_stripped` before appending to `kept` so downstream writers receive trimmed bodies (no leading/trailing whitespace that differs from original). Verified test: round-trip preserves stripped body content.

### File 10 — `tests/test_capture.py` (3 AC)

- **AC20**: Test imports `CAPTURE_KINDS` from `kb.config` (authoritative source), not `kb.capture` (re-export). Verified test: import statement updated; no other assertion changes.
- **AC21**: Two new tests — `test_title_with_backslash_round_trips` passes `r"C:\path\to\file"` as capture title and asserts `frontmatter.loads(written_text)` recovers the same title exactly; `test_title_with_double_quote_round_trips` passes `'"quoted"'` and asserts the same. Guards against future yaml_escape re-introduction.
- **AC30**: Remove duplicate `import re as _test_re` (Ruff F811); fix comment mismatch at current `test_capture.py:120-122` to match actual expression (`'ab\r\n' * 12501 = 50004 raw bytes, 37503 post-LF bytes`).

### File 11 — `tests/conftest.py` (2 AC)

- **AC22**: `tmp_captures_dir` fixture adds `assert captures.resolve().is_relative_to(PROJECT_ROOT.resolve())` right before yielding so a future fixture change that accidentally escapes PROJECT_ROOT fails loudly.
- **AC23**: `RAW_SUBDIRS` derives from `SOURCE_TYPE_DIRS` keys dynamically (currently hardcoded to 5 of 10 subdirs). Keeps fixture in sync as new source types are added.

### File 12 — `src/kb/utils/llm.py` (1 AC)

- **AC24**: `_make_api_call` error-message handling REDACTS common secret patterns (API key prefixes `sk-ant-`, `sk-`, bearer tokens `Bearer [A-Za-z0-9_\-]+`, long hex blobs ≥32 chars, base64-ish `[A-Za-z0-9+/]{40,}`) BEFORE truncating. Pattern list co-located with existing `_LLM_ERROR_TRUNCATE_LEN`. Verified test: `APIError("...sk-ant-abc123...")` surface becomes `"...[REDACTED:ANTHROPIC_KEY]..."` in the re-raised `LLMError`.

### File 13 — `src/kb/mcp/app.py` (1 AC)

- **AC25**: FastMCP `instructions` block entries sorted alphabetically by tool name within each thematic group (Browse / Ingest / Quality / Health), eliminating the out-of-order `kb_detect_drift` / `kb_graph_viz` / `kb_verdict_trends` trailing appends. Verified test: line-by-line assert on the generated block matches a sorted snapshot.

### File 14 — `src/kb/cli.py` (1 AC)

- **AC26**: Move function-local imports (`from kb.X import Y` inside command bodies at approximately lines 32, 63, 88, 89, 107, 129, 143) to module top. CLI startup time is unaffected (Click is lazy), static dep analysis now sees all imports, smoke tests catch renames. Verified test: `python -c "import kb.cli"` must not raise; `ruff check` passes.

### File 15 — `src/kb/ingest/__init__.py` (1 AC)

- **AC27**: Convert eager `from kb.ingest.pipeline import ingest_source` re-export to PEP 562 lazy `__getattr__(name)` pattern matching cycle 8's `src/kb/__init__.py` fix for fast-path preservation. `__all__` still declares `ingest_source`; first attribute access resolves. Verified test: `python -c "import kb.ingest; assert 'kb.ingest.pipeline' not in sys.modules; ingest_source_ = kb.ingest.ingest_source; assert 'kb.ingest.pipeline' in sys.modules"` passes.

### File 16 — `.env.example` (1 AC)

- **AC31**: Change `# Required — Claude API for compile/query/lint operations` to `# Optional — Claude API. NOT needed when using Claude Code (MCP mode is the default LLM; see CLAUDE.md § MCP servers). Required ONLY for: (a) CLI \`kb compile\` / \`kb query\` without use_api=False, (b) MCP tools called with use_api=True, (c) \`kb_query --format=…\` output adapters.` The `ANTHROPIC_API_KEY=sk-ant-...` line stays as-is (user still fills it when needed). Verified test: none (documentation-only change); README parity check via doc-updater agent catches future drift. User-reported issue 2026-04-18.

## Blast radius

- **Touched modules (src/kb/)**: query/engine.py, mcp/health.py, mcp/core.py, mcp/browse.py, mcp/app.py, compile/compiler.py, lint/augment.py, lint/checks.py, evolve/analyzer.py, capture.py, utils/llm.py, cli.py, ingest/__init__.py.
- **Touched tests**: tests/test_capture.py, tests/conftest.py.
- **Touched config**: none (no CLAUDE.md/README behaviour changes — documentation updates only).
- **Zero wiki schema changes**. Zero MCP tool-list changes (additive args only on `kb_compile_scan`).
- **Existing tests**: must stay green (1949 → 1949+N after new regressions for AC1-AC23, AC28, AC29).

## Feeds

- Step 4 design eval scores each AC against blast radius + test plan.
- Step 8 plan gate verifies each AC maps to exactly one task + one failing test.
- Step 11 security verification reconciles AC against threat model (below).

## Risks

- AC1-AC3, AC28: query engine wiki_dir threading touches hot path — regression risk for existing 150+ query tests. Mitigation: run full suite before commit.
- AC16 bounded collision: may produce false-positive `RuntimeError` in rare legitimate `len(existing) > 10000` branches. Mitigation: ceiling configurable via module-level const.
- AC19 NamedTuple: may break any downstream caller reaching into tuple indices — grep confirms internal module only.
- AC25 instructions sort: breaking change if any downstream client parses the block by line order. Risk assessed as zero (block is documentation, not API).
- AC27 lazy __getattr__: CYCLE 8 LESSON — eager re-exports broke `kb --version` fast-path. Mitigation: subprocess test asserts `kb.ingest.pipeline` is NOT in `sys.modules` after `import kb.ingest` (only after attribute access).

## Definition of done

- 30 AC implemented with ≥30 new/updated failing-test-first regressions.
- Full pytest suite green (1949 → 1979+).
- `ruff check src/ tests/` + `ruff format --check` clean.
- `pip-audit -r requirements.txt` diff vs cycle 8 baseline: 0 PR-introduced CVEs.
- CHANGELOG.md `[Unreleased]` notes "Backlog-by-file cycle 9 (30 items)".
- BACKLOG.md deletes resolved items; no strikethrough.
- PR #23 opened, 2 review rounds, merge to main.
- Self-review document `docs/superpowers/decisions/2026-04-18-cycle9-self-review.md` lists executed/first-try/surprise scorecard + any new Red Flags for feature-dev skill.
