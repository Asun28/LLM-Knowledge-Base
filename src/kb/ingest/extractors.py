"""Source-type-specific extraction logic (article, paper, video, etc.)."""

import json

import yaml

from kb.config import SOURCE_TYPE_DIRS, TEMPLATES_DIR
from kb.utils.llm import call_llm

VALID_SOURCE_TYPES = frozenset(SOURCE_TYPE_DIRS.keys())


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

IMPORTANT: Return ONLY valid JSON, no markdown code fences, no explanation.

---
SOURCE DOCUMENT:
{content}
"""


def extract_from_source(content: str, source_type: str) -> dict:
    """Call the LLM to extract structured data from raw source content.

    Args:
        content: The raw source text.
        source_type: One of: article, paper, repo, video, podcast, book, dataset, conversation.

    Returns:
        dict with extracted fields matching the template schema.
    """
    template = load_template(source_type)
    prompt = build_extraction_prompt(content, template)
    system_msg = "You are a precise information extractor. Return only valid JSON."
    response = call_llm(prompt, tier="write", system=system_msg)

    # Strip markdown code fences if present
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        newline_pos = cleaned.find("\n")
        if newline_pos != -1:
            cleaned = cleaned[newline_pos + 1 :]
        else:
            # Single-line: strip opening ``` or ```json prefix
            cleaned = cleaned[3:]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON for {source_type} extraction: {e}\n"
            f"Response (first 200 chars): {response[:200]}"
        ) from e
