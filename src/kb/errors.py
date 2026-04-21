"""KB-wide exception taxonomy.

Cycle 20 AC1: `KBError` is the single base class for kb-originated errors;
five specialisations (`IngestError`, `CompileError`, `QueryError`,
`ValidationError`, `StorageError`) cover the hot paths. `LLMError` and
`CaptureError` reparent to `KBError` (see `kb.utils.llm` and `kb.capture`).

Rules (see also CLAUDE.md "Error Handling Conventions"):
- New code raising a kb-originated error should subclass the nearest specialised
  `KBError`. Bare `except Exception` is only acceptable at boundary layers (CLI
  top-level, MCP tool wrappers, LLM retry loop, per-source continue-on-error
  loops inside `compile_wiki`).
- `StorageError` carries structured metadata in `.kind` and `.path`; `__str__`
  hides the filesystem path unless both are set, and even then emits a
  redacted placeholder (`<path_hidden>`) — the raw path stays on the instance
  for local-debug introspection but never leaks into logs or MCP responses.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "KBError",
    "IngestError",
    "CompileError",
    "QueryError",
    "ValidationError",
    "StorageError",
]


class KBError(Exception):
    """Base class for all kb-originated errors."""


class IngestError(KBError):
    """Raised inside `kb.ingest.pipeline.ingest_source` for ingest failures."""


class CompileError(KBError):
    """Raised inside `kb.compile.compiler.compile_wiki` for compile failures."""


class QueryError(KBError):
    """Raised inside query engine for synthesis / retrieval failures.

    Call sites: ``kb.query.engine.query_wiki`` and ``search_pages``.
    """


class ValidationError(KBError):
    """Input-validation failure (page_id, wiki_dir, manifest_key, notes length, etc.)."""


class StorageError(KBError):
    """Atomic-write, file-lock, manifest-save, or evidence-trail append failure.

    Cycle 20 T1 mitigation: ``path`` is stored on the instance (so local
    debuggers can introspect via ``err.path``) but is NEVER rendered in
    ``__str__`` output — even when ``kind`` is set, the path is replaced with
    the literal ``<path_hidden>`` placeholder to defeat log-aggregator path
    disclosure.
    """

    def __init__(
        self,
        msg: str,
        *,
        kind: str | None = None,
        path: Path | None = None,
    ) -> None:
        super().__init__(msg)
        self.kind = kind
        self.path = path

    def __str__(self) -> str:
        msg = super().__str__()
        if self.kind is not None and self.path is not None:
            return f"{self.kind}: <path_hidden>"
        return msg
