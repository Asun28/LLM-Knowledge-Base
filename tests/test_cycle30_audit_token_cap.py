"""Cycle 30 AC1 — `_audit_token` caps `block["error"]` at 500 chars.

Protects `wiki/log.md` + `kb rebuild-indexes` CLI stdout from audit-log
bloat when `OSError.__str__()` produces ~1KB Windows path messages. Uses
`kb.utils.text.truncate` (cycle-3 M17 head+tail smart-truncation) so
diagnostic anchors at head AND tail survive the cap.

Per cycle-29 precedent:
- Cycle-18 L1 snapshot-bind: monkeypatch PROJECT_ROOT in BOTH
  `kb.compile.compiler` and `kb.config` modules.
- Cycle-20 L1 reload-drift: late-bind any exception classes via the
  production module attribute inside the test function.
- Cycle-28 L2 / cycle-24 L4 revert-tolerance: clean-path test
  (`test_audit_token_clean_path_preserves_bare_cleared`) flips to fail
  if the truncate call is moved outside the truthiness guard and
  `None` error silently becomes the string `"None"`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Helpers (mirror cycle-29 shared test harness for consistency)
# ---------------------------------------------------------------------------


def _patch_project_root(monkeypatch, tmp_path: Path) -> None:
    """Patch PROJECT_ROOT in both compiler and config modules."""
    import kb.compile.compiler as compiler_mod
    import kb.config

    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compiler_mod, "WIKI_DIR", tmp_path / "wiki")
    monkeypatch.setattr(compiler_mod, "HASH_MANIFEST", tmp_path / ".data" / "hashes.json")


def _seed_wiki_and_data(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create wiki + .data layout. Returns (wiki_dir, vec_path, tmp_vec_path)."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    data_dir = tmp_path / ".data"
    data_dir.mkdir()
    vec_path = data_dir / "vector_index.db"
    tmp_vec_path = data_dir / "vector_index.db.tmp"
    return wiki_dir, vec_path, tmp_vec_path


def _last_log_entry(log_path: Path) -> str:
    return log_path.read_text(encoding="utf-8").strip().splitlines()[-1]


# ---------------------------------------------------------------------------
# Unit tests — `_audit_token` direct
# ---------------------------------------------------------------------------


class TestAuditTokenCap:
    """Cycle 30 AC1 — `_audit_token` caps long errors via
    `kb.utils.text.truncate(..., limit=500)`.
    """

    def test_audit_token_caps_long_warn_error(self):
        """cleared=True + 2000-char error → capped, head+tail marker present."""
        from kb.compile.compiler import _audit_token

        long_err = "X" * 2000
        result = _audit_token({"cleared": True, "error": long_err})

        assert result.startswith("cleared (warn: X")
        assert "chars elided" in result
        # Budget: 500 (limit) + ~40 (marker variance) + "cleared (warn: " prefix + ")"
        # Hard ceiling: ~560 chars. 2000 original → well above cap.
        assert len(result) <= 560, f"warn-branch cap overshot: len={len(result)}"
        assert long_err not in result, "raw 2000-char string must not appear in output"

    def test_audit_token_caps_long_fallback_error(self):
        """cleared=False + 2000-char error → fallback branch also capped."""
        from kb.compile.compiler import _audit_token

        long_err = "Y" * 2000
        result = _audit_token({"cleared": False, "error": long_err})

        assert result.startswith("Y")
        assert "chars elided" in result
        # Fallback branch has no "cleared (warn: " wrapping, so 540 budget fits.
        assert len(result) <= 540, f"fallback-branch cap overshot: len={len(result)}"
        assert long_err not in result

    def test_audit_token_short_error_passthrough_unchanged(self):
        """Short errors (below 500) pass through with no marker."""
        from kb.compile.compiler import _audit_token

        short = "lock busy"
        result = _audit_token({"cleared": True, "error": short})
        assert result == f"cleared (warn: {short})"
        assert "chars elided" not in result

    def test_audit_token_clean_path_preserves_bare_cleared(self):
        """R2-A2 amendment — truthiness-guarded: None error → bare 'cleared' (no warn suffix).

        Divergent-fail: a naive revert that calls `truncate(str(None))` before
        the truthiness branch would produce `"cleared (warn: None...)"`, flipping
        this assertion.
        """
        from kb.compile.compiler import _audit_token

        assert _audit_token({"cleared": True, "error": None}) == "cleared"
        assert _audit_token({"cleared": False, "error": None}) == "unknown"

    def test_audit_token_empty_string_error_falsy(self):
        """Empty-string error on cleared path skips the cap branch — bare 'cleared'."""
        from kb.compile.compiler import _audit_token

        # `""` is falsy; should match None-path behavior (bare "cleared").
        assert _audit_token({"cleared": True, "error": ""}) == "cleared"
        # On the non-cleared path, falsy error returns "unknown".
        assert _audit_token({"cleared": False, "error": ""}) == "unknown"


# ---------------------------------------------------------------------------
# E2E tests — `rebuild_indexes` → wiki/log.md audit line bounded
# ---------------------------------------------------------------------------


class TestRebuildIndexesAuditLineBounded:
    """Cycle 30 AC1 — end-to-end: a long `OSError.__str__()` on unlink does
    NOT bloat `wiki/log.md`.
    """

    def test_rebuild_indexes_audit_preserves_tmp_prefix_under_long_error(
        self, tmp_path, monkeypatch
    ):
        """Vector `.tmp` unlink raises 2000-char OSError → audit line bounded,
        head anchor (`vector=cleared (warn: tmp:`) still visible.
        """
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, vec_path, tmp_vec_path = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")
        tmp_vec_path.write_bytes(b"STALE")

        real_unlink = Path.unlink
        long_msg = "A" * 2000

        def _selective_unlink(self, missing_ok=False):
            if self == tmp_vec_path:
                raise OSError(long_msg)
            return real_unlink(self, missing_ok=missing_ok)

        with patch.object(Path, "unlink", _selective_unlink):
            result = rebuild_indexes(wiki_dir=wiki_dir)

        # The library-layer error field still holds the raw (uncapped) string —
        # this is intentional; the cap applies at render time, not data storage.
        assert result["vector"]["cleared"] is True
        assert long_msg in (result["vector"]["error"] or "")

        last = _last_log_entry(wiki_dir / "log.md")
        # Head anchor preserved (cycle-29 grep invariant).
        assert "vector=cleared (warn: tmp:" in last, (
            f"AC1: head anchor must survive truncation; got: {last!r}"
        )
        # Elision marker present — proves the cap fired.
        assert "chars elided" in last, (
            f"AC1: truncate marker must appear in audit line; got last={last[:200]!r}"
        )
        # Total line length bounded (revert-intolerant: uncapped → ~2100 chars).
        assert len(last) <= 700, (
            f"AC1: audit line must stay under ~700 chars under 2KB error; got len={len(last)}"
        )
        # Raw 2000-char message must NOT appear verbatim.
        assert long_msg not in last

    def test_rebuild_indexes_audit_clean_path_untouched(self, tmp_path, monkeypatch):
        """Happy path (no errors) → audit line has no `chars elided` marker."""
        _patch_project_root(monkeypatch, tmp_path)
        from kb.compile.compiler import rebuild_indexes

        wiki_dir, vec_path, _tmp_vec_path = _seed_wiki_and_data(tmp_path)
        vec_path.write_bytes(b"MAIN")
        # No tmp file on disk — unlink(missing_ok=True) succeeds silently.

        result = rebuild_indexes(wiki_dir=wiki_dir)

        assert result["vector"]["cleared"] is True
        assert result["vector"]["error"] is None
        assert result["manifest"]["cleared"] is True

        last = _last_log_entry(wiki_dir / "log.md")
        # Clean path uses the bare `"cleared"` token — no marker, no warn.
        assert "manifest=cleared" in last
        assert "vector=cleared" in last
        assert "(warn:" not in last, f"clean path must have no warn: suffix; got {last!r}"
        assert "chars elided" not in last, f"clean path must have no truncate marker; got {last!r}"
