"""Cycle 33 AC1-AC5 — path-leak redaction at MCP `Error[partial]:` emitters
+ paired `logger.warning` records + `kb_query.save_as` peer + sanitize-helper
OSError-shape unit suite + Q8 UNC/long-path xfail-strict markers.

Threats covered: T1, T2, T3, T4, T5, T10. Revert-fail discipline per cycle-24
L4 — production-fix revert MUST flip ≥4 of these tests to red.
"""

from __future__ import annotations

import errno
import logging
import os
from pathlib import Path

import pytest

# Distinct slug-bearing fixture filenames so caplog assertions can disambiguate
# across concurrent / interleaved tests (T10 / R1-05 mitigation).
#
# Important: ``OSError.__str__`` formats the ``filename`` attribute using
# Python's repr-style escaping, so a single-backslash Windows path
# ``D:\Projects\test\fake.md`` (24 chars) emerges as the doubled-backslash
# form ``D:\\Projects\\test\\fake.md`` (32 chars) in the rendered OSError
# string. The two assertion forms below cover both the input shape AND the
# rendered shape so a revert test cannot pass vacuously (cycle-24 L4 — Windows
# assertion that uses the single-backslash literal would never appear in the
# rendered OSError string regardless of whether redaction ran).
_LEAKY_WIN_INPUT = r"D:\Projects\test\fake.md"  # what we PUT in OSError filename
_LEAKY_WIN_EMITTED = r"D:\\Projects\\test\\fake.md"  # what OSError str EMITS
_LEAKY_WIN_FWD = "D:/Projects/test/fake.md"  # slash-normalized variant
_LEAKY_WIN_BASENAME_DIR = "Projects"  # any leak form will contain this
_LEAKY_POSIX = "/tmp/test/fake.md"
_FIXTURE_TAG = "cycle33-redact-fixture-A1B2"


class _RaisingFile:
    """Context-manager stub whose `.write()` raises a crafted OSError.

    Used by the kb_ingest_content / kb_save_source path-leak fixtures: the
    production code does ``with os.fdopen(fd, "w", ...) as f: f.write(...)``,
    so we need an object that supports the ``__enter__``/``__exit__`` protocol
    AND has a ``.write`` method that raises with the desired path embedded.
    """

    def __init__(self, exc: OSError) -> None:
        self._exc = exc

    def __enter__(self):  # noqa: ANN204
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:  # noqa: ANN001
        return False

    def write(self, *_a, **_kw) -> int:  # noqa: ANN201
        raise self._exc


def _force_oserror_on_fdopen(monkeypatch, exc: OSError, *, fd_to_close: list[int]) -> None:
    """Patch `kb.mcp.core.os.fdopen` so the next call raises `exc` from `.write`.

    The production path opens a real fd via ``os.open`` first; we must close
    that fd ourselves to avoid resource warnings. Pass `fd_to_close` so the
    test owner can sweep on teardown.
    """
    real_fdopen = os.fdopen

    def _stub(fd, *args, **kwargs):
        # Close the real fd that ``os.open`` returned — production code expects
        # ``fd_transferred = True`` to be set inside the with-block; we still
        # want to release the OS handle to keep the fixture clean.
        try:
            os.close(fd)
        except OSError:
            pass
        return _RaisingFile(exc)

    monkeypatch.setattr("kb.mcp.core.os.fdopen", _stub)
    # Keep real_fdopen referenced so it is not garbage-collected (paranoia).
    fd_to_close.append(0)
    _ = real_fdopen


# ---------------------------------------------------------------------------
# AC1 / AC2 / AC3 — kb_ingest_content + kb_save_source `Error[partial]:` redact
# ---------------------------------------------------------------------------


