"""Consolidated adversarial + defense-in-depth tests for Phase 4.11."""

from __future__ import annotations

import ast
import json

import pytest

from kb.query.formats import render_output
from kb.query.formats.chart import render_chart
from kb.query.formats.html import render_html
from kb.query.formats.jupyter import render_jupyter
from kb.query.formats.markdown import render_markdown
from kb.query.formats.marp import render_marp


@pytest.fixture
def xss_payload():
    return {
        "question": "<script>alert('xss')</script>",
        "answer": "<img src=x onerror=alert(1)>",
        "citations": [
            {"type": "wiki", "path": "concepts/rag", "context": "<b>ctx</b>"},
        ],
        "source_pages": ["concepts/rag"],
        "context_pages": [],
    }


def test_html_xss_payload_escaped(xss_payload):
    out = render_html(xss_payload)
    # Raw script tag absent
    assert "<script>alert" not in out
    # Raw img tag absent (escaped form is `&lt;img` — check the open bracket was escaped)
    assert "<img src=x onerror" not in out
    # Confirm escaped form present (defense-in-depth)
    assert "&lt;script&gt;" in out
    assert "&lt;img" in out


def test_markdown_xss_roundtrip(xss_payload):
    """Markdown stays verbatim but YAML frontmatter must remain parseable."""
    import yaml

    out = render_markdown(xss_payload)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm["query"] == xss_payload["question"]


def test_marp_xss_in_frontmatter(xss_payload):
    import yaml

    out = render_marp(xss_payload)
    parts = out.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    assert fm.get("kb_query") == xss_payload["question"]


def test_chart_script_injection_safe():
    """Hostile question + page ID must not appear in Python source; script stays parseable."""
    hostile = {
        "question": '"""; import os; os.system("rm -rf /"); """',
        "answer": "ok",
        "citations": [],
        "source_pages": ["concepts/'); import os; x = ('"],
        "context_pages": [],
    }
    script, json_data = render_chart(hostile)
    ast.parse(script)  # valid Python
    data = json.loads(json_data)
    assert data["question"] == hostile["question"]
    assert data["source_pages"][0]["id"] == hostile["source_pages"][0]
    # Hostile payloads MUST NOT appear in the script source
    assert 'os.system("rm -rf /")' not in script
    assert "os.system('pwn')" not in script


def test_jupyter_not_trusted():
    sample = {
        "question": "q",
        "answer": "a",
        "citations": [],
        "source_pages": [],
        "context_pages": [],
    }
    out = render_jupyter(sample)
    nb = json.loads(out)
    assert nb["metadata"].get("trusted") is not True


def test_load_all_pages_excludes_outputs_dir(tmp_project):
    """Defense-in-depth (opus approval condition #4): even if outputs/ is
    placed adjacent to wiki/, load_all_pages must not surface its files."""
    from kb.utils.pages import load_all_pages

    wiki_dir = tmp_project / "wiki"
    outputs_dir = tmp_project / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    # Plant a file that looks like a wiki page inside outputs/
    (outputs_dir / "malicious.md").write_text(
        "---\ntitle: Malicious\ntype: concept\nconfidence: stated\n"
        "created: 2026-04-14\nupdated: 2026-04-14\n---\n\nBad content.\n",
        encoding="utf-8",
    )

    pages = load_all_pages(wiki_dir)
    for p in pages:
        assert "outputs" not in p.get("id", "")
        assert "malicious" not in p.get("id", "")


def test_windows_reserved_name_question_safe(monkeypatch, tmp_path):
    """Questions containing Windows-reserved names must produce writable files."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    for name in ("What is NUL?", "Tell me about CON.", "PRN details"):
        result = {
            "question": name,
            "answer": "ok",
            "citations": [],
            "source_pages": [],
            "context_pages": [],
        }
        path = render_output("markdown", result)
        assert path.exists()
        assert "ok" in path.read_text(encoding="utf-8")


def test_windows_reserved_bare_name_disambiguated(monkeypatch, tmp_path):
    """A question that slugifies to a bare reserved name gets _0 suffix."""
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = {
        "question": "NUL",
        "answer": "ok",
        "citations": [],
        "source_pages": [],
        "context_pages": [],
    }
    path = render_output("markdown", result)
    assert path.exists()
    assert "nul_0" in path.name


def test_empty_question_slug_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    result = {"question": "???", "answer": "a", "citations": [], "source_pages": []}
    path = render_output("markdown", result)
    assert "untitled" in path.name


def test_oversize_answer_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr("kb.query.formats.common.OUTPUTS_DIR", tmp_path / "outputs")
    oversize = {
        "question": "q",
        "answer": "x" * (500_001),
        "citations": [],
        "source_pages": [],
    }
    with pytest.raises(ValueError, match="MAX_OUTPUT_CHARS"):
        render_output("markdown", oversize)


def test_html_ampersand_escaped():
    """Ampersand in citation path escapes inside href and anchor text."""
    hostile = {
        "question": "q",
        "answer": "a",
        "citations": [{"type": "wiki", "path": "concepts/foo&bar", "context": "x"}],
        "source_pages": [],
        "context_pages": [],
    }
    out = render_html(hostile)
    assert "foo&amp;bar" in out
    assert "foo&bar<" not in out  # no raw ampersand followed by <


def test_marp_fence_preservation_with_xss_inside():
    """A code fence containing HTML-looking payload must not be split."""
    from kb.query.formats.marp import _split_into_slides

    text = "Before.\n\n```\n<script>alert(1)</script>\n\npayload\n```\n\nAfter."
    slides = _split_into_slides(text, max_chars=50)
    # The fenced block stays intact on one slide
    fenced = [s for s in slides if "<script>" in s]
    assert len(fenced) == 1
    # fence opens and closes on the same slide
    assert fenced[0].count("```") == 2
