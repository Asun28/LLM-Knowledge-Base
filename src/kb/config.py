"""Project configuration — paths, model tiers, and settings."""

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
MODEL_TIERS = {
    "scan": "claude-haiku-4-5-20251001",
    "write": "claude-sonnet-4-6",
    "orchestrate": "claude-opus-4-6",
}

# ── Page types ────────────────────────────────────────────────
PAGE_TYPES = ("entity", "concept", "comparison", "synthesis", "summary")
CONFIDENCE_LEVELS = ("stated", "inferred", "speculative")

# ── Phase 2: Quality system paths ────────────────────────────
FEEDBACK_PATH = PROJECT_ROOT / ".data" / "query_feedback.json"
REVIEW_MANIFEST_PATH = PROJECT_ROOT / ".data" / "review_manifest.json"
REVIEW_HISTORY_PATH = PROJECT_ROOT / ".data" / "review_history.json"

# ── Phase 2: Quality thresholds ──────────────────────────────
LOW_TRUST_THRESHOLD = 0.4
SELF_REFINE_MAX_ROUNDS = 2
LINT_MAX_ROUNDS = 3
MAX_CONSISTENCY_GROUP_SIZE = 5
