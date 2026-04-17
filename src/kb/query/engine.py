"""Query engine — BM25 + vector hybrid search + LLM synthesis with citations."""

import logging
import re
import sqlite3
import threading
from datetime import UTC, date, datetime
from pathlib import Path

from kb.config import (
    BM25_B,
    BM25_K1,
    MAX_SEARCH_RESULTS,
    PAGERANK_SEARCH_WEIGHT,
    PROJECT_ROOT,
    QUERY_CONTEXT_MAX_CHARS,
    QUERY_MAX_TOKENS,
    RAW_SOURCE_MAX_BYTES,
    SEARCH_TITLE_WEIGHT,
    VECTOR_INDEX_PATH_SUFFIX,
    WIKI_DIR,
)
from kb.graph.builder import build_graph
from kb.query.bm25 import BM25Index, tokenize
from kb.query.citations import extract_citations
from kb.query.dedup import dedup_results
from kb.query.hybrid import hybrid_search
from kb.utils.llm import call_llm
from kb.utils.markdown import FRONTMATTER_RE
from kb.utils.pages import load_all_pages, load_purpose
from kb.utils.text import wrap_purpose

logger = logging.getLogger(__name__)


def search_pages(
    question: str,
    wiki_dir: Path | None = None,
    max_results: int = 10,
    *,
    search_telemetry: dict | None = None,
) -> list[dict]:
    """Search wiki pages using hybrid BM25 + vector ranking with RRF fusion.

    Builds a BM25 index over all wiki pages (title tokens boosted by
    SEARCH_TITLE_WEIGHT) and combines it with vector search via RRF fusion.
    Falls back gracefully to BM25-only when the vector index does not exist.

    Args:
        question: The search query.
        wiki_dir: Path to wiki directory.
        max_results: Maximum number of results to return.
        search_telemetry: Optional mutable dict populated with backend
            attempt/result counts so callers can distinguish "hybrid
            attempted, zero hits" from "hybrid disabled" (cycle 3 H11 PR
            review R1 Codex MAJOR). Keys set: ``vector_attempts``,
            ``vector_hits``, ``bm25_hits``. Keyword-only — additive.

    Returns:
        List of matching page dicts sorted by relevance score (descending).
    """
    max_results = max(1, min(max_results, MAX_SEARCH_RESULTS))

    # Tokenize query; return empty if all tokens are stopwords (correct behavior)
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    # Cycle 4 item #16 — wiki-side BM25 cache. Keyed on
    # (wiki_dir, page_count, max_mtime_ns, BM25_TOKENIZER_VERSION) — see
    # _wiki_bm25_cache_key for invariants. Under FastMCP's thread pool two
    # concurrent queries may both miss the cache; we check once under the
    # lock, rebuild OUTSIDE the lock (avoids blocking other queries during
    # 100ms+ disk walk on large wikis), then double-check INSIDE the lock
    # before store so whoever finishes first wins.
    cache_key = _wiki_bm25_cache_key(wiki_dir)
    with _WIKI_BM25_CACHE_LOCK:
        cached = _WIKI_BM25_CACHE.get(cache_key) if cache_key is not None else None
    if cached is not None:
        pages, documents, index = cached
    else:
        pages = load_all_pages(wiki_dir)
        if not pages:
            return []
        documents = []
        for page in pages:
            # Title tokens are repeated SEARCH_TITLE_WEIGHT times before indexing.
            # The muted practical effect is expected: title repetition inflates document
            # length, which BM25's length normalization (b parameter) partially cancels out.
            # The net effect is a moderate boost, not a multiplier.
            title_tokens = tokenize(page["title"]) * SEARCH_TITLE_WEIGHT
            content_tokens = tokenize(page["content_lower"])
            documents.append(title_tokens + content_tokens)
        index = BM25Index(documents)
        if cache_key is not None:
            # PR R1 Codex MAJOR 2 — double-check under the lock before store AND
            # reuse whichever concurrent-rebuild-won. Mirrors _RAW_BM25_CACHE
            # single-flight pattern: if another thread finished first, drop
            # the local build and hand back the winner so both callers
            # operate on the same cached instance.
            with _WIKI_BM25_CACHE_LOCK:
                existing = _WIKI_BM25_CACHE.get(cache_key)
                if existing is not None:
                    pages, documents, index = existing
                else:
                    _WIKI_BM25_CACHE[cache_key] = (pages, documents, index)

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
        # Cycle 3 H11: narrow exception handling. The prior `except Exception`
        # swallowed programming bugs (AttributeError from a future refactor,
        # KeyError from schema drift) together with the expected failure
        # modes — silently degrading "hybrid" to BM25-only with no observable
        # signal. Now we only swallow import/open/type-mismatch failures.
        if search_telemetry is not None:
            search_telemetry["vector_attempts"] = search_telemetry.get("vector_attempts", 0) + 1
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
            if search_telemetry is not None:
                search_telemetry["vector_hits"] = search_telemetry.get("vector_hits", 0) + len(
                    results
                )
            return results
        except (ImportError, sqlite3.OperationalError, OSError, ValueError) as e:
            logger.debug("Vector search unavailable: %s", e)
            if search_telemetry is not None:
                search_telemetry["vector_failed"] = True
            return []

    # Hybrid search: RRF fusion of BM25 + vector results
    scored = hybrid_search(question, bm25_search, vector_search, limit=max_results * 2)
    scored = dedup_results(scored)

    # Blend PageRank into scores if weight > 0
    # Cycle 6 AC6 — pass pre-loaded `pages` to avoid a second disk walk;
    # `build_graph(pages=...)` already supports the kwarg (builder.py:37).
    pagerank_scores: dict[str, float] = {}
    if PAGERANK_SEARCH_WEIGHT > 0:
        pagerank_scores = _compute_pagerank_scores(wiki_dir, preloaded_pages=pages)

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


