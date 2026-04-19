# Cycle 12 — Requirements + Acceptance Criteria

**Date:** 2026-04-19
**Base:** `main` @ `a5416b3` (cycle 11 complete)
**Baseline tests:** 2089 collected (cycle 11 ended 2081 passed + 7 skipped)

## Problem

The BACKLOG still contains stale entries (closed by earlier cycles but never deleted) plus a cluster of medium-effort correctness / observability / housekeeping items that share a theme: **make the library friendlier to out-of-tree callers** (custom `wiki_dir`, custom `raw_dir`, package installed outside `-e` checkouts, subprocess callers, cached filesystem reads) without shipping any large refactor.

Cycle 12 groups these by file per `feedback_batch_by_file`, delivers behavioural tests with every change, and sweeps the BACKLOG of entries whose source-level fixes already shipped in cycles 4, 8, 10, and 11.

## Non-goals

- No HIGH-severity architectural refactor (e.g. `kb.errors` error hierarchy, full `compile_wiki` two-phase split, per-page write locks, receipt files, cross-process MPP). Those need their own design cycles.
- No new MCP tools.
- No dependency bumps beyond `requirements.txt` CVE patching in Step 11.5 (if any exist).
- No changes to `wiki/` content or `raw/` files.

## Acceptance Criteria

Each AC is individually testable as pass/fail. ACs are grouped **by file** (`feedback_batch_by_file`), not by severity. Test type is noted in parentheses.

### File 1 — `tests/conftest.py`

- **AC1.** Add `tmp_kb_env(tmp_path, monkeypatch)` fixture that creates a `tmp_project`-shaped sandbox AND monkeypatches every `kb.config.WIKI_*` / `kb.config.RAW_*` / `kb.config.PROJECT_ROOT` / `kb.config.CAPTURES_DIR` / `kb.config.OUTPUTS_DIR` / `kb.config.HASH_MANIFEST` / `kb.config.VERDICTS_PATH` / `kb.config.FEEDBACK_PATH` / `kb.config.REVIEW_HISTORY_PATH` constant to the sandbox AND mirrors the override into every already-imported consumer in `sys.modules` that re-binds those names via `from kb.config import X`. Closes `Phase 4.5 LOW ad-hoc `_setup_*` helper duplication`. *(behavioural test — AC17)*

### File 2 — `src/kb/utils/io.py`

- **AC2.** Add `sweep_orphan_tmp(directory: Path, *, max_age_seconds: float = 3600.0) -> int` that unlinks `*.tmp` files in `directory` older than `max_age_seconds`. Returns count of removed files. Never raises; logs unlink failures at WARNING. Closes `Phase 4.5 LOW R4 network-mount orphan-temp cleanup`. *(behavioural test — AC18)*
- **AC3.** Extend `file_lock`'s module docstring with an explicit caveat block documenting the Windows PID-recycling limitation and stating that cross-process correctness currently depends on the 5 s timeout + lock-file content integrity check, not on PID liveness. No code change. Closes `Phase 4.5 MEDIUM R2 PID-liveness docstring`. *(doc sanity test — AC17 subtest).*
- **AC4.** Extend `atomic_json_write`/`atomic_text_write` docstrings with a network-mount caveat ("on offline OneDrive/SMB mounts, `replace` may time out; `sweep_orphan_tmp` cleans residual `.tmp` siblings"). Closes `Phase 4.5 LOW R4 network-mount docs`. *(doc sanity test — AC17 subtest).*

### File 3 — `src/kb/config.py`

- **AC5.** `PROJECT_ROOT` resolution honours `KB_PROJECT_ROOT` env var when set — `Path(os.environ["KB_PROJECT_ROOT"]).resolve()`. Invalid path (non-existent directory) falls back to the existing 3-level-up heuristic and logs a WARNING. Closes `Phase 4.5 LOW R4 KB_PROJECT_ROOT env override`. *(behavioural test — AC19)*
- **AC6.** When `KB_PROJECT_ROOT` is unset AND the heuristic points at a directory that lacks both `pyproject.toml` and `wiki/` (the pip-install-without-checkout failure mode), walk up from `Path.cwd()` looking for a directory containing `pyproject.toml`, bounded to 5 levels. Falls back to the heuristic if no match. Closes `Phase 4.5 LOW R4 walk-up fallback`. *(behavioural test — AC19).*

