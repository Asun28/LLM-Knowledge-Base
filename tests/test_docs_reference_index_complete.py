"""Tests for AC20 — docs/reference/INDEX.md completeness.

Cycle 65 AC20 — verify that INDEX.md includes all reference files and that
CLAUDE.md's documentation table is up to date.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_index_md_includes_all_reference_files():
    """Assert INDEX.md includes all docs/reference/*.md files (except INDEX.md, README.md).

    C23 — verify the index is complete and current.
    """
    # Read INDEX.md
    index_file = Path("docs/reference/INDEX.md")
    assert index_file.exists(), "docs/reference/INDEX.md not found"

    index_content = index_file.read_text(encoding="utf-8")

    # Get all .md files in docs/reference (except INDEX.md and README.md)
    ref_dir = Path("docs/reference")
    reference_files = sorted(
        [
            f.name
            for f in ref_dir.glob("*.md")
            if f.name not in {"INDEX.md", "README.md"}
        ]
    )

    # Check that each reference file is mentioned in INDEX.md
    for filename in reference_files:
        assert (
            filename in index_content
        ), f"{filename} not found in INDEX.md"


def test_claude_md_table_includes_all_reference_files():
    """Assert CLAUDE.md Detailed Documentation table includes all reference files.

    C23 — verify CLAUDE.md's documentation index is complete.
    """
    # Read CLAUDE.md
    claude_file = Path("CLAUDE.md")
    assert claude_file.exists(), "CLAUDE.md not found"

    claude_content = claude_file.read_text(encoding="utf-8")

    # Get all .md files in docs/reference (except INDEX.md and README.md)
    ref_dir = Path("docs/reference")
    reference_files = sorted(
        [
            f.name
            for f in ref_dir.glob("*.md")
            if f.name not in {"INDEX.md", "README.md"}
        ]
    )

    # Check that each reference file path is mentioned in CLAUDE.md
    # The table format is `docs/reference/filename.md`
    for filename in reference_files:
        file_path = f"docs/reference/{filename}"
        assert (
            file_path in claude_content
        ), f"{file_path} not found in CLAUDE.md Detailed Documentation table"
