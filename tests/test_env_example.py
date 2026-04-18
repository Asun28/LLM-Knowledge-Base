"""Cycle 9 AC30 — .env.example must mark ANTHROPIC_API_KEY as optional."""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_EXAMPLE = _PROJECT_ROOT / ".env.example"


def test_env_example_marks_anthropic_key_optional() -> None:
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    lines = text.splitlines()

    # (a) Line containing `ANTHROPIC_API_KEY=` still matches the prefix.
    key_line_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("ANTHROPIC_API_KEY="):
            key_line_idx = i
            assert line.strip().startswith("ANTHROPIC_API_KEY=sk-ant-"), (
                f"Expected placeholder prefix `ANTHROPIC_API_KEY=sk-ant-`, got: {line!r}"
            )
            break
    assert key_line_idx is not None, "ANTHROPIC_API_KEY declaration not found"

    # Gather the contiguous comment block immediately above the declaration.
    comment_block = []
    for line in reversed(lines[:key_line_idx]):
        if line.startswith("#"):
            comment_block.insert(0, line)
        elif not line.strip():
            # stop at blank line separator above the block
            if comment_block:
                break
            continue
        else:
            break

    comment_text = "\n".join(comment_block).lower()

    # (b) Preceding comment block contains `optional` (case-insensitive) and NOT `required`
    # as a gating word.
    assert "optional" in comment_text, (
        f'Expected "optional" in preceding comment block: {comment_block}'
    )
    # The Required mentions are allowed IF qualified ("Required ONLY for"),
    # but a bare leading "Required —" is not allowed.
    for line in comment_block:
        assert not line.strip().lower().startswith("# required —"), (
            f"Line marks key as required without qualification: {line!r}"
        )

    # (c) A clarifying comment mentions Claude Code / MCP / use_api=True (at least one).
    clarifiers = ("claude code", "mcp", "use_api=true")
    assert any(c in comment_text for c in clarifiers), (
        f"Expected at least one of {clarifiers} in the comment block; got {comment_block!r}"
    )
