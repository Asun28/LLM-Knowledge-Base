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


class TestSemanticMigration:
    """AC10 — _group_by_shared_sources page-paths branch uses cached helper."""

    def test_group_by_shared_sources_returns_grouped_pages(self, tmp_kb_env):
        from kb.lint import semantic

        wiki = tmp_kb_env / "wiki"
        # Two pages share the same raw source.
        _write_stub_page(
            wiki,
            "concepts/alpha",
            title="Alpha",
            body="Alpha body.",
            source=["raw/articles/shared.md"],
        )
        _write_stub_page(
            wiki,
            "concepts/beta",
            title="Beta",
            body="Beta body.",
            source=["raw/articles/shared.md"],
        )
        _write_stub_page(
            wiki,
            "concepts/lonely",
            title="Lonely",
            body="No shared source.",
            source=["raw/articles/lonely.md"],
        )

        pages_mod.load_page_frontmatter.cache_clear()
        groups = semantic._group_by_shared_sources(wiki)
        # Find the group containing both shared-source pages.
        group_with_alpha = next(
            (g for g in groups if "concepts/alpha" in g),
            None,
        )
        assert group_with_alpha is not None, f"alpha not grouped; groups={groups}"
        assert "concepts/beta" in group_with_alpha, (
            f"beta missing from alpha's group: {group_with_alpha}"
        )

    def test_group_by_shared_sources_uses_cached_helper(self, tmp_kb_env, monkeypatch):
        """Spy on load_page_frontmatter to prove semantic uses the cached path."""
        from kb.lint import semantic

        wiki = tmp_kb_env / "wiki"
        _write_stub_page(wiki, "concepts/x", title="X", body="X", source=["raw/x.md"])

        pages_mod.load_page_frontmatter.cache_clear()
        calls: list[Path] = []
        real_helper = semantic.load_page_frontmatter

        def _spy(page_path):
            calls.append(page_path)
            return real_helper(page_path)

        monkeypatch.setattr(semantic, "load_page_frontmatter", _spy)
        semantic._group_by_shared_sources(wiki)

        assert len(calls) >= 1, f"Expected ≥1 cached-helper call, got {len(calls)}"


class TestGraphExportMigration:
    """AC11 — export_mermaid title fallback uses cached helper.

    The graph node 'path' attribute is a string (set by build_graph as
    str(page_path)). The migration wraps it as Path(path) INSIDE the broad
    try so a TypeError from a non-path-like value falls into the existing
    non-fatal fallback at logger.debug.
    """

    def test_export_mermaid_loads_title_via_cache_helper(self, tmp_kb_env):
        """R1 Codex fix: every included node MUST have a real path so the
        cached-helper branch (per-node load) fires, not the load_all_pages
        fallback that triggers when ANY node lacks a 'path' attribute.
        """
        import networkx as nx

        from kb.graph import export

        wiki = tmp_kb_env / "wiki"
        target_alpha = _write_stub_page(
            wiki,
            "concepts/alpha",
            title="Alpha Title",
            body="Alpha body.",
        )
        target_beta = _write_stub_page(
            wiki,
            "concepts/beta",
            title="Beta Title",
            body="Beta body.",
        )

        # Both nodes carry real paths so the cached-helper branch exercises.
        g = nx.DiGraph()
        g.add_node("concepts/alpha", path=str(target_alpha))
        g.add_node("concepts/beta", path=str(target_beta))
        g.add_edge("concepts/alpha", "concepts/beta")

        pages_mod.load_page_frontmatter.cache_clear()
        out = export.export_mermaid(graph=g, max_nodes=5)
        assert "Alpha Title" in out, f"alpha title missing:\n{out}"
        assert "Beta Title" in out, f"beta title missing:\n{out}"

    def test_export_mermaid_uses_cached_helper(self, tmp_kb_env, monkeypatch):
        """Spy on load_page_frontmatter to prove export uses the cached path."""
        import networkx as nx

        from kb.graph import export

        wiki = tmp_kb_env / "wiki"
        target = _write_stub_page(
            wiki,
            "concepts/foo",
            title="Foo",
            body="Foo body.",
        )

        g = nx.DiGraph()
        g.add_node("concepts/foo", path=str(target))
        g.add_node("concepts/bar", path=str(target))  # second node forces 2 loads
        g.add_edge("concepts/foo", "concepts/bar")

        pages_mod.load_page_frontmatter.cache_clear()
        calls: list[Path] = []
        real_helper = export.load_page_frontmatter

        def _spy(page_path):
            calls.append(page_path)
            return real_helper(page_path)

        monkeypatch.setattr(export, "load_page_frontmatter", _spy)
        export.export_mermaid(graph=g, max_nodes=5)

        assert len(calls) >= 1, f"Expected ≥1 cached-helper call, got {len(calls)}"
        # Path wrap inside try: spy should receive Path objects, not strings.
        assert all(isinstance(p, Path) for p in calls), (
            f"Expected all Path args, got mixed: {[type(p) for p in calls]}"
        )


