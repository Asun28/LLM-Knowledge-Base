"""Regression tests for the backlog-by-file cycle 1 batch (38 fixes).

Each test maps to one (or more) BACKLOG items that were closed in the
per-file commits on branch `fix/backlog-by-file-cycle1`. Groups mirror the
design spec in `docs/superpowers/specs/2026-04-17-backlog-by-file-cycle1-design.md`.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# ─────────────────────────────────────────────────────────────────────────
# Theme A — capture.py (A1-A6)
# ─────────────────────────────────────────────────────────────────────────


def test_a1_render_markdown_has_no_slug_param():
    """A1: `_render_markdown` signature no longer accepts `slug`."""
    import inspect

    from kb.capture import _render_markdown

    sig = inspect.signature(_render_markdown)
    assert "slug" not in sig.parameters


def test_a2_capture_schema_caps_body_length():
    """A2: body field carries maxLength=2000."""
    from kb.capture import _CAPTURE_SCHEMA

    body_schema = _CAPTURE_SCHEMA["properties"]["items"]["items"]["properties"]["body"]
    assert body_schema["maxLength"] == 2000


def test_a3_capture_items_accepts_captures_dir(tmp_path, monkeypatch):
    """A3: capture_items (public API) threads captures_dir through without
    monkeypatching the module-level CAPTURES_DIR constant.

    PR review round 1 (Sonnet MINOR): the prior test called _write_item_files
    directly, bypassing the public plumbing. This version exercises the real
    capture_items entry point with a fake LLM that returns a trivial item."""
    from kb import capture

    # Stub out LLM + rate limit so the public API reaches the write path
    # deterministically.
    def fake_extract(normalized):
        return {
            "items": [
                {
                    "title": "Pick atomic N-files",
                    "kind": "decision",
                    "body": "We chose N-files for atomicity.",
                    "one_line_summary": "N-files preserve raw immutability.",
                    "confidence": "stated",
                }
            ],
            "filtered_out_count": 0,
        }

    monkeypatch.setattr(capture, "_extract_items_via_llm", fake_extract)
    monkeypatch.setattr(capture, "_check_rate_limit", lambda: (True, 0))
    # Identity verifier — accept the fake body verbatim
    monkeypatch.setattr(
        capture,
        "_verify_body_is_verbatim",
        lambda raw_items, normalized: (list(raw_items), 0),
    )

    result = capture.capture_items(
        "We chose N-files for atomicity.",
        provenance="test",
        captures_dir=tmp_path,
    )
    assert result.rejected_reason is None, result.rejected_reason
    assert len(result.items) == 1
    assert result.items[0].path.is_relative_to(tmp_path)


def test_a4_secret_regex_catches_anthropic_api_key_suffix():
    """A4: env-var regex matches ANTHROPIC_API_KEY, DJANGO_SECRET_KEY, GH_TOKEN."""
    from kb.capture import _scan_for_secrets

    positives = [
        "ANTHROPIC_API_KEY=abcdefgh12345",
        "DJANGO_SECRET_KEY=django-insecure-xxxxyyyy",
        "GH_TOKEN=ghpxxxxyyyyzzzz",
        "export API_KEY=abcdefgh12",  # export prefix
    ]
    for s in positives:
        assert _scan_for_secrets(s) is not None, f"expected secret match for: {s!r}"

    negatives = [
        "TOKEN_EXPIRY=3600",  # short value, not a secret
        "MY_FIELD=ab",  # short, not a credential field name
    ]
    for s in negatives:
        assert _scan_for_secrets(s) is None, f"expected no match for: {s!r}"


def test_a5_captures_dir_resolved_cached():
    """A5: module-level _CAPTURES_DIR_RESOLVED exposed for cached path checks."""
    from kb import capture

    assert hasattr(capture, "_CAPTURES_DIR_RESOLVED")
    assert isinstance(capture._CAPTURES_DIR_RESOLVED, Path)


def test_a6_authorization_regex_matches_bearer():
    """A6: Authorization: Bearer <16+ chars> is detected."""
    from kb.capture import _scan_for_secrets

    assert _scan_for_secrets("Authorization: Bearer abcdefghijklmnop1234") is not None
    # Short Bearer should not false-positive
    assert _scan_for_secrets("Authorization: Bearer abc") is None


def test_a4_env_var_regex_matches_quoted_value_with_spaces():
    """PR review round 1 (Codex M-NEW-2): quoted values containing spaces
    must be caught — previously `\\S{8,}` stopped at the first whitespace."""
    from kb.capture import _scan_for_secrets

    positives = [
        'SECRET="has spaces and is still a long secret"',
        "API_KEY='quoted with spaces is still secret'",
        'DATABASE_URL="postgres://u:p@host/db with spaces"',
    ]
    for s in positives:
        assert _scan_for_secrets(s) is not None, f"expected match for: {s!r}"


# ─────────────────────────────────────────────────────────────────────────
# Theme B — augment family (wave 0 already shipped; this confirms surface)
# ─────────────────────────────────────────────────────────────────────────


def test_b1_run_augment_has_data_dir_param():
    """B1/B2/B3: run_augment accepts data_dir, raw_dir kwargs."""
    import inspect

    from kb.lint.augment import run_augment

    sig = inspect.signature(run_augment)
    assert "data_dir" in sig.parameters
    assert "raw_dir" in sig.parameters


def test_b2_manifest_accepts_data_dir(tmp_path):
    """B2: Manifest.start honors data_dir override."""
    from kb.lint._augment_manifest import Manifest

    data_dir = tmp_path / "custom_data"
    m = Manifest.start(run_id="abc123", mode="propose", max_gaps=3, stubs=[], data_dir=data_dir)
    assert m.path.is_relative_to(data_dir)


def test_b3_rate_limiter_accepts_data_dir(tmp_path):
    """B3: RateLimiter stores state under supplied data_dir."""
    from kb.lint._augment_rate import RateLimiter

    data_dir = tmp_path / "custom_data"
    limiter = RateLimiter(data_dir=data_dir)
    assert limiter._rate_path.is_relative_to(data_dir)


def test_b4_run_augment_rejects_negative_max_gaps(tmp_path):
    """B4: max_gaps < 1 raises ValueError before any state is touched."""
    from kb.lint.augment import run_augment

    wiki = tmp_path / "wiki"
    for sub in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        (wiki / sub).mkdir(parents=True)
    with pytest.raises(ValueError, match="max_gaps"):
        run_augment(wiki_dir=wiki, max_gaps=0)
    with pytest.raises(ValueError, match="max_gaps"):
        run_augment(wiki_dir=wiki, max_gaps=-1)


# ─────────────────────────────────────────────────────────────────────────
# Theme C — ingest/pipeline.py (wave 0 shipped C1-C3)
# ─────────────────────────────────────────────────────────────────────────


def test_c1_ingest_source_has_raw_dir_param():
    """C1: ingest_source accepts raw_dir kwarg."""
    import inspect

    from kb.ingest.pipeline import ingest_source

    sig = inspect.signature(ingest_source)
    assert "raw_dir" in sig.parameters


def test_c2_ingest_rejects_unsupported_suffix(tmp_project):
    """C2: ingest_source rejects extensions not in SUPPORTED_SOURCE_EXTENSIONS."""
    from kb.ingest.pipeline import ingest_source

    bad = tmp_project / "raw" / "articles" / "README"
    bad.write_text("no suffix", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported source extension"):
        ingest_source(bad, source_type="article", extraction={}, raw_dir=tmp_project / "raw")


# ─────────────────────────────────────────────────────────────────────────
# Theme D — ingest/extractors.py (D1 deepcopy, D2a purpose cap)
# ─────────────────────────────────────────────────────────────────────────


def test_d1_cached_schema_is_deepcopied_per_extraction(monkeypatch):
    """D1: extract_from_source deepcopies the cached schema so an SDK mutation
    in one call cannot poison the next.

    PR review round 1 (Opus MAJOR): the prior test exercised copy.deepcopy
    directly and would pass even if `extract_from_source` stopped deepcopying.
    This test instead stubs `call_llm_json` to MUTATE the schema it receives
    and verifies the next call sees a pristine copy."""
    from kb.ingest import extractors

    # Clear any previous cached schema so the first call populates it fresh.
    extractors._build_schema_cached.cache_clear()

    seen_schemas: list[dict] = []
    call_counter = {"n": 0}

    def mutating_stub(prompt, *, tier, system, schema, tool_description):
        seen_schemas.append(schema)
        call_counter["n"] += 1
        # Mutate only on the first call. The second call must receive a
        # pristine schema — if extract_from_source skipped the deepcopy,
        # the mutation from call 1 would still be visible because lru_cache
        # returns the same object.
        if call_counter["n"] == 1:
            schema["properties"]["POISONED_FROM_SDK"] = True
        return {
            "title": "X",
            "entities_mentioned": [],
            "concepts_mentioned": [],
        }

    monkeypatch.setattr(extractors, "call_llm_json", mutating_stub)
    monkeypatch.setattr(extractors, "load_purpose", lambda _d=None: None)

    extractors.extract_from_source("body one", "article")
    extractors.extract_from_source("body two", "article")

    assert len(seen_schemas) == 2
    # Each call must receive its OWN schema object (distinct ids) AND the
    # second call must not inherit the poison the first injected.
    assert seen_schemas[0] is not seen_schemas[1]
    assert "POISONED_FROM_SDK" not in seen_schemas[1].get("properties", {})


def test_d2a_purpose_caps_at_4kb():
    """D2a: build_extraction_prompt truncates purpose to 4096 chars."""
    from kb.ingest.extractors import build_extraction_prompt, load_template

    tmpl = load_template("article")
    big_purpose = "X" * 10_000
    prompt = build_extraction_prompt("body", tmpl, purpose=big_purpose)
    # Count how many times X repeats; must be ≤ 4096
    x_count = prompt.count("X")
    assert x_count <= 4096, f"purpose not capped, found {x_count} X's"


# ─────────────────────────────────────────────────────────────────────────
# Theme E — ingest/contradiction.py (E1 preserve language tokens)
# ─────────────────────────────────────────────────────────────────────────


def test_e1_preserves_language_name_tokens():
    """E1: short language names survive tokenization."""
    from kb.ingest.contradiction import _extract_significant_tokens

    tokens = _extract_significant_tokens("C and R are used. C++ and F# and .NET too.")
    assert "c" in tokens
    assert "r" in tokens
    assert "c++" in tokens
    assert "f#" in tokens


# ─────────────────────────────────────────────────────────────────────────
# Theme F — mcp/quality.py (F2 refine caps; F3/F4 create validation)
# ─────────────────────────────────────────────────────────────────────────


def test_f2_refine_caps_notes(monkeypatch, tmp_path):
    """F2: kb_refine_page rejects oversized revision_notes."""
    from kb.config import MAX_NOTES_LEN
    from kb.mcp.quality import kb_refine_page

    result = kb_refine_page("concepts/x", "body text", revision_notes="n" * (MAX_NOTES_LEN + 1))
    assert result.startswith("Error: revision_notes too long")


def test_f2_refine_caps_page_id(monkeypatch):
    """F2: kb_refine_page rejects oversized page_id."""
    from kb.mcp.quality import kb_refine_page

    result = kb_refine_page("a" * 201, "body text")
    assert result.startswith("Error: page_id too long")


# ─────────────────────────────────────────────────────────────────────────
# Theme G — mcp/browse.py (G2 search length cap; G3 kb_read_page ambiguity)
# ─────────────────────────────────────────────────────────────────────────


def test_g2_search_rejects_overlong_query():
    """G2: kb_search rejects queries over MAX_QUESTION_LEN."""
    from kb.config import MAX_QUESTION_LEN
    from kb.mcp.browse import kb_search

    result = kb_search("x" * (MAX_QUESTION_LEN + 1))
    assert result.startswith("Error: Query too long")


# ─────────────────────────────────────────────────────────────────────────
# Theme H — mcp/core.py (H1 stat check, H2 source_type allowlist)
# ─────────────────────────────────────────────────────────────────────────


def test_h2_kb_ingest_rejects_unknown_source_type(tmp_project, monkeypatch):
    """H2: kb_ingest validates source_type in SOURCE_TYPE_DIRS."""
    import kb.config
    import kb.mcp.core
    from kb.mcp.core import kb_ingest

    # Point MCP module's PROJECT_ROOT + RAW_DIR at the tmp_project fixture.
    monkeypatch.setattr(kb.config, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(kb.config, "RAW_DIR", tmp_project / "raw")
    monkeypatch.setattr(kb.mcp.core, "PROJECT_ROOT", tmp_project)
    monkeypatch.setattr(kb.mcp.core, "RAW_DIR", tmp_project / "raw")
    article = tmp_project / "raw" / "articles" / "test.md"
    article.write_text("# Test\n", encoding="utf-8")

    result = kb_ingest(str(article), source_type="totally_bogus_xyz")
    assert "Unknown source_type" in result


# ─────────────────────────────────────────────────────────────────────────
# Theme I — query/engine.py (I1 UTC stale, I2 raw BM25 cache, I3 reject prefix)
# ─────────────────────────────────────────────────────────────────────────


def test_i1_flag_stale_uses_utc_dates(tmp_path):
    """I1: _flag_stale_results computes mtime date in UTC."""
    from kb.query.engine import _flag_stale_results

    src = tmp_path / "raw" / "articles" / "x.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x", encoding="utf-8")
    # Set mtime to a known UTC instant
    target = datetime(2025, 6, 15, 23, 59, 59, tzinfo=UTC).timestamp()
    os.utime(src, (target, target))
    results = [
        {
            "id": "concepts/x",
            "updated": "2025-06-10",
            "sources": ["raw/articles/x.md"],
        }
    ]
    flagged = _flag_stale_results(results, project_root=tmp_path)
    # Source is newer than updated → stale
    assert flagged[0]["stale"] is True


def test_i3_rewrite_prefix_leak_rejected():
    """I3: LLM prefix leaks fall back to the original question."""
    from kb.query import engine as engine_mod

    called_with: dict = {}

    def fake_search_pages(*a, **kw):
        called_with["question"] = a[0] if a else kw.get("question")
        return []  # empty → early return avoids downstream mocking

    def fake_rewrite_query(_q, _ctx):
        return "Sure! Here is the standalone: original question"

    with (
        patch.object(engine_mod, "search_pages", side_effect=fake_search_pages),
        patch("kb.query.rewriter.rewrite_query", side_effect=fake_rewrite_query),
    ):
        engine_mod.query_wiki("original question", conversation_context="ctx")

    # The effective question passed to search_pages must be the ORIGINAL,
    # not the preamble-laden rewrite.
    assert called_with["question"] == "original question"


def test_i3_legit_domain_prefix_rewrite_preserved():
    """PR review round 1 (Opus MINOR + Codex M-NEW-1): legit rewrites like
    "RAG: methodology" must NOT be treated as a prefix leak.

    The prior `_LEAK_PREFIX_RE = ^[A-Z][a-zA-Z ]{0,40}:\\s*` dropped these;
    the tightened keyword-anchored regex accepts them."""
    from kb.query import engine as engine_mod

    called_with: dict = {}

    def fake_search_pages(*a, **kw):
        called_with["question"] = a[0] if a else kw.get("question")
        return []

    def fake_rewrite_query(_q, _ctx):
        return "RAG: methodology and evaluation approach"

    with (
        patch.object(engine_mod, "search_pages", side_effect=fake_search_pages),
        patch("kb.query.rewriter.rewrite_query", side_effect=fake_rewrite_query),
    ):
        engine_mod.query_wiki("what about RAG?", conversation_context="ctx")

    assert called_with["question"] == "RAG: methodology and evaluation approach"


# ─────────────────────────────────────────────────────────────────────────
# Theme J — query/rewriter.py (J1 bounds; J2 WH-skip)
# ─────────────────────────────────────────────────────────────────────────


def test_j1_rewrite_cap_enforced_via_config():
    """J1: config.MAX_REWRITE_CHARS exists and is used by the rewriter."""
    from kb.config import MAX_REWRITE_CHARS

    assert isinstance(MAX_REWRITE_CHARS, int)
    assert MAX_REWRITE_CHARS == 500


def test_j2_wh_question_with_proper_noun_skips_rewrite():
    """J2: "What is RAG?" skips rewrite (proper-noun body, standalone)."""
    from kb.query.rewriter import _should_rewrite

    assert _should_rewrite("What is RAG?") is False
    assert _should_rewrite("Who is Andrew Ng?") is False
    # "How does it work?" still needs rewrite because "it" is deictic
    assert _should_rewrite("How does it work?") is True


# ─────────────────────────────────────────────────────────────────────────
# Theme K — query/dedup.py (K1 token cache)
# ─────────────────────────────────────────────────────────────────────────


def test_k1_dedup_tokens_computed_once_per_kept():
    """K1: _content_tokens called exactly once per kept result."""
    from kb.query import dedup as dedup_mod

    # Two different items so neither is deduped
    results = [
        {"id": "a", "score": 1.0, "content_lower": "alpha beta gamma delta"},
        {"id": "b", "score": 0.9, "content_lower": "one two three four"},
    ]
    calls = []
    real = dedup_mod._content_tokens

    def spy(content):
        calls.append(content)
        return real(content)

    with patch.object(dedup_mod, "_content_tokens", side_effect=spy):
        dedup_mod._dedup_by_text_similarity(results, 0.85)

    # Previously O(n*k) with repeat calls for each (r, k) pair. Now: one
    # call per candidate r, plus inner loop reuses cached k_words.
    assert len(calls) == len(results), f"expected {len(results)} calls, got {len(calls)}"


# ─────────────────────────────────────────────────────────────────────────
# Theme M — lint/verdicts.py (M1 mtime cache)
# ─────────────────────────────────────────────────────────────────────────


def test_m1_verdict_cache_invalidates_on_write(tmp_path):
    """M1: load_verdicts cache busts after a save + picks up new entry."""
    from kb.lint import verdicts as verdicts_mod

    path = tmp_path / "verdicts.json"
    verdicts_mod.save_verdicts([{"page_id": "a", "verdict": "pass"}], path)
    first = verdicts_mod.load_verdicts(path)
    assert len(first) == 1

    verdicts_mod.save_verdicts(
        [{"page_id": "a", "verdict": "pass"}, {"page_id": "b", "verdict": "fail"}],
        path,
    )
    second = verdicts_mod.load_verdicts(path)
    assert len(second) == 2, "cache should invalidate on save"


# ─────────────────────────────────────────────────────────────────────────
# Theme O — lint/checks.py (O1 frontmatter fence short-circuit)
# ─────────────────────────────────────────────────────────────────────────


def test_o1_missing_frontmatter_fence_flagged(tmp_path):
    """O1: page without opening --- fence emits a frontmatter issue under the
    canonical 'check' key (not 'type' — see PR review round 1 Sonnet MAJOR)."""
    from kb.lint.checks import check_source_coverage

    wiki = tmp_path / "wiki"
    raw = tmp_path / "raw"
    (wiki / "concepts").mkdir(parents=True)
    raw.mkdir()
    bad_page = wiki / "concepts" / "no-fence.md"
    bad_page.write_text("No frontmatter here.\n", encoding="utf-8")
    issues = check_source_coverage(wiki_dir=wiki, raw_dir=raw, pages=[bad_page])
    checks = [i.get("check") for i in issues]
    assert "frontmatter_missing_fence" in checks


# ─────────────────────────────────────────────────────────────────────────
# Theme P — utils/markdown.py (P1 skip code blocks)
# ─────────────────────────────────────────────────────────────────────────


def test_p1_wikilink_skips_code_spans():
    """P1: wikilinks inside backticks or fenced blocks are ignored."""
    from kb.utils.markdown import extract_wikilinks

    text = "Before `[[concepts/inline]]` after.\n```\n[[concepts/fenced]]\n```\n[[concepts/real]]\n"
    links = extract_wikilinks(text)
    assert "concepts/real" in links
    assert "concepts/inline" not in links
    assert "concepts/fenced" not in links


# ─────────────────────────────────────────────────────────────────────────
# Theme Q — feedback (Q1 widen except, Q2 recompute trust)
# ─────────────────────────────────────────────────────────────────────────


def test_q1_load_feedback_handles_unicode_decode_error(tmp_path):
    """Q1: non-UTF-8 feedback file returns defaults (does not raise)."""
    from kb.feedback.store import load_feedback

    path = tmp_path / "feedback.json"
    # bytes that are invalid UTF-8
    path.write_bytes(b"\x80\x81\x82 not valid utf-8")
    data = load_feedback(path)
    assert data == {"entries": [], "page_scores": {}}


def test_q1_load_feedback_propagates_permission_error(tmp_path, monkeypatch):
    """PR review round 1 (Codex M-NEW-3): Q1's widened OSError catch must
    NOT swallow PermissionError. Silent recovery on EACCES would let a
    subsequent write overwrite an unreadable file, destroying state."""
    from kb.feedback import store

    path = tmp_path / "feedback.json"
    path.write_text('{"entries": [], "page_scores": {}}', encoding="utf-8")

    def raise_permission(*_args, **_kwargs):
        raise PermissionError("EACCES: simulated read-deny")

    monkeypatch.setattr(Path, "read_text", raise_permission)
    with pytest.raises(PermissionError):
        store.load_feedback(path)


def test_q2_get_flagged_pages_recomputes_trust(tmp_path):
    """Q2: entries missing `trust` still flagged when counts indicate low trust."""
    from kb.feedback.reliability import get_flagged_pages

    path = tmp_path / "feedback.json"
    path.write_text(
        json.dumps(
            {
                "entries": [],
                "page_scores": {
                    # wrong=3 useful=0 incomplete=1 → trust = 1/9 ≈ 0.11
                    "concepts/bad": {"useful": 0, "wrong": 3, "incomplete": 1},
                    "concepts/good": {"useful": 5, "wrong": 0, "incomplete": 0, "trust": 0.9},
                },
            }
        ),
        encoding="utf-8",
    )
    flagged = get_flagged_pages(path, threshold=0.4)
    assert "concepts/bad" in flagged
    assert "concepts/good" not in flagged


# ─────────────────────────────────────────────────────────────────────────
# Theme S — utils/wiki_log.py (S1 is_file check after FileExistsError)
# ─────────────────────────────────────────────────────────────────────────


def test_s1_log_directory_raises_oserror(tmp_path):
    """S1: append_wiki_log rejects non-regular-file log targets."""
    from kb.utils.wiki_log import append_wiki_log

    # Create a directory where the log file should be
    target = tmp_path / "log.md"
    target.mkdir()
    with pytest.raises(OSError, match="not a regular file"):
        append_wiki_log("test_op", "test message", target)


def test_s1_log_symlink_raises_oserror(tmp_path):
    """S1: append_wiki_log rejects symlink targets even when the symlink
    points at a valid regular file.

    PR review round 1 (Sonnet MAJOR S1 + Codex): the prior implementation
    used `is_file()`, which follows symlinks and returned True for a
    symlink → regular file. Spec says "directory/symlink/special-file must
    be rejected".
    """
    from kb.utils.wiki_log import append_wiki_log

    real_log = tmp_path / "real.md"
    real_log.write_text("# Wiki Log\n\n", encoding="utf-8")
    symlink = tmp_path / "log.md"
    try:
        symlink.symlink_to(real_log)
    except OSError:
        # Windows without developer mode cannot create symlinks — skip
        pytest.skip("symlink creation not permitted on this platform")

    with pytest.raises(OSError, match="not a regular file"):
        append_wiki_log("test_op", "test message", symlink)
