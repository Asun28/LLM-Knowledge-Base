"""Cycle lint checks."""

import itertools
from pathlib import Path

import networkx as nx

from kb.graph.builder import build_graph
from kb.lint import checks


def check_cycles(wiki_dir: Path | None = None, graph: nx.DiGraph | None = None) -> list[dict]:
    """Find circular wikilink chains (A → B → C → A).

    Returns:
        List of dicts: {cycle, message}.
    """
    wiki_dir = wiki_dir or checks.WIKI_DIR
    if graph is None:
        graph = build_graph(wiki_dir)
    issues = []

    # Phase 4.5 HIGH L1: bound cycle detection to 100 to prevent super-exponential
    # runtime on dense link graphs. nx.simple_cycles is unbounded; islice caps output.
    _MAX_CYCLES = 100
    for cycle in itertools.islice(nx.simple_cycles(graph), _MAX_CYCLES):
        if len(cycle) >= 2:
            cycle_str = " → ".join(cycle + [cycle[0]])
            issues.append(
                {
                    "check": "wikilink_cycle",
                    "severity": "info",
                    "cycle": cycle,
                    "message": f"Wikilink cycle detected: {cycle_str}",
                }
            )

    if len(issues) >= _MAX_CYCLES:
        issues.append(
            {
                "check": "wikilink_cycle",
                "severity": "warning",
                "cycle": [],
                "message": (
                    f"Cycle detection aborted after {_MAX_CYCLES} cycles — graph may contain more"
                ),
            }
        )

    return issues
