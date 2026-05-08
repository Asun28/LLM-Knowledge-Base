"""Cycle 69 AC13-AC15 — snapshot subjects (cycle-64 deferred follow-up).

Three deferred snapshot subjects per design.md Group D:

- AC13: ``kb.ingest.extractors.build_extraction_prompt`` — function is
  deterministic by inputs (verified at extractors.py:276-333; zero datetime
  / os.environ / random refs). NO defensive monkeypatch needed. Pinned
  via fixed (content, template, purpose) triple.
- AC14: ``kb.ingest.pipeline._persist_contradictions`` — embeds
  ``date.today().isoformat()`` at pipeline.py:207. Per amendment A3:
  monkeypatch ``kb.ingest.pipeline.date`` with a ``FakeDate`` returning
  ``date(2026, 5, 8)`` so the contradictions block is deterministic.
- AC15: ``kb.lint.semantic._render_sources`` — uses
  ``QUERY_CONTEXT_MAX_CHARS`` from ``kb.config`` for truncation budget.
  Per cycle-18 L1, the import shape is ``from kb.config import
  QUERY_CONTEXT_MAX_CHARS`` so monkeypatching MUST target the importing
  module's snapshot (``kb.lint.semantic.QUERY_CONTEXT_MAX_CHARS``).

T15/T16 mitigations preserved per cycle-64: snapshot fixtures use
controlled inputs only (no os.environ / Path.home / production paths).
Default ``pytest`` invocation FAILs on drift; only ``--snapshot-update``
rewrites. CI does NOT pass that flag.

Each snapshot has a paired non-vacuous negative-control per cycle-67
AC09: mutate one input bit, assert the captured output DIFFERS from the
baseline (NOT just ``assert "X" in snapshot`` — that's vacuous).
"""

from __future__ import annotations

from datetime import date

# ── AC13: build_extraction_prompt deterministic snapshot ──────────


_AC13_TEMPLATE = {
    "name": "article",
    "description": "blog post or news article",
    "extract": ["title", "key_claims", "entities_mentioned"],
}
_AC13_CONTENT = (
    "# Attention is all you need\n\nThe transformer architecture replaces "
    "recurrence with self-attention.\n"
)


def test_build_extraction_prompt_snapshot(snapshot):
    """AC13: pin kb.ingest.extractors.build_extraction_prompt deterministic
    rendering for fixed (content, template, purpose) triple.
    """
    from kb.ingest.extractors import build_extraction_prompt

    rendered = build_extraction_prompt(
        content=_AC13_CONTENT,
        template=_AC13_TEMPLATE,
        purpose="extract_entities",
    )
    assert rendered == snapshot


def test_build_extraction_prompt_negative_control_purpose_change():
    """AC13 negative-control: mutate purpose from extract_entities to
    extract_concepts; rendered prompt must differ.
    """
    from kb.ingest.extractors import build_extraction_prompt

    rendered_a = build_extraction_prompt(
        content=_AC13_CONTENT, template=_AC13_TEMPLATE, purpose="extract_entities"
    )
    rendered_b = build_extraction_prompt(
        content=_AC13_CONTENT, template=_AC13_TEMPLATE, purpose="extract_concepts"
    )
    assert rendered_a != rendered_b


# ── AC14: _persist_contradictions deterministic snapshot ─────────


class _FakeDate:
    """Deterministic stand-in for datetime.date used in pipeline.py.

    Per amendment A3: monkeypatching ``kb.ingest.pipeline.date`` with
    this class freezes ``date.today().isoformat()`` to ``2026-05-08``.
    """

    @staticmethod
    def today():
        return date(2026, 5, 8)


def test_contradictions_append_snapshot(tmp_path, monkeypatch, snapshot):
    """AC14: pin contradictions block format produced by
    ``_persist_contradictions`` for a fixed pair of contradictory
    extractions.
    """
    import kb.ingest.pipeline as pipeline

    monkeypatch.setattr(pipeline, "date", _FakeDate)

    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    contradictions = [
        {"claim": "Transformers use recurrence"},
        {"claim": "Transformers eliminate recurrence"},
    ]
    pipeline._persist_contradictions(contradictions, "raw/articles/example.md", wiki_dir)
    rendered = (wiki_dir / "contradictions.md").read_text(encoding="utf-8")
    assert rendered.splitlines() == snapshot


def test_contradictions_append_negative_control_claim_text(tmp_path, monkeypatch):
    """AC14 negative-control: change second extraction's claim text;
    persisted block must differ.
    """
    import kb.ingest.pipeline as pipeline

    monkeypatch.setattr(pipeline, "date", _FakeDate)

    wiki_dir_a = tmp_path / "wiki_a"
    wiki_dir_b = tmp_path / "wiki_b"
    wiki_dir_a.mkdir()
    wiki_dir_b.mkdir()

    pipeline._persist_contradictions(
        [{"claim": "X"}, {"claim": "Y"}],
        "raw/x.md",
        wiki_dir_a,
    )
    pipeline._persist_contradictions(
        [{"claim": "X"}, {"claim": "Z"}],
        "raw/x.md",
        wiki_dir_b,
    )
    a = (wiki_dir_a / "contradictions.md").read_text(encoding="utf-8")
    b = (wiki_dir_b / "contradictions.md").read_text(encoding="utf-8")
    assert a != b


# ── AC15: _render_sources deterministic snapshot ─────────────────


_AC15_SOURCES = [
    {"path": "raw/articles/a.md", "content": "First src snippet — concise."},
    {"path": "raw/articles/b.md", "content": "Second snippet, also short."},
    {"path": "raw/articles/c.md", "content": "Third one — same shape."},
]


def test_lint_semantic_render_sources_snapshot(snapshot):
    """AC15: pin _render_sources output for a fixed list of 3 sources.

    Per amendment A9: each source body < 100 chars so _truncate_source
    does NOT fire on the positive snapshot (decoupling the snapshot
    from QUERY_CONTEXT_MAX_CHARS at the default config value).
    """
    from kb.lint.semantic import _render_sources

    lines: list[str] = []
    _render_sources(_AC15_SOURCES, lines)
    assert lines == snapshot


def test_lint_semantic_render_sources_negative_control_truncation(
    monkeypatch,
):
    """AC15 negative-control 2 (per A9): force _truncate_source to fire by
    monkeypatching ``kb.lint.semantic.QUERY_CONTEXT_MAX_CHARS`` to a small
    value. Output for a long source must differ vs default-config run.

    Per cycle-18 L1: monkeypatch the IMPORTING module's snapshot
    (semantic.py uses ``from kb.config import QUERY_CONTEXT_MAX_CHARS``,
    so ``kb.lint.semantic.QUERY_CONTEXT_MAX_CHARS`` is the captured
    name. ``kb.config.QUERY_CONTEXT_MAX_CHARS`` would NOT affect this
    code path post-import.)
    """
    from kb.lint import semantic

    long_source = [{"path": "raw/articles/long.md", "content": "x" * 5000}]
    lines_a: list[str] = []
    semantic._render_sources(long_source, lines_a)

    monkeypatch.setattr(semantic, "QUERY_CONTEXT_MAX_CHARS", 100)
    lines_b: list[str] = []
    semantic._render_sources(long_source, lines_b)

    assert lines_a != lines_b
