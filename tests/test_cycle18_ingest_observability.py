"""Cycle 18 AC9-AC15 — pipeline observability + `_write_index_files` helper.

Threats:
- T1 (JSONL redaction + field allowlist) — absolute paths redacted; unknown
  outcome keys dropped at the writer boundary.
- T7 (JSONL parseability) — fsync + line-size < PIPE_BUF; torn rows avoided.
- T9 (wiki/log.md injection via [req=] prefix) — hex-only safe by construction.

Test strategy: behavioural assertions against JSONL on disk + call-order
spies. No source-scan tests (cycle-11 L2).
"""

from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

# Module-level pattern for [req=<16 hex>] prefix detection.
_REQ_PREFIX_RE = re.compile(r"\[req=([0-9a-f]{16})\]")


def _stub_extraction() -> dict:
    return {
        "title": "Observability Test Source",
        "summary": "Small test source used by cycle 18 JSONL tests.",
        "entities_mentioned": [],
        "concepts_mentioned": [],
        "key_points": ["Trigger the success path."],
    }


def _ingest(tmp_kb_env: Path, slug: str) -> dict:
    """Helper — run one ingest under tmp_kb_env; returns the result dict."""
    from kb.ingest.pipeline import ingest_source  # noqa: PLC0415

    raw = tmp_kb_env / "raw" / "articles" / f"{slug}.md"
    raw.write_text(f"# {slug}\n\nBody.\n", encoding="utf-8")
    return ingest_source(
        raw,
        source_type="article",
        extraction=_stub_extraction(),
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
    )


def _read_jsonl(jsonl_path: Path) -> list[dict]:
    return [
        json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line
    ]


# ---------------------------------------------------------------------------
# AC10 — [req=] prefix in wiki/log.md matches JSONL request_id.
# ---------------------------------------------------------------------------
def test_request_id_prefix_in_log_md(tmp_kb_env: Path) -> None:
    """AC10 — wiki/log.md line carries [req=<16-hex>] as the FIRST token of the
    message field AND the hex matches the JSONL row's request_id.

    Threat T9 position pin (Step-11 Sonnet-fallback LOW): the prefix must be
    the first token inside the `... | ingest | <message>` field — a future
    refactor prepending other text would slip past a loose `re.search`.
    """
    _ingest(tmp_kb_env, "ac10-prefix-match")

    log_md = (tmp_kb_env / "wiki" / "log.md").read_text(encoding="utf-8")
    ingest_lines = [line for line in log_md.splitlines() if "| ingest |" in line]
    assert ingest_lines, f"No `| ingest |` line in log.md:\n{log_md}"
    # Split on " | " to isolate the message field: "- YYYY-MM-DD | ingest | <msg>"
    msg_part = ingest_lines[-1].split(" | ", 2)[-1]
    anchored = _REQ_PREFIX_RE.match(msg_part)
    assert anchored is not None, (
        f"[req=<16-hex>] must be the FIRST token of the message field; got: {msg_part!r}"
    )
    log_request_id = anchored.group(1)

    jsonl = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    success_rows = [row for row in jsonl if row["stage"] == "success"]
    assert len(success_rows) >= 1
    assert success_rows[-1]["request_id"] == log_request_id, (
        f"JSONL request_id {success_rows[-1]['request_id']!r} does not match "
        f"log.md prefix {log_request_id!r}"
    )


# ---------------------------------------------------------------------------
# AC11 — emission at start + success on a normal ingest.
# ---------------------------------------------------------------------------
def test_jsonl_emitted_on_success(tmp_kb_env: Path) -> None:
    """AC11 — 2 rows per successful ingest: start + success with matching request_id."""
    _ingest(tmp_kb_env, "ac11-success")

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    assert len(rows) == 2, f"Expected 2 rows (start + success); got {len(rows)}: {rows}"
    assert rows[0]["stage"] == "start"
    assert rows[1]["stage"] == "success"
    assert rows[0]["request_id"] == rows[1]["request_id"]
    assert rows[1]["outcome"].get("pages_created") is not None
    assert isinstance(rows[1]["outcome"]["pages_created"], int)
    assert isinstance(rows[1]["outcome"]["pages_updated"], int)
    assert isinstance(rows[1]["outcome"]["pages_skipped"], int)


