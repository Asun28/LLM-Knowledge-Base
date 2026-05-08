"""Cycle 70 AC06-AC08 — snapshot subjects deferred from cycle-64 R3.

Pins three additional production functions:

- AC06: ``kb.ingest.pipeline._build_summary_content`` — page-rendering for
  the summary page (entities/concepts/key_claims). Per design.md A1:
  fixture uses ``key_claims`` (NOT ``contradictions`` — the function does
  NOT process contradictions, verified by R1 Opus design eval).

- AC07: ``kb.compile.publish.build_llms_full_txt`` — /llms-full.txt artifact
  body (page concatenation with separators). Per design.md C3: fixture
  frontmatter sets explicit ``title``/``created``/``updated`` (no
  autopopulation); ``incremental=False`` forces full rebuild.

- AC08: ``kb.compile.publish.build_graph_jsonld`` — /graph.jsonld artifact
  (schema.org CreativeWork JSON-LD). Per design.md A4: assertion
  re-parses production output via ``json.loads`` then canonicalizes via
  ``json.dumps(..., sort_keys=True, indent=2)`` — production code
  remains insertion-order; the assertion-side canonicalization decouples
  the snapshot from future production-side dict-key reorderings.

Each AC ships a positive snapshot + paired negative-control (per cycle-67
AC09 non-vacuous-snapshot rule).

Determinism vectors (per design.md C2):
- ``_build_summary_content``: no ``datetime.now``, no ``os.urandom``, no
  random seeds; dict iteration is insertion-order stable in Python 3.7+;
  ``slugify`` / ``sanitize_extraction_field`` / ``wikilink_display_escape``
  / ``_is_untitled_sentinel`` are all input-deterministic.
- ``build_llms_full_txt`` + ``build_graph_jsonld``: pages are sorted by
  ``page_id`` via ``_sort_pages`` (deterministic); fixture frontmatter
  has explicit dates (no clock reads); ``LLMS_FULL_MAX_BYTES`` is a
  config constant; UTF-8 byte counts and separator strings are static.
- AC08 also re-parses + sort_keys for additional decoupling from
  production insertion-order changes.
"""

from __future__ import annotations

import json
from pathlib import Path

# ── Shared fixture (cycle-50 helper-homing pattern, design.md Q4) ──


def _build_fixture_wiki(tmp_path: Path) -> Path:
    """Build a deterministic 3-page wiki fixture for AC07 + AC08.

    Returns the wiki_dir. Pages have explicit dates (no autopopulation),
    no body timestamps, and a fixed wikilink graph used by AC08:
        concepts/transformer  ->  [[concepts/attention]] + [[entities/google]]
        concepts/attention    ->  [[concepts/transformer]]
        entities/google       ->  (no outbound links)
    """
    wiki_dir = tmp_path / "wiki"
    for sub in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki_dir / sub).mkdir(parents=True)

    transformer = wiki_dir / "concepts" / "transformer.md"
    transformer.write_text(
        '---\n'
        'title: "Transformer"\n'
        'source:\n'
        '  - raw/articles/aiayn.md\n'
        'created: 2026-05-08\n'
        'updated: 2026-05-08\n'
        'type: concept\n'
        'confidence: stated\n'
        '---\n'
        '\n'
        '# Transformer\n'
        '\n'
        'A neural net architecture using [[concepts/attention]] '
        'introduced by [[entities/google]].\n',
        encoding="utf-8",
    )

    attention = wiki_dir / "concepts" / "attention.md"
    attention.write_text(
        '---\n'
        'title: "Attention"\n'
        'source:\n'
        '  - raw/articles/aiayn.md\n'
        'created: 2026-05-08\n'
        'updated: 2026-05-08\n'
        'type: concept\n'
        'confidence: stated\n'
        '---\n'
        '\n'
        '# Attention\n'
        '\n'
        'A weighted-sum mechanism. Used by [[concepts/transformer]].\n',
        encoding="utf-8",
    )

    google = wiki_dir / "entities" / "google.md"
    google.write_text(
        '---\n'
        'title: "Google"\n'
        'source:\n'
        '  - raw/articles/aiayn.md\n'
        'created: 2026-05-08\n'
        'updated: 2026-05-08\n'
        'type: entity\n'
        'confidence: stated\n'
        '---\n'
        '\n'
        '# Google\n'
        '\n'
        'Tech company that published the Transformer paper.\n',
        encoding="utf-8",
    )

    return wiki_dir


# ── AC06: _build_summary_content snapshot (no contradictions, A1) ──


_AC06_EXTRACTION = {
    "title": "Attention Is All You Need",
    "authors": ["Vaswani", "Shazeer"],  # 2 authors -> Authors line (plural)
    "core_argument": (
        "A purely attention-based seq2seq model outperforms "
        "recurrent encoders on translation."
    ),
    "key_claims": [
        "Self-attention captures long-range dependencies in O(1) sequential ops.",
        "Multi-head attention learns multiple projection subspaces.",
    ],
    "entities_mentioned": ["Google", "Transformer", "Vaswani"],
    "concepts_mentioned": ["Attention", "Encoder-Decoder"],
}


