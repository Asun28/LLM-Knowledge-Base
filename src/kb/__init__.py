"""LLM Knowledge Base — compile raw sources into an interlinked markdown wiki."""

__version__ = "0.11.0"

__all__ = [
    "ingest_source",
    "compile_wiki",
    "query_wiki",
    "build_graph",
    "WikiPage",
    "RawSource",
    "LLMError",
    "KBError",
    "IngestError",
    "CompileError",
    "QueryError",
    "ValidationError",
    "StorageError",
    "__version__",
]

# Cycle 20 AC3: dispatch table for kb.errors.* lazy re-exports. Mapping avoids
# repeating six almost-identical `if name == "X"` branches in ``__getattr__``.
_ERROR_NAMES = frozenset(
    {
        "KBError",
        "IngestError",
        "CompileError",
        "QueryError",
        "ValidationError",
        "StorageError",
    }
)


def __getattr__(name: str):
    """Lazily expose public API symbols without loading the full package on --version."""
    if name == "ingest_source":
        from kb.ingest import ingest_source

        return ingest_source
    if name == "compile_wiki":
        from kb.compile import compile_wiki

        return compile_wiki
    if name == "query_wiki":
        from kb.query import query_wiki

        return query_wiki
    if name == "build_graph":
        from kb.graph import build_graph

        return build_graph
    if name in {"WikiPage", "RawSource"}:
        from kb.models import RawSource, WikiPage

        return {"WikiPage": WikiPage, "RawSource": RawSource}[name]
    if name == "LLMError":
        from kb.utils.llm import LLMError

        return LLMError
    if name in _ERROR_NAMES:
        import kb.errors as _errors_mod

        return getattr(_errors_mod, name)
    raise AttributeError(f"module 'kb' has no attribute {name!r}")
