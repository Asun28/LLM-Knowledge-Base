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


def test_ac10_ingest_source_rejects_path_inside_default_wiki_dir(tmp_path):
    """A path inside the default WIKI_DIR raises ValidationError.

    The error message is a fixed string — asserts no absolute path leaks
    through ``str(excinfo.value)`` (closes T3 path disclosure).

    Hermetic by construction: passes ``wiki_dir=<tmp>`` + ``raw_dir=<tmp>``
    explicitly so the test does NOT depend on the ``tmp_kb_env`` fixture's
    module-attribute mirror-rebind. Under full-suite ordering, a sibling
    test's ``importlib.reload(kb.config)`` can decouple
    ``kb.ingest.pipeline.WIKI_DIR`` (cycle-18 L1 snapshot-bind hazard) and
    cause fixture-based tests to hit the wrong default path.

    ``ValidationError`` is late-bound via ``pipeline_mod.ValidationError`` —
    NOT imported from ``kb.errors`` at the top of the test function — per
    cycle-20 L1: a sibling ``importlib.reload(kb.config)`` can cascade-reload
    ``kb.errors`` so that ``kb.errors.ValidationError`` becomes a NEW class
    object, while ``kb.ingest.pipeline.ValidationError`` retains the OLD
    one; ``pytest.raises(OLD_CLS)`` then cannot catch the NEW-CLS instance
    that production code raises. Late-binding via the production module
    guarantees the test catches exactly what production raises.
    """
    import kb.ingest.pipeline as pipeline_mod

    ValidationError = pipeline_mod.ValidationError  # late-bind (cycle-20 L1)

    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    (wiki / "entities").mkdir(parents=True)
    (raw / "articles").mkdir(parents=True)

    fake_wiki_page = wiki / "entities" / "fake.md"
    fake_wiki_page.write_text(
        "---\ntitle: Fake\ntype: entity\nconfidence: stated\n"
        "source:\n  - raw/articles/fake.md\n---\n\nFake body.",
        encoding="utf-8",
    )

    # Redirect the ingest_log.jsonl sink to this test's tmp dir so the T4
    # zero-row assertion reads THIS test's log, not the real project log.
    # Use monkeypatch via direct setattr on the module's lazy helper hooks
    # — _emit_ingest_jsonl reads ``kb.config.PROJECT_ROOT`` via the dynamic
    # attribute lookup added in cycle 18.
    from pytest import MonkeyPatch

    import kb.config as _kb_config

    mp = MonkeyPatch()
    try:
        mp.setattr(_kb_config, "PROJECT_ROOT", tmp_path)
        with pytest.raises(ValidationError) as excinfo:
            pipeline_mod.ingest_source(fake_wiki_page, wiki_dir=wiki, raw_dir=raw)
    finally:
        mp.undo()

    msg = str(excinfo.value)
    assert msg == "Source path must not resolve inside wiki/ directory", (
        f"ValidationError message must be the fixed string; got: {msg!r}"
    )
    # T3: absolute path segments must not leak into the error message.
    assert str(fake_wiki_page) not in msg
    assert str(tmp_path) not in msg

    # T4 zero-row pin (Step-14 R1 Codex MAJOR / R1 Sonnet MAJOR 2): the guard
    # fires BEFORE _emit_ingest_jsonl("start",...), so rejected wiki paths
    # must NOT emit any JSONL row. Under redirected PROJECT_ROOT the log would
    # land at ``<tmp_path>/.data/ingest_log.jsonl``. The expected behaviour
    # is either (a) the file does not exist, or (b) it is empty.
    jsonl_path = tmp_path / ".data" / "ingest_log.jsonl"
    if jsonl_path.exists():
        contents = jsonl_path.read_text(encoding="utf-8")
        assert contents == "", (
            f"Rejected wiki-path must not emit any ingest_log.jsonl rows "
            f"(T4 orphan-start guard). Got: {contents[:200]!r}"
        )


