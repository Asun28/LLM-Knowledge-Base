# Changelog

All notable changes to this project are documented in this file.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) + [Semantic Versioning](https://semver.org/).

> **High-level index.** Keep this file brief and newest first. Each cycle gets compact Items / Tests / Scope / Detail fields and points to the full archive in [CHANGELOG-history.md](CHANGELOG-history.md).
> Cross-reference: [BACKLOG.md](BACKLOG.md) tracks open work; resolved items are deleted from BACKLOG once shipped here.

<!-- Entry rule — newest first; keep this file brief and move details to CHANGELOG-history.md.
#### YYYY-MM-DD — cycle N
- Items: <N> AC / <M> src / <K> commits
- Tests: A → B (+Δ)
- Scope:
  <one-sentence scope only>
- Detail: [history archive](CHANGELOG-history.md#<anchor>)

Commit-count convention (codified cycle 28 AC8 per cycle-26 L1 skill patch):
on the feature-branch squash-merge flow, the reported <K> equals pre-doc-update
branch commits + 1 for the landing doc-update that contains this changelog
line (self-referential). If R1/R2 PR review triggers fix commits, increment
<K> atomically with each fix commit and re-check `git log --oneline main..HEAD`
before push.
-->

## [Unreleased]

### Quick Reference

Newest first. `CHANGELOG.md` is the compact index; full detail lives in [CHANGELOG-history.md](CHANGELOG-history.md).

#### 2026-04-27 — cycle 40 (Backlog hygiene + freeze-and-fold continuation + dep-drift re-verification)

- Items: 11 AC (AC1-AC11) / 0 src (`src/kb/` untouched — test fold + BACKLOG + doc-sync only) / 4 test-file edits (`tests/test_mcp_browse_health.py` +90 / -0; `tests/test_compile.py` +14 / -0; `tests/test_utils_text.py` +13 / -0; `tests/test_query.py` +51 / -1) + 3 test-file deletes (`tests/test_cycle10_safe_call.py` -75; `tests/test_cycle10_linker.py` -13; `tests/test_cycle11_stale_results.py` -50) + BACKLOG.md (8 hunks: 7 cycle-40 markers on dep-CVE/resolver/Dependabot-drift entries + 1 Phase 4.5 HIGH #4 progress marker) + CHANGELOG/CHANGELOG-history/CLAUDE.md/docs/reference/README test-FILE count narrative + 4 cycle-40 decision docs / +TBD commits (Step-7 plan expected 5 implementation + 1 self-review = 6 total)
- Tests: 3014 → 3014 (+0: folds preserve count; file count 258 → 255 via 3 source-file deletions; full Windows local: 3003 passed + 11 skipped, unchanged from cycle-39 baseline)
- Scope:
  Continued the cycle-4 freeze-and-fold rule (Phase 4.5 HIGH item #4) by folding three more cycle-10/11 era test files into their canonical homes. AC1 folded `tests/test_cycle10_safe_call.py` (5 tests, sanitization at MCP boundary) into `tests/test_mcp_browse_health.py` as `class TestSanitizeErrorStrAtMCPBoundary` per cycle-39 class-precedent for thematic clusters. AC2 split `tests/test_cycle10_linker.py` (2 misnamed tests — neither was actually about linker.py) by actual symbol ownership: test 1 (`detect_source_drift` docstring contract) → `tests/test_compile.py` Compiler section as bare function; test 2 (`wikilink_display_escape` pipe behavior) → `tests/test_utils_text.py` wikilink section as bare function. AC3 folded `tests/test_cycle11_stale_results.py` (4 tests, `_flag_stale_results` edge cases) into `tests/test_query.py` as `class TestFlagStaleResultsEdgeCases` with the cycle-15 AC1 explanatory comment about the removed `20260101` int parametrize case preserved verbatim. AC4-AC10 re-verified all seven cycle-39+ tagged carry-overs against the live pip-audit + Dependabot baselines (state matches cycle 39 — diskcache 5.6.3 / ragas 0.4.3 / litellm 1.83.0 / pip 26.0.1 all still no-upstream-fix; three resolver conflicts persist verbatim; two Dependabot drift entries still NOT emitted by pip-audit on live env). Notable cycle-40 finding: pip 26.1 was published TODAY 2026-04-27 (now LATEST per `pip index versions pip`), but the GHSA-58qw-9mgm-455v advisory metadata still shows `vulnerable_version_range: <=26.0.1` with `patched_versions: null` — pip-audit therefore continues to emit empty `fix_versions`. Conservative posture per cycle-22 L4: do NOT bump the pip pin until the advisory or PyPA security disclosure confirms 26.1 patches the CVE; track for next cycle. AC11 marker-appended on Phase 4.5 HIGH #4 BACKLOG entry: 4 files folded across cycles 39+40 (1 + 3); tests/ file count 258 → 255 via this cycle's deletions; HIGH item remains open with ~200+ versioned files still to fold across future cycles. Steps 1-13 ran primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary holds context); Steps 3 (brainstorming), 4 (design eval), 6 (Context7), and 9.5 (simplify) all skipped per their skip-eligibility rules (pure hygiene, trivial, no third-party libs, zero src changes). Step 5 design gate ran via Opus subagent per skill rule despite zero open questions → 6 questions resolved with HIGH confidence + 15 binding CONDITIONS; ALL 15 satisfied by Step 9 implementation. All 6 threat-model checklist items verified clean (T1 PR-introduced CVE diff = empty since cycle 40 changes zero deps; T2-T4 baselines match; T5 deferred-promise BACKLOG tags consistent post-re-tag; T6 test-count invariant 3014).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-40)

#### 2026-04-27 — cycle 39 (Backlog hygiene + dep-drift re-verification + cycle-38 test fold)

- Items: 11 AC (AC1-AC11) / 0 src (`src/kb/` untouched — BACKLOG + test fold + doc-sync only) / 1 test-file edit (`tests/test_capture.py` +180 / -0) + 1 test-file delete (`tests/test_cycle38_mock_scan_llm_reload_safe.py` -192) + BACKLOG.md (10 hunks: 7 re-confirm markers + 3 cycle-39+→cycle-40+ re-tags + 1 resolved-fold-entry deletion) + CHANGELOG/CHANGELOG-history/CLAUDE.md/docs/reference test-count narrative + README test/file count + 4 cycle-39 decision docs / +TBD commits (Step-5 D7 expected 4 implementation + 1 self-review = 5 total; actual 5 implementation post-Codex-NIT fixes + 1 Step-16 = 6 total post-merge)
- Tests: 3014 → 3014 (+0: fold preserves count; file count 259 → 258 via cycle-38 file deletion; full Windows local: 3003 passed + 11 skipped, unchanged from cycle-38 baseline)
- Scope:
  Backlog hygiene cycle. Re-confirmed seven cycle-39+ tagged carry-over entries against the live pip-audit + Dependabot baselines: four no-upstream-fix CVEs (`diskcache 5.6.3 / CVE-2025-69872`, `ragas 0.4.3 / CVE-2026-6587`, `litellm 1.83.0 / GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc + GHSA-v4p8-mg3p-g94g`, `pip 26.0.1 / CVE-2026-3219`), three resolver conflicts (cycle-34 AC52 carry-over: `arxiv requests~=2.32.0 vs 2.33.0`, `crawl4ai lxml~=5.3 vs 6.1.0`, `instructor rich<15.0.0 vs 15.0.0`), and two Dependabot pip-audit drift entries (litellm `GHSA-r75f-5x8p-qvmc` + `GHSA-v4p8-mg3p-g94g` reported by Dependabot but still NOT emitted by pip-audit on the live env). litellm upgrade still ResolutionImpossible: `pip download litellm==1.83.14 --no-deps` zipfile metadata shows `Requires-Dist: click==8.1.8` (no relaxation across 7 patch releases since cycle 32 baseline). Folded `tests/test_cycle38_mock_scan_llm_reload_safe.py` into `tests/test_capture.py::TestMockScanLlmReloadSafety` per cycle-4 L4 freeze-and-fold rule and cycle 38's own self-tagged candidate note: 2 test methods + 4 module-level helpers + 1 autouse `_restore_kb_capture` fixture moved verbatim with full docstrings (manual revert-check guidance preserved per `feedback_test_behavior_over_signature`); defensive `import kb.capture as _kb_capture` line dropped (test_capture.py:20 `from kb.capture import (...)` already loads kb.capture under real PROJECT_ROOT before any fixture runs); `import importlib` added for the autouse fixture body. Re-tagged 3 cycle-39+ items deferred from cycle 39 (windows-latest CI matrix re-enable, GHA-Windows multiprocessing spawn investigation, `TestWriteItemFiles` POSIX off-by-one) to cycle-40+ per cycle-23 L3 deferred-promise BACKLOG sync — these need self-hosted Windows runner / POSIX shell access unavailable to the cycle-39 operator session. Steps 1-13 ran primary-session per C37-L5 (≤15 ACs / ≤5 src files / primary holds context); Step 6 Context7 skipped per pure-stdlib/internal rule; Step 9.5 simplify pass skipped per <50 LoC src trivial-diff rule (zero src changes). All 4 threat-model items verified clean (T1 PR-introduced CVE diff = empty since cycle 39 changes zero deps; T2 `git diff origin/main -- src/` = 0 bytes; T3 folded tests pass + 3003+11 baseline preserved; T4 deferred-promise BACKLOG tags consistent post-re-tag).
- Detail: [history archive](CHANGELOG-history.md#2026-04-27--cycle-39)

#### 2026-04-26 — cycle 38 (POSIX test re-enable: mock_scan_llm dual-site + ruff T20)

- Items: 9 AC (AC0-AC6, AC9, AC10) / 0 src (`src/kb/` untouched — fixture + test-side fix) / 4 test-file edits (`tests/conftest.py`, `tests/test_capture.py`, `tests/test_mcp_core.py`, `tests/test_cycle38_mock_scan_llm_reload_safe.py` NEW) + 1 config (`pyproject.toml` ruff T20) + BACKLOG.md cleanup + 8 cycle-38 decision docs / +TBD commits (expected 3-4 squash-merge per Step-5 Q5 squash mandate)
- Tests: 3012 → 3014 (+2: cycle-38 mock_scan_llm reload-safety regression — case (a) baseline + case (b) dual-site contract assertion; full Windows local: 3003 passed + 11 skipped, was 2991 + 21 — 10 SDK tests + 2 atomic_text_write tests now exercise unconditionally)
- Scope:
  Closes 2 of 5 cycle-38 BACKLOG candidates: (a) Category A 10-test mock_scan_llm POSIX reload-leak (AC1-AC5) and (b) Category B 2-test atomic_text_write POSIX patch class (AC6 strict scope per design Q3). The original "reload-leak class" hypothesis (cycle-19 L2 / cycle-20 L1) was REFUTED by R2 Codex in Step-4 design eval — `kb.config` imports only stdlib (verified at `src/kb/config.py:3-9`), so reloading it cannot cascade to `kb.utils.llm` or `kb.capture`. The actual contamination source is `del sys.modules["kb.capture"]` + reimport in `tests/test_capture.py::TestSymlinkGuard` (line 700-714) which leaves the file's pre-collection bindings (line 20+ `from kb.capture import ...`) holding OLD module function objects whose `__globals__` is the OLD `__dict__` — patching `sys.modules["kb.capture"].call_llm_json` post-reimport doesn't reach the OLD `__dict__` that test functions actually use. AC0 refactors `TestSymlinkGuard` to subprocess so it never touches the parent's `sys.modules`, eliminating the contamination source. AC1 widens `mock_scan_llm` fixture to dual-site patch (`kb.utils.llm.call_llm_json` BEFORE `kb.capture.call_llm_json`) as defense-in-depth. AC2 propagates the dual-site pattern to 2 inline `monkeypatch.setattr` sites in `test_capture.py`. AC3+AC4 drop 7 + 3 = 10 `@_REQUIRES_REAL_API_KEY` decorators. AC5 codifies the cycle-38 contract via order-independent assertion (the original sys.modules-deletion replay was full-suite-fragile). AC6 widens both atomic_text_write patches and drops `@_WINDOWS_ONLY` from `test_cleans_up_*` (strict scope per R2 grep table — only test_capture.py:741,754 had the cycle-36 risk pattern). AC9 re-confirms Dependabot drift unchanged (litellm GHSA-r75f / GHSA-v4p8 still not surfaced by pip-audit; expected no-change branch). AC10 deletes 2 resolved cycle-38+ BACKLOG entries; re-pins 2 unresolved Windows-CI candidates + 2 Dependabot-drift entries to cycle-39+; adds new cycle-39+ entry for fold-into-canonical of the new test file (cycle-4 L4 freeze-and-fold). Design Q5 amendment: ruff T20 (flake8-print) added to `pyproject.toml [tool.ruff.lint].select` for probe-print defense. AC7+AC8 (POSIX off-by-one slug + creates_dir) DEFERRED to cycle-39 per design M1 standing pre-auth — investigation requires deeper POSIX shell access; the `@_WINDOWS_ONLY` skipif on the 2 affected `TestWriteItemFiles` tests stays. ZERO new CI dimensions per cycle-36 L1 (windows-latest matrix + GHA spawn investigation re-pinned to cycle-39+).
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-38)

#### 2026-04-26 — cycle 37 (POSIX symlink security fix + requirements split)

- Items: 9 AC across 5 file-grouped tasks / 1 src (`src/kb/review/context.py`) + 1 test (`tests/test_phase45_theme3_sanitizers.py`) + 6 NEW requirements files + 1 NEW test (`tests/test_cycle37_requirements_split.py`) + 1 README + 4 cycle-37 decision docs / +TBD commits (2 implementation + 1 doc-update; expected 3 total per Step-5 squash-merge cadence)
- Tests: 3005 → 3012 (+7: 6 cycle-37 requirements-split regression + 1 positive-case `test_qb_symlink_inside_raw_accepted`; full Windows local: 2991 passed + 21 skipped 0 failures)
- Scope:
  Closes 2 of 7 cycle-37 BACKLOG candidates filed at cycle-36 close: (a) production POSIX symlink security gap in `pair_page_with_sources` (cycle-36 ubuntu-probe surfaced; was masked by Windows-only `is_symlink()` check that became dead code after `.resolve()` was called first), and (b) requirements.txt split into runtime + 5 per-extra files mirroring `pyproject.toml [project.optional-dependencies]`. AC1 reorders `is_symlink()` capture to BEFORE `.resolve()` so the existing containment check at `context.py:86-103` (previously dead code on POSIX) actually fires; AC2 drops the cycle-36 `skipif(os.name != "nt")` marker on `test_qb_symlink_outside_raw_rejected`; AC3 adds positive-case `test_qb_symlink_inside_raw_accepted` covering legitimate intra-`raw/` symlinks (target stays within `raw_dir`). AC4-AC8 mirror pyproject extras as 6 new layered `requirements-{runtime,hybrid,augment,formats,eval,dev}.txt` files; AC7 amended at design gate Q3 from "shim" to "UNCHANGED" — `requirements.txt` stays as the 295-line frozen snapshot for backward-compat reproducibility, new files are additive. AC6 propagates cycle-35 L8 floor pin `langchain-openai>=1.1.14` into `requirements-eval.txt` (closes GHSA-r7w7-9xr2-qq2r). AC9 6-assertion regression test `test_cycle37_requirements_split.py` pins file existence + `-r` includes + floor pin + tomllib pyproject cross-check + snapshot-preservation. ZERO new CI dimensions per cycle-36 L1 (windows-latest matrix re-enable + remaining 5 cycle-37 candidates DEFERRED to cycle 38+: GHA-Windows multiprocessing spawn investigation, mock_scan_llm POSIX reload-leak, TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behaviour, Dependabot pip-audit drift on 2 litellm GHSAs).
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-37)

#### 2026-04-26 — cycle 36 (test+CI infrastructure hardening)

- Items: 26 designed AC, ~23 effective after Q7=B Area E deferral (AC1-AC13, AC18-AC25; AC14-AC17 + AC26 deferred to cycle 37 per Step-5 Q7=B; AC9 confirmed unchanged after pip-audit live-env audit) / 0 src (`src/kb/` untouched — test+CI infrastructure only) / 9 test-file edits + 2 NEW (`tests/_helpers/api_key.py`, `tests/test_cycle36_ci_hardening.py`) + 1 NEW dir (`tests/_helpers/`) + 4 config files (`.github/workflows/ci.yml`, `pyproject.toml`, `requirements.txt`, `SECURITY.md`) + 8 cycle-36 decision docs + BACKLOG.md / +TBD commits (backfill post-merge per cycle-30 L1; expected ~3 commits in three-commit sequence per Step-5 Q16/Q21 plus doc-update commits)
- Tests: 2995 → 3005 (+10 cycle-36 hardening tests in `tests/test_cycle36_ci_hardening.py`; full Windows local: 2985 passed + 20 skipped no failures; 10 added skips are `requires_real_api_key` markers on developer machine without real key)
- Scope:
  Closes 2 of 3 explicit cycle-36 BACKLOG follow-ups (strict pytest CI gate AC8 +
  cross-OS portability matrix AC11/AC12) + opportunistic CVE recheck (AC18-AC20).
  Area E (requirements split AC14-AC17) deferred to cycle 37 per Step-5 design Q7=B.
  Four-commit sequence on the cycle-36 PR: probe → fix → strict-gate → ubuntu-only
  pivot. Probe ubuntu-latest CI run surfaced 23 failures across 5 fragility classes;
  commit 2 applied marker fixes; commit 3 attempted matrix [ubuntu, windows] with
  strict-gate but windows-latest hit a SECOND hang at threading.py:355 after the
  cycle-23 multiprocessing skipif fired; commit 4 pivots to ubuntu-only single-OS
  strict-gate to close cycle-36 cleanly without more failed CI runs (windows-latest
  matrix re-enable filed as cycle-37 BACKLOG entry per CI-cost-discipline lesson). `pytest-timeout>=2.3`
  added to `[dev]` extras + `requirements.txt` with `[tool.pytest.ini_options]
  timeout = 120` global default to fail fast on hangs (was silent KeyboardInterrupt
  on cycle-23 multiprocessing spawn-bootstrap under GHA 6-hour ceiling).
  `tests/_helpers/api_key.py::requires_real_api_key()` predicate gates SDK-using
  tests on dummy CI key (matched via `sk-ant-dummy-key-` prefix per cycle-36 AC6).
  AC11 anti-Windows + anti-POSIX skipif markers data-driven from probe (AC11 list
  was partly mis-directional in requirements doc per Step-5 Q8 / R1-NEW-1; replaced
  with probe-driven list per Q5=B). AC5 mirror-rebind adds `kb.config.WIKI_DIR`
  patch to cycle-10 quality tests + `kb.mcp.quality.WIKI_DIR` to MCP phase 2 tests
  (cycle-19 L1 snapshot pattern; Windows CI previously masked these via cycle-23
  multiprocessing-hang at #1155). `pip-audit --ignore-vuln` switched from PowerShell
  backtick continuation to bash backslash for cross-OS shell compatibility (regression
  test in `test_cycle34_release_hygiene.py` updated to accept either form).
  SECURITY.md trim: removed parenthetical Dependabot-only `GHSA-r75f-5x8p-qvmc` from
  litellm row to satisfy C10 set-equality test; both that ID and new
  `GHSA-v4p8-mg3p-g94g` (created 2026-04-25T23:37Z) tracked as cycle-37 BACKLOG drift
  entries (pip-audit on live CI install env doesn't emit those IDs as of 2026-04-26
  — workflow `--ignore-vuln` set unchanged at 4 IDs). 5 NEW cycle-37 BACKLOG entries
  filed for deferred investigations: GHA-Windows multiprocessing spawn,
  mock_scan_llm POSIX reload-leak, `test_qb_symlink_outside_raw_rejected` POSIX
  symlink security gap, TestExclusiveAtomicWrite/TestWriteItemFiles POSIX behaviour,
  Dependabot pip-audit drift on 2 litellm GHSAs.
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-36)

#### 2026-04-26 — cycle 35 (Pre-Phase-5 BACKLOG batch + cycle-34 AC4e completion)

- Items: 18 designed AC + AC1b T1b proactive close + AC-Dep1 GitPython bump + AC-Doc1 doc updates = 21 effective / 4 src (`utils/sanitize.py`, `ingest/pipeline.py`, `mcp/core.py`, `requirements.txt`) + 2 NEW test files (`tests/test_cycle35_ingest_index_writers.py`, `tests/test_cycle35_mcp_core_filename_validator.py`) + 4 docs (`docs/architecture/architecture-diagram.html`, `architecture-diagram-detailed.html`, `architecture-diagram.png`, `docs/reference/conventions.md`) + 3 doc-anchor test re-anchors after the cycle-34-followup CLAUDE.md split + 1 ruff format normalization carryover / +TBD commits (backfill post-merge per cycle-30 L1)
- Tests: 2941 → 2995 (+54 passed: 6 new sanitize tests on `test_cycle33_mcp_core_path_leak.py` — including 4 AC1/AC1b/AC3 + 1 R1 Codex AC10 NIT + 2 R1 Sonnet PR-49 negatives — 8 new ingest index-writer tests, 39 new mcp/core filename-validator tests, +1 baseline net adjustment after the doc-anchor re-anchor)
- Scope:
  Closes 6 pre-Phase-5 BACKLOG items (M11 RMW lock + M12 UNC slash-normalize + M13 empty-list +
  M14 backtick-dedup + M15 filename validator parity + M21 architecture v0.11.0 sync) plus
  cycle-34's deferred AC4e diagram + PNG re-render. `_ABS_PATH_PATTERNS` gains TWO new
  alternatives — slash-form Windows UNC long-path `(?://\?/UNC/...)` (T1b) AND URI-guarded
  ordinary slash UNC `(?<!:)(?://...)` (T1) — plus a `(?<![A-Za-z])` lookbehind on the
  drive-letter alternative to prevent URL overmatch (`https://host/path` no longer collapses
  to `<path>` via the `s://` collision; pre-existing behavior since cycle 18 AC13 that no
  prior cycle had caught). `sanitize_error_text` per-path substitution now probes both
  single-backslash AND OSError-doubled-backslash forms of the filename attribute, closing
  the cycle-33 xfail-strict gap directly (XPASS-strict semantic forced marker removal in
  the same commit). `_update_sources_mapping` and `_update_index_batch` RMW windows wrapped
  in `file_lock(target_path)` (cycle-19 discipline; NO wrapper-level lock in
  `_write_index_files` because `file_lock` is `os.O_EXCL` non-reentrant per Step-5 Q7);
  empty-`wiki_pages` early-return at function entry kills the malformed `→ \n` line +
  suppresses the `_sources.md not found` warning (T8); membership + per-line scan switched
  to `escaped_ref` so backtick-bearing source_refs dedup correctly. New shared
  `_validate_filename_slug(filename) -> tuple[str, str | None]` helper rejects NUL byte /
  path separators / `..` / trailing dot or space (Windows trim aliasing) / non-ASCII
  (`[^\x00-\x7F]` blocks homoglyph + RTL-override + zero-width attacks) / over-200-char /
  Windows-reserved (via existing `_is_windows_reserved`); allows leading dot (`.env`) and
  leading dash (`-foo`) per Step-5 Q5. Wired into `_validate_file_inputs` so
  `kb_ingest_content` + `kb_save_source` reach validation parity with `kb_query.save_as`
  for the security-class checks (looser slug-equality contract appropriate to free-form
  names). Architecture diagrams bumped v0.10.0 → v0.11.0 with Playwright PNG re-render
  (closes deferred cycle-34 AC4e); canonical Playwright snippet codified in
  `docs/reference/conventions.md` to prevent a third deferral. Step-11b GitPython 3.1.46 →
  3.1.47 closes Dependabot GHSA-x2qx-6953-8485 + GHSA-rpm5-65cw-6hj4 (zero `import git` in
  `src/kb`; transitive tooling dep only).
- Detail: [history archive](CHANGELOG-history.md#2026-04-26--cycle-35)

#### 2026-04-26 — cycle 35 post-merge hotfix (CI pip-audit fix)

- Items: 1 / 1 src (`pyproject.toml`) / 1 commit (`cf0f996`)
- Tests: 2995 → 2995 (no test changes; CI pip-audit step now passes)
- Scope:
  Cycle-35 merge-commit CI failed at the `Pip-audit (live env)` step on a
  late-arrival LOW-severity advisory: `langchain-openai 1.1.10
  GHSA-r7w7-9xr2-qq2r` (DNS-rebinding SSRF in image-token-counting helper,
  fix at 1.1.14). The advisory landed DURING cycle 35, AFTER the Step-2
  baseline + Step-11.5 Dependabot read. `requirements.txt` already pinned
  `langchain-openai==1.1.14` (so the local `.venv` was patched), but CI's
  `pip install -e '.[dev,formats,augment,hybrid,eval]'` walks pyproject.toml
  extras instead — and the `[eval]` extra had no floor pin on
  langchain-openai (transitively pulled by ragas), so the CI resolver picked
  1.1.10. One-line fix: add `langchain-openai>=1.1.14` to the `[eval]`
  extra in pyproject.toml. Zero `import langchain_openai` in `src/kb`
  (transitive eval-only dep used by the ragas evaluation harness). CI step-
  level verification (cycle-34 L7) passed: every job step `success | skipped`,
  zero failures. Process miss documented as C35-L8 skill patch in
  `references/cycle-lessons.md`.
- Detail: see commit message for full failure-reproduction trace.

#### 2026-04-25 — cycle 34 (Release hygiene · v0.10.0 → v0.11.0)

- Items: 54 AC delivered (out of 57 designed; AC4e diagram bump DEFERRED to cycle 35 + AC49 boot-lean fix DROPPED at Step 9 with test-anchor retention + AC55 architecture-diagram-version-test DROPPED with the deferred AC4e) / 4 src (`pyproject.toml`, `src/kb/__init__.py`, `src/kb/config.py`, `src/kb/ingest/pipeline.py`) + 2 NEW user-facing files (`SECURITY.md`, `.github/workflows/ci.yml`) + 1 NEW test file (`tests/test_cycle34_release_hygiene.py`) + 4 doc/config files modified (`README.md`, `README.zh-CN.md`, `requirements.txt`, `.gitignore`) + 6 untracked deletions (`findings.md`, `progress.md`, `task_plan.md`, `claude4.6.md`, `docs/repo_review.md`, `docs/repo_review.html`) + 2 NEW review artifacts committed (`docs/reviews/2026-04-25-comprehensive-repo-review.{md,html}`) / +TBD commits (backfill post-merge per cycle-15 L4 + cycle-30 L1)
- Tests: 2923 → 2941 (+18 passed: cycle-34 release-hygiene regressions covering pyproject readme, extras structure, jsonschema runtime dep, version lockstep across pyproject + `__init__.py` + README badge, "No vectors" tagline absent regression, `.pdf` extension removal, scratch-file deletion regression, `.gitignore` patterns present, SECURITY.md required sections, CI workflow YAML structure, save_as= clarification in CLAUDE.md, comprehensive-review presence, kb_save_synthesis absent forward regression, README v0.11.0 badge, pip-audit -r flag, and boot-lean subprocess probe)
- Scope:
  Closes 8 P0/P1 ship-blocker findings from `docs/reviews/2026-04-25-comprehensive-repo-review.md`
  (Findings 1, 2, 3, 5, 6, 7, 9, 20). Packaging metadata aligned with code surface
  (`pyproject.toml.readme = "README.md"`; new `[project.optional-dependencies]` extras
  `hybrid` / `augment` / `formats` / `eval` / `dev` with concrete pin lower-bounds; `jsonschema`
  added to runtime dependencies for cycle-21 cli_backend; version 0.10.0 → 0.11.0 across
  pyproject + `src/kb/__init__.py`). New `SECURITY.md` documents narrow-role acceptance for the
  four open advisories (`diskcache 5.6.3` CVE-2025-69872, `litellm 1.83.0` GHSA-xqmj-j6mv-4862,
  `pip 26.0.1` CVE-2026-3219, `ragas 0.4.3` CVE-2026-6587) with verification grep + unblock
  conditions + per-cycle re-check cadence. New `.github/workflows/ci.yml` provides the first
  automated CI gate (ruff + pytest --collect-only + full pytest + pip check soft-fail +
  pip-audit with documented `--ignore-vuln` + `python -m build && twine check`); workflow
  ships with `permissions: read-all` (T1), `concurrency: cancel-in-progress` (NT5),
  `on: { push: { branches: [main] }, pull_request: {} }` (NT4 cost containment),
  `actions/{checkout,setup-python}@v6` (Step-6 Context7 amendment vs original @v4/@v5),
  and a dedicated `pip install build twine pip-audit` step (NEW-Q13 / AC50). README content
  drift fixes: `> blockquote` tagline at line 5 replaced from "No vectors. No chunking."
  to "Markdown-first; optional hybrid retrieval"; matching bullet at line 17 from
  "Structure, not chunks." to "Structure first, optional vectors."; PDF row removed from
  Supported File Formats with sentence directing at markitdown/docling; tests-2850 badge
  → tests-passing-brightgreen (drift surface eliminated per Q6); v0.10.0 → v0.11.0 badge;
  Quick Start expanded with extras-aware install paths. `src/kb/config.py` removes `.pdf`
  from `SUPPORTED_SOURCE_EXTENSIONS` (Finding 7); `src/kb/ingest/pipeline.py` updates the
  binary-rejection message at lines 1261-1265 to enumerate supported extensions for better
  UX, and the now-stale comment at line 1198. Six untracked scratch/superseded files
  deleted (filesystem `rm`, not `git rm`, per NEW-Q19); the comprehensive review
  committed at the new `docs/reviews/` convention. `README.zh-CN.md` gains a 1-line
  "English canonical, may lag" note (Q8 + R1 AC23.5). CLAUDE.md state-line + test-count
  + Latest cycle summary updated; new Release-artifacts pointer added. `BACKLOG.md` adds
  5 cycle-34 follow-up entries (cycle-35 `pip check` resolver-conflict unblock, cycle-35
  architecture-diagram v0.11.0 + PNG re-render, cycle-N+1 if requested real PDF extraction,
  cycle-N+1 if requested `KB_DISABLE_VECTORS` runtime flag, cycle-36 `requirements.txt`
  per-extra split). The 4 narrow-role CVE BACKLOG entries STAY (no upstream patch
  installable; SECURITY.md documents acceptance). Step-9 DESIGN-AMENDs: AC49 production
  fix DROPPED after primary-session probe confirmed `kb.cli` already does NOT pull in
  `kb.lint.fetcher`/`httpx`/`trafilatura` at module-load (R2 NT1 premise was stale);
  AC56 boot-lean test retained as forward-protection regression per cycle-15 L2.
  AC4e architecture-diagram bump deferred per design-gate fallback (NEW-Q15 option B).
- Detail: [history archive](CHANGELOG-history.md#2026-04-25--cycle-34--release-hygiene)

#### 2026-04-25 — cycle 33

- Items: 11 AC / 2 src (`mcp/core.py`, `ingest/pipeline.py`) + 2 new test files / 8 commits (6 feat+docs+fix on branch + 1 merge + 1 self-review)
- Tests: 2901 → 2923 (+21 passed including R1 mkdir-failure + R2 lazy-import-failure regressions; +1 xfailed for the Q8 ordinary-UNC residual)
- Scope:
  Closes BACKLOG `mcp/core.py:762,881` MEDIUM (cycle-32 threat T11) —
  AC1/AC2/AC3 wrap raw `OSError write_err` interpolation in pre-computed
  `sanitized_err = _sanitize_error_str(write_err, file_path)` at the
  paired `logger.warning` + `Error[partial]:` return for both
  `kb_ingest_content` (`core.py:748-768`) and `kb_save_source`
  (`core.py:868-893`); single binding ensures log + return cannot drift
  apart. AC4 same-class peer at `kb_query.save_as` (`core.py:279-285`)
  upgrades BOTH the previously-asymmetric `logger.warning(... %s, exc)`
  AND the return string to use `_sanitize_error_str(exc, target)` for
  symmetric path-attribute redaction depth (matches AC1/AC2). AC5
  regression suite at `tests/test_cycle33_mcp_core_path_leak.py` —
  15 tests covering Windows-drive-letter + POSIX shapes for all 3 sites,
  5-case parametrised `sanitize_error_text` OSError-shape unit suite
  (3-arg / no-filename / filename=None / filename2 / args[1] path),
  plus 3 UNC/long-path tests. AC6 adds "## Idempotency" docstring
  paragraphs to `_update_sources_mapping` + `_update_index_batch`
  documenting (a) safe-on-crash-then-reingest contract, (b) merge-on-
  new-pages contract, (c) explicit "Concurrent calls may race"
  serial-only disclaimer. AC7+AC8 pin both contracts behaviorally via
  `tests/test_cycle33_ingest_index_idempotency.py` — 5 tests with
  `MagicMock(side_effect=atomic_text_write)` spy + call_count assertions
  (1 for dedup branches, 2 for merge branch, 0 for missing-file
  early-out at `pipeline.py:773-775`). AC9 deletes the closed
  `mcp/core.py:762,881` BACKLOG entry. AC10 narrows the
  `ingest/pipeline.py` BACKLOG entry from "duplicate-on-reingest"
  (closed) to "RMW-concurrency residual" (still open — the serial
  dedup is now contract+test pinned but concurrent-ingest race remains
  unfixed). AC11 files three new MINOR BACKLOG entries (R1-08 empty
  wiki_pages, R1-10 backtick source_ref, R1-11 weaker filename
  validation) and one new MEDIUM (Q8 — `sanitize.py` UNC slash-
  normalize gap, the spawn cost of closing AC1+AC2). One Q8 test marked
  `pytest.mark.xfail(strict=True)` per cycle-16 L3 REPL probe — when
  the helper is fixed, removing the marker forces the strict-pass flip.
  Step-2 CVE baseline showed 4 existing advisories (diskcache, ragas,
  pip, litellm) all deferred per existing BACKLOG mitigation; Step-11
  PR-CVE diff returns empty (zero new dependencies introduced — no
  imports added beyond the already-imported `_sanitize_error_str`
  helper). R1 Opus design-eval (4.9/5 avg, PROCEED) + R1 Codex (5
  MAJOR + 6 MINOR, APPROVE-WITH-FIXES) → Step 5 decision gate folded
  in 12 question outcomes via 7 AC amendments before Step 9.
  Revert-fail discipline (cycle-24 L4) verified — `git stash` on
  `src/kb/mcp/core.py` produces 6 of 7 integration-test failures.
- Detail: [history archive](CHANGELOG-history.md#2026-04-25-cycle-33)

#### 2026-04-25 — cycle 32

- Items: 8 AC / 2 src (`cli.py`, `utils/io.py`) + 1 new test file / 10 commits (9 feat+docs+fix + 1 self-review)
- Tests: 2882 → 2901 (+19; Step 14 R1 Codex MAJOR 2 added stagger-integration pin)
- Scope:
  Closes CLI ↔ MCP parity category (b) — AC1/AC2 add `compile-scan`
  thin-wrapper over `kb_compile_scan` and AC4/AC5 add
  `ingest-content` over `kb_ingest_content` (both via the cycle
  27+ function-local-import pattern; `--incremental/--no-incremental`
  boolean flag pair matches cycle 15 `kb publish` precedent; Click
  `click.Path(exists=True, file_okay=False)` for `--wiki-dir`;
  Click `click.File("r", lazy=False, encoding="utf-8")` for
  `--content-file` + `--extraction-json-file` with native `-` stdin
  support per Context7-verified Click 8.3 semantics). AC3 widens
  `_is_mcp_error_response` tuple to include `"Error["` prefix,
  closing a silent-exit-0 bug where `kb_ingest_content`'s
  post-create OSError path (`Error[partial]: write to ... failed`
  at `mcp/core.py:762`) would have routed to stdout + exit 0 under
  the cycle-31 three-tuple; docstring updated with the full
  emitter map. AC6/AC7 add `utils/io.py` fair-queue stagger
  mitigation — module-level `_LOCK_WAITERS` counter guarded by
  `threading.Lock`, incremented via `_take_waiter_slot()` (0-based
  position snapshot) on entry to `file_lock` retry loop and
  decremented via `_release_waiter_slot()` in the outermost
  `finally` (C3 symmetry across success / TimeoutError /
  KeyboardInterrupt); first-sleep stagger is
  `position * _FAIR_QUEUE_STAGGER_MS / 1000` clamped to
  `LOCK_POLL_INTERVAL=50ms` (C11 prevents double-compounding with
  exponential backoff); position=0 → zero stagger so uncontended
  N=1 acquire sees no latency change; `_release_waiter_slot`
  emits `logger.warning` on underflow (C14, post-R1 Opus AMEND)
  instead of silently clamping to zero so counter drift surfaces
  to operators. AC8 doc sync updates CLI count 22 → 24 and
  deletes the BACKLOG fair-queue entry (lines 125-126) since AC6
  resolves it as a mitigation. Step-2 CVE baseline showed 2 open
  no-upstream-fix advisories (diskcache, ragas); Step-11 PR-CVE
  diff surfaced 3 mid-cycle arrivals per cycle-22 L4: litellm
  GHSA-xqmj-j6mv-4862 + GHSA-r75f-5x8p-qvmc (patched at 1.83.7
  but blocked by click<8.2 transitive — narrow-role exception
  documented in BACKLOG since zero runtime imports in `src/kb/`),
  python-dotenv CVE-2026-28684 (fixed via 1.1.1 → 1.2.2 already
  pinned in requirements.txt), pip CVE-2026-3219 (no upstream fix
  yet — tooling-only narrow-role). R1 Opus AMEND verdict (AC5
  add --use-api test, AC6 observable-warning on underflow, AC8
  explicit T11 BACKLOG filing); R2 Codex design-eval stopped
  past 12 min hang (cycle-20 L4) — primary-session manual
  verify caught `core.py:535` misread of `MAX_INGEST_CONTENT_CHARS*4`
  as a JSON-overhead ratio (actually UTF-8 bytes-per-char
  upper bound). Step 5 Opus decision gate hung past 10 min;
  primary-session synthesis per cycle-20 L4 fallback. Step 8
  Codex plan-gate hung past 8 min; primary-session self-review
  per cycle-21 L1 inline-resolve (all conditions grep-verifiable,
  no code-exploration gaps).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-32-2026-04-25)

#### 2026-04-25 — cycle 31

- Items: 8 AC / 1 src (`cli.py`) + 1 new test file / 9 commits (post-merge backfill per cycle-30 L1)
- Tests: 2850 → 2882 (+32)
- Scope:
  Continues cycle-27/30 CLI ↔ MCP parity — AC1-AC3 add
  `read-page` / `affected-pages` / `lint-deep` thin-wrappers
  over the three page_id-input MCP tools (`kb_read_page`,
  `kb_affected_pages`, `kb_lint_deep`). These tools emit
  heterogeneous error-prefix shapes (`"Error:"` colon-form,
  `"Error <verb>..."` space-form runtime-exception shapes, and
  the unique `"Page not found:"` logical-miss from `kb_read_page`),
  so AC4 introduces a shared `_is_mcp_error_response(output)`
  discriminator near `_error_exit` that classifies by first-line
  prefix only against the three shapes (Q1; first-line split
  prevents misfire on page bodies containing `Error:` on line 2;
  empty / blank-first-line outputs stay exit-0 to preserve MCP
  parity for zero-length page bodies). AC5 pins body-spy tests
  per subcommand (patching the OWNER module `kb.mcp.browse` /
  `kb.mcp.quality` — NOT `kb.cli` — because function-local
  imports resolve at call time per cycle-30 L2). AC6 adds
  traversal-boundary tests (`".."` → validator colon-form error)
  PLUS non-colon boundary tests per subcommand (`Page not found:`
  for read-page; forced `build_backlinks` / `build_fidelity_context`
  exceptions for affected-pages / lint-deep) — revert-divergent
  by construction: the tests flip `exit_code` from 1 to 0 if the
  discriminator reverts to `startswith("Error:")`. Q3 parity
  tests exercise both channels (direct MCP call + CLI invocation)
  with strict stream semantics (`stdout == mcp_output + "\n"` on
  success, `stderr == mcp_output + "\n"` + exit 1 on error;
  `CliRunner()` alone suffices on Click 8.3+ since `mix_stderr`
  was removed in 8.2). AC8 closes a pre-existing silent-failure
  bug latent since cycles 27 (`stats`) and 30 (`reliability-map`,
  `lint-consistency`): all three legacy wrappers wrap MCP tools
  that also emit non-colon runtime-error shapes, so AC8
  retrofits them to `_is_mcp_error_response` (one-line swap each
  plus 3 regression tests). T6 boot-lean pinned by subprocess
  probe asserting `import kb.cli` doesn't transitively pull
  `kb.mcp.browse` / `kb.mcp.quality`. AC7 BACKLOG hygiene —
  remove cluster (b) from the CLI↔MCP parity bullet; narrow
  "~12 remaining" to "~9 remaining" (7 write-path + 2 ingest/
  compile variants). Step-2 CVE baseline + Step-11 branch diff
  show identical 2 open no-upstream-fix CVEs (diskcache + ragas)
  — Step 11.5 no-op. R1 Opus APPROVE-WITH-AMENDS; R2 Codex AMEND
  (discovered the pre-existing silent-failure bug — scope
  expanded to AC8 via Step-5 Q4 Option A); Step 5 APPROVE; Step 8
  plan-gate REJECT resolved inline per cycle-21 L1.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-31-2026-04-25)

#### 2026-04-25 — cycle 30

- Items: 7 AC / 2 src + 2 new test files / 12 commits
- Tests: 2826 → 2850 (+24)
- Scope:
  Pre-Phase-5 backlog hygiene — AC1 `_audit_token` caps
  `block["error"]` at 500 chars via `kb.utils.text.truncate`
  (truthiness-guarded: `None`/empty skips the cap and keeps the
  bare `"cleared"`/`"unknown"` token; R2-A2 amendment) so a
  pathological `OSError.__str__()` on Windows can't bloat
  `wiki/log.md` or `kb rebuild-indexes` CLI stdout. AC2-AC6
  extend cycle-27's CLI ↔ MCP parity with 5 read-only
  subcommands — `graph-viz` (`--max-nodes` help text documents
  "1-500; 0 rejected" per R1 Opus amendment), `verdict-trends`,
  `detect-drift`, `reliability-map` (zero args; "No feedback
  recorded yet" exits 0), `lint-consistency` (`--page-ids`
  forwarded raw; no `--wiki-dir` since the MCP tool signature
  omits it). All 5 wrappers use the cycle-27 thin-wrapper
  pattern (function-local import + forward args raw +
  `"Error:"`-prefix contract + `_error_exit(exc)` wrap). AC7
  BACKLOG hygiene — delete cycle-29 audit-cap MEDIUM entry +
  narrow CLI↔MCP parity from "~14 remaining" to "~12 remaining"
  (R2-A3 arithmetic correction + `kb_save_synthesis` non-tool
  call-out); skip no-op CVE re-verify (diskcache + ragas
  identical cycle-29 baseline, same-day). R2 Codex stalled
  ~14min; primary-session R2 fallback per cycle-20 L4 then
  R2 findings folded in via DESIGN-AMEND.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-30-2026-04-25)

#### 2026-04-24 — cycle 29

- Items: 5 AC / 3 src + 2 new test files / 6 commits
- Tests: 2809 → 2826 (+17)
- Scope:
  Backlog-by-file hygiene cycle. AC1 `_audit_token(block)` helper in
  `compile/compiler.py` replaces the inline audit ternary so a partial
  vector clear (main `unlink()` succeeded + sibling `.tmp` unlink failed)
  renders `vector=cleared (warn: tmp: <msg>)` instead of swallowing the
  error tail; mirrored to `kb rebuild-indexes` CLI stdout via function-
  local import in `cli.py` (cycle-23 AC4 boot-lean preserved); Q3
  embedded-newline regression pins the `append_wiki_log` sanitizer
  contract. AC2 `_validate_path_under_project_root(path, field_name)`
  helper applies the dual-anchor `PROJECT_ROOT` containment (literal-abs
  + `.resolve()` target both under root) to `hash_manifest` + `vector_db`
  overrides of `rebuild_indexes`; void-return helper (cycle-23 L2) with
  explicit empty-path reject (cycle-19 L3); wiki_dir block refactored to
  use the same helper so all 3 sites share one contract. AC3 architectural
  carve-out comment above `CAPTURES_DIR = RAW_DIR / "captures"` (5 lines,
  mirrors CLAUDE.md §raw/ language) + deletes stale `config.py:40-53`
  BACKLOG bullet (Q13 expansion — BACKLOG lifecycle). AC4 deletes stale
  `_PROMPT_TEMPLATE inline string` BACKLOG bullet (shipped cycle-19 AC15
  via lazy `_get_prompt_template()`). AC5 deletes stale Phase 4.5 HIGH #6
  cold-load bullet ("0.81s + 67 MB RSS delta") — shipped cycle-26 AC1-AC5
  warm-load + cycle-26/28 observability; HIGH-Deferred summary with the
  true residual (dim-mismatch AUTO-rebuild) survives. Step-11 T1 PARTIAL
  (unbounded `OSError.__str__()` → `wiki/log.md` + CLI stdout) filed as
  new MEDIUM BACKLOG entry per cycle-12 L3. Dep-CVE baseline 2026-04-24:
  diskcache + ragas both `fix_versions: []`, unchanged; PR-introduced
  diff empty.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-29-2026-04-24)

#### 2026-04-24 — cycle 28

- Items: 9 AC / 2 src + 1 new test file / 7 commits
- Tests: 2801 → 2809 (+8)
- Scope:
  First-query observability completion — `VectorIndex._ensure_conn`
  sqlite-vec extension load and `BM25Index.__init__` corpus indexing
  (closes HIGH-Deferred sub-item (b), cycle-26 Q16 follow-up). AC1/AC2/AC3:
  `SQLITE_VEC_LOAD_WARN_THRESHOLD_SECS=0.3` module constant +
  `_sqlite_vec_loads_seen` counter (exact, inside `_conn_lock`) +
  `get_sqlite_vec_load_count()` getter; INFO log always on successful
  extension load + WARNING above 0.3s; post-success ordering (NO
  `finally:` wraps the log/counter — defended by
  `test_sqlite_vec_load_no_info_on_failure_path`). AC4/AC5: lock-free
  `_bm25_builds_seen` counter (aggregates `engine.py:110` wiki +
  `engine.py:794` raw call sites — "constructor executions, NOT distinct
  cache insertions" per Q11) + `get_bm25_build_count()` getter; INFO
  log on every `BM25Index.__init__` including empty-corpus (no WARN
  threshold — corpus-size variance defeats a fixed threshold). AC6:
  8 regression tests. AC7: BACKLOG hygiene — narrow HIGH-Deferred entry
  (sub-item b landed), delete MEDIUM AC17-drop rationale line (duplicate
  of CHANGELOG-history cycle-13 AC2), delete resolved LOW cycle-27
  commit-tally entry. AC8: CHANGELOG format-guide commit-count rule
  codified (self-referential +1 per cycle-26 L1 skill patch). AC9:
  no-op CVE re-verify, matches cycle-26 baseline (diskcache + ragas
  still no upstream fix).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-28-2026-04-24)

#### 2026-04-24 — cycle 27

- Items: 7 AC / 2 src + 1 new test file / 3 commits
- Tests: 2790 → 2801 (+11)
- Scope:
  CLI ↔ MCP parity — 4 new read-only CLI subcommands (`kb search`,
  `kb stats`, `kb list-pages`, `kb list-sources`) wrapping existing MCP
  browse tools with function-local imports (AC1/AC2/AC3/AC4 — preserves
  cycle-23 AC4 boot-lean contract). AC1b extracts `_format_search_results`
  helper from `kb_search` body so CLI reuses identical formatter without
  duplication. AC5: 7 regression tests (4 `--help` smoke + empty-query
  non-zero-exit + 2 helper semantics). AC6 narrows BACKLOG CLI↔MCP parity
  entry (18 → 14 remaining tools). AC7 skip-on-no-diff CVE re-verify
  (pip-audit matches cycle-26 baseline, same-day noise avoidance).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-27-2026-04-24)

#### 2026-04-24 — cycle 26

- Items: 8 AC (+AC2b) / 2 src + 1 new test file + 1 extended cycle-23 test / 7 commits
- Tests: 2782 → 2790 (+8)
- Scope:
  Vector-model cold-load observability — new `maybe_warm_load_vector_model(wiki_dir)`
  daemon-thread warm-load hook wired into `kb.mcp.__init__.main()` after tool
  registration, before stdio loop (AC1/AC2); boot-lean allowlist extension pins
  function-local import contract (AC2b); `_get_model()` instrumented with
  `time.perf_counter` — INFO log always on cold-load + WARNING above
  `VECTOR_COLD_LOAD_WARN_THRESHOLD_SECS=0.3s` (AC3); module-level
  `_vector_model_cold_loads_seen` counter + `get_vector_model_cold_load_count()`
  getter, exact counts inside `_model_lock` (AC4 — intentional asymmetry
  vs cycle-25 lock-free `_dim_mismatches_seen`, documented in getter docstring);
  seven regression tests including subprocess sys.modules probe + exception-
  swallow pin (AC5); BACKLOG hygiene — delete stale multiprocessing file_lock
  entry (AC6 — resolved by cycle-23 AC7), skip no-op CVE re-stamp (AC7 —
  pip-audit matches cycle-25 baseline), narrow HIGH-Deferred vector-index
  lifecycle entry + add Q16 follow-up (AC8).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-26-2026-04-24)

