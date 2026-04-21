"""Cycle 19 AC1-AC7/AC20 — inject_wikilinks_batch.

Replaces N separate inject_wikilinks calls with one batch pass that scans each
existing wiki page AT MOST ONCE (per chunk). Under per-page lock the winner
is re-derived from FRESH body content (AC1b — pre-lock scan is candidate-
gathering only).

Test strategy mirrors cycle-18 linker tests: spy on file_lock + Path.read_text
to count interactions; cycle-11 L1 vacuous-gate revert checks confirm test
divergence is real (reverting to per-target inject_wikilinks would fail T-2/T-4).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


def _write_page(page_path: Path, title: str, body: str) -> None:
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        f"---\ntitle: {title}\ntype: concept\nsource: []\n---\n\n{body}\n",
        encoding="utf-8",
    )


# ────────────────────────────────────────────────────────────────────────────
# AC1 — basic batch with two new titles to disjoint pages
# ────────────────────────────────────────────────────────────────────────────


def test_two_new_titles_to_disjoint_pages(tmp_wiki: Path) -> None:
    """T-1 — Batch injects wikilinks for both new titles to disjoint matched pages."""
    from kb.compile import linker  # noqa: PLC0415

    _write_page(tmp_wiki / "entities" / "alice.md", "Alice", "Alice mentions RAG often.")
    _write_page(tmp_wiki / "entities" / "bob.md", "Bob", "Bob talks about Vectors.")
    # Targets:
    _write_page(tmp_wiki / "concepts" / "rag.md", "RAG", "Target body.")
    _write_page(tmp_wiki / "concepts" / "vectors.md", "Vectors", "Target body.")

    new_pages = [("RAG", "concepts/rag"), ("Vectors", "concepts/vectors")]
    result = linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    assert "concepts/rag" in result
    assert "concepts/vectors" in result
    assert "entities/alice" in result["concepts/rag"]
    assert "entities/bob" in result["concepts/vectors"]


# ────────────────────────────────────────────────────────────────────────────
# AC1b — under-lock re-derivation
# ────────────────────────────────────────────────────────────────────────────


def test_under_lock_rederive_picks_fresh_winner(tmp_wiki: Path, monkeypatch) -> None:
    """T-1b — Pre-lock candidate set is filtered against fresh body under lock.

    Snapshot says pages mentions both Alice and Bob; under the lock, the body
    is mutated to remove Alice. Batch must pick Bob from fresh body, not Alice
    from snapshot.
    """
    from kb.compile import linker  # noqa: PLC0415

    page_path = tmp_wiki / "entities" / "host.md"
    _write_page(page_path, "Host", "Host mentions Alice and Bob.")
    _write_page(tmp_wiki / "concepts" / "alice.md", "Alice", "Target body.")
    _write_page(tmp_wiki / "concepts" / "bob.md", "Bob", "Target body.")

    new_pages = [("Alice", "concepts/alice"), ("Bob", "concepts/bob")]
    # Mutate fresh body between snapshot and lock acquisition by rewriting the page
    # via a spy on file_lock that runs the mutation BEFORE yielding.
    real_file_lock = linker.file_lock
    mutated = {"done": False}

    @contextmanager
    def mutating_lock(path: Path, timeout=None):
        if not mutated["done"] and path.name == "host.md":
            # Simulate a concurrent process that removed "Alice" from the body
            # between our snapshot read and our under-lock re-read.
            new_body = path.read_text(encoding="utf-8").replace("Alice and ", "")
            path.write_text(new_body, encoding="utf-8")
            mutated["done"] = True
        with real_file_lock(path, timeout=timeout):
            yield

    monkeypatch.setattr(linker, "file_lock", mutating_lock)

    result = linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    # Bob should win since Alice was removed from fresh body.
    assert "entities/host" in result.get("concepts/bob", []), (
        f"Expected fresh-body winner Bob; got result={result}"
    )
    assert "entities/host" not in result.get("concepts/alice", []), (
        "Snapshot winner Alice should NOT be injected after fresh body removed it"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC2 — read budget (≤ U + 2M)
# ────────────────────────────────────────────────────────────────────────────


def test_read_budget_bounded(tmp_wiki: Path, monkeypatch) -> None:
    """T-2 — Each page is read at most once for peek + once under lock if matched."""
    from kb.compile import linker  # noqa: PLC0415

    # Construct a tmp_wiki where exactly 2 of 5 pages match.
    _write_page(tmp_wiki / "entities" / "p1.md", "P1", "this page mentions Foo.")
    _write_page(tmp_wiki / "entities" / "p2.md", "P2", "this page mentions Foo too.")
    _write_page(tmp_wiki / "entities" / "p3.md", "P3", "no match here.")
    _write_page(tmp_wiki / "entities" / "p4.md", "P4", "no match either.")
    _write_page(tmp_wiki / "entities" / "p5.md", "P5", "still no match.")
    _write_page(tmp_wiki / "concepts" / "foo.md", "Foo", "Target.")

    real_read_text = Path.read_text
    read_count = {"n": 0}

    def counting_read_text(self, *args, **kwargs):
        # Only count reads of the entities/p*.md files, not the target.
        if "entities" in str(self):
            read_count["n"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    new_pages = [("Foo", "concepts/foo")]
    linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    # 5 pages, 2 matches: budget = 5 (peek) + 2 (under-lock re-read) = 7
    assert read_count["n"] <= 7, (
        f"Read budget exceeded: expected ≤ 7 (5 peek + 2 under-lock), got {read_count['n']}"
    )


# ────────────────────────────────────────────────────────────────────────────
# AC3 — at most one wikilink per page per batch
# ────────────────────────────────────────────────────────────────────────────


def test_at_most_one_wikilink_per_page(tmp_wiki: Path) -> None:
    """T-3 — Page mentioning A and B gets one injection (longest-title wins)."""
    from kb.compile import linker  # noqa: PLC0415

    _write_page(tmp_wiki / "entities" / "host.md", "Host", "Host mentions Alphabet and Sun.")
    _write_page(tmp_wiki / "concepts" / "alphabet.md", "Alphabet", "Target.")
    _write_page(tmp_wiki / "concepts" / "sun.md", "Sun", "Target.")

    # Both candidates; longest-title wins (Alphabet).
    result = linker.inject_wikilinks_batch(
        [("Alphabet", "concepts/alphabet"), ("Sun", "concepts/sun")],
        wiki_dir=tmp_wiki,
    )
    # host.md should appear in exactly one of the two target lists.
    in_alphabet = "entities/host" in result.get("concepts/alphabet", [])
    in_sun = "entities/host" in result.get("concepts/sun", [])
    assert in_alphabet ^ in_sun, f"Expected exactly one injection per page; got result={result}"
    # Longest-title-first tie-break → Alphabet wins.
    assert in_alphabet, "Longest-title-first tie-break should pick Alphabet"


# ────────────────────────────────────────────────────────────────────────────
# AC4 — chunk cap
# ────────────────────────────────────────────────────────────────────────────


def test_batch_processes_more_than_one_chunk(tmp_wiki: Path, monkeypatch) -> None:
    """T-4 — Batches longer than MAX_INJECT_TITLES_PER_BATCH split into chunks."""
    from kb.compile import linker  # noqa: PLC0415

    # Lower the chunk cap for this test so we don't have to seed 250 pages.
    monkeypatch.setattr(linker, "MAX_INJECT_TITLES_PER_BATCH", 3)

    _write_page(tmp_wiki / "entities" / "host.md", "Host", "mentions FooA FooB FooC FooD FooE.")
    for name in ("FooA", "FooB", "FooC", "FooD", "FooE"):
        _write_page(tmp_wiki / "concepts" / f"{name.lower()}.md", name, "T.")

    new_pages = [(n, f"concepts/{n.lower()}") for n in ("FooA", "FooB", "FooC", "FooD", "FooE")]

    # Spy on _process_inject_chunk to count chunk invocations.
    real_chunk = linker._process_inject_chunk
    chunk_calls = {"n": 0}

    def spy_chunk(chunk, *args, **kwargs):
        chunk_calls["n"] += 1
        return real_chunk(chunk, *args, **kwargs)

    monkeypatch.setattr(linker, "_process_inject_chunk", spy_chunk)

    result = linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    # 5 titles, chunk size 3 → 2 chunks (3 + 2)
    assert chunk_calls["n"] == 2, (
        f"Expected 2 chunks for 5 titles at chunk-size 3, got {chunk_calls['n']}"
    )
    # All 5 targets should be present in result dict (initialised with empty lists).
    for n in ("FooA", "FooB", "FooC", "FooD", "FooE"):
        assert f"concepts/{n.lower()}" in result


# ────────────────────────────────────────────────────────────────────────────
# AC4b — per-title length cap
# ────────────────────────────────────────────────────────────────────────────


def test_overlength_title_skipped_with_warning(tmp_wiki: Path, caplog) -> None:
    """T-4b — Titles longer than MAX_INJECT_TITLE_LEN are skipped with log.warning."""
    from kb.compile import linker  # noqa: PLC0415

    _write_page(tmp_wiki / "entities" / "host.md", "Host", "mentions ShortTitle.")
    _write_page(tmp_wiki / "concepts" / "shorttitle.md", "ShortTitle", "Target.")

    long_title = "X" * 1000
    new_pages = [
        ("ShortTitle", "concepts/shorttitle"),
        (long_title, "concepts/longtitle"),
    ]
    import logging

    with caplog.at_level(logging.WARNING):
        result = linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    # Long title not in result dict (it was filtered before alternation)
    assert "concepts/longtitle" not in result
    # Short title processed
    assert "entities/host" in result.get("concepts/shorttitle", [])
    # Warning emitted for the overlength title
    assert any(
        "skipping overlength title" in r.message and "len=1000" in r.message for r in caplog.records
    ), f"Expected overlength warning; got records: {[r.message for r in caplog.records]}"


# ────────────────────────────────────────────────────────────────────────────
# AC5 — no-lock fast path for unmatched pages
# ────────────────────────────────────────────────────────────────────────────


def test_unmatched_pages_acquire_zero_locks(tmp_wiki: Path, monkeypatch) -> None:
    """T-5 — Pages with zero candidate matches acquire ZERO file_lock."""
    from kb.compile import linker  # noqa: PLC0415

    # 3 unmatched pages, 1 target.
    _write_page(tmp_wiki / "entities" / "p1.md", "P1", "no relevant text.")
    _write_page(tmp_wiki / "entities" / "p2.md", "P2", "still nothing.")
    _write_page(tmp_wiki / "entities" / "p3.md", "P3", "and nothing.")
    _write_page(tmp_wiki / "concepts" / "foo.md", "Foo", "Target.")

    lock_paths: list[Path] = []

    @contextmanager
    def spy_lock(path: Path, timeout=None):
        lock_paths.append(path)
        yield

    monkeypatch.setattr(linker, "file_lock", spy_lock)

    linker.inject_wikilinks_batch([("Foo", "concepts/foo")], wiki_dir=tmp_wiki)

    # No page matches; no locks acquired.
    assert lock_paths == [], f"Fast-path violated: locks acquired on unmatched pages: {lock_paths}"


# ────────────────────────────────────────────────────────────────────────────
# AC7 — pages= bundle skips disk walk
# ────────────────────────────────────────────────────────────────────────────


def test_pages_kwarg_skips_disk_walk(tmp_wiki: Path, monkeypatch) -> None:
    """T-7 — pages=[] returns {} with zero scan_wiki_pages calls."""
    from kb.compile import linker  # noqa: PLC0415

    scan_calls = {"n": 0}

    real_scan = linker.scan_wiki_pages

    def counting_scan(*args, **kwargs):
        scan_calls["n"] += 1
        return real_scan(*args, **kwargs)

    monkeypatch.setattr(linker, "scan_wiki_pages", counting_scan)

    # pages=[] explicitly provided → no scan
    result = linker.inject_wikilinks_batch([("Foo", "concepts/foo")], wiki_dir=tmp_wiki, pages=[])

    assert scan_calls["n"] == 0, (
        f"pages=[] should skip scan_wiki_pages, but called {scan_calls['n']} times"
    )
    # Result dict still includes the target with an empty list (no candidates → no injections).
    assert result.get("concepts/foo") == []


# ────────────────────────────────────────────────────────────────────────────
# AC6 — chunk-level failure granularity
# ────────────────────────────────────────────────────────────────────────────


def test_chunk_failure_does_not_block_remaining_chunks(tmp_wiki: Path, monkeypatch, caplog) -> None:
    """T-6b — One chunk failure logs warning and continues with remaining chunks."""
    from kb.compile import linker  # noqa: PLC0415

    monkeypatch.setattr(linker, "MAX_INJECT_TITLES_PER_BATCH", 2)

    _write_page(tmp_wiki / "entities" / "host.md", "Host", "mentions Foo Bar Baz Qux.")
    for name in ("Foo", "Bar", "Baz", "Qux"):
        _write_page(tmp_wiki / "concepts" / f"{name.lower()}.md", name, "T.")

    new_pages = [(n, f"concepts/{n.lower()}") for n in ("Foo", "Bar", "Baz", "Qux")]

    # Make chunk #0 raise; chunk #1 should still process.
    real_chunk = linker._process_inject_chunk
    call_no = {"n": 0}

    def failing_chunk(chunk, *args, **kwargs):
        call_no["n"] += 1
        if call_no["n"] == 1:
            raise RuntimeError("simulated chunk failure")
        return real_chunk(chunk, *args, **kwargs)

    monkeypatch.setattr(linker, "_process_inject_chunk", failing_chunk)

    import logging

    with caplog.at_level(logging.WARNING):
        result = linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    # Chunk 1 (Foo, Bar) failed; chunk 2 (Baz, Qux) processed → result has Baz or Qux.
    assert any(result.get(f"concepts/{n.lower()}") for n in ("Baz", "Qux")), (
        f"Expected at least one inject from chunk 2; got result={result}"
    )
    # Warning for the failed chunk
    assert any("chunk 1/2 failed" in r.message for r in caplog.records), (
        f"Expected chunk-failure warning; got records: {[r.message for r in caplog.records]}"
    )


# ────────────────────────────────────────────────────────────────────────────
# T2 (cycle 19 plan-gate amendment) — null-byte title sanitization
# ────────────────────────────────────────────────────────────────────────────


def test_null_byte_title_sanitized(tmp_wiki: Path) -> None:
    """T-1c — Title containing \\x00 is stripped at entry; injection uses sanitized form."""
    from kb.compile import linker  # noqa: PLC0415

    # Target "AB" exists; the malicious title "A\x00deadbeef\x00B" sanitizes to "AdeadbeefB".
    _write_page(tmp_wiki / "entities" / "host.md", "Host", "mentions AdeadbeefB literally.")
    _write_page(tmp_wiki / "concepts" / "ab.md", "AdeadbeefB", "Target.")

    new_pages = [("A\x00deadbeef\x00B", "concepts/ab")]
    result = linker.inject_wikilinks_batch(new_pages, wiki_dir=tmp_wiki)

    # Sanitized title should match "AdeadbeefB" in the body.
    assert "entities/host" in result.get("concepts/ab", []), (
        f"Sanitized title should match; got {result}"
    )
    # Confirm the wikilink in the rewritten body uses the sanitized target_pid.
    new_body = (tmp_wiki / "entities" / "host.md").read_text(encoding="utf-8")
    assert "[[concepts/ab|AdeadbeefB]]" in new_body, (
        f"Expected sanitized wikilink; body = {new_body!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Cycle-11 L1 vacuous-gate revert checks
# ────────────────────────────────────────────────────────────────────────────


def test_revert_to_per_target_inject_would_inflate_read_count(tmp_wiki: Path, monkeypatch) -> None:
    """Revert-check: per-target inject_wikilinks calls produce ≥ 2× the batch budget.

    This proves T-2's read-budget assertion is non-vacuous: reverting the batch
    helper to per-target calls would fail it.
    """
    from kb.compile import linker  # noqa: PLC0415

    # Same fixture as test_read_budget_bounded.
    _write_page(tmp_wiki / "entities" / "p1.md", "P1", "mentions Foo.")
    _write_page(tmp_wiki / "entities" / "p2.md", "P2", "mentions Foo.")
    _write_page(tmp_wiki / "entities" / "p3.md", "P3", "no match.")
    _write_page(tmp_wiki / "entities" / "p4.md", "P4", "no match.")
    _write_page(tmp_wiki / "entities" / "p5.md", "P5", "no match.")
    _write_page(tmp_wiki / "concepts" / "foo.md", "Foo", "T.")
    _write_page(tmp_wiki / "concepts" / "bar.md", "Bar", "T.")
    _write_page(tmp_wiki / "concepts" / "baz.md", "Baz", "T.")

    real_read_text = Path.read_text
    read_count = {"n": 0}

    def counting_read_text(self, *args, **kwargs):
        if "entities" in str(self):
            read_count["n"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    # Per-target equivalent: 3 separate inject_wikilinks calls
    for title, pid in [("Foo", "concepts/foo"), ("Bar", "concepts/bar"), ("Baz", "concepts/baz")]:
        linker.inject_wikilinks(title, pid, wiki_dir=tmp_wiki)

    # Per-target: each call peeks all 5 pages. 5 × 3 = 15 minimum.
    # Some matches will trigger under-lock re-reads → ≥ 17.
    assert read_count["n"] >= 14, (
        f"Per-target reverted call should produce ≥ 14 reads; got {read_count['n']} — "
        f"vacuous-gate broken."
    )
