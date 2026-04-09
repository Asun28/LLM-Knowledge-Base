"""Project configuration — paths, model tiers, and settings."""

import os
from pathlib import Path

# ── Project paths ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "raw"
WIKI_DIR = PROJECT_ROOT / "wiki"
RESEARCH_DIR = PROJECT_ROOT / "research"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

# ── Wiki index files ──────────────────────────────────────────
WIKI_INDEX = WIKI_DIR / "index.md"
WIKI_SOURCES = WIKI_DIR / "_sources.md"
WIKI_CATEGORIES = WIKI_DIR / "_categories.md"
WIKI_LOG = WIKI_DIR / "log.md"
WIKI_CONTRADICTIONS = WIKI_DIR / "contradictions.md"

# ── Wiki subdirectories ───────────────────────────────────────
WIKI_ENTITIES = WIKI_DIR / "entities"
WIKI_CONCEPTS = WIKI_DIR / "concepts"
WIKI_COMPARISONS = WIKI_DIR / "comparisons"
WIKI_SUMMARIES = WIKI_DIR / "summaries"
WIKI_SYNTHESIS = WIKI_DIR / "synthesis"

# ── Raw subdirectories ────────────────────────────────────────
RAW_ARTICLES = RAW_DIR / "articles"
RAW_PAPERS = RAW_DIR / "papers"
RAW_REPOS = RAW_DIR / "repos"
RAW_VIDEOS = RAW_DIR / "videos"
RAW_PODCASTS = RAW_DIR / "podcasts"
RAW_BOOKS = RAW_DIR / "books"
RAW_DATASETS = RAW_DIR / "datasets"
RAW_CONVERSATIONS = RAW_DIR / "conversations"
RAW_ASSETS = RAW_DIR / "assets"

# ── Source type → subdirectory mapping ────────────────────────
SOURCE_TYPE_DIRS: dict[str, Path] = {
    "article": RAW_ARTICLES,
    "paper": RAW_PAPERS,
    "repo": RAW_REPOS,
    "video": RAW_VIDEOS,
    "podcast": RAW_PODCASTS,
    "book": RAW_BOOKS,
    "dataset": RAW_DATASETS,
    "conversation": RAW_CONVERSATIONS,
}

# ── Model tiering (from tooling-research.md) ──────────────────
# Haiku for mechanical scanning, Sonnet for writing, Opus for orchestration
# Override via env vars: CLAUDE_SCAN_MODEL, CLAUDE_WRITE_MODEL, CLAUDE_ORCHESTRATE_MODEL
MODEL_TIERS = {
    "scan": os.environ.get("CLAUDE_SCAN_MODEL", "").strip() or "claude-haiku-4-5-20251001",
    "write": os.environ.get("CLAUDE_WRITE_MODEL", "").strip() or "claude-sonnet-4-6",
    "orchestrate": os.environ.get("CLAUDE_ORCHESTRATE_MODEL", "").strip() or "claude-opus-4-6",
}

# ── Page types ────────────────────────────────────────────────
PAGE_TYPES = ("entity", "concept", "comparison", "synthesis", "summary")
CONFIDENCE_LEVELS = ("stated", "inferred", "speculative")

# ── Phase 2: Quality system paths ────────────────────────────
FEEDBACK_PATH = PROJECT_ROOT / ".data" / "query_feedback.json"
REVIEW_HISTORY_PATH = PROJECT_ROOT / ".data" / "review_history.json"
VERDICTS_PATH = PROJECT_ROOT / ".data" / "lint_verdicts.json"

# ── LLM retry / timeout settings ─────────────────────────────
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 1.0  # seconds
LLM_RETRY_MAX_DELAY = 30.0  # seconds
LLM_REQUEST_TIMEOUT = 120.0  # seconds

# ── Phase 2: Quality thresholds ──────────────────────────────
LOW_TRUST_THRESHOLD = 0.4
MAX_CONSISTENCY_GROUP_SIZE = 5

# ── Lint tuning ──────────────────────────────────────────────
STALENESS_MAX_DAYS = 90

# ── Evolve / connection discovery tuning ─────────────────────
MIN_PAGES_FOR_TERM = 2
MAX_PAGES_FOR_TERM = 5
MIN_SHARED_TERMS = 3

# ── Query search weights ────────────────────────────────────
SEARCH_TITLE_WEIGHT = 3

# ── BM25 search parameters ─────────────────────────────────
BM25_K1 = 1.5  # Term frequency saturation (1.2-2.0 typical)
BM25_B = 0.75  # Document length normalization (0.0-1.0)

# ── PageRank search blending ──────────────────────────────────
# Weight for blending PageRank into BM25 scores.
# final_score = bm25_score * (1 + PAGERANK_SEARCH_WEIGHT * normalized_pagerank)
# Set to 0 to disable PageRank blending (pure BM25).
PAGERANK_SEARCH_WEIGHT = 0.5

# ── Query context limits ───────────────────────────────────
# Approximate character budget for query context sent to LLM.
# ~4 chars/token, 100k context window → conservative 80k char limit.
QUERY_CONTEXT_MAX_CHARS = 80_000

# ── Search result limits ──────────────────────────────────────
MAX_SEARCH_RESULTS = 100

# ── Ingest limits ────────────────────────────────────────────
MAX_ENTITIES_PER_INGEST = 50
MAX_CONCEPTS_PER_INGEST = 50

# ── Content-length ingest tiering ────────────────────────────
# Sources under this character count get simplified processing:
# summary page only, entity/concept pages deferred.
SMALL_SOURCE_THRESHOLD = 1000

# ── Data retention limits ──────────────────────────────────────
# Maximum entries retained in JSON stores before old entries are pruned.
MAX_FEEDBACK_ENTRIES = 10_000
MAX_VERDICTS = 10_000
MAX_REVIEW_HISTORY_ENTRIES = 10_000

# ── Feedback store input limits ────────────────────────────────
MAX_QUESTION_LEN = 2000
MAX_NOTES_LEN = 2000
MAX_PAGE_ID_LEN = 200
MAX_CITED_PAGES = 50

# ── Wiki subdir → page type mapping ───────────────────────────
WIKI_SUBDIR_TO_TYPE: dict[str, str] = {
    "entities": "entity",
    "concepts": "concept",
    "comparisons": "comparison",
    "summaries": "summary",
    "synthesis": "synthesis",
}

# ── Verdict trend analysis ────────────────────────────────────
# Threshold for classifying weekly trend direction as significant.
# Used by kb.lint.trends to determine "improving", "stable", or "declining".
VERDICT_TREND_THRESHOLD = 0.1
