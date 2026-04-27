# Testing

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "Testing" section. Pairs with [error-handling.md](error-handling.md).

Pytest with `testpaths = ["tests"]`, `pythonpath = ["src"]`. Fixtures in `conftest.py`:

- `project_root` / `raw_dir` / `wiki_dir` — point to real project directories (read-only use)
- `tmp_wiki(tmp_path)` — isolated wiki directory with all 5 subdirectories for tests that write wiki pages
- `tmp_project(tmp_path)` — full project directory with wiki/ (5 subdirs + log.md) and raw/ (all `SOURCE_TYPE_DIRS` subdirs) for tests
- `create_wiki_page` — factory fixture for creating wiki pages with proper frontmatter (parameterized: page_id, title, content, source_ref, page_type, confidence, updated, wiki_dir)
- `create_raw_source` — factory fixture for creating raw source files

Full suite: 3007 tests / 242 files (2996 passed + 11 skipped on Windows local; cycle 38 added 2 dual-site `mock_scan_llm` fixture-contract regression tests + unskipped 12 cycle-36 ubuntu-probe leftovers — 7 in `test_capture.py::TestCaptureItems` / `TestPipelineFrontmatterStrip` / `TestRoundTripIntegration`, 3 in `test_mcp_core.py::TestKbCaptureWrapper`, 2 in `test_capture.py::TestExclusiveAtomicWrite::test_cleans_up_*`; cycle 39 folded the cycle-38 cycle-tagged file into `test_capture.py::TestMockScanLlmReloadSafety` per cycle-4 L4 freeze-and-fold rule — file count 259 → 258, test count unchanged at 3014; cycle 40 folded three more cycle-10/11 files — `test_cycle10_safe_call.py` → `test_mcp_browse_health.py::TestSanitizeErrorStrAtMCPBoundary`, `test_cycle10_linker.py` SPLIT to `test_compile.py` + `test_utils_text.py` (both as bare functions per host shape), `test_cycle11_stale_results.py` → `test_query.py::TestFlagStaleResultsEdgeCases` — file count 258 → 255, test count unchanged at 3014; cycle 41 folded four more cycle-10/11 files — `test_cycle10_validate_wiki_dir.py` → `test_mcp_browse_health.py` (8 tests + helper), `test_cycle10_capture.py` → `test_capture.py` (4 tests), `test_cycle10_quality.py` → `test_mcp_quality_new.py` (2 tests), `test_cycle11_cli_imports.py` → `test_cli.py` (8 tests) — and replaced the C40-L3 docstring-grep `test_detect_source_drift_docstring_documents_deletion_pruning_persistence` with a behavior-based `test_detect_source_drift_does_not_mutate_manifest_when_sources_deleted` regression — file count 255 → 251, test count unchanged at 3014; cycle 43 folded eleven cycle-10/11/12/13 files — `test_cycle10_browse.py` → `test_mcp_browse_health.py`, `test_cycle10_extraction_validation.py` → `test_ingest.py`, `test_cycle10_vector_min_sim.py` → `test_query.py`, `test_cycle11_conftest_fixture.py` → `test_paths.py::TestTmpProjectFixtureContract`, `test_cycle11_ingest_coerce.py` → `test_ingest.py` (4-of-11 unique; 7 _coerce_str_field bare-function duplicates of cycle-43 AC2's parametrized fold dropped per cycle-17 L3), `test_cycle11_utils_pages.py` → `test_utils.py`, `test_cycle12_config_project_root.py` → `test_paths.py::TestProjectRootResolution` (autouse reload-isolation fixture per cycle-19 L2), `test_cycle12_frontmatter_cache.py` → `test_models.py` (1 vacuous-test flagged in BACKLOG), `test_cycle12_io_sweep.py` → `test_utils_io.py` (2 vacuous-tests flagged), `test_cycle13_augment_raw_dir.py` → `test_lint.py::TestRawDirDerivation`, `test_cycle13_sweep_wiring.py` → `test_cli.py::TestCliBootSweep` — file count 251 → 242, test count 3014 → 3007 (-7 from AC5 dedup). New tests per cycle go in versioned files (e.g. `test_cycle41_*.py`). Per-cycle test-file details → `CHANGELOG-history.md`.

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
