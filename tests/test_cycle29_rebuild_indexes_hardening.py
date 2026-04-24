"""Cycle 29 AC1 + AC2 — rebuild_indexes audit + override validation hardening.

AC1 — Compound audit token that reflects partial clears.
    Prior to cycle 29, the `wiki/log.md` audit rendered `vector=cleared` even
    when the sibling `.tmp` unlink failed (cycle-25 CONDITION 1 preserved the
    `result["vector"]["error"]` tail but the audit swallowed it). AC1 replaces
    the inline ternary with a shared `_audit_token(block)` helper that emits
    `cleared (warn: <error>)` when `cleared=True` AND `error` is truthy.
    Mirrored to `kb.cli.rebuild_indexes_cmd` so the interactive CLI status
    matches the durable audit record (Q4 same-class peer rule).

AC2 — Dual-anchor PROJECT_ROOT validation on `hash_manifest` + `vector_db`.
    Prior to cycle 29, `rebuild_indexes(hash_manifest=..., vector_db=...)`
    accepted absolute overrides and passed them to `unlink()` without the
    containment check that `wiki_dir` gets. AC2 extracts a shared
    `_validate_path_under_project_root(path, field_name)` helper and applies
    it to all three inputs. Helper returns void (raises only) to avoid
    stub-return-type ambiguity (cycle-23 L2).

Cycle-20 L1 reload-drift: every test late-binds ``ValidationError`` via
``compiler.ValidationError`` inside the test function. NEVER
``from kb.errors import ValidationError`` at module top — reload chains
can desync class identity and silently pass ``pytest.raises``.

Cycle-18 L1 snapshot-bind: `compiler.py` imports `PROJECT_ROOT` at module
load, so tests MUST monkeypatch BOTH `kb.compile.compiler.PROJECT_ROOT` and
`kb.config.PROJECT_ROOT` (cycle-23 precedent at `test_cycle23_rebuild_indexes.py:90-93`).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_wiki_and_data(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal wiki + .data layout. Returns (wiki_dir, vec_path, tmp_vec_path)."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    data_dir = tmp_path / ".data"
    data_dir.mkdir()
    vec_path = data_dir / "vector_index.db"
    tmp_vec_path = data_dir / "vector_index.db.tmp"
    return wiki_dir, vec_path, tmp_vec_path


def _patch_project_root(monkeypatch, tmp_path: Path) -> None:
    """Patch PROJECT_ROOT in BOTH compiler and config modules (cycle-18 L1 + cycle-23 precedent)."""
    import kb.compile.compiler as compiler_mod
    import kb.config

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(compiler_mod, "HASH_MANIFEST", tmp_path / ".data" / "hashes.json")


def _last_log_entry(log_path: Path) -> str:
    """Return the last non-blank line of wiki/log.md (cycle-24 design §8 rule)."""
    return log_path.read_text(encoding="utf-8").strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# AC1 — compound audit token
# ---------------------------------------------------------------------------


class TestAuditCompoundToken:
    """AC1 — `_audit_token(block)` renders cleared+error as compound."""

    def test_audit_renders_vector_cleared_with_tmp_error(self, tmp_path, monkeypatch):
        """Main unlink succeeds + .tmp unlink fails → `vector=cleared (warn: tmp: ...)`."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, vec_path, tmp_vec_path = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")
        tmp_vec_path.write_bytes(b"STALE TMP")

        real_unlink = Path.unlink

        def _selective_unlink(self, missing_ok=False):
            if self == tmp_vec_path:
                raise OSError("simulated tmp lock")
            return real_unlink(self, missing_ok=missing_ok)

        with patch.object(Path, "unlink", _selective_unlink):
            result = rebuild_indexes(wiki_dir=wiki_dir)

        assert result["vector"]["cleared"] is True
        assert "tmp:" in (result["vector"]["error"] or "")

        last = _last_log_entry(wiki_dir / "log.md")
        assert "vector=cleared (warn: tmp:" in last, (
            f"AC1: audit line must expose tmp error inside compound token; got: {last!r}"
        )
        assert "simulated tmp lock" in last, (
            f"AC1: audit line must preserve the error message tail; got: {last!r}"
        )

    def test_audit_renders_vector_cleared_clean_when_no_error(self, tmp_path, monkeypatch):
        """Happy path — both unlinks succeed → `vector=cleared ` (no warn suffix)."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, vec_path, tmp_vec_path = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")
        # No tmp file on disk — unlink(missing_ok=True) succeeds silently.

        result = rebuild_indexes(wiki_dir=wiki_dir)

        assert result["vector"]["cleared"] is True
        assert result["vector"]["error"] is None

        last = _last_log_entry(wiki_dir / "log.md")
        assert "vector=cleared " in last, (
            f"AC1: clean path must render plain cleared; got: {last!r}"
        )
        assert "(warn:" not in last, f"AC1: clean path must NOT emit warn suffix; got: {last!r}"

    def test_audit_renders_vector_error_when_main_unlink_fails(self, tmp_path, monkeypatch):
        """Main vec unlink raises → `vector=vec: <error>` (no cleared token)."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, vec_path, _ = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")

        real_unlink = Path.unlink

        def _fail_main_unlink(self, missing_ok=False):
            if self == vec_path:
                raise OSError("main unlink boom")
            return real_unlink(self, missing_ok=missing_ok)

        with patch.object(Path, "unlink", _fail_main_unlink):
            result = rebuild_indexes(wiki_dir=wiki_dir)

        assert result["vector"]["cleared"] is False
        last = _last_log_entry(wiki_dir / "log.md")
        assert "vector=vec:" in last, f"AC1: main-fail must render error token; got: {last!r}"
        assert "main unlink boom" in last
        assert "vector=cleared" not in last

    def test_audit_renders_embedded_newline_as_single_line(self, tmp_path, monkeypatch):
        """Q3 — embedded `\\n` in OSError collapses to space via append_wiki_log sanitizer."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, vec_path, tmp_vec_path = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")
        tmp_vec_path.write_bytes(b"STALE")

        real_unlink = Path.unlink

        def _multiline_unlink(self, missing_ok=False):
            if self == tmp_vec_path:
                raise OSError("line1\nline2\nline3")
            return real_unlink(self, missing_ok=missing_ok)

        with patch.object(Path, "unlink", _multiline_unlink):
            result = rebuild_indexes(wiki_dir=wiki_dir)

        assert result["vector"]["cleared"] is True
        err = result["vector"]["error"] or ""
        # Error string as stored in result preserves newlines (helper is pure);
        # the sanitizer runs at append_wiki_log write-time only.
        assert "line1" in err and "line2" in err

        last = _last_log_entry(wiki_dir / "log.md")
        # Sanitizer at wiki_log.py:92 replaces \n with space.
        assert "line1" in last and "line2" in last and "line3" in last
        assert "\n" not in last, (
            f"Q3: embedded newlines must sanitize to single line; got raw newline in: {last!r}"
        )
        assert "vector=cleared (warn: tmp:" in last

    def test_cli_rebuild_indexes_shows_compound_vector_status(self, tmp_path, monkeypatch):
        """Q4 — CLI mirror renders compound token via shared `_audit_token`."""
        _patch_project_root(monkeypatch, tmp_path)

        wiki_dir, vec_path, tmp_vec_path = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")
        tmp_vec_path.write_bytes(b"STALE")

        real_unlink = Path.unlink

        def _selective_unlink(self, missing_ok=False):
            if self == tmp_vec_path:
                raise OSError("cli tmp lock")
            return real_unlink(self, missing_ok=missing_ok)

        from kb.cli import cli

        runner = CliRunner()
        with patch.object(Path, "unlink", _selective_unlink):
            result = runner.invoke(
                cli,
                ["rebuild-indexes", "--wiki-dir", str(wiki_dir), "--yes"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0, f"CLI exit code != 0; output={result.output!r}"
        assert "vector=cleared (warn: tmp:" in result.output, (
            f"Q4: CLI must mirror compound token; got: {result.output!r}"
        )
        assert "cli tmp lock" in result.output


# ---------------------------------------------------------------------------
# AC2 — PROJECT_ROOT override validation
# ---------------------------------------------------------------------------


def _outside_project_path(tmp_path: Path) -> Path:
    """Return an absolute path that is NOT under tmp_path.

    Uses tmp_path.parent.parent (guaranteed outside the patched PROJECT_ROOT
    since tmp_path is itself the patched root); the parent traversal is purely
    to produce a clean non-child absolute Path, not to actually escape.
    """
    # `tmp_path` = patched PROJECT_ROOT. Walk up two levels; that's outside.
    outside = tmp_path.parent.parent / f"_kb_c29_outside_{os.getpid()}.json"
    return outside.resolve()


class _ResolvingPath(type(Path())):
    """Path subclass whose `.resolve()` returns a caller-supplied out-of-root target.

    Used to exercise the dual-anchor divergence test: literal path looks in-root,
    but `resolve()` returns an escape target. Per Python 3.12, `Path` is abstract
    and dispatches via `type(Path())` to the concrete PosixPath / WindowsPath.
    Subclass that concrete class.
    """

    _resolve_target: Path | None = None

    def resolve(self, strict: bool = False) -> Path:  # noqa: D401 — override stdlib contract
        if self._resolve_target is not None:
            return self._resolve_target
        return super().resolve(strict=strict)

    @classmethod
    def with_target(cls, literal: Path, target: Path) -> _ResolvingPath:
        inst = cls(literal)
        inst._resolve_target = target
        return inst


class TestOverrideValidation:
    """AC2 — `_validate_path_under_project_root` applied to both overrides."""

    def test_hash_manifest_override_outside_project_raises(self, tmp_path, monkeypatch):
        """Out-of-root `hash_manifest` → ValidationError BEFORE any unlink."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile import compiler

        ValidationError = compiler.ValidationError

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)
        outside = _outside_project_path(tmp_path)

        with patch.object(Path, "unlink") as unlink_spy:
            with pytest.raises(ValidationError, match="hash_manifest must be inside project root"):
                compiler.rebuild_indexes(wiki_dir=wiki_dir, hash_manifest=outside)

        assert unlink_spy.call_count == 0, "AC2: validation must fire BEFORE any unlink() call"

    def test_vector_db_override_outside_project_raises(self, tmp_path, monkeypatch):
        """Out-of-root `vector_db` → ValidationError BEFORE any unlink."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile import compiler

        ValidationError = compiler.ValidationError

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)
        outside = _outside_project_path(tmp_path)

        with patch.object(Path, "unlink") as unlink_spy:
            with pytest.raises(ValidationError, match="vector_db must be inside project root"):
                compiler.rebuild_indexes(wiki_dir=wiki_dir, vector_db=outside)

        assert unlink_spy.call_count == 0

    def test_hash_manifest_override_resolve_escape_raises(self, tmp_path, monkeypatch):
        """Q8 sub-test (a) — literal in-root BUT resolve() out-of-root → ValidationError.

        Uses `_ResolvingPath` subclass to simulate the dual-anchor divergence
        portably on any platform (no real symlink, no global Path.resolve
        monkeypatch). Exercises the second anchor of the check.
        """
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile import compiler

        ValidationError = compiler.ValidationError

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)
        literal = tmp_path / ".data" / "fake_hashes.json"  # in-root literal
        outside = _outside_project_path(tmp_path)  # out-of-root resolve target
        resolving = _ResolvingPath.with_target(literal, outside)

        with pytest.raises(ValidationError, match="hash_manifest must be inside project root"):
            compiler.rebuild_indexes(wiki_dir=wiki_dir, hash_manifest=resolving)

    @pytest.mark.skipif(
        os.name == "nt",
        reason="Windows symlinks require admin/developer mode; decorator-skip per C6 "
        "grep-invariant (cycle-29 R1 Codex M2 — runtime pytest.skip is not grep-verifiable).",
    )
    def test_hash_manifest_override_symlink_to_outside_raises(self, tmp_path, monkeypatch):
        """Q8 sub-test (b) — real `os.symlink` to out-of-root target → ValidationError.

        On POSIX, creates an in-root `.lnk` pointing to an out-of-root target;
        the dual-anchor resolve() check catches the escape. Skipped on Windows
        via decorator so C6's grep-invariant (``rg '@pytest.mark.skipif'``)
        passes without a runtime-inspection walk through test bodies.
        """
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile import compiler

        ValidationError = compiler.ValidationError

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)
        outside_target = _outside_project_path(tmp_path)
        outside_target.write_text("{}", encoding="utf-8")
        link_path = tmp_path / ".data" / "link_hashes.json"
        os.symlink(outside_target, link_path)

        try:
            with pytest.raises(ValidationError, match="hash_manifest must be inside project root"):
                compiler.rebuild_indexes(wiki_dir=wiki_dir, hash_manifest=link_path)
        finally:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            if outside_target.exists():
                outside_target.unlink()

    def test_hash_manifest_override_inside_project_succeeds(self, tmp_path, monkeypatch):
        """In-root `hash_manifest` override validates OK and unlinks normally."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)
        custom_manifest = tmp_path / ".data" / "custom_hashes.json"
        custom_manifest.write_text("{}", encoding="utf-8")
        assert custom_manifest.exists()

        result = rebuild_indexes(wiki_dir=wiki_dir, hash_manifest=custom_manifest)

        assert result["manifest"]["cleared"] is True
        assert not custom_manifest.exists()

    def test_none_override_uses_default_without_validation_drift(self, tmp_path, monkeypatch):
        """None overrides skip extra validation — defaults are derived from PROJECT_ROOT.

        Pins the backward-compat contract AND divergent-fails on removal of the
        `hash_manifest is not None` / `vector_db is not None` guards in
        `rebuild_indexes` (R1 Codex M1): spy the helper and assert it is called
        exactly ONCE (for `wiki_dir` — not for the None overrides). Under guard
        removal, `_validate_path_under_project_root(None, ...)` would either fire
        a 3rd call (AttributeError inside) or add 2 extra calls, flipping the
        assertion.
        """
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile import compiler

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)

        # Spy on the validator — wrap the real helper, count calls.
        real_validator = compiler._validate_path_under_project_root
        call_log: list[tuple] = []

        def _spy(path, field_name):
            call_log.append((path, field_name))
            return real_validator(path, field_name)

        monkeypatch.setattr(compiler, "_validate_path_under_project_root", _spy)

        result = compiler.rebuild_indexes(wiki_dir=wiki_dir)

        assert result["manifest"]["cleared"] is True
        assert result["vector"]["cleared"] is True
        assert result["manifest"]["error"] is None
        assert result["vector"]["error"] is None

        # Exactly ONE validator call — for wiki_dir. None overrides must skip.
        # A revert removing the `is not None` guards would make this 3.
        fields_validated = [field for _, field in call_log]
        assert fields_validated == ["wiki_dir"], (
            f"Expected exactly one validator call (wiki_dir); got {fields_validated}. "
            "None overrides for hash_manifest/vector_db must NOT enter validation."
        )


