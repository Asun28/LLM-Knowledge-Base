"""Cycle 19 AC18 — forward-looking lint guard.

A test method that takes ``tmp_kb_env`` as a parameter MUST NOT also call
``monkeypatch.setattr("kb.compile.compiler.HASH_MANIFEST", ...)`` because the
fixture (cycle-18 D6 extension) already redirects HASH_MANIFEST under the tmp
project. Method-scope detection (NOT file-scope) avoids the false positive
where a sibling test class in the same file uses ``tmp_project`` instead of
``tmp_kb_env``.

AC17 (cleanup of existing redundant patches) was DROPPED at plan-gate per
cycle-17 L3 scope-narrowing rule — re-grep showed zero actual cohabitations
in the current tree (the four standalone HASH_MANIFEST patchers don't use
tmp_kb_env, and the one tmp_kb_env+HASH_MANIFEST file scopes them to
different test classes). This test pins AC18 as a guard against future drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).parent


def _method_uses_tmp_kb_env(node: ast.FunctionDef) -> bool:
    return any(arg.arg == "tmp_kb_env" for arg in node.args.args)


def _method_body_text(source: str, node: ast.FunctionDef) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def test_no_redundant_hash_manifest_patch_inside_tmp_kb_env_method() -> None:
    """A test method that takes tmp_kb_env MUST NOT also patch kb.compile.compiler.HASH_MANIFEST.

    Method-scope detection: walks each test file's AST, finds every
    ``def test_*(...tmp_kb_env...)`` function, and checks the function's
    own source body (NOT the whole file) for a literal HASH_MANIFEST patch.
    File-scope grep produces false positives when a sibling test class uses
    ``tmp_project`` and patches HASH_MANIFEST inside its own helper.
    """
    offenders: list[str] = []
    for py in TESTS_DIR.glob("test_*.py"):
        if py.name == "test_cycle19_lint_redundant_patches.py":
            continue
        source = py.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            if not _method_uses_tmp_kb_env(node):
                continue
            body = _method_body_text(source, node)
            if "kb.compile.compiler.HASH_MANIFEST" in body and "monkeypatch.setattr" in body:
                offenders.append(f"{py.name}::{node.name}")
    assert not offenders, (
        "Test methods using tmp_kb_env must not also monkeypatch "
        "kb.compile.compiler.HASH_MANIFEST; the fixture (cycle-18 D6) already "
        f"redirects it. Offenders: {offenders}"
    )
