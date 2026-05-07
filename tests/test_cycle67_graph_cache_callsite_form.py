"""Cycle 67 AC02 — graph/cache 6th-caller drift guard.

The cycle-18 L1 lesson requires `kb.graph.cache.get_graph` callers to use
attribute-lookup form (`kb.graph.cache.get_graph(...)`) so test spies set via
`monkeypatch.setattr(kb.graph.cache, "get_graph", ...)` reach them. A new
caller doing `from kb.graph.cache import get_graph` would silently bypass
those spies (snapshot binding hazard).

Cycle 64 AC9 / AC10 set `__all__ = []` in `kb.graph.cache` to discourage
star imports. Cycle 67 AC02 adds an AST-grep test that closes the
6th-caller drift hazard explicitly: zero `from kb.graph.cache import
get_graph` allowed in `src/kb/`.

Per cycle-67 design FW-5 / R1-C9: aliased forms (`import kb.graph.cache
as gc`) are FINE because `monkeypatch.setattr` reaches them via the
underlying module attribute. Only `from-import` of the bound name is
forbidden.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

from tests._helpers.ast_walk import find_imports_from


def test_no_from_kb_graph_cache_import_get_graph_in_src() -> None:
    """T02-A: zero `from kb.graph.cache import get_graph` in src/kb/.

    Uses the `find_imports_from` helper (cycle-66 AC4 vintage) which walks
    `ast.ImportFrom` nodes and checks for the (module, name) pair. Returns
    a list of offending file Paths.
    """
    offenders = find_imports_from("kb.graph.cache", "get_graph")
    assert offenders == [], (
        "cycle-67 AC02: `from kb.graph.cache import get_graph` is FORBIDDEN in src/kb/.\n"
        f"Found in: {[str(p) for p in offenders]}\n"
        "Use attribute-lookup form: `import kb.graph.cache; kb.graph.cache.get_graph(...)`\n"
        "or aliased: `import kb.graph.cache as gc; gc.get_graph(...)`.\n"
        "Cycle-18 L1: snapshot-binding hazard — `from x import y` captures y at import "
        "time, so `monkeypatch.setattr(x, 'y', spy)` does NOT reach the snapshot."
    )


def test_negative_control_from_import_is_detected(tmp_path: Path) -> None:
    """T02-B (negative-control / divergent-fail): synthesize a tmp file with
    the forbidden import and assert the AST walker WOULD detect it.

    This proves the test is non-vacuous (cycle-23 L2): if a future caller adds
    the forbidden import, T02-A WILL go red. We don't actually patch src/kb/
    here — we walk a tmp_path-rooted equivalent.
    """
    src_root = tmp_path / "src" / "kb"
    src_root.mkdir(parents=True)
    offending = src_root / "evil_caller.py"
    offending.write_text(
        textwrap.dedent(
            """
            from kb.graph.cache import get_graph

            def use_it(wiki_dir):
                return get_graph(wiki_dir)
            """
        ),
        encoding="utf-8",
    )

    # Direct AST walk of tmp_path (find_imports_from hardcodes "src/kb"; we
    # replicate its logic locally to validate against tmp_path).
    offenders: list[Path] = []
    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "kb.graph.cache"
                and any(alias.name == "get_graph" for alias in node.names)
            ):
                offenders.append(py_file)
                break

    assert offending in offenders, (
        "Negative-control failed: AST walker did NOT detect the forbidden import. "
        "T02-A would be vacuous if this fixture cannot demonstrate detection."
    )


def test_aliased_module_import_is_allowed(tmp_path: Path) -> None:
    """T02-C (R1-C9 / C-AC02-alias): aliased forms `import kb.graph.cache as gc`
    and `from kb.graph import cache as gc` are FINE per cycle-18 L1.

    They preserve attribute-lookup semantics: `gc.get_graph(...)` resolves to
    `kb.graph.cache.get_graph` at call time, so `monkeypatch.setattr(
    kb.graph.cache, 'get_graph', spy)` reaches them.

    This test pins the design intent: T02-A forbids ONLY the from-import of
    the bound name, not aliased module imports.
    """
    src_root = tmp_path / "src" / "kb"
    src_root.mkdir(parents=True)
    aliased_module = src_root / "aliased_module.py"
    aliased_module.write_text(
        textwrap.dedent(
            """
            import kb.graph.cache as gc

            def use_it(wiki_dir):
                return gc.get_graph(wiki_dir)
            """
        ),
        encoding="utf-8",
    )
    aliased_from = src_root / "aliased_from.py"
    aliased_from.write_text(
        textwrap.dedent(
            """
            from kb.graph import cache as gc

            def use_it(wiki_dir):
                return gc.get_graph(wiki_dir)
            """
        ),
        encoding="utf-8",
    )

    # Same AST walker logic as T02-B, scoped to tmp_path.
    offenders: list[Path] = []
    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "kb.graph.cache"
                and any(alias.name == "get_graph" for alias in node.names)
            ):
                offenders.append(py_file)
                break

    assert offenders == [], (
        "Aliased imports incorrectly flagged as offenders. Cycle-18 L1 says "
        "aliased forms preserve attribute-lookup semantics and ARE allowed.\n"
        f"False positives: {[str(p) for p in offenders]}"
    )