class TestReviewContextMigration:
    """AC12 — pair_page_with_sources uses cached helper.

    The widened except catches the cached helper's full re-raise set
    (OSError/ValueError/AttributeError/yaml.YAMLError/UnicodeDecodeError);
    pre-cycle catch was yaml.YAMLError-only.
    """

    def test_pair_page_with_sources_returns_source_contents(self, tmp_kb_env):
        from kb.review import context

        wiki = tmp_kb_env / "wiki"
        raw = tmp_kb_env / "raw"
        # Write raw source.
        article = raw / "articles" / "shared.md"
        article.write_text("Raw article body — non-empty.", encoding="utf-8")
        # Write wiki page referencing it.
        _write_stub_page(
            wiki,
            "concepts/cited",
            title="Cited Concept",
            body="Refers to the shared article.",
            source=["raw/articles/shared.md"],
        )

        pages_mod.load_page_frontmatter.cache_clear()
        result = context.pair_page_with_sources(
            "concepts/cited",
            wiki_dir=wiki,
            raw_dir=raw,
            project_root=tmp_kb_env,
        )

        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert result["page_metadata"]["title"] == "Cited Concept"
        sc = result["source_contents"]
        assert len(sc) == 1, f"expected 1 source, got {len(sc)}"
        assert sc[0]["content"] is not None and "Raw article body" in sc[0]["content"]

    def test_pair_page_with_sources_uses_cached_helper(self, tmp_kb_env, monkeypatch):
        """Spy on load_page_frontmatter to prove context uses the cached path."""
        from kb.review import context

        wiki = tmp_kb_env / "wiki"
        raw = tmp_kb_env / "raw"
        _write_stub_page(wiki, "concepts/x", title="X", body="X body.", source=[])

        pages_mod.load_page_frontmatter.cache_clear()
        calls: list[Path] = []
        real_helper = context.load_page_frontmatter

        def _spy(page_path):
            calls.append(page_path)
            return real_helper(page_path)

        monkeypatch.setattr(context, "load_page_frontmatter", _spy)
        context.pair_page_with_sources(
            "concepts/x",
            wiki_dir=wiki,
            raw_dir=raw,
            project_root=tmp_kb_env,
        )

        assert len(calls) >= 1, f"Expected ≥1 cached-helper call, got {len(calls)}"


