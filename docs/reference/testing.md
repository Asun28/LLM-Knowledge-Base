# Testing

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "Testing" section. Pairs with [error-handling.md](error-handling.md).

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:

- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (all `SOURCE_TYPE_DIRS` subdirs) for tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

Full suite: 3005 tests / 257 files (2985 passed + 20 skipped on Windows local; cycle 36 added 10 cycle-36 hardening tests + 10 `requires_real_api_key` skipif markers + 4 anti-POSIX skipif markers + cycle-23 multiprocessing CI=true skipif). New tests per cycle go in versioned files (e.g. `test_cycle36_ci_hardening.py`). Per-cycle test-file details → `CHANGELOG-history.md`.

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
