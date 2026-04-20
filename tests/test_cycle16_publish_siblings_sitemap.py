"""Cycle 16 AC20-AC22 — build_per_page_siblings + build_sitemap_xml.

Behavioural regressions covering T7 (XML escaping), T8 (relative POSIX),
T9 (sibling traversal), T10 (retracted cleanup on incremental).
"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from kb.compile import publish
from kb.compile.publish import build_per_page_siblings, build_sitemap_xml


def _write_page(
    wiki_dir: Path,
    page_id: str,
    *,
    belief_state: str = "",
    confidence: str = "stated",
    status: str = "",
    updated: str = "2026-04-01",
) -> Path:
    path = wiki_dir / f"{page_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        f'title: "{page_id}"',
        'source: ["raw/articles/x.md"]',
        "created: 2026-04-01",
        f"updated: {updated}",
        "type: concept",
        f"confidence: {confidence}",
    ]
    if belief_state:
        lines.append(f"belief_state: {belief_state}")
    if status:
        lines.append(f"status: {status}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {page_id}\n\nbody text for {page_id}.\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


class TestBuildPerPageSiblings:
    def test_happy_path_writes_txt_and_json(self, tmp_project) -> None:
        """AC20 — every kept page emits .txt + .json under pages/."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/rag")
        _write_page(wiki, "entities/openai")
        out_dir = tmp_project / "out"
        written = build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        assert (pages_dir / "concepts" / "rag.txt").exists()
        assert (pages_dir / "concepts" / "rag.json").exists()
        assert (pages_dir / "entities" / "openai.txt").exists()
        assert (pages_dir / "entities" / "openai.json").exists()
        # Written list contains both types.
        assert any(p.suffix == ".txt" for p in written)
        assert any(p.suffix == ".json" for p in written)

    def test_excludes_retracted(self, tmp_project) -> None:
        """T10 — retracted page does NOT appear in output."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/kept")
        _write_page(wiki, "concepts/bad", belief_state="retracted")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        assert (pages_dir / "concepts" / "kept.txt").exists()
        assert not (pages_dir / "concepts" / "bad.txt").exists()

    def test_excludes_speculative_confidence(self, tmp_project) -> None:
        """T10 — speculative pages excluded."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/spec", confidence="speculative")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        assert not (pages_dir / "concepts" / "spec.txt").exists()

    def test_cleanup_on_newly_retracted(self, tmp_project) -> None:
        """Q2/C3 — page flipping to retracted has its siblings unlinked on
        the next publish, even with incremental=True.
        """
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/will-retract")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        assert (pages_dir / "concepts" / "will-retract.txt").exists()

        # Flip to retracted.
        _write_page(wiki, "concepts/will-retract", belief_state="retracted")
        # Advance mtime so incremental-skip doesn't no-op.
        time.sleep(0.05)
        (wiki / "concepts/will-retract.md").touch()

        build_per_page_siblings(wiki, out_dir, incremental=True)
        assert not (pages_dir / "concepts" / "will-retract.txt").exists()
        assert not (pages_dir / "concepts" / "will-retract.json").exists()

    def test_incremental_skip_honoured(self, tmp_project, monkeypatch) -> None:
        """AC22 — incremental=True skips write when output is newer."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/a")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        first_mtime = (pages_dir / "concepts" / "a.txt").stat().st_mtime_ns

        # Second call — incremental should skip re-write.
        build_per_page_siblings(wiki, out_dir, incremental=True)
        second_mtime = (pages_dir / "concepts" / "a.txt").stat().st_mtime_ns
        # Mtime unchanged (no re-write).
        assert first_mtime == second_mtime

    def test_incremental_rewrites_on_page_content_update(self, tmp_project) -> None:
        """R1 Sonnet Major 3 / R2 N2 — file-mtime incremental skip must
        detect in-place page content updates even when the output
        DIRECTORY mtime has advanced past the page mtime.

        Bug being regressed: on NTFS/ext4 the directory mtime only updates
        on add/remove, but in test filesystems (or under filesystem noise
        / explicit `touch`) the dir mtime can drift above the newest page
        mtime. The OLD ``_publish_skip_if_unchanged(wiki_dir, pages_dir)``
        compared max page mtime to PAGES_DIR.stat().st_mtime_ns — if the
        dir mtime was newer, it incorrectly skipped even though a page
        body had changed.

        This test reproduces that exact divergence: advance pages_dir's
        mtime to STRICTLY GREATER than the updated page's mtime, leave
        the individual sibling file mtimes at T0 (older than the updated
        page), then run incremental. OLD logic (dir-mtime) would skip.
        NEW logic (min sibling-file mtime) rewrites because at least one
        sibling is older than the newest wiki page.
        """
        import os as _os
        import time as _time

        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/page-a")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        sibling_txt = pages_dir / "concepts" / "page-a.txt"
        first_content = sibling_txt.read_text(encoding="utf-8")
        sibling_mtime_ns = sibling_txt.stat().st_mtime_ns

        _time.sleep(0.05)
        # Update the page body in place.
        path = wiki / "concepts" / "page-a.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace("body text", "UPDATED body text"),
            encoding="utf-8",
        )
        stat = path.stat()
        _os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
        updated_page_mtime_ns = path.stat().st_mtime_ns

        # Force pages_dir mtime strictly greater than both the updated page
        # mtime AND the sibling file mtimes — simulating the dir-mtime
        # drift that fooled the old skip logic. Sibling files stay at T0.
        dir_mtime_target_ns = updated_page_mtime_ns + 50_000_000
        _os.utime(pages_dir, ns=(dir_mtime_target_ns, dir_mtime_target_ns))

        # Sanity — test preconditions for exercising the bug:
        assert pages_dir.stat().st_mtime_ns > updated_page_mtime_ns
        assert sibling_txt.stat().st_mtime_ns < updated_page_mtime_ns

        # Old dir-mtime logic: max_page_mtime (T1) <= dir_mtime (T2) → skip.
        # New file-mtime logic: min_sibling_mtime (T0) < max_page_mtime (T1) → rewrite.
        build_per_page_siblings(wiki, out_dir, incremental=True)
        second_content = sibling_txt.read_text(encoding="utf-8")
        assert "UPDATED body text" in second_content, (
            "incremental sibling publish failed to detect in-place page update; "
            "file-mtime skip contract is broken"
        )
        assert first_content != second_content
        # And the sibling mtime itself advanced (confirms a rewrite happened).
        assert sibling_txt.stat().st_mtime_ns > sibling_mtime_ns

    def test_subdir_page_id_writes_nested(self, tmp_project) -> None:
        """AC20 — page IDs with one-level subdir (e.g. concepts/foo) produce
        nested paths under pages/. Matches load_all_pages' flat-subdir contract.
        """
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/rag")
        _write_page(wiki, "entities/openai")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        base = (out_dir / "pages").resolve()
        assert (base / "concepts" / "rag.txt").exists()
        assert (base / "concepts" / "rag.json").exists()
        assert (base / "entities" / "openai.txt").exists()

    def test_json_is_sort_keys_deterministic(self, tmp_project) -> None:
        """R1 amendment — json output has sorted keys (deterministic bytes)."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/det")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        json_path = (out_dir / "pages").resolve() / "concepts" / "det.json"
        content = json_path.read_text(encoding="utf-8")
        # Re-dump parsed JSON with sort_keys and verify byte-identical match.
        data = json.loads(content)
        expected = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        assert content == expected

    def test_idempotent_bytes_on_repeat(self, tmp_project) -> None:
        """AC22 idempotency — two non-incremental runs produce identical bytes."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/idem")
        out_dir = tmp_project / "out"
        build_per_page_siblings(wiki, out_dir)
        first_txt = ((out_dir / "pages").resolve() / "concepts" / "idem.txt").read_text(
            encoding="utf-8"
        )
        first_json = ((out_dir / "pages").resolve() / "concepts" / "idem.json").read_text(
            encoding="utf-8"
        )
        build_per_page_siblings(wiki, out_dir)
        second_txt = ((out_dir / "pages").resolve() / "concepts" / "idem.txt").read_text(
            encoding="utf-8"
        )
        second_json = ((out_dir / "pages").resolve() / "concepts" / "idem.json").read_text(
            encoding="utf-8"
        )
        assert first_txt == second_txt
        assert first_json == second_json

    def test_rejects_sibling_prefix_directory(self, tmp_project, monkeypatch) -> None:
        """Step-11 N1 regression — containment uses path-component comparison,
        NOT string prefix. A sibling directory whose name starts with 'pages'
        (e.g. 'pages_evil') must NOT be treated as contained under 'pages/'.

        Direct test of _is_contained: even when resolved_target.startswith(pages/)
        in string form, path-component comparison correctly rejects.
        """
        from kb.compile.publish import _is_contained

        pages_base = tmp_project / "out" / "pages"
        pages_base.mkdir(parents=True, exist_ok=True)
        # Sibling directory with prefix-overlapping name.
        sibling = tmp_project / "out" / "pages_evil"
        sibling.mkdir(parents=True, exist_ok=True)
        malicious_target = sibling / "pwn.txt"
        # String-prefix check would return True; path-component check must return False.
        assert not _is_contained(malicious_target, pages_base)
        # And a legitimate target under pages_base DOES return True.
        legit = pages_base / "concepts" / "ok.txt"
        assert _is_contained(legit, pages_base)

    def test_rejects_traversal_page_id(self, tmp_project, monkeypatch) -> None:
        """T9 — containment check skips hostile page_ids."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/legit")
        out_dir = tmp_project / "out"

        # Force a synthetic page dict with an escaping id into _partition_pages.
        original_load = publish.load_all_pages

        def _inject(*a, **k):
            pages = list(original_load(*a, **k))
            pages.append(
                {
                    "id": "../escape",
                    "path": "/fake",
                    "title": "hostile",
                    "type": "concept",
                    "confidence": "stated",
                    "sources": [],
                    "created": "2026-04-01",
                    "updated": "2026-04-01",
                    "content": "pwned",
                    "status": "",
                    "belief_state": "",
                    "authored_by": "",
                }
            )
            return pages

        monkeypatch.setattr(publish, "load_all_pages", _inject)
        build_per_page_siblings(wiki, out_dir)
        pages_dir = (out_dir / "pages").resolve()
        # Legit page written; hostile NOT written anywhere.
        assert (pages_dir / "concepts" / "legit.txt").exists()
        assert not (pages_dir.parent / "escape.txt").exists()
        assert not (pages_dir.parent.parent / "escape.txt").exists()


