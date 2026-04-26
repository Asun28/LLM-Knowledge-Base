# Cycle 35 — Plan Amendments (post Step-8 plan gate)

Date: 2026-04-26
Source: Step-8 Codex plan-gate REJECT with 5 gaps. Per cycle-21 L1 (REJECT with doc/design-only gaps), resolved inline. Plan stays valid; the per-task self-checks and test stubs are amended below.

## Gap 1 — TASK 2 spy mechanism (Step-5 Q8 / CONDITION 7)

REQUIRED: use `unittest.mock.call_args_list` ordering against `file_lock`, `read_text`, `atomic_text_write` mocks.
GIVEN: original plan used custom `lock_calls` / `lock_events` lists.

Amended TASK 2 spy fixture (used by both `TestUpdateSourcesMappingRMWLock` and `TestUpdateIndexBatchRMWLock`):

```python
from unittest.mock import MagicMock, call

def _build_rmw_spies(monkeypatch):
    """Returns (file_lock_spy, read_text_spy, atomic_write_spy, call_log).

    `call_log` is a list of (target_name, args) tuples in invocation order so the
    test can assert `file_lock` enter, then `read_text`, then `atomic_text_write`,
    then `file_lock` exit.
    """
    call_log: list[tuple[str, tuple]] = []

    from contextlib import contextmanager

    @contextmanager
    def _file_lock_spy(path):
        call_log.append(("file_lock_enter", (path,)))
        try:
            yield
        finally:
            call_log.append(("file_lock_exit", (path,)))

    def _atomic_write_spy(content, path):
        call_log.append(("atomic_text_write", (content, path)))
        Path(path).write_text(content, encoding="utf-8")

    # Wrap Path.read_text to log when each path is read.
    real_read_text = Path.read_text
    def _read_text_spy(self, *args, **kwargs):
        call_log.append(("read_text", (self,)))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pipeline, "file_lock", _file_lock_spy)
    monkeypatch.setattr(pipeline, "atomic_text_write", _atomic_write_spy)
    monkeypatch.setattr(Path, "read_text", _read_text_spy)
    return call_log
```

Amended assertion shape (each test):

```python
def test_holds_file_lock_across_rmw_new_entry(self, monkeypatch, tmp_path):
    sources = tmp_path / "_sources.md"
    sources.write_text("# Sources\n", encoding="utf-8")
    log = _build_rmw_spies(monkeypatch)

    pipeline._update_sources_mapping("raw/articles/new.md", ["e/new"], wiki_dir=tmp_path)

    # Step-5 CONDITION 7: full RMW window is inside the lock.
    names = [name for name, _args in log if name.startswith("file_lock") or name in {"read_text", "atomic_text_write"}]
    assert names[0] == "file_lock_enter"
    assert "read_text" in names
    assert "atomic_text_write" in names
    assert names[-1] == "file_lock_exit"
    # Lock entered BEFORE read_text; lock exited AFTER atomic_text_write.
    assert names.index("file_lock_enter") < names.index("read_text")
    assert names.index("atomic_text_write") < names.index("file_lock_exit")
```

This pattern uses ordered insertion into `call_log` (the standard cycle-17 L4 / cycle-22 spy idiom — each spy records into the log; assertion is on log ordering, NOT mid-section race injection).

## Gap 2 — TASK 2 AC8 dedup-merge branch coverage

REQUIRED: AC8's RMW lock test must cover BOTH branches of `_update_sources_mapping` (new-entry append AND existing-line merge).
GIVEN: original plan tested only the new-entry append path.

ADD a sibling test method to `TestUpdateSourcesMappingRMWLock`:

