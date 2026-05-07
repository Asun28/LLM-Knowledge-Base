"""Audit Python functions for docstring sections (Args / Returns / Raises / Yields).

Cycle 68 AC05 — warn-only transition mode for the public ``kb.*`` API. Scans
functions reachable from ``--paths`` (default: ``src/kb/``) and flags those
missing the conventional Google-style sections when their AST shape implies a
section is required:

- ``Args:`` required when the function has at least one non-self/non-cls
  parameter.
- ``Returns:`` required when the function has any non-bare ``return`` AND
  contains no ``yield`` (i.e., it's not a generator).
- ``Yields:`` required when the function contains any ``yield``.
- ``Raises:`` required when the function body contains any ``raise``
  statement, INCLUDING when the function is a generator (FW-4 — the
  cycle-67 carry-over: generators must NOT be exempt).

Exits 0 in ``--warn-only`` mode (cycle-68 transition); without that flag,
exits 1 when any function violates the rules. JSON findings stream to
stdout (one combined object); diagnostics stream to stderr.

Style precedent: ``scripts/verify_docs.py`` (Phase 4.5 docs-sync). No
third-party dependencies — stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Default scope: src/kb (skipped __pycache__, __init__-only files OK).
DEFAULT_SCAN_PATH = PROJECT_ROOT / "src" / "kb"


def _iter_python_files(roots: list[Path]) -> list[Path]:
    """Yield every ``*.py`` file under each root (recursive); skip __pycache__.

    Args:
        roots: One or more file or directory paths.

    Returns:
        Flat list of file paths to audit.
    """
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fname in filenames:
                if fname.endswith(".py"):
                    files.append(Path(dirpath) / fname)
    return files


def _func_has_meaningful_args(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if the function has at least one arg that isn't self/cls.

    Args:
        node: AST function-def node.

    Returns:
        True iff non-self/cls positional, kwonly, *args, or **kwargs is present.
    """
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    return bool(positional or args.vararg or args.kwonlyargs or args.kwarg)


def _walk_excluding_nested(body: list[ast.stmt]) -> list[ast.AST]:
    """Walk AST nodes from ``body`` but skip nested function/class bodies.

    Required so ``raise`` inside a nested helper doesn't taint the parent.

    Args:
        body: List of top-level statements (the function's ``.body``).

    Returns:
        Flattened list of AST nodes belonging only to the outermost function.
    """
    out: list[ast.AST] = []
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        out.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        for child in ast.iter_child_nodes(node):
            stack.append(child)
    return out


def _func_has_return_value(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if any non-nested ``return EXPR`` (with non-None value) exists.

    Args:
        node: AST function-def node.

    Returns:
        True iff the function explicitly returns a value (not bare ``return``).
    """
    for sub in _walk_excluding_nested(node.body):
        if isinstance(sub, ast.Return) and sub.value is not None:
            return True
    return False


def _func_is_generator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if any (non-nested) ``yield`` / ``yield from`` is present.

    Args:
        node: AST function-def node.

    Returns:
        True iff the function is a generator.
    """
    for sub in _walk_excluding_nested(node.body):
        if isinstance(sub, (ast.Yield, ast.YieldFrom)):
            return True
    return False


def _func_has_raise(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if any (non-nested) ``raise`` statement is present.

    FW-4: this check IS run on generators too — a generator that raises
    needs ``Raises:`` documented.

    Args:
        node: AST function-def node.

    Returns:
        True iff the function body raises (excluding nested closures).
    """
    for sub in _walk_excluding_nested(node.body):
        if isinstance(sub, ast.Raise):
            return True
    return False


def _has_section(docstring: str | None, label: str) -> bool:
    """Return True if ``label:`` appears as a section header in the docstring.

    Looks for ``label`` followed by ``:`` at the start of a (possibly indented)
    line — matches Google-style and NumPy-style emitted by sphinx.

    Args:
        docstring: The function's docstring (or None).
        label: Section label, e.g., ``"Args"`` or ``"Raises"``.

    Returns:
        True iff a matching section header was found.
    """
    if not docstring:
        return False
    needle = label + ":"
    for line in docstring.splitlines():
        if line.strip().startswith(needle):
            return True
    return False


def _audit_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: Path,
) -> dict | None:
    """Return a finding dict if ``node`` is missing required docstring sections.

    Args:
        node: AST function-def node.
        file_path: Path to the source file (for reporting).

    Returns:
        Finding dict ``{"file","name","lineno","missing","has_docstring"}`` or
        None if all required sections are present.
    """
    docstring = ast.get_docstring(node)
    missing: list[str] = []

    has_args = _func_has_meaningful_args(node)
    is_generator = _func_is_generator(node)
    has_return_value = _func_has_return_value(node)
    has_raise = _func_has_raise(node)

    if has_args and not _has_section(docstring, "Args"):
        missing.append("Args")
    if is_generator:
        if not _has_section(docstring, "Yields"):
            missing.append("Yields")
    elif has_return_value:
        if not _has_section(docstring, "Returns"):
            missing.append("Returns")
    # FW-4: generators with raise still need Raises:
    if has_raise and not _has_section(docstring, "Raises"):
        missing.append("Raises")

    if not missing:
        return None
    return {
        "file": str(file_path),
        "name": node.name,
        "lineno": node.lineno,
        "missing": missing,
        "has_docstring": docstring is not None,
    }


def _audit_file(file_path: Path) -> list[dict]:
    """Parse ``file_path`` and audit every top-level + class-method function.

    Args:
        file_path: Path to a Python source file.

    Returns:
        List of finding dicts (empty if clean or unreadable).
    """
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []
    findings: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip dunder methods (__init__, __repr__, etc.) — they have
            # well-known semantics and PEP 257 doesn't require sections.
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            finding = _audit_function(node, file_path)
            if finding is not None:
                findings.append(finding)
    return findings


def _build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser.

    Returns:
        Configured ``argparse.ArgumentParser``.
    """
    parser = argparse.ArgumentParser(
        prog="audit_docstrings",
        description=(
            "Cycle 68 AC05 — audit kb.* (or supplied paths) for missing "
            "Args/Returns/Raises/Yields docstring sections."
        ),
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Exit 0 even if violations found (cycle-68 transition mode).",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=None,
        help="One or more file/dir paths to audit; defaults to src/kb/.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the audit and emit JSON to stdout.

    Args:
        argv: Optional override of ``sys.argv[1:]`` for testing.

    Returns:
        Exit code: 0 always under ``--warn-only``; otherwise 1 when any
        finding is reported, 0 when clean.
    """
    parser = _build_arg_parser()
    ns = parser.parse_args(argv)

    if ns.paths:
        roots = [Path(p).resolve() for p in ns.paths]
    else:
        roots = [DEFAULT_SCAN_PATH]

    files = _iter_python_files(roots)
    findings: list[dict] = []
    for fp in files:
        findings.extend(_audit_file(fp))

    sys.stdout.write(json.dumps(findings) + "\n")
    if findings:
        sys.stderr.write(
            f"audit_docstrings: {len(findings)} finding(s) across {len(files)} file(s)\n"
        )
        for f in findings[:20]:
            sys.stderr.write(f"  {f['file']}:{f['lineno']} {f['name']} missing={f['missing']}\n")
        if len(findings) > 20:
            sys.stderr.write(f"  ... ({len(findings) - 20} more)\n")
    else:
        sys.stderr.write(f"audit_docstrings: clean ({len(files)} files scanned)\n")
    sys.stderr.write(
        f"summary: {len(files)} files, {len(findings)} findings, warn_only={ns.warn_only}\n"
    )
    if ns.warn_only:
        return 0
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