class TestKbIngestContentPathRedacted:
    """AC1 + AC3 — kb_ingest_content `Error[partial]:` + paired logger.warning."""

    def _invoke(
        self, monkeypatch, caplog, tmp_kb_env, leaky_path: str
    ) -> tuple[str, str]:
        from kb.mcp import core as mcp_core

        # R1 Sonnet MINOR — defense-in-depth + Step-5 Q9 explicit monkeypatch.
        # Under full-suite ordering, `tmp_kb_env`'s mirror-rebind loop
        # (conftest:248-255) can MISS `kb.mcp.core.SOURCE_TYPE_DIRS` because the
        # comparison `kb.mcp.core.SOURCE_TYPE_DIRS == mirror_original` returns
        # False when an earlier test reloaded kb.config (snapshot drift; see
        # cycle-19 L2 reload-leak class). Defensive monkeypatch ensures
        # production code lands under tmp regardless of mirror-rebind state.
        article_dir = tmp_kb_env / "raw" / "articles"
        article_dir.mkdir(parents=True, exist_ok=True)
        patched_dirs = {
            **mcp_core.SOURCE_TYPE_DIRS,
            "article": article_dir,
        }
        monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", patched_dirs)
        # Now confirm the production-computed file_path WILL resolve under tmp.
        article_dir_used = mcp_core.SOURCE_TYPE_DIRS["article"]
        assert str(article_dir_used).startswith(str(tmp_kb_env)), (
            f"defensive monkeypatch failed — article_dir={article_dir_used!r}"
        )

        caplog.set_level(logging.WARNING, logger="kb.mcp.core")
        exc = OSError(errno.EACCES, "Access is denied", leaky_path)
        _force_oserror_on_fdopen(monkeypatch, exc, fd_to_close=[])

        result = mcp_core.kb_ingest_content(
            content=f"hello world {_FIXTURE_TAG}",
            filename=f"{_FIXTURE_TAG}-ingest",
            source_type="article",
            extraction_json='{"title": "T", "entities_mentioned": [], "concepts_mentioned": []}',
        )
        # caplog.text is the formatted text including args interpolation.
        return result, caplog.text

    def test_windows_drive_letter_path_redacted_in_return_and_log(
        self, monkeypatch, caplog, tmp_kb_env
    ):
        result, log_text = self._invoke(monkeypatch, caplog, tmp_kb_env, _LEAKY_WIN_INPUT)
        # MCP return string contract — must NOT contain any of the three
        # leak forms (input single-backslash, OSError emitted double-backslash,
        # slash-normalized forward variant) and must NOT contain the
        # distinguishing directory token "Projects".
        assert "Error[partial]:" in result
        assert _LEAKY_WIN_INPUT not in result
        assert _LEAKY_WIN_EMITTED not in result
        assert _LEAKY_WIN_FWD not in result
        assert _LEAKY_WIN_BASENAME_DIR not in result
        # caplog contract — paired logger.warning at core.py:756-760.
        assert _LEAKY_WIN_INPUT not in log_text
        assert _LEAKY_WIN_EMITTED not in log_text
        assert _LEAKY_WIN_FWD not in log_text
        assert _LEAKY_WIN_BASENAME_DIR not in log_text
        # Positive: errno + strerror should still surface (operator diagnostic).
        assert "Access is denied" in result
        assert "Access is denied" in log_text

    def test_posix_path_redacted_in_return_and_log(self, monkeypatch, caplog, tmp_kb_env):
        result, log_text = self._invoke(monkeypatch, caplog, tmp_kb_env, _LEAKY_POSIX)
        assert "Error[partial]:" in result
        assert _LEAKY_POSIX not in result
        assert _LEAKY_POSIX not in log_text
        assert "Permission denied" in result or "Access is denied" in result


class TestKbSaveSourcePathRedacted:
    """AC2 + AC3 — kb_save_source `Error[partial]:` + paired logger.warning."""

    def _invoke(
        self, monkeypatch, caplog, tmp_kb_env, leaky_path: str
    ) -> tuple[str, str]:
        from kb.mcp import core as mcp_core

        # R1 Sonnet MINOR defense-in-depth + Step-5 Q9 explicit monkeypatch
        # (mirrors kb_ingest_content tests; see comment block there).
        article_dir = tmp_kb_env / "raw" / "articles"
        article_dir.mkdir(parents=True, exist_ok=True)
        patched_dirs = {
            **mcp_core.SOURCE_TYPE_DIRS,
            "article": article_dir,
        }
        monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", patched_dirs)
        article_dir_used = mcp_core.SOURCE_TYPE_DIRS["article"]
        assert str(article_dir_used).startswith(str(tmp_kb_env)), (
            f"defensive monkeypatch failed — article_dir={article_dir_used!r}"
        )

        caplog.set_level(logging.WARNING, logger="kb.mcp.core")
        exc = OSError(errno.EACCES, "Access is denied", leaky_path)
        _force_oserror_on_fdopen(monkeypatch, exc, fd_to_close=[])

        result = mcp_core.kb_save_source(
            content=f"raw content {_FIXTURE_TAG}",
            filename=f"{_FIXTURE_TAG}-save",
            source_type="article",
        )
        return result, caplog.text

    def test_windows_drive_letter_path_redacted_in_return_and_log(
        self, monkeypatch, caplog, tmp_kb_env
    ):
        result, log_text = self._invoke(monkeypatch, caplog, tmp_kb_env, _LEAKY_WIN_INPUT)
        assert "Error[partial]:" in result
        assert _LEAKY_WIN_INPUT not in result
        assert _LEAKY_WIN_EMITTED not in result
        assert _LEAKY_WIN_FWD not in result
        assert _LEAKY_WIN_BASENAME_DIR not in result
        assert _LEAKY_WIN_INPUT not in log_text
        assert _LEAKY_WIN_EMITTED not in log_text
        assert _LEAKY_WIN_FWD not in log_text
        assert _LEAKY_WIN_BASENAME_DIR not in log_text

    def test_posix_path_redacted_in_return_and_log(self, monkeypatch, caplog, tmp_kb_env):
        result, log_text = self._invoke(monkeypatch, caplog, tmp_kb_env, _LEAKY_POSIX)
        assert "Error[partial]:" in result
        assert _LEAKY_POSIX not in result
        assert _LEAKY_POSIX not in log_text