#### 2026-04-24 — cycle 25

- Items: 10 AC / 2 src + 3 new test files / 6 commits
- Tests: 2768 → 2782 (+14)
- Scope:
  `rebuild_indexes` also unlinks `<vec_db>.tmp` sibling (AC1/AC2 —
  cycle-24 R2 Codex follow-up); vector-index dim-mismatch warning now
  includes operator remediation command + module-level observability
  counter (AC3/AC4/AC5 — HIGH-Deferred sub-item 3 narrow-scope shipped,
  auto-rebuild remains deferred); `compile_wiki` emits `in_progress:{hash}`
  pre-markers before each `ingest_source`, stale-marker entry scan on
  next invocation warns per-source, full-mode prune exempts in_progress
  values (AC6/AC7/AC8 + CONDITION 13 — MEDIUM M2 narrow observability
  variant); BACKLOG + diskcache/ragas CVE 2026-04-24 re-verify (AC9/AC10).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-25-2026-04-24)

#### 2026-04-23 — cycle 24

- Items: 15 AC / 4 src + 5 new test files / 9 commits
- Tests: 2743 → 2768 (+25)
- Scope:
  Evidence-trail inline render at first write + StorageError on update-path
  evidence failure (AC1/AC2); `append_evidence_trail` sentinel search
  section-span-limited against attacker-planted body sentinels (AC14/AC15);
  vector-index atomic rebuild via `<vec_db>.tmp` + `os.replace` with
  cache-pop+close before replace and crash-cleanup (AC5/AC6/AC7/AC8);
  `file_lock` exponential backoff across all 3 polling sites with
  `LOCK_POLL_INTERVAL` as CAP (AC9/AC10); BACKLOG cleanup +
  diskcache/ragas CVE re-verification (AC11/AC12/AC13).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-24-2026-04-23)

