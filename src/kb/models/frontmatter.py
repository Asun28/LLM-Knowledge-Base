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

    if "type" in post.metadata and post.metadata["type"] not in PAGE_TYPES:
        errors.append(f"Invalid type: {post.metadata['type']}. Must be one of {PAGE_TYPES}")

    if "confidence" in post.metadata and post.metadata["confidence"] not in CONFIDENCE_LEVELS:
        errors.append(
            f"Invalid confidence: {post.metadata['confidence']}. Must be one of {CONFIDENCE_LEVELS}"
        )

    return errors
