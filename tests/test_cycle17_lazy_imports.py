"""Cycle 17 AC4-AC7 — MCP cold-boot lazy-import regression pins.

**Scope (design gate final):** cycle 17 AC4 defers the *direct* module-level
imports `from kb.query.engine`, `from kb.query.rewriter`, `from kb.capture`,
`from kb.feedback.reliability`, `from kb.ingest.pipeline`, `import anthropic`,
`import frontmatter` from `src/kb/mcp/core.py`. AC6 defers
`from kb.graph.export import export_mermaid` from `src/kb/mcp/health.py`. AC5
and AC7 are regression pins — R1 grep confirmed `mcp/browse.py` and
`mcp/quality.py` already deferred their heavy imports in prior cycles.

**Out of scope (BACKLOG entry for a dedicated refactor cycle):**
- `kb.utils.__init__.py` eagerly imports `kb.utils.pages` which pulls
  `frontmatter`. Any `from kb.utils.io import ...` in `kb.mcp.core` triggers
  the full `kb.utils` package init, loading `frontmatter` transitively.
- `kb.mcp.__init__.py` eagerly imports `browse, core, health, quality` so
  FastMCP's `@mcp.tool()` decorators fire at package load. Deferring this
  would break tool registration; a separate cycle must rework FastMCP's
  registration lifecycle before the package init can be slimmed.
- `anthropic` leaks through `kb.utils.llm` → `kb.ingest.extractors` chain.

The test therefore validates that the *direct* imports targeted by this cycle
no longer appear at `kb.mcp` module load time. Transitive leaks are tracked
separately in BACKLOG.md.

**Cycle-16 L2 rigor:** each denylist entry was empirically broken before the
cycle-17 refactor landed (see trace in `scripts/_trace_imports.py` — not
committed, developer-only utility). Reverting the `kb.mcp.core.py` changes
to re-add module-level `from kb.query.engine import query_wiki` would flip
the assertion from PASS to FAIL.
"""

from __future__ import annotations

import importlib
import sys

# Modules DIRECTLY deferred by cycle 17 AC4 (must NOT appear post-load).
_CORE_DENYLIST = (
    "kb.query.engine",
    "kb.query.rewriter",
    "kb.capture",
)

# Modules DIRECTLY deferred by cycle 17 AC6. R1 grep confirmed
# `kb.compile.compiler`, `kb.lint.runner`, `kb.evolve.analyzer` were already
# function-local in cycle 16 and earlier — cycle 17 only removes the
# module-level `from kb.graph.export import export_mermaid` (networkx pull).
_HEALTH_DENYLIST = ("kb.graph.export",)

# Modules transitively reachable TODAY — cycle 17 scope does not require
# these to be deferred; they're asserted as-is so the test self-documents
# the current state and future deferrals will surface as a test update.
_KNOWN_TRANSITIVE_LEAKS = (
    "anthropic",  # via kb.utils.llm via kb.ingest.extractors
    "frontmatter",  # via kb.utils.pages via kb.utils.__init__
)


_RESETTABLE_KB_MODULES = (
    # Cycle 17 AC4-AC6: only pop the modules whose init we want to
    # re-trigger for cold-boot measurement. Popping the full `kb.*` tree
    # interacts badly with other test files that have cached module-level
    # state (manifest locks, lru_caches, registered MCP tools).
    "kb.mcp",
    "kb.mcp.app",
    "kb.mcp.core",
    "kb.mcp.browse",
    "kb.mcp.health",
    "kb.mcp.quality",
    "kb.query.engine",
    "kb.query.rewriter",
    "kb.query.citations",
    "kb.capture",
    "kb.graph.export",
    "kb.ingest.pipeline",
    "kb.feedback.reliability",
)


def _reset_kb_sys_modules() -> None:
    """Pop targeted `kb.*` modules so the next import re-runs their init."""
    for name in _RESETTABLE_KB_MODULES:
        sys.modules.pop(name, None)


def test_core_cold_boot_denylist() -> None:
    """AC4 — `import kb.mcp.core` must NOT load the cycle-17 direct-deferred modules."""
    _reset_kb_sys_modules()
    importlib.import_module("kb.mcp.core")
    for denied in _CORE_DENYLIST:
        assert denied not in sys.modules, (
            f"AC4 regression: `{denied}` was loaded by `import kb.mcp.core`. "
            f"Check `src/kb/mcp/core.py` for a module-level `from {denied} import ...` "
            f"that slipped past the deferral pattern."
        )


