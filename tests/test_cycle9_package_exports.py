"""Cycle 9 package export coverage."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_ingest_source_export_lazy_loads_pipeline():
    repo_root = Path(__file__).resolve().parents[1]
    repo_src = repo_root / "src"
    existing_pythonpath = os.environ.get("PYTHONPATH")
    pythonpath = (
        str(repo_src) if not existing_pythonpath else f"{repo_src}{os.pathsep}{existing_pythonpath}"
    )
    probe = """
import sys

import kb.ingest

assert "kb.ingest.pipeline" not in sys.modules
kb.ingest.ingest_source
assert "kb.ingest.pipeline" in sys.modules
"""

    result = subprocess.run(
        [sys.executable, "-c", probe],
        env={**os.environ, "PYTHONPATH": pythonpath},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
