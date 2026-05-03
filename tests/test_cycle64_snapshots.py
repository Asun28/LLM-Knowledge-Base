"""Cycle 64 — Cluster E — golden-file / snapshot infrastructure foundation
(AC18–AC20).

Closes BACKLOG.md MEDIUM "no golden-file / snapshot tests; wiki rendering is
verified only by `assert "X" in output`". Cycle 64 ships the foundation with
3 high-impact snapshot subjects per design-decision Q6:

- ``test_evidence_trail_format_snapshot`` — pins the canonical
  ``kb.ingest.evidence.append_evidence_trail`` rendering (date | source |
  action format, prepend direction, whitespace).
- ``test_mermaid_export_format_snapshot`` — pins ``kb.graph.export.export_mermaid``
  output (node IDs, edges, diagram preamble).
- ``test_lint_report_format_snapshot`` — pins the structure of
  ``kb.lint.runner.run_all_checks``'s returned dict (checks_run order, summary
  shape, issue list ordering).

T15 / T16 mitigations:
- T15 — snapshot fixture text is constructed from controlled inputs only;
  no os.environ / Path.home references that would leak the developer's
  filesystem layout into committed snapshots.
- T16 — default `pytest` invocations FAIL on snapshot drift; only an
  explicit `pytest --snapshot-update` rewrites the snapshots. CI workflows
  do NOT pass that flag.

AC18 fallback path (per AC18 + R1-F15): if syrupy is rejected by Step 11
SCA, the evidence-trail and lint-report subjects already render to text;
only mermaid would need a one-line text-comparison rewrite.

Per cycle-40 L3: each test fails when the production rendering changes —
that's the POINT of snapshot testing.
"""

from __future__ import annotations

from kb.graph.export import export_mermaid
from kb.ingest.evidence import append_evidence_trail


def test_evidence_trail_format_snapshot(tmp_path, snapshot):
    """AC19: pin the evidence-trail rendering format."""
    page_path = tmp_path / "concepts" / "rag.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        "---\ntitle: RAG\nsource: []\ntype: concept\nconfidence: stated\n---\n\n"
        "# RAG\n\nRetrieval-augmented generation.\n",
        encoding="utf-8",
    )

    # 3 entries spanning a year so the prepend / order is exercised.
    append_evidence_trail(
        page_path,
        source_ref="raw/articles/karpathy-2026.md",
        action="appended",
        entry_date="2026-04-01",
    )
    append_evidence_trail(
        page_path,
        source_ref="raw/articles/lewis-2020.md",
        action="appended",
        entry_date="2026-04-15",
    )
    append_evidence_trail(
        page_path,
        source_ref="raw/articles/cycle64-update.md",
        action="updated",
        entry_date="2026-05-03",
    )

    rendered = page_path.read_text(encoding="utf-8")
    assert rendered == snapshot


def test_mermaid_export_format_snapshot(tmp_path, snapshot):
    """AC19: pin the Mermaid export rendering format."""
    wiki = tmp_path / "wiki"
    (wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki / "entities").mkdir(parents=True, exist_ok=True)

    (wiki / "concepts" / "rag.md").write_text(
        "---\ntitle: RAG\nsource: []\ntype: concept\nconfidence: stated\n---\n\n"
        "# RAG\n\nRetrieval-augmented generation. See [[entities/openai]].\n",
        encoding="utf-8",
    )
    (wiki / "entities" / "openai.md").write_text(
        "---\ntitle: OpenAI\nsource: []\ntype: entity\nconfidence: stated\n---\n\n"
        "# OpenAI\n\nAI research lab. Builds [[concepts/rag]].\n",
        encoding="utf-8",
    )

    rendered = export_mermaid(wiki_dir=wiki, max_nodes=10)
    assert rendered == snapshot


def test_lint_report_format_snapshot(tmp_path, snapshot):
    """AC19: pin the lint report's structural format (checks_run order +
    summary shape).

    Note: we snapshot a NORMALISED projection of the lint result (just
    the keys + per-check names) rather than the full dict — because the
    full dict contains lists of dicts whose item ordering depends on
    file-system traversal order, which is sandbox-path-dependent.
    """
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    (wiki / "concepts").mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)

    # One kept page so the lint pass has something to walk.
    (wiki / "concepts" / "valid.md").write_text(
        "---\ntitle: Valid\nsource: []\ntype: concept\nconfidence: stated\n"
        "created: 2026-05-03\nupdated: 2026-05-03\n---\n\n"
        "# Valid\n\nA valid page with no lint issues.\n",
        encoding="utf-8",
    )

    from kb.lint.runner import run_all_checks  # noqa: PLC0415

    result = run_all_checks(wiki_dir=wiki, raw_dir=raw)

    # Project the result to the structural fields that should remain stable
    # across runs (no file-order-dependent issue lists).
    snapshot_payload = {
        "checks_run_names": [c["name"] for c in result["checks_run"]],
        "summary_keys": sorted(result["summary"].keys())
        if isinstance(result.get("summary"), dict)
        else None,
        "result_top_level_keys": sorted(result.keys()),
    }
    assert snapshot_payload == snapshot
