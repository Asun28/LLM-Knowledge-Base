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
    "TierBoundaryError",
    "ValueDomainError",
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


class PageReadBudgetError(ValidationError):
    """Cycle 97 AC04: a wiki page could not be read within its byte budget.

    Raised by ``kb.review.context._read_page_within_budget`` in exactly two
    cases: the configured budget is non-positive, or the budget cut the read
    before the page's frontmatter block closed. The second is the one that
    matters — ``frontmatter.parse`` answers an unclosed block by returning
    empty metadata and the whole prefix as content, which is indistinguishable
    from a page that legitimately has no frontmatter. A review context built on
    that reports every field as ``unknown`` and no sources at all, so the
    pairing helper fails closed instead.

    Deliberately NOT a ``ValueError`` subclass: the pairing helper's broad
    ``except (OSError, ValueError, AttributeError, yaml.YAMLError,
    UnicodeDecodeError)`` would otherwise swallow it and re-label a budget
    problem as malformed YAML, sending the operator to the page instead of to
    ``PAIRED_PAGE_READ_MAX_BYTES``. Subclassing ``ValidationError`` keeps it
    inside the ``KBError`` tree for callers that catch broadly.
    """


class TierBoundaryError(ValidationError):
    """Cycle 73 AC04: scan-tier → orchestrate-tier output rejected at the
    cross-tier verification boundary.

    Raised by ``kb.lint.augment.orchestrator._validate_tier_boundary`` when
    a scan-tier ``_call_llm_json`` response fails the orchestrate-tier
    consumption rules (extra key, oversize string, deep nesting,
    unsupported value type, non-dict root). Subclasses ``ValidationError``
    so legacy ``except ValidationError`` catch sites still catch it; a
    more-specific ``except TierBoundaryError`` handler in the orchestrator
    distinguishes the failure forensically (``manifest.advance(stub_id,
    'failed', payload={'reason': 'tier_boundary_rejected: ...'})``).

    Threat-model: T4 (EscalationOfPrivilege — bounds the blast radius of
    cycle-72's prompt-injection probability reduction).
    """


class ValueDomainError(TierBoundaryError):
    """Cycle 86 AC02: a scan-tier response carried a value outside the
    schema-declared vocabulary for its key.

    Distinct from its ``TierBoundaryError`` parent, which covers the KEY
    domain (unexpected key, missing required key) plus the shape bounds
    (depth, string length, key count). This subclass covers the VALUE
    domain: ``{"action": "exfiltrate"}`` has a perfectly legal key set
    and shape, so nothing before cycle 86 rejected it at the boundary —
    the permitted-action enum lived only in JSON-schema text plus a
    hand-rolled ``if`` at each call site, which meant every new caller
    had to re-implement the check or silently inherit the gap.

    Subclasses ``TierBoundaryError`` (and therefore ``ValidationError``)
    so every legacy ``except TierBoundaryError`` / ``except
    ValidationError`` site still catches it. Callers that want forensic
    distinctness split-catch this class FIRST and record the
    ``action_not_in_vocabulary: ...`` reason, mirroring how cycle-73 AC04
    split ``tier_boundary_rejected: ...`` out of the generic handler.

    Threat-model: T3 (EscalationOfPrivilege — an invented action must not
    reach an orchestrate-tier consumer).
    """


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
        # Cycle-19 L3 rule — truthy check excludes empty-string kind, so a
        # future caller that accidentally passes kind="" gets the raw msg
        # instead of a confusing `": <path_hidden>"` rendering. path is
        # compared to None explicitly because `Path("")` is falsy in some
        # Python versions; we want any non-None Path to trigger redaction.
        if self.kind and self.path is not None:
            return f"{self.kind}: <path_hidden>"
        return msg
