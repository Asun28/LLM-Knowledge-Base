"""Frontmatter schema validation using python-frontmatter."""

import frontmatter

from kb.config import CONFIDENCE_LEVELS, PAGE_TYPES

REQUIRED_FIELDS = ("title", "source", "created", "updated", "type", "confidence")


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

    if "type" in post.metadata and post.metadata["type"] not in PAGE_TYPES:
        errors.append(f"Invalid type: {post.metadata['type']}. Must be one of {PAGE_TYPES}")

    if "confidence" in post.metadata and post.metadata["confidence"] not in CONFIDENCE_LEVELS:
        errors.append(
            f"Invalid confidence: {post.metadata['confidence']}. Must be one of {CONFIDENCE_LEVELS}"
        )

    return errors
