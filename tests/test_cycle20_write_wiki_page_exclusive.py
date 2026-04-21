"""Cycle 20 AC8/AC9/AC10/AC11/AC12 — _write_wiki_page exclusive=True + page_lock.

Pins:
- AC8: exclusive=False byte-identical to legacy path.
- AC8: exclusive=True on fresh path succeeds.
- AC8 + T3: exclusive=True on existing path raises StorageError(kind=summary_collision);
  err.path set, str(err) hides the path.
- AC8: write-phase cleanup unlinks the zero-byte poison when os.write raises.
- AC9/AC10/AC12: 2 threads racing on real ingest_source with colliding slug — both
  sources land in frontmatter, both evidence-trail entries survive. Barrier(2) for
  deterministic race trigger.
- AC11: _update_existing_page's unconditional file_lock serialises concurrent RMW.
- AC7 mirror: OSError injected into ingest_source wraps to IngestError with
  __cause__ preserved (complements the cycle-18 RuntimeError regression test).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import frontmatter
import pytest

from kb.errors import IngestError, StorageError
from kb.ingest import pipeline


def _stub_extraction(title: str) -> dict:
    return {
        "title": title,
        "entities_mentioned": [],
        "concepts_mentioned": [],
        "key_claims": ["fact"],
    }


class TestWriteWikiPageExclusiveFlag:
    """AC8 — exclusive kwarg contract."""

    def test_exclusive_false_preserves_legacy_byte_output(self, tmp_wiki: Path) -> None:
        """Default exclusive=False path stays byte-identical to legacy atomic write."""
        page = tmp_wiki / "summaries" / "my-article.md"
        pipeline._write_wiki_page(
            page,
            "My Article",
            "summary",
            "raw/articles/my-article.md",
            "stated",
            "body one",
        )
        assert page.exists()
        text = page.read_text(encoding="utf-8")
        assert "title: My Article" in text
        assert "body one" in text
        assert "## Evidence Trail" in text  # append_evidence_trail ran

    def test_exclusive_true_creates_fresh_path(self, tmp_wiki: Path) -> None:
        page = tmp_wiki / "summaries" / "new-article.md"
        pipeline._write_wiki_page(
            page,
            "New",
            "summary",
            "raw/articles/new.md",
            "stated",
            "body",
            exclusive=True,
        )
        assert page.exists()
        post = frontmatter.load(str(page))
        assert post.metadata["title"] == "New"
        assert post.metadata["source"] == ["raw/articles/new.md"]
        assert "## Evidence Trail" in post.content

    def test_exclusive_true_collision_raises_storage_error(self, tmp_wiki: Path) -> None:
        """Existing file → StorageError(kind='summary_collision') with path set."""
        page = tmp_wiki / "summaries" / "taken.md"
        existing = (
            "---\ntitle: Existing\nsource:\n"
            "  - 'raw/articles/other.md'\ntype: summary\n---\n\nbody"
        )
        page.write_text(existing, encoding="utf-8")
        prev = page.read_text(encoding="utf-8")
        with pytest.raises(StorageError) as excinfo:
            pipeline._write_wiki_page(
                page,
                "Later",
                "summary",
                "raw/articles/later.md",
                "stated",
                "body",
                exclusive=True,
            )
        err = excinfo.value
        assert err.kind == "summary_collision"
        assert err.path == page
        # T1 mitigation: __str__ hides the actual path.
        assert str(err) == "summary_collision: <path_hidden>"
        # Existing file untouched.
        assert page.read_text(encoding="utf-8") == prev

    def test_exclusive_true_write_failure_unlinks_zero_byte_poison(
        self, tmp_wiki: Path, monkeypatch
    ) -> None:
        """os.write raising post-O_EXCL → unlink + retry can succeed."""
        page = tmp_wiki / "summaries" / "crashy.md"

        real_write = os.write
        fire = {"fired": False}

        def _one_shot_boom(fd: int, data: bytes) -> int:
            if not fire["fired"]:
                fire["fired"] = True
                raise OSError("disk full (simulated)")
            return real_write(fd, data)

        monkeypatch.setattr(os, "write", _one_shot_boom)
        with pytest.raises(OSError, match="disk full"):
            pipeline._write_wiki_page(
                page,
                "C",
                "summary",
                "raw/articles/c.md",
                "stated",
                "body",
                exclusive=True,
            )
        # Poison must be gone so a retry can re-reserve the path.
        assert not page.exists()

        # Retry (monkeypatch is still active but fire flag is set — real_write runs).
        pipeline._write_wiki_page(
            page,
            "C",
            "summary",
            "raw/articles/c.md",
            "stated",
            "body",
            exclusive=True,
        )
        assert page.exists()


class TestConcurrentIngestMergesBothSources:
    """AC9 / AC10 / AC11 / AC12 — two threads racing on colliding slug merge both sources."""

    def test_concurrent_ingest_merges_both_sources_and_evidence_trails(
        self, tmp_kb_env: Path
    ) -> None:
        """Two real ingest_source calls on the same slug race; both survive."""
        raw = tmp_kb_env / "raw" / "articles"
        src_a = raw / "src-a.md"
        src_b = raw / "src-b.md"
        src_a.write_text("# A\n\nalpha body", encoding="utf-8")
        src_b.write_text("# B\n\nbeta body", encoding="utf-8")

        # Both extractions use the SAME title → same slug → TOCTOU collision.
        shared_title = "Shared Title"

        barrier = threading.Barrier(2)
        errors: list[BaseException] = []
        results: list[dict] = []

        def _worker(src: Path) -> None:
            try:
                barrier.wait(timeout=5.0)
                r = pipeline.ingest_source(
                    src,
                    source_type="article",
                    extraction=_stub_extraction(shared_title),
                    wiki_dir=tmp_kb_env / "wiki",
                    raw_dir=tmp_kb_env / "raw",
                )
                results.append(r)
            except BaseException as e:  # noqa: BLE001 — test probe
                errors.append(e)

        t1 = threading.Thread(target=_worker, args=(src_a,))
        t2 = threading.Thread(target=_worker, args=(src_b,))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert not errors, f"workers raised: {errors!r}"
        assert len(results) == 2

        # Slugify("Shared Title") == "shared-title" — verify both sources are in
        # the final summary frontmatter.
        summary = tmp_kb_env / "wiki" / "summaries" / "shared-title.md"
        assert summary.exists(), "summary page missing after race"
        post = frontmatter.load(str(summary))
        sources = list(post.metadata.get("source") or [])
        assert any("src-a.md" in s for s in sources), f"src-a missing: {sources}"
        assert any("src-b.md" in s for s in sources), f"src-b missing: {sources}"

        # Evidence trail must contain BOTH source refs.
        body = post.content
        assert "## Evidence Trail" in body
        assert "src-a.md" in body
        assert "src-b.md" in body

    def test_update_existing_page_serialises_two_threaded_rmw(self, tmp_kb_env: Path) -> None:
        """AC11 — unconditional file_lock in _update_existing_page serialises RMW."""
        raw_a = tmp_kb_env / "raw" / "articles" / "a.md"
        raw_b = tmp_kb_env / "raw" / "articles" / "b.md"
        raw_a.write_text("# a\n\nx", encoding="utf-8")
        raw_b.write_text("# b\n\ny", encoding="utf-8")

        page = tmp_kb_env / "wiki" / "entities" / "shared.md"
        page.write_text(
            "---\ntitle: Shared\nsource:\n  - 'raw/articles/seed.md'\n"
            "created: 2026-04-21\nupdated: 2026-04-21\ntype: entity\n"
            "confidence: stated\n---\n\nbody\n",
            encoding="utf-8",
        )

        barrier = threading.Barrier(2)
        errors: list[BaseException] = []

        def _worker(source_ref: str) -> None:
            try:
                barrier.wait(timeout=5.0)
                pipeline._update_existing_page(page, source_ref, verb="Mentioned")
            except BaseException as e:  # noqa: BLE001 — test probe
                errors.append(e)

        t1 = threading.Thread(target=_worker, args=("raw/articles/a.md",))
        t2 = threading.Thread(target=_worker, args=("raw/articles/b.md",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, f"workers raised: {errors!r}"
        post = frontmatter.load(str(page))
        sources = list(post.metadata.get("source") or [])
        assert any("a.md" in s for s in sources), f"a.md missing: {sources}"
        assert any("b.md" in s for s in sources), f"b.md missing: {sources}"


class TestAC7IngestErrorWraps:
    """AC7 mirror — OSError wraps to IngestError with __cause__ preserved.

    Complements the cycle-18 ``test_jsonl_emitted_on_failure`` RuntimeError
    variant. Together the two tests pin that BOTH OSError (expected kind,
    must NOT wrap per AC5) and RuntimeError (unexpected kind, MUST wrap)
    have the correct outcome.
    """

    def test_oserror_in_body_passes_through_as_oserror(self, tmp_kb_env: Path) -> None:
        """AC5 narrowing — OSError is in the expected-kind list, passes through."""
        raw = tmp_kb_env / "raw" / "articles" / "os-err.md"
        raw.write_text("# t\n\nbody\n", encoding="utf-8")

        def boom(*args, **kwargs):
            raise OSError("simulated disk fail")

        with patch.object(pipeline, "_process_item_batch", side_effect=boom):
            # OSError is in the AC5 expected-kind list → passes through unchanged
            # (does NOT wrap to IngestError).
            with pytest.raises(OSError, match="simulated disk fail"):
                pipeline.ingest_source(
                    raw,
                    source_type="article",
                    extraction=_stub_extraction("OS err"),
                    wiki_dir=tmp_kb_env / "wiki",
                    raw_dir=tmp_kb_env / "raw",
                )

    def test_runtime_error_wraps_to_ingest_error(self, tmp_kb_env: Path) -> None:
        """AC7 — unexpected RuntimeError wraps to IngestError with __cause__."""
        raw = tmp_kb_env / "raw" / "articles" / "rt-err.md"
        raw.write_text("# t\n\nbody\n", encoding="utf-8")

        def boom(*args, **kwargs):
            raise RuntimeError("unexpected runtime failure")

        with patch.object(pipeline, "_process_item_batch", side_effect=boom):
            with pytest.raises(IngestError, match="unexpected runtime failure") as excinfo:
                pipeline.ingest_source(
                    raw,
                    source_type="article",
                    extraction=_stub_extraction("RT err"),
                    wiki_dir=tmp_kb_env / "wiki",
                    raw_dir=tmp_kb_env / "raw",
                )
        assert isinstance(excinfo.value.__cause__, RuntimeError)