class TestOverrideCwdSemantics:
    """Cycle 29 R1 S1 — `Path("")` / `Path(".")` cross-platform equivalence.

    Python pathlib treats `Path("")` and `Path(".")` as the same path on both
    POSIX and Windows — both stringify to `"."` and `.resolve()` to CWD. The
    Q7-A "empty reject" check was removed at R1-fix time because it could not
    discriminate between a caller who meant CWD and one who passed empty
    string (they're indistinguishable in pathlib). Instead the dual-anchor
    resolve check handles both: `Path("")` / `Path(".")` resolves to CWD and
    is ACCEPTED iff CWD is under `PROJECT_ROOT`, rejected otherwise.
    """

    def test_empty_path_as_hash_manifest_rejected_when_cwd_outside_project(
        self, tmp_path, monkeypatch
    ):
        """`hash_manifest=Path("")` with CWD outside PROJECT_ROOT → reject by dual-anchor.

        Uses `monkeypatch.chdir(tmp_path.parent)` to force CWD outside the
        patched PROJECT_ROOT (which equals tmp_path). `Path("")` resolves to
        that CWD, the dual-anchor finds it out-of-root, raises
        ValidationError with the "inside project root" message.
        """
        _patch_project_root(monkeypatch, tmp_path)
        monkeypatch.chdir(tmp_path.parent)  # CWD := tmp_path.parent, OUTSIDE PROJECT_ROOT
        from kb.compile import compiler

        ValidationError = compiler.ValidationError

        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)

        with pytest.raises(ValidationError, match="hash_manifest must be inside project root"):
            compiler.rebuild_indexes(wiki_dir=wiki_dir, hash_manifest=Path(""))

    def test_dot_path_as_wiki_dir_accepted_when_cwd_inside_project(self, tmp_path, monkeypatch):
        """`wiki_dir=Path(".")` with CWD == tmp_wiki → accepted (S1 regression pin).

        Divergent-fail anchor for the R1 Sonnet S1 regression: under any guard
        that blanket-rejects `Path("")` / `Path(".")` (including `path ==
        Path("")` which returns True for both), this test would fail with
        "wiki_dir must be non-empty". With the resolve-anchor approach, CWD
        resolves inside PROJECT_ROOT and the call succeeds.
        """
        _patch_project_root(monkeypatch, tmp_path)
        wiki_dir, _, _ = _seed_wiki_and_data(tmp_path)
        monkeypatch.chdir(wiki_dir)  # CWD := tmp_path/wiki, inside PROJECT_ROOT=tmp_path

        from kb.compile.compiler import rebuild_indexes

        # Does NOT raise — Path(".") resolves to wiki_dir which is under tmp_path.
        result = rebuild_indexes(wiki_dir=Path("."))
        assert result["manifest"]["cleared"] is True