# ---------------------------------------------------------------------------
# AC4 — kb_query.save_as same-class peer (logger + return symmetry)
# ---------------------------------------------------------------------------


class TestKbQuerySaveAsPathRedacted:
    """AC4 — `_save_synthesis` OSError path; both log AND return get sanitized.

    `_save_synthesis` is the helper kb_query calls when `save_as=...` is set.
    We invoke it directly with a stub `result` dict to avoid the full kb_query
    pipeline (LLM call, BM25 search, etc.) — the leak surface is the OSError
    handler at `core.py:279-285`, not the upstream synthesis logic.
    """

    def _invoke_with_oserror(
        self, monkeypatch, caplog, leaky_path: str
    ) -> tuple[str, str]:
        from kb.mcp import core as mcp_core

        caplog.set_level(logging.WARNING, logger="kb.mcp.core")

        # Patch save_page_frontmatter (the only OSError-raising call inside
        # _save_synthesis's try block) to raise the crafted error.
        exc = OSError(errno.EACCES, "Access is denied", leaky_path)

        def _raising_save(*_a, **_kw):
            raise exc

        monkeypatch.setattr("kb.utils.pages.save_page_frontmatter", _raising_save)

        result_dict = {
            "answer": "synthetic answer body",
            "source_pages": ["entities/foo"],
            "low_confidence": False,
        }
        msg = mcp_core._save_synthesis(f"{_FIXTURE_TAG}-synth", result_dict)
        return msg, caplog.text

    def test_windows_path_redacted_in_return(self, monkeypatch, caplog, tmp_kb_env):
        msg, _log_text = self._invoke_with_oserror(monkeypatch, caplog, _LEAKY_WIN_INPUT)
        assert "[warn] save_as failed:" in msg
        assert _LEAKY_WIN_INPUT not in msg
        assert _LEAKY_WIN_EMITTED not in msg
        assert _LEAKY_WIN_FWD not in msg
        assert _LEAKY_WIN_BASENAME_DIR not in msg

    def test_windows_path_redacted_in_log(self, monkeypatch, caplog, tmp_kb_env):
        _msg, log_text = self._invoke_with_oserror(monkeypatch, caplog, _LEAKY_WIN_INPUT)
        # AC4 fix at core.py:280 — logger.warning must NOT leak path either.
        assert "save_as write failed" in log_text
        assert _LEAKY_WIN_INPUT not in log_text
        assert _LEAKY_WIN_EMITTED not in log_text
        assert _LEAKY_WIN_FWD not in log_text
        assert _LEAKY_WIN_BASENAME_DIR not in log_text

    def test_posix_path_redacted_in_return_and_log(self, monkeypatch, caplog, tmp_kb_env):
        msg, log_text = self._invoke_with_oserror(monkeypatch, caplog, _LEAKY_POSIX)
        assert _LEAKY_POSIX not in msg
        assert _LEAKY_POSIX not in log_text

    def test_lazy_import_oserror_does_not_raise_unboundlocalerror(
        self, monkeypatch, caplog, tmp_kb_env
    ):
        """Cycle 33 R2 Codex C33-R2-01 regression — same-class extension of A1.

        The original A1 fix moved `target` assignment BEFORE `mkdir`. R2 caught
        a remaining gap: the lazy `import frontmatter` (and
        `from kb.utils.pages import save_page_frontmatter`) inside the try
        block can ALSO raise OSError on a corrupted .pyc / disk-error
        condition, leaving `target` unbound at the except handler. Final fix
        moves `target` (and `synthesis_dir`) OUTSIDE the try block entirely.
        Path / str is pure construction and cannot fail, so this is safe.
        """
        from kb.mcp import core as mcp_core

        caplog.set_level(logging.WARNING, logger="kb.mcp.core")

        # Patch sys.modules to force `import frontmatter` to raise OSError.
        # The lazy import inside _save_synthesis goes through importlib;
        # we simulate by removing frontmatter from sys.modules and inserting
        # a finder that raises.
        import sys

        leaky_path = _LEAKY_WIN_INPUT
        exc_to_raise = OSError(errno.EACCES, "Access is denied", leaky_path)

        # Remove the cached frontmatter module if present, then patch builtins
        # __import__ to raise OSError when 'frontmatter' is requested.
        # `monkeypatch.delitem` auto-restores the original module on teardown
        # — using bare `sys.modules.pop` would leave frontmatter unloaded and
        # break any sibling test that mutates the module object via
        # `import frontmatter as fm_lib; fm_lib.load = mock` (e.g.
        # `tests/test_v0915_task06.py::test_does_not_swallow_keyboard_interrupt`
        # — that test gets a stale handle when frontmatter re-imports fresh).
        monkeypatch.delitem(sys.modules, "frontmatter", raising=False)
        # __builtins__ is a dict in non-main modules but a module in __main__;
        # handle both by sniffing the type before patch.
        if isinstance(__builtins__, dict):
            original_import = __builtins__["__import__"]
        else:
            original_import = __builtins__.__import__

        def _raising_import(name, *args, **kwargs):
            if name == "frontmatter":
                raise exc_to_raise
            return original_import(name, *args, **kwargs)

        if isinstance(__builtins__, dict):
            monkeypatch.setitem(__builtins__, "__import__", _raising_import)
        else:
            monkeypatch.setattr(__builtins__, "__import__", _raising_import)

        result_dict = {
            "answer": "synthetic answer body",
            "source_pages": ["entities/foo"],
            "low_confidence": False,
        }
        # MUST NOT raise UnboundLocalError — `target` is now bound BEFORE the
        # try block, so the except handler can use it regardless of where
        # inside the try the OSError fired.
        msg = mcp_core._save_synthesis(f"{_FIXTURE_TAG}-import-fail", result_dict)

        # AC4 path-redaction contract preserved.
        assert "[warn] save_as failed:" in msg
        assert leaky_path not in msg
        assert _LEAKY_WIN_EMITTED not in msg
        assert _LEAKY_WIN_BASENAME_DIR not in msg

    def test_mkdir_oserror_does_not_raise_unboundlocalerror(
        self, monkeypatch, caplog, tmp_kb_env
    ):
        """Cycle 33 R1 Codex MAJOR A1 regression — `synthesis_dir.mkdir` failing
        BEFORE `target` is assigned must NOT raise UnboundLocalError.

        Pre-fix code at `core.py:247-249` had ``mkdir`` then ``target = ...`` so
        an OSError from ``mkdir`` would jump to the except handler with `target`
        unbound. The except references `target` for path-redaction, producing
        UnboundLocalError that crashes through MCP's "never raises" contract.
        Fix moves `target` assignment BEFORE ``mkdir``.
        """
        from kb.mcp import core as mcp_core

        caplog.set_level(logging.WARNING, logger="kb.mcp.core")

        # Patch mkdir on the Path class to raise — affects the synthesis_dir
        # mkdir at the start of the try block, BEFORE any other code can run.
        leaky_path = _LEAKY_WIN_INPUT
        exc = OSError(errno.EACCES, "Access is denied", leaky_path)

        original_mkdir = Path.mkdir

        def _raising_mkdir(self, *args, **kwargs):
            # Only raise for the synthesis_dir; let other mkdir calls work.
            if self.name == "synthesis":
                raise exc
            return original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", _raising_mkdir)

        result_dict = {
            "answer": "synthetic answer body",
            "source_pages": ["entities/foo"],
            "low_confidence": False,
        }
        # MUST NOT raise UnboundLocalError — the post-fix code assigns
        # `target` before `mkdir` so the except handler can use it.
        msg = mcp_core._save_synthesis(f"{_FIXTURE_TAG}-mkdir-fail", result_dict)

        # And the leak must still be redacted (AC4 contract preserved).
        assert "[warn] save_as failed:" in msg
        assert leaky_path not in msg
        assert _LEAKY_WIN_EMITTED not in msg
        assert _LEAKY_WIN_BASENAME_DIR not in msg


