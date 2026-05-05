"""Cycle 66 AC3 — lru_cache regression tests for `_heuristic_walk_up_cached`.

Pins:
  - Q-7.3: cache_info().hits increments on second call with same cwd_str.
  - `_reset_project_root()` clears the cache (delta-based assertion).
  - `KB_PROJECT_ROOT` env shortcut does NOT increase cache size.
  - Module-level `PROJECT_ROOT` monkeypatch does NOT increase cache size via
    `get_project_root()`.
  - Different cwd_str values produce separate cache entries (cache key is cwd).

All tests use `kb.config.X` attribute access (NOT `from kb.config import X`)
per cycle-20 L1 reload-leak: sibling tests in the suite call
`importlib.reload(kb.config)`, which creates a NEW `_heuristic_walk_up_cached`
function with an empty cache. A `from`-imported name would snapshot the
old object and miss subsequent state. Late-bind everything via the module
reference so each call hits the current implementation.

Assertions are delta-based (compare currsize / hits before-and-after) rather
than absolute (`currsize == 0`) so background cache state from other suite
tests does not poison this file.
"""

import kb.config


class TestProjectRootCache:
    """Cycle-66 AC3 cache behaviour."""

    def setup_method(self):
        kb.config._reset_project_root()

    def teardown_method(self):
        kb.config._reset_project_root()

    def test_cache_hit_on_second_call(self, tmp_path):
        """Two calls with same cwd_str yield exactly one cache hit (Q-7.3)."""
        kb.config._heuristic_walk_up_cached(str(tmp_path))
        hits_before = kb.config._heuristic_walk_up_cached.cache_info().hits
        kb.config._heuristic_walk_up_cached(str(tmp_path))
        hits_after = kb.config._heuristic_walk_up_cached.cache_info().hits
        assert hits_after == hits_before + 1, (
            f"Expected cache hit on second call with same cwd_str; "
            f"hits before={hits_before}, hits after={hits_after}"
        )

    def test_reset_clears_cache(self, tmp_path):
        """`_reset_project_root()` empties the lru_cache."""
        kb.config._heuristic_walk_up_cached(str(tmp_path))
        size_after_call = kb.config._heuristic_walk_up_cached.cache_info().currsize
        assert size_after_call >= 1, "Cache must populate after a fresh call"
        kb.config._reset_project_root()
        size_after_reset = kb.config._heuristic_walk_up_cached.cache_info().currsize
        assert size_after_reset == 0, (
            f"_reset_project_root() must clear the cache; size after reset={size_after_reset}"
        )

    def test_env_override_bypasses_cache(self, monkeypatch, tmp_path):
        """`KB_PROJECT_ROOT` shortcuts in `_resolve_project_root` before the cache."""
        monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
        size_before = kb.config._heuristic_walk_up_cached.cache_info().currsize
        result = kb.config._resolve_project_root()
        size_after = kb.config._heuristic_walk_up_cached.cache_info().currsize
        assert result == tmp_path.resolve()
        assert size_after == size_before, (
            f"Cache size must not grow when KB_PROJECT_ROOT short-circuits; "
            f"before={size_before}, after={size_after}"
        )

    def test_module_binding_override_bypasses_cache(self, monkeypatch, tmp_path):
        """`PROJECT_ROOT` module monkeypatch shortcuts in `get_project_root` before the cache."""
        monkeypatch.delenv("KB_PROJECT_ROOT", raising=False)
        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
        size_before = kb.config._heuristic_walk_up_cached.cache_info().currsize
        result = kb.config.get_project_root()
        size_after = kb.config._heuristic_walk_up_cached.cache_info().currsize
        assert result == tmp_path
        assert size_after == size_before, (
            f"Cache size must not grow when PROJECT_ROOT binding short-circuits; "
            f"before={size_before}, after={size_after}"
        )

    def test_cwd_change_invalidates_cache(self, tmp_path):
        """Different cwd_str values produce separate cache entries (key includes cwd)."""
        cwd1 = tmp_path / "subdir_a"
        cwd1.mkdir()
        cwd2 = tmp_path / "subdir_b"
        cwd2.mkdir()
        size_before = kb.config._heuristic_walk_up_cached.cache_info().currsize
        kb.config._heuristic_walk_up_cached(str(cwd1))
        kb.config._heuristic_walk_up_cached(str(cwd2))
        size_after = kb.config._heuristic_walk_up_cached.cache_info().currsize
        assert size_after - size_before >= 2, (
            f"Expected at least 2 new cache entries (separate cwds); "
            f"size before={size_before}, size after={size_after}"
        )
        # Repeating cwd1 must hit the existing entry, proving cwd_str is the key.
        hits_before = kb.config._heuristic_walk_up_cached.cache_info().hits
        kb.config._heuristic_walk_up_cached(str(cwd1))
        hits_after = kb.config._heuristic_walk_up_cached.cache_info().hits
        assert hits_after == hits_before + 1, (
            f"Expected cache hit on cwd1 repeat; hits before={hits_before}, hits after={hits_after}"
        )
