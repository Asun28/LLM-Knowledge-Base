"""Source-type-specific extraction logic (article, paper, video, etc.)."""

import functools
import re

import yaml

from kb.config import SOURCE_TYPE_DIRS, TEMPLATES_DIR
from kb.utils.llm import call_llm_json

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
        "chapters",
        "key_themes",
        "key_arguments",
        "quotes",
        "themes",
        # Dataset
        "columns",
        "use_cases",
        # Conversation
        "participants",
        "topic_segments",
        "key_exchanges",
        "open_questions",
    }
)


@functools.lru_cache(maxsize=16)
def load_template(source_type: str) -> dict:
    """Load extraction template YAML for a given source type.

    Raises:
        ValueError: If source_type is not in the whitelist.
        FileNotFoundError: If template file is missing.
    """
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"Invalid source type: {source_type!r}. "
            f"Valid types: {', '.join(sorted(VALID_SOURCE_TYPES))}"
        )
    template_path = TEMPLATES_DIR / f"{source_type}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"No template for source type: {source_type}")
    return yaml.safe_load(template_path.read_text(encoding="utf-8"))


def _parse_field_spec(spec: str) -> tuple[str, str, bool]:
    """Parse a template field spec into (name, description, is_list).

    Handles two formats:
    - Simple: "field_name" or "field_name  # comment"
    - Annotated: "field_name (type): description"
    """
    spec = spec.strip().strip('"')

    # Strip YAML-style inline comments
    if " #" in spec:
        spec = spec[: spec.index(" #")].strip()

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

    is_list = name in KNOWN_LIST_FIELDS
    return name, desc, is_list


def build_extraction_schema(template: dict) -> dict:
    """Build JSON Schema from extraction template fields for tool_use.

    Parses template field specs into a JSON Schema object that can be
    used with Claude's tool_use feature for guaranteed structured output.
    """
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

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


@functools.lru_cache(maxsize=16)
def _build_schema_cached(source_type: str) -> dict:
    """LRU-cached schema builder: load template then build schema.

    Use this instead of calling build_extraction_schema(template) directly
    to avoid rebuilding the schema on every extraction call.
    """
    template = load_template(source_type)
    return build_extraction_schema(template)


def build_extraction_prompt(content: str, template: dict) -> str:
    """Build the LLM prompt for extracting structured data from a raw source."""
    fields = template["extract"]
    field_descriptions = "\n".join(f"- {f}" for f in fields)

    return f"""Extract structured information from the following source document.

Source type: {template["name"]} — {template["description"]}

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
    prompt = build_extraction_prompt(content, template)
    schema = build_extraction_schema(template)
    system_msg = "You are a precise information extractor."

    return call_llm_json(
        prompt,
        tier="write",
        system=system_msg,
        schema=schema,
        tool_description=f"Extract structured data from a {source_type} document.",
    )
