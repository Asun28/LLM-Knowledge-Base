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
import time
from collections import Counter

from kb.utils.text import STOPWORDS as STOP_WORDS

logger = logging.getLogger(__name__)

# Cycle 28 AC5 — process-level observability counter for BM25 index builds.
# Lock-free per design Q2 (matches cycle-25 `_dim_mismatches_seen` pattern):
# `BM25Index.__init__` is called from outside any cache lock (`engine.py:110`
# wiki-side + `engine.py:794` raw-side both release the cache lock before
# constructing), and the counter is intended as operator diagnostic telemetry,
# NOT billing-grade. Approximate counts are adequate; a concurrent pair of
# cache-miss rebuilds may under-count by 1 under the non-atomic `+= 1` race.
# Python `int` has no overflow (threat-model T7). Contrast cycle-26 AC4
# `_vector_model_cold_loads_seen` which IS locked — different rate profile.
_bm25_builds_seen: int = 0


def get_bm25_build_count() -> int:
    """Return the process-level count of `BM25Index.__init__` executions.

    Cycle 28 AC5 — module-level observability counter. Semantics pinned
    by Q11: "constructor executions, NOT distinct cache insertions".
    Aggregates both call sites: `engine.py:110` (wiki-page BM25 cache
    rebuilds) and `engine.py:794` (raw-source BM25 cache rebuilds). Under
    concurrent cache-misses two threads may both build and both increment,
    so the counter is approximate.

    Lock-free per cycle-25 Q8 design precedent: operator-diagnostic use
    tolerates undercount by ≤N under N concurrent rebuilds. Contrast
    cycle-26 `get_vector_model_cold_load_count()` which IS locked via
    `_model_lock` because cold-loads happen at most once per process.

    The counter is READ-only: no reset helper. Tests observe monotonic
    deltas via baseline-snapshot pattern (reload-safe per cycle-20 L1 /
    threat-model T8). Python `int` is arbitrary-precision — no overflow risk.
    """
    return _bm25_builds_seen


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words for BM25 indexing.

    Extracts alphanumeric tokens of length >= 2, filters stopwords.
    Applies the STOPWORDS filter (see kb.utils.text.STOPWORDS) — tokens
    like 'what', 'is', 'the' are dropped, so a query like 'what is rag'
    reduces to ['rag'] before scoring.
    Keeps hyphens within words (e.g., 'fine-tuning' stays as one token).

    Note: Version strings like 'v0.9.13' fragment across dots — the dot
    is not a word character, so '0', '9', '13' become separate tokens
    and single-digit components are dropped by the length filter.
    """
    text = text.lower()
    # Normalize consecutive hyphens (e.g., "pre--compiled" → "pre-compiled")
    text = re.sub(r"-{2,}", "-", text)
    # Match words: letters/digits/hyphens, at least 2 chars
    # Single pattern: \b\w[\w-]*\w\b covers multi-char tokens with optional hyphens
    words = re.findall(r"\b\w[\w-]*\w\b", text)
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

        Cycle 4 item #24 — also builds a postings dict (``_postings``) mapping
        each term to the list of doc indices where it appears, so ``score``
        can skip non-matching docs instead of walking every doc per term.
        At ~5K pages with hundreds of unique terms the memory cost is ~150 MB;
        the scoring speedup for sparse queries outweighs the cost.

        Cycle 28 AC4 — instrumented with ``time.perf_counter`` around the FULL
        constructor body (corpus loop + avgdl + IDF pre-computation per
        design CONDITION 2). Emits one INFO log per call. Counter increments
        and log emission sit at the end of the method body (post-success
        ordering — no `finally:` wraps them).

        Args:
            documents: List of token lists (one per document).
        """
        self.n_docs = len(documents)
        # Cycle 28 AC4 — bracket starts AFTER `self.n_docs` assignment so the
        # log can reference `n_docs` even for the empty-corpus edge case.
        start = time.perf_counter()
        self.doc_freqs: list[Counter[str]] = []
        self.doc_lengths: list[int] = []
        self.df: Counter[str] = Counter()
        # Cycle 4 item #24: inverted postings for sparse-query scoring.
        self._postings: dict[str, list[int]] = {}

        for i, tokens in enumerate(documents):
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            self.doc_lengths.append(len(tokens))
            for term in freq:
                self.df[term] += 1
                self._postings.setdefault(term, []).append(i)

        self.avgdl = sum(self.doc_lengths) / self.n_docs if self.n_docs > 0 else 1.0
        if self.avgdl == 0:
            self.avgdl = 1.0
            logger.debug("BM25 corpus has zero average document length — using fallback avgdl=1.0")

        # Pre-compute IDF for each term
        self.idf: dict[str, float] = {}
        for term, df in self.df.items():
            self.idf[term] = math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1.0)

        # Cycle 28 AC4/AC5 — post-success instrumentation (design CONDITION 2 + C9).
        # Log + counter fire AT THE END of the method body, NOT in a `finally:`.
        # Even empty-corpus case (`n_docs=0`) emits the INFO line (Q10 empty-
        # corpus coverage + R2 finding 6).
        elapsed = time.perf_counter() - start
        global _bm25_builds_seen
        _bm25_builds_seen += 1
        logger.info("BM25 index built in %.3fs (n_docs=%d)", elapsed, self.n_docs)

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

        # Cycle 4 item #24 — iterate only docs that contain the term, via the
        # postings dict. At 5K pages the prior O(N) walk per query term was
        # the hot path; sparse queries ("rag fine-tuning") would visit
        # all 5K docs twice. Using postings cuts to the matching subset.
        for term in dict.fromkeys(query_tokens):
            if term not in self.idf:
                continue
            idf = self.idf[term]
            for i in self._postings.get(term, ()):
                tf = self.doc_freqs[i].get(term, 0)
                if tf == 0:
                    continue
                dl = self.doc_lengths[i]
                denom = tf + k1 * (1.0 - b + b * dl / self.avgdl)
                scores[i] += idf * (tf * (k1 + 1.0)) / denom

        return scores
