"""Tests for Phase 4 compile/ fixes."""

from __future__ import annotations


def test_code_mask_handles_tilde_fences():
    """~~~-fenced code blocks must be masked so wikilink injection cannot fire inside."""
    from kb.compile.linker import _CODE_MASK_RE

    text = "~~~python\nfoo_entity()\n~~~"
    masked = _CODE_MASK_RE.sub("MASKED", text)
    assert "foo_entity" not in masked, f"Expected masked but got: {masked!r}"


def test_template_hashes_skips_backup_files(tmp_path, monkeypatch):
    """Editor backup YAML files (~foo.yaml, .hidden.yaml) must not be treated as templates."""
    from kb.compile import compiler as _c

    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "article.yaml").write_text("extract: []\n", encoding="utf-8")
    (tdir / "~article.yaml").write_text("bogus: true\n", encoding="utf-8")
    (tdir / ".hidden.yaml").write_text("bogus: true\n", encoding="utf-8")

    monkeypatch.setattr(_c, "TEMPLATES_DIR", tdir)
    # Clear any LRU cache if _template_hashes is cached
    if hasattr(_c._template_hashes, "cache_clear"):
        _c._template_hashes.cache_clear()
    hashes = _c._template_hashes()
    assert set(hashes.keys()) == {"_template/article"}, (
        f"Expected only '_template/article', got {set(hashes.keys())}"
    )


def test_inject_wikilinks_smoke(tmp_wiki):
    """Basic smoke test: wikilink injection still works after refactor."""
    from kb.compile.linker import inject_wikilinks

    # Create a page that mentions "Python" in plain text
    page = tmp_wiki / "concepts" / "general.md"
    page.write_text(
        "---\ntitle: General\n---\nThis is about Python programming.\n",
        encoding="utf-8",
    )
    # Create the target page so it exists in the wiki
    target = tmp_wiki / "entities" / "python.md"
    target.write_text("---\ntitle: Python\n---\nThe Python language.\n", encoding="utf-8")

    updated = inject_wikilinks("Python", "entities/python", wiki_dir=tmp_wiki)
    assert isinstance(updated, list)
    # general.md should have been updated with a wikilink
    assert any("general" in pid for pid in updated)


def test_tilde_fence_not_injected(tmp_wiki):
    """Wikilink injection must not fire inside ~~~-fenced code blocks."""
    from kb.compile.linker import inject_wikilinks

    # Content with entity mention ONLY inside a ~~~ fence
    page = tmp_wiki / "concepts" / "codepage.md"
    page.write_text(
        "---\ntitle: Code Page\n---\nSome text.\n\n~~~python\nTransformer()\n~~~\n",
        encoding="utf-8",
    )
    target = tmp_wiki / "entities" / "transformer.md"
    target.write_text("---\ntitle: Transformer\n---\nThe Transformer.\n", encoding="utf-8")

    updated = inject_wikilinks("Transformer", "entities/transformer", wiki_dir=tmp_wiki)
    # codepage.md should NOT have been updated (mention is inside code fence)
    assert not any("codepage" in pid for pid in updated)
    # Verify file unchanged
    content = page.read_text(encoding="utf-8")
    assert "[[entities/transformer" not in content
