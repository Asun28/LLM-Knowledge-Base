"""AC4 + AC5 meta-tests for the cycle-64 autouse path-sandbox fixture.

AC4 — structural test that the autouse decorator is present
AC4-bis — behavioural test that paths are actually redirected
AC5 — sys.modules walk replaces hardcoded cache_clear list
"""

import ast
import sys
import types
from functools import lru_cache
from pathlib import Path

from tests._helpers.ast_walk import find_function_def


def test_autouse_decorator_present_structural() -> None:
    """AC4 — Assert _autouse_kb_path_sandbox has @pytest.fixture(autouse=True)."""
    conftest_path = Path("tests/conftest.py")
    func_def = find_function_def(conftest_path, "_autouse_kb_path_sandbox")

    assert func_def is not None, f"Function _autouse_kb_path_sandbox not found in {conftest_path}"

    # Check for @pytest.fixture decorator with autouse=True keyword
    found_autouse = False
    for dec in func_def.decorator_list:
        if isinstance(dec, ast.Call):
            # @pytest.fixture(autouse=True) style
            if isinstance(dec.func, ast.Attribute) and dec.func.attr == "fixture":
                # Check for autouse=True keyword argument
                for kw in dec.keywords:
                    if kw.arg == "autouse" and isinstance(kw.value, ast.Constant):
                        if kw.value.value is True:
                            found_autouse = True
                            break

    assert found_autouse, (
        f"@pytest.fixture(autouse=True) not found on _autouse_kb_path_sandbox "
        f"at {conftest_path}:{func_def.lineno}. "
        f"Decorators: {[ast.dump(d) for d in func_def.decorator_list]}"
    )


def test_autouse_decorator_redirects_paths_behavioural(
    tmp_kb_env: Path,
) -> None:
    """AC4-bis — Behavioural test: autouse fixture actually redirects kb.config paths.

    Uses the tmp_kb_env fixture (which depends on the autouse fixture) and
    verifies that kb.config.WIKI_DIR is redirected to a tmp path, proving
    the autouse fixture actually redirects paths at runtime.
    """
    import kb.config

    # The tmp_kb_env fixture applies the autouse fixture's monkeypatches,
    # which redirect kb.config.WIKI_DIR and other paths to tmp_path.
    # Verify that WIKI_DIR is NOT the real repo's wiki directory.
    wiki_dir = kb.config.WIKI_DIR
    real_repo_wiki = Path(__file__).parent.parent / "wiki"

    assert wiki_dir != real_repo_wiki, (
        f"WIKI_DIR was not redirected by autouse fixture. "
        f"Expected tmp path, got real repo path: {wiki_dir}"
    )


def test_lru_cache_walk_clears_kb_modules() -> None:
    """AC5 — sys.modules walk clears @lru_cache decorated functions in kb modules.

    Stubs a fake kb._test_path_sensitive_module with an @lru_cache function,
    populates the cache, then simulates the autouse fixture teardown and verifies
    the cache was cleared.
    """
    # Create a fake module with an lru_cache function
    test_mod = types.ModuleType("kb._test_path_sensitive_module")

    @lru_cache(maxsize=32)
    def fake_cached_func(x: int) -> int:
        return x * 2

    # Populate the cache
    fake_cached_func(42)
    assert fake_cached_func.cache_info().currsize == 1, "Cache should have 1 entry"

    # Register the module temporarily
    sys.modules["kb._test_path_sensitive_module"] = test_mod
    test_mod.fake_cached_func = fake_cached_func

    try:
        # Simulate the sys.modules walk that the autouse fixture does
        for mod_name, mod in list(sys.modules.items()):
            if mod_name.startswith("kb.") and mod is not None:
                for attr_name, attr_value in vars(mod).items():
                    if callable(attr_value):
                        cache_clear = getattr(attr_value, "cache_clear", None)
                        if callable(cache_clear):
                            try:
                                cache_clear()
                            except Exception:
                                # Some objects may have cache_clear that raises
                                pass

        # Verify the test module's cache was cleared
        assert fake_cached_func.cache_info().currsize == 0, (
            "Cache should be empty after sys.modules walk"
        )
    finally:
        # Clean up
        del sys.modules["kb._test_path_sensitive_module"]


# -- Cycle 94 fold from test_v070.py (tmp_kb_env fixture coverage) --


# ── 9. tmp_kb_env fixture coverage (cycle 51 fold from test_cycle12_conftest.py) ─


def _is_under(path: Path, base: Path) -> bool:
    return path.resolve().is_relative_to(base.resolve())


def test_tmp_kb_env_rebinds_preimported_config_consumers(request):
    import kb.capture as capture
    import kb.config as config
    import kb.mcp.browse as browse
    import kb.mcp.core as core

    original_source_keys = tuple(config.SOURCE_TYPE_DIRS)

    project = request.getfixturevalue("tmp_kb_env")
    raw = project / "raw"

    for module in (config, core, browse, capture):
        assert _is_under(module.PROJECT_ROOT, project)

    for module in (config, core, browse):
        assert _is_under(module.RAW_DIR, project)

    for module in (config, browse):
        assert _is_under(module.WIKI_DIR, project)

    assert _is_under(config.CAPTURES_DIR, project)
    assert _is_under(capture.CAPTURES_DIR, project)

    assert tuple(config.SOURCE_TYPE_DIRS) == original_source_keys
    assert tuple(core.SOURCE_TYPE_DIRS) == original_source_keys
    for source_dir in config.SOURCE_TYPE_DIRS.values():
        assert _is_under(source_dir, raw)
    for source_dir in core.SOURCE_TYPE_DIRS.values():
        assert _is_under(source_dir, raw)

    assert _is_under(capture._CAPTURES_DIR_RESOLVED, project)
    assert _is_under(capture._captures_resolved, project)
    assert _is_under(capture._project_resolved, project)


# Cycle 64 AC1/AC3: `test_tmp_kb_env_is_not_autouse` deleted — its contract
# (tmp_kb_env path patches must NOT apply unless explicitly requested) was
# deliberately reversed by cycle 64. The autouse `_autouse_kb_path_sandbox`
# fixture now redirects `kb.config.WIKI_*` / `RAW_*` / `PROJECT_ROOT` for
# every test by default. Replacement coverage lives in
# `tests/test_cycle64_conftest_leak.py::test_default_isolation_redirects_wiki_constants_to_tmp`
# (asserts the FORWARD contract: config.PROJECT_ROOT != real_project_root
# under default pytest invocation). Per cycle-15 L2 / cycle-44 L4 DROP-with-
# test-anchor, the deletion is safe because replacement coverage is in
# place.


# -- Cycle 94 fold from test_v09_cycle5_fixes.py (pytest marker registration in pyproject) --


def test_pytest_markers_registered():
    import tomllib
    from pathlib import Path

    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    markers = data["tool"]["pytest"]["ini_options"]["markers"]

    assert "slow: marks tests as slow (deselect with '-m not slow')" in markers
    assert "network: marks tests requiring network access" in markers
    assert "integration: marks integration tests requiring real filesystem or DB" in markers
    assert "llm: marks tests that invoke a real LLM API" in markers