### File 4 — `src/kb/mcp/__init__.py` + `src/kb/mcp_server.py` + `pyproject.toml`

- **AC7.** Add `main()` function to `kb.mcp` package (wrapping the existing `mcp.run()`); keep `kb/mcp_server.py` as a 3-line back-compat shim that re-exports `main`; add a second `project.scripts` entry `kb-mcp = "kb.mcp:main"` so users can skip the `kb mcp` → `cli.mcp()` → `mcp_server.main` chain. Closes `Phase 4.5 LOW R3 3-layer MCP boot`. *(behavioural subprocess test — AC20)*

### File 5 — `src/kb/utils/pages.py`

- **AC8.** Add `load_page_frontmatter(page_path: Path) -> tuple[dict, str]` returning `(metadata, body)` with an `@lru_cache(maxsize=2048)` keyed on `(str(page_path), page_path.stat().st_mtime_ns)`. Falls back to `(dict, "")` on parse errors (same contract as existing `scan_wiki_pages` error-tolerance). Closes `Phase 4.5 MEDIUM R1 frontmatter.load hot-path`. *(behavioural test — AC21)*
- **AC9.** Migrate the single `frontmatter.load(str(page_path))` call in `utils/pages.py::scan_wiki_pages` (line 108) to `load_page_frontmatter`. *(regression test — AC21).*

### File 6 — `src/kb/graph/builder.py`

- **AC10.** Extend the `page_id`/`scan_wiki_pages` re-export docstring with an explicit case-sensitivity caveat: "IDs are lowercased; consumers that reconstruct `wiki_dir / f"{pid}.md"` on case-sensitive filesystems must use the page's stored `path` field instead." No code change. Closes `Phase 4.5 MEDIUM R2 page_id lowercasing doc`. *(doc sanity test — AC21 subtest).*

### File 7 — `src/kb/lint/checks.py`

- **AC11.** Migrate the 4 `frontmatter.load(str(page_path))` sites at lines 317, 398, 454, 601 to `load_page_frontmatter(page_path)`. Each call site must still handle parse-error fallthrough. Closes `Phase 4.5 MEDIUM R1 frontmatter hot-path (primary 4 sites)`. *(regression test — AC22 behavioural call-count pin).*

### File 8 — `tests/test_v5_lint_augment_cli.py`

- **AC12.** Add a public-surface test that invokes `kb lint --augment --execute --wiki-dir <tmp>/wiki` via `CliRunner` and asserts: (a) raw gap-fill artefacts written under `<tmp>/raw`, (b) manifest JSON at `<tmp>/.data/augment/*.json`, (c) zero writes to the real `PROJECT_ROOT`. Closes `Phase 5 three-round LOW R3 #1`. *(behavioural test)*

### File 9 — `tests/test_v5_lint_augment_orchestrator.py`

- **AC13.** Add a default-path regression test that runs `run_augment` with `wiki_dir=tmp_project/"wiki"` and NO `monkeypatch.setattr` on `MANIFEST_DIR` / `RATE_PATH`, asserting all writes land under `tmp_project`. Closes `Phase 5 three-round LOW R3 #2`. *(behavioural test)*

### File 10 — new `tests/test_cycle12_*.py` regression files

- **AC14.** `tests/test_cycle12_sanitize_context.py` — behavioural regression test that `kb_query(conversation_context=...)` strips control chars + role-tag patterns AND wraps the forwarded text in `<prior_turn>…</prior_turn>` sentinel. Pins cycle-4 behaviour so future refactors can't silently regress. Closes deferred test coverage for the already-shipped `Phase 4.5 LOW mcp/core.py conversation_context`.

### File 11 — `BACKLOG.md`

