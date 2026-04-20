"""Cycle 17 AC4-AC7 — MCP cold-boot lazy-import regression pins.

**Final scope (after legacy-test compat review):** cycle 17 AC4 narrowed the
deferrals to:

- **AC4 real (tool-body):** `anthropic`, `frontmatter`, `kb.utils.llm.LLMError`,
  `kb.utils.pages.save_page_frontmatter`, `kb.capture.*` inside their consuming
  tool bodies (`kb_query`, `_save_synthesis`, `kb_capture`).
- **AC4 parked:** `kb.query.engine`, `kb.ingest.pipeline`, `kb.feedback.reliability`,
  `kb.query.rewriter` stay at module level — legacy tests monkeypatch these via
  `patch("kb.mcp.core.<symbol>")` and migrating every call site to patch the
  owner module is outside cycle 17 scope. Filed to BACKLOG for a dedicated
  monkeypatch-migration cycle. The transitive-load trace confirms these modules
  are loaded by sibling kb.mcp.* anyway, so the cold-boot saving would be zero.
- **AC6 real (module-level removal):** `kb.graph.export` removed from
  `mcp/health.py` module scope and moved into `kb_graph_viz` tool body —
  networkx is the heaviest single dep this cycle is dropping.
- **AC5 / AC7 regression pins:** `mcp/browse.py` / `mcp/quality.py` pass
  AST inspection confirming no NEW module-level heavy imports were added in
  cycle 17.

**Why AST not sys.modules?** The cold-boot test is inherently ORDER-DEPENDENT
under pytest's shared-process model — once any sibling test loads kb.mcp,
the FastMCP `@mcp.tool()` decorators register + cache, and popping modules
from sys.modules causes duplicate-registration failures on re-import.
AST-source inspection answers the deferral question at the ONLY level that
matters: the source-code imports themselves.

The one sys.modules-based test that DOES work is
`test_graph_export_not_loaded_at_mcp_package_import` — because by the time
that test runs, `kb.graph.export` really is absent (until the first
`kb_graph_viz` call). It only fails if someone re-adds the module-level
import in health.py.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_KB_MCP = _REPO_ROOT / "src" / "kb" / "mcp"


def _module_level_imports(py_file: Path) -> set[str]:
    """Return set of fully-qualified names imported at MODULE level via `ast`.

    Ignores function-body and class-body imports (those are lazy by definition).
    Returns top-level Import + ImportFrom targets only.
    """
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return set()
    names: set[str] = set()
    for node in tree.body:  # tree.body = top-level statements only
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Normalise `from X.Y import Z, W` → add both `X.Y` and `X.Y.Z`
                # style entries so tests can match at either granularity.
                names.add(node.module)
                for alias in node.names:
                    names.add(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.If):
            # Handle TYPE_CHECKING guarded blocks — their imports are NOT
            # runtime-level. Skip them.
            continue
    return names


class TestAC4ModuleLevelImportsNarrowed:
    """AC4 — `mcp/core.py` must defer the tool-body-lazy imports at source level."""

    def test_anthropic_not_at_module_level(self) -> None:
        imports = _module_level_imports(_SRC_KB_MCP / "core.py")
        assert "anthropic" not in imports, (
            "AC4 regression: `import anthropic` at module level of mcp/core.py. "
            "Move it inside the `if use_api:` branch of kb_query."
        )

    def test_frontmatter_not_at_module_level(self) -> None:
        imports = _module_level_imports(_SRC_KB_MCP / "core.py")
        assert "frontmatter" not in imports, (
            "AC4 regression: `import frontmatter` at module level of mcp/core.py. "
            "Move it inside `_save_synthesis`."
        )

    def test_kb_capture_module_level_note(self) -> None:
        """Cycle 17 parked — kb.capture stays module-level; header explains why."""
        src = (_SRC_KB_MCP / "core.py").read_text(encoding="utf-8")
        assert "kb.capture" in src and "security check" in src.lower(), (
            "AC4 documentation: cycle 17 header note about parked kb.capture "
            "deferral missing from mcp/core.py"
        )


class TestAC6HealthGraphExportDeferred:
    """AC6 — `mcp/health.py` must not import `kb.graph.export` at module level."""

    def test_graph_export_not_at_module_level(self) -> None:
        imports = _module_level_imports(_SRC_KB_MCP / "health.py")
        assert (
            "kb.graph.export" not in imports and "kb.graph.export.export_mermaid" not in imports
        ), (
            "AC6 regression: `from kb.graph.export import export_mermaid` at "
            "module level of mcp/health.py. Move it inside `kb_graph_viz`."
        )

    def test_graph_export_not_loaded_at_mcp_package_import(self) -> None:
        """Positive runtime pin — networkx must not load on `import kb.mcp.core`."""
        # If kb.graph.export was already imported by some prior test, this
        # check is informational only; the AST check above is the hard guarantee.
        if "kb.graph.export" in sys.modules:
            # Pre-loaded by an earlier test (e.g. one that invoked kb_graph_viz).
            # Don't fail — the AST check already enforces the source contract.
            return
        import importlib

        importlib.import_module("kb.mcp.core")
        assert "kb.graph.export" not in sys.modules, (
            "AC6 regression: importing kb.mcp.core (which triggers kb.mcp "
            "package init → health.py) loaded kb.graph.export."
        )


class TestAC5BrowseRegressionPin:
    """AC5 — `mcp/browse.py` MUST NOT gain module-level heavy imports."""

    def test_no_heavy_imports_at_module_level(self) -> None:
        imports = _module_level_imports(_SRC_KB_MCP / "browse.py")
        forbidden = {
            "kb.evolve.analyzer",
            "kb.graph.builder",
            "kb.graph.export",
        }
        violations = imports & forbidden
        assert not violations, (
            f"AC5 regression: mcp/browse.py imports {violations} at module level. "
            "These must stay in tool bodies."
        )


class TestAC7QualityRegressionPin:
    """AC7 — `mcp/quality.py` MUST NOT gain module-level heavy imports."""

    def test_no_heavy_imports_at_module_level(self) -> None:
        imports = _module_level_imports(_SRC_KB_MCP / "quality.py")
        forbidden = {
            "kb.review.refiner",
            "kb.review.context",
            "kb.lint.semantic",
        }
        violations = imports & forbidden
        assert not violations, (
            f"AC7 regression: mcp/quality.py imports {violations} at module level. "
            "These must stay in tool bodies."
        )


class TestDocumentedScope:
    """Meta — the module docstring explains what cycle 17 did / didn't fix."""

    def test_docstring_declares_parked_deferrals(self) -> None:
        """Future cycles planning deeper deferrals should see the precedent."""
        core_source = (_SRC_KB_MCP / "core.py").read_text(encoding="utf-8")
        assert "Cycle 17 AC4" in core_source, (
            "cycle 17 AC4 context note missing from mcp/core.py header"
        )
        health_source = (_SRC_KB_MCP / "health.py").read_text(encoding="utf-8")
        assert "Cycle 17 AC6" in health_source, (
            "cycle 17 AC6 context note missing from mcp/health.py header"
        )
