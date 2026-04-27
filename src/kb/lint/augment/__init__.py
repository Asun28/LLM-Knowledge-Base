"""Augment package re-exports for backward-compatible imports.

Ruff must not strip these compatibility exports; callers historically imported
private helpers from `kb.lint.augment` while the implementation lived in a flat
module.
"""

from __future__ import annotations

import frontmatter as frontmatter  # noqa: F401  # re-exported for backward compat (cycle-23 L5)

from kb.config import (
    RAW_DIR,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    WIKI_DIR,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    collector as collector,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    fetcher as fetcher,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    manifest as manifest,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    orchestrator as orchestrator,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    persister as persister,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    proposer as proposer,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    quality as quality,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment import (
    rate as rate,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.collector import (
    _PLACEHOLDER_TITLE_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _collect_eligible_stubs,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.manifest import (
    MANIFEST_DIR,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    RESUME_COMPLETE_STATES,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    TERMINAL_STATES,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    Manifest,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.orchestrator import (
    Mode,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _load_purpose_text,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    run_augment,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.persister import (
    _PROPOSAL_ACTION_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _PROPOSAL_HEADER_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _PROPOSAL_RATIONALE_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _PROPOSAL_REASON_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _PROPOSAL_TITLE_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _PROPOSAL_URL_ITEM_RE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _format_proposals_md,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _mark_page_augmented,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _parse_proposals_md,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _record_attempt,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _save_raw_file,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.proposer import (
    _PROPOSER_PROMPT_TEMPLATE,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _PROPOSER_SCHEMA,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _RELEVANCE_SCHEMA,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _build_proposer_prompt,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _propose_urls,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _relevance_score,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _wikipedia_fallback,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    call_llm_json,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.quality import (
    _count_final_stub_outcomes,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _post_ingest_quality,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _record_verdict_gap_callout,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    _resolve_raw_dir,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.lint.augment.rate import (
    RATE_PATH,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    RateLimiter,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
from kb.utils.pages import (
    load_page_frontmatter,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
    save_page_frontmatter,  # noqa: F401  # re-exported for backward compat (cycle-23 L5)
)