- **AC15.** Delete stale entries that already shipped: (i) Phase 4.5 LOW `mcp/core.py` `conversation_context` control-char strip + `<prior_turn>` sentinel (shipped cycle 4). Delete every cycle-12-resolved item after tests pass. No strikethrough — always hard delete.

### File 12 — `CHANGELOG.md`

- **AC16.** Append `Phase 4.5 — Backlog-by-file cycle 12 (2026-04-19)` entry under `[Unreleased]` with Added / Changed / Fixed / Security sections and update the Quick Reference table with a new row for cycle 12.

### File 13 — `CLAUDE.md`

- **AC17 (docs only).** Update the "Testing" section's test count reference to point at `CHANGELOG.md` as source of truth (no numeric edits per convention); add one line under "Five Operations Cycle" describing the new `KB_PROJECT_ROOT` env var.

## Blast Radius

Touched modules (all confirmed by grep):

- `src/kb/config.py` — env-var + walk-up fallback
- `src/kb/utils/io.py` — orphan-temp sweep helper + docstrings (no lock semantics change)
- `src/kb/utils/pages.py` — `load_page_frontmatter` helper + migration of local call site
- `src/kb/graph/builder.py` — docstring addition on re-export
- `src/kb/lint/checks.py` — 4 frontmatter.load migrations
- `src/kb/mcp/__init__.py` — add `main()` function
- `src/kb/mcp_server.py` — shim re-export
- `pyproject.toml` — add `kb-mcp` script
- `tests/conftest.py` — `tmp_kb_env` fixture
- `tests/test_v5_lint_augment_cli.py` — new CLI public-surface test
- `tests/test_v5_lint_augment_orchestrator.py` — new default-path test
- `tests/test_cycle12_sanitize_context.py` — NEW
- `tests/test_cycle12_conftest.py` — NEW (covers AC17 fixture behaviour)
- `tests/test_cycle12_io_sweep.py` — NEW (covers AC18)
- `tests/test_cycle12_config_project_root.py` — NEW (covers AC19)
- `tests/test_cycle12_mcp_console_script.py` — NEW (covers AC20)
- `tests/test_cycle12_frontmatter_cache.py` — NEW (covers AC21 + regression for AC22 count)
- `BACKLOG.md` / `CHANGELOG.md` / `CLAUDE.md` — doc updates

**Module import surface unchanged.** No public function signatures modified (only additions and docstring appends). No constant renames. No manifest / verdict / feedback schema changes.

## Mapping to BACKLOG.md sections

| AC | BACKLOG origin |
|----|----------------|
| AC1 | Phase 4.5 MEDIUM R3 `tests/` ad-hoc `_setup_*` helpers |
| AC2 | Phase 4.5 LOW R4 `utils/io.py` orphan-temp cleanup |
| AC3 | Phase 4.5 MEDIUM R2 `utils/io.py` PID-liveness |
| AC4 | Phase 4.5 LOW R4 `utils/io.py` network-mount docs |
| AC5 | Phase 4.5 LOW R4 `config.py` PROJECT_ROOT env override |
| AC6 | Phase 4.5 LOW R4 `config.py` PROJECT_ROOT walk-up fallback |
| AC7 | Phase 4.5 LOW R3 `mcp_server.py` 3-layer boot |
| AC8 | Phase 4.5 MEDIUM R1 `lint/*.py` + `graph/export.py` frontmatter.load hot-path (shared helper) |
| AC9 | same, utils/pages.py migration |
| AC10 | Phase 4.5 MEDIUM R2 `graph/builder.py` page_id lowercasing (doc) |
| AC11 | same, lint/checks.py migration (4 sites) |
| AC12 | Phase 5 three-round LOW R3 #1 CLI/MCP augment coverage |
| AC13 | Phase 5 three-round LOW R3 #2 orchestrator default-path |
| AC14 | deferred test pin for cycle-4 conversation_context sanitizer |
| AC15 | BACKLOG.md hygiene — delete stale items |
| AC16 | CHANGELOG.md cycle-12 entry |
| AC17 | CLAUDE.md minor refresh |