#### 2026-04-23 — cycle 23

- Items: 8 AC / 6 src + 4 new tests / 6 commits
- Tests: 2725 → 2743 (+18)
- Scope:
  MCP boot-leanness via PEP-562 lazy shim (cycle-19 AC15 contract preserved),
  `rebuild_indexes` helper + `kb rebuild-indexes` CLI for clean-slate recompiles,
  hermetic ingest→query→lint E2E coverage, and cross-process `file_lock`
  regression (Phase 4.5 HIGH-Deferred).
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-23-2026-04-23)

#### 2026-04-22 — cycle 22

- Items: 14 AC / 3 src + 2 new tests / 11 commits
- Tests: 2720 → 2725 (+5; 1 Windows-skip)
- Scope:
  Pre-Phase-5 backlog hardening: wiki-path ingest guard, universal extraction grounding clause,
  behavioural prompt test rewrite, stale BACKLOG cleanup, and lxml CVE pin bump.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-22-2026-04-22)

#### 2026-04-21 — cycle 21

- Items: 30 AC / 4 src / 1 commit
- Tests: 2697 → 2710 (+13)
- Scope:
  CLI subprocess backend for 8 local AI tools, with env-var routing, JSON extraction, per-backend
  concurrency limits, secret redaction, and Anthropic path compatibility.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-21-2026-04-21)

