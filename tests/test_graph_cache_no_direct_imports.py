"""AC17 — graph cache __all__ + import discipline test."""

import kb.graph.cache
from tests._helpers.ast_walk import find_imports_from


class TestGraphCacheNoDirectImports:
    """AC17 (C21) — graph cache __all__ + attribute-lookup discipline."""

    def test_all_callers_use_attribute_lookup_form(self):
        """C21 — no direct imports from kb.graph.cache of get_graph.

        Per CLAUDE.md cycle-18 L1, callers MUST use attribute-lookup form:
            kb.graph.cache.get_graph(...)
        NOT
            from kb.graph.cache import get_graph

        AC17 enforces this discipline via __all__ = [] signal and AST scan.
        """
        # Find all imports of get_graph from kb.graph.cache (the helper
        # walks src/kb relative to cwd internally).
        bad_imports = find_imports_from(module="kb.graph.cache", name="get_graph")

        # Should be empty — all callers use attribute-lookup form
        assert len(bad_imports) == 0, (
            f"Found direct imports from kb.graph.cache: {bad_imports}. "
            f"Use kb.graph.cache.get_graph(...) attribute-lookup form instead."
        )

    def test_cache_module_all_is_empty(self):
        """__all__ = [] signals no symbols to export (defensive, cycle-18 L1 enforcement)."""
        assert hasattr(kb.graph.cache, "__all__"), "Module should have __all__"
        assert kb.graph.cache.__all__ == [], "Module __all__ should be empty list"
