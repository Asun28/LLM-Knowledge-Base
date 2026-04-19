# Cycle 12 — Design Gate (Step 5)

**Date:** 2026-04-19
**Gate:** Opus 4.7 (1M context) — feature-dev Step 5
**Inputs reviewed:** requirements (2026-04-19-cycle12-requirements.md), threat model (2026-04-19-cycle12-threat-model.md), brainstorm (2026-04-19-cycle12-brainstorm.md), CLAUDE.md principles, plus live source-file grep of `pages.py`, `lint/checks.py`, `lint/augment.py`, `mcp/core.py`, `mcp_server.py`, `mcp/__init__.py`, `config.py`, `capture.py`, and `tests/test_v070.py`.
**Prior verdicts:** Opus R1 PASS-WITH-NOTES, Codex R2 PASS-WITH-CHANGES. Neither rejected.

## VERDICT

**PROCEED TO STEP 7 (PLAN).** 16 open questions resolved below. No escalations — every question is reversible (doc/test/library-only change) or already covered by a project principle. All four R1 action items plus seven R2 action items are integrated into the FINAL DECIDED DESIGN.

## DECISIONS (summary)

| Q | Topic | Decision | Confidence |
|---|-------|----------|------------|
| Q1 | AC11 scope | **STRICT-4** (lint/checks.py only; cycle-13 BACKLOG for other 8 sites) | HIGH |
| Q2 | AC7 back-compat | **KEEP-BOTH** `main` + `mcp` re-exports in `mcp_server.py` | HIGH |
| Q3 | AC1 fixture scope | **OPT-IN** (not autouse) | HIGH |
| Q4 | AC14 branches | **BOTH-BRANCHES** (parameterise on `use_api`) | HIGH |
| Q5 | AC15 sweep | **GREP-VERIFIED-MAP** (12 AC→BACKLOG pairs only) | HIGH |
| Q6 | AC1 filter | **EXPLICIT + DERIVED-STATE** (23 constants + 4 derived) | HIGH |
| Q7 | AC2 caller | **LIBRARY-ONLY** (cycle-13 wiring BACKLOG) | HIGH |
| Q8 | AC6 marker | **PYPROJECT-MATCH, WIKI-LOG** (pyproject alone matches; wiki-absent logged) | MED-HIGH |
| Q9 | AC6 depth | **KEEP-5** levels | HIGH |
| Q10 | AC11 parse-error | **RE-RAISE** (preserves caller `except` semantics) | HIGH |
| Q11 | AC8 cache size | **8192** (not 2048) | MED-HIGH |
| Q12 | AC13 raw_dir | **TEST-SUPPLIES-BOTH, PRODUCT-CHANGE-DEFERRED** | HIGH |
| Q13 | AC12 precondition | **TWO-PHASE** (propose then execute) | HIGH |
| Q14 | AC14 role-tags | **DROP-FROM-AC** (sentinel is bounding defense) | HIGH |
| Q15 | AC1 derived state | **ALLOWLIST + DERIVED** (4 derived caches patched) | HIGH |
| Q16 | AC9 site name | **FIX-AC9-TEXT** to name `load_all_pages` (not `scan_wiki_pages`) | HIGH |

Full analytical `## Analysis` blocks per question were produced in the gate subagent's output and summarised here. Key verbatim decision text is carried into the CONDITIONS and FINAL DECIDED DESIGN sections below.

## CONDITIONS (must be true before Step 7 starts)

1. **AC8 helper contract** follows Q10: re-raises parse errors; caller `except` tuples unchanged.
2. **AC8 cache size** raised to 8192 per Q11.
3. **AC1 allowlist** uses explicit 23-constant enumeration per Q6; derived-state patches for `_CAPTURES_DIR_RESOLVED`, `_captures_resolved`, `_project_resolved`, `SOURCE_TYPE_DIRS` are MANDATORY.
4. **AC7 shim** preserves BOTH `main` and `mcp` re-exports per Q2 — `tests/test_v070.py:400` must keep passing.
5. **AC9 text** corrected to name `load_all_pages` (not `scan_wiki_pages`) per Q16.
6. **AC11 scope** stays at 4 sites; cycle-13 BACKLOG entry covers remaining 8 sites per Q1.
7. **AC12 test** uses two-phase (`--augment` propose then `--execute`) per Q13.
8. **AC13 test** passes both `wiki_dir=` AND `raw_dir=` explicitly per Q12; does NOT monkeypatch `MANIFEST_DIR`/`RATE_PATH`.
9. **AC14 test** drops role-tag assertion per Q14; asserts only fence-strip + control-strip + sentinel wrap, parameterised on `use_api`.
10. **AC15 deletions** frozen to the 12 grep-verified mappings per Q5.
11. **AC6 walk-up** matches on `pyproject.toml` alone (Q8-refined), logs `INFO` on detection (noting wiki presence/absence).
12. **Threat-model integrated actions** carried into FINAL AC text: `Path.resolve() + .is_dir()` on `KB_PROJECT_ROOT`, non-recursive `glob("*.tmp")`, mtime_ns coarse-filesystem caveat, CHANGELOG Security section.