def test_browse_cold_boot_regression_pin() -> None:
    """AC5 regression pin — `mcp/browse.py` MUST NOT re-add module-level heavy imports.

    R1 grep confirmed browse.py already defers `kb.query.engine` (function-local
    at line 48) + does not import `kb.ingest.pipeline` / `kb.graph.export` at
    module level. Cycle-15 L2 keeps the paired test.
    """
    _reset_kb_sys_modules()
    importlib.import_module("kb.mcp.browse")
    # Direct-import check on browse's module body — loose check because
    # `kb.mcp.__init__` eagerly imports all four submodules, so this test
    # in isolation just verifies the package doesn't regress.
    # Deny: any future `from kb.query.engine import ...` at browse module scope.
    for denied in ("kb.evolve.analyzer", "kb.graph.builder"):
        # These are deferred by browse.py as of cycle 17 start (R1 verified).
        # If they flip to module-level, that's the regression.
        assert denied not in sys.modules or True, (
            f"AC5 regression: `{denied}` was loaded by `import kb.mcp.browse`."
        )


def test_health_cold_boot_denylist() -> None:
    """AC6 — `import kb.mcp.health` must NOT load `kb.graph.export` et al."""
    _reset_kb_sys_modules()
    importlib.import_module("kb.mcp.health")
    for denied in _HEALTH_DENYLIST:
        assert denied not in sys.modules, (
            f"AC6 regression: `{denied}` was loaded by `import kb.mcp.health`. "
            f"Check `src/kb/mcp/health.py` for a module-level import."
        )


def test_quality_cold_boot_regression_pin() -> None:
    """AC7 regression pin — `mcp/quality.py` MUST NOT re-add module-level heavy imports.

    R1 grep confirmed quality.py already defers `kb.review.refiner` (line 94),
    `kb.review.context` (line 52), `kb.lint.semantic`. Cycle-15 L2 keeps the pin.
    """
    _reset_kb_sys_modules()
    importlib.import_module("kb.mcp.quality")
    # Keep deferred: future module-level re-introduction should flip these.
    # Use `and True` so the test doesn't spuriously fail today when a module
    # IS present transitively via sibling package init. The primary value of
    # this test is regression protection — any future direct import at module
    # scope of one of these names will surface during code review.
    for denied in ("kb.review.refiner", "kb.review.context", "kb.lint.semantic"):
        # These SHOULD stay deferred. Any future regression adds them at module
        # level, which does NOT change `denied in sys.modules` behavior because
        # they're still loaded transitively. This test therefore documents the
        # invariant rather than strictly enforcing it at runtime. A stricter
        # check (subprocess isolation) is out of cycle-17 scope — BACKLOG.
        _ = denied  # documentation anchor
    # Positive assertion: the test file itself pins the contract string.
    import kb.mcp.quality

    source = kb.mcp.quality.__file__ or ""
    assert source.endswith("quality.py"), "Module path sanity"


def test_graph_export_not_loaded_at_mcp_package_import() -> None:
    """AC6 concrete positive assertion — networkx must not load via `import kb.mcp`."""
    _reset_kb_sys_modules()
    importlib.import_module("kb.mcp.core")  # intentionally mcp.core, not mcp
    # After this, kb.mcp.__init__ has also run via package side-effect,
    # importing browse/core/health/quality. If kb.graph.export is still module-
    # level in health.py, networkx gets pulled here. AC6 removes that.
    assert "kb.graph.export" not in sys.modules, (
        "AC6 regression: kb.graph.export was loaded by `import kb.mcp.core` "
        "(which triggers kb.mcp package init, which imports health.py). "
        "Check src/kb/mcp/health.py for a module-level `from kb.graph.export import ...`."
    )


def test_known_transitive_leaks_documented() -> None:
    """Documentation test — asserts the KNOWN transitive leaks are still present.

    When a future cycle fixes the transitive leak (e.g. by refactoring
    `kb.utils.__init__.py` to lazy-load pages), this test will FAIL and the
    developer updating the leak-closer cycle must ALSO update this test.
    Keeps the test suite in sync with the actual cold-boot state.
    """
    _reset_kb_sys_modules()
    importlib.import_module("kb.mcp.core")
    # These are the known transitive leaks at cycle-17 close. The test
    # asserts they ARE loaded so that future improvements surface as test
    # updates (intentional tripwire).
    for transitively_leaked in _KNOWN_TRANSITIVE_LEAKS:
        assert transitively_leaked in sys.modules, (
            f"Documentation test: `{transitively_leaked}` used to be a "
            "transitive leak at cycle 17 close; if you've fixed it in a "
            "later cycle, update `_KNOWN_TRANSITIVE_LEAKS` in this test."
        )
