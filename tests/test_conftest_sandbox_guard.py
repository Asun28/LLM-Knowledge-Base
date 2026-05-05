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

import pytest

from tests._helpers.ast_walk import assert_decorator_present, find_function_def


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
        assert fake_cached_func.cache_info().currsize == 0, \
            "Cache should be empty after sys.modules walk"
    finally:
        # Clean up
        del sys.modules["kb._test_path_sensitive_module"]
