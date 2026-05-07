"""Cycle 67 AC08 — `_autouse_kb_path_sandbox` autouse decorator preservation.

The autouse fixture at `tests/conftest.py:_autouse_kb_path_sandbox` (cycle 64
AC1) silently cascades to ~200+ tests that depend on `kb.config.WIKI_*` /
`RAW_*` / `PROJECT_ROOT` being redirected to per-test `tmp_path`. If a future
refactor flips `autouse=True` to `False` or removes the decorator entirely,
those tests start writing to the real `wiki/`/`raw/` directories without
warning.

This meta-test AST-parses `tests/conftest.py` and asserts the decorator list
of `_autouse_kb_path_sandbox` includes `pytest.fixture(autouse=True)` as a
keyword argument with the literal Python value `True`.

Per cycle-23 L2 + cycle-67 R1-F9: the test must distinguish "decorator
present with autouse=True" from "decorator present with autouse=False" —
both render as `@pytest.fixture(...)` decorator but only the former cascades
to the implicit-application semantics we depend on.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path


_CONFTEST_PATH = Path(__file__).resolve().parent / "conftest.py"
_FIXTURE_NAME = "_autouse_kb_path_sandbox"


def _has_autouse_true(decorator_list: list[ast.expr]) -> bool:
    """Return True iff some decorator is a `Call` with `autouse=True` kwarg."""
    for dec in decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        for kw in dec.keywords:
            if (
                kw.arg == "autouse"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                return True
    return False


def _find_function(source: str, name: str) -> ast.FunctionDef | None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def test_autouse_kb_path_sandbox_decorator_intact() -> None:
    """T08-A: live conftest.py has `pytest.fixture(autouse=True)` on the
    sandbox fixture. Failure means future maintainer flipped it to False
    (or removed the decorator) and ~200 tests are now writing real paths."""
    source = _CONFTEST_PATH.read_text(encoding="utf-8")
    fdef = _find_function(source, _FIXTURE_NAME)
    assert fdef is not None, (
        f"Cycle-67 AC08: function `{_FIXTURE_NAME}` not found in {_CONFTEST_PATH}. "
        "Cycle 64 AC1 contract violated — autouse sandbox missing entirely."
    )
    assert _has_autouse_true(fdef.decorator_list), (
        f"Cycle-67 AC08: function `{_FIXTURE_NAME}` at {_CONFTEST_PATH}:{fdef.lineno} "
        "MUST have `@pytest.fixture(autouse=True)` decorator. The autouse=True keyword "
        "is what cascades the sandbox to ~200 tests; without it tests start writing "
        "real `wiki/`/`raw/` directories. (Cycle 64 AC1 / cycle 67 AC08.)"
    )


def test_negative_control_autouse_false_is_detected(tmp_path: Path) -> None:
    """T08-B (negative-control / divergent-fail): synthesize a tmp conftest
    with the same fixture but `autouse=False`, run the AST walker, assert
    the assertion FAILS for that fixture.

    Closes cycle-23 L2 vacuous-test class: T08-A would be a no-op if the
    walker can't distinguish autouse=True from autouse=False.
    """
    bad_conftest = tmp_path / "conftest.py"
    bad_conftest.write_text(
        textwrap.dedent(
            f"""
            import pytest
            from pathlib import Path

            @pytest.fixture(autouse=False)
            def {_FIXTURE_NAME}(tmp_path, monkeypatch, request):
                pass
            """
        ),
        encoding="utf-8",
    )
    source = bad_conftest.read_text(encoding="utf-8")
    fdef = _find_function(source, _FIXTURE_NAME)
    assert fdef is not None, "fixture not found in synthesized conftest"
    assert not _has_autouse_true(fdef.decorator_list), (
        "Negative-control failed: walker did NOT distinguish autouse=False from "
        "autouse=True. T08-A would be vacuous."
    )


def test_negative_control_no_decorator_is_detected(tmp_path: Path) -> None:
    """Additional divergent-fail: completely remove the @pytest.fixture
    decorator. Walker should also FAIL the autouse=True check.
    """
    no_dec = tmp_path / "conftest_no_dec.py"
    no_dec.write_text(
        textwrap.dedent(
            f"""
            from pathlib import Path

            def {_FIXTURE_NAME}(tmp_path, monkeypatch, request):
                pass
            """
        ),
        encoding="utf-8",
    )
    source = no_dec.read_text(encoding="utf-8")
    fdef = _find_function(source, _FIXTURE_NAME)
    assert fdef is not None
    assert not _has_autouse_true(fdef.decorator_list), (
        "Walker incorrectly reported autouse=True for an undecorated function."
    )
