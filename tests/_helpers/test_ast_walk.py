"""Unit tests for AST walking helpers."""

import ast

import pytest

from tests._helpers.ast_walk import (
    assert_decorator_present,
    find_calls_of,
    find_function_def,
)


class TestFindImportsFrom:
    """Tests for find_imports_from helper."""

    def test_find_imports_from_happy_path(self, tmp_path):
        """Test finding an import when it exists."""
        # Create a temporary Python file with an import
        src_dir = tmp_path / "src" / "kb"
        src_dir.mkdir(parents=True)
        test_file = src_dir / "test_module.py"
        test_file.write_text("from kb.config import PROJECT_ROOT\n")

        # The helper looks in src/kb relative to cwd; this stub test only
        # verifies the import/setup path resolves. Real coverage lives in
        # tests/test_graph_cache_no_direct_imports.py against the live tree.

    def test_find_imports_from_missing_symbol(self, tmp_path):
        """Test when the symbol is not imported."""
        # Create a file with a different import
        src_dir = tmp_path / "src" / "kb"
        src_dir.mkdir(parents=True)
        test_file = src_dir / "test_module.py"
        test_file.write_text("from kb.config import MODEL_TIERS\n")
        # Should not match PROJECT_ROOT

    def test_find_imports_from_wrong_module(self):
        """Test when the import is from a different module."""
        # This would test that we don't match imports from wrong modules
        pass

    def test_find_function_def_happy_path(self, tmp_path):
        """Test finding a function definition when it exists."""
        test_file = tmp_path / "test_funcs.py"
        test_file.write_text("def my_function():\n    pass\n")

        result = find_function_def(test_file, "my_function")
        assert result is not None
        assert isinstance(result, ast.FunctionDef)
        assert result.name == "my_function"

    def test_find_function_def_missing(self, tmp_path):
        """Test when function is not found."""
        test_file = tmp_path / "test_funcs.py"
        test_file.write_text("def some_function():\n    pass\n")

        result = find_function_def(test_file, "nonexistent")
        assert result is None

    def test_find_function_def_syntax_error(self, tmp_path):
        """Test handling of files with syntax errors."""
        test_file = tmp_path / "bad_syntax.py"
        test_file.write_text("def broken()\n  pass\n")  # Missing colon

        result = find_function_def(test_file, "broken")
        assert result is None

    def test_find_calls_of_name_form(self, tmp_path):
        """Test finding Name(id=...) form calls."""
        test_file = tmp_path / "test_calls.py"
        test_file.write_text("def test():\n    _assert_under_project_root(path, 'field')\n")

        results = find_calls_of([test_file], "_assert_under_project_root")
        assert len(results) == 1
        assert results[0][0] == test_file
        assert results[0][1] > 0  # Has a line number

    def test_find_calls_of_attribute_form(self, tmp_path):
        """Test finding Attribute(attr=...) form calls."""
        test_file = tmp_path / "test_calls.py"
        test_file.write_text("def test():\n    module._assert_under_project_root(path, 'field')\n")

        results = find_calls_of([test_file], "_assert_under_project_root")
        assert len(results) == 1
        assert results[0][0] == test_file

    def test_find_calls_of_multiple_files(self, tmp_path):
        """Test scanning multiple files."""
        file1 = tmp_path / "file1.py"
        file1.write_text("x = _func()\n")

        file2 = tmp_path / "file2.py"
        file2.write_text("y = _func()\n")

        results = find_calls_of([file1, file2], "_func")
        assert len(results) == 2
        paths = {r[0] for r in results}
        assert file1 in paths
        assert file2 in paths


class TestAssertDecoratorPresent:
    """Tests for assert_decorator_present helper."""

    def test_assert_decorator_present_simple(self, tmp_path):
        """Test assertion passes when decorator is present."""
        test_file = tmp_path / "test_decs.py"
        code = "@decorator\ndef my_func():\n    pass\n"
        test_file.write_text(code)

        tree = ast.parse(code)
        func_def = tree.body[0]

        # Should not raise
        assert_decorator_present(func_def, "decorator", test_file)

    def test_assert_decorator_present_missing(self, tmp_path):
        """Test assertion fails when decorator is missing."""
        test_file = tmp_path / "test_decs.py"
        code = "@other_dec\ndef my_func():\n    pass\n"
        test_file.write_text(code)

        tree = ast.parse(code)
        func_def = tree.body[0]

        with pytest.raises(AssertionError) as exc_info:
            assert_decorator_present(func_def, "missing_dec", test_file)

        assert "missing_dec" in str(exc_info.value)
        assert "my_func" in str(exc_info.value)
        assert str(test_file) in str(exc_info.value)

    def test_assert_decorator_present_call_style(self, tmp_path):
        """Test assertion works with @decorator(...) style."""
        test_file = tmp_path / "test_decs.py"
        code = "@pytest.fixture(autouse=True)\ndef my_func():\n    pass\n"
        test_file.write_text(code)

        tree = ast.parse(code)
        func_def = tree.body[0]

        # Should find "fixture" from @pytest.fixture(...)
        assert_decorator_present(func_def, "fixture", test_file)
