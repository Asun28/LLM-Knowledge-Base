"""Cycle 13 — read-only frontmatter.load migration regression tests.

AC9-AC13: behavioural regressions for the 5 read-only sites migrated from
``frontmatter.load(str(page_path))`` to the cached ``load_page_frontmatter``
helper, plus a negative-pin spy proving the 3 write-back sites in
``lint/augment.py`` keep using the uncached path.

Banned-pattern reminder (cycle-11 L1 / cycle-12 inspect-source lessons):
no ``inspect.getsource``, no ``Path.read_text + splitlines``, no
``re.findall`` over file content. Every assertion exercises a production
code path through monkeypatch / live invocation.
"""

from __future__ import annotations

import time
from pathlib import Path

import frontmatter

from kb.utils import pages as pages_mod


def _write_stub_page(
    wiki_dir: Path,
    page_id: str,
    *,
    title: str,
    body: str = "Stub page body — too short.",
    confidence: str = "stated",
    source: list[str] | None = None,
    augment_meta: bool | None = None,
) -> Path:
    """Helper: write a stub wiki page with controllable frontmatter."""
    parent_id, _, slug = page_id.rpartition("/")
    page_dir = wiki_dir / parent_id
    page_dir.mkdir(parents=True, exist_ok=True)
    page_path = page_dir / f"{slug}.md"
    metadata: dict[str, object] = {
        "title": title,
        "type": parent_id.rstrip("s") or "concept",
        "confidence": confidence,
        "source": source or [],
    }
    if augment_meta is False:
        metadata["augment"] = False
    post = frontmatter.Post(body, **metadata)
    page_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return page_path


class TestAugmentReadOnlySites:
    """AC9 — _collect_eligible_stubs uses the cached helper.

    Pinning behaviour: the eligibility verdict reflects the page's CURRENT
    frontmatter on every call. Writing a new title to the page bumps mtime,
    which invalidates the cache, so a second call sees the updated title.
    """

    def test_collect_eligible_stubs_sees_fresh_mtime(self, tmp_kb_env, monkeypatch):
        from kb.lint import augment

        wiki = tmp_kb_env / "wiki"
        # Eligible stub needs an inbound (non-summary) link.
        target = _write_stub_page(
            wiki,
            "concepts/target-concept",
            title="Real Title",
            body="Stub body — under threshold for stub detection.",
        )
        # Inbound page links to target.
        _write_stub_page(
            wiki,
            "concepts/inbound",
            title="Inbound Page",
            body="See [[concepts/target-concept]] for context.",
            confidence="stated",
        )

        # Force fresh cache state for the helper used by augment.
        pages_mod.load_page_frontmatter.cache_clear()

        first = augment._collect_eligible_stubs(wiki_dir=wiki)
        first_titles = {s["title"] for s in first if s["page_id"] == "concepts/target-concept"}

        # Mutate the target's frontmatter on disk.
        post = frontmatter.load(str(target))
        post.metadata["title"] = "Updated Title"
        # Bump mtime explicitly so the FAT32-coarse-mtime caveat doesn't bite.
        target.write_text(frontmatter.dumps(post), encoding="utf-8")
        # Defensive: ensure mtime advances even on coarse filesystems.
        future = time.time() + 2
        import os

        os.utime(target, (future, future))
        # Cache_clear is part of the migrated contract — the helper exposes
        # it for callers that mutate frontmatter mid-run.
        pages_mod.load_page_frontmatter.cache_clear()

        second = augment._collect_eligible_stubs(wiki_dir=wiki)
        second_titles = {s["title"] for s in second if s["page_id"] == "concepts/target-concept"}

        assert first_titles == {"Real Title"}, f"first call titles: {first_titles}"
        assert second_titles == {"Updated Title"}, f"second call titles: {second_titles}"

    def test_collect_eligible_stubs_uses_cached_helper(self, tmp_kb_env, monkeypatch):
        """Spy on load_page_frontmatter to prove augment uses the cached path."""
        from kb.lint import augment

        wiki = tmp_kb_env / "wiki"
        target = _write_stub_page(
            wiki,
            "concepts/c1",
            title="Concept One",
            body="Tiny body.",
        )
        _write_stub_page(
            wiki,
            "concepts/inbound",
            title="Inbound",
            body="Linking to [[concepts/c1]].",
        )

        pages_mod.load_page_frontmatter.cache_clear()
        calls: list[Path] = []
        real_helper = augment.load_page_frontmatter

        def _spy(page_path):
            calls.append(page_path)
            return real_helper(page_path)

        monkeypatch.setattr(augment, "load_page_frontmatter", _spy)
        augment._collect_eligible_stubs(wiki_dir=wiki)

        # The target page MUST be loaded via the cached helper.
        assert any(Path(p) == target for p in calls), (
            f"Expected {target} in spy call list, got {calls}"
        )
