"""Source-type-specific extraction logic (article, paper, video, etc.)."""

import copy
import functools
import logging
import re

import yaml

from kb.config import SOURCE_TYPE_DIRS, TEMPLATES_DIR
from kb.utils.llm import call_llm_json
from kb.utils.pages import load_purpose

logger = logging.getLogger(__name__)

# Restrict to types that have raw/ directory mappings (excludes comparison/synthesis).
# compiler.py imports this to guard template-change detection and looks up SOURCE_TYPE_DIRS.
VALID_SOURCE_TYPES = frozenset(SOURCE_TYPE_DIRS.keys())

# Fields that are always lists across all extraction templates.
# Used as fallback when template specs lack explicit type annotations.
_ANNOTATED_FIELD_RE = re.compile(r"^(\w+)\s*\(([^)]+)\)\s*:\s*(.+)$")

KNOWN_LIST_FIELDS = frozenset(
    {
        # Common across all templates
        "entities_mentioned",
        "concepts_mentioned",
        # Article
        "key_claims",
        "evidence",
        # Paper
        "authors",
        "citations_relevant",
        "results",
        "limitations",
        # Video
        "key_points",
        "claims_with_timestamps",
        "action_items",
        # Podcast
        "speakers",
        "topics_by_timestamp",
        "speaker_claims",
        "agreements",
        "disagreements",
        # Repo
        "dependencies",
        "usage_patterns",
        # Book
        "quotes",
        "themes",
        # Dataset
        "columns",
        "use_cases",
        # Conversation
        "participants",
        "topic_segments",
        "open_questions",
    }
)


@functools.lru_cache(maxsize=16)
def _load_template_cached(source_type: str) -> dict:
    """Internal LRU-cached template loader. Returns the raw dict — do not mutate."""
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"Invalid source type: {source_type!r}. "
            f"Valid types: {', '.join(sorted(VALID_SOURCE_TYPES))}"
        )
    template_path = TEMPLATES_DIR / f"{source_type}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"No template for source type: {source_type}")
    return yaml.safe_load(template_path.read_text(encoding="utf-8"))


def load_template(source_type: str) -> dict:
    """Load extraction template YAML for a given source type.

    Returns a fresh deep copy each call so callers may freely mutate the result
    without corrupting the internal LRU cache.

    Results are cached per-process via LRU cache. Template changes on disk
    will not be reflected until the process is restarted (cache is not invalidated).

    Raises:
        ValueError: If source_type is not in the whitelist.
        FileNotFoundError: If template file is missing.
    """
    return copy.deepcopy(_load_template_cached(source_type))


def _parse_field_spec(spec: str) -> tuple[str, str, bool]:
    """Parse a template field spec into (name, description, is_list).

    Handles two formats:
    - Simple: "field_name" or "field_name  # comment"
    - Annotated: "field_name (type): description"
    """
    spec = spec.strip().strip('"')

    # Fix 2.16: Strip YAML-style inline comments only when preceded by double space
    if "  # " in spec:
        spec = spec[: spec.index("  # ")].strip()

    # Check for annotated format: "name (type): description"
    annotated = _ANNOTATED_FIELD_RE.match(spec)
    if annotated:
        name = annotated.group(1)
        type_hint = annotated.group(2).strip()
        desc = annotated.group(3).strip()
        is_list = "list" in type_hint.lower()
        return name, desc, is_list

    # Simple format: "field_name" or "field_name: description"
    if ":" in spec:
        name, desc = spec.split(":", 1)
        name = name.strip()
        desc = desc.strip()
    else:
        name = spec.strip()
        desc = ""

    # Warn on field names that won't match LLM output
    if not re.match(r"^\w+$", name):
        logger.warning(
            "Field name %r contains non-identifier characters; "
            "it may not match LLM extraction output",
            name,
        )

    is_list = name in KNOWN_LIST_FIELDS
    return name, desc, is_list


def build_extraction_schema(template: dict) -> dict:
    """Build JSON Schema from extraction template fields for tool_use.

    Parses template field specs into a JSON Schema object that can be
    used with Claude's tool_use feature for guaranteed structured output.
    """
    # Fix 2.5: clear error on missing or invalid extract key
    if "extract" not in template or not isinstance(template["extract"], list):
        raise ValueError(
            f"Template missing 'extract' key or invalid value: {template.get('name', '?')}. "
            "Expected a list of field specs."
        )

    properties = {}
    required = []

    for field_spec in template["extract"]:
        name, desc, is_list = _parse_field_spec(field_spec)

        if is_list:
            properties[name] = {
                "type": "array",
                "items": {"type": "string"},
                "description": desc or name.replace("_", " "),
            }
        else:
            properties[name] = {
                "type": "string",
                "description": desc or name.replace("_", " "),
            }

        if name in ("title", "name"):
            required.append(name)

    # Fix 2.6: ensure at least the first field is required
    if not required and properties:
        required = [next(iter(properties))]

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def clear_template_cache() -> None:
    """Clear the LRU caches for template loading and schema building.

    Useful during long-running processes or interactive template development.
    """
    _load_template_cached.cache_clear()
    _build_schema_cached.cache_clear()


@functools.lru_cache(maxsize=16)
def _build_schema_cached(source_type: str) -> dict:
    """LRU-cached schema builder: load template then build schema.

    Use this instead of calling build_extraction_schema(template) directly
    to avoid rebuilding the schema on every extraction call.
    """
    template = load_template(source_type)
    return build_extraction_schema(template)


def build_extraction_prompt(content: str, template: dict, purpose: str | None = None) -> str:
    """Build the LLM prompt for extracting structured data from a raw source."""
    fields = template["extract"]
    field_descriptions = "\n".join(f"- {f}" for f in fields)
    source_name = template.get("name", "document")
    source_desc = template.get("description", "")
    purpose_section = f"\nKB FOCUS (bias extraction toward these goals):\n{purpose}\n" if purpose else ""

    return f"""Extract structured information from the following source document.
{purpose_section}
Source type: {source_name} — {source_desc}

Extract these fields as a JSON object:
{field_descriptions}

For list fields (key_claims, entities_mentioned, concepts_mentioned, etc.),
return arrays of strings.
For scalar fields, return strings.
If a field cannot be determined from the source, use null.

Use the provided tool to return the extracted data.

---
SOURCE DOCUMENT:
{content}
"""


def extract_from_source(content: str, source_type: str) -> dict:
    """Call the LLM to extract structured data from raw source content.

    Uses Claude's tool_use feature for guaranteed valid JSON output,
    eliminating JSON parsing errors from code fences or malformed text.

    Args:
        content: The raw source text.
        source_type: One of: article, paper, repo, video, podcast, book, dataset, conversation.

    Returns:
        dict with extracted fields matching the template schema.
    """
    template = load_template(source_type)
    purpose = load_purpose()
    prompt = build_extraction_prompt(content, template, purpose=purpose)
    schema = _build_schema_cached(source_type)
    system_msg = "You are a precise information extractor."

    return call_llm_json(
        prompt,
        tier="write",
        system=system_msg,
        schema=schema,
        tool_description=f"Extract structured data from a {source_type} document.",
    )