Three new BACKLOG entries to be drafted in Step 9 alongside AC15 deletions:

- "Phase 4.5 MEDIUM — migrate remaining 8 `frontmatter.load` sites (augment×5, semantic×1, graph-export×1, review-context×1) to `load_page_frontmatter`. Target cycle 13." (Q1)
- "Phase 4.5 LOW — wire `sweep_orphan_tmp` into CLI boot or ingest-tail. Target cycle 13." (Q7)
- "Phase 5 LOW — plumb `run_augment` `raw_dir` default from `wiki_dir.parent / 'raw'` to match `effective_data_dir` derivation. Target cycle 13." (Q12)

## FINAL DECIDED DESIGN (updated AC text)

### File 1 — `tests/conftest.py`

- **AC1.** Add `tmp_kb_env(tmp_path, monkeypatch)` **opt-in (non-autouse)** fixture that creates a `tmp_project`-shaped sandbox AND monkeypatches the following 23 `kb.config` constants to the sandbox: `PROJECT_ROOT`, `RAW_DIR`, `WIKI_DIR`, `CAPTURES_DIR`, `OUTPUTS_DIR`, `VERDICTS_PATH`, `FEEDBACK_PATH`, `REVIEW_HISTORY_PATH`, `WIKI_ENTITIES`/`WIKI_CONCEPTS`/`WIKI_COMPARISONS`/`WIKI_SUMMARIES`/`WIKI_SYNTHESIS`, `RAW_ARTICLES`/`RAW_PAPERS`/`RAW_REPOS`/`RAW_VIDEOS`/`RAW_PODCASTS`/`RAW_BOOKS`/`RAW_DATASETS`/`RAW_CONVERSATIONS`/`RAW_ASSETS` — AND mirrors the override into every already-imported consumer in `sys.modules` that re-binds those names via `from kb.config import X`. **Additionally patches derived state:** `kb.capture._CAPTURES_DIR_RESOLVED`, `kb.capture._captures_resolved`, `kb.capture._project_resolved` (all reassigned to tmp-rooted `.resolve()` values), and rebuilds `kb.config.SOURCE_TYPE_DIRS` as `{k: tmp_raw / orig_v.name for k, orig_v in original.items()}`. Fixture docstring lists every patched name + states "if you add a new config constant or derived cache, add it here too". *(behavioural test — new `tests/test_cycle12_conftest.py`; deliberate-leak test proves allowlist completeness.)*

### File 2 — `src/kb/utils/io.py`

- **AC2.** Add `sweep_orphan_tmp(directory: Path, *, max_age_seconds: float = 3600.0) -> int` that unlinks `*.tmp` files in `directory` older than `max_age_seconds`. Contract: (a) `directory` is `Path.resolve()`'d before scan; (b) uses `directory.glob("*.tmp")` **non-recursively**; (c) age check uses `time.time() - path.stat().st_mtime`; (d) unlink failures log `WARNING` with path + errno; (e) never raises past the boundary; (f) returns `int` count of removed files. **No default caller wired this cycle** — helper ships with regression tests only; BACKLOG entry tracks cycle-13 wiring. *(behavioural test — new `tests/test_cycle12_io_sweep.py`.)*

- **AC3.** Extend `file_lock`'s module docstring with a caveat block documenting the Windows PID-recycling limitation and stating cross-process correctness depends on 5 s timeout + lock-file content integrity, not PID liveness. Doc-only. *(doc sanity subtest.)*

- **AC4.** Extend `atomic_json_write`/`atomic_text_write` docstrings with a network-mount caveat: "on offline OneDrive/SMB mounts, `replace` may time out; `sweep_orphan_tmp` cleans residual `.tmp` siblings". Doc-only. *(doc sanity subtest.)*

### File 3 — `src/kb/config.py`

- **AC5.** `PROJECT_ROOT` resolution honours `KB_PROJECT_ROOT` env var when set — `Path(os.environ["KB_PROJECT_ROOT"]).resolve()`, additionally validated by `.is_dir()`. Invalid path (non-existent OR not a directory) falls back to the heuristic (then walk-up per AC6) and logs `WARNING` with the attempted path. *(behavioural test — new `tests/test_cycle12_config_project_root.py`.)*

- **AC6.** When `KB_PROJECT_ROOT` is unset AND the 3-level-up heuristic points at a directory that lacks `pyproject.toml`, walk up from `Path.cwd()` looking for a directory containing `pyproject.toml`, **bounded to 5 levels**. On match: PROJECT_ROOT = that directory; log `INFO` with detected path AND whether `wiki/` exists (library-mode vs. checkout-mode debuggability). If no match found within 5 levels, fall back to the heuristic. *(shares `tests/test_cycle12_config_project_root.py`.)*