#### 2026-04-21 — cycle 20

- Items: 21 AC / 10 src / 13 commits
- Tests: 2639 → 2697 (+58)
- Scope:
  Error taxonomy, slug-collision O_EXCL hardening, locked page updates, stale-refine sweep/list
  tools, CLI/MCP refine surfaces, and Windows tilde-path regression coverage.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-20-2026-04-21)

#### 2026-04-21 — cycle 19

- Items: 23 AC / 6 src / 9 commits
- Tests: 2592 → 2639 (+47)
- Scope:
  Batch wikilink injection, manifest-key consistency, refine two-phase writes, stale-pending
  visibility, MCP monkeypatch migration, and reload-leak fixes.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-19-2026-04-21)

#### 2026-04-21 — cycle 18

- Items: 16 AC / 5 src / 6 commits
- Tests: 2548 → 2592 (+44)
- Scope:
  Structured ingest audit log, locked wikilink injection, log rotation under lock, UNC sanitization,
  index-file helper, HASH_MANIFEST test redirection, and e2e workflow coverage.
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-18-2026-04-21)

#### 2026-04-20 — cycle 17

- Items: 16 AC / 11 src / 14 commits
- Tests: 2464 → 2548 (+84)
- Scope:
  manifest lock symmetry, capture two-pass, lint augment resume, shared run-id validator, MCP lazy
  imports (narrowed), thin-tool coverage
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-17-2026-04-20)

