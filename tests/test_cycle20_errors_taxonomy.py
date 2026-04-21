"""Cycle 20 AC1/AC2/AC3/AC6/AC7 — exception taxonomy + query AC7 regression.

Pins:
- `kb.errors` module surface (6 classes via ``KBError`` base).
- ``LLMError`` + ``CaptureError`` reparenting preserves MRO/.kind/isinstance.
- ``StorageError(kind, path)`` redaction contract (T1 mitigation).
- ``kb`` top-level lazy import surface exposes all 7 names.
- ``from kb.errors import *`` is NOT used anywhere in the tree (lint).
- AC7 query_wiki unexpected-exception wrap to ``QueryError`` (matching cycle-18
  test_jsonl_emitted_on_failure + tests/test_cycle20_write_wiki_page_exclusive
  for the ingest side).
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

    def test_empty_kind_string_does_not_trigger_redaction(self) -> None:
        """Cycle-20 R1 Sonnet MAJOR 2 — `kind=""` must fall through to raw msg,
        not render `": <path_hidden>"`. The `__str__` guard uses a truthy check
        on `self.kind` so an empty string disables redaction (cycle-19 L3
        rule: empty strings must not bypass a rejection-oriented guard).
        """
        err = StorageError("raw msg", kind="", path=Path("/secret"))
        assert str(err) == "raw msg"

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


class TestAC7QueryErrorWraps:
    """AC7 — unexpected exceptions inside query_wiki wrap into QueryError.

    Mirror of the cycle-18 test_jsonl_emitted_on_failure on the ingest side;
    the query-side wrap lands in ``query_wiki``'s trampoline around
    ``_query_wiki_body``.
    """

    def test_runtime_error_wraps_to_query_error(self, tmp_project, monkeypatch) -> None:
        """RuntimeError at search_pages → QueryError with __cause__ preserved."""
        import kb.query.engine as engine

        def boom(*args, **kwargs):
            raise RuntimeError("search engine explosion")

        # Patch at engine-module attribute — _query_wiki_body resolves the
        # bound name at call time, so patching `kb.query.engine.search_pages`
        # reaches the synthesis path.
        monkeypatch.setattr("kb.query.engine.search_pages", boom, raising=True)

        with pytest.raises(QueryError, match="search engine explosion") as excinfo:
            engine.query_wiki("hello world", wiki_dir=tmp_project / "wiki")
        assert isinstance(excinfo.value, QueryError)
        assert isinstance(excinfo.value.__cause__, RuntimeError)

    def test_oserror_passes_through_unchanged(self, tmp_project, monkeypatch) -> None:
        """AC5 narrowing — OSError is in expected-kind list, passes through."""
        import kb.query.engine as engine

        def boom(*args, **kwargs):
            raise OSError("simulated io fail")

        monkeypatch.setattr("kb.query.engine.search_pages", boom, raising=True)

        with pytest.raises(OSError, match="simulated io fail"):
            engine.query_wiki("hello", wiki_dir=tmp_project / "wiki")


def test_kb_errors_module_reimportable() -> None:
    """Defensive: reimport ``kb.errors`` shouldn't crash."""
    import kb.errors

    mod = importlib.reload(kb.errors)
    assert hasattr(mod, "KBError")
    assert mod.KBError is kb.errors.KBError or issubclass(mod.KBError, Exception)
