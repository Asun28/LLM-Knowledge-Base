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
WIKI_LOG = WIKI_DIR / "log.md"
WIKI_CONTRADICTIONS = WIKI_DIR / "contradictions.md"
WIKI_PURPOSE = WIKI_DIR / "purpose.md"

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

# ── Raw subdirectories (contd.) ──────────────────────────────
CAPTURES_DIR = RAW_DIR / "captures"

# ── Query output adapters (Phase 4.11) ───────────────────────
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MAX_OUTPUT_CHARS = 500_000

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
    "capture": CAPTURES_DIR,
}

# ── Capture configuration (Phase 5 — kb_capture MCP tool) ───────
CAPTURE_MAX_BYTES = 50_000  # hard input size cap (UTF-8 bytes)
CAPTURE_MAX_ITEMS = 20  # cap items extracted per scan-tier call
CAPTURE_KINDS = ("decision", "discovery", "correction", "gotcha")
CAPTURE_MAX_CALLS_PER_HOUR = 60  # per-process rate limit (sliding 1h window)

# Cycle 2 item 13: per-file size cap for search_raw_sources. Files above this
# threshold are skipped before `read_text` to prevent a single 10 MB scraped
# article from ballooning the in-memory corpus and tokenizer.
RAW_SOURCE_MAX_BYTES = 2_097_152  # 2 MiB

# ── Supported source file extensions ─────────────────────────────────
# Single source of truth — imported by both compiler.py and mcp/core.py.
SUPPORTED_SOURCE_EXTENSIONS = frozenset(
    {".md", ".txt", ".pdf", ".json", ".yaml", ".yml", ".rst", ".csv"}
)

# J1 (Phase 4.5 MEDIUM): hard ceiling on rewriter output. Floor is
# max(3 * len(question), 120) — these two together accept legitimate
# short reference expansions while rejecting LLM rambles.
MAX_REWRITE_CHARS = 500

# ── Valid source types for extraction ────────────────────────────────
# Includes comparison/synthesis which have templates but no raw/ subdirectory.
VALID_SOURCE_TYPES = frozenset(list(SOURCE_TYPE_DIRS.keys()) + ["comparison", "synthesis"])

# ── Model tiering (from tooling-research.md) ──────────────────
# Haiku for mechanical scanning, Sonnet for writing, Opus for orchestration
# Override via env vars: CLAUDE_SCAN_MODEL, CLAUDE_WRITE_MODEL, CLAUDE_ORCHESTRATE_MODEL
# NOTE: Env vars are read once at import time. Process restart required for changes.
_DEFAULT_MODEL_TIERS: dict[str, str] = {
    "scan": "claude-haiku-4-5-20251001",
    "write": "claude-sonnet-4-6",
    "orchestrate": "claude-opus-4-6",
}


def get_model_tier(tier: str) -> str:
    """Return the model ID for ``tier`` with fresh env lookup.

    Cycle 7 AC24: previously ``MODEL_TIERS`` captured ``os.environ`` at import
    time, so tests mutating ``CLAUDE_*_MODEL`` mid-run saw stale values (first
    test to hit ``kb.config`` pinned the tier table). This helper re-reads env
    on every call so CLI overrides, test fixtures, and long-lived processes
    observe the current environment.

    Args:
        tier: One of ``"scan"``, ``"write"``, ``"orchestrate"``.

    Raises:
        ValueError: if ``tier`` is not a known tier name.
    """
    if tier not in _DEFAULT_MODEL_TIERS:
        raise ValueError(f"invalid tier: {tier!r}; valid={tuple(_DEFAULT_MODEL_TIERS)}")
    env_key = f"CLAUDE_{tier.upper()}_MODEL"
    return os.environ.get(env_key, "").strip() or _DEFAULT_MODEL_TIERS[tier]


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
MAX_CONSISTENCY_GROUPS = 20
MAX_CONSISTENCY_PAGE_CONTENT_CHARS = 4096

# ── Lint tuning ──────────────────────────────────────────────
STALENESS_MAX_DAYS = 90
UNDER_COVERED_TYPE_THRESHOLD = 3
STUB_MIN_CONTENT_CHARS = 100

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

# Maximum tokens for the LLM answer synthesis response.
QUERY_MAX_TOKENS = 2048

# ── Search result limits ──────────────────────────────────────
MAX_SEARCH_RESULTS = 100