#### 2026-04-20 — cycle 16

- Items: 24 AC / 8 src / 14 commits
- Tests: 2334 → 2464 (+130)
- Scope:
  enrichment targets, query rephrasings, duplicate-slug + inline-callout lint, kb_query `save_as`,
  per-page siblings + sitemap publish
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-16-2026-04-20)

#### 2026-04-20 — cycle 15

- Items: 26 AC / 6 src / 7 commits
- Tests: 2245 → 2334 (+89)
- Scope:
  authored-by boost, source volatility, per-source decay, incremental publish, lint decay/status
  wiring
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-15-2026-04-20)

#### 2026-04-20 — cycle 14

- Items: 21 AC / 9 src / 8 commits
- Tests: 2140 → 2235 (+95)
- Scope:
  Epistemic-Integrity 2.0 vocabularies, coverage-confidence refusal gate, `kb publish` module
  (/llms.txt, /llms-full.txt, /graph.jsonld), status ranking boost
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-14-2026-04-20)

#### 2026-04-20 — cycle 13

- Items: 8 AC / 5 src / 7 commits
- Tests: 2119 → 2131 (+12)
- Scope:
  frontmatter migration to cached loader, CLI boot `sweep_orphan_tmp`, `run_augment` raw_dir
  derivation
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-13-2026-04-20)