# ── AC11 — custom wiki_dir= rejection ─────────────────────────────────────────


def test_ac11_ingest_source_rejects_path_inside_custom_wiki_dir(tmp_path):
    """Guard fires for caller-supplied ``wiki_dir=`` outside of WIKI_DIR default.

    ``ValidationError`` late-bound via ``pipeline_mod.ValidationError`` per
    cycle-20 L1 (reload-drift defense — see AC10 docstring).
    """
    import kb.ingest.pipeline as pipeline_mod

    ValidationError = pipeline_mod.ValidationError  # late-bind (cycle-20 L1)

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
        pipeline_mod.ingest_source(fake_page, wiki_dir=custom_wiki)

    assert str(excinfo.value) == "Source path must not resolve inside wiki/ directory"


# ── AC11b — T1 symlink-into-wiki rejection (Step-14 R1 Sonnet MAJOR 3 pin) ────


def test_ac11b_ingest_source_rejects_symlink_into_wiki(tmp_path):
    """T1 filesystem-level regression pin: a file that LOOKS LIKE a raw path
    but ``.resolve()`` dereferences to a location inside wiki/ must be rejected.

    The original cycle-22 design claimed the guard closes T1 (symlink bypass)
    because ``Path(source_path).resolve()`` dereferences symlinks BEFORE the
    normcase+relative_to compare. This test exercises that path at the
    filesystem level. The prior AC11 test places the source directly in the
    wiki dir, which verifies the guard but does NOT verify the resolve-first
    ordering — a revert that dropped ``source_path = ...resolve()`` would
    pass the direct-path test while breaking symlink dereferencing.

    Skipped on platforms where os.symlink is unavailable or privileged.
    """
    import os as _os

    import kb.ingest.pipeline as pipeline_mod

    ValidationError = pipeline_mod.ValidationError  # late-bind (cycle-20 L1)

    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    (wiki / "entities").mkdir(parents=True)
    (raw / "articles").mkdir(parents=True)

    # Real wiki page (the symlink target).
    real_wiki_page = wiki / "entities" / "real.md"
    real_wiki_page.write_text(
        "---\ntitle: Real\ntype: entity\nconfidence: stated\nsource: []\n---\n\nBody.",
        encoding="utf-8",
    )

    # Symlink at raw/articles/sneaky.md → wiki/entities/real.md.
    symlink_source = raw / "articles" / "sneaky.md"
    try:
        _os.symlink(real_wiki_page, symlink_source)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"os.symlink unavailable on this platform / privilege: {e}")

    # Guard MUST dereference the symlink and reject the resolved wiki path.
    with pytest.raises(ValidationError) as excinfo:
        pipeline_mod.ingest_source(symlink_source, wiki_dir=wiki, raw_dir=raw)

    assert str(excinfo.value) == "Source path must not resolve inside wiki/ directory"


# ── AC12 — raw/ path passes the guard (happy-path revert-detector) ────────────


