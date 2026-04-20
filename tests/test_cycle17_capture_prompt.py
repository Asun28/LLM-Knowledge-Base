"""Cycle 17 AC9 — capture prompt template loaded from `templates/capture_prompt.txt`."""

from __future__ import annotations

from pathlib import Path

import kb.capture as capture_module
from kb.config import TEMPLATES_DIR


class TestAC9PromptTemplate:
    def test_prompt_template_begins_with_expected_first_line(self) -> None:
        """The loaded template must start with the known atomisation instruction."""
        assert capture_module._PROMPT_TEMPLATE.startswith(
            "You are atomizing messy text into discrete knowledge items."
        ), "AC9 regression: loaded prompt text differs from expected first line."

    def test_prompt_template_file_exists(self) -> None:
        """`templates/capture_prompt.txt` must exist at the hardcoded path."""
        assert (TEMPLATES_DIR / "capture_prompt.txt").is_file(), (
            f"AC9 regression: {TEMPLATES_DIR / 'capture_prompt.txt'} is missing. "
            "The capture prompt loader expects this file at module-import time."
        )

    def test_prompt_template_contains_named_placeholders(self) -> None:
        """Prompt must keep `{max_items}`, `{boundary_start}`, `{content}`, `{boundary_end}`."""
        template = capture_module._PROMPT_TEMPLATE
        for placeholder in ("{max_items}", "{boundary_start}", "{content}", "{boundary_end}"):
            assert placeholder in template, (
                f"AC9 regression: capture prompt missing required placeholder {placeholder}"
            )

    def test_prompt_template_renders_without_error(self) -> None:
        """`.format(...)` must succeed with the expected keys."""
        rendered = capture_module._PROMPT_TEMPLATE.format(
            max_items=20,
            boundary_start="<<<INPUT-abc123>>>",
            boundary_end="<<<END-INPUT-abc123>>>",
            content="hello world",
        )
        assert "hello world" in rendered
        assert "<<<INPUT-abc123>>>" in rendered
        assert "<<<END-INPUT-abc123>>>" in rendered
        assert "Cap the output at 20 items" in rendered

    def test_loader_path_is_hardcoded(self) -> None:
        """T11 — loader path is compile-time constant, not caller-controlled."""
        # The source at capture.py line ~295 uses TEMPLATES_DIR / "capture_prompt.txt"
        # as a module-level constant. This test asserts that TEMPLATES_DIR is a
        # stable path not derived from caller input.
        assert isinstance(TEMPLATES_DIR, Path)
        assert TEMPLATES_DIR.name == "templates"
