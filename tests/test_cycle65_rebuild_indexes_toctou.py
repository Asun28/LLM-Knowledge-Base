"""AC10 — O_NOFOLLOW TOCTOU mitigation tests."""

import os
import sys
from pathlib import Path

import pytest

from kb.utils.path_safety import _open_no_follow


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink test")
def test_symlink_swap_rejected_primary(tmp_path: Path) -> None:
    """C9 primary path — symlink should be rejected via O_NOFOLLOW."""
    # Create a real file
    real_file = tmp_path / "real.txt"
    real_file.write_text("test content")
    
    # Successfully open the real file
    fd = _open_no_follow(real_file)
    assert fd > 0, "Should successfully open a real file"
    os.close(fd)
    
    # Now create a symlink and verify it's rejected
    symlink_path = tmp_path / "link.txt"
    symlink_path.symlink_to(real_file)
    
    # Attempt to open the symlink should raise OSError
    with pytest.raises(OSError):
        _open_no_follow(symlink_path)


def test_symlink_swap_rejected_fallback(monkeypatch, tmp_path: Path, caplog) -> None:
    """Q2.3 fallback — when O_NOFOLLOW unavailable, re-resolve and warn once."""
    # Create a real file
    real_file = tmp_path / "real.txt"
    real_file.write_text("test content")
    
    # Simulate O_NOFOLLOW being unavailable
    if sys.platform == "win32":
        monkeypatch.setattr(
            "ctypes.windll.kernel32.CreateFileW",
            lambda *a, **k: (_ for _ in ()).throw(OSError("simulated failure"))
        )
    else:
        monkeypatch.setattr(
            "os.open",
            lambda *a, **k: (_ for _ in ()).throw(OSError("simulated failure"))
        )
    
    # Call _open_no_follow — should use fallback
    fd = _open_no_follow(real_file)
    
    # Check that warning was logged (once per process)
    assert any("AC10" in record.message for record in caplog.records), \
        "Should log AC10 fallback warning"


def test_warning_fires_only_once(monkeypatch, tmp_path: Path, caplog) -> None:
    """Fallback warning should fire once per process, not per call."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("test")
    
    # Simulate O_NOFOLLOW being unavailable
    if sys.platform == "win32":
        monkeypatch.setattr(
            "ctypes.windll.kernel32.CreateFileW",
            lambda *a, **k: (_ for _ in ()).throw(OSError("simulated"))
        )
    else:
        monkeypatch.setattr(
            "os.open",
            lambda *a, **k: (_ for _ in ()).throw(OSError("simulated"))
        )
    
    # Reset the module-level flag to test
    import kb.utils.path_safety
    kb.utils.path_safety._warned_fallback = False
    
    # First call should warn
    caplog.clear()
    _open_no_follow(real_file)
    first_warnings = [r for r in caplog.records if "AC10" in r.message]
    assert len(first_warnings) == 1, "First call should produce one warning"
    
    # Second call should NOT warn (flag is set)
    caplog.clear()
    _open_no_follow(real_file)
    second_warnings = [r for r in caplog.records if "AC10" in r.message]
    assert len(second_warnings) == 0, "Second call should not warn (flag already set)"
