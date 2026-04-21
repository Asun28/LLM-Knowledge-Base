"""Cycle 20 AC20 — Windows tilde-shortened path equivalence for _canonical_rel_path.

Closes the cycle-19 T-13a placeholder skipif. On Windows filesystems with 8.3
short-name generation enabled, a long path like ``C:\\Program Files\\...``
also resolves to a tilde-shortened form like ``C:\\PROGRA~1\\...``.
``_canonical_rel_path`` must canonicalise both to the same manifest key so a
``compile_wiki(raw_dir=C:\\PROGRA~1)`` run produces the same hashes.json entry
as a ``compile_wiki(raw_dir=C:\\Program Files)`` run.

Runtime-skip rules:
- Platform gate: ``skipif(sys.platform != "win32")``.
- If the underlying filesystem has 8.3 generation disabled,
  ``GetShortPathNameW`` returns the long form verbatim → skip.
- If the short→long roundtrip via ``GetLongPathNameW`` does not match the
  original long form, the fixture is broken → skip rather than test a bogus
  equivalence (cycle-16 L2 "don't test stdlib helpers in isolation").
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

import pytest


def _get_short_path_w(long_path: Path) -> Path | None:
    """Call Win32 GetShortPathNameW; return short path or None if the buffer
    is empty / call fails / the filesystem returns the long form verbatim.
    """
    buf = ctypes.create_unicode_buffer(260)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    n = kernel32.GetShortPathNameW(str(long_path), buf, 260)
    if n == 0:
        return None
    short = Path(buf.value)
    if short == long_path:
        # Filesystem has 8.3 short-name generation disabled — no tilde form.
        return None
    return short


def _get_long_path_w(short_path: Path) -> Path | None:
    """Roundtrip sanity — `GetLongPathNameW(short)` should equal the long form."""
    buf = ctypes.create_unicode_buffer(260)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    n = kernel32.GetLongPathNameW(str(short_path), buf, 260)
    if n == 0:
        return None
    return Path(buf.value)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tilde-shortened path test")
def test_canonical_rel_path_tilde_equivalence(tmp_path: Path) -> None:
    """``_canonical_rel_path`` treats long-form + tilde-shortened as equivalent."""
    from kb.compile.compiler import _canonical_rel_path

    # Create a long-ish directory name that 8.3 MUST truncate (>8 chars).
    long_dir = tmp_path / "Program Files Extended"
    long_dir.mkdir()
    source_file = long_dir / "source.md"
    source_file.write_text("# test\n", encoding="utf-8")

    short_dir = _get_short_path_w(long_dir)
    if short_dir is None:
        pytest.skip("filesystem does not generate tilde-shortened names (8.3 disabled)")

    # Roundtrip sanity — short must map BACK to the long form. If this fails
    # the fixture is unreliable and the equivalence assertion below would be
    # vacuous (cycle-16 L2 rule).
    round_trip = _get_long_path_w(short_dir)
    if round_trip is None or round_trip != long_dir:
        pytest.skip(f"GetLongPathNameW roundtrip failed: {short_dir} -> {round_trip} != {long_dir}")

    # Now the real test: feeding the long-form + short-form source paths to
    # `_canonical_rel_path` with the same raw_dir yields the same manifest key.
    short_source = short_dir / "source.md"
    raw_dir = tmp_path  # the common ancestor

    long_key = _canonical_rel_path(source_file, raw_dir)
    short_key = _canonical_rel_path(short_source, raw_dir)

    assert long_key == short_key, (
        f"tilde vs long-form must produce identical manifest keys:\n"
        f"  long_source  = {source_file}\n"
        f"  long_key     = {long_key}\n"
        f"  short_source = {short_source}\n"
        f"  short_key    = {short_key}"
    )