def _compute_pagerank_scores(
    wiki_dir: Path | None = None,
    *,
    preloaded_pages: list[dict] | None = None,
) -> dict[str, float]:
    """Compute normalized PageRank scores for all wiki pages.

    Returns a dict mapping page_id to normalized PageRank (0.0 to 1.0).
    Normalized so the maximum PageRank in the graph maps to 1.0.

    Cycle 6 AC4 — cached on (resolved wiki_dir, max_mtime_ns, page_count).
    Thread-safe under FastMCP's thread pool via `_PAGERANK_CACHE_LOCK`.
    Cycle 6 AC6 — accepts `preloaded_pages` to avoid a second disk walk
    when the caller has already invoked `load_all_pages`.
    """
    cache_key = _pagerank_cache_key(wiki_dir)
    if cache_key is not None:
        with _PAGERANK_CACHE_LOCK:
            cached = _PAGERANK_CACHE.get(cache_key)
        if cached is not None:
            return cached

    try:
        import networkx as nx

        graph = build_graph(wiki_dir, pages=preloaded_pages)
        if graph.number_of_nodes() == 0:
            result: dict[str, float] = {}
        elif graph.number_of_edges() == 0:
            logger.debug("No wikilink edges — PageRank blending skipped")
            result = {}
        else:
            pr = nx.pagerank(graph)
            max_pr = max(pr.values()) if pr else 1.0
            result = (
                {} if max_pr == 0 else {node: score / max_pr for node, score in pr.items()}
            )
    except (nx.PowerIterationFailedConvergence, nx.NetworkXError, ValueError, OSError) as e:
        logger.debug("Failed to compute PageRank for search blending: %s", e)
        return {}

    if cache_key is not None:
        with _PAGERANK_CACHE_LOCK:
            # Double-check: another thread may have populated the same key.
            existing = _PAGERANK_CACHE.get(cache_key)
            if existing is not None:
                return existing
            _PAGERANK_CACHE[cache_key] = result
    return result


