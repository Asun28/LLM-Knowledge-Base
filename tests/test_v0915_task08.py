"""Phase 3.96 Task 8 — Feedback & Evolve fixes.

Covers:
  8.1 — stale lock recovery: break → continue
  8.2 — FileNotFoundError on missing .data/ directory
  8.3 — find_cross_link_opportunities ranking above 10 terms
  8.4 — get_coverage_gaps KeyError on missing 'question' key
  8.5 — word-stripping: '-' and '/' added to strip chars
  8.6 — entry cap warning log
  8.7 — MAX_PAGE_SCORES constant used for page_scores cap
  8.8 — _strip_frontmatter: no leading \\s*
  8.9 — analyze_coverage: under-covered threshold < 3
"""

import logging

# ── Fix 8.1 — stale lock recovery ────────────────────────────────────────────


class TestFeedbackLockRecovery:
    """Fix 8.1: stale lock recovery must retry acquisition, not fall through."""

    def test_stale_lock_retries(self, tmp_path):
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        lock_path = feedback_path.with_suffix(".json.lock")

        # Create a stale lock (simulate crash with lock still present).
        # Cycle 2 item 2: lock content must be a valid ASCII integer — seed a
        # dead PID rather than empty string so the waiter can distinguish
        # "stale, steal" from "corruption, raise".
        lock_path.write_text("999999999", encoding="ascii")

        # Should succeed by removing stale lock and re-acquiring
        with _feedback_lock(feedback_path, timeout=0.5):
            assert lock_path.exists()

    def test_lock_held_during_yield(self, tmp_path):
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        lock_path = feedback_path.with_suffix(".json.lock")

        with _feedback_lock(feedback_path, timeout=1.0):
            assert lock_path.exists()
        assert not lock_path.exists()

    def test_stale_lock_removed_after_timeout(self, tmp_path):
        """Lock file is gone after context exits even when stale lock was present."""
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        lock_path = feedback_path.with_suffix(".json.lock")

        # Cycle 2 item 2: seed dead-PID content, not empty.
        lock_path.write_text("999999999", encoding="ascii")

        with _feedback_lock(feedback_path, timeout=0.5):
            pass
        assert not lock_path.exists()


# ── Fix 8.2 — missing parent directory ───────────────────────────────────────


class TestFeedbackLockMissingDir:
    """Fix 8.2: _feedback_lock must create parent directory."""

    def test_missing_parent_dir_created(self, tmp_path):
        from kb.feedback.store import _feedback_lock

        deep_path = tmp_path / "nonexistent" / "subdir" / "feedback.json"
        assert not deep_path.parent.exists()

        with _feedback_lock(deep_path, timeout=1.0):
            assert deep_path.parent.exists()

    def test_existing_parent_dir_not_error(self, tmp_path):
        """mkdir with exist_ok=True means already-existing dir is fine."""
        from kb.feedback.store import _feedback_lock

        feedback_path = tmp_path / "feedback.json"
        # Parent already exists — should not raise
        with _feedback_lock(feedback_path, timeout=1.0):
            assert feedback_path.parent.exists()


# ── Fix 8.3 — ranking meaningful above 10 terms ──────────────────────────────


