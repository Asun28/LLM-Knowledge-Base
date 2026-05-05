"""AST walking helpers for meta-tests — used by AC4, AC17, AC18, AC20, AC23."""

import ast
from pathlib import Path


def find_imports_from(module: str, name: str) -> list[Path]:
    """
    Scan src/kb/**/*.py and return list of files importing `name` from `module`.

    Example:
        find_imports_from("kb.config", "PROJECT_ROOT")
        → [Path("src/kb/utils/foo.py"), ...]

    Args:
        module: Module name (e.g., "kb.config")
        name: Symbol name to search for

    Returns:
        List of Path objects to matching files
    """
    src_kb = Path("src/kb")
    if not src_kb.exists():
        return []

    matches = []
    for py_file in src_kb.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module == module:
                        for alias in node.names:
                            if alias.name == name:
                                matches.append(py_file)
                                break
        except (SyntaxError, UnicodeDecodeError):
            pass

    return matches


def find_function_def(file_path: Path, name: str) -> ast.FunctionDef | None:
    """
    Parse a file and return the FunctionDef node for the given function name.

    Args:
        file_path: Path to the Python file
        name: Function name to search for

    Returns:
        ast.FunctionDef node if found, None otherwise
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
    except (SyntaxError, UnicodeDecodeError):
        pass

    return None


def find_calls_of(file_paths: list[Path], qualified_name: str) -> list[tuple[Path, int]]:
    """
    Scan a list of files for calls to a qualified name (e.g., "_assert_under_project_root").

    Handles both:
      - Name(id="...") — direct function calls
      - Attribute(attr="...") — method/attribute access calls

    Args:
        file_paths: List of Path objects to scan
        qualified_name: Function name to find calls to

    Returns:
        List of (file_path, line_number) tuples where calls are found
    """
    matches = []

    for file_path in file_paths:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    # Handle Name(id="...") case
                    if isinstance(func, ast.Name) and func.id == qualified_name:
                        matches.append((file_path, node.lineno))
                    # Handle Attribute(attr="...") case
                    elif isinstance(func, ast.Attribute) and func.attr == qualified_name:
                        matches.append((file_path, node.lineno))
        except (SyntaxError, UnicodeDecodeError):
            pass

    return matches


def assert_decorator_present(
    func_def: ast.FunctionDef, expected_decorator: str, source_path: Path
) -> None:
    """
    Assert that a function definition has the expected decorator.

    Prints expected vs. actual + line number on failure.

    Args:
        func_def: The FunctionDef AST node
        expected_decorator: Name of the decorator to check for
        source_path: Path to the source file (for error messages)

    Raises:
        AssertionError: If the decorator is not found
    """
    decorator_names = []
    for dec in func_def.decorator_list:
        if isinstance(dec, ast.Name):
            decorator_names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorator_names.append(dec.attr)
        elif isinstance(dec, ast.Call):
            # Handle @pytest.fixture(...) style
            if isinstance(dec.func, ast.Attribute):
                decorator_names.append(dec.func.attr)
            elif isinstance(dec.func, ast.Name):
                decorator_names.append(dec.func.id)

    if expected_decorator not in decorator_names:
        raise AssertionError(
            f"Decorator '{expected_decorator}' not found on function '{func_def.name}' "
            f"at {source_path}:{func_def.lineno}. "
            f"Found decorators: {decorator_names}"
        )