def test_build_summary_content_snapshot(snapshot):
    """AC06: pin ``_build_summary_content`` for a fixed extraction dict.

    Per design.md A1: fixture has 3 entities_mentioned + 2
    concepts_mentioned + 2 key_claims + 2 authors + 1 core_argument
    (NO contradictions — the function does not process them).

    Determinism: no datetime/random; dict insertion order stable.
    """
    from kb.ingest.pipeline import _build_summary_content

    rendered = _build_summary_content(_AC06_EXTRACTION, "article")
    assert rendered.splitlines() == snapshot


def test_build_summary_content_negative_control_entity_name():
    """AC06 negative-control: change the FIRST entity name; output differs."""
    from kb.ingest.pipeline import _build_summary_content

    extraction_a = dict(_AC06_EXTRACTION)
    extraction_b = dict(_AC06_EXTRACTION)
    extraction_b["entities_mentioned"] = ["Microsoft", "Transformer", "Vaswani"]

    rendered_a = _build_summary_content(extraction_a, "article")
    rendered_b = _build_summary_content(extraction_b, "article")
    assert rendered_a != rendered_b


# ── AC07: build_llms_full_txt snapshot (incremental=False, C3) ──


def test_build_llms_full_txt_snapshot(tmp_path, snapshot):
    """AC07: pin ``build_llms_full_txt`` output for a fixed 3-page wiki.

    Per design.md C3: fixture sets explicit dates (no autopopulation);
    body has no timestamps; ``incremental=False`` forces full rebuild.

    Determinism: pages sorted by page_id via ``_sort_pages``;
    UTF-8 byte counts deterministic; separator string is a static
    module constant; ``LLMS_FULL_MAX_BYTES`` is a config constant.
    """
    from kb.compile.publish import build_llms_full_txt

    wiki_dir = _build_fixture_wiki(tmp_path)
    out_path = tmp_path / "_publish" / "llms-full.txt"
    build_llms_full_txt(wiki_dir, out_path, incremental=False)
    rendered = out_path.read_text(encoding="utf-8")
    assert rendered.splitlines() == snapshot


def test_build_llms_full_txt_negative_control_body_change(tmp_path):
    """AC07 negative-control: change one page body; output differs."""
    from kb.compile.publish import build_llms_full_txt

    wiki_dir_a = _build_fixture_wiki(tmp_path / "a")
    wiki_dir_b = _build_fixture_wiki(tmp_path / "b")

    # Mutate ONE page body in fixture B
    attention_b = wiki_dir_b / "concepts" / "attention.md"
    text = attention_b.read_text(encoding="utf-8")
    attention_b.write_text(
        text.replace("A weighted-sum mechanism.", "A normalized softmax mechanism."),
        encoding="utf-8",
    )

    out_a = tmp_path / "_publish_a" / "llms-full.txt"
    out_b = tmp_path / "_publish_b" / "llms-full.txt"
    build_llms_full_txt(wiki_dir_a, out_a, incremental=False)
    build_llms_full_txt(wiki_dir_b, out_b, incremental=False)
    assert out_a.read_text(encoding="utf-8") != out_b.read_text(encoding="utf-8")


# ── AC08: build_graph_jsonld snapshot (re-parse + sort_keys, A4) ──


def test_build_graph_jsonld_snapshot(tmp_path, snapshot):
    """AC08: pin ``build_graph_jsonld`` output for a fixed 3-page wiki.

    Per design.md A4: assertion re-parses production JSON via
    ``json.loads`` then canonicalizes via
    ``json.dumps(..., sort_keys=True, indent=2)``. Production code is
    insertion-order; the assertion-side canonicalization decouples the
    snapshot from future production dict-key reorderings.

    Determinism: pages sorted by page_id; ``extract_wikilinks`` preserves
    source order (already lowercased + .md-stripped); citations sorted
    via id_to_url lookup over deterministically-sorted ``kept``.
    """
    from kb.compile.publish import build_graph_jsonld

    wiki_dir = _build_fixture_wiki(tmp_path)
    out_path = tmp_path / "_publish" / "graph.jsonld"
    build_graph_jsonld(wiki_dir, out_path, incremental=False)

    raw = out_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    canonicalized = json.dumps(parsed, sort_keys=True, indent=2)
    assert canonicalized.splitlines() == snapshot


def test_build_graph_jsonld_negative_control_remove_wikilink(tmp_path):
    """AC08 negative-control: remove one wikilink; canonicalized output differs."""
    from kb.compile.publish import build_graph_jsonld

    wiki_dir_a = _build_fixture_wiki(tmp_path / "a")
    wiki_dir_b = _build_fixture_wiki(tmp_path / "b")

    # Strip one wikilink from fixture B's transformer page
    transformer_b = wiki_dir_b / "concepts" / "transformer.md"
    text = transformer_b.read_text(encoding="utf-8")
    transformer_b.write_text(
        text.replace(" introduced by [[entities/google]]", ""),
        encoding="utf-8",
    )

    out_a = tmp_path / "_publish_a" / "graph.jsonld"
    out_b = tmp_path / "_publish_b" / "graph.jsonld"
    build_graph_jsonld(wiki_dir_a, out_a, incremental=False)
    build_graph_jsonld(wiki_dir_b, out_b, incremental=False)

    canonicalized_a = json.dumps(json.loads(out_a.read_text(encoding="utf-8")), sort_keys=True)
    canonicalized_b = json.dumps(json.loads(out_b.read_text(encoding="utf-8")), sort_keys=True)
    assert canonicalized_a != canonicalized_b
