"""Tests for Phase 3.9 features (v0.9.9)."""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Task 1: Environment-configurable model tiers ───────────────


class TestEnvConfigurableModelTiers:
    """Test that model tiers can be overridden via environment variables."""

    def test_default_tiers_unchanged(self):
        """Default tiers remain when no env vars set."""
        # Reimport to get fresh state
        from kb.config import MODEL_TIERS

        assert MODEL_TIERS["scan"] == "claude-haiku-4-5-20251001"
        assert MODEL_TIERS["write"] == "claude-sonnet-4-6"
        assert MODEL_TIERS["orchestrate"] == "claude-opus-4-6"

    def test_env_override_scan_model(self, monkeypatch):
        """CLAUDE_SCAN_MODEL env var overrides scan tier."""
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "custom-haiku-model")
        # Need to reimport the module to pick up env var
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["scan"] == "custom-haiku-model"
        finally:
            # Restore defaults
            monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_env_override_write_model(self, monkeypatch):
        """CLAUDE_WRITE_MODEL env var overrides write tier."""
        monkeypatch.setenv("CLAUDE_WRITE_MODEL", "custom-sonnet-model")
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["write"] == "custom-sonnet-model"
        finally:
            monkeypatch.delenv("CLAUDE_WRITE_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_env_override_orchestrate_model(self, monkeypatch):
        """CLAUDE_ORCHESTRATE_MODEL env var overrides orchestrate tier."""
        monkeypatch.setenv("CLAUDE_ORCHESTRATE_MODEL", "custom-opus-model")
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["orchestrate"] == "custom-opus-model"
        finally:
            monkeypatch.delenv("CLAUDE_ORCHESTRATE_MODEL", raising=False)
            importlib.reload(kb.config)

    def test_partial_override_preserves_others(self, monkeypatch):
        """Setting one env var doesn't affect other tiers."""
        monkeypatch.setenv("CLAUDE_SCAN_MODEL", "custom-scan")
        import importlib

        import kb.config
        importlib.reload(kb.config)
        try:
            assert kb.config.MODEL_TIERS["scan"] == "custom-scan"
            assert kb.config.MODEL_TIERS["write"] == "claude-sonnet-4-6"
            assert kb.config.MODEL_TIERS["orchestrate"] == "claude-opus-4-6"
        finally:
            monkeypatch.delenv("CLAUDE_SCAN_MODEL", raising=False)
            importlib.reload(kb.config)
