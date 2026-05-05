"""Cycle 66 AC2 — secret-scrub key set derives from CLI_BACKEND_ENV_INJECT.

Pins:
  - T2: argv leak of 5 net-new keys (GEMINI/KIMI/QWEN/ZAI/ZHIPUAI) is now blocked.
  - T3: substring-scrub false-positive — intended behaviour preserved (negative
        control: literal env-var name in argv WITHOUT the value set in env does
        not raise).
  - T4: revert hazard CLOSED. The parametrize source is the LIVE canonical map
        `kb.config.CLI_BACKEND_ENV_INJECT.values()` flattened, NOT a literal
        mirror of the post-AC2 _SCRUB_KEYS frozenset. If a future commit reverts
        the production helper to a hardcoded list and forgets one of the keys,
        the parametrize case for that key fires RED.

Late-bind production symbols via `kb.utils.cli_backend.X` and `kb.utils.llm.X`
attribute access per cycle-20 L1 reload-leak hazard (sibling tests in the
suite call `importlib.reload(kb.utils.cli_backend)` / `importlib.reload(
kb.utils.llm)`, which would invalidate `from`-imported names).
"""

import pytest

import kb.config
import kb.utils.cli_backend
import kb.utils.llm

# Source-of-truth: the canonical map plus 4 standalone keys. NEVER hardcode.
# This MUST exactly mirror the derivation logic inside
# `kb.utils.cli_backend._SCRUB_KEYS` so a revert that hardcodes the production
# list (and forgets one) fires RED here.
_CANONICAL_SCRUB_KEYS = sorted(
    {"ANTHROPIC_API_KEY", "FIRECRAWL_API_KEY", "MIMOCODING_API_KEY", "MIMOCHAT_API_KEY"}
    | {key for keys in kb.config.CLI_BACKEND_ENV_INJECT.values() for key in keys}
)


@pytest.mark.parametrize("key", _CANONICAL_SCRUB_KEYS)
def test_scrub_blocks_argv_with_env_value(key, monkeypatch):
    """For each canonical scrub key: setting it in env then placing the value
    in an argv element MUST raise LLMError.

    Closes T2 (5 net-new keys gain coverage) and T4 (parametrize source is
    canonical — revert that hardcodes a 6-key list fires here for the missing
    GEMINI/KIMI/QWEN/ZAI/ZHIPUAI cases).
    """
    sentinel = f"SENTINEL-NOT-A-REAL-KEY-{key}-12345"
    monkeypatch.setenv(key, sentinel)
    with pytest.raises(kb.utils.llm.LLMError, match=r"(?i)refusing to place env secret"):
        kb.utils.cli_backend._check_no_secrets_on_argv(
            ["kb", "--header", f"Authorization: Bearer {sentinel}"]
        )


def test_scrub_allows_argv_without_env_value(monkeypatch):
    """T3 negative control: literal env-var NAME in argv must NOT raise unless
    the env VALUE is also set.

    The substring scrub looks for the env value, not the env name. This
    confirms the cycle-65 substring-scrub semantics are unchanged — adding the
    5 net-new keys did not introduce a false-positive on argv that mentions
    the literal name `GEMINI_API_KEY`.
    """
    for key in _CANONICAL_SCRUB_KEYS:
        monkeypatch.delenv(key, raising=False)
    # Mention every canonical key as a literal in argv. Env values are unset,
    # so the substring scan should not fire for any of them.
    argv = ["kb", "--note", "discussing " + " ".join(_CANONICAL_SCRUB_KEYS)]
    kb.utils.cli_backend._check_no_secrets_on_argv(argv)


def test_scrub_empty_env_value(monkeypatch):
    """Empty env value short-circuits the scrub even when the literal env-var
    name appears in argv (matches the cycle-65 behaviour preserved here)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    kb.utils.cli_backend._check_no_secrets_on_argv(
        ["kb", "--header", "Authorization: Bearer ANTHROPIC_API_KEY"]
    )


def test_scrub_keys_set_matches_production_module():
    """Defence-in-depth: the canonical sorted list this test uses to parametrize
    must equal the production `_SCRUB_KEYS` frozenset (sorted). Diverging the
    two means one side has drifted from the canonical map.
    """
    assert sorted(kb.utils.cli_backend._SCRUB_KEYS) == _CANONICAL_SCRUB_KEYS, (
        "Production _SCRUB_KEYS has drifted from the canonical CLI_BACKEND_ENV_INJECT-derived set."
    )