def _flag_stale_results(results: list[dict], project_root: Path | None = None) -> list[dict]:
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
                # I1 (Phase 4.5 MEDIUM): UTC-aware mtime date computation. Prior
                # code used date.fromtimestamp(mtime) which applies local TZ,
                # while date.fromisoformat(updated_str) is naive. On DST/TZ
                # boundaries near midnight UTC the comparison would flip.
                mtime = datetime.fromtimestamp(src_path.stat().st_mtime, tz=UTC).date()
                if newest_source_mtime is None or mtime > newest_source_mtime:
                    newest_source_mtime = mtime
        if newest_source_mtime and newest_source_mtime > page_date:
            r["stale"] = True
        flagged.append(r)
    return flagged


# I2 (Phase 4.5 MEDIUM): module-level cache for search_raw_sources BM25
# index. Keyed on (resolved_raw_dir, file_count, max_mtime_ns) so deletion
# (count change) or any file update (mtime change) invalidates. Resolves
# the per-query rebuild hot path on large raw/ trees.
#
# PR review round 1 (Codex m-new-1): under FastMCP's thread pool two
# concurrent queries can both miss the cache and both rebuild. The lock
# serializes the check-then-set so only the first rebuild runs.
_RAW_BM25_CACHE: dict[tuple[str, int, int, int], tuple[list[dict], "BM25Index"]] = {}
_RAW_BM25_CACHE_LOCK = threading.Lock()

# Cycle 4 item #16 — wiki-side BM25 cache mirroring _RAW_BM25_CACHE. Keyed
# on (str(wiki_dir.resolve()), page_count, max_mtime_ns, BM25_TOKENIZER_VERSION)
# per Condition 10 so both file changes AND tokenizer-semantic edits
# (STOPWORDS prune, new BIDI stripping) invalidate the cache. Resolves the
# per-query corpus+index rebuild that dominated the search_pages hot path.
_WIKI_BM25_CACHE: dict[
    tuple[str, int, int, int], tuple[list[dict], list[list[str]], "BM25Index"]
] = {}
_WIKI_BM25_CACHE_LOCK = threading.Lock()

# Cycle 6 AC4 — PageRank process-level cache. Keyed on
# (str(wiki_dir.resolve()), max_mtime_ns, page_count) per Condition OQ1 so
# mtime-invariant file adds (test fixtures copied in via shutil.copy) still
# invalidate when page count changes. Unbounded per OQ2: mirrors the
# _WIKI_BM25_CACHE + _RAW_BM25_CACHE precedent — growth is bounded by
# distinct (wiki_dir, mtime_ns, count) snapshots per process, which is
# a handful in practice. FastMCP thread-pool safe via the paired lock.
_PAGERANK_CACHE: dict[tuple[str, int, int], dict[str, float]] = {}
_PAGERANK_CACHE_LOCK = threading.Lock()


def _pagerank_cache_key(wiki_dir: Path | None) -> tuple[str, int, int] | None:
    """Return cache key (wiki_dir, max_mtime_ns, page_count) or None on error."""
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    try:
        resolved = str(wiki_dir.resolve())
    except OSError:
        return None
    count = 0
    max_mtime = 0
    for subdir in wiki_dir.iterdir() if wiki_dir.exists() else ():
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        for f in subdir.glob("*.md"):
            try:
                count += 1
                mt = f.stat().st_mtime_ns
                if mt > max_mtime:
                    max_mtime = mt
            except OSError:
                continue
    return (resolved, max_mtime, count)


