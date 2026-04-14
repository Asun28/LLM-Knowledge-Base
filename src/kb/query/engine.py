"""Query engine — BM25 + vector hybrid search + LLM synthesis with citations."""

import logging
from datetime import date
from pathlib import Path

from kb.config import (
    BM25_B,
    BM25_K1,
    MAX_SEARCH_RESULTS,
    PAGERANK_SEARCH_WEIGHT,
    PROJECT_ROOT,
    QUERY_CONTEXT_MAX_CHARS,
    QUERY_MAX_TOKENS,
    SEARCH_TITLE_WEIGHT,
    VECTOR_INDEX_PATH_SUFFIX,
)
from kb.graph.builder import build_graph
from kb.query.bm25 import BM25Index, tokenize
from kb.query.citations import extract_citations
from kb.query.dedup import dedup_results
from kb.query.hybrid import hybrid_search
from kb.utils.llm import call_llm
from kb.utils.pages import load_all_pages, load_purpose

logger = logging.getLogger(__name__)


def search_pages(question: str, wiki_dir: Path | None = None, max_results: int = 10) -> list[dict]:
    """Search wiki pages using hybrid BM25 + vector ranking with RRF fusion.

    Builds a BM25 index over all wiki pages (title tokens boosted by
    SEARCH_TITLE_WEIGHT) and combines it with vector search via RRF fusion.
    Falls back gracefully to BM25-only when the vector index does not exist.

    Args:
        question: The search query.
        wiki_dir: Path to wiki directory.
        max_results: Maximum number of results to return.

    Returns:
        List of matching page dicts sorted by relevance score (descending).
    """
    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))
    pages = load_all_pages(wiki_dir)
    if not pages:
        return []

    # Tokenize query; return empty if all tokens are stopwords (correct behavior)
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    # Build document corpus: title tokens (boosted) + content tokens
    # NOTE: Index rebuilt per-query. Acceptable at current wiki size (~200 pages).
    # Add module-level cache keyed on wiki-dir mtime before Phase 4 corpus growth.
    documents = []
    for page in pages:
        # Title tokens are repeated SEARCH_TITLE_WEIGHT times before indexing.
        # The muted practical effect is expected: title repetition inflates document
        # length, which BM25's length normalization (b parameter) partially cancels out.
        # The net effect is a moderate boost, not a multiplier.
        title_tokens = tokenize(page["title"]) * SEARCH_TITLE_WEIGHT
        content_tokens = tokenize(page["content_lower"])
        documents.append(title_tokens + content_tokens)

    # Build BM25 index once — shared by the bm25_search closure below
    index = BM25Index(documents)

    def bm25_search(query: str, lim: int) -> list[dict]:
        qtoks = tokenize(query)
        if not qtoks:
            return []
        sc = index.score(qtoks, k1=BM25_K1, b=BM25_B)
        hits = []
        for i, score in enumerate(sc):
            if score > 0:
                hits.append({**pages[i], "score": round(score, 4)})
        hits.sort(key=lambda p: p["score"], reverse=True)
        return hits[:lim]

    def vector_search(query: str, lim: int) -> list[dict]:
        try:
            from kb.query.embeddings import embed_texts, get_vector_index

            vec_path = Path(PROJECT_ROOT) / VECTOR_INDEX_PATH_SUFFIX
            if not vec_path.exists():
                return []
            vecs = embed_texts([query])
            if not vecs:
                return []
            idx = get_vector_index(str(vec_path))
            hits = idx.query(vecs[0], limit=lim)
            page_map = {p["id"]: p for p in pages}
            results = []
            for pid, dist in hits:
                if pid in page_map:
                    results.append({**page_map[pid], "score": round(1.0 / (1.0 + dist), 4)})
            return results
        except Exception as e:
            logger.debug("Vector search unavailable: %s", e)
            return []

    # Hybrid search: RRF fusion of BM25 + vector results
    scored = hybrid_search(question, bm25_search, vector_search, limit=max_results * 2)
    scored = dedup_results(scored)

    # Blend PageRank into scores if weight > 0
    pagerank_scores: dict[str, float] = {}
    if PAGERANK_SEARCH_WEIGHT > 0:
        pagerank_scores = _compute_pagerank_scores(wiki_dir)

    if pagerank_scores:
        blended = []
        for r in scored:
            pr = pagerank_scores.get(r["id"].lower(), 0.0)
            new_score = r["score"] * (1 + PAGERANK_SEARCH_WEIGHT * pr)
            blended.append({**r, "score": round(new_score, 4)})
        blended.sort(key=lambda p: p["score"], reverse=True)
        scored = blended

    scored = _flag_stale_results(scored[:max_results])
    return scored


