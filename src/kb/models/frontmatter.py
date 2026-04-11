"""Frontmatter schema validation using python-frontmatter."""

import datetime

import frontmatter

from kb.config import CONFIDENCE_LEVELS, PAGE_TYPES

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

    return errors
