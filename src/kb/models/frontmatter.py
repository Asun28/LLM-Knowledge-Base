"""Frontmatter schema validation using python-frontmatter."""

import datetime

import frontmatter

from kb.config import (
    AUTHORED_BY_VALUES,
    BELIEF_STATES,
    CONFIDENCE_LEVELS,
    PAGE_STATUSES,
    PAGE_TYPES,
)

REQUIRED_FIELDS = ("title", "source", "created", "updated", "type", "confidence")

_VALID_DATE_TYPES = (str, datetime.date, datetime.datetime)


def _is_valid_date(value: object) -> bool:
    """Return True if value is a valid date representation."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return True
    if isinstance(value, str):
        if not value:
            return False
        try:
            datetime.date.fromisoformat(value)
            return True
        except ValueError:
            return False
    return False


def validate_frontmatter(post: frontmatter.Post) -> list[str]:
    """Validate frontmatter fields. Returns list of error messages."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in post.metadata:
            errors.append(f"Missing required field: {field}")

    source = post.metadata.get("source")
    if "source" in post.metadata:
        if source is None or not isinstance(source, (str, list)):
            errors.append(
                f"Invalid source type: {type(source).__name__}. Must be a string or list."
            )
        elif isinstance(source, list) and not source:
            errors.append("Source list is empty.")
        elif isinstance(source, list) and not all(isinstance(s, str) for s in source):
            errors.append("Source list items must all be strings.")

    if "created" in post.metadata and not _is_valid_date(post.metadata["created"]):
        errors.append(
            f"Invalid created date type: {type(post.metadata['created']).__name__}. "
            "Must be a string or date."
        )

    if "updated" in post.metadata and not _is_valid_date(post.metadata["updated"]):
        errors.append(
            f"Invalid updated date type: {type(post.metadata['updated']).__name__}. "
            "Must be a string or date."
        )

    if "type" in post.metadata and post.metadata["type"] not in PAGE_TYPES:
        errors.append(f"Invalid type: {post.metadata['type']}. Must be one of {PAGE_TYPES}")

    if "confidence" in post.metadata and post.metadata["confidence"] not in CONFIDENCE_LEVELS:
        errors.append(
            f"Invalid confidence: {post.metadata['confidence']}. Must be one of {CONFIDENCE_LEVELS}"
        )

    # Cycle 14 AC2 — optional epistemic-integrity fields. Absent is valid
    # (backwards compatible); when present, the value must be a non-empty
    # string from the associated vocabulary. None / empty-string / YAML
    # boolean coercion (e.g. `status: yes` → True) are all rejected.
    for field, vocab in (
        ("belief_state", BELIEF_STATES),
        ("authored_by", AUTHORED_BY_VALUES),
        ("status", PAGE_STATUSES),
    ):
        if field in post.metadata:
            value = post.metadata[field]
            if not isinstance(value, str) or not value or value not in vocab:
                errors.append(f"Invalid {field}: {value!r}. Must be one of {vocab}")

    return errors
