"""Tests for BM25 search implementation — tokenizer, index, and search integration."""

from kb.query.bm25 import BM25Index, tokenize
from kb.query.engine import search_pages

# ── 1. Tokenizer tests ───────────────────────────────────────────


def test_tokenize_basic():
    """tokenize lowercases and splits into words."""
    assert tokenize("Hello World") == ["hello", "world"]


def test_tokenize_removes_stopwords():
    """tokenize filters common stopwords."""
    result = tokenize("the quick brown fox")
    assert "the" not in result
    assert "quick" in result
    assert "brown" in result
    assert "fox" in result


def test_tokenize_keeps_hyphenated():
    """tokenize preserves hyphens within words like 'fine-tuning'."""
    result = tokenize("fine-tuning is great")
    assert "fine-tuning" in result
    assert "great" in result
    # "is" is a stopword
    assert "is" not in result


def test_tokenize_empty():
    """tokenize returns empty list for empty string."""
    assert tokenize("") == []


def test_tokenize_all_stopwords():
    """tokenize returns empty list when all words are stopwords."""
    assert tokenize("the a an is are") == []


# ── 2. BM25Index tests ───────────────────────────────────────────


def test_bm25_basic_ranking():
    """Query matching one doc scores it higher than a non-matching doc."""
    docs = [
        tokenize("retrieval augmented generation for language models"),
        tokenize("supervised fine-tuning of neural networks"),
    ]
    index = BM25Index(docs)
    scores = index.score(tokenize("retrieval augmented generation"))
    assert scores[0] > scores[1]
    assert scores[0] > 0
    assert scores[1] == 0.0


def test_bm25_idf_effect():
    """A term appearing in fewer docs has higher IDF and boosts score more."""
    # "model" appears in both docs; "retrieval" only in doc 0
    docs = [
        tokenize("retrieval model for search"),
        tokenize("language model for generation"),
    ]
    index = BM25Index(docs)
    # "retrieval" is rare (1 doc), so doc 0 should score higher for it
    scores_rare = index.score(["retrieval"])
    scores_common = index.score(["model"])
    # The rare term ("retrieval") should give a higher score to doc 0
    # than the common term ("model") gives to either doc
    assert scores_rare[0] > scores_common[0]


def test_bm25_tf_saturation():
    """BM25 saturates term frequency — 10x occurrences does NOT yield 10x score."""
    # Doc 0: "transformer" appears once; Doc 1: "transformer" appears 10 times
    doc_single = ["transformer", "model"]
    doc_repeated = ["transformer"] * 10 + ["model"]
    index = BM25Index([doc_single, doc_repeated])
    scores = index.score(["transformer"])
    # Doc 1 should score higher (more occurrences) but NOT 10x higher
    assert scores[1] > scores[0]
    ratio = scores[1] / scores[0]
    assert ratio < 10.0, f"TF saturation failed: ratio was {ratio}"


def test_bm25_length_normalization():
    """Shorter doc with same term gets higher score than longer doc (when b > 0)."""
    short_doc = ["transformer", "attention"]
    long_doc = ["transformer", "attention"] + ["padding"] * 50
    index = BM25Index([short_doc, long_doc])
    scores = index.score(["transformer"], b=0.75)
    # Short doc should score higher due to length normalization
    assert scores[0] > scores[1]


def test_bm25_empty_index():
    """BM25Index handles empty corpus without errors."""
    index = BM25Index([])
    scores = index.score(["anything"])
    assert scores == []


def test_bm25_no_match():
    """Query terms not in any document yield all-zero scores."""
    docs = [
        tokenize("retrieval augmented generation"),
        tokenize("fine-tuning language models"),
    ]
    index = BM25Index(docs)
    scores = index.score(["quantum", "computing"])
    assert all(s == 0.0 for s in scores)


# ── 3. Search integration tests ──────────────────────────────────


def test_search_bm25_basic(tmp_wiki, create_wiki_page):
    """Search finds the page containing the query term and ranks it first."""
    create_wiki_page(
        "concepts/transformers",
        title="Transformers",
        content="Transformers use self-attention mechanisms for sequence modeling.",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/cnn",
        title="Convolutional Neural Networks",
        content="CNNs are used for image classification and object detection.",
        wiki_dir=tmp_wiki,
    )
    results = search_pages("transformers attention", tmp_wiki)
    assert len(results) >= 1
    assert results[0]["id"] == "concepts/transformers"


