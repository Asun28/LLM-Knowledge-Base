## Per-AC verification (17 items)
- AC1: IMPLEMENTED — `tests/conftest.py:127` defines opt-in `tmp_kb_env`; `tests/conftest.py:206-221` monkeypatches `kb.config`, mirrors already-imported `sys.modules` bindings, and patches capture derived paths. `tests/test_cycle12_conftest.py:10` verifies pre-imported consumers are rebound; `tests/test_cycle12_conftest.py:45` verifies the fixture is not autouse.
- AC2: PARTIAL — `src/kb/utils/io.py:154` implements `sweep_orphan_tmp`; `src/kb/utils/io.py:180` uses non-recursive `directory.glob("*.tmp")`; `src/kb/utils/io.py:187` uses `time.time() - path.stat().st_mtime`; `src/kb/utils/io.py:182,189,196` logs scan/stat/unlink failures at WARNING and returns a count. Gap: `src/kb/utils/io.py:176` raises `FileNotFoundError` for a missing directory, so the original "never raises" contract is not fully met.
- AC3: IMPLEMENTED — `src/kb/utils/io.py:234-239` documents the Windows PID-recycling caveat in `file_lock`; the `d97343f` diff shows this AC touched only docstring/test lines for `file_lock`.
- AC4: IMPLEMENTED — `src/kb/utils/io.py:60-68` and `src/kb/utils/io.py:95-103` document OneDrive/SMB network-mount atomic-write caveats and point callers to `sweep_orphan_tmp`; `tests/test_cycle12_io_sweep.py:69` asserts the caveat text exists.
- AC5: IMPLEMENTED — `src/kb/config.py:13-22` reads `KB_PROJECT_ROOT`, applies `Path(env_root).resolve()`, gates with `.is_dir()`, and logs WARNING on invalid values; `tests/test_cycle12_config_project_root.py:18,30,43` covers valid, missing, and regular-file env values.
- AC6: IMPLEMENTED — `src/kb/config.py:24-38` only walks up when env is unset and the heuristic lacks `pyproject.toml`, bounds the cwd parent search to five levels, logs INFO with `wiki_exists`, and falls back to the heuristic; `tests/test_cycle12_config_project_root.py:59,90` covers match and no-match cases.
- AC7: IMPLEMENTED — `src/kb/mcp/__init__.py:8-14` exposes package-level `main()` wrapping `mcp.run()`; `src/kb/mcp_server.py:3-6` re-exports both `main` and `mcp` and keeps `python -m kb.mcp_server`; `pyproject.toml:18` adds `kb-mcp = "kb.mcp:main"`; `tests/test_cycle12_mcp_console_script.py:1,7,17` covers package, shim, and script metadata.
- AC8: PARTIAL — `src/kb/utils/pages.py:58-66` implements the LRU cache keyed by `(str(path), mtime_ns)` with maxsize 8192, and `src/kb/utils/pages.py:69` exposes `cache_clear`; `tests/test_cycle12_frontmatter_cache.py:23,43,69` covers cache hit, mtime invalidation, and parse-error re-raise/non-caching. Gap: the required mtime_ns coarse-filesystem caveat is not present in a `load_page_frontmatter` docstring.
- AC9: IMPLEMENTED — `src/kb/utils/pages.py:91` is `load_all_pages`; `src/kb/utils/pages.py:122` now uses `load_page_frontmatter(page_path)` and the existing tolerant `except` block remains at `src/kb/utils/pages.py:137-146`; `tests/test_cycle12_frontmatter_cache.py:100` covers the regression.
- AC10: IMPLEMENTED — `src/kb/graph/builder.py:5-10` documents that lowercased IDs should not be used to reconstruct paths and that callers should use the stored `path`; `tests/test_cycle12_frontmatter_cache.py:180` asserts the caveat exists.
- AC11: IMPLEMENTED — `src/kb/lint/checks.py:317,399,456,604` are the four migrated `lint/checks.py` call sites; the surrounding `try/except` blocks are preserved; `tests/test_cycle12_frontmatter_cache.py:133` pins shared-cache call count and `tests/test_cycle12_frontmatter_cache.py:162` covers malformed frontmatter reporting.
- AC12: IMPLEMENTED — `tests/test_v5_lint_augment_cli.py:89` adds the two-phase public CLI regression; `tests/test_v5_lint_augment_cli.py:144-152` runs propose then execute with `--wiki-dir`; `tests/test_v5_lint_augment_cli.py:154-157` asserts raw/data writes land under the temp project and real `PROJECT_ROOT` snapshots are unchanged.
- AC13: IMPLEMENTED — `tests/test_v5_lint_augment_orchestrator.py:595` adds the custom-wiki `run_augment` regression; it passes `wiki_dir` and `raw_dir` explicitly at `tests/test_v5_lint_augment_orchestrator.py:645`, does not monkeypatch `MANIFEST_DIR`/`RATE_PATH` in the new test, and asserts temp `.data`, temp raw, and unchanged real project state at `tests/test_v5_lint_augment_orchestrator.py:647-658`.
- AC14: IMPLEMENTED — `tests/test_cycle12_sanitize_context.py:35` parameterizes the sanitizer pin over `use_api={False, True}`; `tests/test_cycle12_sanitize_context.py:80-94` asserts fence/control/BIDI stripping; `tests/test_cycle12_sanitize_context.py:98` verifies the sanitizer is called before branch selection.
- AC15: IMPLEMENTED — `BACKLOG.md` diff hard-deletes the stale cycle-12-resolved entries and adds the scoped cycle-13 follow-ups at `BACKLOG.md:186,220,222`; no strikethrough replacements were introduced.
- AC16: IMPLEMENTED — `CHANGELOG.md:37-60` adds the cycle-12 Added/Changed/Fixed/Security sections; `CHANGELOG.md:60` records the `KB_PROJECT_ROOT` trust assumption; `CHANGELOG.md:107` adds the Quick Reference row with the 2115 collected-test count.
- AC17: IMPLEMENTED — `CLAUDE.md:33` and `CLAUDE.md:169` point test counts at `CHANGELOG.md`; `CLAUDE.md:55` documents `KB_PROJECT_ROOT` and the heuristic/walk-up fallback.