def _compute_pagerank_scores(wiki_dir: Path | None = None) -> dict[str, float]:
    """Compute normalized PageRank scores for all wiki pages.

    Returns a dict mapping page_id to normalized PageRank (0.0 to 1.0).
    Normalized so the maximum PageRank in the graph maps to 1.0.
    """
    try:
        import networkx as nx

        graph = build_graph(wiki_dir)
        if graph.number_of_nodes() == 0:
            return {}
        if graph.number_of_edges() == 0:
            logger.debug("No wikilink edges — PageRank blending skipped")
            return {}
        pr = nx.pagerank(graph)
        max_pr = max(pr.values()) if pr else 1.0
        if max_pr == 0:
            return {}
        return {node: score / max_pr for node, score in pr.items()}
    except (nx.PowerIterationFailedConvergence, nx.NetworkXError, ValueError, OSError) as e:
        logger.debug("Failed to compute PageRank for search blending: %s", e)
        return {}


def _flag_stale_results(
    results: list[dict], project_root: Path | None = None
) -> list[dict]:
    """Flag results where page updated date is older than newest source mtime.

    Adds 'stale': True/False to each result dict. Non-destructive — modifies
    copies of the input dicts.
    """
    root = project_root or PROJECT_ROOT
    flagged = []
    for r in results:
        r = {**r, "stale": False}
        updated_str = r.get("updated", "")
        sources = r.get("sources", [])
        if not updated_str or not sources:
            flagged.append(r)
            continue
        try:
            page_date = date.fromisoformat(str(updated_str))
        except (ValueError, TypeError):
            flagged.append(r)
            continue
        newest_source_mtime = None
        for src in sources:
            src_path = root / src
            if src_path.exists():
                mtime = date.fromtimestamp(src_path.stat().st_mtime)
                if newest_source_mtime is None or mtime > newest_source_mtime:
                    newest_source_mtime = mtime
        if newest_source_mtime and newest_source_mtime > page_date:
            r["stale"] = True
        flagged.append(r)
    return flagged


def search_raw_sources(
    question: str, raw_dir: Path | None = None, max_results: int = 5
) -> list[dict]:
    """Search raw/ source files using BM25 for verbatim context fallback.

    Returns list of dicts with keys: id, path, content, score.
    """
    from kb.config import RAW_DIR

    raw_dir = raw_dir or RAW_DIR
    if not raw_dir.exists():
        return []

    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    sources = []
    for subdir in raw_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith(".") or subdir.name == "assets":
            continue
        for f in subdir.glob("*.md"):
            try:
                content = f.read_text(encoding="utf-8")
                sources.append({
                    "id": f"raw/{subdir.name}/{f.name}",
                    "path": str(f),
                    "content": content,
                    "content_lower": content.lower(),
                })
            except (OSError, UnicodeDecodeError):
                continue

    if not sources:
        return []

    documents = [tokenize(s["content_lower"]) for s in sources]
    index = BM25Index(documents)
    scores = index.score(query_tokens, k1=BM25_K1, b=BM25_B)

    scored = []
    for i, score in enumerate(scores):
        if score > 0:
            scored.append({**sources[i], "score": round(score, 4)})

    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:max_results]


def _build_query_context(pages: list[dict], max_chars: int = QUERY_CONTEXT_MAX_CHARS) -> dict:
    """Build context string from matching wiki pages using tiered loading.

    Tier 1: Summary pages loaded first (up to CONTEXT_TIER1_BUDGET).
    Tier 2: Non-summary pages loaded in score order (remaining budget).

    Returns:
        dict with keys:
            context: The formatted context string.
            context_pages: List of page IDs actually included in context.
    """
    if not pages:
        return {"context": "No relevant wiki pages found.", "context_pages": []}

    from kb.config import CONTEXT_TIER1_BUDGET, CONTEXT_TIER2_BUDGET

    effective_max = min(max_chars, CONTEXT_TIER1_BUDGET + CONTEXT_TIER2_BUDGET)
    summaries = [p for p in pages if p.get("type") == "summary"]
    others = [p for p in pages if p.get("type") != "summary"]

    sections = []
    context_pages = []
    total = 0
    skipped = 0

    def _try_add(page: dict) -> bool:
        nonlocal total, skipped
        section = (
            f"--- Page: {page['id']} (type: {page.get('type', 'unknown')}, "
            f"confidence: {page.get('confidence', 'unknown')}) ---\n"
            f"Title: {page['title']}\n\n{page['content']}\n"
        )
        if total + len(section) > effective_max:
            if not sections:
                # First page — truncate rather than skip
                remaining = effective_max - total
                header_len = len(section) - len(page["content"])
                if remaining > header_len:
                    logger.warning(
                        "Top-ranked page %s (%d chars) exceeds context limit (%d); truncating",
                        page["id"],
                        len(section),
                        effective_max,
                    )
                    sections.append(section[:remaining])
                    context_pages.append(page["id"])
                    total += remaining
                    return True
            skipped += 1
            return False
        sections.append(section)
        context_pages.append(page["id"])
        total += len(section)
        return True

    # Tier 1: summaries — capped by CONTEXT_TIER1_BUDGET
    tier1_used = 0
    for p in summaries:
        if tier1_used >= CONTEXT_TIER1_BUDGET:
            skipped += 1
            continue
        before = total
        if _try_add(p):
            tier1_used += total - before  # how much _try_add added

    # Tier 2: everything else
    for p in others:
        _try_add(p)

    if skipped:
        logger.info(
            "Query context: included %d pages, skipped %d (limit: %d chars)",
            len(sections), skipped, effective_max,
        )

    if not sections and pages:
        skipped = max(0, skipped - 1)
        top = pages[0]
        header = (
            f"--- Page: {top['id']} (type: {top.get('type', 'unknown')}, "
            f"confidence: {top.get('confidence', 'unknown')}) ---\n"
            f"Title: {top['title']}\n\n"
        )
        if effective_max <= len(header):
            return {"context": "No relevant wiki pages found.", "context_pages": []}
        section = header + top["content"]
        sections.append(section[:effective_max])
        context_pages.append(top["id"])

    return {"context": "\n".join(sections), "context_pages": context_pages}