# ---------------------------------------------------------------------------
# AC11 — duplicate ingest emits start + duplicate_skip.
# ---------------------------------------------------------------------------
def test_jsonl_emitted_on_duplicate(tmp_kb_env: Path, monkeypatch) -> None:
    """AC11 — duplicate ingest emits start + duplicate_skip (distinct request_id from first).

    Duplicate detection in `_check_and_reserve_manifest` uses `PROJECT_ROOT`
    to verify the other source file still exists. The fixture mirror-rebind
    may leave `pipeline.PROJECT_ROOT` stale in some test orderings; force the
    binding here so the behaviour is deterministic.
    """
    from kb.ingest import pipeline  # noqa: PLC0415

    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_kb_env)

    identical_body = "# dup-source\n\nBody that will have the same hash.\n"
    raw_a = tmp_kb_env / "raw" / "articles" / "ac11-dup-a.md"
    raw_b = tmp_kb_env / "raw" / "articles" / "ac11-dup-b.md"
    raw_a.write_text(identical_body, encoding="utf-8")
    raw_b.write_text(identical_body, encoding="utf-8")

    result_a = pipeline.ingest_source(
        raw_a,
        source_type="article",
        extraction=_stub_extraction(),
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
    )
    assert result_a.get("duplicate") is not True

    result_b = pipeline.ingest_source(
        raw_b,
        source_type="article",
        extraction=_stub_extraction(),
        wiki_dir=tmp_kb_env / "wiki",
        raw_dir=tmp_kb_env / "raw",
    )
    assert result_b.get("duplicate") is True, (
        f"Expected duplicate=True on second ingest; got {result_b}"
    )

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    stages = [r["stage"] for r in rows]
    assert stages == ["start", "success", "start", "duplicate_skip"], (
        f"Unexpected stage sequence: {stages}"
    )
    # request_ids correlate in pairs but differ across ingests.
    assert rows[0]["request_id"] == rows[1]["request_id"]
    assert rows[2]["request_id"] == rows[3]["request_id"]
    assert rows[0]["request_id"] != rows[2]["request_id"]


