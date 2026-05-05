"""AC16 — CLI value-based secret scrub tests."""

import pytest

from kb.utils.cli_backend import _check_no_secrets_on_argv
from kb.utils.llm import LLMError


class TestCheckNoSecretsOnArgv:
    """AC16 (C18) — value-based secret scrub via secrets.compare_digest."""

    def test_legitimate_token_format_discussion_allowed(self, monkeypatch):
        """Positive prong (Q2.10 lock): fake token allowed when no env value set.

        C18 — when ANTHROPIC_API_KEY is not set in the environment,
        discussing a token-shaped string in argv is allowed.
        """
        # Ensure the env var is NOT set
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # A fake token should NOT raise when no env value to compare against
        argv = ["kb", "ingest", "sk-ant-api03-AAAA-fake-token-not-real"]

        # Should not raise
        _check_no_secrets_on_argv(argv)
        # If we get here, the test passes

    def test_actual_env_value_blocked(self, monkeypatch):
        """Negative prong (Q2.10 lock): actual env value is blocked.

        C18 — when an env secret value is set, any argv element matching
        that exact value (via secrets.compare_digest) raises LLMError.
        """
        # Set a fake value in the env
        test_secret = "test-fake-value-not-real-injection"
        monkeypatch.setenv("ANTHROPIC_API_KEY", test_secret)

        # Pass it in argv — should raise
        argv = ["kb", "ingest", test_secret]

        with pytest.raises(LLMError, match="Refusing to place env secret"):
            _check_no_secrets_on_argv(argv)

    def test_multiple_env_keys_checked(self, monkeypatch):
        """All six env keys are checked."""
        # Set a secret in OPENAI_API_KEY
        openai_secret = "sk-openai-test-secret"
        monkeypatch.setenv("OPENAI_API_KEY", openai_secret)

        # Pass it in argv — should raise with OPENAI_API_KEY mentioned
        argv = ["kb", "query", openai_secret]

        with pytest.raises(LLMError) as exc_info:
            _check_no_secrets_on_argv(argv)

        assert "OPENAI_API_KEY" in str(exc_info.value)

    def test_different_string_not_blocked(self, monkeypatch):
        """Different strings are allowed even if they look token-shaped."""
        # Set a secret
        secret = "sk-real-secret-12345"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

        # Different string that looks similar but isn't equal
        argv = ["kb", "ingest", "sk-different-secret-67890"]

        # Should not raise
        _check_no_secrets_on_argv(argv)

    def test_empty_env_values_ignored(self, monkeypatch):
        """Empty env values are skipped."""
        # Set empty
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")

        # Any argv is fine since the env value is empty
        argv = ["kb", "query", "something"]

        _check_no_secrets_on_argv(argv)

    def test_timing_safe_comparison(self, monkeypatch):
        """Verification that the secret-in-argv check fires for exact match.

        Note: cycle-65 Step 10 simplify pass relaxed the equality check to
        substring containment; see test_embedded_secret_in_flag_blocked below
        for the substring case the original equality check missed.
        """
        secret = "sk-test-timing-safe"
        monkeypatch.setenv("FIRECRAWL_API_KEY", secret)

        # Test with exact match
        with pytest.raises(LLMError):
            _check_no_secrets_on_argv(["--api-key", secret])

        # Test with different value
        _check_no_secrets_on_argv(["--api-key", "sk-different"])

    def test_embedded_secret_in_flag_blocked(self, monkeypatch):
        """C18 substring leak — secret embedded inside a longer argv element MUST
        also be blocked, not just bare-equality.

        Cycle-65 Step 09 background review (deepseek-rescue) surfaced this gap:
        the original secrets.compare_digest equality check would let an argv
        element like ``Authorization: Bearer <SECRET>`` slip through because no
        element EQUALS the bare secret. The substring check closes that gap.
        """
        secret = "sk-real-secret-9876543210"
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

        # Embedded inside a longer string — equality check would miss this.
        argv = ["curl", "-H", f"Authorization: Bearer {secret}", "https://api.example/"]

        with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
            _check_no_secrets_on_argv(argv)

        # Embedded inside an env-var assignment shape.
        argv2 = ["python", "-c", f"import os; os.environ['X']='{secret}'"]
        with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
            _check_no_secrets_on_argv(argv2)