def query_wiki(
    question: str,
    wiki_dir: Path | None = None,
    max_results: int = 10,
    conversation_context: str | None = None,
    *,
    output_format: str | None = None,
) -> dict:
    """Query the knowledge base and synthesize an answer.

    Args:
        question: The user's question.
        wiki_dir: Path to wiki directory (uses config default if None).
        max_results: Maximum number of pages to retrieve for context.
        conversation_context: Recent conversation history for follow-up query rewriting.
        output_format: If set and non-text, render the result to a file under
            OUTPUTS_DIR. One of: 'text', 'markdown', 'marp', 'html', 'chart',
            'jupyter'. Keyword-only to preserve existing callers.

    Returns:
        dict with keys:
            question: The original question.
            answer: LLM-synthesized answer text.
            citations: list of dicts, each with keys 'type' ('wiki'|'raw'),
                'path' (str), 'context' (str surrounding text).
            source_pages: list of page IDs retrieved by BM25 search.
            context_pages: list of page IDs actually included in LLM context.
            output_path: str (only when output_format is set, non-text, and
                answer synthesized).
            output_format: str (only when output_path is present).
            output_error: str (only when the adapter failed — answer still usable).
    """
    # Rewrite follow-up queries into standalone queries
    effective_question = question
    if conversation_context:
        from kb.query.rewriter import rewrite_query
        effective_question = rewrite_query(question, conversation_context)

    # 1. Search for relevant pages
    matching_pages = search_pages(effective_question, wiki_dir, max_results=max_results)

    if not matching_pages:
        return {
            "question": question,
            "answer": "No relevant pages found in the knowledge base for this question.",
            "citations": [],
            "source_pages": [],
            "context_pages": [],
        }

    # 2. Build context from matching pages
    ctx = _build_query_context(matching_pages)
    context = ctx["context"]

    # Raw-source fallback: supplement thin wiki context with verbatim raw source content
    raw_context = ""
    if len(ctx["context"]) < QUERY_CONTEXT_MAX_CHARS // 2:
        raw_results = search_raw_sources(effective_question, max_results=3)
        if raw_results:
            raw_sections = []
            budget = QUERY_CONTEXT_MAX_CHARS - len(ctx["context"])
            for rs in raw_results:
                section = f"--- Raw Source: {rs['id']} (verbatim) ---\n{rs['content']}\n"
                if len(section) > budget:
                    if not raw_sections:  # first section — truncate rather than skip
                        raw_sections.append(section[:budget])
                    break
                raw_sections.append(section)
                budget -= len(section)
            if raw_sections:
                raw_context = "\n" + "\n".join(raw_sections)

    context = ctx["context"] + raw_context

    # 3. Synthesize answer with LLM
    purpose = load_purpose(wiki_dir)
    purpose_section = f"\nKB FOCUS (bias answers toward these goals):\n{purpose}\n" if purpose else ""

    prompt = f"""You are answering a question using a knowledge wiki as your source.
{purpose_section}
QUESTION: {effective_question[:2000].replace(chr(10), " ").replace(chr(13), " ")}

WIKI CONTEXT:
{context}

INSTRUCTIONS:
- Answer the question based ONLY on the wiki context provided.
- Cite your sources using [source: page_id] format (e.g., [source: concepts/rag]).
- If the wiki doesn't contain enough information, say so clearly.
- Be concise but thorough.
- Distinguish between stated facts and inferences.
"""

    answer = call_llm(
        prompt,
        tier="orchestrate",
        system=(
            "You are a knowledge base assistant. "
            "Answer questions using wiki content with inline citations."
        ),
        max_tokens=QUERY_MAX_TOKENS,
    )

    # 4. Extract citations from the answer
    citations = extract_citations(answer)

    result_dict = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_pages": [p["id"] for p in matching_pages],
        "context_pages": ctx["context_pages"],
    }

    # 5. Optional output adapter (Phase 4.11)
    if output_format and output_format.strip().lower() != "text":
        from kb.query.formats import render_output
        try:
            path = render_output(output_format, result_dict)
            if path is not None:
                result_dict["output_path"] = str(path)
                result_dict["output_format"] = output_format.strip().lower()
        except (ValueError, OSError) as e:
            logger.warning("Output format '%s' failed: %s", output_format, e)
            result_dict["output_error"] = str(e)

    return result_dict