# ---------------------------------------------------------------------------
# R1-03 IN-CYCLE — sanitize_error_text OSError-shape parametrised unit suite
# ---------------------------------------------------------------------------


class TestSanitizeErrorTextOSErrorShapes:
    """R1-03 IN-CYCLE — pin redaction across the OSError constructor space.

    AC5 covers one shape (3-arg with filename); this suite extends to the
    five most common variants the helper might see in production. Each case
    asserts ABSENCE of the leaky path literal, NOT a specific output form,
    so internal helper output changes are tolerated.
    """

    def test_3arg_form_with_posix_filename(self):
        from kb.utils.sanitize import sanitize_error_text

        out = sanitize_error_text(OSError(errno.EACCES, "Access is denied", "/home/user/secret.md"))
        assert "/home/user/secret.md" not in out
        assert "Access is denied" in out

    def test_no_filename_arg_returns_clean_string(self):
        from kb.utils.sanitize import sanitize_error_text

        # 1-arg form has no filename attribute — nothing to leak; helper must
        # not crash and must preserve the strerror prefix.
        out = sanitize_error_text(OSError("Access is denied"))
        assert "Access is denied" in out

    def test_filename_is_none_no_spurious_path_token(self):
        from kb.utils.sanitize import sanitize_error_text

        # Some libraries pass filename=None explicitly; helper must not insert
        # a spurious `<path>` token where no path was present.
        exc = OSError(errno.EACCES, "Access is denied", None)
        out = sanitize_error_text(exc)
        assert "Access is denied" in out
        # filename=None means OSError.__str__ omits the trailing `: '<path>'`.
        assert "/home" not in out
        assert "D:\\" not in out

    def test_filename2_attr_5arg_form_redacts_both(self):
        from kb.utils.sanitize import sanitize_error_text

        # 5-arg form populates both filename + filename2 (e.g., MoveFile).
        # Helper iterates ("filename", "filename2") at sanitize.py:68-76 so
        # both should be redacted.
        exc = OSError(
            errno.EACCES,
            "MoveFile failed",
            "/home/user/src.md",
            None,
            "/home/user/dst.md",
        )
        out = sanitize_error_text(exc)
        assert "/home/user/src.md" not in out
        assert "/home/user/dst.md" not in out
        assert "MoveFile failed" in out

    def test_path_in_args1_text_only(self):
        from kb.utils.sanitize import sanitize_error_text

        # Path appears inside the strerror text (args[1]) without a filename
        # attr. Regex sweep must catch it via _ABS_PATH_PATTERNS.
        exc = OSError(errno.EACCES, "/home/user/leaked-via-msg.md")
        out = sanitize_error_text(exc)
        assert "/home/user/leaked-via-msg.md" not in out


