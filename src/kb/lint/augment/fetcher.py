"""Fetch-phase facade for augment.

The network fetch implementation remains in `kb.lint.fetcher`; this module
provides the phase-local package path for imports introduced by the Cycle 44
augment split.
"""

from __future__ import annotations

from kb.lint.fetcher import (
    AugmentFetcher,  # noqa: F401  # re-exported for augment split (cycle 44)
    FetchResult,  # noqa: F401  # re-exported for augment split (cycle 44)
    _registered_domain,  # noqa: F401  # re-exported for augment split (cycle 44)
    _url_is_allowed,  # noqa: F401  # re-exported for augment split (cycle 44)
)
