"""Lazy YAML loader for wiki/_lint.yml allowlist overrides.

Cycle 68 AC03 — yaml.safe_load ONLY (RCE class T7 mitigation).

Policy:
- Reads ``WIKI_DIR/_lint.yml`` (or supplied ``wiki_dir/_lint.yml``) at CALL
  TIME (cycle-19 L2 no-cache) — every call hits the disk so editing the
  file between calls reflects on the next read.
- Uses ``yaml.safe_load`` ONLY. ``yaml.load`` is forbidden by FW-2 because
  it accepts ``!!python/object/new`` tags that execute arbitrary code on
  parse — a confirmed RCE class (T7 in the cycle-68 threat model).
- Graceful fallback: missing file, parse error, or read error → ``{}``
  with a warning. Never raises to callers.
- Schema gate: ``duplicate_slug_allowlist`` MUST be a list of 2-element
  lists; wrong shape → warning + key dropped (caller falls through to
  ``DUPLICATE_SLUG_ALLOWLIST`` defaults).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from kb.config import WIKI_DIR

logger = logging.getLogger(__name__)


def load_lint_config(wiki_dir: Path | None = None) -> dict[str, Any]:
    """Load ``wiki_dir/_lint.yml`` overrides via ``yaml.safe_load`` (FW-2).

    Args:
        wiki_dir: Optional override of the wiki root. Defaults to
            ``kb.config.WIKI_DIR`` at call time (cycle-19 L2).

    Returns:
        The parsed mapping, or ``{}`` if the file is missing, unreadable,
        malformed, or has a non-mapping top-level. Schema-rejected keys
        (e.g., wrong-shape ``duplicate_slug_allowlist``) are dropped from
        the returned dict so callers can rely on key presence as a
        well-formedness signal.

    Notes:
        FW-2: never call ``yaml.load`` here — only ``yaml.safe_load`` is
        permitted. Adding new YAML loaders requires a threat-model update.
    """
    target = (wiki_dir or WIKI_DIR) / "_lint.yml"
    if not target.exists():
        return {}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("kb.lint._lint_yaml: read error %s: %s", target, exc)
        return {}
    try:
        data = yaml.safe_load(text)  # FW-2: NEVER yaml.load
    except yaml.YAMLError as exc:
        logger.warning("kb.lint._lint_yaml: YAML parse error: %s", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "kb.lint._lint_yaml: top-level must be mapping; got %s",
            type(data).__name__,
        )
        return {}
    if "duplicate_slug_allowlist" in data:
        val = data["duplicate_slug_allowlist"]
        if not (isinstance(val, list) and all(isinstance(p, list) and len(p) == 2 for p in val)):
            logger.warning(
                "kb.lint._lint_yaml: duplicate_slug_allowlist must be list-of-pairs; got %r",
                val,
            )
            data.pop("duplicate_slug_allowlist", None)
    return data
