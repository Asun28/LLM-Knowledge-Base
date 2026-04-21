"""Cycle 22 regression pins for wiki-path guard + extraction grounding clause.

Covers AC10-AC13 of cycle 22:
- AC10: ingest_source rejects a path inside the default WIKI_DIR with
        ValidationError and a fixed (non-path) message.
- AC11: same guard fires when the caller passes a custom ``wiki_dir=`` arg.
- AC12: a legitimate ``raw/articles/*.md`` path passes the guard and reaches
        downstream pipeline stages (happy path revert-detector).
- AC13: ``build_extraction_prompt`` output contains the grounding clause and
        the clause appears BEFORE the ``<source_document>`` fence, so
        adversarial raw content cannot reflect a counter-instruction.

Test-design notes:
- ``ValidationError`` is imported inside each test function to late-bind
  against the current ``kb.errors`` module object — defeats the cycle-20 L1
  reload-drift class where a sibling test's ``importlib.reload(kb.config)``
  would leave ``pytest.raises(OLD_CLS)`` unable to catch ``NEW_CLS``.
- AC12 monkeypatches ``extract_from_source`` + ``inject_wikilinks_batch`` to
  short-circuit the LLM + cascade-link passes; we only need to prove the
  guard does NOT reject the raw-dir path.
"""

from __future__ import annotations

import pytest

# ── AC10 — default WIKI_DIR rejection ─────────────────────────────────────────


def test_ac10_ingest_source_rejects_path_inside_default_wiki_dir(tmp_kb_env):
    """A path inside the default WIKI_DIR raises ValidationError.

    The error message is a fixed string — asserts no absolute path leaks
    through str(excinfo.value) (closes T3 path disclosure).
    """
    from kb.errors import ValidationError
    from kb.ingest.pipeline import ingest_source

    fake_wiki_page = tmp_kb_env / "wiki" / "entities" / "fake.md"
    fake_wiki_page.write_text(
        "---\ntitle: Fake\ntype: entity\nconfidence: stated\n"
        "source:\n  - raw/articles/fake.md\n---\n\nFake body.",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        ingest_source(fake_wiki_page)

    msg = str(excinfo.value)
    assert msg == "Source path must not be inside wiki directory", (
        f"ValidationError message must be the fixed string; got: {msg!r}"
    )
    # T3: absolute path segments must not leak into the error message.
    assert str(fake_wiki_page) not in msg
    assert str(tmp_kb_env) not in msg


# ── AC11 — custom wiki_dir= rejection ─────────────────────────────────────────


def test_ac11_ingest_source_rejects_path_inside_custom_wiki_dir(tmp_path):
    """Guard fires for caller-supplied ``wiki_dir=`` outside of WIKI_DIR default."""
    from kb.errors import ValidationError
    from kb.ingest.pipeline import ingest_source

    custom_wiki = tmp_path / "custom_wiki"
    (custom_wiki / "entities").mkdir(parents=True)
    (custom_wiki / "raw" / "articles").mkdir(parents=True)
    fake_page = custom_wiki / "entities" / "fake.md"
    fake_page.write_text(
        "---\ntitle: Fake\ntype: entity\nconfidence: stated\n"
        "source:\n  - raw/articles/fake.md\n---\n\nFake body.",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as excinfo:
        ingest_source(fake_page, wiki_dir=custom_wiki)

    assert str(excinfo.value) == "Source path must not be inside wiki directory"


# ── AC12 — raw/ path passes the guard (happy-path revert-detector) ────────────


def test_ac12_ingest_source_allows_raw_articles_path(tmp_kb_env, monkeypatch):
    """A legitimate ``raw/articles/*.md`` path passes the new wiki-dir guard.

    Revert-detector: if AC1-AC4 are reverted such that NO ingest_source path
    is allowed, this test fails at the guard. If the guard is wired to the
    wrong variable (e.g. raw_dir by mistake), this also fails.

    The test monkeypatches the LLM extraction + wikilink cascade so we only
    exercise the guard → extract → ingest pipeline up to page-write without
    touching the network or full wikilink scan.
    """
    import kb.ingest.pipeline as pipeline_mod

    raw_article = tmp_kb_env / "raw" / "articles" / "cycle22_happy_path.md"
    raw_article.write_text(
        "# Cycle 22 happy path\n\nBody text about the cycle 22 happy-path test.",
        encoding="utf-8",
    )

    def fake_extract(content, source_type, wiki_dir=None):
        return {
            "title": "Cycle 22 happy path",
            "summary": "A smoke-test article.",
            "key_claims": [],
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }

    monkeypatch.setattr(pipeline_mod, "extract_from_source", fake_extract)
    # inject_wikilinks_batch is imported function-locally inside ingest_source
    # from kb.compile.linker — patch at the source module. With an empty
    # entities/concepts extraction, the batch is a no-op anyway, but the patch
    # keeps the test hermetic regardless of pipeline internals.
    import kb.compile.linker as linker_mod

    monkeypatch.setattr(linker_mod, "inject_wikilinks_batch", lambda *a, **kw: {})

    # Guard must NOT raise ValidationError for this path. Any OTHER exception
    # downstream is acceptable — this test only pins the guard-pass behaviour.
    result = pipeline_mod.ingest_source(raw_article, source_type="article")
    # Result is either a "pages_created" dict or a "duplicate" dict — both are
    # past the guard and prove AC12.
    assert isinstance(result, dict)
    assert "pages_created" in result or result.get("duplicate") is True


# ── AC13 — grounding clause present AND precedes <source_document> fence ──────


def test_ac13_build_extraction_prompt_contains_grounding_before_fence():
    """The grounding clause must appear in every extraction prompt, and it must
    sit BEFORE the ``<source_document>`` sentinel fence so adversarial raw
    content inside the fence cannot reflect a counter-instruction (T6).

    Positive-phrased assertion per Opus 4.7 literal-instruction rule — we
    check for the canonical clause text exactly.
    """
    from kb.ingest.extractors import build_extraction_prompt, load_template

    for source_type in ("article", "paper", "repo", "video", "podcast"):
        tpl = load_template(source_type)
        prompt = build_extraction_prompt("smoke-test content", tpl)

        clause = "Ground every extracted field in verbatim source content."
        assert clause in prompt, (
            f"source_type={source_type!r}: grounding clause missing from prompt"
        )

        clause_idx = prompt.index(clause)
        fence_idx = prompt.index("<source_document>")
        assert clause_idx < fence_idx, (
            f"source_type={source_type!r}: grounding clause must appear BEFORE "
            f"the <source_document> fence so adversarial content cannot reflect "
            f"a counter-instruction (T6). Got clause_idx={clause_idx}, fence_idx={fence_idx}."
        )