#### 2026-04-19 — cycle 12

- Items: 17 AC / 13 src / 11 commits
- Tests: 2089 → 2118 (+29)
- Scope:
  conftest fixture, io sweep, `KB_PROJECT_ROOT`, LRU frontmatter cache, `kb-mcp` console script
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-12-2026-04-19)

#### 2026-04-19 — cycle 11

- Items: 14 AC / 14 src / 13 commits
- Tests: 2041 → 2081 (+40)
- Scope:
  ingest coercion, comparison/synthesis reject, page-helper relocation, CLI import smoke,
  stale-result edges
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-11-2026-04-19)

#### 2026-04-18 — cycle 10

- Items: 14 AC / 10 src
- Tests: 2004 → 2041 (+37)
- Scope:
  MCP `_validate_wiki_dir` rollout, `kb_affected_pages` warnings, `VECTOR_MIN_SIMILARITY` floor,
  capture hardening
- Detail: [history archive](CHANGELOG-history.md#backlog-by-file-cycle-10-2026-04-18)

#### 2026-04-18 — cycle 9

- Items: 30 AC / 14 src
- Tests: 1949 → 2003 (+54)
- Scope:
  wiki_dir isolation across query/MCP, LLM redaction, env-example docs, lazy ingest export
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-9-2026-04-18)