def test_ac12_ingest_source_allows_raw_articles_path(tmp_path, monkeypatch):
    """A legitimate ``raw/articles/*.md`` path passes the new wiki-dir guard.

    Revert-detector: if AC1-AC4 are reverted such that NO ingest_source path
    is allowed, this test fails at the guard. If the guard is wired to the
    wrong variable (e.g. raw_dir by mistake), this also fails.

    Passes ``wiki_dir`` + ``raw_dir`` explicitly (rather than relying on the
    ``tmp_kb_env`` fixture's module-attribute mirror-rebind) so the test is
    immune to the cycle-19 L2 reload-leak class where a sibling test's
    ``importlib.reload(kb.config)`` decouples ``kb.ingest.pipeline.WIKI_DIR``
    from ``kb.config.WIKI_DIR``.
    """
    import kb.ingest.pipeline as pipeline_mod

    # Set up an isolated wiki + raw under tmp_path.
    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    for sub in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / sub).mkdir(parents=True)
    (raw / "articles").mkdir(parents=True)
    (wiki / "index.md").write_text(
        "---\ntitle: Wiki Index\nsource: []\ntype: index\n---\n\n# Wiki Index\n",
        encoding="utf-8",
    )
    (wiki / "_sources.md").write_text(
        "---\ntitle: Sources\nsource: []\ntype: index\n---\n\n# Sources\n",
        encoding="utf-8",
    )
    (wiki / "log.md").write_text("# Log\n", encoding="utf-8")

    raw_article = raw / "articles" / "cycle22_happy_path.md"
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
    # from kb.compile.linker — patch at the source module.
    import kb.compile.linker as linker_mod

    monkeypatch.setattr(linker_mod, "inject_wikilinks_batch", lambda *a, **kw: {})

    # Explicit wiki_dir + raw_dir pass the guard without depending on the
    # module-top WIKI_DIR / RAW_DIR snapshots (which may be stale under
    # full-suite reload-leak — cycle-19 L2).
    result = pipeline_mod.ingest_source(
        raw_article,
        source_type="article",
        wiki_dir=wiki,
        raw_dir=raw,
    )
    # Result is either a "pages_created" dict or a "duplicate" dict — both are
    # past the guard and prove AC12.
    assert isinstance(result, dict)
    assert "pages_created" in result or result.get("duplicate") is True


# ── AC13 — grounding clause present AND precedes <source_document> fence ──────


def test_ac13_build_extraction_prompt_contains_grounding_before_fence(monkeypatch):
    """The grounding clause must appear in every extraction prompt, and it must
    sit BEFORE the ``<source_document>`` sentinel fence so adversarial raw
    content inside the fence cannot reflect a counter-instruction (T6).

    Positive-phrased assertion per Opus 4.7 literal-instruction rule — we
    check for the canonical clause text exactly.
    """
    from pathlib import Path as _Path

    import kb.ingest.extractors as extractors_mod
    from kb.ingest.extractors import build_extraction_prompt, load_template

    # Cycle-19 L2 reload-leak defense: if a sibling test ran
    # ``importlib.reload(kb.config)`` under a contaminated ``KB_PROJECT_ROOT``,
    # the LRU cache on ``_load_template_cached`` holds a stale path and
    # ``extractors.TEMPLATES_DIR`` itself may point at a tmp path that no
    # longer exists. Force the module attribute back to the canonical repo
    # templates directory and clear the cache before calling the builder.
    _real_templates = _Path(__file__).resolve().parent.parent / "templates"
    monkeypatch.setattr(extractors_mod, "TEMPLATES_DIR", _real_templates)
    extractors_mod._load_template_cached.cache_clear()

    # Step-14 R1 Sonnet NIT 2: anchor the FULL two-sentence clause rather
    # than just the first sentence, so a future refactor that splits the
    # sentences (or drops the null-fallback half) is caught.
    # Match the exact line-wrapped shape of the clause as it appears in
    # ``build_extraction_prompt``'s f-string (newline between the two
    # sentences — see extractors.py).
    full_clause = (
        "Ground every extracted field in verbatim source content. When uncertain\n"
        "whether a claim is in the source, use null."
    )

    for source_type in ("article", "paper", "repo", "video", "podcast"):
        tpl = load_template(source_type)
        prompt = build_extraction_prompt("smoke-test content", tpl)

        assert full_clause in prompt, (
            f"source_type={source_type!r}: full grounding clause missing from prompt"
        )

        clause_idx = prompt.index(full_clause)
        fence_idx = prompt.index("<source_document>")
        assert clause_idx < fence_idx, (
            f"source_type={source_type!r}: grounding clause must appear BEFORE "
            f"the <source_document> fence so adversarial content cannot reflect "
            f"a counter-instruction (T6). Got clause_idx={clause_idx}, fence_idx={fence_idx}."
        )
