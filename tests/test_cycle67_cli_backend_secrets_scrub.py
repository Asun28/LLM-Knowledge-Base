"""Cycle 67 AC15 — `_check_no_secrets_on_argv` design-intent lock-in tests.

Mimo r4 A claimed `_check_no_secrets_on_argv` does a "self-DoS via generic
regex match on full argv" — VERIFIED INCORRECT by inspecting the function
at `src/kb/utils/cli_backend.py:132-157`. The function does NOT regex-match
argv; it iterates known env-var keys (`_SCRUB_KEYS`) and scans argv for
ACTUAL VALUE substrings of the env vars.

This file adds three test cases that lock the design intent so a future
maintainer who tries to "simplify" the scan to a regex-on-argv (which
WOULD re-introduce the false-positive class mimo claimed exists today)
fails the gate.

NO production code change. Pure documentation-via-test of existing
behavior at `_check_no_secrets_on_argv`.

Per `feedback_no_secrets_in_code`: synthetic env values are split-string
constructed so platform secret scanners (e.g. GitHub push protection)
do not block the commit.
"""

from __future__ import annotations

import pytest

from kb.utils.cli_backend import _check_no_secrets_on_argv
from kb.utils.llm import LLMError


# Split-string construction so platform scanners don't tag the literal as a
# real secret. The actual env value is the concatenated string, which is what
# `_check_no_secrets_on_argv` matches against argv.
_SYNTHETIC_VALUE = "synthetic" + "_test_value_" + "cycle67_NotARealKey"
_SCRUB_KEY = "FIRECRAWL_API_KEY"  # one of the keys in _SCRUB_KEYS


def test_t15a_bare_equality_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """T15-A: argv element EQUALS the env value verbatim → LLMError raised.

    This is the cycle-65 Step 09 background review's primary case (bare
    equality / equality-shaped exfiltration).
    """
    monkeypatch.setenv(_SCRUB_KEY, _SYNTHETIC_VALUE)
    argv = ["mybackend", "--flag", _SYNTHETIC_VALUE]
    with pytest.raises(LLMError) as exc_info:
        _check_no_secrets_on_argv(argv)
    assert _SCRUB_KEY in str(exc_info.value), (
        f"LLMError message must name the offending env key {_SCRUB_KEY}; "
        f"got: {exc_info.value!s}"
    )


def test_t15b_embedded_in_flag_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """T15-B: argv element CONTAINS the env value as a substring (embedded
    in a header/prefix) → LLMError raised.

    This is the cycle-65 Step 09 background review's added case: an attacker
    or careless caller might construct `f"Authorization: Bearer {value}"`.
    Bare equality would miss this; substring containment catches it.
    """
    monkeypatch.setenv(_SCRUB_KEY, _SYNTHETIC_VALUE)
    embedded = "Authorization: Bearer " + _SYNTHETIC_VALUE
    argv = ["mybackend", "--header", embedded]
    with pytest.raises(LLMError):
        _check_no_secrets_on_argv(argv)


def test_t15c_key_name_only_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """T15-C (false-positive guard): argv contains the env-var KEY NAME
    (literal `"FIRECRAWL_API_KEY"`), NOT the env-var VALUE → does NOT raise.

    This pins the design intent against the mimo r4 A finding ("generic
    regex match on full argv would self-DoS on benign argv elements").
    The current function does NOT regex-match key names. Future maintainer
    who simplifies to `re.match(KEY_NAME_RE, elem)` would FAIL this test.
    """
    monkeypatch.setenv(_SCRUB_KEY, _SYNTHETIC_VALUE)
    # argv contains the LITERAL key-name string but NOT the env value.
    argv = ["mybackend", "--describe", _SCRUB_KEY]
    _check_no_secrets_on_argv(argv)  # must NOT raise


def test_t15c_partial_value_substring_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Additional false-positive guard: argv contains a STRICT PREFIX of the
    env value (not the full value). Should not raise — substring containment
    requires the full value to appear.

    Pins the substring contract (`if secret_value in elem`): the WHOLE
    secret must appear, not just a prefix shared with other strings.
    """
    monkeypatch.setenv(_SCRUB_KEY, _SYNTHETIC_VALUE)
    prefix = _SYNTHETIC_VALUE[:10]  # strict prefix of the synthetic value
    argv = ["mybackend", "--user-agent", f"app/{prefix}"]
    _check_no_secrets_on_argv(argv)  # must NOT raise


def test_t15_empty_env_value_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive: if env var is unset/empty, the scrub short-circuits the
    inner loop (`if not secret_value: continue`). This documents the
    early-out behavior so a future maintainer doesn't change the order of
    checks.
    """
    monkeypatch.delenv(_SCRUB_KEY, raising=False)
    argv = ["mybackend", "--flag", _SYNTHETIC_VALUE]
    # Despite the synthetic value being on argv, scrub does NOT raise because
    # the env var is unset (no value to match against).
    _check_no_secrets_on_argv(argv)


def test_t15_value_match_is_per_argv_element(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Element-level scan: the value scrub runs on each argv element
    independently. If the value spans multiple elements (one element has
    a prefix, another has the suffix), neither single element contains the
    full value, so no raise.

    This is technically a residual surface — if argv is reassembled into a
    shell line by the OS, the secret would reform. But our subprocess.run
    uses `shell=False` and never joins argv into a string, so the per-element
    invariant is what matters.
    """
    monkeypatch.setenv(_SCRUB_KEY, _SYNTHETIC_VALUE)
    half = len(_SYNTHETIC_VALUE) // 2
    argv = ["mybackend", _SYNTHETIC_VALUE[:half], _SYNTHETIC_VALUE[half:]]
    # Each element holds half the value; neither contains the full value.
    _check_no_secrets_on_argv(argv)
