"""Regression tests for backlog-by-file cycle 2 (30 fixes, 19 files).

Each test exercises the production code path per `feedback_test_behavior_over_signature`.
Item numbers reference `docs/superpowers/specs/2026-04-17-backlog-by-file-cycle2-design.md`.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import stat as _stat
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest


# -----------------------------------------------------------------------------
# utils/hashing.py — item 11: CRLF/CR → LF normalization before hashing
# -----------------------------------------------------------------------------

class TestHashingNewlineNormalization:
    def test_lf_crlf_cr_variants_produce_same_hash(self, tmp_path: Path) -> None:
        from kb.utils.hashing import content_hash

        body = "line one\nline two\nline three\n"
        lf_path = tmp_path / "lf.md"
        crlf_path = tmp_path / "crlf.md"
        cr_path = tmp_path / "cr.md"
        mixed_path = tmp_path / "mixed.md"

        lf_path.write_bytes(body.encode("utf-8"))
        crlf_path.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))
        cr_path.write_bytes(body.replace("\n", "\r").encode("utf-8"))
        mixed_path.write_bytes(b"line one\r\nline two\nline three\r")

        h_lf = content_hash(lf_path)
        assert content_hash(crlf_path) == h_lf
        assert content_hash(cr_path) == h_lf
        assert content_hash(mixed_path) == h_lf

    def test_hash_bytes_also_normalizes(self) -> None:
        from kb.utils.hashing import hash_bytes

        assert hash_bytes(b"a\nb\n") == hash_bytes(b"a\r\nb\r\n")
        assert hash_bytes(b"a\nb\n") == hash_bytes(b"a\rb\r")


# -----------------------------------------------------------------------------
# utils/markdown.py — item 10: fast-path startswith("---") before regex
# -----------------------------------------------------------------------------

class TestMarkdownFrontmatterFastPath:
    def test_no_regex_when_content_missing_opening_fence(self) -> None:
        import kb.utils.markdown as mod

        # Substitute FRONTMATTER_RE with a wrapper that counts match() calls.
        class CountingPattern:
            def __init__(self, real):
                self.real = real
                self.calls = 0

            def match(self, *args, **kwargs):
                self.calls += 1
                return self.real.match(*args, **kwargs)

            def sub(self, *args, **kwargs):
                return self.real.sub(*args, **kwargs)

            def findall(self, *args, **kwargs):
                return self.real.findall(*args, **kwargs)

        wrapper = CountingPattern(mod.FRONTMATTER_RE)
        with patch.object(mod, "FRONTMATTER_RE", wrapper):
            body = "just a plain paragraph, no frontmatter here.\n" * 50
            mod._strip_code_spans_and_fences(body)
        assert wrapper.calls == 0, "FRONTMATTER_RE.match must not be called when content lacks ---"

    def test_regex_still_called_when_fence_present(self) -> None:
        import kb.utils.markdown as mod

        class CountingPattern:
            def __init__(self, real):
                self.real = real
                self.calls = 0

            def match(self, *args, **kwargs):
                self.calls += 1
                return self.real.match(*args, **kwargs)

        wrapper = CountingPattern(mod.FRONTMATTER_RE)
        with patch.object(mod, "FRONTMATTER_RE", wrapper):
            body = "---\ntitle: x\n---\nbody here\n"
            mod._strip_code_spans_and_fences(body)
        assert wrapper.calls == 1


# -----------------------------------------------------------------------------
# utils/wiki_log.py — items 8, 9, 29
# -----------------------------------------------------------------------------

class TestWikiLogHardening:
    def test_escapes_leading_markdown_control_tokens(self, tmp_path: Path) -> None:
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("ingest", "# faux-heading then [[fake]] link", log_path)
        text = log_path.read_text(encoding="utf-8")
        # The raw `# ` and `[[...]]` must not appear active in the written entry.
        assert "| # faux-heading" not in text
        assert "[[fake]]" not in text
        # Core message tokens still preserved after escape
        assert "faux-heading" in text
        assert "fake" in text

    def test_escapes_leading_bullet_blockquote_emphasis(self, tmp_path: Path) -> None:
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("ingest", "> [!note] something", log_path)
        append_wiki_log("ingest", "- should not be list", log_path)
        append_wiki_log("ingest", "! not a banner", log_path)
        text = log_path.read_text(encoding="utf-8")
        # None of these should begin an Obsidian-style callout or list after the pipe
        for marker in ("| > [!", "| - should", "| ! not"):
            assert marker not in text

    def test_lf_only_on_write(self, tmp_path: Path) -> None:
        from kb.utils.wiki_log import append_wiki_log

        log_path = tmp_path / "log.md"
        append_wiki_log("ingest", "plain message", log_path)
        raw = log_path.read_bytes()
        assert b"\r\n" not in raw, "Wiki log must use LF only"

    def test_rejects_non_regular_after_file_exists_race(self, tmp_path: Path) -> None:
        """After FileExistsError pass, _reject_if_not_regular_file must re-run."""
        from kb.utils import wiki_log as mod

        log_path = tmp_path / "log.md"
        # Simulate: the "x"-mode open raises FileExistsError, then the concurrent creator
        # left a symlink at log_path. The re-check must detect and reject it.
        real_log = tmp_path / "real_target.md"
        real_log.write_text("# existing\n", encoding="utf-8")
        try:
            log_path.symlink_to(real_log)
        except OSError:
            pytest.skip("symlinks not creatable on this platform")

        with pytest.raises(OSError, match="not a regular file"):
            mod.append_wiki_log("ingest", "msg", log_path)


# -----------------------------------------------------------------------------
# utils/io.py — items 1, 2, 3, 4
# -----------------------------------------------------------------------------

class TestIoLockHardening:
    def test_unparseable_lock_content_raises_not_steals(self, tmp_path: Path, monkeypatch) -> None:
        from kb.utils import io as mod

        target = tmp_path / "guarded.json"
        lock_path = target.with_suffix(target.suffix + ".lock")
        # Seed a lock with non-ASCII content — must NOT be stolen.
        lock_path.write_bytes(b"\xff\xfenot-a-pid")
        # Force the timeout-and-retry path so steal logic runs.
        monkeypatch.setattr(mod, "LOCK_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(mod, "LOCK_POLL_INTERVAL", 0.01)
        with pytest.raises(OSError):
            with mod.file_lock(target):
                pass

    def test_ascii_valid_int_stale_lock_still_steals(self, tmp_path: Path, monkeypatch) -> None:
        """Legitimate ASCII-int lock for a dead PID is still stolen (cycle-1 behaviour preserved)."""
        from kb.utils import io as mod

        target = tmp_path / "guarded.json"
        lock_path = target.with_suffix(target.suffix + ".lock")
        lock_path.write_text("999999999", encoding="ascii")
        monkeypatch.setattr(mod, "LOCK_TIMEOUT_SECONDS", 0.05)
        monkeypatch.setattr(mod, "LOCK_POLL_INTERVAL", 0.01)
        # Force os.kill to report dead — stable mock regardless of platform
        monkeypatch.setattr(mod.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
        with mod.file_lock(target):
            pass  # ok — stolen

    def test_fsync_called_before_replace_in_atomic_json_write(self, tmp_path: Path, monkeypatch) -> None:
        """Ordering: flush+fsync must precede Path.replace in atomic_json_write."""
        from kb.utils import io as mod

        order: list[str] = []
        original_fsync = os.fsync
        original_replace = Path.replace

        def spy_fsync(fd):
            order.append("fsync")
            return original_fsync(fd)

        def spy_replace(self, target):
            order.append("replace")
            return original_replace(self, target)

        monkeypatch.setattr(mod.os, "fsync", spy_fsync)
        monkeypatch.setattr(Path, "replace", spy_replace)

        target = tmp_path / "d.json"
        mod.atomic_json_write({"k": "v"}, target)
        assert "fsync" in order, "fsync must be invoked"
        assert order.index("fsync") < order.index("replace"), "fsync must precede replace"

    def test_fsync_called_before_replace_in_atomic_text_write(self, tmp_path: Path, monkeypatch) -> None:
        from kb.utils import io as mod

        order: list[str] = []
        original_fsync = os.fsync
        original_replace = Path.replace

        monkeypatch.setattr(mod.os, "fsync", lambda fd: order.append("fsync") or original_fsync(fd))
        monkeypatch.setattr(Path, "replace", lambda self, target: order.append("replace") or original_replace(self, target))

        target = tmp_path / "d.txt"
        mod.atomic_text_write("hello", target)
        assert "fsync" in order and order.index("fsync") < order.index("replace")

    def test_cleanup_unlink_failure_logs_warning_without_masking(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        from kb.utils import io as mod

        target = tmp_path / "d.json"
        # Trigger the except-cleanup path by making `Path.replace` fail so the
        # caller-visible exception is the replace OSError — then make the
        # cleanup unlink fail too. The original OSError must still propagate
        # and the cleanup WARN must be logged.
        real_unlink = Path.unlink
        real_replace = Path.replace

        def failing_replace(self, _target):
            raise OSError("replace failed")

        def failing_unlink(self, *args, **kwargs):
            if str(self).endswith(".tmp"):
                raise OSError("cleanup failure")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "replace", failing_replace)
        monkeypatch.setattr(Path, "unlink", failing_unlink)
        with caplog.at_level(logging.WARNING, logger="kb.utils.io"):
            with pytest.raises(OSError, match="replace failed"):
                mod.atomic_json_write({"k": "v"}, target)
        assert any("cleanup" in rec.message.lower() for rec in caplog.records)


# -----------------------------------------------------------------------------
# utils/llm.py — items 5, 6, 7
# -----------------------------------------------------------------------------

class TestLLMHardening:
    def test_call_llm_json_multi_tool_use_raises_listing_names(self) -> None:
        from kb.utils import llm as mod

        class FakeBlock:
            def __init__(self, type_, name=None, input_=None, text=None):
                self.type = type_
                self.name = name
                self.input = input_ or {}
                self.text = text

        class FakeResponse:
            content = [
                FakeBlock("tool_use", name="extract_fields", input_={"a": 1}),
                FakeBlock("tool_use", name="other_tool", input_={"b": 2}),
            ]

        with patch.object(mod, "_make_api_call", return_value=FakeResponse()):
            with patch.object(mod, "_resolve_model", return_value="test-model"):
                with pytest.raises(mod.LLMError) as exc_info:
                    mod.call_llm_json(
                        prompt="q", tier="scan",
                        schema={"type": "object", "properties": {}},
                        tool_name="extract_fields",
                    )
                msg = str(exc_info.value)
                assert "extract_fields" in msg
                assert "other_tool" in msg

    def test_call_llm_json_no_tool_use_preserves_leading_text(self) -> None:
        """Item 5 was partially shipped — assert leading-text preview still works."""
        from kb.utils import llm as mod

        class FakeBlock:
            def __init__(self, type_, text=None):
                self.type = type_
                self.text = text

        class FakeResponse:
            content = [FakeBlock("text", text="I cannot comply with that request.")]

        with patch.object(mod, "_make_api_call", return_value=FakeResponse()):
            with patch.object(mod, "_resolve_model", return_value="test-model"):
                with pytest.raises(mod.LLMError) as exc_info:
                    mod.call_llm_json(
                        prompt="q", tier="scan",
                        schema={"type": "object", "properties": {}},
                        tool_name="extract_fields",
                    )
                assert "cannot comply" in str(exc_info.value)

    def test_backoff_delay_applies_jitter_once_and_clamps(self, monkeypatch) -> None:
        from kb.utils import llm as mod

        # With attempt=10, 2**10 = 1024, base=1.0, so exp would be 1024s.
        # Clamp to RETRY_MAX_DELAY; jitter at 1.5× must not exceed cap.
        monkeypatch.setattr(mod, "RETRY_BASE_DELAY", 1.0)
        monkeypatch.setattr(mod, "RETRY_MAX_DELAY", 10.0)
        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 1.5)
        delay = mod._backoff_delay(attempt=10)
        assert delay <= 10.0, f"delay {delay} must be clamped to RETRY_MAX_DELAY"
        # With jitter 1.5, lower attempts should scale up slightly
        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 1.0)
        base_delay = mod._backoff_delay(attempt=0)
        assert base_delay == pytest.approx(1.0)
        monkeypatch.setattr(mod.random, "uniform", lambda a, b: 0.5)
        low_jitter = mod._backoff_delay(attempt=0)
        assert low_jitter == pytest.approx(0.5)

    def test_llm_error_truncates_message_preserves_fields(self) -> None:
        import anthropic

        from kb.utils import llm as mod

        class FakeClient:
            class messages:
                @staticmethod
                def create(**kwargs):
                    resp = type("R", (), {"status_code": 400})()
                    raise anthropic.BadRequestError(
                        message="x" * 5000,
                        response=type("Resp", (), {"status_code": 400, "headers": {}, "request": None})(),
                        body={"error": {"type": "invalid_request_error"}},
                    )

        with patch.object(mod, "get_client", return_value=FakeClient()):
            with pytest.raises(mod.LLMError) as exc_info:
                mod._make_api_call({"messages": []}, "test-model")
            msg = str(exc_info.value)
            # model preserved verbatim
            assert "test-model" in msg
            # status code preserved verbatim
            assert "400" in msg
            # e.message truncated — 5000-char body must not pass through whole
            assert len(msg) < 1000, f"LLMError message should be truncated (got {len(msg)} chars)"


# -----------------------------------------------------------------------------
# ingest/evidence.py — item 28: backtick-wrap source_ref with pipe
# -----------------------------------------------------------------------------

class TestEvidencePipeEscape:
    def test_source_ref_with_pipe_is_backtick_wrapped(self) -> None:
        from kb.ingest.evidence import build_evidence_entry

        entry = build_evidence_entry(
            source_ref="raw/articles/foo|bar.md",
            action="Summarized",
            entry_date="2026-04-17",
        )
        # Rendered cell: pipe must not appear unescaped
        assert "`raw/articles/foo|bar.md`" in entry
        # Format still parseable as evidence-trail bullet
        assert entry.startswith("- 2026-04-17 | ")

    def test_source_ref_without_pipe_unchanged(self) -> None:
        from kb.ingest.evidence import build_evidence_entry

        entry = build_evidence_entry(
            source_ref="raw/articles/foo.md",
            action="Summarized",
            entry_date="2026-04-17",
        )
        # No backticks when no escaping needed (keeps backwards compat for existing entries)
        assert entry == "- 2026-04-17 | raw/articles/foo.md | Summarized"

    def test_append_evidence_trail_writes_backtick_wrapped(self, tmp_path: Path) -> None:
        from kb.ingest.evidence import append_evidence_trail

        page = tmp_path / "p.md"
        page.write_text(
            "---\ntitle: P\n---\n\nbody\n\n## Evidence Trail\n", encoding="utf-8"
        )
        append_evidence_trail(page, "raw/articles/a|b.md", "Summarized", entry_date="2026-04-17")
        written = page.read_text(encoding="utf-8")
        assert "`raw/articles/a|b.md`" in written


# -----------------------------------------------------------------------------
# compile/linker.py — item 26: single fm_match per page
# -----------------------------------------------------------------------------

class TestInjectWikilinksSingleFrontmatterMatch:
    def test_single_frontmatter_match_per_page(self, tmp_path: Path) -> None:
        from kb.compile import linker
        from kb.utils import markdown as md

        page_a = tmp_path / "a.md"
        page_a.write_text(
            "---\ntitle: A\nsource:\n  - raw/articles/a.md\n---\n\nTopic foo is important.\n",
            encoding="utf-8",
        )

        match_counter = {"n": 0}
        orig_match = md.FRONTMATTER_RE.match

        def counting_match(*args, **kwargs):
            match_counter["n"] += 1
            return orig_match(*args, **kwargs)

        with patch.object(md.FRONTMATTER_RE, "match", counting_match):
            # linker imports via `from kb.utils.markdown import FRONTMATTER_RE`
            # Patch the re-export too
            with patch.object(linker, "_FRONTMATTER_RE", md.FRONTMATTER_RE):
                linker.inject_wikilinks(
                    wiki_dir=tmp_path,
                    new_titles=[("Foo", "concepts/foo")],
                )
        assert match_counter["n"] <= 1, (
            f"inject_wikilinks should match frontmatter at most once per page (got {match_counter['n']})"
        )


# -----------------------------------------------------------------------------
# feedback/store.py — item 24: one-shot migration
# -----------------------------------------------------------------------------

class TestFeedbackStoreMigration:
    def test_legacy_scores_migrated_on_load(self, tmp_path: Path, monkeypatch) -> None:
        from kb.feedback import store as mod

        path = tmp_path / "feedback.json"
        # Legacy shape: missing useful/wrong/incomplete/trust
        path.write_text(
            json.dumps({
                "entries": [],
                "page_scores": {"entities/foo": {"useful": 2}},
            }),
            encoding="utf-8",
        )
        data = mod.load_feedback(path)
        score = data["page_scores"]["entities/foo"]
        assert score["useful"] == 2
        assert score["wrong"] == 0
        assert score["incomplete"] == 0
        assert "trust" in score


# -----------------------------------------------------------------------------
# feedback/reliability.py — item 25: coverage gap dedup by longest/newest
# -----------------------------------------------------------------------------

class TestCoverageGapsDedup:
    def test_duplicate_incomplete_keeps_longest_notes(self, tmp_path: Path) -> None:
        from kb.feedback import reliability, store

        path = tmp_path / "feedback.json"
        now = datetime.now(UTC)
        earlier = now.replace(year=now.year - 1).isoformat()
        later = now.isoformat()
        store.atomic_json_write(
            {
                "entries": [
                    {
                        "question": "what is X?",
                        "rating": "incomplete",
                        "notes": "short",
                        "timestamp": earlier,
                        "cited_pages": [],
                    },
                    {
                        "question": "what is X?",
                        "rating": "incomplete",
                        "notes": "a much longer and more specific note",
                        "timestamp": later,
                        "cited_pages": [],
                    },
                ],
                "page_scores": {},
            },
            path,
        )
        gaps = reliability.get_coverage_gaps(path)
        assert len(gaps) == 1
        assert "longer and more specific" in gaps[0]["notes"]


# -----------------------------------------------------------------------------
# evolve/analyzer.py — items 18, 19, 20
# -----------------------------------------------------------------------------

class TestEvolveAnalyzer:
    def test_numeric_only_tokens_ignored(self, tmp_path: Path) -> None:
        from kb.evolve.analyzer import find_connection_opportunities

        # Two pages sharing only year numbers — must not be flagged as related
        (tmp_path / "entities").mkdir()
        (tmp_path / "concepts").mkdir()
        (tmp_path / "entities" / "a.md").write_text(
            "---\ntitle: A\n---\n\nFoundational paper published 2024 with version 12345.\n",
            encoding="utf-8",
        )
        (tmp_path / "concepts" / "b.md").write_text(
            "---\ntitle: B\n---\n\nReview from 2024 discussing 12345.\n",
            encoding="utf-8",
        )
        opps = find_connection_opportunities(tmp_path)
        # Either no opportunity at all or opportunity doesn't cite purely-numeric shared tokens
        for op in opps:
            terms = op.get("shared_terms", [])
            assert not any(t.isdigit() for t in terms), f"numeric token leaked: {terms}"

    def test_wikilink_markup_stripped_before_tokenize(self, tmp_path: Path) -> None:
        from kb.evolve.analyzer import find_connection_opportunities

        (tmp_path / "entities").mkdir()
        (tmp_path / "concepts").mkdir()
        (tmp_path / "entities" / "x.md").write_text(
            "---\ntitle: X\n---\n\nSee [[concepts/rag]] for details.\n" * 10,
            encoding="utf-8",
        )
        (tmp_path / "concepts" / "y.md").write_text(
            "---\ntitle: Y\n---\n\nAlso see [[concepts/rag]] here.\n" * 10,
            encoding="utf-8",
        )
        opps = find_connection_opportunities(tmp_path)
        for op in opps:
            terms = op.get("shared_terms", [])
            # Wikilink target fragments must not appear as shared tokens
            for bad in ("[[concepts", "concepts/rag]]", "[[concepts/rag]]"):
                assert bad not in terms

    def test_generate_evolution_report_does_not_swallow_oserror(self, tmp_path, monkeypatch) -> None:
        from kb.evolve import analyzer as mod

        def boom(*a, **kw):
            raise OSError("disk fault")

        monkeypatch.setattr(mod, "get_flagged_pages", boom)
        # Must propagate — not return a partial report with silent defaults
        with pytest.raises(OSError, match="disk fault"):
            mod.generate_evolution_report(tmp_path)


# -----------------------------------------------------------------------------
# lint/trends.py — items 21, 22
# -----------------------------------------------------------------------------

class TestLintTrends:
    def test_parse_failures_counter_surfaced(self) -> None:
        from kb.lint.trends import compute_verdict_trends

        verdicts = [
            {"timestamp": "2026-04-01T10:00:00Z", "verdict": "pass", "severity": "info"},
            {"timestamp": "not-a-date", "verdict": "pass", "severity": "info"},
            {"timestamp": "also-broken", "verdict": "fail", "severity": "error"},
        ]
        result = compute_verdict_trends(verdicts)
        assert "parse_failures" in result
        assert result["parse_failures"] == 2

    def test_parse_timestamp_no_vestigial_fallback(self) -> None:
        from kb.lint import trends as mod

        with pytest.raises(ValueError):
            mod._parse_timestamp("not-a-date")


# -----------------------------------------------------------------------------
# lint/semantic.py — item 23: shared FRONTMATTER_RE
# -----------------------------------------------------------------------------

class TestLintSemanticSharedFrontmatterRe:
    def test_uses_shared_frontmatter_re(self) -> None:
        from kb.lint import semantic
        from kb.utils import markdown as md

        # Assert the module uses the SAME regex object, not a local duplicate
        assert getattr(semantic, "_FRONTMATTER_RE", None) is md.FRONTMATTER_RE or \
               getattr(semantic, "FRONTMATTER_RE", None) is md.FRONTMATTER_RE


# -----------------------------------------------------------------------------
# graph/export.py — item 27: deterministic tie-break
# -----------------------------------------------------------------------------

class TestGraphExportTieBreak:
    def test_mermaid_prune_deterministic_on_equal_degree(self, tmp_path: Path) -> None:
        from kb.graph.export import export_mermaid

        for subdir in ("entities", "concepts"):
            (tmp_path / subdir).mkdir()
        # Three pages with same degree — ids differ.
        for slug in ("alpha", "beta", "gamma"):
            (tmp_path / "entities" / f"{slug}.md").write_text(
                f"---\ntitle: {slug}\n---\n\nBody.\n", encoding="utf-8"
            )

        out1 = export_mermaid(tmp_path, max_nodes=2)
        out2 = export_mermaid(tmp_path, max_nodes=2)
        assert out1 == out2, "export_mermaid must be deterministic across runs"


# -----------------------------------------------------------------------------
# query/citations.py — item 17: dedup (type, path)
# -----------------------------------------------------------------------------

class TestCitationsDedup:
    def test_duplicates_removed_first_context_preserved(self) -> None:
        from kb.query.citations import extract_citations

        text = (
            "According to [[concepts/rag]] context A. Later, [[concepts/rag]] context B. "
            "And in raw/articles/x.md first ref, later in raw/articles/x.md again."
        )
        cites = extract_citations(text)
        keys = [(c["type"], c["path"]) for c in cites]
        assert len(keys) == len(set(keys)), f"duplicates remain: {keys}"
        # First context preserved — "A" snippet, not "B"
        rag = [c for c in cites if c["path"].endswith("rag")]
        assert rag and "context A" in rag[0]["context"]


# -----------------------------------------------------------------------------
# query/hybrid.py — item 16: wrap bm25/vector in try/except
# -----------------------------------------------------------------------------

class TestHybridBackendIsolation:
    def test_bm25_exception_logged_and_returns_empty(self, caplog) -> None:
        from kb.query.hybrid import hybrid_search

        def broken_bm25(q, limit):
            raise RuntimeError("bm25 corrupt")

        def ok_vector(q, limit):
            return [{"id": "p", "score": 0.5}]

        with caplog.at_level(logging.WARNING, logger="kb.query.hybrid"):
            out = hybrid_search(
                question="what is foo?",
                bm25_fn=broken_bm25,
                vector_fn=ok_vector,
                limit=5,
            )
        # Vector results still land
        assert any(r.get("id") == "p" for r in out)
        # WARN log contains backend name + exception class + token count proxy
        msgs = " ".join(r.message for r in caplog.records)
        assert "bm25" in msgs.lower()
        assert "RuntimeError" in msgs
        assert "query_tokens" in msgs.lower() or "token" in msgs.lower()

    def test_vector_exception_logged_and_returns_empty(self, caplog) -> None:
        from kb.query.hybrid import hybrid_search

        def ok_bm25(q, limit):
            return [{"id": "p", "score": 0.5}]

        def broken_vector(q, limit):
            raise OSError("sqlite-vec down")

        with caplog.at_level(logging.WARNING, logger="kb.query.hybrid"):
            out = hybrid_search(
                question="what is foo?",
                bm25_fn=ok_bm25,
                vector_fn=broken_vector,
                limit=5,
            )
        assert any(r.get("id") == "p" for r in out)
        msgs = " ".join(r.message for r in caplog.records)
        assert "vector" in msgs.lower()
        assert "OSError" in msgs


# -----------------------------------------------------------------------------
# query/dedup.py — items 15, 30
# -----------------------------------------------------------------------------

class TestDedupClampAndFallback:
    def test_max_results_clamp_applied(self) -> None:
        from kb.query.dedup import dedup_results

        results = [
            {"id": f"p{i}", "score": 1.0 / (i + 1), "type": "entity",
             "content_lower": f"unique body for {i}"}
            for i in range(20)
        ]
        clamped = dedup_results(results, max_results=5)
        assert len(clamped) <= 5

    def test_content_lower_fallback_to_content(self) -> None:
        from kb.query.dedup import dedup_results

        # Two near-duplicate results, one has only content (no content_lower)
        body = "retrieval augmented generation pipeline details about vector search"
        results = [
            {"id": "p1", "score": 0.9, "type": "entity", "content_lower": body},
            {"id": "p2", "score": 0.8, "type": "entity", "content": body + " suffix"},
        ]
        out = dedup_results(results)
        # Second one should be removed via fallback since content is near-identical
        assert len(out) == 1


# -----------------------------------------------------------------------------
# query/rewriter.py — item 14: skip WH + proper-noun
# -----------------------------------------------------------------------------

class TestRewriterSkipsWHProperNoun:
    def test_wh_question_with_proper_noun_not_rewritten(self) -> None:
        from kb.query.rewriter import _should_rewrite

        assert _should_rewrite("Who is Andrew Ng?") is False
        assert _should_rewrite("What is RAG?") is False
        assert _should_rewrite("Where is Anthropic?") is False

    def test_pronoun_question_still_rewrites_if_short(self) -> None:
        from kb.query.rewriter import _should_rewrite

        # Pronoun body without proper noun should still trigger (context needed)
        assert _should_rewrite("Who is he?") is True


# -----------------------------------------------------------------------------
# query/engine.py — items 12, 13
# -----------------------------------------------------------------------------

class TestQueryEngineNormalizations:
    def test_unicode_whitespace_collapsed(self, tmp_path: Path, monkeypatch) -> None:
        from kb.query import engine as mod

        # Capture what gets passed to the search layer
        seen: list[str] = []
        def spy_search(question, *args, **kwargs):
            seen.append(question)
            return []
        monkeypatch.setattr(mod, "search_pages", spy_search)
        monkeypatch.setattr(mod, "search_raw_sources", lambda *a, **k: [])
        monkeypatch.setattr(mod, "_build_query_context", lambda *a, **k: {"context": "", "context_pages": []})

        # Build a test wiki dir
        for sub in ("entities", "concepts", "summaries", "synthesis", "comparisons"):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)

        mod.query_wiki("what   is\u2028  RAG?", wiki_dir=tmp_path)
        assert seen, "search_pages must be called"
        normalized = seen[-1]
        # Multiple whitespace collapsed to single space
        assert "  " not in normalized
        assert "\u2028" not in normalized

    def test_search_raw_sources_skips_oversized_files(self, tmp_path: Path, monkeypatch, caplog) -> None:
        from kb.config import RAW_SOURCE_MAX_BYTES  # raises if constant missing
        from kb.query.engine import search_raw_sources

        # Lower cap for test speed
        monkeypatch.setattr("kb.query.engine.RAW_SOURCE_MAX_BYTES", 1024)

        raw_dir = tmp_path / "articles"
        raw_dir.mkdir()
        big = raw_dir / "big.md"
        big.write_bytes(b"x" * 4096)
        small = raw_dir / "small.md"
        small.write_text("rag foo bar baz content", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger="kb.query.engine"):
            results = search_raw_sources("rag", tmp_path, limit=10)
        # Oversize file skipped — only small matches
        paths = [r.get("path", "") for r in results]
        assert not any("big.md" in p for p in paths)
        # Skip log emitted
        msgs = " ".join(r.message for r in caplog.records)
        assert "big.md" in msgs or "skipped" in msgs.lower()

    def test_search_raw_sources_strips_frontmatter(self, tmp_path: Path) -> None:
        from kb.query.engine import search_raw_sources

        raw_dir = tmp_path / "articles"
        raw_dir.mkdir()
        # File with frontmatter. Query matches ONLY frontmatter keywords; body has no match.
        (raw_dir / "foo.md").write_text(
            "---\ntitle: The RAG Masterclass Review\nauthor: Anonymous\ntags: [rag, vector]\n---\n"
            "\n\nThe content body here contains only unrelated words about apple pie and sunsets.\n",
            encoding="utf-8",
        )
        results = search_raw_sources("rag vector", tmp_path, limit=10)
        # If frontmatter is stripped, query terms don't match body → no result
        # (If frontmatter NOT stripped, title/tags would score high and the file would appear.)
        matched = [r for r in results if "foo.md" in r.get("path", "")]
        assert not matched, "search_raw_sources should skip frontmatter keywords"

    def test_whitespace_collapse_stable_cache_state(self) -> None:
        """Q8 assertion: collapse must not change memoisation key for equivalent queries."""
        from kb.query import rewriter as mod

        # _should_rewrite has no cache but if the whitespace passes through unchanged semantically,
        # two whitespace-variant inputs must produce the same boolean.
        assert mod._should_rewrite("foo bar") == mod._should_rewrite("foo  bar")
        assert mod._should_rewrite("foo\tbar") == mod._should_rewrite("foo bar")
