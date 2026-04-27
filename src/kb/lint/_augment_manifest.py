"""Compatibility shim for `kb.lint.augment.manifest`.

Cycle-44 transition shim; delete in cycle 45 after legacy patch sites migrate.
"""

from __future__ import annotations

import sys
import types

from kb.lint.augment import manifest as _manifest
from kb.lint.augment.manifest import (
    MANIFEST_DIR,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    RESUME_COMPLETE_STATES,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    TERMINAL_STATES,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    Manifest,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)


class _CompatShim(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        if name in {"MANIFEST_DIR", "Manifest"}:
            setattr(_manifest, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _CompatShim