# ── RRF hybrid search ─────────────────────────────────────────
RRF_K = 60  # RRF fusion constant: score = 1/(K + rank)
VECTOR_SEARCH_LIMIT_MULTIPLIER = 2  # Vector search fetches limit * N candidates
BM25_SEARCH_LIMIT_MULTIPLIER = 1  # BM25 candidates = limit * this (intentionally 1×)
# Cycle 10 AC7 — vector hit must reach this similarity (after
# 1/(1+distance) conversion in engine.vector_search) to contribute to
# RRF fusion. Below this, the vector backend is treated as silent for
# that query (prevents noise-query false positives when only vector
# returns hits).
VECTOR_MIN_SIMILARITY = 0.3
# Cycle 3 L6: hoisted from hardcoded `[:3]` in query/hybrid.py so operators can
# tune expansion breadth without touching code. Total queries sent to vector
# search = 1 (original) + MAX_QUERY_EXPANSIONS. A value of 2 matches the pre-
# cycle-3 behaviour; raising trades latency for recall.
MAX_QUERY_EXPANSIONS = 2
EMBEDDING_MODEL = "minishlab/potion-base-8M"  # model2vec model (~8MB, local)
VECTOR_INDEX_PATH_SUFFIX = ".data/vector_index.db"  # sqlite-vec index file

# ── Search dedup parameters ─────────────────────────────────
DEDUP_JACCARD_THRESHOLD = 0.85  # Text similarity threshold for dedup layer 2
DEDUP_MAX_TYPE_RATIO = 0.6  # Max fraction of results from one page type
DEDUP_MAX_PER_PAGE = 2  # Max results per page in final output

# ── Layered context assembly ────────────────────────────────
CONTEXT_TIER1_BUDGET = 20_000  # Chars for summaries tier
CONTEXT_TIER2_BUDGET = 60_000  # Additional chars for full pages on demand

# ── Contradiction detection ──────────────────────────────────
CONTRADICTION_MAX_CLAIMS_TO_CHECK = 10  # Max existing claims to compare per ingest

# ── Multi-turn query rewriting ───────────────────────────────
MAX_CONVERSATION_CONTEXT_CHARS = 4000  # Max chars of conversation history for rewriting

# ── Ingest limits ────────────────────────────────────────────
MAX_ENTITIES_PER_INGEST = 50
MAX_CONCEPTS_PER_INGEST = 50
MAX_INGEST_CONTENT_CHARS = 160_000

# ── Content-length ingest tiering ────────────────────────────
# Sources under this character count get simplified processing:
# summary page only, entity/concept pages deferred.
SMALL_SOURCE_THRESHOLD = 1000

# ── Data retention limits ──────────────────────────────────────
# Maximum entries retained in JSON stores before old entries are pruned.
MAX_FEEDBACK_ENTRIES = 10_000
MAX_VERDICTS = 10_000
MAX_REVIEW_HISTORY_ENTRIES = 10_000
MAX_PAGE_SCORES = 10_000

# ── Feedback store input limits ────────────────────────────────
MAX_QUESTION_LEN = 2000
MAX_NOTES_LEN = 2000
VALID_SEVERITIES = ("error", "warning", "info")
VALID_VERDICT_TYPES: tuple[str, ...] = (
    "fidelity",
    "consistency",
    "completeness",
    "review",
    "augment",
)
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

# Autogen wiki page prefixes — pages under these subdirs are auto-generated entry points,
# not stubs to enrich. Used by lint orphan/isolated/stub checks and kb_lint --augment eligibility.
AUTOGEN_PREFIXES: tuple[str, ...] = ("summaries/", "comparisons/", "synthesis/")

# === Augment (kb_lint --augment) ===
# Reactive gap-fill: lint detects a stub → fetch web content → ingest as raw source.
# See docs/superpowers/specs/2026-04-15-kb-lint-augment-design.md.

AUGMENT_FETCH_MAX_BYTES = 5_000_000
AUGMENT_FETCH_CONNECT_TIMEOUT = 5.0
AUGMENT_FETCH_READ_TIMEOUT = 30.0
AUGMENT_FETCH_MAX_REDIRECTS = 10
AUGMENT_FETCH_MAX_CALLS_PER_RUN = 10  # hard ceiling; runtime max_gaps must be ≤ this
AUGMENT_FETCH_MAX_CALLS_PER_HOUR = 60  # global cross-process
AUGMENT_FETCH_MAX_CALLS_PER_HOST_PER_HOUR = 3
AUGMENT_COOLDOWN_HOURS = 24
AUGMENT_RELEVANCE_THRESHOLD = 0.5
AUGMENT_WIKIPEDIA_FUZZY_THRESHOLD = 0.7

AUGMENT_ALLOWED_DOMAINS: tuple[str, ...] = tuple(
    d.strip()
    for d in os.getenv("AUGMENT_ALLOWED_DOMAINS", "en.wikipedia.org,arxiv.org").split(",")
    if d.strip()
)
AUGMENT_CONTENT_TYPES: tuple[str, ...] = (
    "text/html",
    "text/markdown",
    "text/plain",
    "application/pdf",
    "application/json",
    "application/xml",
)

# ── Verdict trend analysis ────────────────────────────────────
# Threshold for classifying weekly trend direction as significant.
# Used by kb.lint.trends to determine "improving", "stable", or "declining".
VERDICT_TREND_THRESHOLD = 0.1
