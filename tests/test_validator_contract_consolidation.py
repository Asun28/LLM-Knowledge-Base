"""AC23 — validator contract consolidation regression test.

Ensures the three historical validator sites were properly migrated to
_assert_under_project_root per AC9.
"""

from pathlib import Path


def test_three_historical_sites_present() -> None:
    """C8 — Assert three historical validators migrated to _assert_under_project_root."""
    # Simple text-based grep to verify migrations
    app_py = Path("src/kb/mcp/app.py")
    compiler_py = Path("src/kb/compile/compiler.py")
    
    app_content = app_py.read_text()
    compiler_content = compiler_py.read_text()
    
    # Check for the migrated calls in the source code
    assert "_assert_under_project_root" in app_content, \
        "Expected _assert_under_project_root calls in mcp/app.py"
    assert "_assert_under_project_root" in compiler_content, \
        "Expected _assert_under_project_root calls in compile/compiler.py"
    
    # Count the calls (at least 2 in app.py from two different functions)
    app_count = app_content.count('_assert_under_project_root(')
    compiler_count = compiler_content.count('_assert_under_project_root(')
    
    assert app_count >= 2, (
        f"Expected at least 2 _assert_under_project_root calls in app.py "
        f"(_validate_wiki_dir + _validate_page_id), found {app_count}"
    )
    assert compiler_count >= 1, (
        f"Expected at least 1 _assert_under_project_root call in compiler.py "
        f"(_validate_path_under_project_root), found {compiler_count}"
    )
    
    # Total should be at least 3
    total_count = app_count + compiler_count
    assert total_count >= 3, (
        f"Expected at least 3 total _assert_under_project_root calls, found {total_count}"
    )
