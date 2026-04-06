"""Query engine — search wiki, synthesize answers with citations."""

import logging
from pathlib import Path

import frontmatter

from kb.config import SEARCH_CONTENT_WEIGHT, SEARCH_TITLE_WEIGHT, WIKI_DIR
from kb.query.citations import extract_citations
from kb.utils.llm import call_llm

logger = logging.getLogger(__name__)


def _load_wiki_pages(wiki_dir: Path | None = None) -> list[dict]:
    """Load all wiki pages with their metadata and content.

    Returns:
        List of dicts with keys: path, id, title, type, confidence, content, raw_content.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    pages = []
    for subdir in ("entities", "concepts", "comparisons", "summaries", "synthesis"):
        subdir_path = wiki_dir / subdir
        if not subdir_path.exists():
            continue
        for page_path in sorted(subdir_path.glob("*.md")):
            try:
                post = frontmatter.load(str(page_path))
                page_id = (
                    str(page_path.relative_to(wiki_dir)).replace("\\", "/").removesuffix(".md")
                )
                pages.append(
                    {
                        "path": str(page_path),
                        "id": page_id,
                        "title": post.metadata.get("title", page_path.stem),
                        "type": post.metadata.get("type", "unknown"),
                        "confidence": post.metadata.get("confidence", "unknown"),
                        "content": post.content,
                        "raw_content": post.content.lower(),
                    }
                )
            except Exception as e:
                logger.warning("Failed to load wiki page %s: %s", page_path, e)
                continue
    return pages


def search_pages(question: str, wiki_dir: Path | None = None, max_results: int = 10) -> list[dict]:
    """Search wiki pages by keyword matching.

    Simple keyword-based search: splits the question into words and scores pages
    by how many question words appear in their content.

    Args:
        question: The search query.
        wiki_dir: Path to wiki directory.
        max_results: Maximum number of results to return.

    Returns:
        List of matching page dicts sorted by relevance score (descending).
    """
    pages = _load_wiki_pages(wiki_dir)
    if not pages:
        return []

    # Tokenize question into search terms
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "not",
        "with",
        "by",
        "from",
        "what",
        "how",
        "why",
        "when",
        "where",
        "which",
        "who",
        "does",
        "do",
        "can",
        "will",
        "should",
        "would",
        "it",
    }
    terms = [
        w.lower().strip("?.,!")
        for w in question.split()
        if w.lower().strip("?.,!") not in stop_words
    ]

    if not terms:
        # All words were stopwords — use the full question as a substring match
        # instead of individual common words that would match everything
        terms = [question.lower().strip("?.,!")]

    scored = []
    for page in pages:
        score = 0
        content_lower = page["raw_content"]
        title_lower = page["title"].lower()
        for term in terms:
            if term in title_lower:
                score += SEARCH_TITLE_WEIGHT
            if term in content_lower:
                score += SEARCH_CONTENT_WEIGHT
        if score > 0:
            page["score"] = score
            scored.append(page)

    scored.sort(key=lambda p: p["score"], reverse=True)
    return scored[:max_results]


def _build_query_context(pages: list[dict]) -> str:
    """Build context string from matching wiki pages for the LLM."""
    if not pages:
        return "No relevant wiki pages found."
    sections = []
    for page in pages:
        sections.append(
            f"--- Page: {page['id']} (type: {page['type']}, confidence: {page['confidence']}) ---\n"
            f"Title: {page['title']}\n\n{page['content']}\n"
        )
    return "\n".join(sections)


def query_wiki(question: str, wiki_dir: Path | None = None) -> dict:
    """Query the knowledge base and synthesize an answer.

    Args:
        question: The user's question.
        wiki_dir: Path to wiki directory (uses config default if None).

    Returns:
        dict with keys: question, answer, citations, source_pages.
    """
    # 1. Search for relevant pages
    matching_pages = search_pages(question, wiki_dir)

    if not matching_pages:
        return {
            "question": question,
            "answer": "No relevant pages found in the knowledge base for this question.",
            "citations": [],
            "source_pages": [],
        }

    # 2. Build context from matching pages
    context = _build_query_context(matching_pages)

    # 3. Synthesize answer with LLM
    prompt = f"""You are answering a question using a knowledge wiki as your source.

QUESTION: {question}

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
        max_tokens=2048,
    )

    # 4. Extract citations from the answer
    citations = extract_citations(answer)

    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "source_pages": [p["id"] for p in matching_pages],
    }
