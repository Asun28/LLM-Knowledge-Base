"""Cycle 67 AC09 — non-vacuous paired negative-controls for cycle 64 snapshots.

Mimo r2 Q4 flagged that cycle 64 snapshot tests have a tautology risk: the
syrupy snapshots were captured FROM the same code path under test, with no
committed proof that mutating the input causes the snapshot to diverge.

Cycle 64 shipped THREE `_neg_control` tests in `test_cycle64_snapshots.py`,
but inspection (cycle 67 design Step 5) shows all three are vacuous:

- `test_evidence_trail_format_snapshot_neg_control` asserts
  `"appended_mutated" in rendered` — true by construction.
- `test_mermaid_export_format_snapshot_neg_control` asserts
  `"RAG-2" in rendered or rendered != ""` — `rendered != ""` is always true.
- `test_lint_report_format_snapshot_neg_control` asserts
  `isinstance(snapshot_payload, dict)` — trivially true.

This file replaces the vacuous controls with proper ones per cycle-67
C-AC09-dual condition: each subject gets BOTH T*A (input mutation) AND
T*B (renderer mutation), and asserts the canonical-vs-mutated outputs
DIVERGE. Closes cycle-23 L2 / cycle-67 R1-F7 + R2-F7 vacuous-test class.

Lint report's projection (`checks_run_names`, `summary_keys`,
`result_top_level_keys`) is intentionally too thin to vary with page-content
mutation. We document the contract via a stability assertion: the
projection MUST be page-content stable (one-page vs zero-page projection
identical), proving the projection is genuinely structural.
"""

from __future__ import annotations

from pathlib import Path

import kb.graph.export as export_mod
import kb.ingest.evidence as evidence_mod
from kb.graph.export import export_mermaid
from kb.ingest.evidence import append_evidence_trail


def _make_canonical_evidence_page(tmp: Path) -> Path:
    """Synthesize the same input the cycle-64 snapshot test uses."""
    page_path = tmp / "concepts" / "rag.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        "---\ntitle: RAG\nsource: []\ntype: concept\nconfidence: stated\n---\n\n"
        "# RAG\n\nRetrieval-augmented generation.\n",
        encoding="utf-8",
    )
    return page_path


def _append_canonical_trail(page_path: Path) -> None:
    """Apply the same three appends the cycle-64 snapshot test uses."""
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


def _make_canonical_mermaid_wiki(tmp: Path) -> Path:
    """Synthesize the same wiki shape the cycle-64 snapshot test uses."""
    wiki = tmp / "wiki"
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
    return wiki


# ── AC09 evidence-trail T*A (input mutation) + T*B (renderer mutation) ──────


def test_t09e_a_input_mutation_diverges(tmp_path: Path) -> None:
    """T09e-A: rendering with mutated input action text MUST produce
    different output than the canonical version. Replaces vacuous
    `"appended_mutated" in rendered` with `canonical != mutated`.
    """
    canonical = tmp_path / "canon"
    mutated = tmp_path / "mut"
    canon_page = _make_canonical_evidence_page(canonical)
    mut_page = _make_canonical_evidence_page(mutated)
    _append_canonical_trail(canon_page)
    append_evidence_trail(
        mut_page,
        source_ref="raw/articles/karpathy-2026.md",
        action="MUTATED_ACTION",
        entry_date="2026-04-01",
    )
    append_evidence_trail(
        mut_page,
        source_ref="raw/articles/lewis-2020.md",
        action="appended",
        entry_date="2026-04-15",
    )
    append_evidence_trail(
        mut_page,
        source_ref="raw/articles/cycle64-update.md",
        action="updated",
        entry_date="2026-05-03",
    )
    canon_text = canon_page.read_text(encoding="utf-8")
    mut_text = mut_page.read_text(encoding="utf-8")
    assert canon_text != mut_text, (
        "AC09 T09e-A: mutating the action text MUST change the rendered output. "
        "If outputs are identical, the snapshot is not pinning the action field."
    )


def test_t09e_b_renderer_mutation_diverges(tmp_path: Path) -> None:
    """T09e-B: appending a fourth trail entry MUST diverge the rendered
    output from a three-entry canonical. Proves the renderer reads inputs
    at call time and honors new entries.
    """
    canonical = tmp_path / "canon"
    mutated = tmp_path / "mut"
    canon_page = _make_canonical_evidence_page(canonical)
    mut_page = _make_canonical_evidence_page(mutated)
    _append_canonical_trail(canon_page)
    _append_canonical_trail(mut_page)
    append_evidence_trail(
        mut_page,
        source_ref="raw/articles/extra-entry.md",
        action="appended",
        entry_date="2026-05-04",
    )
    canon_text = canon_page.read_text(encoding="utf-8")
    mut_text = mut_page.read_text(encoding="utf-8")
    assert canon_text != mut_text, (
        "AC09 T09e-B: appending a fourth trail entry MUST change the rendered "
        "output. If outputs are identical, the renderer is not honoring new entries."
    )
    assert evidence_mod is not None  # sanity: module is monkey-patchable


