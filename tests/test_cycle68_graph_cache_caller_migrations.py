"""Cycle 68 AC14 — graph cache caller migrations AST guard + cache-hit spy.

TDD red→green pin for AC07/AC08 caller migrations. Three pins:

1. AST guard (FW-7 predicate) — every ``build_graph(...)`` call site in the
   four migrated files (``evolve/analyzer.py``, ``graph/export.py``,
   ``mcp/browse.py``, ``query/engine.py``) MUST supply ``pages=`` with a
   non-None value, OR be a passthrough wrapper. Pages-supplying callers
   are the only legitimate ``build_graph`` direct callers post-migration
   (R1-F5: pages-snapshot poisoning prevention).
2. Cache-hit spy on ``kb.graph.builder.build_graph`` — calling
   ``kb.graph.cache.get_graph(wiki_dir)`` twice in a row MUST trigger the
   real builder exactly once (cache hit on second call).
3. Negative control — replacing ``get_graph`` with a no-cache stub MUST
   make the second call also increment the build counter, proving the
   cache-hit assertion has signal (FW-7 / R2 BLOCKER F3 divergent-fail
   proof).

Reset cache state via ``kb.graph.cache._reset_for_tests()`` between phases.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import kb.graph.cache as graph_cache_mod
from kb.graph.cache import _reset_for_tests, get_graph

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_KB = PROJECT_ROOT / "src" / "kb"

# The four files migrated in AC07 / AC08a / AC08b / AC08c (cycle 68).
MIGRATED_FILES = (
    SRC_KB / "evolve" / "analyzer.py",
    SRC_KB / "graph" / "export.py",
    SRC_KB / "mcp" / "browse.py",
    SRC_KB / "query" / "engine.py",
)


def _is_build_graph_call(node: ast.AST) -> bool:
    """Return True iff ``node`` is a Call to a name ending in ``build_graph``.

    Args:
        node: Any AST node.

    Returns:
        True for ``build_graph(...)`` and ``module.build_graph(...)`` calls.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "build_graph":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "build_graph":
        return True
    return False


def _pages_supplied(node: ast.Call) -> bool:
    """Return True iff ``pages=`` is passed with a non-None value (FW-7 predicate).

    Args:
        node: An ``ast.Call`` node already known to call ``build_graph``.

    Returns:
        True iff a ``pages`` keyword arg exists AND its literal value is not
        ``None`` (catch-all heuristic: any non-Constant or non-None Constant
        passes; ``pages=None`` literal fails — i.e., a regression).
    """
    for kw in node.keywords:
        if kw.arg != "pages":
            continue
        if isinstance(kw.value, ast.Constant) and kw.value.value is None:
            return False
        return True
    return False


def test_no_pages_none_build_graph_calls_in_migrated_files() -> None:
    """AC14 / FW-7 — every build_graph call in migrated files supplies pages=non-None.

    Walks each of the 4 migrated files, finds every ``build_graph(...)`` call
    site, and asserts the FW-7 predicate. A regression that re-introduces
    a ``build_graph(wiki_dir)`` (no pages) call site flips this assertion red.
    """
    violations: list[tuple[str, int, str]] = []
    for src in MIGRATED_FILES:
        assert src.exists(), f"Migrated source missing: {src}"
        source_text = src.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(src))
        for node in ast.walk(tree):
            if not _is_build_graph_call(node):
                continue
            if not _pages_supplied(node):
                snippet = ast.get_source_segment(source_text, node) or "<node>"
                violations.append((str(src), node.lineno, snippet[:120]))
    assert not violations, (
        "FW-7 violation — pages-None build_graph call in migrated file(s). "
        "Per AC07/AC08, pages-None callers must route through "
        "kb.graph.cache.get_graph(...). Offenders:\n  "
        + "\n  ".join(f"{f}:{ln} -> {s!r}" for f, ln, s in violations)
    )


@pytest.fixture
def _reset_cache():
    """Reset graph cache before AND after each test for isolation."""
    _reset_for_tests()
    yield
    _reset_for_tests()


def _make_minimal_wiki(wiki_dir: Path) -> None:
    """Build a minimal wiki layout so build_graph has at least one page.

    Args:
        wiki_dir: Per-test wiki root.
    """
    (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "concepts" / "alpha.md").write_text(
        "---\ntitle: Alpha\nsource: []\ntype: concept\nconfidence: stated\n---\n\n"
        "# Alpha\n\nSee [[concepts/alpha]] for self-link.\n",
        encoding="utf-8",
    )


def test_get_graph_cache_hit_on_repeat_call(
    tmp_kb_env: Path, monkeypatch: pytest.MonkeyPatch, _reset_cache
) -> None:
    """AC14 — second get_graph(wiki_dir) hits cache; build_graph called once total.

    Spy on ``kb.graph.cache.build_graph`` (the OWNER module attribute, per
    cycle-18 L1) and assert the call counter does NOT increment on the
    second get_graph call — that's the cache-hit signal.
    """
    wiki_dir = tmp_kb_env / "wiki"
    _make_minimal_wiki(wiki_dir)

    call_count = 0
    real_build = graph_cache_mod.build_graph

    def _spy(wiki_dir, *, pages=None):
        nonlocal call_count
        call_count += 1
        return real_build(wiki_dir, pages=pages)

    monkeypatch.setattr(graph_cache_mod, "build_graph", _spy)

    first = get_graph(wiki_dir)
    assert call_count == 1, f"First get_graph should call build once; got {call_count}"

    second = get_graph(wiki_dir)
    assert call_count == 1, (
        f"Second get_graph MUST hit cache (count==1); got count={call_count}. "
        "If count==2, the cache-hit path is broken (regression in get_graph)."
    )
    assert first is second, (
        f"Cache hit should return the same graph object; "
        f"first id={id(first)} != second id={id(second)}"
    )


def test_get_graph_negative_control_no_caching_diverges(
    tmp_kb_env: Path, monkeypatch: pytest.MonkeyPatch, _reset_cache
) -> None:
    """AC14 / R2-F3 — negative control: no-cache stub MUST diverge (count==2).

    Replaces ``get_graph`` with a stub that always rebuilds, and asserts the
    counter increments on the second call. Without this divergent-fail proof,
    the positive cache-hit assertion lacks signal — a stub that returns the
    same object would also pass.
    """
    wiki_dir = tmp_kb_env / "wiki"
    _make_minimal_wiki(wiki_dir)

    call_count = 0
    real_build = graph_cache_mod.build_graph

    def _spy(wiki_dir, *, pages=None):
        nonlocal call_count
        call_count += 1
        return real_build(wiki_dir, pages=pages)

    monkeypatch.setattr(graph_cache_mod, "build_graph", _spy)

    # Replace get_graph with a no-cache passthrough so caching is bypassed.
    def _no_cache_get_graph(wiki_dir, *, pages=None):
        return graph_cache_mod.build_graph(wiki_dir, pages=pages)

    monkeypatch.setattr(graph_cache_mod, "get_graph", _no_cache_get_graph)

    # Now call the patched name; both invocations rebuild → count == 2.
    graph_cache_mod.get_graph(wiki_dir)
    graph_cache_mod.get_graph(wiki_dir)

    assert call_count == 2, (
        f"Negative control: no-cache stub MUST rebuild on both calls; "
        f"got count={call_count}. If count==1, the stub silently shares state — "
        f"divergent-fail proof is broken."
    )
