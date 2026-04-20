"""Cycle 17 AC8 — dead-code contract for ``WikiPage`` / ``RawSource``.

Two assertions form the contract:

1. ``test_models_docstring_contract`` — module docstring of ``kb.models.page``
   declares the classes as a "Phase-5 migration target". A future deleter
   must remove the docstring marker first, forcing PR-review visibility.

2. ``test_wikipage_rawsource_not_imported_by_production_code`` — AST scan of
   every ``.py`` file under ``src/kb/`` (excluding ``models/`` itself and the
   ``__init__.py`` re-exports) asserts no production module imports
   ``WikiPage`` or ``RawSource``. Cycle 17 AC8 Option (b) — keep-and-document
   decision; if future code starts using them, delete the docstring contract
   or extend the production paths accordingly.

Design gate Q7 rationale: source-scan string tests are forbidden by cycle-11
L1 and cycle-16 L2 because they test code SHAPE instead of BEHAVIOUR. This
test uses ``ast.parse`` to walk *import structure* — it's an inventory gate,
not a behavioural assertion. It answers a concrete question ("does any
production module import this name today?") with a structural parse of
Python's import graph, not a regex over source text.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import kb.models.page as page_module

_SRC_KB = Path(__file__).resolve().parent.parent / "src" / "kb"

# Excluded paths — these legitimately export or re-export the dead classes.
# Any NEW file that legitimately imports WikiPage/RawSource must be added
# here, which creates PR-review friction (aligned with the AC8 contract).
_ALLOWED_PRODUCTION_IMPORTERS = {
    # Cycle 8 re-export for `from kb.models import WikiPage`.
    _SRC_KB / "models" / "__init__.py",
    # Top-level PEP-562 re-export for `from kb import WikiPage`.
    _SRC_KB / "__init__.py",
    # The definitions themselves.
    _SRC_KB / "models" / "page.py",
}


def _names_imported_by_file(file_path: Path) -> set[str]:
    """Return the set of imported names in `file_path`, parsed via ast."""
    try:
        source = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # from X import Y, Z
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[-1])
    return names


class TestAC8DeadCodeContract:
    """Cycle 17 AC8 — keep-and-document the dead Phase-5 migration classes."""

    def test_models_docstring_contract(self) -> None:
        """Module docstring must flag the classes as Phase-5 migration targets."""
        doc = page_module.__doc__ or ""
        assert "Phase-5 migration target" in doc, (
            "AC8 regression: `kb.models.page` module docstring no longer "
            "declares WikiPage/RawSource as a Phase-5 migration target. "
            "Restore the contract block or document the deletion decision "
            "in BACKLOG.md."
        )

    def test_wikipage_rawsource_not_imported_by_production_code(self) -> None:
        """AST inventory — no production `.py` under src/kb/ imports these names."""
        violations: list[str] = []
        for py_file in _SRC_KB.rglob("*.py"):
            if py_file in _ALLOWED_PRODUCTION_IMPORTERS:
                continue
            names = _names_imported_by_file(py_file)
            bad = names & {"WikiPage", "RawSource"}
            if bad:
                violations.append(f"{py_file.relative_to(_SRC_KB)}: imports {bad}")
        assert not violations, (
            "AC8 regression: production code now imports dead-code classes. "
            "Either: (1) migrate the callers to use dicts (prefer), or "
            "(2) remove the AC8 docstring contract + BACKLOG deletion note + "
            "add the new importer to `_ALLOWED_PRODUCTION_IMPORTERS` above. "
            "Violations:\n  " + "\n  ".join(violations)
        )

    def test_dataclasses_remain_constructible(self) -> None:
        """Sanity — the classes themselves still work for the Phase-5 migration.

        If this fails, the Phase-5 migration target is broken. Block the PR.
        """
        from kb.models import RawSource, WikiPage

        raw = RawSource(
            path=Path("raw/articles/demo.md"),
            source_type="article",
        )
        assert raw.source_type == "article"
        assert raw.content_hash is None

        page = WikiPage(
            path=Path("wiki/summaries/demo.md"),
            title="Demo",
            page_type="summary",
            confidence="stated",
        )
        assert page.page_type == "summary"
        assert page.sources == []


@pytest.fixture
def _cycle17_skip_if_src_missing(tmp_path: Path) -> None:
    """Guard — skip if running outside the repo (src/kb absent)."""
    if not _SRC_KB.exists():
        pytest.skip(f"src/kb/ not found at {_SRC_KB}")