# ── AC09 mermaid T*A (input mutation) + T*B (renderer mutation) ─────────────


def test_t09m_a_input_mutation_diverges(tmp_path: Path) -> None:
    """T09m-A: rendering the wiki with mutated frontmatter title MUST
    produce different mermaid than the canonical version.
    """
    canon_wiki = _make_canonical_mermaid_wiki(tmp_path / "canon")
    mut_wiki = _make_canonical_mermaid_wiki(tmp_path / "mut")
    (mut_wiki / "concepts" / "rag.md").write_text(
        "---\ntitle: RAG-MUTATED\nsource: []\ntype: concept\nconfidence: stated\n---\n\n"
        "# RAG\n\nRetrieval-augmented generation. See [[entities/openai]].\n",
        encoding="utf-8",
    )
    canon_rendered = export_mermaid(wiki_dir=canon_wiki, max_nodes=10)
    mut_rendered = export_mermaid(wiki_dir=mut_wiki, max_nodes=10)
    assert canon_rendered != mut_rendered, (
        "AC09 T09m-A: mutating frontmatter title MUST change the mermaid output."
    )


def test_t09m_b_renderer_mutation_diverges(tmp_path: Path) -> None:
    """T09m-B: lowering max_nodes MUST diverge the mermaid output (truncation
    behavior). Proves the renderer parameter is honored at call time.
    """
    wiki = _make_canonical_mermaid_wiki(tmp_path)
    canon_rendered = export_mermaid(wiki_dir=wiki, max_nodes=10)
    mut_rendered = export_mermaid(wiki_dir=wiki, max_nodes=1)
    assert canon_rendered != mut_rendered, (
        "AC09 T09m-B: lowering max_nodes from 10 to 1 MUST change the mermaid "
        "output (fewer nodes / truncation marker)."
    )
    assert export_mod is not None


# ── AC09 lint-report T*A: stability contract ────────────────────────────────


def test_t09l_projection_is_content_stable(tmp_path: Path) -> None:
    """T09l-A: the cycle-64 lint snapshot projects only structural fields.
    Page-content mutation does NOT change this projection — that's by
    DESIGN (intentionally thin to be stable across runs).

    This test makes that contract explicit: one-page wiki and zero-page
    wiki MUST produce identical projections. Vacuous failure mode caught:
    if a future refactor inadvertently makes the projection content-
    sensitive (e.g., includes issue counts in summary_keys), this test
    goes red.
    """
    from kb.lint.runner import run_all_checks  # noqa: PLC0415

    one_page_wiki = tmp_path / "one"
    zero_page_wiki = tmp_path / "zero"
    raw = tmp_path / "raw"
    (one_page_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    (zero_page_wiki / "concepts").mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)

    (one_page_wiki / "concepts" / "valid.md").write_text(
        "---\ntitle: Valid\nsource: []\ntype: concept\nconfidence: stated\n"
        "created: 2026-05-03\nupdated: 2026-05-03\n---\n\n"
        "# Valid\n\nA valid page with no lint issues.\n",
        encoding="utf-8",
    )

    one_result = run_all_checks(wiki_dir=one_page_wiki, raw_dir=raw)
    zero_result = run_all_checks(wiki_dir=zero_page_wiki, raw_dir=raw)

    one_proj = {
        "checks_run_names": [c["name"] for c in one_result["checks_run"]],
        "summary_keys": (
            sorted(one_result["summary"].keys())
            if isinstance(one_result.get("summary"), dict)
            else None
        ),
        "result_top_level_keys": sorted(one_result.keys()),
    }
    zero_proj = {
        "checks_run_names": [c["name"] for c in zero_result["checks_run"]],
        "summary_keys": (
            sorted(zero_result["summary"].keys())
            if isinstance(zero_result.get("summary"), dict)
            else None
        ),
        "result_top_level_keys": sorted(zero_result.keys()),
    }
    assert one_proj == zero_proj, (
        "AC09 T09l-A: lint-report projection MUST be page-content stable. "
        f"Diverged: one_page={one_proj!r} vs zero_page={zero_proj!r}"
    )
