"""Cycle 18 AC7/AC8 — inject_wikilinks per-page lock with TOCTOU re-read.

Threat T3: concurrent `ingest_source` calls injecting into the same target
page clobber each other. The fix acquires `file_lock(page_path)` around the
read+modify+write sequence. The pre-lock cheap read preserves the zero-lock
fast-path for pages that will NOT be modified (threat T8 perf guard).

Test strategy: call-order spies per cycle-17 L2 — do NOT simulate
concurrency. The locked-RMW invariant is testable by spying on the sequence
of read_text → lock_enter → read_text → atomic_text_write → lock_exit.
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


def test_inject_wikilinks_fast_path_no_lock_on_no_match(tmp_wiki: Path, monkeypatch) -> None:
    """AC7/AC8 — no-match page acquires ZERO locks (fast-path contract)."""
    from kb.compile import linker  # noqa: PLC0415

    target_title = "RAG"
    target_pid = "concepts/rag"
    _write_page(tmp_wiki / "concepts" / "rag.md", target_title, "Target body.")
    # No-match page: body does not contain the title pattern at all.
    _write_page(tmp_wiki / "entities" / "nomatch.md", "NoMatch", "body with no trigger words.")

    lock_calls: list[Path] = []

    @contextmanager
    def spy_file_lock(path: Path, timeout=None):
        lock_calls.append(path)
        yield

    monkeypatch.setattr(linker, "file_lock", spy_file_lock)

    updated = linker.inject_wikilinks(target_title, target_pid, wiki_dir=tmp_wiki)

    assert updated == [], f"Expected no updates on no-match page, got {updated}"
    assert lock_calls == [], (
        f"Fast-path violated: lock acquired {len(lock_calls)} time(s) on no-match page — "
        f"{lock_calls}"
    )


def test_inject_wikilinks_lock_acquired_on_match_page(tmp_wiki: Path, monkeypatch) -> None:
    """AC7/AC8 — match page acquires exactly one lock; no-match page acquires zero."""
    from kb.compile import linker  # noqa: PLC0415

    target_title = "RAG"
    target_pid = "concepts/rag"
    _write_page(tmp_wiki / "concepts" / "rag.md", target_title, "Target body.")
    _write_page(
        tmp_wiki / "entities" / "matchpage.md",
        "MatchPage",
        "This entity works with RAG techniques.",
    )
    _write_page(tmp_wiki / "entities" / "nomatch.md", "NoMatch", "body with no trigger words.")

    lock_calls: list[Path] = []

    @contextmanager
    def spy_file_lock(path: Path, timeout=None):
        lock_calls.append(path)
        yield

    monkeypatch.setattr(linker, "file_lock", spy_file_lock)

    updated = linker.inject_wikilinks(target_title, target_pid, wiki_dir=tmp_wiki)

    assert target_pid != "entities/matchpage"  # sanity
    assert "entities/matchpage" in updated, f"Expected match page in updated, got {updated}"
    assert len(lock_calls) == 1, (
        f"Expected exactly 1 lock on the match page, got {len(lock_calls)}: {lock_calls}"
    )
    assert lock_calls[0].name == "matchpage.md"


def test_inject_wikilinks_sequence_order(tmp_wiki: Path, monkeypatch) -> None:
    """AC7/AC8 — match page sequence: peek → lock_enter → lock_read → atomic_write → lock_exit."""
    from kb.compile import linker  # noqa: PLC0415

    target_title = "RAG"
    target_pid = "concepts/rag"
    _write_page(tmp_wiki / "concepts" / "rag.md", target_title, "Target body.")
    match_page = tmp_wiki / "entities" / "matchpage.md"
    _write_page(match_page, "MatchPage", "About RAG here.")

    events: list[str] = []

    @contextmanager
    def spy_file_lock(path: Path, timeout=None):
        if path == match_page:
            events.append("lock_enter")
        try:
            yield
        finally:
            if path == match_page:
                events.append("lock_exit")

    real_read_text = Path.read_text

    def spy_read_text(self, *a, **kw):
        if self == match_page:
            events.append("read_text")
        return real_read_text(self, *a, **kw)

    real_atomic_write = linker.atomic_text_write

    def spy_atomic_write(content, path):
        if path == match_page:
            events.append("atomic_write")
        return real_atomic_write(content, path)

    monkeypatch.setattr(linker, "file_lock", spy_file_lock)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(linker, "atomic_text_write", spy_atomic_write)

    linker.inject_wikilinks(target_title, target_pid, wiki_dir=tmp_wiki)

    # Expected sequence on the match page:
    #   peek_read (pre-lock) → lock_enter → lock_read → atomic_write → lock_exit
    # Assert each event is strictly after the preceding one.
    assert "read_text" in events and "lock_enter" in events, f"events: {events}"
    peek_idx = events.index("read_text")
    lock_enter_idx = events.index("lock_enter")
    assert peek_idx < lock_enter_idx, f"peek read must precede lock_enter; events: {events}"

    # Post-lock read is the SECOND read_text event on match_page.
    post_read_idx = events.index("read_text", peek_idx + 1)
    assert lock_enter_idx < post_read_idx, (
        f"Post-lock read must come after lock_enter; events: {events}"
    )

    atomic_idx = events.index("atomic_write")
    assert post_read_idx < atomic_idx, (
        f"atomic_write must come after post-lock read; events: {events}"
    )

    lock_exit_idx = events.index("lock_exit")
    assert atomic_idx < lock_exit_idx, f"lock_exit must follow atomic_write; events: {events}"


def test_inject_wikilinks_toctou_skip(tmp_wiki: Path, monkeypatch) -> None:
    """AC7/AC8 — under-lock re-read sees already-linked; skip atomic_write.

    Seeds a match page whose pre-lock read shows the title; a monkeypatched
    Path.read_text returns DIFFERENT content on the second (under-lock) call —
    the replacement was already injected by a hypothetical concurrent linker.
    The production code MUST skip atomic_text_write.
    """
    from kb.compile import linker  # noqa: PLC0415

    target_title = "RAG"
    target_pid = "concepts/rag"
    _write_page(tmp_wiki / "concepts" / "rag.md", target_title, "Target body.")
    match_page = tmp_wiki / "entities" / "matchpage.md"
    _write_page(match_page, "MatchPage", "About RAG here.")

    real_read_text = Path.read_text
    read_calls = {"count": 0}

    def race_read_text(self, *a, **kw):
        if self == match_page:
            read_calls["count"] += 1
            if read_calls["count"] == 1:
                # Pre-lock peek — return the original content unchanged.
                return real_read_text(self, *a, **kw)
            # Under-lock re-read — simulate concurrent linker already linked it.
            return (
                "---\ntitle: MatchPage\ntype: concept\nsource: []\n---\n\n"
                "About [[concepts/rag|RAG]] here.\n"
            )
        return real_read_text(self, *a, **kw)

    write_calls: list[Path] = []

    def spy_atomic_write(content, path):
        write_calls.append(path)
        # no-op to avoid corrupting the simulation

    monkeypatch.setattr(Path, "read_text", race_read_text)
    monkeypatch.setattr(linker, "atomic_text_write", spy_atomic_write)

    updated = linker.inject_wikilinks(target_title, target_pid, wiki_dir=tmp_wiki)

    assert match_page not in write_calls, (
        f"TOCTOU: atomic_text_write should be skipped when under-lock re-read "
        f"shows already-linked; got writes: {write_calls}"
    )
    assert "entities/matchpage" not in updated, (
        f"TOCTOU: updated list should NOT include the race-lost page; got {updated}"
    )


def test_inject_wikilinks_lock_timeout_warning(tmp_wiki: Path, monkeypatch, caplog) -> None:
    """AC7/AC8/Q21 — lock timeout skips the page with a WARNING (does not raise)."""
    import logging  # noqa: PLC0415

    from kb.compile import linker  # noqa: PLC0415

    target_title = "RAG"
    target_pid = "concepts/rag"
    _write_page(tmp_wiki / "concepts" / "rag.md", target_title, "Target body.")
    match_page = tmp_wiki / "entities" / "matchpage.md"
    _write_page(match_page, "MatchPage", "About RAG here.")

    @contextmanager
    def spy_file_lock(path: Path, timeout=None):
        if path == match_page:
            raise TimeoutError(f"simulated stuck lock on {path}")
        yield

    monkeypatch.setattr(linker, "file_lock", spy_file_lock)

    with caplog.at_level(logging.WARNING, logger="kb.compile.linker"):
        updated = linker.inject_wikilinks(target_title, target_pid, wiki_dir=tmp_wiki)

    assert updated == [], f"Timed-out page should not appear in updated; got {updated}"
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("Skipping inject_wikilinks" in m and "lock timeout" in m for m in warning_msgs), (
        f"Expected a 'Skipping inject_wikilinks ... lock timeout' WARNING; got {warning_msgs}"
    )