# ---------------------------------------------------------------------------
# Q8 — UNC / long-path filename xfail-strict (only ordinary-UNC currently leaks)
# ---------------------------------------------------------------------------


class TestSanitizeErrorTextUNCAndLongPath:
    r"""Q8 — Three Windows path shapes that flow through ``_rel(Path(fn_str))``.

    Per Step-9 REPL probe (cycle-16 L3 — reproduce the failure mode first):
      - long_path ``\\?\C:\...``: REDACTS via final regex sweep (drive-letter
        match after slash-normalize).
      - ordinary_unc ``\\server\share\...``: LEAKS — see BACKLOG cycle-34
        candidate ``sanitize.py UNC slash-normalize bug``. Marked xfail-strict
        so a future helper fix flips the marker and forces removal.
      - unc_long_path ``\\?\UNC\server\share\...``: REDACTS via long-path regex.
    """

    def test_windows_long_path_filename_redacts(self):
        from kb.utils.sanitize import sanitize_error_text

        out = sanitize_error_text(
            OSError(errno.EACCES, "Access is denied", r"\\?\C:\Projects\foo.md")
        )
        assert "C:\\Projects" not in out
        assert "C:/Projects" not in out
        assert "foo.md" not in out

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "sanitize.py UNC slash-normalize bug — see BACKLOG cycle-34 candidate. "
            "OSError.__str__ doubles backslashes; _ABS_PATH_PATTERNS UNC alternative "
            "matches single backslashes only, so doubled-backslash UNC slips through. "
            "Removing this xfail when the helper is fixed will force the marker "
            "removal (strict=True semantic)."
        ),
    )
    def test_windows_ordinary_unc_filename_redacts(self):
        from kb.utils.sanitize import sanitize_error_text

        out = sanitize_error_text(
            OSError(errno.EACCES, "Access is denied", r"\\server\share\secret.md")
        )
        # Both backslash and slash-normalized forms must be absent.
        assert "server" not in out
        assert "share" not in out
        assert "secret.md" not in out

    def test_windows_unc_long_path_filename_redacts(self):
        from kb.utils.sanitize import sanitize_error_text

        out = sanitize_error_text(
            OSError(errno.EACCES, "Access is denied", r"\\?\UNC\server\share\foo.md")
        )
        assert "server" not in out
        assert "share" not in out
        assert "foo.md" not in out
