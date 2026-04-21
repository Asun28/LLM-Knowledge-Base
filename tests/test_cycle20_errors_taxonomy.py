"""Cycle 20 AC1/AC2/AC3/AC6 — exception taxonomy tests.

Pins:
- `kb.errors` module surface (6 classes via ``KBError`` base).
- ``LLMError`` + ``CaptureError`` reparenting preserves MRO/.kind/isinstance.
- ``StorageError(kind, path)`` redaction contract (T1 mitigation).
- ``kb`` top-level lazy import surface exposes all 7 names.
- ``from kb.errors import *`` is NOT used anywhere in the tree (lint).

AC7 regression tests (ingest + query outer-except wrap into IngestError /
QueryError) are covered separately in the Task 3 / Task 4 test files because
they require AC5 production wiring to have landed first.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from kb.capture import CaptureError
from kb.errors import (
    CompileError,
    IngestError,
    KBError,
    QueryError,
    StorageError,
    ValidationError,
)
from kb.utils.llm import LLMError


class TestKBErrorHierarchy:
    """AC1 — ``KBError`` base class + 5 specialised subclasses."""

    @pytest.mark.parametrize(
        "subclass",
        [IngestError, CompileError, QueryError, ValidationError, StorageError],
    )
    def test_subclass_inherits_kberror(self, subclass: type) -> None:
        assert issubclass(subclass, KBError)
        assert issubclass(subclass, Exception)

    def test_kberror_itself_inherits_exception(self) -> None:
        assert issubclass(KBError, Exception)

    def test_kberror_not_baseexception_only(self) -> None:
        """Guard against accidentally reparenting KBError to BaseException."""
        assert issubclass(KBError, Exception)
        # BaseException only is True for every Exception subclass; the real
        # guard is that KBError is a narrower class than BaseException.
        assert KBError.__mro__[1:3] == (Exception, BaseException)


class TestLLMErrorReparent:
    """AC2 — ``LLMError`` reparented to ``KBError`` with kind preserved."""

    def test_llmerror_is_kberror(self) -> None:
        assert issubclass(LLMError, KBError)
        assert issubclass(LLMError, Exception)

    def test_llmerror_instance_is_kberror_and_exception(self) -> None:
        err = LLMError("boom")
        assert isinstance(err, KBError)
        assert isinstance(err, Exception)

    def test_llmerror_kind_preserved(self) -> None:
        err = LLMError("401 Unauthorized", kind="auth")
        assert err.kind == "auth"

    def test_llmerror_kind_default_none(self) -> None:
        err = LLMError("generic")
        assert err.kind is None


class TestCaptureErrorReparent:
    """AC2 — ``CaptureError`` reparented to ``KBError``."""

    def test_captureerror_is_kberror(self) -> None:
        assert issubclass(CaptureError, KBError)
        assert issubclass(CaptureError, Exception)

    def test_captureerror_instance(self) -> None:
        err = CaptureError("boom")
        assert isinstance(err, KBError)
        assert str(err) == "boom"


class TestStorageErrorContract:
    """AC1 — ``StorageError`` path-hiding contract (T1 mitigation)."""

    def test_defaults_kind_and_path_none(self) -> None:
        err = StorageError("msg")
        assert err.kind is None
        assert err.path is None
        assert str(err) == "msg"

    def test_kind_and_path_hides_path_in_str(self) -> None:
        err = StorageError("x", kind="summary_collision", path=Path("/secret/abs"))
        assert err.kind == "summary_collision"
        assert err.path == Path("/secret/abs")
        # __str__ hides the path — T1 mitigation against log-aggregator leakage.
        assert str(err) == "summary_collision: <path_hidden>"

    def test_kind_only_renders_raw_msg(self) -> None:
        """Path unset → raw msg verbatim (redaction only kicks in when both fields set)."""
        err = StorageError("custom message", kind="summary_collision")
        assert str(err) == "custom message"

    def test_path_only_renders_raw_msg(self) -> None:
        """Kind unset → raw msg verbatim."""
        err = StorageError("plain", path=Path("/also/secret"))
        assert str(err) == "plain"

    def test_can_be_caught_as_kberror(self) -> None:
        try:
            raise StorageError("x", kind="summary_collision", path=Path("/a"))
        except KBError as caught:
            assert isinstance(caught, StorageError)
            assert caught.kind == "summary_collision"


class TestTopLevelImportSurface:
    """AC3 — ``from kb import X`` works via lazy ``__getattr__``."""

    def test_import_kberror_and_all_subclasses(self) -> None:
        import kb

        for name in (
            "KBError",
            "IngestError",
            "CompileError",
            "QueryError",
            "ValidationError",
            "StorageError",
            "LLMError",
        ):
            cls = getattr(kb, name)
            assert isinstance(cls, type)
            assert issubclass(cls, Exception)

    def test_kb_error_names_resolve_to_errors_module(self) -> None:
        import kb
        import kb.errors

        assert kb.KBError is kb.errors.KBError
        assert kb.IngestError is kb.errors.IngestError
        assert kb.StorageError is kb.errors.StorageError

    def test_kb_all_exposes_new_names(self) -> None:
        import kb

        for name in (
            "KBError",
            "IngestError",
            "CompileError",
            "QueryError",
            "ValidationError",
            "StorageError",
        ):
            assert name in kb.__all__


@pytest.mark.lint
class TestNoStarImportFromKbErrors:
    """AC4 + Q10 — ``from kb.errors import *`` is a lint violation.

    Grep-based lint: scan the whole repo for the anti-pattern. Uses
    ``Path.rglob`` rather than ``subprocess`` to stay hermetic.
    """

    def test_no_star_import(self) -> None:
        # Build the needle at runtime so this file itself does not contain
        # the literal phrase (would otherwise self-trigger).
        needle = "from kb.errors import " + "*"
        repo_root = Path(__file__).resolve().parents[1]
        violators: list[Path] = []
        for py in repo_root.rglob("*.py"):
            # Skip virtualenv / caches / this test file.
            parts = set(py.parts)
            if ".venv" in parts or "site-packages" in parts or "__pycache__" in parts:
                continue
            if py.resolve() == Path(__file__).resolve():
                continue
            text = py.read_text(encoding="utf-8", errors="replace")
            if needle in text:
                violators.append(py)
        assert not violators, f"star-import violates AC4: {violators}"


def test_kb_errors_module_reimportable() -> None:
    """Defensive: reimport ``kb.errors`` shouldn't crash."""
    import kb.errors

    mod = importlib.reload(kb.errors)
    assert hasattr(mod, "KBError")
    assert mod.KBError is kb.errors.KBError or issubclass(mod.KBError, Exception)