def _wiki_bm25_cache_key(wiki_dir: Path | None) -> tuple[str, int, int, int] | None:
    """Return cache key (wiki_dir, page_count, max_mtime_ns, tokenizer_version) or None."""
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    try:
        resolved = str(wiki_dir.resolve())
    except OSError:
        return None
    from kb.utils.text import BM25_TOKENIZER_VERSION

    count = 0
    max_mtime = 0
    for subdir in wiki_dir.iterdir() if wiki_dir.exists() else ():
        if not subdir.is_dir() or subdir.name.startswith("."):
            continue
        for f in subdir.glob("*.md"):
            try:
                count += 1
                mt = f.stat().st_mtime_ns
                if mt > max_mtime:
                    max_mtime = mt
            except OSError:
                continue
    return (resolved, count, max_mtime, BM25_TOKENIZER_VERSION)


# I3 (Phase 4.5 R4 HIGH): rewrite-leak detection. PR review round 1
# (Opus MINOR I3 + Codex M-NEW-1): the original `^[A-Z][a-zA-Z ]{0,40}:\s*`
# dropped legitimate domain-prefixed rewrites like "RAG: methodology".
# Replaced with a keyword-anchored pattern that only fires on known LLM
# scaffolding phrases.
# PR review round 2 (Codex): removed bare "alright" / "okay" / "sure"
# alternation — those matched legitimate conversational rewrite output.
# Each keyword now requires a trailing ,/./:/phrase that marks it as a
# preamble, not a legitimate leading word. Case-insensitive.
_LEAK_KEYWORD_RE = re.compile(
    r"^\s*("
    r"(sure|okay|certainly|alright)[,.!]?\s+(here|so|the|i('|')?ll)\b|"
    r"here(\'s)? (is|the|your)|"
    r"the (standalone|rewritten|revised)|"
    r"rewritten (query|question)|"
    r"standalone question is|"
    r"(rewritten|standalone|revised) (query|question)(\s+is)?:|"
    r"query:"
    r")",
    re.IGNORECASE,
)


def _raw_sources_cache_key(raw_dir: Path) -> tuple[str, int, int, int] | None:
    """Return cache key for raw_dir or None if it can't be computed.

    Cycle 4 item #18 — added ``BM25_TOKENIZER_VERSION`` as the 4th tuple
    component so any change to STOPWORDS or tokenize() semantics invalidates
    the cache on next query (mtime-based keys miss pure code edits).
    """
    try:
        resolved = str(raw_dir.resolve())
    except OSError:
        return None
    from kb.utils.text import BM25_TOKENIZER_VERSION

    count = 0
    max_mtime = 0
    for subdir in raw_dir.iterdir():
        if not subdir.is_dir() or subdir.name.startswith(".") or subdir.name == "assets":
            continue
        for f in subdir.glob("*.md"):
            try:
                count += 1
                mt = f.stat().st_mtime_ns
                if mt > max_mtime:
                    max_mtime = mt
            except OSError:
                continue
    return (resolved, count, max_mtime, BM25_TOKENIZER_VERSION)


