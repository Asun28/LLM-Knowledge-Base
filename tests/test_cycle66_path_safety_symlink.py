"""Cycle 66 AC5: tests for `_assert_under_project_root` after `allow_symlinks` removal.

Belt-and-suspenders coverage per cycle-7 L4 (signature pin alone is vacuous,
but signature pin + behavioral test + caller pin is divergent-fail under any
revert combination):

- `test_signature_excludes_allow_symlinks` — structural: kwarg removed.
- `test_symlink_rejected_under_tmp_path` — behavioral: rejection still fires
  on a real symlink (now structurally unconditional).
- `test_compiler_validates_symlink_rejection` — caller pin: the production
  caller `compile/compiler.py::_validate_path_under_project_root` still
  re-raises as `ValidationError` on symlink input.

Closes T7 (future-fourth-caller `allow_symlinks=True` opt-out hazard) per
the cycle-66 design lock.
"""

from __future__ import annotations

import inspect

import pytest

import kb.config
from kb.errors import ValidationError
from kb.utils.path_safety import _assert_under_project_root


def _try_create_symlink(symlink_path, target_path):
    """Create a symlink, skipping the test if the platform refuses.

    Windows without developer-mode + non-admin user cannot create symlinks
    (raises OSError [WinError 1314]). Skipping is correct behavior: the
    cycle-66 AC5 contract holds on every platform that supports symlinks;
    a platform that can't create symlinks also can't be attacked via them
    in the local-filesystem threat model.
    """
    try:
        symlink_path.symlink_to(target_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlink creation not supported on this platform: {exc}")


class TestAllowSymlinksKwargRemoved:
    """AC5 belt-and-suspenders: signature + behavioral + caller pin."""

    def test_signature_excludes_allow_symlinks(self):
        """Signature pin (cycle-66 AC5): `allow_symlinks` parameter is gone.

        Cycle-7 L4: signature pin alone is vacuous (the body could still
        check `allow_symlinks` from a closure or default). Paired with the
        behavioral test below, this becomes belt-and-suspenders divergent-fail.
        """
        sig = inspect.signature(_assert_under_project_root)
        assert "allow_symlinks" not in sig.parameters, (
            "AC5: allow_symlinks kwarg should have been removed in cycle 66; "
            f"present parameters: {list(sig.parameters)}"
        )
        # Cap drops to 3 keyword-only params per Q2.2 cycle-66 update.
        # Positional params (path, field_name) excluded from this set.
        kw_only = {
            name
            for name, p in sig.parameters.items()
            if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        assert kw_only == {"require_exists", "require_dir", "dual_anchor"}, (
            f"AC5 Q2.2: keyword-only param set drifted; got {kw_only}"
        )

    def test_symlink_rejected_under_tmp_path(self, tmp_path, monkeypatch):
        """Behavioral: rejection fires on a real symlink, structurally unconditional.

        Divergent-fail proof: if line 98-99 reverts to `if not allow_symlinks
        and path.is_symlink()`, this test STILL passes (allow_symlinks default
        was False). The signature pin above catches the kwarg revert. Together
        the two cover both partial-revert directions.
        """
        # Anchor project root at tmp_path so the symlink and its target both
        # pass the dual-anchor containment check, leaving the symlink rejection
        # as the ONLY check that can fire.
        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
        target = tmp_path / "real_file.txt"
        target.write_text("real content")
        symlink = tmp_path / "symlink_to_real.txt"
        _try_create_symlink(symlink, target)

        with pytest.raises(ValueError, match=r"is a symlink"):
            _assert_under_project_root(symlink, "test_field")

    def test_compiler_validates_symlink_rejection(self, tmp_path, monkeypatch):
        """Caller pin: `compile/compiler.py::_validate_path_under_project_root`
        re-raises symlink rejection as `ValidationError` (transitive via the
        helper). Confirms the AC5 change does not break the existing
        compile-pipeline contract.
        """
        from kb.compile.compiler import _validate_path_under_project_root

        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
        target = tmp_path / "compile_target.txt"
        target.write_text("compile data")
        symlink = tmp_path / "compile_symlink.txt"
        _try_create_symlink(symlink, target)

        with pytest.raises(ValidationError, match=r"is a symlink"):
            _validate_path_under_project_root(symlink, "compile_target")


class TestAllowSymlinksKwargRejectedAtCallSite:
    """Defensive: passing the removed kwarg should TypeError at the call site."""

    def test_calling_with_allow_symlinks_raises_typeerror(self, tmp_path, monkeypatch):
        """If a future caller mistakenly passes `allow_symlinks=True`, Python
        raises TypeError BEFORE the body executes — closes T7 against the
        most likely partial-revert pattern (someone re-adds the kwarg to a
        caller before re-adding it to the helper signature).
        """
        monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
        ok_path = tmp_path / "regular.txt"
        ok_path.write_text("regular")

        with pytest.raises(TypeError, match=r"unexpected keyword argument"):
            _assert_under_project_root(  # type: ignore[call-arg]
                ok_path,
                "test_field",
                allow_symlinks=True,
            )
