"""Cycle 35 — `_validate_filename_slug` helper + `_validate_file_inputs` parity.

Threats: T6a (NUL), T6b (homoglyph), T6c (Windows-reserved), T6d
(path-separator), T6e (no false-positive). Cycle-24 L4 revert-fail
discipline: every rejection test fails when the production helper is
reverted to a no-op (`return filename, None`).
"""

from __future__ import annotations

import pytest

from kb.mcp.core import _validate_file_inputs, _validate_filename_slug

# ---------------------------------------------------------------------------
# AC12 — _validate_filename_slug rejects the documented threat set
# ---------------------------------------------------------------------------


class TestValidateFilenameSlugRejects:
    def test_rejects_nul_byte(self):
        slug, err = _validate_filename_slug("foo\x00.md")
        assert slug == ""
        assert err is not None
        assert "NUL" in err

    def test_rejects_homoglyph_cyrillic(self):
        # U+0430 Cyrillic а — visually identical to ASCII а
        slug, err = _validate_filename_slug("а.md")
        assert slug == ""
        assert err is not None
        assert "ASCII" in err

    def test_rejects_emoji(self):
        # Non-ASCII non-letter (emoji) also blocked under the strict gate.
        slug, err = _validate_filename_slug("\U0001f4c4.md")
        assert slug == ""
        assert err is not None
        assert "ASCII" in err

    @pytest.mark.parametrize("name", ["CON.md", "PRN.txt", "NUL", "AUX", "com1.md", "lpt9.txt"])
    def test_rejects_windows_reserved(self, name):
        slug, err = _validate_filename_slug(name)
        assert slug == ""
        assert err is not None
        assert "reserved" in err or "device" in err

    @pytest.mark.parametrize("name", ["../escape.md", "foo/bar.md", "foo\\bar.md", "..", "../"])
    def test_rejects_path_separators(self, name):
        slug, err = _validate_filename_slug(name)
        assert slug == ""
        assert err is not None
        assert "separator" in err or ".." in err

    def test_rejects_trailing_dot(self):
        slug, err = _validate_filename_slug("trailing.")
        assert slug == ""
        assert err is not None
        assert "dot" in err.lower() or "Windows" in err

    @pytest.mark.parametrize("name", [" leading-space.md", "trailing-space.md ", " padded "])
    def test_rejects_whitespace_padding(self, name):
        slug, err = _validate_filename_slug(name)
        assert slug == ""
        assert err is not None
        assert "whitespace" in err.lower() or "empty" in err.lower()

    def test_rejects_oversized(self):
        slug, err = _validate_filename_slug("x" * 201)
        assert slug == ""
        assert err is not None
        assert "too long" in err

    def test_rejects_empty(self):
        slug, err = _validate_filename_slug("")
        assert slug == ""
        assert err is not None

    def test_rejects_non_string(self):
        slug, err = _validate_filename_slug(123)  # type: ignore[arg-type]
        assert slug == ""
        assert err is not None
        assert "string" in err


# ---------------------------------------------------------------------------
# AC15 — _validate_filename_slug accepts legitimate inputs
# ---------------------------------------------------------------------------


class TestValidateFilenameSlugAccepts:
    @pytest.mark.parametrize(
        "name",
        [
            "karpathy-llm-knowledge-bases.md",
            "my_doc.md",
            "file-2026-04-26.md",
            ".env",  # leading dot allowed (POSIX hidden-file convention)
            "-foo.md",  # leading dash allowed (POSIX legitimate)
            "Document_With_Underscores.md",
            "ALLCAPS.MD",
            "single.md",
            "no-extension",
        ],
    )
    def test_accepts_legitimate(self, name):
        slug, err = _validate_filename_slug(name)
        assert err is None, f"unexpected rejection of {name!r}: {err}"
        assert slug == name


# ---------------------------------------------------------------------------
# AC13 — _validate_file_inputs delegates to _validate_filename_slug
# ---------------------------------------------------------------------------


class TestValidateFileInputsWiring:
    def test_rejects_homoglyph_via_wiring(self):
        err = _validate_file_inputs("а.md", "ok")
        assert err is not None
        assert "ASCII" in err

    def test_rejects_path_separator_via_wiring(self):
        err = _validate_file_inputs("../escape.md", "ok")
        assert err is not None
        assert "separator" in err or ".." in err

    def test_rejects_windows_reserved_via_wiring(self):
        err = _validate_file_inputs("CON.md", "ok")
        assert err is not None
        assert "reserved" in err or "device" in err

    def test_rejects_nul_via_wiring(self):
        err = _validate_file_inputs("foo\x00.md", "ok")
        assert err is not None
        assert "NUL" in err

    def test_rejects_trailing_dot_via_wiring(self):
        err = _validate_file_inputs("trailing.", "ok")
        assert err is not None

    def test_accepts_legitimate(self):
        # Baseline preservation — these passed before cycle 35 too.
        assert _validate_file_inputs("karpathy-llm-knowledge-bases.md", "ok") is None
        assert _validate_file_inputs("my_doc.md", "ok") is None

    def test_existing_empty_check_unchanged(self):
        err = _validate_file_inputs("", "ok")
        assert err is not None
        assert "empty" in err.lower()

    def test_existing_length_check_unchanged(self):
        err = _validate_file_inputs("x" * 250, "ok")
        # Existing check fires at len > 200; should win the tie (placed BEFORE
        # the helper call per Step-5 CONDITION 11).
        assert err is not None
        assert "too long" in err.lower()

    def test_existing_content_check_unchanged(self):
        from kb.config import MAX_INGEST_CONTENT_CHARS

        err = _validate_file_inputs("ok.md", "x" * (MAX_INGEST_CONTENT_CHARS + 1))
        assert err is not None
        assert "too large" in err.lower()