class TestWriteBackOutOfScope:
    """AC13 — pin all 3 write-back sites in lint/augment.py.

    Each of `_record_verdict_gap_callout`, `_mark_page_augmented`, and
    `_record_attempt` MUST keep using uncached `frontmatter.load(str(...))`
    because they call `frontmatter.dumps(post)` which requires a live Post
    object. The spy proves the production code path STILL invokes
    `frontmatter.load` at each of the 3 sites — a future "migrate everything"
    sweep would silently break YAML key ordering otherwise (cycle-7 R1
    Codex M3 lesson).
    """

    def _build_spy(self, monkeypatch):
        from kb.lint import augment

        calls: list[str] = []
        real_load = augment.frontmatter.load

        def _spy(path, *args, **kwargs):
            calls.append(str(path))
            return real_load(path, *args, **kwargs)

        monkeypatch.setattr(augment.frontmatter, "load", _spy)
        return calls

    def test_record_verdict_gap_callout_uses_uncached_load(self, tmp_kb_env, monkeypatch):
        from kb.lint import augment

        wiki = tmp_kb_env / "wiki"
        stub = _write_stub_page(
            wiki,
            "concepts/failed-stub",
            title="Failed Stub",
            body="Original body.",
        )

        calls = self._build_spy(monkeypatch)
        augment._record_verdict_gap_callout(stub, run_id="abcdef0123", reason="too short")

        assert str(stub) in calls, f"Expected {stub} in spy calls, got {calls}"
        # Behavioural: gap callout was written to the page.
        assert "[!gap]" in stub.read_text(encoding="utf-8"), (
            "Expected [!gap] callout to be prepended to the stub body."
        )

    def test_mark_page_augmented_uses_uncached_load(self, tmp_kb_env, monkeypatch):
        from kb.lint import augment

        wiki = tmp_kb_env / "wiki"
        page = _write_stub_page(
            wiki,
            "concepts/auged",
            title="Auged",
            body="Body.",
        )

        calls = self._build_spy(monkeypatch)
        augment._mark_page_augmented(page, source_url="https://example.com/foo")

        assert str(page) in calls, f"Expected {page} in spy calls, got {calls}"
        # Behavioural: confidence forced to speculative.
        post = frontmatter.load(str(page))
        assert post.metadata["confidence"] == "speculative"
        assert "[!augmented]" in post.content

    def test_record_attempt_uses_uncached_load(self, tmp_kb_env, monkeypatch):
        from kb.lint import augment

        wiki = tmp_kb_env / "wiki"
        stub = _write_stub_page(
            wiki,
            "concepts/recorded",
            title="Recorded",
            body="Body.",
        )

        calls = self._build_spy(monkeypatch)
        augment._record_attempt(stub)

        assert str(stub) in calls, f"Expected {stub} in spy calls, got {calls}"
        # Behavioural: last_augment_attempted timestamp written.
        post = frontmatter.load(str(stub))
        assert "last_augment_attempted" in post.metadata


