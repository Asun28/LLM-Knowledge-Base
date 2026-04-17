# Cycle 3 Planning Findings

Findings will record verified functions, file paths, signatures, and caller/test checks.

## Verified Definitions

- `src/kb/utils/llm.py:62` `def _make_api_call(kwargs: dict, model: str)`; `LLMError` currently has no custom `__init__` or `kind`.
- `src/kb/utils/io.py:149` `def file_lock(path: Path, timeout: float | None = None)`.
- `src/kb/feedback/store.py:97` `def add_feedback_entry(...)`; NFC target is before `dict.fromkeys(cited_pages)`.
- `src/kb/feedback/reliability.py:9` `def compute_trust_scores(path: Path | None = None)`.
- `src/kb/query/embeddings.py:146` `VectorIndex.build(...)`, `:180` `VectorIndex.query(...)`; `_index_cache` currently lacks its own lock.
- `src/kb/query/engine.py:449` `def query_wiki(...)`; no callers found that require exact return-key equality.
- `src/kb/query/hybrid.py:10` `def rrf_fusion(...)`; expansion cap is in `hybrid_search` as `[:3]`.
- `src/kb/ingest/contradiction.py:26` `def detect_contradictions(...)`; `detect_contradictions_with_metadata` not present and must be new sibling.
- `src/kb/ingest/extractors.py:204` `def build_extraction_prompt(...)`.
- `src/kb/ingest/pipeline.py:366` `def _update_existing_page(...)`.
- `src/kb/lint/checks.py:149` `def check_orphan_pages(...)`.
- `src/kb/lint/runner.py:23` `def run_all_checks(...)`; `src/kb/lint/verdicts.py:178` `def get_verdict_summary(path: Path | None = None)`.
- `src/kb/graph/export.py:47` `def export_mermaid(...)`.
- `src/kb/review/context.py:15` `def pair_page_with_sources(...)`, `:157` `def build_review_context(...)`.
- `src/kb/mcp/browse.py:117` `def kb_list_pages(page_type: str = "")`, `:151` `def kb_list_sources()`.
- `src/kb/mcp/health.py:130` `def kb_graph_viz(max_nodes: int = 30)`.
- `src/kb/cli.py:11` `def _truncate(msg: str, limit: int = 500)`.

## Compatibility Checks

- `grep -rn "query_wiki(" src/ tests/ docs/` found CLI/MCP/docs/tests callers; existing tests check required keys are present, not exact key equality.
- `kb_list_pages` existing tests call no args, positional `page_type`, and keyword `page_type`; adding keyword params must preserve this.
- `kb_list_sources` existing tests call no args only; adding keyword params is compatible.
- Existing `_truncate` tests expect `500 + "..."`; new test must update behavior in the new cycle file or only assert changed behavior there.
