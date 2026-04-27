"""Compatibility shim for `kb.lint.augment.rate`.

Cycle-44 transition shim; delete in cycle 45 after legacy patch sites migrate.
"""

from __future__ import annotations

import sys
import types

from kb.lint.augment import rate as _rate
from kb.lint.augment.rate import (
    RATE_PATH,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    RateLimiter,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)


class _CompatShim(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        if name in {"RATE_PATH", "RateLimiter"}:
            setattr(_rate, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _CompatShim
