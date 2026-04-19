"""Cycle 14 TASK 1 — config constants + helpers.

Covers AC1 (frontmatter vocabularies), AC4 (coverage threshold), AC7/AC8
(tier1 split + helper), AC10/AC11/AC12 (decay days + helper + IDN/bare),
Q10 (STATUS_RANKING_BOOST constant). Threats: T6 (decay hostname match).
"""

from __future__ import annotations

import pytest

from kb import config


class TestFrontmatterVocabularies:
    """AC1 — three optional-field vocabularies."""

    def test_belief_states_tuple(self):
        assert config.BELIEF_STATES == (
            "confirmed",
            "uncertain",
            "contradicted",
            "stale",
            "retracted",
        )

    def test_authored_by_values_tuple(self):
        assert config.AUTHORED_BY_VALUES == ("human", "llm", "hybrid")

    def test_page_statuses_tuple(self):
        assert config.PAGE_STATUSES == ("seed", "developing", "mature", "evergreen")


class TestCoverageThreshold:
    """AC4 — query coverage-confidence threshold."""

    def test_threshold_is_float_in_range(self):
        assert isinstance(config.QUERY_COVERAGE_CONFIDENCE_THRESHOLD, float)
        assert 0.0 <= config.QUERY_COVERAGE_CONFIDENCE_THRESHOLD <= 1.0

    def test_threshold_value(self):
        assert config.QUERY_COVERAGE_CONFIDENCE_THRESHOLD == 0.45


class TestTier1Split:
    """AC7, AC8, AC9 — CONTEXT_TIER1_SPLIT + tier1_budget_for helper."""

    def test_split_has_four_components(self):
        assert set(config.CONTEXT_TIER1_SPLIT) == {
            "wiki_pages",
            "chat_history",
            "index",
            "system",
        }

    def test_percentages_sum_to_100(self):
        assert sum(config.CONTEXT_TIER1_SPLIT.values()) == 100

    def test_budget_for_each_component_is_nonzero(self):
        for component in config.CONTEXT_TIER1_SPLIT:
            assert config.tier1_budget_for(component) > 0

    def test_budgets_sum_to_total(self):
        total = sum(config.tier1_budget_for(c) for c in config.CONTEXT_TIER1_SPLIT)
        # 100 divides 60/20/5/15 cleanly into integer budgets; the integer
        # division in tier1_budget_for means the sum equals the full total.
        assert total == config.CONTEXT_TIER1_BUDGET

    def test_invalid_component_raises(self):
        with pytest.raises(ValueError, match="invalid tier1 component"):
            config.tier1_budget_for("nonexistent")

    def test_invalid_component_mentions_valid_set(self):
        with pytest.raises(ValueError, match="valid="):
            config.tier1_budget_for("x")


class TestSourceDecay:
    """AC10, AC11, AC12 — SOURCE_DECAY_DAYS + decay_days_for helper."""

    def test_default_is_staleness_max(self):
        assert config.SOURCE_DECAY_DEFAULT_DAYS == config.STALENESS_MAX_DAYS

    def test_six_hosts_present(self):
        assert set(config.SOURCE_DECAY_DAYS) == {
            "huggingface.co",
            "github.com",
            "stackoverflow.com",
            "arxiv.org",
            "wikipedia.org",
            "openlibrary.org",
        }

    def test_each_documented_host(self):
        cases = [
            ("https://huggingface.co/m", 120),
            ("https://github.com/u/r", 180),
            ("https://stackoverflow.com/q/1", 365),
            ("https://arxiv.org/abs/2401.12345", 1095),
            ("https://en.wikipedia.org/wiki/X", 1460),
            ("https://openlibrary.org/works/OL1W", 1825),
        ]
        for ref, expected in cases:
            assert config.decay_days_for(ref) == expected, f"mismatch for {ref}"

    def test_none_and_empty_default(self):
        assert config.decay_days_for(None) == config.SOURCE_DECAY_DEFAULT_DAYS
        assert config.decay_days_for("") == config.SOURCE_DECAY_DEFAULT_DAYS

    def test_no_scheme_bare_domain_default(self):
        # urlparse("github.com/foo").hostname is None — no scheme means no
        # hostname extraction. This is correct: bare paths are not URLs.
        assert config.decay_days_for("github.com/foo") == config.SOURCE_DECAY_DEFAULT_DAYS

    def test_no_scheme_bare_domain_is_path_like(self):
        # raw/articles/github.com-note.md is a local path; should not match.
        assert (
            config.decay_days_for("raw/articles/github.com-note.md")
            == config.SOURCE_DECAY_DEFAULT_DAYS
        )

    def test_subdomain_dot_boundary_match(self):
        assert config.decay_days_for("https://sub.arxiv.org/x") == 1095
        assert config.decay_days_for("https://en.wikipedia.org/x") == 1460

    def test_attacker_spoof_rejected(self):
        """T6 — substring match would wrongly grant the longer decay window."""
        assert (
            config.decay_days_for("https://arxiv.org.evil.com/x")
            == config.SOURCE_DECAY_DEFAULT_DAYS
        )
        assert (
            config.decay_days_for("https://github.com-phish.net/x")
            == config.SOURCE_DECAY_DEFAULT_DAYS
        )

    def test_port_stripped_from_host(self):
        assert config.decay_days_for("https://github.com:443/foo") == 180

    def test_userinfo_stripped(self):
        assert config.decay_days_for("https://user@arxiv.org/x") == 1095

    def test_uppercase_hostname_normalized(self):
        assert config.decay_days_for("https://Arxiv.ORG/x") == 1095

    def test_idn_punycode_not_in_list_uses_default(self):
        # xn--arxv-7qa.org is a punycode-encoded host that is NOT the real
        # arxiv.org — it must return default, not 1095.
        assert (
            config.decay_days_for("https://xn--arxv-7qa.org/foo")
            == config.SOURCE_DECAY_DEFAULT_DAYS
        )

    def test_malformed_ref_default(self):
        # urlparse is very forgiving; most garbage still returns a hostname
        # of None or empty. Any case that fails parsing returns default.
        assert config.decay_days_for("not a url at all ???") == config.SOURCE_DECAY_DEFAULT_DAYS


class TestStatusBoost:
    """Q10 — STATUS_RANKING_BOOST constant."""

    def test_status_boost_is_float(self):
        assert isinstance(config.STATUS_RANKING_BOOST, float)
        assert 0.0 < config.STATUS_RANKING_BOOST < 1.0

    def test_status_boost_value(self):
        assert config.STATUS_RANKING_BOOST == 0.05