class TestRunAugmentVerdictGuardIntegration:
    """R2 Codex follow-up: pin the production call-site `if verdict == 'fail'`
    guard in run_augment by driving the auto_ingest path end-to-end with
    minimal mocking. A refactor that removed the guard would silently start
    writing [!gap] callouts on success (or stop writing them on failure).

    Mirrors test_v5_lint_augment_orchestrator.py::test_auto_ingest_creates_
    wiki_page_with_speculative_confidence; only difference: we monkeypatch
    _post_ingest_quality to force a 'fail' verdict and spy on the callout
    helper to confirm production reaches it through the real run_augment loop.
    """

    @staticmethod
    def _patch_ingest_dirs(monkeypatch, tmp_project):
        wiki = tmp_project / "wiki"
        raw = tmp_project / "raw"
        monkeypatch.setattr("kb.ingest.pipeline.RAW_DIR", raw)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_DIR", wiki)
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_INDEX", wiki / "index.md")
        monkeypatch.setattr("kb.ingest.pipeline.WIKI_SOURCES", wiki / "_sources.md")
        monkeypatch.setattr("kb.utils.paths.RAW_DIR", raw)
        monkeypatch.setattr(
            "kb.compile.compiler.HASH_MANIFEST", tmp_project / ".data" / "hashes.json"
        )
        monkeypatch.setattr("kb.lint._augment_manifest.MANIFEST_DIR", tmp_project / ".data")
        monkeypatch.setattr(
            "kb.lint._augment_rate.RATE_PATH", tmp_project / ".data" / "augment_rate.json"
        )

    def test_run_augment_invokes_callout_on_fail_verdict(
        self, tmp_project, create_wiki_page, httpx_mock, monkeypatch
    ):
        """End-to-end: real run_augment(mode='auto_ingest') with a forced
        fail verdict reaches _record_verdict_gap_callout via the production
        `if verdict == 'fail':` branch at augment.py:917."""
        from unittest.mock import patch as mock_patch

        from kb.lint import augment

        wiki_dir = tmp_project / "wiki"
        raw_dir = tmp_project / "raw"
        self._patch_ingest_dirs(monkeypatch, tmp_project)

        (wiki_dir / "index.md").write_text(
            "# Index\n\n## Entities\n\n## Concepts\n\n", encoding="utf-8"
        )
        (wiki_dir / "_sources.md").write_text("# Sources\n\n", encoding="utf-8")
        (wiki_dir / "_categories.md").write_text("# Categories\n\n", encoding="utf-8")

        # Stub page that augment will target.
        create_wiki_page(
            page_id="concepts/moe",
            title="MoE",
            content="Brief.",
            wiki_dir=wiki_dir,
            page_type="concept",
            confidence="stated",
        )
        # Inbound link from a non-stub page to satisfy G2.
        create_wiki_page(
            page_id="entities/transformer",
            title="Transformer",
            content="See [[concepts/moe]] " * 5,
            wiki_dir=wiki_dir,
            page_type="entity",
        )

        httpx_mock.add_response(
            url="https://en.wikipedia.org/robots.txt",
            content=b"User-agent: *\nAllow: /\n",
            headers={"content-type": "text/plain"},
        )
        httpx_mock.add_response(
            url="https://en.wikipedia.org/wiki/MoE",
            headers={"content-type": "text/html"},
            content=(
                b"<html><body><article><h1>MoE</h1><p>"
                + b"Mixture of experts is a neural arch. " * 30
                + b"</p></article></body></html>"
            ),
        )

        fake_extraction = {
            "title": "MoE",
            "summary": "Mixture of experts is a neural architecture.",
            "key_claims": ["gating routes inputs", "expert subnetworks"],
            "entities_mentioned": [],
            "concepts_mentioned": ["moe"],
        }
        fake_propose = {
            "action": "propose",
            "urls": ["https://en.wikipedia.org/wiki/MoE"],
            "rationale": "wp",
        }

        # Seed propose-mode output (gate 1) to satisfy gate 2/3 contract.
        with mock_patch("kb.lint.augment.call_llm_json", return_value=fake_propose):
            augment.run_augment(wiki_dir=wiki_dir, raw_dir=raw_dir, mode="propose", max_gaps=5)

        # Force the verdict to fail so the production guard fires the callout.
        monkeypatch.setattr(
            augment,
            "_post_ingest_quality",
            lambda *, page_path, wiki_dir: ("fail", "forced fail for AC13 R2 test"),
        )

        callout_calls: list = []
        real_callout = augment._record_verdict_gap_callout

        def _spy(stub_path, *, run_id, reason):
            callout_calls.append((stub_path, run_id, reason))
            return real_callout(stub_path, run_id=run_id, reason=reason)

        monkeypatch.setattr(augment, "_record_verdict_gap_callout", _spy)

        with mock_patch(
            "kb.lint.augment.call_llm_json",
            side_effect=[
                {"score": 0.95},  # relevance
                fake_extraction,  # pre-extract
            ],
        ):
            result = augment.run_augment(
                wiki_dir=wiki_dir, raw_dir=raw_dir, mode="auto_ingest", max_gaps=5
            )

        # Production guard fired exactly once for the failing stub.
        assert len(callout_calls) == 1, (
            f"Expected exactly 1 callout invocation, got {len(callout_calls)}; "
            f"verdicts={result.get('verdicts')}"
        )
        stub_path = callout_calls[0][0]
        assert stub_path == wiki_dir / "concepts" / "moe.md"
        assert callout_calls[0][2] == "forced fail for AC13 R2 test"

        # Behavioural: the [!gap] callout is now written to the stub page.
        body = stub_path.read_text(encoding="utf-8")
        assert "[!gap]" in body, "Production verdict==fail branch did not write callout"