### File 4 — `src/kb/mcp/__init__.py` + `src/kb/mcp_server.py` + `pyproject.toml`

- **AC7.** Add `main()` function to `kb.mcp` package (wrapping existing `mcp.run()` logic). Keep `kb/mcp_server.py` as a back-compat shim that re-exports **BOTH** `main` AND `mcp` (preserves `tests/test_v070.py:400`). Add `project.scripts` entry `kb-mcp = "kb.mcp:main"` alongside existing `kb = "kb.cli:cli"`. `python -m kb.mcp_server` continues to work. No double tool registration. *(behavioural subprocess test — new `tests/test_cycle12_mcp_console_script.py` invokes `kb-mcp --help` via `subprocess.run` and asserts exit 0.)*

### File 5 — `src/kb/utils/pages.py`

- **AC8.** Add `load_page_frontmatter(page_path: Path) -> tuple[dict, str]` returning `(metadata, body)` with `@functools.lru_cache(maxsize=8192)` keyed on `(str(page_path), page_path.stat().st_mtime_ns)`. **Re-raises parse errors** (`OSError`, `ValueError`, `AttributeError`, `yaml.YAMLError`, `UnicodeDecodeError`) to the caller — callers `except` the same exception types they do today; the cache stores only successful parses. Docstring notes: "mtime_ns resolution depends on filesystem (FAT32/SMB may be coarser → short cache-key collision window if two edits land in the same second — acceptable because lint/query re-runs start with fresh cache). maxsize=8192 covers wikis up to ~8k pages; larger wikis see partial eviction." Includes `cache_clear()` escape hatch for tests. *(behavioural test — new `tests/test_cycle12_frontmatter_cache.py`: call-count pin, parse-error re-raise, mtime-bump invalidation.)*

- **AC9.** Migrate the single `frontmatter.load(str(page_path))` call in `utils/pages.py::load_all_pages` (line 108, NOT `scan_wiki_pages`) to `load_page_frontmatter`. Existing `except` block at lines 125-135 keeps identical error-tolerance semantics. *(shares `tests/test_cycle12_frontmatter_cache.py`.)*

### File 6 — `src/kb/graph/builder.py`

- **AC10.** Extend the `page_id`/`scan_wiki_pages` re-export docstring with an explicit case-sensitivity caveat: "IDs are lowercased. Consumers reconstructing `wiki_dir / f'{pid}.md'` on case-sensitive filesystems MUST use the page's stored `path` field instead — the original filesystem case is preserved on `path` but lost on `id`." Doc-only. *(doc sanity subtest.)*

### File 7 — `src/kb/lint/checks.py`

- **AC11.** Migrate the 4 `frontmatter.load(str(page_path))` sites at lines 317, 398, 454, 601 to `load_page_frontmatter(page_path)`. Each call site retains its existing `try/except` clause with identical exception tuple. **SCOPE IS STRICT-4**: do NOT migrate the 8 remaining sites in `lint/augment.py`/`lint/semantic.py`/`graph/export.py`/`review/context.py` this cycle. *(shares `tests/test_cycle12_frontmatter_cache.py`: call-count pin asserts `frontmatter.load` called ≤ N times over a batch lint run.)*

### File 8 — `tests/test_v5_lint_augment_cli.py`

- **AC12.** Add a public-surface test that invokes `kb lint --augment --wiki-dir <tmp>/wiki` (propose mode) then `kb lint --augment --execute --wiki-dir <tmp>/wiki` (execute mode) via `CliRunner` — **two-phase sequence** required because execute mode short-circuits on missing proposals file. Fixture: `tmp/wiki` contains ONE stub page that triggers exactly one proposal. Assertions: (a) raw gap-fill artefact written under `<tmp>/raw`, (b) manifest JSON at `<tmp>/.data/augment/*.json`, (c) ZERO writes to real `PROJECT_ROOT/raw` AND `PROJECT_ROOT/.data` (assert via pre/post `iterdir()` snapshot diff). *(behavioural test.)*

### File 9 — `tests/test_v5_lint_augment_orchestrator.py`

- **AC13.** Add a default-path regression test that runs `run_augment` with `wiki_dir=tmp_project/"wiki"` AND `raw_dir=tmp_project/"raw"` (both explicit) and **NO** `monkeypatch.setattr` on `MANIFEST_DIR` / `RATE_PATH`. Asserts: (a) manifest under `tmp_project/.data/augment/`, (b) rate-limit state under `tmp_project/.data/`, (c) raw files under `tmp_project/raw/`, (d) ZERO writes to real `PROJECT_ROOT`. The raw_dir-from-wiki_dir derivation is deferred to cycle 13 (BACKLOG entry). *(behavioural test.)*

