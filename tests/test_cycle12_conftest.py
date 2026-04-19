"""Cycle 12 coverage for temporary KB environment isolation."""

from pathlib import Path


def _is_under(path: Path, base: Path) -> bool:
    return path.resolve().is_relative_to(base.resolve())


def test_tmp_kb_env_rebinds_preimported_config_consumers(request):
    import kb.capture as capture
    import kb.config as config
    import kb.mcp.browse as browse
    import kb.mcp.core as core

    original_source_keys = tuple(config.SOURCE_TYPE_DIRS)

    project = request.getfixturevalue("tmp_kb_env")
    raw = project / "raw"

    for module in (config, core, browse, capture):
        assert _is_under(module.PROJECT_ROOT, project)

    for module in (config, core, browse):
        assert _is_under(module.RAW_DIR, project)

    for module in (config, browse):
        assert _is_under(module.WIKI_DIR, project)

    assert _is_under(config.CAPTURES_DIR, project)
    assert _is_under(capture.CAPTURES_DIR, project)

    assert tuple(config.SOURCE_TYPE_DIRS) == original_source_keys
    assert tuple(core.SOURCE_TYPE_DIRS) == original_source_keys
    for source_dir in config.SOURCE_TYPE_DIRS.values():
        assert _is_under(source_dir, raw)
    for source_dir in core.SOURCE_TYPE_DIRS.values():
        assert _is_under(source_dir, raw)

    assert _is_under(capture._CAPTURES_DIR_RESOLVED, project)
    assert _is_under(capture._captures_resolved, project)
    assert _is_under(capture._project_resolved, project)


def test_tmp_kb_env_is_not_autouse(tmp_project):
    import kb.config as config

    assert config.PROJECT_ROOT != tmp_project
    assert config.PROJECT_ROOT == Path(__file__).resolve().parents[1]
