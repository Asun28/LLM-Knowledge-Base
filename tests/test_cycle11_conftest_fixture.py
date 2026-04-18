"""Cycle 11 fixture coverage for tmp_project canonical wiki files."""

EXPECTED_INDEX = (
    "---\n"
    "title: Wiki Index\n"
    "source: []\n"
    "type: index\n"
    "---\n\n"
    "# Knowledge Base Index\n\n"
    "## Pages\n\n"
    "*No pages yet.*\n\n"
    "## Entities\n\n"
    "*No pages yet.*\n\n"
    "## Concepts\n\n"
    "*No pages yet.*\n\n"
    "## Comparisons\n\n"
    "*No pages yet.*\n\n"
    "## Summaries\n\n"
    "*No pages yet.*\n\n"
    "## Synthesis\n\n"
    "*No pages yet.*\n"
)

EXPECTED_SOURCES = "---\ntitle: Source Mapping\nsource: []\ntype: index\n---\n\n# Source Mapping\n"


def test_tmp_project_creates_canonical_index_sources_and_log(tmp_project):
    wiki = tmp_project / "wiki"

    assert (wiki / "index.md").read_text(encoding="utf-8") == EXPECTED_INDEX
    assert (wiki / "_sources.md").read_text(encoding="utf-8") == EXPECTED_SOURCES
    assert (wiki / "log.md").read_text(encoding="utf-8") == "# Wiki Log\n\n"