def search_raw_sources(
    question: str, raw_dir: Path | None = None, max_results: int = 5
) -> list[dict]:
    """Search raw/ source files using BM25 for verbatim context fallback.

    Returns list of dicts with keys: id, path, content, score.

    I2 (Phase 4.5 MEDIUM): cache the BM25 index + loaded sources keyed on
    (raw_dir, file_count, max_mtime_ns) so subsequent queries skip the
    per-query disk rebuild. Cache is busted by any raw/*.md addition,
    deletion, or mtime bump.
    """
    from kb.config import RAW_DIR

    raw_dir = raw_dir or RAW_DIR
    if not raw_dir.exists():
        return []

    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    cache_key = _raw_sources_cache_key(raw_dir)
    # PR review round 2 (Codex MAJOR): the check-then-set lock alone let
    # two concurrent misses both rebuild the index (doubling disk I/O and
    # racing on shared state). Fix: check once under the lock; if miss,
    # rebuild OUTSIDE the lock to avoid blocking other queries for 1-2s of
    # disk I/O; then double-check INSIDE the lock before store so whoever
    # finishes first wins and the other reuses that result.
    with _RAW_BM25_CACHE_LOCK:
        cached = _RAW_BM25_CACHE.get(cache_key) if cache_key is not None else None
    if cached is not None:
        sources, index = cached
    else:
        sources = []
        for subdir in raw_dir.iterdir():
            if not subdir.is_dir() or subdir.name.startswith(".") or subdir.name == "assets":
                continue
            for f in subdir.glob("*.md"):
                # Item 13 (cycle 2): skip oversized files before read to prevent
                # a single 10 MB scraped article from ballooning the in-memory
                # corpus + BM25 index.
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                if size > RAW_SOURCE_MAX_BYTES:
                    logger.info(
                        "search_raw_sources skipped %s: %d bytes > %d cap",
                        f,
                        size,
                        RAW_SOURCE_MAX_BYTES,
                    )
                    continue
                try:
                    content = f.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                # Item 13 (cycle 2): strip YAML frontmatter before tokenizing.
                # Obsidian Web Clipper prepends `title:`, `author:`, `tags:` —
                # indexing those as body content mis-ranks hits toward files
                # whose frontmatter shares vocabulary with the question.
                fm_match = FRONTMATTER_RE.match(content) if content.startswith("---") else None
                body = fm_match.group(2) if fm_match else content
                sources.append(
                    {
                        "id": f"raw/{subdir.name}/{f.name}",
                        "path": str(f),
                        "content": content,
                        "content_lower": body.lower(),
                    }
                )

        if not sources:
            return []

        documents = [tokenize(s["content_lower"]) for s in sources]
        index = BM25Index(documents)
        if cache_key is not None:
            with _RAW_BM25_CACHE_LOCK:
                winner = _RAW_BM25_CACHE.get(cache_key)
                if winner is not None:
                    # Another thread populated the cache during our rebuild
                    # — use their result and discard ours.
                    sources, index = winner
                else:
                    _RAW_BM25_CACHE[cache_key] = (sources, index)

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
        # Cycle 3 H9: surface staleness in the LLM prompt so the synthesizer
        # can caveat or demote stale facts. `stale` is attached by
        # `_flag_stale_results` in search_pages; when True we prefix [STALE]
        # to the page header. The `stale_citations` return-dict field
        # (populated in query_wiki) is derived from the same signal so MCP
        # callers can expose it without re-parsing prompt text.
        stale_marker = "[STALE] " if page.get("stale") else ""
        section = (
            f"--- {stale_marker}Page: {page['id']} (type: {page.get('type', 'unknown')}, "
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

    # Phase 4.5 HIGH Q1: per-addition tier budget. Each summary must fit within
    # the REMAINING tier-1 budget, not just be checked against the cap as a
    # stopping rule. Prevents one 30K summary from starving tier 2.
    tier1_used = 0
    for p in summaries:
        tier1_remaining = CONTEXT_TIER1_BUDGET - tier1_used
        if tier1_remaining <= 0:
            skipped += 1
            continue
        section_estimate = len(p.get("content", "")) + 100  # header overhead
        if section_estimate > tier1_remaining and sections:
            # This summary would exceed tier-1 budget and we already have content
            skipped += 1
            continue
        before = total
        if _try_add(p):
            tier1_used += total - before

    # Tier 2: everything else
    for p in others:
        _try_add(p)

    if skipped:
        logger.info(
            "Query context: included %d pages, skipped %d (limit: %d chars)",
            len(sections),
            skipped,
            effective_max,
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
    raw_dir: Path | None = None,
) -> dict:
    """Query the knowledge base and synthesize an answer.

    Args:
        question: The user's question.
        wiki_dir: Path to wiki directory (uses config default if None).
        max_results: Maximum number of pages to retrieve for context.
        conversation_context: Recent conversation history for follow-up query rewriting.
        raw_dir: Path to raw/ directory for fallback search (keyword-only). When None
            and wiki_dir is set, derives raw_dir as wiki_dir.parent / "raw" (sibling
            directory) with a resolve() check that confirms raw/ has wiki/'s parent as
            its parent. Does NOT enforce PROJECT_ROOT containment — pass raw_dir
            explicitly if stricter scoping is needed.
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
    # Derive effective_raw_dir from wiki_dir when not explicitly provided (item 7 fix).
    # raw_dir is derived from wiki_dir; containment is guaranteed by construction.
    effective_raw_dir = raw_dir
    if effective_raw_dir is None and wiki_dir is not None:
        effective_raw_dir = (wiki_dir.parent / "raw").resolve()

    # Item 12 (cycle 2): collapse ALL Unicode whitespace (Unicode line
    # separators, paragraph separators, tabs, non-breaking spaces, etc.) to a
    # single space BEFORE any downstream consumer — prior code only replaced
    # `\n`/`\r` in the synthesis prompt line 544, so vertical tab `\v`,
    # `\u2028`, and `\u2029` still reflowed the prompt structure.
    normalized_question = re.sub(r"\s+", " ", question).strip()
    effective_question = normalized_question
    if conversation_context:
        from kb.query.rewriter import rewrite_query

        # Cycle 2 PR review R1 MAJOR: pass the NORMALIZED question (not the
        # raw one) so downstream rewriter, BM25, vector search, and
        # synthesis prompt share a single canonical form; the prior code
        # silently undid item 12's whitespace-collapse on the rewrite path.
        effective_question = rewrite_query(normalized_question, conversation_context)
        # I3 (Phase 4.5 R4 HIGH): reject rewrites with LLM prefix leaks.
        # Scan-tier models sometimes emit "Sure! Here's the rewrite: …" or
        # "The standalone question is: …" — these pollute downstream BM25,
        # vector, and synthesis prompts. If detected, fall back to the
        # original question so search quality doesn't silently degrade.
        leaked = False
        if effective_question != normalized_question:
            # PR review round 1 (Opus MINOR I3 + Codex M-NEW-1): only treat
            # embedded newlines and known LLM-scaffolding keywords as leaks.
            # The prior generic `^[A-Z][a-zA-Z ]{0,40}:\s*` rejected legit
            # domain-prefixed rewrites like "RAG: methodology and evaluation".
            if "\n" in effective_question:
                leaked = True
            elif _LEAK_KEYWORD_RE.match(effective_question):
                leaked = True
        if leaked:
            logger.warning(
                "rewrite_query output rejected as prefix-leak; reverting to normalized: %r",
                effective_question[:200],
            )
            effective_question = normalized_question

    # Cycle 3 H11 (PR review R1 Codex MAJOR): derive search_mode from actual
    # vector-search runtime behaviour, not just "index file exists + module
    # importable". The prior definition reported "hybrid" even when dim
    # mismatch or sqlite-vec extension load failure caused
    # `VectorIndex.query` to return [] for every call, defeating the
    # observability contract. Thread a telemetry dict through `search_pages`;
    # vector_search records attempts / hits / failures, and we classify:
    #   - hybrid   → vector_search produced >=1 hit
    #   - bm25_only → vector_search either never ran (disabled / absent) or
    #                 attempted but all calls failed / returned 0
    search_telemetry: dict = {}
    matching_pages = search_pages(
        effective_question,
        wiki_dir,
        max_results=max_results,
        search_telemetry=search_telemetry,
    )

    # The static pre-check (import ok AND vec_path exists) is still a useful
    # filter: without it we'd always report "bm25_only" for the no-vector-
    # config case. If the static gate is False we stay BM25-only regardless
    # of telemetry. If True, we require telemetry to prove vector hits.
    try:
        from kb.query import embeddings as _embeddings

        _vec_path = Path(PROJECT_ROOT) / VECTOR_INDEX_PATH_SUFFIX
        _hybrid_configured = _embeddings._hybrid_available and _vec_path.exists()
    except Exception:
        _hybrid_configured = False

    if not _hybrid_configured:
        search_mode = "bm25_only"
    elif search_telemetry.get("vector_hits", 0) > 0:
        search_mode = "hybrid"
    else:
        # Hybrid was configured but vector_search contributed no results
        # (dim mismatch, extension load fail, or a legitimate empty index).
        # Surface as bm25_only so observers can distinguish from the
        # success case — the H11 observability contract.
        search_mode = "bm25_only"

    if not matching_pages:
        return {
            "question": question,
            "answer": "No relevant pages found in the knowledge base for this question.",
            "citations": [],
            "source_pages": [],
            "context_pages": [],
            "stale_citations": [],
            "search_mode": search_mode,
        }

    # 2. Build context from matching pages
    ctx = _build_query_context(matching_pages)
    context = ctx["context"]

    # Raw-source fallback: supplement thin wiki context with verbatim raw source content.
    # Cycle 3 H15: trigger on SEMANTIC signal, not post-truncation char count.
    # Old gate (`len(context) < QUERY_CONTEXT_MAX_CHARS // 2`) fired for a
    # perfectly good 39K context AND for "No relevant wiki pages found." (35
    # chars) — doubling per-query disk I/O and BM25 rebuild. New gate: fire
    # ONLY when (a) no pages made it into context, or (b) every context page
    # is a summary (summaries lose detail — raw verbatim has value).
    ctx_ids = ctx.get("context_pages", [])
    context_types = {p.get("type") for p in matching_pages if p["id"] in ctx_ids}
    raw_fallback_needed = (not ctx_ids) or context_types == {"summary"}

    raw_context = ""
    if raw_fallback_needed:
        raw_results = search_raw_sources(
            effective_question, raw_dir=effective_raw_dir, max_results=3
        )
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
    if purpose:
        wrapped = wrap_purpose(purpose)
        purpose_section = f"\nKB FOCUS (bias answers toward these goals):\n{wrapped}\n"
    else:
        purpose_section = ""

    prompt = f"""You are answering a question using a knowledge wiki as your source.
{purpose_section}
QUESTION: {effective_question[:2000].replace(chr(10), " ").replace(chr(13), " ")}

WIKI CONTEXT:
{context}

INSTRUCTIONS:
- Answer the question based ONLY on the wiki context provided.
- Cite your sources using [[page_id]] format (e.g., [[concepts/rag]]).
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

    # Cycle 3 H9: derive stale_citations from the intersection of
    # context_pages (actually included in the LLM prompt) and matching_pages
    # whose stale flag is True. We deliberately do NOT use `citations`
    # (LLM-extracted) because those may reference pages outside context.
    ctx_ids_set = set(ctx["context_pages"])
    stale_citations = [p["id"] for p in matching_pages if p["id"] in ctx_ids_set and p.get("stale")]

    result_dict = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_pages": [p["id"] for p in matching_pages],
        "context_pages": ctx["context_pages"],
        "stale_citations": stale_citations,
        "search_mode": search_mode,
    }

    # 5. Optional output adapter (Phase 4.11)
    if output_format and output_format.strip().lower() != "text":
        from kb.query.formats import render_output

        try:
            path = render_output(output_format, result_dict)
            if path is not None:
                result_dict["output_path"] = str(path)
                result_dict["output_format"] = output_format.strip().lower()
        except ValueError as e:
            # ValueError comes from our own validation — safe to surface verbatim
            logger.warning("Output format '%s' failed: %s", output_format, e)
            result_dict["output_error"] = str(e)
        except Exception as e:  # noqa: BLE001
            # Catch-all for adapter failures (OSError on disk, ImportError for
            # optional deps like nbformat, nbformat.ValidationError, etc.) —
            # the synthesized answer is still valid, so surface a scrubbed
            # error message instead of letting the exception abort query_wiki.
            logger.warning("Output format '%s' %s: %s", output_format, type(e).__name__, e)
            result_dict["output_error"] = (
                f"write failed ({type(e).__name__}); see server logs for details"
            )

    return result_dict
