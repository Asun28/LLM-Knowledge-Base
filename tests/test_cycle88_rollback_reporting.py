"""Cycle 88 — honest reporting of durability and rollback outcomes.

Three residuals filed by cycle-87's own Codex review. All three share one shape:
the code takes a correct ACTION but then tells the caller something the
filesystem does not support.

* **AC01** ``review/refiner.py`` records a revision as ``failed`` when only the
  durability barrier failed. The page already holds the new text at that point,
  so the revision state contradicts the file on disk.
* **AC02** ``capture.py`` promises all-or-nothing but its rollback is
  best-effort: every unlink swallows ``OSError`` with a warning and no barrier
  follows the deletions, so a partially-rolled-back batch is reported as
  ``([], error)`` — indistinguishable from "nothing was written".
* **AC03** ``lint/checks/evidence_resolvable.py``'s no-follow stat is pinned on
  POSIX symlinks only. Windows reparse points (junctions) and hardlinks are the
  uncovered discriminators on this project's primary development platform.

AC01 and AC02 are reporting-accuracy defects, not data loss: in both cases the
bytes on disk are correct and a retry is idempotent. That is exactly why they
are worth closing — a caller that cannot trust the report cannot automate the
retry.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import kb.capture as capture_mod
import kb.lint.checks.evidence_resolvable as evidence_mod
import kb.utils.io as io_mod
from kb.lint.checks.evidence_resolvable import (
    _is_regular_file_no_follow,
    check_evidence_resolvable,
)
from kb.review import refiner
from kb.review.refiner import load_review_history, refine_page

# ==========================================================================
# AC01 — a failed barrier is not a failed revision
# ==========================================================================


def _seed_page(wiki_dir: Path, page_id: str, body: str) -> Path:
    page_path = wiki_dir / f"{page_id}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        f"---\ntitle: Foo\ntype: concept\nsource: []\nupdated: 2026-01-01\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return page_path


def _write_then_barrier_failure(content: str, path, **kwargs):
    """Model the real failure precisely: the bytes land, THEN the barrier fails.

    Writing the file first is the whole point. A stub that only raises would
    pass against the pre-fix code too, because the pre-fix complaint is not
    "it raised" but "it said `failed` while the page held the new text".
    """
    Path(path).write_text(content, encoding="utf-8")
    raise io_mod.RenameCompletedBarrierError(5, "Input/output error")


def test_barrier_failure_records_applied_not_failed(tmp_wiki: Path, tmp_path: Path, monkeypatch):
    """The page holds `new_text`, so `failed` is a false report.

    Fails against a revert to the single broad `except OSError`: the row comes
    back `failed` while the page on disk carries the revision.
    """
    page_path = _seed_page(tmp_wiki, "concepts/foo", "Original body.")
    history_path = tmp_path / "review_history.json"
    monkeypatch.setattr(refiner, "atomic_text_write", _write_then_barrier_failure)

    result = refine_page(
        "concepts/foo",
        "Revised body that genuinely reached the page.",
        revision_notes="cycle88 AC01",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    assert "Revised body that genuinely reached the page." in page_path.read_text(encoding="utf-8")
    (row,) = load_review_history(history_path)
    assert row["status"] == "applied", f"page holds the revision; got {row}"
    assert row["durable"] is False
    assert "Input/output error" in row.get("durability_error", "")
    assert result.get("error") is None, "a completed write must not be reported as an error"
    assert result.get("updated") is True
    assert result.get("durable") is False


def test_a_plain_oserror_still_flips_to_failed(tmp_wiki: Path, tmp_path: Path, monkeypatch):
    """Non-regression on the cycle-19 contract, and the catch-ORDER pin.

    `RenameCompletedBarrierError` subclasses `OSError`, so the two handlers are
    order-sensitive in the same way `ValueDomainError` / `TierBoundaryError` are
    (C86 lesson). If the broad handler is ever placed first the barrier case is
    swallowed and the test above fails; if the narrow one somehow widened, this
    one fails. Neither ordering passes both.
    """
    page_path = _seed_page(tmp_wiki, "concepts/foo", "Original body unchanged.")
    original = page_path.read_text(encoding="utf-8")
    history_path = tmp_path / "review_history.json"

    def _boom(*args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(refiner, "atomic_text_write", _boom)

    result = refine_page(
        "concepts/foo",
        "Refused content",
        revision_notes="cycle88 AC01 non-regression",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    assert "error" in result
    assert page_path.read_text(encoding="utf-8") == original
    (row,) = load_review_history(history_path)
    assert row["status"] == "failed"
    assert "durable" not in row, "a write that never landed has no durability verdict to give"


def test_the_happy_path_makes_no_durability_claim(tmp_wiki: Path, tmp_path: Path):
    """`durable` is written ONLY on the not-durable path.

    Absence means "no caveat recorded", following the `get_prompt_version`
    legacy-default convention rather than stamping every historical row.
    """
    _seed_page(tmp_wiki, "concepts/foo", "Original body.")
    history_path = tmp_path / "review_history.json"

    result = refine_page(
        "concepts/foo",
        "Revised body.",
        revision_notes="cycle88 AC01 happy path",
        wiki_dir=tmp_wiki,
        history_path=history_path,
    )

    (row,) = load_review_history(history_path)
    assert row["status"] == "applied"
    assert "durable" not in row
    assert "durability_error" not in row
    assert result.get("durable") is not False


# ==========================================================================
# AC02 — a rollback that could not finish must say so
# ==========================================================================


def _make_item(title: str) -> dict:
    return {
        "title": title,
        "kind": "decision",
        "body": "body content",
        "one_line_summary": "summary",
        "confidence": "stated",
    }


def _fail_unlink_for(monkeypatch, *names: str) -> None:
    """Make `Path.unlink` raise for exactly these basenames, leaving the file."""
    real_unlink = Path.unlink
    targets = set(names)

    def _unlink(self, *args, **kwargs):
        if self.name in targets:
            raise OSError(13, "Permission denied")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _unlink)


def _fail_promote_on(index: int, exc_factory):
    """Return a `durable_replace` stub that fails on the `index`-th promote."""
    calls = {"n": 0}

    def _promote(src, dst):
        if calls["n"] == index:
            raise exc_factory(src, dst)
        calls["n"] += 1
        return os.replace(src, dst)

    return _promote


def _write_three(captures_dir: Path):
    return capture_mod._write_item_files(
        [_make_item("alpha"), _make_item("beta"), _make_item("gamma")],
        "prov",
        "2026-04-13T00:00:00Z",
        captures_dir=captures_dir,
    )


def _oserror(src, dst):
    return OSError(28, "No space left on device")


def test_rollback_reports_indeterminacy_when_an_unlink_fails(tmp_path, monkeypatch):
    """`([], error)` currently means "nothing was written". After a failed
    rollback unlink that is a lie — item 0's file is still on disk.

    Fails pre-fix: the surviving file is logged as a warning and the caller is
    handed the same plain error it gets for a clean rollback.
    """
    captures_dir = tmp_path / "captures"
    monkeypatch.setattr(capture_mod, "durable_replace", _fail_promote_on(2, _oserror))
    _fail_unlink_for(monkeypatch, "decision-alpha.md")

    written, err = _write_three(captures_dir)

    assert written == []
    assert err is not None
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in err
    assert "decision-alpha.md" in err, "the caller needs to know WHICH file survived"
    assert (captures_dir / "decision-alpha.md").exists(), "precondition: the unlink really failed"


def test_a_clean_rollback_makes_no_indeterminacy_claim(tmp_path, monkeypatch):
    """Over-reporting is its own defect: when every deletion succeeds the batch
    state is known-empty and the error must stay the plain one."""
    captures_dir = tmp_path / "captures"
    monkeypatch.setattr(capture_mod, "durable_replace", _fail_promote_on(2, _oserror))

    written, err = _write_three(captures_dir)

    assert written == []
    assert err is not None
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER not in err
    assert list(captures_dir.glob("*.md")) == []


def test_rollback_deletions_are_fsynced_once_after_the_last_unlink(tmp_path, monkeypatch):
    """Without a directory barrier the deletions can revert on power loss, so
    items the caller was told do not exist reappear.

    Pins both that the barrier runs and that it runs AFTER the unlinks — a
    barrier taken first would flush nothing that matters.
    """
    captures_dir = tmp_path / "captures"
    order: list[str] = []
    real_unlink = Path.unlink

    def _spy_unlink(self, *args, **kwargs):
        if self.suffix == ".md":
            order.append(f"unlink:{self.name}")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _spy_unlink)
    monkeypatch.setattr(
        capture_mod, "_fsync_parent_dir", lambda d: order.append(f"fsync:{Path(d).name}")
    )
    monkeypatch.setattr(capture_mod, "durable_replace", _fail_promote_on(2, _oserror))

    _write_three(captures_dir)

    assert order.count("fsync:captures") == 1, f"expected exactly one dir barrier; got {order}"
    assert order[-1] == "fsync:captures", f"barrier must follow the deletions; got {order}"
    assert "unlink:decision-alpha.md" in order


def test_a_failed_rollback_barrier_is_itself_reported_as_indeterminate(tmp_path, monkeypatch):
    """The barrier is the thing that makes "deleted" survive a power cut. If it
    raises, the deletions are not guaranteed and the batch state is unknown —
    silently swallowing that recreates the defect one layer down."""
    captures_dir = tmp_path / "captures"
    monkeypatch.setattr(capture_mod, "durable_replace", _fail_promote_on(2, _oserror))

    def _barrier_boom(directory):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(capture_mod, "_fsync_parent_dir", _barrier_boom)

    written, err = _write_three(captures_dir)

    assert written == []
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in err


def test_an_orphan_from_a_failed_barrier_is_reported_when_its_unlink_fails(tmp_path, monkeypatch):
    """Cycle 87 made the completed-promote orphan get unlinked. That unlink can
    itself fail, and pre-cycle-88 it was a bare warning — so the exact orphan
    cycle 87 set out to prevent could still survive an `([], error)` silently."""
    captures_dir = tmp_path / "captures"

    def _rename_then_barrier_failure(src, dst):
        os.replace(src, dst)
        raise io_mod.RenameCompletedBarrierError(5, "Input/output error")

    monkeypatch.setattr(
        capture_mod,
        "durable_replace",
        _fail_promote_on(2, lambda src, dst: _rename_then_barrier_failure(src, dst)),
    )
    _fail_unlink_for(monkeypatch, "decision-gamma.md")

    written, err = _write_three(captures_dir)

    assert written == []
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in err
    assert "decision-gamma.md" in err
    assert (captures_dir / "decision-gamma.md").exists(), "precondition: the orphan survived"


def test_a_reservation_rollback_failure_is_reported(tmp_path, monkeypatch):
    """Phase 1 has the same contract as Phase 3 — `([], error)` claims nothing
    was left behind, and a stuck `.reserving` temp falsifies that."""
    captures_dir = tmp_path / "captures"
    captures_dir.mkdir(parents=True)
    calls = {"n": 0}
    real_reserve = capture_mod._reserve_hidden_temp

    def _reserve(item, existing, cdir):
        if calls["n"] == 1:
            raise OSError(28, "No space left on device")
        calls["n"] += 1
        return real_reserve(item, existing, cdir)

    monkeypatch.setattr(capture_mod, "_reserve_hidden_temp", _reserve)
    _fail_unlink_for(monkeypatch, ".decision-alpha.reserving")

    written, err = capture_mod._write_item_files(
        [_make_item("alpha"), _make_item("beta")],
        "prov",
        "2026-04-13T00:00:00Z",
        captures_dir=captures_dir,
    )

    assert written == []
    assert capture_mod.ROLLBACK_INCOMPLETE_MARKER in err
    assert ".decision-alpha.reserving" in err


# ==========================================================================
# AC03 — Windows reparse-point + hardlink discriminators
# ==========================================================================


def _write_page(wiki_dir: Path, ref: str) -> Path:
    wiki_dir.mkdir(parents=True, exist_ok=True)
    page = wiki_dir / "page.md"
    page.write_text(f'---\ntitle: "P"\nsource:\n  - "{ref}"\n---\n\nBody.\n', encoding="utf-8")
    return page


def _make_junction(link: Path, target: Path) -> None:
    """Create an NTFS directory junction. Unlike a symlink this needs no
    privileges, which is why it — not `symlink_to` — is the viable Windows
    reparse-point probe (unprivileged symlink creation fails WinError 1314)."""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"mklink /J unavailable: {result.stdout.strip()} {result.stderr.strip()}")


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction test")
def test_no_follow_helper_rejects_a_windows_junction(tmp_path):
    """A junction is a directory reparse point, so `S_ISREG` is false for it and
    the stat refuses it without traversing. Completes the cycle-87 AC03 coverage
    on the platform the POSIX symlink test cannot run on."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("host secret", encoding="utf-8")
    link = tmp_path / "raw_evidence"
    _make_junction(link, outside)

    assert _is_regular_file_no_follow(link) is False


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction test")
def test_a_junction_planted_under_raw_escapes_containment_before_any_stat(tmp_path):
    """A junction left in place is caught EARLIER and harder than the stat.

    `_resolve_evidence_ref` calls `.resolve()`, which traverses the junction, so
    containment rejects the target as outside `raw/` — severity `error`, and the
    path is deliberately never stat'd (the T1 no-oracle rule). This is the
    Windows peer of cycle-87's note that an out-of-tree POSIX symlink was
    already an `error` rather than a silent pass.

    Written after this test first asserted `warning` and failed: the weaker
    verdict was the wrong expectation, not the code.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("host secret", encoding="utf-8")
    _make_junction(raw_dir / "evidence.md", outside)

    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")

    issues = check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page])

    assert [i["check"] for i in issues] == ["evidence_unresolvable"]
    assert issues[0]["severity"] == "error"
    assert "does not point inside raw/" in issues[0]["message"]


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction test")
def test_a_junction_swapped_in_after_the_containment_check_is_refused(tmp_path, monkeypatch):
    """The genuine Windows TOCTOU peer of the POSIX symlink test.

    `_resolve_evidence_ref` is stubbed to return the contained path because that
    is what it does in the real race: it resolves and judges containment BEFORE
    the swap lands. Only afterwards does that path become a junction pointing
    outside. Letting the real resolver run against an already-planted junction
    tests the containment check instead (the test above), never the stat.

    Pre-cycle-87 the `Path.is_file()` stat would traverse it; `os.lstat` does
    not, so the ref is reported unresolvable rather than confirming a host path
    exists.
    """
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("host secret", encoding="utf-8")

    swapped = raw_dir / "evidence.md"
    _make_junction(swapped, outside)
    monkeypatch.setattr(evidence_mod, "_resolve_evidence_ref", lambda ref, raw: swapped)

    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")

    issues = check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page])

    assert [i["check"] for i in issues] == ["evidence_unresolvable"]
    assert issues[0]["severity"] == "warning"
    assert "does not resolve to a file" in issues[0]["message"]


def test_a_hardlink_is_still_accepted_as_evidence(tmp_path):
    """Guard against over-rejection. `os.lstat` reports a hardlink as a regular
    file — it IS one, a second name for the same inode, not a reparse point —
    and a `raw/` tree that dedupes with hardlinks must keep linting clean. Pins
    the boundary of the AC03 rejection so a future tightening to `st_nlink == 1`
    gets caught."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    real = raw_dir / "real.md"
    real.write_text("evidence", encoding="utf-8")
    hard = raw_dir / "evidence.md"
    try:
        os.link(real, hard)
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip(f"hardlinks unsupported here: {exc}")

    assert _is_regular_file_no_follow(hard) is True

    wiki_dir = tmp_path / "wiki"
    page = _write_page(wiki_dir, "raw/evidence.md")
    assert check_evidence_resolvable(wiki_dir=wiki_dir, raw_dir=raw_dir, pages=[page]) == []


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS junction test")
def test_a_file_inside_a_junctioned_subdir_is_the_documented_residual(tmp_path):
    """Honest-scope pin, not a defect claim. Cycle 87 documented that only the
    FINAL component is protected; an ANCESTOR swap still resolves through. This
    records that residual as a test so a future `openat2(RESOLVE_BENEATH)` pass
    has an executable statement of what changes."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("host secret", encoding="utf-8")
    _make_junction(raw_dir / "sub", outside)

    # The final component IS a regular file; the junction is one level up.
    assert _is_regular_file_no_follow(raw_dir / "sub" / "secret.md") is True