# ---------------------------------------------------------------------------
# AC11 — failure path emits start + failure; original exception propagates.
# ---------------------------------------------------------------------------
def test_jsonl_emitted_on_failure(tmp_kb_env: Path) -> None:
    """AC11 — synthetic exception → start + failure rows; exc re-raised.

    Cycle 20 AC5 / AC7 — unexpected exceptions (RuntimeError here) are now
    wrapped in ``kb.errors.IngestError`` so callers get a stable taxonomy.
    The original ``RuntimeError`` is preserved in ``__cause__`` so the
    synthetic message text still round-trips to the JSONL ``error_summary``
    field via ``sanitize_text(str(exc))``.
    """
    from kb.errors import IngestError  # noqa: PLC0415
    from kb.ingest import pipeline  # noqa: PLC0415

    raw = tmp_kb_env / "raw" / "articles" / "ac11-fail.md"
    raw.write_text("# fail\n\nBody.\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("synthetic cycle18 failure at /home/ci/path")

    with patch.object(pipeline, "_process_item_batch", side_effect=boom):
        with pytest.raises(IngestError, match="synthetic cycle18 failure") as excinfo:
            pipeline.ingest_source(
                raw,
                source_type="article",
                extraction=_stub_extraction(),
                wiki_dir=tmp_kb_env / "wiki",
                raw_dir=tmp_kb_env / "raw",
            )
    # Cycle 20 AC7 — original RuntimeError preserved in __cause__.
    assert isinstance(excinfo.value.__cause__, RuntimeError)

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    stages = [r["stage"] for r in rows]
    assert stages == ["start", "failure"], f"Unexpected stage sequence: {stages}"
    err_summary = rows[1]["outcome"].get("error_summary", "")
    assert "synthetic cycle18 failure" in err_summary
    # Absolute path in the exception string must be redacted.
    assert "/home/ci/path" not in err_summary, (
        f"Absolute path leaked into JSONL error_summary: {err_summary!r}"
    )
    assert "<path>" in err_summary


def test_jsonl_emitted_on_pre_body_exception(tmp_kb_env: Path) -> None:
    """PR #32 R1 Codex BLOCKER pin — validation failure BEFORE body still emits `failure`.

    Raising from `_pre_validate_extraction` (or `extract_from_source`) must
    emit the terminal `failure` row, not leave an orphan `start`. The fix
    moved the try/except boundary up so extraction + validation + duplicate
    reservation are all inside the envelope.
    """
    from kb.ingest import pipeline  # noqa: PLC0415

    raw = tmp_kb_env / "raw" / "articles" / "ac11-pre-body-fail.md"
    raw.write_text("# prebody\n\nBody.\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise ValueError("synthetic pre-body validation failure")

    with patch.object(pipeline, "_pre_validate_extraction", side_effect=boom):
        with pytest.raises(ValueError, match="synthetic pre-body"):
            pipeline.ingest_source(
                raw,
                source_type="article",
                extraction=_stub_extraction(),
                wiki_dir=tmp_kb_env / "wiki",
                raw_dir=tmp_kb_env / "raw",
            )

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    stages = [r["stage"] for r in rows]
    assert stages == ["start", "failure"], (
        f"Pre-body exception must still emit terminal `failure`; got: {stages}"
    )
    assert "synthetic pre-body" in rows[1]["outcome"].get("error_summary", "")


# ---------------------------------------------------------------------------
# AC12 — rotation kicks in when jsonl exceeds threshold; new file created,
# rotation happens inside the same file_lock as the append.
# ---------------------------------------------------------------------------
def test_jsonl_rotation(tmp_kb_env: Path) -> None:
    """AC12 — oversized jsonl rotates on next emission."""
    jsonl_path = tmp_kb_env / ".data" / "ingest_log.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    # Pre-populate above the 500KB threshold.
    from kb.utils.wiki_log import LOG_SIZE_WARNING_BYTES  # noqa: PLC0415

    jsonl_path.write_text("x" * (LOG_SIZE_WARNING_BYTES + 1000), encoding="utf-8")

    _ingest(tmp_kb_env, "ac12-rotate")

    archives = list((tmp_kb_env / ".data").glob("ingest_log.*.jsonl"))
    assert len(archives) >= 1, (
        f"Expected at least one ingest_log archive; got {list((tmp_kb_env / '.data').iterdir())}"
    )
    # New jsonl contains the fresh start+success rows for the single ingest.
    rows = _read_jsonl(jsonl_path)
    stages = [r["stage"] for r in rows]
    assert "start" in stages and "success" in stages


def test_jsonl_rotation_inside_lock(tmp_path: Path, monkeypatch) -> None:
    """AC12 — rotate_if_oversized is called INSIDE file_lock in the JSONL writer."""
    from kb.ingest import pipeline  # noqa: PLC0415

    jsonl_path = tmp_path / ".data" / "ingest_log.jsonl"
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    # Patch PROJECT_ROOT inside pipeline so _emit_ingest_jsonl targets tmp_path.
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)

    events: list[str] = []

    @contextmanager
    def spy_lock(path, timeout=None):
        events.append(f"lock_enter:{path.name}")
        try:
            yield
        finally:
            events.append(f"lock_exit:{path.name}")

    real_rotate = pipeline.rotate_if_oversized

    def spy_rotate(path, max_bytes, prefix):
        events.append(f"rotate:{path.name}")
        return real_rotate(path, max_bytes, prefix)

    monkeypatch.setattr(pipeline, "file_lock", spy_lock)
    monkeypatch.setattr(pipeline, "rotate_if_oversized", spy_rotate)

    pipeline._emit_ingest_jsonl(
        "start",
        "a" * 16,
        "raw/x",
        "h" * 64,
        outcome={},
    )

    # rotate event must land strictly between lock_enter and lock_exit.
    lock_enter_idx = next(i for i, e in enumerate(events) if e.startswith("lock_enter"))
    rotate_idx = next(i for i, e in enumerate(events) if e.startswith("rotate:"))
    lock_exit_idx = next(i for i, e in enumerate(events) if e.startswith("lock_exit"))
    assert lock_enter_idx < rotate_idx < lock_exit_idx, f"events: {events}"


# ---------------------------------------------------------------------------
# AC13 — absolute path redaction in JSONL error_summary.
# ---------------------------------------------------------------------------
def test_jsonl_redacts_absolute_paths(tmp_kb_env: Path, monkeypatch) -> None:
    """AC13/T1 — Windows/UNC/POSIX paths in error_summary are redacted to <path>."""
    from kb.ingest import pipeline  # noqa: PLC0415

    pipeline._emit_ingest_jsonl(
        "failure",
        "a" * 16,
        "raw/x",
        "h" * 64,
        outcome={
            "error_summary": (
                "failed at C:\\Users\\Admin\\file.md and \\\\server\\share\\x "
                "and /home/user/file and C:/Users/Admin/file"
            )
        },
    )

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    assert rows, "Expected at least one row"
    err = rows[-1]["outcome"]["error_summary"]
    assert "C:\\Users" not in err
    assert "\\\\server\\share" not in err
    assert "/home/user" not in err
    assert "C:/Users" not in err
    assert err.count("<path>") >= 4, f"Expected >=4 <path> substitutions; got: {err!r}"


# ---------------------------------------------------------------------------
# AC11/T1 — field allowlist enforcement (invalid stage + unexpected keys).
# ---------------------------------------------------------------------------
def test_jsonl_field_allowlist(tmp_kb_env: Path, caplog) -> None:
    """AC11/Q19 — invalid stage raises; unexpected outcome keys dropped with WARNING."""
    from kb.ingest import pipeline  # noqa: PLC0415

    # (a) Invalid stage → ValueError at writer boundary.
    with pytest.raises(ValueError, match="Unknown ingest_jsonl stage"):
        pipeline._emit_ingest_jsonl(
            "bogus_stage",
            "a" * 16,
            "raw/x",
            "h" * 64,
            outcome={},
        )

    # (b) Unexpected outcome keys are DROPPED; secret content must not appear.
    with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
        pipeline._emit_ingest_jsonl(
            "failure",
            "a" * 16,
            "raw/x",
            "h" * 64,
            outcome={
                "error_summary": "msg",
                "raw_content": "SECRET_TOKEN_abc123",
                "evil_key": "unexpected",
            },
        )

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    row = rows[-1]
    assert "raw_content" not in row["outcome"], f"allowlist violated: {row}"
    assert "evil_key" not in row["outcome"], f"allowlist violated: {row}"
    assert "SECRET_TOKEN_abc123" not in json.dumps(row), f"secret leaked into JSONL row: {row}"
    # WARNING with the dropped key names.
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("Dropping unexpected ingest_log outcome fields" in m for m in warning_msgs), (
        f"Expected drop-warning; got warnings: {warning_msgs}"
    )


# ---------------------------------------------------------------------------
# AC11/Q20 — error_summary truncation to 2048 bytes.
# ---------------------------------------------------------------------------
def test_jsonl_error_summary_truncation(tmp_kb_env: Path) -> None:
    """AC11/Q20 — error_summary capped at 2048 BYTES after redaction.

    PR #32 R1 Sonnet M1 pin — truncation is byte-based, not char-based, so
    PIPE_BUF atomicity (threat T7) survives CJK-heavy errors.
    """
    from kb.ingest import pipeline  # noqa: PLC0415

    pipeline._emit_ingest_jsonl(
        "failure",
        "a" * 16,
        "raw/x",
        "h" * 64,
        outcome={"error_summary": "x" * 10_000},
    )

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    row = rows[-1]
    assert len(row["outcome"]["error_summary"].encode("utf-8")) <= 2048


def test_jsonl_error_summary_truncation_cjk_byte_bounded(tmp_kb_env: Path) -> None:
    """PR #32 R1 Sonnet M1 pin — CJK (3 UTF-8 bytes per char) stays ≤ 2048 bytes.

    Char-slicing would produce a 6144-byte string for 2048 CJK chars, exceeding
    PIPE_BUF atomicity. Byte-slicing via encode/decode must enforce the
    byte cap regardless of character width.
    """
    from kb.ingest import pipeline  # noqa: PLC0415

    # 3000 CJK chars → ~9000 UTF-8 bytes pre-truncation.
    cjk_error = "漢" * 3000
    pipeline._emit_ingest_jsonl(
        "failure",
        "a" * 16,
        "raw/x",
        "h" * 64,
        outcome={"error_summary": cjk_error},
    )

    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    row = rows[-1]
    encoded_len = len(row["outcome"]["error_summary"].encode("utf-8"))
    assert encoded_len <= 2048, (
        f"Expected error_summary <= 2048 bytes; got {encoded_len} bytes (char-slicing regression)"
    )


# ---------------------------------------------------------------------------
# AC14 — _write_index_files ordering + independent per-call failure.
# ---------------------------------------------------------------------------
def test_write_index_files_ordering(tmp_wiki: Path, monkeypatch) -> None:
    """AC14 — sources is called BEFORE index; both called exactly once."""
    from kb.ingest import pipeline  # noqa: PLC0415

    calls: list[str] = []

    def spy_sources(source_ref, all_pages, wiki_dir=None):
        calls.append("sources")

    def spy_index(entries, wiki_dir=None):
        calls.append("index")

    monkeypatch.setattr(pipeline, "_update_sources_mapping", spy_sources)
    monkeypatch.setattr(pipeline, "_update_index_batch", spy_index)

    pipeline._write_index_files(
        created_entries=[("summary", "x", "X")],
        source_ref="raw/x",
        all_pages=["summaries/x"],
        wiki_dir=tmp_wiki,
    )

    assert calls == ["sources", "index"], f"Unexpected call order: {calls}"


def test_write_index_files_independent_failure(tmp_wiki: Path, monkeypatch, caplog) -> None:
    """AC14/Q10 — sources raises; index STILL runs; WARNING logged for sources."""
    from kb.ingest import pipeline  # noqa: PLC0415

    calls: list[str] = []

    def broken_sources(*a, **kw):
        calls.append("sources_call")
        raise OSError("synthetic sources failure")

    def spy_index(entries, wiki_dir=None):
        calls.append("index")

    monkeypatch.setattr(pipeline, "_update_sources_mapping", broken_sources)
    monkeypatch.setattr(pipeline, "_update_index_batch", spy_index)

    with caplog.at_level(logging.WARNING, logger="kb.ingest.pipeline"):
        pipeline._write_index_files(
            created_entries=[("summary", "x", "X")],
            source_ref="raw/x",
            all_pages=["summaries/x"],
            wiki_dir=tmp_wiki,
        )

    assert "index" in calls, f"index_batch must run even when sources fails; got {calls}"
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("Failed to update _sources.md" in m for m in warning_msgs), (
        f"Expected sources WARNING; got {warning_msgs}"
    )


# ---------------------------------------------------------------------------
# AC9 — request_id format sanity.
# ---------------------------------------------------------------------------
def test_request_id_format(tmp_kb_env: Path) -> None:
    """AC9 — request_id is 16 lowercase hex characters."""
    _ingest(tmp_kb_env, "ac9-format")
    rows = _read_jsonl(tmp_kb_env / ".data" / "ingest_log.jsonl")
    for row in rows:
        rid = row["request_id"]
        assert isinstance(rid, str)
        assert len(rid) == 16
        assert re.fullmatch(r"[0-9a-f]{16}", rid), f"Malformed request_id: {rid!r}"
