"""Cycle 9 MCP app instruction tests."""

import asyncio
import re


def _instruction_tool_groups(instructions: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    current_group: str | None = None

    for line in instructions.splitlines():
        if match := re.fullmatch(r"### (?P<group>.+)", line):
            current_group = match.group("group")
            groups[current_group] = []
            continue

        if current_group and (match := re.fullmatch(r"- `(?P<name>kb_[^`]+)` — .+", line)):
            groups[current_group].append(match.group("name"))

    return groups


def test_instructions_tool_names_sorted_within_groups():
    from kb.mcp import mcp

    groups = _instruction_tool_groups(mcp.instructions or "")

    assert groups
    for group_name, tool_names in groups.items():
        assert tool_names, f"{group_name} has no documented tools"
        assert sorted(tool_names) == tool_names

    rendered_tool_names = {name for tool_names in groups.values() for name in tool_names}
    registered_tools = asyncio.run(mcp.list_tools(run_middleware=False))
    registered_tool_names = {tool.name for tool in registered_tools}

    assert rendered_tool_names == registered_tool_names
