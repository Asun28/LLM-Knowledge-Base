"""Query module — search wiki and synthesize answers with citations."""

__all__ = ["query_wiki", "search_pages"]


def __getattr__(name: str):
    """Lazily expose query exports without loading the engine on package import.

    Cycle 23 AC4 — mirrors ``kb.ingest.__init__``. Deferring the engine load
    keeps ``anthropic``/``sentence-transformers`` out of ``sys.modules`` when
    the MCP server or CLI boots without actually running a query; the engine
    materialises on first attribute access and is cached thereafter.
    """
    if name == "query_wiki":
        from kb.query.engine import query_wiki as _qw

        globals()["query_wiki"] = _qw
        return _qw
    if name == "search_pages":
        from kb.query.engine import search_pages as _sp

        globals()["search_pages"] = _sp
        return _sp
    raise AttributeError(f"module 'kb.query' has no attribute {name!r}")


def __dir__():
    return sorted(set(list(globals()) + __all__))
