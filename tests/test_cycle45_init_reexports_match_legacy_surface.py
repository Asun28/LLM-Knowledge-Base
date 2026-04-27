"""Cycle 45 C1: split modules preserve the legacy import surface."""

from __future__ import annotations

import ast
import importlib
import subprocess

import pytest

BASE_REF = "68f8574"

EXTRA_IMPORT_SURFACE = {
    "src/kb/lint/augment.py": {"call_llm_json", "save_page_frontmatter"},
    "src/kb/mcp/core.py": {
        "PROJECT_ROOT",
        "RAW_DIR",
        "SOURCE_TYPE_DIRS",
        "atomic_text_write",
    },
}

MODULE_PAIRS = [
    # Cycle 44 parallel merge resolution: the checks.py, _augment_manifest.py,
    # and _augment_rate.py surface cases were dropped because cycle 44's M1/M2
    # chose a different decomposition.
    ("src/kb/lint/augment.py", "kb.lint.augment"),
    ("src/kb/mcp/core.py", "kb.mcp.core"),
]


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names.update(_target_names(elt))
        return names
    return set()


def _legacy_source(path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{BASE_REF}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _legacy_surface(path: str) -> set[str]:
    tree = ast.parse(_legacy_source(path))
    symbols = set(EXTRA_IMPORT_SURFACE[path])
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _target_names(target):
                    if name.isupper() or name.startswith("_"):
                        symbols.add(name)
        elif isinstance(node, ast.AnnAssign):
            for name in _target_names(node.target):
                if name.isupper() or name.startswith("_"):
                    symbols.add(name)
    return symbols


@pytest.mark.parametrize(("legacy_path", "module_name"), MODULE_PAIRS)
def test_init_reexports_match_legacy_surface(legacy_path: str, module_name: str):
    module = importlib.import_module(module_name)
    missing = sorted(_legacy_surface(legacy_path) - set(dir(module)))

    assert missing == []
