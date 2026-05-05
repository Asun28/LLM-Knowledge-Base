"""Cycle 65 AC1: Test PROJECT_ROOT call-time accessor (C1)."""

from pathlib import Path

import kb.config


class TestProjectRootCallTime:
    """Verify kb.config.get_project_root() reads KB_PROJECT_ROOT at call time."""

    def test_get_project_root_call_time_accessor(self, monkeypatch, tmp_path):
        """C1: get_project_root() reads KB_PROJECT_ROOT at call time.

        Tests the accessor function directly, which must read env at CALL TIME
        per cycle-19 L2. This guards against the reload-leak hazard where env
        mutations after import are silently ignored.
        """
        # First call: set env to tmp_path
        monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
        result1 = kb.config.get_project_root()
        assert result1 == tmp_path.resolve()

        # Second call: mutation to a different env value
        another_tmp = tmp_path / "another"
        another_tmp.mkdir()
        monkeypatch.setenv("KB_PROJECT_ROOT", str(another_tmp))
        result2 = kb.config.get_project_root()
        assert result2 == another_tmp.resolve()

        # Verify they are different (env was re-read, not cached)
        assert result1 != result2, (
            "get_project_root() must re-read env on each call; "
            "got same result for different env values (reload-leak hazard)"
        )

    def test_kb_config_project_root_shim_back_compat(self, monkeypatch, tmp_path):
        """Test that kb.config.PROJECT_ROOT attribute access still works.

        The module-level PROJECT_ROOT binding (snapshot at import time) is
        retained for back-compat. Code that does `from kb.config import PROJECT_ROOT`
        gets the import-time snapshot. Code that accesses via attribute lookup
        (kb.config.PROJECT_ROOT) may use the shim if the dynamic access pattern
        is needed, but since PROJECT_ROOT is in the module dict, the shim
        doesn't fire for this attribute.
        """
        # The module-level PROJECT_ROOT is the import-time snapshot
        assert hasattr(kb.config, "PROJECT_ROOT")
        assert isinstance(kb.config.PROJECT_ROOT, Path)

    def test_reset_project_root_helper_exists(self):
        """Verify _reset_project_root() helper exists and is callable."""
        # Should not raise
        kb.config._reset_project_root()