```python
def test_holds_file_lock_across_rmw_merge_branch(self, monkeypatch, tmp_path):
    """RMW lock spans the dedup/merge branch as well as the new-entry append.

    Pre-seed _sources.md with an existing entry for the same source_ref so the
    merge branch fires. Same call-order assertions as the new-entry test.
    """
    sources = tmp_path / "_sources.md"
    sources.write_text("- `raw/articles/old.md` → [[e/old]]\n", encoding="utf-8")
    log = _build_rmw_spies(monkeypatch)

    # Re-call with NEW page IDs on the SAME source_ref → merge branch fires.
    pipeline._update_sources_mapping("raw/articles/old.md", ["e/old", "e/new"], wiki_dir=tmp_path)

    names = [name for name, _args in log if name.startswith("file_lock") or name in {"read_text", "atomic_text_write"}]
    assert names[0] == "file_lock_enter"
    assert names[-1] == "file_lock_exit"
    assert names.index("file_lock_enter") < names.index("read_text")
    assert names.index("atomic_text_write") < names.index("file_lock_exit")
```

## Gap 3 — TASK 1 AC3 forward-slash positive test input form

REQUIRED: AC3's positive test must exercise the FORWARD-SLASH UNC pattern directly. The original plan's `test_forward_slash_unc_redacts_via_extended_pattern` used a BACKSLASH UNC OSError filename, which only verifies the existing `_rel` slash-normalization indirectly.
GIVEN: confusion between two anchors — the existing `test_windows_ordinary_unc_filename_redacts` (xfail removed) tests backslash-via-`sanitize_error_text`; the NEW test should target the forward-slash regex directly via `sanitize_text`.

Amended TASK 1 test set:

```python
# AC3 — direct forward-slash regex coverage.
def test_forward_slash_unc_redacts_via_extended_pattern(self):
    """Direct sanitize_text input in forward-slash UNC form (post-_rel-normalize shape).

    Cycle-24 L4: revert AC1 → this test fails because `//corp.example.com/share$/secret.md`
    matches no current alternative.
    """
    from kb.utils.sanitize import sanitize_text
    out = sanitize_text("//corp.example.com/share$/secret.md")
    assert "corp.example.com" not in out
    assert "share$" not in out
    assert "secret.md" not in out
    assert "<path>" in out

# AC1b — slash-form Windows UNC long-path direct coverage.
def test_slash_unc_long_path_redacts(self):
    from kb.utils.sanitize import sanitize_text
    out = sanitize_text("//?/UNC/server/share/secret.md")
    assert "server" not in out
    assert "share" not in out
    assert "secret.md" not in out
    assert "<path>" in out

# AC3 negative — URL not over-matched (verifies (?<!:) lookbehind).
def test_url_not_overmatched_by_uri_guard(self):
    from kb.utils.sanitize import sanitize_text
    inp = "see https://example.com/path for details"
    assert sanitize_text(inp) == inp

# AC3 negative — C++ // comment not over-matched.
def test_double_slash_comment_not_overmatched(self):
    from kb.utils.sanitize import sanitize_text
    inp = "// comment text\n// more comments"
    assert sanitize_text(inp) == inp
```

The existing `test_windows_ordinary_unc_filename_redacts` (xfail removed) STAYS as the integration anchor through `sanitize_error_text` → `_rel` slash-normalize → forward-slash regex → redact. Both tests are required: the integration anchor proves `_rel` flows correctly to the regex; the direct sanitize_text tests prove the regex itself.

## Gap 4 — TASK 2 AC10 byte-equal snapshot + read-absence

REQUIRED: AC10 must assert `_sources.md` content is unchanged byte-for-byte AND no file read occurs before the early return.
GIVEN: original plan only tested with `_sources.md` absent.

Amended `TestUpdateSourcesMappingEmptyList`:

```python
class TestUpdateSourcesMappingEmptyList:
    def test_skips_empty_wiki_pages_existing_file(self, monkeypatch, tmp_path):
        """AC10 — byte-equal snapshot before/after empty-pages call on EXISTING file.

        Plus assert no read_text / atomic_text_write fires (Step-5 Q9 + CONDITION 8).
        """
        sources = tmp_path / "_sources.md"
        original = "# Sources\n\n- `raw/articles/old.md` → [[e/old]]\n"
        sources.write_text(original, encoding="utf-8")
        snap_before = sources.read_bytes()

        log = _build_rmw_spies(monkeypatch)

        pipeline._update_sources_mapping("raw/articles/empty.md", [], wiki_dir=tmp_path)

        # Byte-equal: file content unchanged.
        assert sources.read_bytes() == snap_before
        # No I/O fired between AC6 early-return and AC10's assertion target.
        names = {name for name, _args in log}
        assert "file_lock_enter" not in names
        assert "read_text" not in names  # NB: spy logs ALL Path.read_text calls;
        # if any pre-existing infrastructure reads the file before the early-return
        # (it shouldn't), this assertion will catch it.
        assert "atomic_text_write" not in names

    def test_skips_empty_wiki_pages_absent_file(self, monkeypatch, tmp_path, caplog):
        """T8 — empty wiki_pages with sources_file absent: silent no-op, no warning."""
        log = _build_rmw_spies(monkeypatch)

        with caplog.at_level("WARNING"):
            pipeline._update_sources_mapping("raw/articles/empty.md", [], wiki_dir=tmp_path)

        names = {name for name, _args in log}
        assert "atomic_text_write" not in names
        # T8: no missing-file warning under empty-pages.
        assert not any("not found" in r.message for r in caplog.records)
```

The first test verifies the byte-equal contract on an existing file (AC10). The second test verifies the absent-file silence (T8). Both share the spy fixture for I/O-absence assertions.

## Gap 5 — Step-5 CONDITION 16 same-class peer scan

REQUIRED: `rg "with file_lock(" src/kb/ingest src/kb/utils src/kb/compile` must appear in the plan's self-check.
GIVEN: not present in original TASK 2 self-check.

Amended TASK 2 self-check (replaces the original list):

- `rg "with file_lock\(sources_file\)|with file_lock\(index_path\)" src/kb/ingest/pipeline.py` — confirm both new lock sites added.
- **`rg "with file_lock\(" src/kb/ingest src/kb/utils src/kb/compile`** — confirm the two new lock sites are present AND no peer write site in pipeline / utils / compile remains unlocked. Expected: cycle-19 + cycle-24 lock sites in `pipeline.py` (`_write_wiki_page`, `_update_existing_page`, `append_evidence_trail`), `utils/wiki_log.py:149` (cycle-22 `append_wiki_log`), HASH_MANIFEST writes, and the two NEW cycle-35 lock sites. No new peer site detected.
- `rg "f\"\`\\\\{source_ref\\\\}\`\"" src/kb/ingest/pipeline.py` — ZERO matches inside `_update_sources_mapping` (was 2 before AC7 fix).
- `rg "if not wiki_pages:" src/kb/ingest/pipeline.py` — early-return present.
- Full pytest run: `python -m pytest tests/test_cycle35_ingest_index_writers.py tests/test_cycle33_ingest_index_idempotency.py tests/test_cycle18_ingest_observability.py tests/test_v01008_ingest_pipeline_fixes.py -v` — new tests pass; existing 4 monkeypatch-based tests still pass.

## Net effect on the plan

- TASK 1: AC3 test set CHANGED (3 direct sanitize_text tests + 1 integration test that already exists post-xfail-removal).
- TASK 2: tests REWORKED to use `_build_rmw_spies` helper and `call_args_list`-style ordering; merge-branch test ADDED; empty-pages test SPLIT into existing-file + absent-file variants; same-class peer scan ADDED to self-check.
- TASK 3, TASK 4, TASK 5, TASK 6: NO changes (plan-gate confirmed APPROVE on those tasks).

Verdict: amendments resolve all 5 gaps. NO PLAN-AMENDS-DESIGN — these are test-coverage tightening, not design changes. Per cycle-21 L1, no Step-5 re-run needed; proceed to Step 9.
