# Cycle 12 — Threat Model (Step 2 Opus)

**Date:** 2026-04-19
**Reviewer:** Opus 4.7 subagent (think-step-by-step scaffold)
**Scope:** 17 ACs across 13 files per `2026-04-19-cycle12-requirements.md`.

## Analysis

Cycle 12 is additive — no signature breaks, no schema changes, no new network surfaces beyond an already-vetted stdio entry. The realistic threat surface reduces to five items: (1) `KB_PROJECT_ROOT` env var reframing `PROJECT_ROOT` from compile-time constant to runtime value; (2) `sweep_orphan_tmp()` walking a caller-supplied directory and unlinking `.tmp` files; (3) `load_page_frontmatter()` caching parsed frontmatter keyed on mtime_ns (stale-cache on coarse-mtime filesystems); (4) `tmp_kb_env` fixture mutating `sys.modules` bindings (test-contamination risk if teardown leaks); (5) `kb-mcp` console script as a second `project.scripts` entry.

Each mitigation is either already present in the existing code (`Path.resolve()`, path-prefix validation at MCP boundary, `_validate_page_id`, `logger.warning(...)` on cleanup failures) or must be added by the ACs themselves — notably the invalid-path WARNING log and `is_dir()` check on `KB_PROJECT_ROOT`, the non-recursive `glob("*.tmp")` contract on `sweep_orphan_tmp`, and the `cache_clear()` hook on `load_page_frontmatter` for tests that mutate frontmatter mid-run.

## Trust boundaries

- **Env var → library config** (new): `KB_PROJECT_ROOT` flows from `os.environ` into `Path(...).resolve()` → becomes the root for every file I/O constant.
- **Process cwd → library config** (widened): AC6 walk-up fallback reads `Path.cwd()` up to 5 levels.
- **Caller → `sweep_orphan_tmp(directory, ...)`** (new internal-only): Directory arg is trusted-internal (no MCP surface).
- **Filesystem mtime → in-memory cache** (new): `load_page_frontmatter` trusts mtime_ns as a monotonic freshness signal.
- **`sys.modules` rebinding in test fixtures** (correctness only, not security).
- **Unchanged**: MCP stdio boundary, LLM API boundary, augment HTTP fetch boundary, path-traversal `_validate_page_id`.

## Data classification

- **No new persisted data classes.** `sweep_orphan_tmp` deletes `.tmp` orphans (already ephemeral). `load_page_frontmatter` caches public frontmatter. No new feedback/verdict/manifest schema.
- **Env var itself (`KB_PROJECT_ROOT`)** is a path, not a secret.

## Authn/authz

N/A everywhere. Local single-user CLI; OS-level environment is trusted. Document the assumption in the AC5 docstring and CHANGELOG Security section.

## Logging/audit

- **AC2**: unlink failure → `logger.warning(path, errno)`. Never raise past the boundary.
- **AC5**: invalid `KB_PROJECT_ROOT` → `logger.warning("attempted=<path>, falling back to heuristic")`.
- **AC6**: walk-up picks cwd-derived root differing from heuristic → `logger.info(...)` for operator debuggability.
- **AC7**: reuse existing logging-config guard in `main()`.
- **AC8**: optional DEBUG log on cache miss; no WARNING (stale-fallback is expected).

## Step-11 verification checklist (feed to Codex)

- **AC1** `tmp_kb_env`: teardown restores EVERY listed attribute; fixture is NOT `autouse`; deliberate leak test proves the `sys.modules` mirror list is complete; `PROJECT_ROOT` override uses `Path.resolve()`.
- **AC2** `sweep_orphan_tmp`: `max_age` uses `time.time() - path.stat().st_mtime`; unlink failures log WARNING with path + errno; returns int; never raises past the boundary; matches `directory.glob("*.tmp")` non-recursively; caller-provided `directory` is `resolve()`'d before scan.
- **AC3** `file_lock` docstring: diff shows only docstring lines.
- **AC4** atomic-write docstring: same — doc-only diff.
- **AC5** `KB_PROJECT_ROOT`: `Path(os.environ[...]).resolve()` applied; `is_dir()` checked; invalid fallback logs WARNING and does NOT raise; test with `KB_PROJECT_ROOT=/nonexistent` resolves to heuristic.
- **AC6** walk-up: hard-coded 5-level bound; only triggers when env unset AND heuristic fails both-marker test; walk-past-root falls back, does not crash.
- **AC7** `kb-mcp` console: `pyproject.toml` has `kb-mcp = "kb.mcp:main"`; `kb.mcp_server.main` is a re-export; `python -m kb.mcp_server` still works; no double tool registration.
- **AC8** cache: key includes `mtime_ns`; `maxsize=2048`; parse error returns `({}, "")`; `.cache_clear()` hook available; call-count pin confirms cache hit.
- **AC9** `utils/pages.py:108` migration: replaced; `scan_wiki_pages` tests still pass; existing `except` still catches helper fallthrough.
- **AC10** `graph/builder.py` docstring: caveat says "use `page['path']`, not `wiki_dir / f'{pid}.md'`".
- **AC11** `lint/checks.py` 4 migrations at 317, 398, 454, 601: each call-site's `except` preserved; pin test asserts `frontmatter.load` is called ≤ N times over a batch lint run.
- **AC12** new CLI test: `CliRunner` with `--wiki-dir <tmp>/wiki`; asserts ZERO writes under `PROJECT_ROOT`; manifest path is `<tmp>/.data/augment/*.json`.
- **AC13** new orchestrator test: NO `monkeypatch.setattr` on `MANIFEST_DIR`/`RATE_PATH`; only `wiki_dir=tmp_project/"wiki"`; rglob assertions.
- **AC14** conversation_context pin: hostile payload (embedded `</prior_turn>`, `\x00`-`\x1f`, fullwidth brackets) stripped; sentinel wrap verified; test FAILS if sanitizer removed.
- **AC15** BACKLOG sweep: hard deletes (no strikethrough); each deletion maps to a cycle-4/8/10/11 CHANGELOG entry; no open items removed.
- **AC16** CHANGELOG: Added/Changed/Fixed/Security sections; Security section calls out `KB_PROJECT_ROOT` env-var trust; Quick Reference row matches final `pytest --collect-only` count.
- **AC17** CLAUDE.md: `KB_PROJECT_ROOT` line added; test-count refs point to `CHANGELOG.md`; no numeric edits.

## Action items for implementers (surfacing from Opus notes)

1. **AC5**: MUST `Path.resolve()` AND `.is_dir()` — a `KB_PROJECT_ROOT=/path/to/regular-file.txt` must fall back, not silently produce bad joined paths later.
2. **AC2**: `sweep_orphan_tmp` MUST be non-recursive (`glob("*.tmp")`, not `rglob`).
3. **AC8**: One-line comment that mtime_ns resolution depends on filesystem (FAT32/SMB coarse-grain → cache-key collision window).
4. **AC16**: Security section MUST record the `KB_PROJECT_ROOT` trust-on-environment assumption.

## VERDICT

**PASS-WITH-NOTES** — 4 action items above integrated into AC text. Proceed to Step 3.
