"""Cycle 36 AC6 — predicate for tests that risk a real Anthropic API call.

Tests that ENTER code paths ultimately calling
``anthropic.Anthropic(...).messages.create(...)`` should mark themselves with
``@pytest.mark.skipif(not requires_real_api_key(), reason=...)``.

The CI runner sets ``ANTHROPIC_API_KEY=sk-ant-dummy-key-for-ci-tests-only``
(see ``.github/workflows/ci.yml`` env block), so the dummy-prefix check
identifies CI environments without coupling to a specific CI provider env
var (``CI=true`` would also catch local ``act`` runs and is reserved for
the cycle-23 multiprocessing skipif per cycle 36 AC2).

The dummy-prefix is matched broadly via ``startswith("sk-ant-dummy-key-")``
so any future CI key with that prefix is correctly identified as dummy.
"""

import os

_DUMMY_KEY_PREFIX = "sk-ant-dummy-key-"


def requires_real_api_key() -> bool:
    """Return True iff ``ANTHROPIC_API_KEY`` appears to be a real key.

    Returns False when:
    - ``ANTHROPIC_API_KEY`` is unset or empty.
    - ``ANTHROPIC_API_KEY`` starts with the documented CI dummy prefix
      ``sk-ant-dummy-key-``.

    Returns True when:
    - ``ANTHROPIC_API_KEY`` is set, non-empty, and does NOT start with the
      dummy prefix (i.e. a real developer-machine key).
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key) and not key.startswith(_DUMMY_KEY_PREFIX)
