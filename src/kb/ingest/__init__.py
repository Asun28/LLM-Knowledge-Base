"""Ingest module — read raw sources and create wiki pages."""

__all__ = ["ingest_source"]


def __getattr__(name: str):
    """Lazily expose ingest exports without loading the pipeline on package import."""
    if name == "ingest_source":
        from kb.ingest.pipeline import ingest_source as _is

        globals()["ingest_source"] = _is
        return _is
    raise AttributeError(f"module 'kb.ingest' has no attribute {name!r}")
