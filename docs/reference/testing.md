# Testing
<!-- FORMAT GUIDE
Purpose: Pytest layout, fixture rules, CI conventions, and snapshot workflow.
- Update "Full suite:" line each cycle with current test/file counts.
- Do NOT add per-cycle fold details here — those live in implementation-status.md.
- Add new fixture types to the "conftest.py" fixture list below.
- Add new CI conventions (new skipif markers, new timeout rules) to the "Cycle 36 conventions" section.
- Snapshot tests: update the "Snapshot Tests" section when new snapshot subjects are added.
-->

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "Testing" section. Pairs with [error-handling.md](error-handling.md).

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:

- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (all `SOURCE_TYPE_DIRS` subdirs) for tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

Full suite: **3134 tests · ~213 files** (3134 passed + 21 skipped on Windows local; cycle 65 HEAD). For cycle-by-cycle test-count changes and fold history see [implementation-status.md](implementation-status.md).

New tests per cycle go in versioned files (e.g. `test_cycle65_*.py`). Freeze-and-fold cadence (Phase 4.5 HIGH #4): once a cycle version ships, fold its versioned test file into the canonical module file with one commit per receiver, revert-verified per C40-L3. Per-cycle fold details → `CHANGELOG-history.md`.

## Cycle 36 conventions (2026-04-26)

**CI matrix strict gate.** `.github/workflows/ci.yml` runs on `[ubuntu-latest, windows-latest]` matrix with `continue-on-error: true` DROPPED from the pytest step. Marker mechanisms make this strict-gating safe across platforms:

- **`tests/_helpers/api_key.py::requires_real_api_key()`** — predicate gates SDK-using tests on dummy CI key (matches `sk-ant-dummy-key-` prefix per cycle 36 AC6). Use `@pytest.mark.skipif(not requires_real_api_key(), reason=...)` on tests that reach a real Anthropic SDK call. CI dummy key is documented at `.github/workflows/ci.yml:38` as `sk-ant-dummy-key-for-ci-tests-only`.
- **`pytest-timeout >= 2.3`** in `[dev]` extras + `[tool.pytest.ini_options] timeout = 120` global default. Per-test override via `@pytest.mark.timeout(N)` for legitimately-slow integration tests.
- **`@pytest.mark.skipif(sys.platform != "win32", reason="...")`** for tests asserting Windows path semantics (drive-letter abspath, `\` separator).
- **`@pytest.mark.skipif(os.name != "nt", reason="...")`** for Windows-helper tests with POSIX-incompatible cleanup behaviour (cycle-37 follow-up tracked).
- **`@pytest.mark.skipif(os.environ.get("CI") == "true", reason="...")`** on the cycle-23 cross-process file_lock test (Windows GHA spawn-bootstrap hang; local 1.03s pass).
- **WIKI_DIR mirror-rebind** (cycle-19 L1) — when a test patches `kb.review.refiner.WIKI_DIR` etc., also patch `kb.config.WIKI_DIR` to defend against future re-imports that capture the source snapshot. `test_mcp_phase2.py::_setup_project` now patches `kb.mcp.quality.WIKI_DIR` for the same reason.

## Fixture rules

Enforced by `test_cycle19_lint_redundant_patches.py` AST scan:

- Writing tests: use `tmp_wiki` / `tmp_project` / `tmp_kb_env` only — never touch the real `wiki/` or `raw/`.
- `tmp_kb_env` already redirects `kb.compile.compiler.HASH_MANIFEST` — do NOT also `monkeypatch.setattr` it.
- Patching the four migrated MCP callables (`ingest_source`, `query_wiki`, `search_pages`, `compute_trust_scores`): patch the OWNER MODULE (`kb.ingest.pipeline.ingest_source`), not `kb.mcp.core.*`.
- Tests that reach `sweep_stale_pending` / `list_stale_pending` via MCP or CLI: also `monkeypatch.setattr(kb.review.refiner.REVIEW_HISTORY_PATH, ...)` and `kb.mcp.quality.WIKI_DIR` defensively (mirror-rebind loop isn't guaranteed to hit post-fixture imports under every test ordering).

## Cycle 64 Test Sandbox

Cycle 64 adds an autouse path sandbox. `_autouse_kb_path_sandbox` redirects `kb.config.PROJECT_ROOT`, `RAW_*`, `WIKI_*`, capture/output/history paths, and `SOURCE_TYPE_DIRS` to per-test `tmp_path` by default. `project_root` / `raw_dir` / `wiki_dir` are sandbox-aware after this change.

Tests that genuinely need the real repository root must request `real_project_root` and run pytest with `--use-real-paths`. Do not bypass the autouse sandbox by importing `kb.config.PROJECT_ROOT` at module top in tests.

Explicit `tmp_kb_env` and its public alias `kb_sandbox` keep the patch+mkdir contract for tests that need a fully-built temporary project tree. `_kb_sandbox` remains as a compatibility alias.

Cycle 64 branch reference: 3036 passed + 18 skipped on Windows local. The new cycle-64 tests cover conftest sandboxing, vector dim-mismatch auto-rebuild, graph cache invalidation, compile auto-publish, publish-siblings manifest cleanup, and snapshots.

## Snapshot Tests

Cycle 64 introduced `syrupy>=4.6.0` under the `dev` extra and committed `tests/__snapshots__/test_cycle64_snapshots.ambr`. Snapshot subjects cover evidence-trail rendering, Mermaid export, and lint report structure.

Run ordinary snapshot tests with:

```bash
python -m pytest tests/test_cycle64_snapshots.py
```

After an intentional rendering-format change, update the committed snapshot with:

```bash
python -m pytest tests/test_cycle64_snapshots.py --snapshot-update
```

Never run `--snapshot-update` in CI. Review snapshot diffs like source code; they are the canonical expected rendering for the tested output surfaces.