### File 10 — new `tests/test_cycle12_*.py` regression files

- **AC14.** `tests/test_cycle12_sanitize_context.py` — behavioural regression test that `kb_query(conversation_context=...)` strips control chars + `<prior_turn>` fence variants (ASCII, fullwidth, case-insensitive) AND wraps the forwarded text in `<prior_turn>…</prior_turn>` sentinel. **Parameterised on `use_api={False, True}`** — asserts sanitization runs before BOTH branches reach their respective LLM. Hostile payload: `\x00\x1f`, embedded `</prior_turn>`, fullwidth `＜prior_turn＞`, BIDI marks. **Does NOT assert role-tag tokens are removed** — the sentinel wrap is the bounding defense (cycle-4 threat-model decision). Test FAILS if sanitizer removed or moved into only one branch.

### File 11 — `BACKLOG.md`

- **AC15.** Delete stale entries matching the 12 grep-verified cycle-12 AC→BACKLOG mappings: (i) Phase 4.5 LOW `mcp/core.py conversation_context` sanitizer (shipped cycle 4, tested cycle 12 via AC14); (ii) Phase 4.5 MEDIUM R3 conftest `_setup_*` helpers (closed by AC1); (iii) Phase 4.5 LOW R4 orphan-temp cleanup (closed by AC2); (iv) Phase 4.5 MEDIUM R2 PID-liveness (closed by AC3 doc); (v) Phase 4.5 LOW R4 network-mount docs (closed by AC4); (vi) Phase 4.5 LOW R4 `KB_PROJECT_ROOT` env override (closed by AC5); (vii) Phase 4.5 LOW R4 walk-up fallback (closed by AC6); (viii) Phase 4.5 LOW R3 3-layer MCP boot (closed by AC7); (ix) Phase 4.5 MEDIUM R1 frontmatter hot-path — PARTIAL (only 4 sites closed; add narrower cycle-13 entry for remaining 8); (x) Phase 4.5 MEDIUM R2 `page_id` lowercasing doc (closed by AC10); (xi) Phase 5 three-round LOW R3 #1 augment CLI coverage (closed by AC12); (xii) Phase 5 three-round LOW R3 #2 orchestrator default-path (closed by AC13). **Hard deletes only — no strikethrough.** ADD three new cycle-13 entries per CONDITIONS.

### File 12 — `CHANGELOG.md`

- **AC16.** Append `Phase 4.5 — Backlog-by-file cycle 12 (2026-04-19)` entry under `[Unreleased]` with Added / Changed / Fixed / **Security** sections. Security section MUST record the `KB_PROJECT_ROOT` env-var trust assumption ("OS-level environment is trusted; a hostile `KB_PROJECT_ROOT` pointing at a controlled directory could redirect file I/O — acceptable in single-user CLI context, documented for awareness"). Update the Quick Reference table with a cycle-12 row matching the final `pytest --collect-only` count.

### File 13 — `CLAUDE.md`

- **AC17 (docs only).** Update the "Testing" section's test-count reference to point at `CHANGELOG.md` (no numeric edits per convention). Add one line under "Five Operations Cycle" or "Development Commands" documenting `KB_PROJECT_ROOT` env var + the walk-up fallback.

## Integrated action items traceability

**R1 (Opus, threat-model) → AC text:**
- AC5 `Path.resolve()` + `.is_dir()` ✅
- AC2 non-recursive `glob("*.tmp")` + `resolve()` ✅
- AC8 mtime_ns coarse-filesystem docstring ✅
- AC16 CHANGELOG Security section ✅

**R2 (Codex, edge-cases) → decisions:**
- Q10 helper re-raises parse errors ✅
- Q11 LRU `maxsize=8192` ✅
- Q12 AC13 test supplies both dirs explicitly; product change deferred ✅
- Q13 AC12 two-phase propose→execute ✅
- Q14 AC14 drops role-tag assertion ✅
- Q15 fixture patches 4 derived caches ✅
- Q16 AC9 names `load_all_pages` ✅

## Step 7 (plan) handoff

- 13 files touched (blast-radius manifest unchanged).
- ~9 logical commit clusters per brainstorm Approach B.
- Ordering: conftest fixture → `utils/io.py` → `config.py` → `utils/pages.py` (AC8+AC9 atomic) → `graph/builder.py` doc → `lint/checks.py` (4-site migration) → MCP shim cluster (3 files atomic) → regression tests → BACKLOG+CHANGELOG+CLAUDE.md docs.
- No new dependencies, no schema changes, no signature breaks.
- Tests baseline 2089 → target ~2109 (+5-6 cycle-12 tests with ~20 assertions).

**Proceed to Step 7 (plan).**
