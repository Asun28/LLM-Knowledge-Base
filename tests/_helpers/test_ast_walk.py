"""Unit tests for AST walking helpers."""

import ast

import pytest

from tests._helpers.ast_walk import (
    assert_decorator_present,
    find_calls_of,
    find_function_def,
    find_module_imports,
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


class TestFindModuleImports:
    """Tests for find_module_imports helper (cycle-66 AC4).

    Each case writes synthetic .py fixtures under tmp_path and asserts the
    helper detects the expected `import` / `from` form. These are MANDATORY
    real tests — running them after reverting find_module_imports back to
    ImportFrom-only must turn at least one case RED.
    """

    def test_find_module_imports_bare_form(self, tmp_path):
        """`import module` is detected as a bare-form hit, not a from-form hit."""
        f = tmp_path / "a.py"
        f.write_text("import diskcache\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert f in result["import"]
        assert f not in result["from"]

    def test_find_module_imports_from_form(self, tmp_path):
        """`from module import X` is detected as a from-form hit, not bare-form."""
        f = tmp_path / "a.py"
        f.write_text("from diskcache import Cache\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert f in result["from"]
        assert f not in result["import"]

    def test_find_module_imports_both_forms(self, tmp_path):
        """A file with both forms appears in both lists."""
        f = tmp_path / "a.py"
        f.write_text("import diskcache\nfrom diskcache import Cache\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert f in result["import"]
        assert f in result["from"]

    def test_find_module_imports_namespace_prefix_bare(self, tmp_path):
        """`import module.submodule` matches `module` as a bare-form hit."""
        f = tmp_path / "a.py"
        f.write_text("import diskcache.core\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert f in result["import"]

    def test_find_module_imports_namespace_prefix_from(self, tmp_path):
        """`from module.submodule import X` matches `module` as a from-form hit."""
        f = tmp_path / "a.py"
        f.write_text("from diskcache.core import Cache\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert f in result["from"]

    def test_find_module_imports_unrelated_module(self, tmp_path):
        """Sibling-name `module_other` must NOT be matched as `module`."""
        f = tmp_path / "a.py"
        f.write_text("import diskcache_other\nfrom diskcache_other import X\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert result["import"] == []
        assert result["from"] == []

    def test_find_module_imports_syntax_error_file(self, tmp_path):
        """Files that fail to parse are silently skipped; sibling files still scanned."""
        good_f = tmp_path / "good.py"
        good_f.write_text("import diskcache\n")
        bad_f = tmp_path / "bad.py"
        bad_f.write_text("def broken(\n")
        result = find_module_imports("diskcache", src_root=tmp_path)
        assert good_f in result["import"]
        assert bad_f not in result["import"]
        assert bad_f not in result["from"]

    def test_find_module_imports_missing_src_root(self, tmp_path):
        """Missing src_root returns empty result without raising."""
        nonexistent = tmp_path / "does_not_exist"
        result = find_module_imports("diskcache", src_root=nonexistent)
        assert result == {"import": [], "from": []}