def test_search_bm25_title_boost(tmp_wiki, create_wiki_page):
    """Page with query term in title ranks above page with term only in content."""
    create_wiki_page(
        "concepts/embeddings",
        title="Embeddings",
        content="Vector representations of words used in language models.",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "summaries/article-overview",
        title="Overview of Deep Learning",
        content="This article discusses embeddings and their applications.",
        page_type="summary",
        wiki_dir=tmp_wiki,
    )
    results = search_pages("embeddings", tmp_wiki)
    assert len(results) >= 1
    # Title match should rank higher due to SEARCH_TITLE_WEIGHT boost
    assert results[0]["id"] == "concepts/embeddings"


def test_search_bm25_relevance_ranking(tmp_wiki, create_wiki_page):
    """Correct topic ranks first when searching among three different topics."""
    create_wiki_page(
        "concepts/rag",
        title="Retrieval Augmented Generation",
        content="RAG combines retrieval with generation for better LLM answers.",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/fine-tuning",
        title="Fine Tuning",
        content="Fine-tuning adapts a pre-trained model to specific tasks.",
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/pruning",
        title="Model Pruning",
        content="Pruning removes unnecessary weights from neural networks.",
        wiki_dir=tmp_wiki,
    )
    results = search_pages("retrieval augmented generation", tmp_wiki)
    assert len(results) >= 1
    assert results[0]["id"] == "concepts/rag"


def test_search_bm25_returns_float_scores(tmp_wiki, create_wiki_page):
    """BM25 search scores are floats, not integers."""
    create_wiki_page(
        "concepts/attention",
        title="Attention Mechanism",
        content="Attention allows models to focus on relevant parts of the input.",
        wiki_dir=tmp_wiki,
    )
    results = search_pages("attention mechanism", tmp_wiki)
    assert len(results) >= 1
    for result in results:
        assert isinstance(result["score"], float)


def test_search_bm25_stopword_fallback(tmp_wiki, create_wiki_page):
    """Query with all stopwords still works via raw-token fallback."""
    create_wiki_page(
        "concepts/is-a-relationship",
        title="Is A Relationship",
        content="The is-a relationship defines type hierarchies in ontologies.",
        wiki_dir=tmp_wiki,
    )
    # "the" and "is" are stopwords, but fallback should use raw lowercased tokens
    results = search_pages("the is", tmp_wiki)
    # Should not crash; may or may not find results depending on fallback matching
    assert isinstance(results, list)


# ── 4. BM25 vs old search quality tests ──────────────────────────


def test_bm25_synonym_proximity():
    """A page about 'retrieval augmented generation' ranks for 'RAG retrieval'."""
    docs = [
        tokenize("retrieval augmented generation combines search with language models"),
        tokenize("convolutional neural networks for image processing"),
        tokenize("recurrent neural networks for sequence modeling"),
    ]
    index = BM25Index(docs)
    scores = index.score(tokenize("RAG retrieval"))
    # "retrieval" is a shared term — doc 0 should rank highest
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]
    assert scores[0] > 0


def test_bm25_multi_term_ranking(tmp_wiki, create_wiki_page):
    """Page matching multiple query terms ranks above page matching just one."""
    create_wiki_page(
        "concepts/vector-search",
        title="Vector Search",
        content=(
            "Vector search uses embeddings and approximate nearest neighbor "
            "algorithms for semantic retrieval of documents."
        ),
        wiki_dir=tmp_wiki,
    )
    create_wiki_page(
        "concepts/keyword-search",
        title="Keyword Search",
        content="Keyword search matches exact terms in documents using inverted indices.",
        wiki_dir=tmp_wiki,
    )
    # "vector search embeddings" — concepts/vector-search matches all 3 terms,
    # concepts/keyword-search matches only "search"
    results = search_pages("vector search embeddings", tmp_wiki)
    assert len(results) >= 2
    assert results[0]["id"] == "concepts/vector-search"


def test_bm25_empty_docs_no_division_by_zero():
    """BM25 should handle all-empty documents without division by zero."""
    index = BM25Index([[], [], []])
    scores = index.score(["test"])
    assert len(scores) == 3
    assert all(s == 0.0 for s in scores)
