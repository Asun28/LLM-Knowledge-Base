"""Project configuration — paths, model tiers, and settings."""

import logging
import math
import os
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

# ── Project paths ──────────────────────────────────────────────
_LOG = logging.getLogger(__name__)


def _resolve_project_root() -> Path:
    heuristic = Path(__file__).resolve().parent.parent.parent
    env_root = os.environ.get("KB_PROJECT_ROOT")
    if env_root:
        try:
            candidate = Path(env_root).resolve()
            if candidate.is_dir():
                return candidate
            reason = "resolved path is not a directory"
        except (OSError, RuntimeError) as exc:
            reason = f"could not resolve path: {exc}"
        _LOG.warning("Invalid KB_PROJECT_ROOT=%s: %s; using %s", env_root, reason, heuristic)
        return heuristic

    if (heuristic / "pyproject.toml").exists():
        return heuristic

    # Walk from cwd through at most 5 parent levels; no unbounded filesystem scan.
    try:
        cwd = Path.cwd().resolve()
    except (OSError, RuntimeError):
        return heuristic
    for candidate in (cwd, *cwd.parents[:5]):
        if (candidate / "pyproject.toml").exists():
            _LOG.info(
                "Detected project root from cwd walk-up via pyproject.toml: path=%s wiki_exists=%s",
                candidate,
                (candidate / "wiki").exists(),
            )
            return candidate
    return heuristic


PROJECT_ROOT = _resolve_project_root()
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

# ── Cycle 14 AC1 — optional epistemic-integrity frontmatter vocabularies ──
# Fields are optional; absent is valid. When present, values must be in these
# tuples (enforced by kb.models.frontmatter.validate_frontmatter).
BELIEF_STATES = ("confirmed", "uncertain", "contradicted", "stale", "retracted")
AUTHORED_BY_VALUES = ("human", "llm", "hybrid")
PAGE_STATUSES = ("seed", "developing", "mature", "evergreen")

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

# ── Cycle 14 AC4 — query coverage-confidence refusal gate ─────
# When the mean vector-similarity of pages packed into Tier-1 context falls
# below this threshold, query_wiki skips synthesis and returns a fixed
# refusal advisory. See src/kb/query/engine.py::query_wiki.
QUERY_COVERAGE_CONFIDENCE_THRESHOLD = 0.45

# ── Cycle 14 AC7 — CONTEXT_TIER1_BUDGET proportional split (vocabulary) ──
# Integer percentages summing to 100. Helper: tier1_budget_for(component).
# No existing call-site migrated this cycle; follow-up BACKLOG entry tracks
# wiring into query/engine.py's context assembly.
CONTEXT_TIER1_SPLIT: dict[str, int] = {
    "wiki_pages": 60,
    "chat_history": 20,
    "index": 5,
    "system": 15,
}


def tier1_budget_for(component: str) -> int:
    """Return the CONTEXT_TIER1_BUDGET share for a split component.

    Args:
        component: One of ``CONTEXT_TIER1_SPLIT`` keys.

    Raises:
        ValueError: if ``component`` is not a known split key.
    """
    if component not in CONTEXT_TIER1_SPLIT:
        raise ValueError(
            f"invalid tier1 component: {component!r}; valid={tuple(CONTEXT_TIER1_SPLIT)}"
        )
    return (CONTEXT_TIER1_BUDGET * CONTEXT_TIER1_SPLIT[component]) // 100


# ── Cycle 14 AC10/AC11 — per-platform source-freshness decay (vocabulary) ──
# Keys are hostname tokens; values are decay windows in days. Ordered dict:
# first match wins on exact-or-dot-suffix lookup via decay_days_for(). No existing
# call-site migrated this cycle; BACKLOG tracks wiring into
# _flag_stale_results + lint staleness scan.
SOURCE_DECAY_DAYS: dict[str, int] = {
    "huggingface.co": 120,
    "github.com": 180,
    "stackoverflow.com": 365,
    "arxiv.org": 1095,
    "wikipedia.org": 1460,
    "openlibrary.org": 1825,
}
SOURCE_DECAY_DEFAULT_DAYS = STALENESS_MAX_DAYS


# ── Cycle 15 AC14 — per-topic volatility multipliers ──────────
# Case-folded keyword map: when a page's tags/title match one of these
# keywords, the source decay window is multiplied so volatile topics
# (LLMs, agents, web frameworks) treat sources as fresh for shorter
# windows — or in the cycle-14/15 shape, the multiplier EXTENDS decay
# because max() wins and 1.1× a 1095d arxiv window is 1204d. Read-only
# mapping prevents caller mutation; keys are casefolded at definition
# so lookup does not have to worry about case drift (threat T1).
_RAW_VOLATILITY_TOPICS: dict[str, float] = {
    "llm": 1.1,
    "react": 1.1,
    "docker": 1.1,
    "claude": 1.1,
    "agent": 1.1,
    "mcp": 1.1,
}
SOURCE_VOLATILITY_TOPICS: Mapping[str, float] = MappingProxyType(
    {k.casefold(): v for k, v in _RAW_VOLATILITY_TOPICS.items()}
)