## Opus R1 action items
- R1.1: IMPLEMENTED — `src/kb/config.py:16-17` uses `Path(env_root).resolve()` plus `.is_dir()` before accepting `KB_PROJECT_ROOT`; invalid values log and fall back at `src/kb/config.py:22`.
- R1.2: IMPLEMENTED — `src/kb/utils/io.py:180` uses `directory.glob("*.tmp")`; no `rglob` is used inside `sweep_orphan_tmp`.
- R1.3: MISSING — grep of `src/kb/utils/pages.py` shows `mtime_ns` in the cache key at `src/kb/utils/pages.py:59,65`, but `load_page_frontmatter` has no docstring and no coarse-filesystem caveat.
- R1.4: IMPLEMENTED — `CHANGELOG.md:60` records the OS-trusted `KB_PROJECT_ROOT` assumption and notes that a hostile local environment can redirect file I/O.

## Same-class completeness
- load_page_frontmatter — IMPLEMENTED with deliberate deferral: production migrated sites are `src/kb/utils/pages.py:122` plus `src/kb/lint/checks.py:317,399,456,604`. Remaining production `frontmatter.load` sites are exactly the deferred eight: `src/kb/lint/augment.py:72,914,1026,1053,1082`, `src/kb/lint/semantic.py:122`, `src/kb/graph/export.py:132`, and `src/kb/review/context.py:56`; `BACKLOG.md:186` tracks them for cycle 13.
- KB_PROJECT_ROOT — IMPLEMENTED: `PROJECT_ROOT = _resolve_project_root()` at `src/kb/config.py:44`, and downstream path constants derive from it at `src/kb/config.py:45-92,164-166` rather than from the pre-cycle-12 literal.
- sweep_orphan_tmp — IMPLEMENTED as library-only: `rg "sweep_orphan_tmp\\(" src/kb` finds only docstring mentions and the definition at `src/kb/utils/io.py:154`; `BACKLOG.md:220` tracks default caller wiring for cycle 13.

## Bypass + source-scan anti-pattern grep
- No cycle-12 diff hits for `def _\w*_for_legacy|bypass|unsafe_` under `src/kb/` (`git diff main..HEAD -G... -- src/kb/` returned empty). Repository-wide `rg` has older comments containing "bypass", but none are PR-introduced by cycle 12.
- No cycle-12 test source-scan anti-pattern hits for `read_text|splitlines|getsource|findall.*\.py` in `tests/test_cycle12*.py` (`git diff main..HEAD -G... -- tests/test_cycle12*.py` returned empty).

## Class B CVE diff
- requirements.txt diff: EMPTY — `git diff main..HEAD -- requirements.txt` returned no output.
- pyproject.toml diff: OK — only `[project.scripts]` adds `kb-mcp = "kb.mcp:main"`; no dependency changes.
- pip-audit advisories (branch): `{CVE-2025-69872}` on `diskcache==5.6.3` with alias `GHSA-w8v5-vhqr-4h9v` and no fix versions.
- vs baseline (main): `{CVE-2025-69872}` per `docs/superpowers/decisions/2026-04-19-cycle12-cve-baseline.md`.
- Class B delta: empty

## VERDICT
PASS-WITH-PARTIAL [AC2 missing-directory raise despite "never raises" contract; AC8/R1.3 missing mtime_ns caveat docstring]
