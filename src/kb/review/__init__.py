"""Page review + refinement helpers (implementation-only namespace).

Submodules in this package are imported via fully-qualified paths
(``kb.review.context``, ``kb.review.refiner``); nothing is re-exported at
the package level. ``__all__`` is intentionally empty so star-imports are
a no-op and so static analyzers flag any future drift toward implicit
re-exports.

Cycle 42 AC7 — added module docstring + explicit empty ``__all__`` per the
"implementation-only namespace" pattern documented for Phase 4.6 LOW.
"""

__all__: tuple[str, ...] = ()