class TestBuildSitemapXml:
    def test_happy_path_all_kept_pages(self, tmp_project) -> None:
        """AC21 — every kept page gets a <url> entry."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/a")
        _write_page(wiki, "entities/b")
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        parsed = ET.fromstring(body)
        # Namespace-aware: ignore the urlset namespace in tag search.
        urls = [el for el in parsed.iter() if el.tag.endswith("url")]
        assert len(urls) == 2

    def test_excludes_retracted_contradicted_speculative(self, tmp_project) -> None:
        """T10 — epistemic filter same as other Tier-1 builders."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/ok")
        _write_page(wiki, "concepts/ret", belief_state="retracted")
        _write_page(wiki, "concepts/spec", confidence="speculative")
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        assert "pages/concepts/ok.txt" in body
        assert "pages/concepts/ret.txt" not in body
        assert "pages/concepts/spec.txt" not in body

    def test_escapes_special_characters_in_title(self, tmp_project) -> None:
        """T7 — XML entities escaped by ET.SubElement.text."""
        wiki = tmp_project / "wiki"
        # Inject a page_id containing '&' would be filesystem-unsafe, but
        # we can verify via an UPDATED field that contains '&' (frontmatter
        # legal; filename not involved).
        path = wiki / "concepts/amp.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\n"
            'title: "amp"\n'
            'source: ["raw/articles/x.md"]\n'
            "created: 2026-04-01\n"
            'updated: "2026-04-01 & more"\n'
            "type: concept\n"
            "confidence: stated\n"
            "---\n\nbody.\n",
            encoding="utf-8",
        )
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        # Raw '&' must NOT appear as a bare char in content.
        # ET escapes to &amp; reliably.
        assert "&amp;" in body or "& more" not in body

    def test_urls_relative_posix(self, tmp_project) -> None:
        """T8 — no absolute paths / schemes in <loc> entries specifically.

        The sitemap.org schema namespace `http://www.sitemaps.org/...`
        legitimately appears in the xmlns attribute, so we check <loc>
        values directly rather than string-scanning the whole body.
        """
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/a")
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        parsed = ET.fromstring(body)
        locs = [el.text or "" for el in parsed.iter() if el.tag.endswith("loc")]
        assert locs, "sitemap must have at least one <loc> entry"
        for loc in locs:
            for bad in ("file:", "http:", "https:", ":\\", "..", "//"):
                assert bad not in loc, f"forbidden substring {bad!r} in <loc>={loc!r}"
            assert loc.startswith("pages/"), f"<loc>={loc!r} must start with pages/"

    def test_round_trips_xml(self, tmp_project) -> None:
        """T7 — output parses as valid XML (never corrupted by injection)."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/a")
        _write_page(wiki, "entities/b")
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        # Must not raise.
        parsed = ET.fromstring(body)
        assert parsed.tag.endswith("urlset")

    def test_incremental_skip_honoured(self, tmp_project) -> None:
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/a")
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        first_mtime = out.stat().st_mtime_ns

        build_sitemap_xml(wiki, out, incremental=True)
        second_mtime = out.stat().st_mtime_ns
        assert first_mtime == second_mtime

    def test_lastmod_when_present(self, tmp_project) -> None:
        """AC21 — <lastmod> included when updated frontmatter is non-empty."""
        wiki = tmp_project / "wiki"
        _write_page(wiki, "concepts/a", updated="2026-04-15")
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        assert "<lastmod>2026-04-15</lastmod>" in body

    def test_no_pages_empty_urlset(self, tmp_project) -> None:
        """Edge: empty wiki produces a valid empty <urlset>."""
        wiki = tmp_project / "wiki"
        out = tmp_project / "sitemap.xml"
        build_sitemap_xml(wiki, out)
        body = out.read_text(encoding="utf-8")
        parsed = ET.fromstring(body)
        urls = [el for el in parsed.iter() if el.tag.endswith("url")]
        assert urls == []
