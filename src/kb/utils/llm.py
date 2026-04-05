"""Anthropic API wrapper with model tiering."""


import anthropic

from kb.config import MODEL_TIERS


def get_client() -> anthropic.Anthropic:
    """Get an Anthropic client (uses ANTHROPIC_API_KEY env var)."""
    return anthropic.Anthropic()


def call_llm(
    prompt: str,
    *,
    tier: str = "write",
    system: str = "",
    max_tokens: int = 4096,
) -> str:
    """Call Claude with the appropriate model tier.

    Tiers: "scan" (Haiku), "write" (Sonnet), "orchestrate" (Opus).
    """
    client = get_client()
    model = MODEL_TIERS[tier]

    messages = [{"role": "user", "content": prompt}]
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return response.content[0].text
