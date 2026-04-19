def test_kb_mcp_package_exposes_main():
    from kb.mcp import main

    assert callable(main)


def test_kb_mcp_server_reexports_main_and_mcp():
    from kb.mcp import main as pkg_main
    from kb.mcp import mcp as pkg_mcp
    from kb.mcp_server import main as shim_main
    from kb.mcp_server import mcp as shim_mcp

    assert shim_main is pkg_main
    assert shim_mcp is pkg_mcp


def test_pyproject_has_kb_mcp_script_entry():
    import tomllib

    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    scripts = data.get("project", {}).get("scripts", {})
    assert scripts.get("kb-mcp") == "kb.mcp:main"
    assert scripts.get("kb") == "kb.cli:cli"
