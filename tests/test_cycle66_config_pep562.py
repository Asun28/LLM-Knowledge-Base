"""Cycle 66 AC1: tests for `kb.config.__getattr__` after dead-branch removal.

The PEP 562 `__getattr__` hook in `kb.config` previously had two branches:
`PROJECT_ROOT` and `AUGMENT_ALLOWED_DOMAINS`. The `PROJECT_ROOT` branch was
dead — line 107 binds the name at module load, so attribute access
(`kb.config.PROJECT_ROOT`) returns the module-dict binding directly and the
PEP 562 hook never fires for that name. Cycle-66 AC1 deleted the dead
branch; the live route remains the `globals().get("PROJECT_ROOT")` shim
inside `get_project_root()` at line 70 (cycle-65 Step-12 fix).

Test design (IR-2 monkeypatch caveat):
- `monkeypatch.setattr(kb.config, "__getattr__", ...)` may not replace
  Python's special-method lookup for module-level `__getattr__`.
- Direct binding `kb.config.__getattr__ = new_fn` with explicit teardown
  is the reliable pattern; pytest's `monkeypatch` does not manage direct
  module-attribute rebindings, so we restore the original explicitly.

Closes T1 (test-correctness regression on dead-branch revert) per cycle-66
threat model.
"""

from __future__ import annotations

import pytest

import kb.config


class TestProjectRootGoesThroughModuleBinding:
    """AC1 divergent-fail control: prove the module-binding path is the live route."""

    def test_get_project_root_uses_module_binding_not_dead_branch(self, tmp_path, monkeypatch):
        """Divergent-fail: with `__getattr__` rebound to raise for ANY name,
        `get_project_root()` MUST still return the monkeypatched value
        because the live route is the module-dict binding (line 107) +
        `globals().get('PROJECT_ROOT')` shim (line 70), NOT the deleted
        PEP 562 branch.
        """
        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)

        # Direct binding (per IR-2) — monkeypatch.setattr does not reliably
        # replace module-level __getattr__ across all Python implementations.
        original_getattr = kb.config.__getattr__

        def fail_for_any_name(name):
            raise AttributeError(
                f"AC1 divergent-fail: __getattr__ should not fire for {name!r} "
                f"(PROJECT_ROOT is bound at line 107, AUGMENT_ALLOWED_DOMAINS "
                f"may legitimately route here but is not exercised in this test)"
            )

        kb.config.__getattr__ = fail_for_any_name
        try:
            result = kb.config.get_project_root()
        finally:
            kb.config.__getattr__ = original_getattr

        assert result == tmp_path, (
            f"AC1: get_project_root() should return monkeypatched PROJECT_ROOT "
            f"({tmp_path}) via the module-dict binding + globals().get shim, "
            f"NOT via the deleted PEP 562 branch; got {result}"
        )

    def test_project_root_monkeypatch_propagates(self, tmp_path, monkeypatch):
        """Standard regression: monkeypatching `kb.config.PROJECT_ROOT`
        flows through `get_project_root()` via the cycle-65 Step-12 shim.
        """
        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
        assert kb.config.get_project_root() == tmp_path

    def test_kb_project_root_env_override(self, tmp_path, monkeypatch):
        """Env-var override: KB_PROJECT_ROOT short-circuits before the
        module-binding shim at line 64-66. Verifies env-first ordering
        is preserved post-AC1.
        """
        monkeypatch.setenv("KB_PROJECT_ROOT", str(tmp_path))
        result = kb.config.get_project_root()
        assert result == tmp_path.resolve()

    def test_augment_allowed_domains_pep562_route_still_live(self, monkeypatch):
        """Confirm the OTHER PEP 562 branch (`AUGMENT_ALLOWED_DOMAINS`)
        still routes via `__getattr__` — the AC1 deletion ONLY removed
        the `PROJECT_ROOT` branch, not the whole hook.
        """
        monkeypatch.setenv("KB_AUGMENT_ALLOWED_DOMAINS", "example.com,test.org")
        result = kb.config.AUGMENT_ALLOWED_DOMAINS
        assert isinstance(result, tuple)
        assert "example.com" in result
        assert "test.org" in result

    def test_unknown_attribute_raises_attributeerror(self):
        """The `__getattr__` AttributeError fallback survives AC1.

        Confirms only the `PROJECT_ROOT` branch was removed — the catch-all
        AttributeError is preserved.
        """
        with pytest.raises(AttributeError, match=r"has no attribute"):
            _ = kb.config.SOME_UNDEFINED_NAME  # type: ignore[attr-defined]

    def test_dead_branch_absent_when_module_binding_removed(self):
        """Strengthened AC1 divergent-fail (R1 review fix).

        The earlier tests verify module-binding propagation but do not
        divergent-fail on AC1 revert because the dead branch is structurally
        unreachable while line 107 binds `PROJECT_ROOT` in the module dict.
        This test forces the PEP 562 path to fire by removing the module
        binding, then asserts attribute access RAISES AttributeError —
        proving the `if name == "PROJECT_ROOT"` branch is gone.

        After AC1 revert (re-add the `if name == "PROJECT_ROOT": return
        get_project_root()` branch), this test FAILS RED because the branch
        returns a Path instead of raising.
        """
        original_value = kb.config.PROJECT_ROOT
        try:
            delattr(kb.config, "PROJECT_ROOT")
            with pytest.raises(AttributeError, match=r"has no attribute 'PROJECT_ROOT'"):
                _ = kb.config.PROJECT_ROOT
        finally:
            kb.config.PROJECT_ROOT = original_value