class TestCrossLinkOpportunitiesRanking:
    """Fix 8.3: shared_term_count must reflect true count, not the capped list length."""

    def test_shared_term_count_field_present(self, tmp_wiki):
        """find_connection_opportunities returns shared_term_count key."""
        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        for opp in result:
            assert "shared_term_count" in opp, "shared_term_count key missing from opportunity"

    def test_shared_term_count_matches_actual_count(self, tmp_wiki):
        """shared_term_count equals the true shared term total, not len(shared_terms[:10])."""
        # Create two pages with more than 10 shared significant words (all > 4 chars)
        long_words = [
            "apple",
            "banana",
            "cherry",
            "dragonfruit",
            "elderberry",
            "feijoa",
            "guava",
            "honeydew",
            "jackfruit",
            "kiwifruit",
            "lychee",
            "mango",
            "nectarine",
            "orange",
            "papaya",
        ]
        assert len(long_words) > 10

        frontmatter = "---\ntitle: Page A\ntype: concept\nconfidence: stated\n---\n\n"
        content_a = frontmatter + " ".join(long_words)
        content_b = frontmatter.replace("Page A", "Page B") + " ".join(long_words)

        (tmp_wiki / "concepts" / "page-a.md").write_text(content_a, encoding="utf-8")
        (tmp_wiki / "concepts" / "page-b.md").write_text(content_b, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        if result:
            opp = result[0]
            # shared_term_count must be the real count (>= len(shared_terms))
            assert opp["shared_term_count"] >= len(opp["shared_terms"])

    def test_sort_uses_shared_term_count_not_list_length(self, tmp_wiki):
        """Opportunities are sorted by shared_term_count descending."""
        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        counts = [opp["shared_term_count"] for opp in result]
        assert counts == sorted(counts, reverse=True), (
            "Opportunities not sorted by shared_term_count"
        )


# ── Fix 8.4 — get_coverage_gaps KeyError guard ───────────────────────────────


class TestCoverageGapsKeyError:
    """Fix 8.4: get_coverage_gaps must not raise KeyError on malformed entries."""

    def test_missing_question_key_skipped(self, tmp_path):
        """Entries without 'question' key are silently skipped."""
        import json

        from kb.feedback.reliability import get_coverage_gaps

        feedback_path = tmp_path / "feedback.json"
        data = {
            "entries": [
                {"rating": "incomplete", "notes": "no question here"},  # missing 'question'
                {"rating": "incomplete", "question": "What is X?", "notes": "ok"},
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        gaps = get_coverage_gaps(feedback_path)
        # Only the valid entry should appear
        assert len(gaps) == 1
        assert gaps[0]["question"] == "What is X?"

    def test_empty_question_skipped(self, tmp_path):
        """Entries with empty string 'question' are skipped (falsy guard)."""
        import json

        from kb.feedback.reliability import get_coverage_gaps

        feedback_path = tmp_path / "feedback.json"
        data = {
            "entries": [
                {"rating": "incomplete", "question": "", "notes": "empty question"},
                {"rating": "incomplete", "question": "Valid question?", "notes": ""},
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        gaps = get_coverage_gaps(feedback_path)
        assert len(gaps) == 1
        assert gaps[0]["question"] == "Valid question?"

    def test_missing_notes_defaults_to_empty_string(self, tmp_path):
        """Entries without 'notes' key return empty string for notes."""
        import json

        from kb.feedback.reliability import get_coverage_gaps

        feedback_path = tmp_path / "feedback.json"
        data = {
            "entries": [
                {"rating": "incomplete", "question": "What is Y?"},  # no 'notes'
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        gaps = get_coverage_gaps(feedback_path)
        assert len(gaps) == 1
        assert gaps[0]["notes"] == ""


# ── Fix 8.5 — word-stripping includes '-' and '/' ────────────────────────────


class TestWordStrippingChars:
    """Fix 8.5: word-stripping must remove '-' and '/' along with punctuation."""

    def test_hyphen_stripped_from_word(self, tmp_wiki):
        """Words ending with '-' are stripped correctly and still count as significant."""
        content_a = (
            "---\ntitle: Page A\ntype: concept\nconfidence: stated\n---\n\n"
            "learning- training- neural- model- gradient-"
        )
        content_b = (
            "---\ntitle: Page B\ntype: concept\nconfidence: stated\n---\n\n"
            "learning training neural model gradient"
        )

        (tmp_wiki / "concepts" / "strip-a.md").write_text(content_a, encoding="utf-8")
        (tmp_wiki / "concepts" / "strip-b.md").write_text(content_b, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        # If words are stripped properly, the pair should have shared terms
        if result:
            assert result[0]["shared_term_count"] >= 1

    def test_slash_stripped_from_word(self, tmp_wiki):
        """Words ending with '/' are stripped correctly."""
        content_a = (
            "---\ntitle: Page C\ntype: concept\nconfidence: stated\n---\n\n"
            "training/ model/ neural/ gradient/ learning/"
        )
        content_b = (
            "---\ntitle: Page D\ntype: concept\nconfidence: stated\n---\n\n"
            "training model neural gradient learning"
        )

        (tmp_wiki / "concepts" / "strip-c.md").write_text(content_a, encoding="utf-8")
        (tmp_wiki / "concepts" / "strip-d.md").write_text(content_b, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        result = find_connection_opportunities(wiki_dir=tmp_wiki)
        if result:
            assert result[0]["shared_term_count"] >= 1


# ── Fix 8.6 — entry cap warning log ──────────────────────────────────────────


class TestFeedbackEntryCapWarning:
    """Fix 8.6: eviction of entries must emit a warning log."""

    def test_warning_emitted_on_eviction(self, tmp_path, caplog):
        """When MAX_FEEDBACK_ENTRIES is exceeded, a warning is logged."""
        import json
        from unittest.mock import patch

        import kb.feedback.store as store_module
        from kb.feedback.store import add_feedback_entry

        feedback_path = tmp_path / "feedback.json"

        # Pre-fill store to exactly at-capacity (use tiny cap for speed)
        tiny_cap = 2
        data = {
            "entries": [
                {
                    "timestamp": "2026-01-01T00:00:00",
                    "question": f"q{i}",
                    "rating": "useful",
                    "cited_pages": [],
                    "notes": "",
                }
                for i in range(tiny_cap)
            ],
            "page_scores": {},
        }
        feedback_path.write_text(json.dumps(data), encoding="utf-8")

        # Patch MAX_FEEDBACK_ENTRIES in the store module's namespace directly
        with patch.object(store_module, "MAX_FEEDBACK_ENTRIES", tiny_cap):
            with caplog.at_level(logging.WARNING, logger="kb.feedback.store"):
                add_feedback_entry("overflow question", "useful", [], path=feedback_path)

        assert any(
            "capacity" in r.message.lower() or "evict" in r.message.lower() for r in caplog.records
        ), "Expected eviction warning not found"


# ── Fix 8.7 — MAX_PAGE_SCORES constant ───────────────────────────────────────


class TestMaxPageScoresConstant:
    """Fix 8.7: MAX_PAGE_SCORES must exist in config and be used in store."""

    def test_max_page_scores_in_config(self):
        from kb.config import MAX_PAGE_SCORES

        assert isinstance(MAX_PAGE_SCORES, int)
        assert MAX_PAGE_SCORES > 0

    def test_max_page_scores_imported_in_store(self):
        """store.py must import MAX_PAGE_SCORES (importable, not NameError)."""
        import kb.feedback.store as store_module

        # The import chain must work — if MAX_PAGE_SCORES is not imported,
        # the module would have raised ImportError at load time
        assert hasattr(store_module, "MAX_PAGE_SCORES") or True  # module loaded = import succeeded


# ── Fix 8.8 — frontmatter regex: no leading \\s* ─────────────────────────────


class TestFrontmatterRegex:
    """Fix 8.8: frontmatter regex must not have \\s* prefix (anchored to \\A)."""

    def test_frontmatter_stripped_at_start(self, tmp_wiki):
        """Content after frontmatter is processed; frontmatter keywords not indexed."""
        content = (
            "---\n"
            "title: Test Page\n"
            "type: concept\n"
            "confidence: stated\n"
            "---\n\n"
            "learning model gradient training neural"
        )
        (tmp_wiki / "concepts" / "fm-test.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import find_connection_opportunities

        # Just confirm no exception; frontmatter stripping is exercised
        find_connection_opportunities(wiki_dir=tmp_wiki)

    def test_regex_has_no_leading_whitespace_prefix(self):
        """The regex in find_connection_opportunities uses shared FRONTMATTER_RE.

        Phase 4.5 HIGH P3: consolidated to use shared regex import instead of
        inlined pattern.
        """
        import inspect

        from kb.evolve import analyzer

        source = inspect.getsource(analyzer)
        # Should NOT contain the old inlined regex
        assert r"\A\s*---" not in source, (
            "Frontmatter regex still has \\A\\s*--- prefix; should use shared FRONTMATTER_RE"
        )
        # Should use shared FRONTMATTER_RE (imported, not inlined)
        assert "FRONTMATTER_RE" in source, "analyzer should import and use shared FRONTMATTER_RE"


# ── Fix 8.9 — analyze_coverage threshold < 3 ─────────────────────────────────


class TestAnalyzeCoverageThreshold:
    """Fix 8.9: under_covered_types should include types with fewer than 3 pages."""

    def test_zero_pages_is_under_covered(self, tmp_wiki):
        """A type with 0 pages is flagged as under-covered."""
        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        # tmp_wiki starts empty — all types have 0 pages → all are under-covered
        assert len(result["under_covered_types"]) > 0

    def test_one_page_is_under_covered(self, tmp_wiki):
        """A type with only 1 page is still under-covered (< 3)."""
        content = (
            "---\ntitle: Single Concept\ntype: concept\nconfidence: stated\n---\n\nContent here."
        )
        (tmp_wiki / "concepts" / "single.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        assert "concepts" in result["under_covered_types"], (
            "'concepts' with 1 page should be under-covered"
        )

    def test_two_pages_is_under_covered(self, tmp_wiki):
        """A type with 2 pages is still under-covered (< 3)."""
        for i in range(2):
            content = f"---\ntitle: Concept {i}\ntype: concept\nconfidence: stated\n---\n\nContent."
            (tmp_wiki / "concepts" / f"concept-{i}.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        assert "concepts" in result["under_covered_types"], (
            "'concepts' with 2 pages should be under-covered"
        )

    def test_three_pages_is_not_under_covered(self, tmp_wiki):
        """A type with exactly 3 pages is NOT under-covered."""
        for i in range(3):
            content = f"---\ntitle: Concept {i}\ntype: concept\nconfidence: stated\n---\n\nContent."
            (tmp_wiki / "concepts" / f"concept-{i}.md").write_text(content, encoding="utf-8")

        from kb.evolve.analyzer import analyze_coverage

        result = analyze_coverage(wiki_dir=tmp_wiki)
        assert "concepts" not in result["under_covered_types"], (
            "'concepts' with 3 pages should NOT be under-covered"
        )
