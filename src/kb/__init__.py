"""LLM Knowledge Base — compile raw sources into an interlinked markdown wiki."""

__version__ = "0.10.0"

from kb.compile import compile_wiki
from kb.graph import build_graph
from kb.ingest import ingest_source
from kb.models import RawSource, WikiPage
from kb.query import query_wiki
from kb.utils.llm import LLMError

__all__ = [
    "ingest_source",
    "compile_wiki",
    "query_wiki",
    "build_graph",
    "WikiPage",
    "RawSource",
    "LLMError",
    "__version__",
]
