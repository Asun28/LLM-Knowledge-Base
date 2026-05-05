"""Cycle 65 AC3: Test AUGMENT_ALLOWED_DOMAINS call-time accessor (C2)."""

import os
from pathlib import Path

import pytest

import kb.config


class TestAllowedDomainsCallTime:
    """Verify kb.config.get_allowed_domains() reads env at call time."""

    def test_allowed_domains_call_time_kb_prefix(self, monkeypatch):
        """Test KB_AUGMENT_ALLOWED_DOMAINS env var (KB-prefixed, preferred)."""
        monkeypatch.setenv("KB_AUGMENT_ALLOWED_DOMAINS", "foo.com,bar.com")
        result = kb.config.get_allowed_domains()
        assert result == ("foo.com", "bar.com"), (
            f"Expected ('foo.com', 'bar.com'), got {result}"
        )

        # Also test the shim access form (back-compat)
        shim_result = kb.config.AUGMENT_ALLOWED_DOMAINS
        assert shim_result == ("foo.com", "bar.com"), (
            "PEP 562 shim should return same value"
        )

    def test_allowed_domains_call_time_unprefixed_fallback(self, monkeypatch):
        """Test AUGMENT_ALLOWED_DOMAINS env var (unprefixed, fallback)."""
        # Clear KB_ prefix
        monkeypatch.delenv("KB_AUGMENT_ALLOWED_DOMAINS", raising=False)
        monkeypatch.setenv("AUGMENT_ALLOWED_DOMAINS", "baz.org")
        result = kb.config.get_allowed_domains()
        assert result == ("baz.org",)

    def test_allowed_domains_default(self, monkeypatch):
        """Test default when no env vars set."""
        monkeypatch.delenv("KB_AUGMENT_ALLOWED_DOMAINS", raising=False)
        monkeypatch.delenv("AUGMENT_ALLOWED_DOMAINS", raising=False)
        result = kb.config.get_allowed_domains()
        assert result == ("en.wikipedia.org", "arxiv.org")

    def test_allowed_domains_whitespace_stripped(self, monkeypatch):
        """Test that whitespace is stripped from domain names."""
        monkeypatch.setenv("KB_AUGMENT_ALLOWED_DOMAINS", "  foo.com  ,  bar.org  ")
        result = kb.config.get_allowed_domains()
        assert result == ("foo.com", "bar.org")

    def test_allowed_domains_empty_entries_skipped(self, monkeypatch):
        """Test that empty entries are skipped."""
        monkeypatch.setenv("KB_AUGMENT_ALLOWED_DOMAINS", "foo.com,,bar.org,")
        result = kb.config.get_allowed_domains()
        assert result == ("foo.com", "bar.org")

    def test_kb_prefix_takes_priority(self, monkeypatch):
        """Test that KB_ prefix takes priority over unprefixed."""
        monkeypatch.setenv("KB_AUGMENT_ALLOWED_DOMAINS", "kb-domain.com")
        monkeypatch.setenv("AUGMENT_ALLOWED_DOMAINS", "fallback.com")
        result = kb.config.get_allowed_domains()
        assert result == ("kb-domain.com",), (
            "KB_AUGMENT_ALLOWED_DOMAINS should take priority"
        )