#### 2026-04-18 — cycle 8

- Items: 30 AC / 19 src
- Tests: 1919 → 1949 (+30)
- Scope:
  model validators, LLM telemetry, PageRank → RRF list, contradictions idempotency, pip toolchain
  CVE patch
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-8-2026-04-18)

#### 2026-04-18 — cycle 7

- Items: 30 AC / 22 src
- Tests: 1868 → 1919 (+51)
- Scope:
  `_safe_call` helper, MCP error-path sanitization, Evidence Trail convention, many
  lint/query/ingest refinements
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-7-2026-04-18)

#### 2026-04-18 — cycle 6

- Items: 15 AC / 14 src
- Tests: 1836 → 1868 (+32)
- Scope:
  PageRank cache, vector-index reuse, CLI `--verbose`, hybrid rrf tuple storage, graph
  `include_centrality` opt-in
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-6-2026-04-18)

#### 2026-04-18 — cycle 5 redo

- Items: 6 AC / 6 src
- Tests: 1821 → 1836 (+15)
- Scope:
  pipeline retrofit for Steps 2/5 artifacts; citation format symmetry, page-id SSOT,
  purpose-sentinel coverage
- Detail: [history archive](CHANGELOG-history.md#phase-45--cycle-5-redo-hardening-2026-04-18)

#### 2026-04-18 — cycle 5

- Items: 14 AC / 13 src
- Tests: 1811 → 1820 (+9)
- Scope:
  `wrap_purpose` sentinel, pytest markers, verdicts/config consolidation, `_validate_page_id`
  control-char reject
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-5-2026-04-18)

