"""Cycle 69 AC06 — graph builder intentional FW-7 bypass lock-in.

AST guard pinning that every direct ``build_graph`` call in
``src/kb/query/engine.py`` and ``src/kb/evolve/analyzer.py`` supplies the
``pages=`` keyword argument (intentional cache bypass per FW-7). Lock-in
for the AC04 BACKLOG deletion (Phase 4.5 HIGH "non-lint build_graph
callers" entry — verified shipped via cycle-68 AC07/AC08a/AC08b plus the
3 remaining sites being pages-supplying bypasses by design).

Per amendment A10 (R1 N6): synthetic mutation = add a bare
``build_graph(wiki_dir)`` call (no ``pages=`` kwarg) near
``src/kb/query/engine.py:408``. This test MUST FAIL under that mutation.
"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "kb"

IN_SCOPE_MODULES = (
    SRC_DIR / "query" / "engine.py",
    SRC_DIR / "evolve" / "analyzer.py",
)


def _walk_build_graph_calls(tree):
    """Yield every Call node whose func is ast.Name('build_graph')."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "build_graph":
                yield node


def test_build_graph_calls_supply_pages_kwarg():
    """AC06: every direct build_graph call in query/engine + evolve/analyzer
    supplies pages= kwarg (FW-7 intentional cache bypass).
    """
    violations: list[str] = []
    for module_path in IN_SCOPE_MODULES:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for call in _walk_build_graph_calls(tree):
            kwargs = {kw.arg for kw in call.keywords if kw.arg is not None}
            if "pages" not in kwargs:
                rel = module_path.relative_to(PROJECT_ROOT)
                violations.append(f"{rel}:{call.lineno} — build_graph(...) missing pages= kwarg")
    assert not violations, (
        "AC06 violation — build_graph call without pages= (FW-7 bypass requirement):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_in_scope_modules_have_at_least_one_build_graph_call():
    """Sanity guard: if a future refactor removes ALL build_graph calls from
    the in-scope modules, the AST walk above passes vacuously. Pin the
    expected baseline of >=3 calls (analyzer.py:29, analyzer.py:360,
    engine.py:408 per cycle-69 design.md).
    """
    total = 0
    for module_path in IN_SCOPE_MODULES:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        total += sum(1 for _ in _walk_build_graph_calls(tree))
    assert total >= 3, (
        f"Expected >=3 build_graph calls across query/engine + evolve/analyzer, got {total}"
    )
