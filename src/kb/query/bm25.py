"""BM25 ranking algorithm for wiki page search.

Replaces naive bag-of-words keyword matching with BM25 (Best Matching 25),
which accounts for term frequency saturation, inverse document frequency,
and document length normalization.

This is NOT RAG — the wiki pages are pre-compiled from sources, not raw
chunks retrieved at query time. BM25 just improves how we find the most
relevant compiled pages for a given question.
"""

import logging
import math
import re
from collections import Counter

logger = logging.getLogger(__name__)

# Words that appear in most documents and carry no discriminative signal
STOP_WORDS = frozenset(
    {
        "a",
        "about",
        "after",
        "all",
        "also",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "each",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "may",
        "more",
        "most",
        "new",
        "not",
        "of",
        "on",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words for BM25 indexing.

    Extracts alphanumeric tokens of length >= 2, filters stopwords.
    Keeps hyphens within words (e.g., 'fine-tuning' stays as one token).
    """
    # Match words: letters/digits/hyphens, at least 2 chars
    words = re.findall(r"\b[\w][\w-]*[\w]\b|\b\w{2,}\b", text.lower())
    return [w for w in words if w not in STOP_WORDS]


class BM25Index:
    """BM25 ranking index for a collection of tokenized documents.

    Standard BM25 formula:
        score(D, Q) = Σ IDF(qi) * tf(qi,D)*(k1+1) / (tf(qi,D) + k1*(1-b+b*|D|/avgdl))

    Where:
        tf(qi, D) = term frequency of qi in document D
        |D| = document length (in tokens)
        avgdl = average document length across corpus
        k1 = term frequency saturation parameter
        b = document length normalization parameter
        IDF(qi) = log((N - n(qi) + 0.5) / (n(qi) + 0.5) + 1)
    """

    def __init__(self, documents: list[list[str]]) -> None:
        """Build index from pre-tokenized documents.

        Args:
            documents: List of token lists (one per document).
        """
        self.n_docs = len(documents)
        self.doc_freqs: list[Counter[str]] = []
        self.doc_lengths: list[int] = []
        self.df: Counter[str] = Counter()

        for tokens in documents:
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            self.doc_lengths.append(len(tokens))
            for term in freq:
                self.df[term] += 1

        self.avgdl = sum(self.doc_lengths) / self.n_docs if self.n_docs > 0 else 1.0
        if self.avgdl == 0:
            self.avgdl = 1.0
            logger.warning(
                "BM25 corpus has zero average document length — using fallback avgdl=1.0"
            )

        # Pre-compute IDF for each term
        self.idf: dict[str, float] = {}
        for term, df in self.df.items():
            self.idf[term] = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
        """Score all documents against query tokens.

        Args:
            query_tokens: Tokenized query.
            k1: Term frequency saturation (1.2-2.0 typical). Higher = more weight to TF.
            b: Length normalization (0.0-1.0). Higher = more penalty for long docs.

        Returns:
            List of scores, one per document (same order as construction).
        """
        scores = [0.0] * self.n_docs

        for term in dict.fromkeys(query_tokens):
            if term not in self.idf:
                continue
            idf = self.idf[term]

            for i, doc_freq in enumerate(self.doc_freqs):
                tf = doc_freq.get(term, 0)
                if tf == 0:
                    continue
                dl = self.doc_lengths[i]
                denom = tf + k1 * (1.0 - b + b * dl / self.avgdl)
                scores[i] += idf * (tf * (k1 + 1.0)) / denom

        return scores