#### 2026-04-18 — PR #17 concurrency

- Items: 3 files
- Tests: 1810 → 1811 (+1)
- Scope:
  `_VERDICTS_WRITE_LOCK` fix + capture docstring clarity; CHANGELOG split into active vs history
- Detail: [history archive](CHANGELOG-history.md#concurrency-fix--docs-tidy-pr-17-2026-04-18)

#### 2026-04-17 — cycle 4

- Items: 22 AC / 16 src
- Tests: 1754 → 1810 (+56)
- Scope:
  `_rel()` path-leak sweep, `<prior_turn>` sentinel sanitizer, kb_read_page cap, rewriter CJK gate,
  BM25 postings index
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-4-2026-04-17)

#### 2026-04-17 — cycle 3

- Items: 24 AC / 16 src
- Tests: 1727 → 1754 (+27)
- Scope:
  `LLMError.kind` taxonomy, vector dim guard + lock, stale markers in context, hybrid catch-degrade,
  inverted-postings consistency
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-3-2026-04-17)

#### 2026-04-17 — cycle 2

- Items: 30 AC / 19 src
- Tests: 1697 → 1727 (+30)
- Scope:
  hashing CRLF normalization, file_lock hardening, rrf metadata merge, extraction schema deepcopy
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-2-2026-04-17)

#### 2026-04-17 — cycle 1

- Items: 38 AC / 18 src
- Tests: → 1697
- Scope:
  pipeline wiki/raw dir plumbing, augment rate/manifest scoping, capture secret patterns, 3-round PR
  review pattern established
- Detail: [history archive](CHANGELOG-history.md#phase-45--backlog-by-file-cycle-1-2026-04-17)

#### 2026-04-17 — HIGH cycle 2

- Items: 22 / 16 src
- Tests: → 1645
- Scope:
  frontmatter regex cap, orphan-graph copy, semantic inverted index, trends UTC-aware timestamps
- Detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-2-2026-04-17)

#### 2026-04-16 — HIGH cycle 1

- Items: 22 / multi
- Tests: → baseline
- Scope:
  RMW locks across refiner/evidence/wiki_log, hybrid vector-index lifecycle, error-tag categories
- Detail: [history archive](CHANGELOG-history.md#phase-45--high-cycle-1-2026-04-16)

#### 2026-04-16 — CRITICAL docs-sync

- Items: 2
- Tests: 1546 → 1552
- Scope:
  version-string alignment + `scripts/verify_docs.py` drift check
- Detail: [history archive](CHANGELOG-history.md#phase-45--critical-cycle-1-docs-sync-2026-04-16)

> Older released-version history is also archived in [CHANGELOG-history.md](CHANGELOG-history.md).

---