def volatility_multiplier_for(text: str | None) -> float:
    """Return the highest matching volatility multiplier for ``text``.

    Scans ``text`` for word-boundary matches against each key in
    ``SOURCE_VOLATILITY_TOPICS``. Returns the maximum matched multiplier,
    or ``1.0`` when no key matches. "Most volatile topic wins" semantics
    — a page tagged both ``llm`` and a hypothetical ``rust`` key would
    take the larger multiplier.

    Threat T1 mitigation:
      - ``text`` is truncated to 4096 chars before scanning (length cap
        prevents pathological-input CPU exhaustion on adversarial tags).
      - Each key is ``re.escape``-ed so future keys with regex metachars
        cannot corrupt the pattern.

    Args:
        text: Page tags + title concatenated; ``None``/empty returns 1.0.

    Returns:
        Multiplier in ``[1.0, max(SOURCE_VOLATILITY_TOPICS.values())]``.
    """
    if not text:
        return 1.0
    # Cycle 15 T1 — length cap before regex loop.
    text = text[:4096]
    hits: list[float] = []
    for key, mult in SOURCE_VOLATILITY_TOPICS.items():
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, text, re.IGNORECASE):
            hits.append(mult)
    return max(hits, default=1.0)


def decay_days_for(ref: str | None, topics: str | None = None) -> int:
    """Return the decay-window days for a source reference.

    Parses ``ref`` as a URL via urllib.parse, extracts the hostname, and
    matches against ``SOURCE_DECAY_DAYS`` via exact or dot-boundary suffix
    match only (cycle-14 threat T6 — avoid partial-match domain spoof).
    IDN hostnames are IDNA-encoded before comparison. Refs without a
    scheme or hostname fall back to ``SOURCE_DECAY_DEFAULT_DAYS``.

    Cycle 15 AC16 — optional ``topics`` kwarg composes with the base
    decay window via ``volatility_multiplier_for``. When provided, the
    result is clamped to ``[1, SOURCE_DECAY_DEFAULT_DAYS * 50]`` to
    defend against hostile/typo multipliers (threat T2). Non-finite or
    non-positive multipliers fall back to 1.0 BEFORE the ``int()``
    coercion (``int(nan)`` raises on CPython).

    Args:
        ref: URL-style source reference (e.g. ``"https://arxiv.org/abs/X"``)
            or ``None``/empty string.
        topics: Optional concatenation of tags + title for per-topic
            volatility. ``None`` (default) preserves pre-cycle-15
            backward compat (no multiplier applied).

    Returns:
        Decay window in days, always in ``[1, SOURCE_DECAY_DEFAULT_DAYS * 50]``.
    """
    if not ref:
        base_days = SOURCE_DECAY_DEFAULT_DAYS
    else:
        base_days = _lookup_decay_by_host(ref)
    if topics is None:
        return base_days
    # Cycle 15 T2 — fallback BEFORE int() to avoid ValueError on NaN.
    mult = volatility_multiplier_for(topics)
    if not math.isfinite(mult) or mult <= 0:
        mult = 1.0
    return max(1, min(int(base_days * mult), SOURCE_DECAY_DEFAULT_DAYS * 50))


def _lookup_decay_by_host(ref: str) -> int:
    """Internal helper — host match via urlparse + dot-boundary keyfind."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(ref.strip())
    except (ValueError, AttributeError):
        return SOURCE_DECAY_DEFAULT_DAYS
    host = (parsed.hostname or "").lower()
    if not host:
        return SOURCE_DECAY_DEFAULT_DAYS
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        pass
    for key, days in SOURCE_DECAY_DAYS.items():
        if host == key or host.endswith("." + key):
            return days
    return SOURCE_DECAY_DEFAULT_DAYS


# ── Cycle 14 AC23 / Q10 — status ranking boost magnitude ──────
# Multiplicative boost factor applied to pages whose frontmatter status is
# in ("mature", "evergreen") AND passes validate_frontmatter (AC2 gate).
# Applied in src/kb/query/engine.py::search_pages AFTER RRF fusion and
# BEFORE dedup_results.
STATUS_RANKING_BOOST = 0.05

# ── Cycle 15 AC3 — authored_by ranking boost magnitude ──────────
# Multiplicative boost factor applied to pages whose frontmatter
# authored_by is in ("human", "hybrid") AND passes validate_frontmatter
# (T7 gate). Applied by _apply_authored_by_boost AFTER _apply_status_boost
# in the query score pipeline.
AUTHORED_BY_BOOST = 0.02


# ── Cycle 16 AC1-AC3 — query refinement + lint quality ──────────
# QUERY_REPHRASING_MAX: maximum rephrasings surfaced in the low-coverage
# refusal advisory. Consumed by kb.query.engine._suggest_rephrasings.
QUERY_REPHRASING_MAX: int = 3

# DUPLICATE_SLUG_DISTANCE_THRESHOLD: maximum edit-distance at which two
# page slugs are considered near-duplicates. Consumed by
# kb.lint.checks.check_duplicate_slugs. Levenshtein lower bound
# abs(len(a) - len(b)) <= distance dictates bucket iteration radius.
DUPLICATE_SLUG_DISTANCE_THRESHOLD: int = 3

# CALLOUT_MARKERS: recognised Obsidian-style inline callout marker names.
# Consumed by kb.lint.checks.parse_inline_callouts (regex-escaped per entry
# before alternation — future additions with metachars cannot corrupt
# the pattern).
CALLOUT_MARKERS: tuple[str, ...] = ("contradiction", "gap", "stale", "key-insight")
