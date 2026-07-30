"""Cycle 91 AC01-AC03 — stale ``in_progress:`` marker hygiene.

Regression tests for:
- AC01: `compile_wiki`'s premarker carries a birth-timestamp third segment
  (`in_progress:{pre_hash}:{unix_ts}`); `_marker_age_days` parses it and
  reports ``None`` ("age unknown") for legacy two-segment / unparseable /
  future-dated values.
- AC02: AC7's stale-marker warning annotates each key with its age and caps
  the per-key enumeration at ``STALE_MARKER_WARNING_CAP`` with an
  "and M more" suffix (supersedes cycle-25's full-enumeration choice per
  cycle-83 T6).
- AC03: `clear_stale_markers()` removes exactly the ``in_progress:``-valued
  entries under ``file_lock``, and `kb compile --clear-stale-markers` is the
  operator-invoked path to it (auto-deletion stays rejected per cycle-25
  Q10).
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from click.testing import CliRunner

from kb.cli import cli
from kb.compile import compiler as compiler_mod
from kb.compile.compiler import (
    STALE_MARKER_WARNING_CAP,
    _marker_age_days,
    clear_stale_markers,
    compile_wiki,
    load_manifest,
)


def _write_manifest(manifest_path: Path, data: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# AC01 — _marker_age_days parsing
# ---------------------------------------------------------------------------


def test_marker_age_days_parses_timestamped_marker():
    now = 1_800_000_000.0
    two_days_ago = int(now - 2 * 86400)
    age = _marker_age_days(f"in_progress:abc123:{two_days_ago}", now=now)
    assert age is not None
    assert abs(age - 2.0) < 0.01


def test_marker_age_days_legacy_two_segment_returns_none():
    assert _marker_age_days("in_progress:abc123") is None


def test_marker_age_days_garbage_timestamp_returns_none():
    assert _marker_age_days("in_progress:abc123:not-a-number") is None


def test_marker_age_days_future_timestamp_returns_none():
    now = 1_800_000_000.0
    assert _marker_age_days(f"in_progress:abc123:{int(now) + 9999}", now=now) is None


def test_marker_age_days_nonpositive_timestamp_returns_none():
    assert _marker_age_days("in_progress:abc123:0") is None
    assert _marker_age_days("in_progress:abc123:-5") is None


def test_premarker_write_carries_timestamp_segment(tmp_path, monkeypatch):
    """AC01 — the premarker written before ingest has 3 segments.

    Mirrors the cycle-25 AC6 revert-detection pattern: a stub ingest_source
    snapshots the manifest value mid-flight (before AC8's ``failed:``
    overwrite), then raises.
    """
    raw_dir = tmp_path / "raw"
    src = raw_dir / "articles" / "example.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Example\n\nContent.\n", encoding="utf-8")
    manifest_path = tmp_path / "hashes.json"
    _write_manifest(manifest_path, {})

    captured: dict[str, str] = {}

    def _snapshot_then_raise(source, **kwargs):
        manifest = load_manifest(manifest_path)
        for key, value in manifest.items():
            if str(value).startswith("in_progress:"):
                captured[key] = str(value)
        raise RuntimeError("simulated ingest failure")

    monkeypatch.setattr(compiler_mod, "ingest_source", _snapshot_then_raise)
    monkeypatch.setattr(compiler_mod, "scan_raw_sources", lambda _rd: [src])

    before = int(time.time())
    compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)
    after = int(time.time())

    assert captured, "premarker must be visible during ingest"
    (value,) = captured.values()
    match = re.fullmatch(r"in_progress:([0-9a-f]+):(\d+)", value)
    assert match, f"expected in_progress:{{hash}}:{{unix_ts}}; got {value!r}"
    ts = int(match.group(2))
    assert before <= ts <= after, "timestamp segment must be the marker's birth time"

    # AC8 contract unchanged: the normal exception overwrote the marker.
    final = load_manifest(manifest_path)
    (final_value,) = (v for k, v in final.items() if not k.startswith("_template/"))
    assert str(final_value).startswith("failed:")


# ---------------------------------------------------------------------------
# AC02 — AC7 warning: age annotation + cap
# ---------------------------------------------------------------------------


def _run_scan_only_compile(tmp_path, monkeypatch, caplog, manifest_data):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    manifest_path = tmp_path / "hashes.json"
    _write_manifest(manifest_path, manifest_data)
    monkeypatch.setattr(compiler_mod, "scan_raw_sources", lambda _rd: [])
    with caplog.at_level(logging.WARNING, logger="kb.compile.compiler"):
        compile_wiki(incremental=False, raw_dir=raw_dir, manifest_path=manifest_path)
    warning_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    stale = [m for m in warning_msgs if "stale in_progress" in m]
    assert stale, f"expected stale-marker warning; got {warning_msgs!r}"
    return stale[0]


def test_stale_warning_caps_enumeration_and_reports_overflow(tmp_path, monkeypatch, caplog):
    count = STALE_MARKER_WARNING_CAP + 2
    manifest = {f"raw/articles/stale{i:02d}.md": "in_progress:abc123" for i in range(count)}
    msg = _run_scan_only_compile(tmp_path, monkeypatch, caplog, manifest)

    assert f"{count} stale in_progress marker" in msg, "full count always reported"
    listed = re.findall(r"raw/articles/stale\d{2}\.md", msg)
    assert len(listed) == STALE_MARKER_WARNING_CAP, "per-key listing capped"
    # Keys are sorted, so the overflow is deterministic: the LAST two keys.
    assert f"stale{count - 1:02d}.md" not in msg
    assert "and 2 more" in msg


def test_stale_warning_below_cap_names_every_key_without_suffix(tmp_path, monkeypatch, caplog):
    manifest = {
        "raw/articles/stale1.md": "in_progress:abc123",
        "raw/articles/stale2.md": "in_progress:def456",
    }
    msg = _run_scan_only_compile(tmp_path, monkeypatch, caplog, manifest)
    assert "raw/articles/stale1.md" in msg
    assert "raw/articles/stale2.md" in msg
    assert "and 1 more" not in msg and "and 2 more" not in msg, (
        "no overflow suffix when everything is listed"
    )


def test_stale_warning_annotates_age_and_unknown(tmp_path, monkeypatch, caplog):
    two_days_ago = int(time.time()) - 2 * 86400
    manifest = {
        "raw/articles/aged.md": f"in_progress:abc123:{two_days_ago}",
        "raw/articles/legacy.md": "in_progress:def456",
    }
    msg = _run_scan_only_compile(tmp_path, monkeypatch, caplog, manifest)
    assert "raw/articles/aged.md (age 2.0d)" in msg
    assert "raw/articles/legacy.md (age unknown)" in msg


def test_stale_warning_mentions_clear_stale_markers_remedy(tmp_path, monkeypatch, caplog):
    manifest = {"raw/articles/stale1.md": "in_progress:abc123"}
    msg = _run_scan_only_compile(tmp_path, monkeypatch, caplog, manifest)
    assert "--clear-stale-markers" in msg


# ---------------------------------------------------------------------------
# AC03 — clear_stale_markers + CLI flag
# ---------------------------------------------------------------------------


def test_clear_stale_markers_removes_only_in_progress_entries(tmp_path):
    manifest_path = tmp_path / "hashes.json"
    data = {
        "raw/articles/ok.md": "deadbeef",
        "raw/articles/broken.md": "failed:cafe01",
        "_template/article": "feedface",
        "raw/articles/stale_legacy.md": "in_progress:abc123",
        "raw/articles/stale_stamped.md": f"in_progress:def456:{int(time.time())}",
    }
    _write_manifest(manifest_path, data)

    cleared = clear_stale_markers(manifest_path)

    assert cleared == [
        "raw/articles/stale_legacy.md",
        "raw/articles/stale_stamped.md",
    ]
    final = load_manifest(manifest_path)
    assert final == {
        "raw/articles/ok.md": "deadbeef",
        "raw/articles/broken.md": "failed:cafe01",
        "_template/article": "feedface",
    }


def test_clear_stale_markers_noop_returns_empty_and_preserves_manifest(tmp_path):
    manifest_path = tmp_path / "hashes.json"
    data = {"raw/articles/ok.md": "deadbeef", "_template/article": "feedface"}
    _write_manifest(manifest_path, data)
    raw_before = manifest_path.read_text(encoding="utf-8")

    assert clear_stale_markers(manifest_path) == []
    assert manifest_path.read_text(encoding="utf-8") == raw_before, (
        "no-op must not rewrite the manifest file"
    )


def _fake_compile_result():
    return {
        "sources_processed": 0,
        "pages_created": [],
        "pages_updated": [],
        "pages_skipped": [],
        "errors": [],
    }


def test_cli_compile_clear_stale_markers_flag(monkeypatch):
    calls = []

    def fake_clear(manifest_path=None):
        calls.append(manifest_path)
        return ["raw/articles/stale1.md", "raw/articles/stale2.md"]

    monkeypatch.setattr(compiler_mod, "clear_stale_markers", fake_clear)
    monkeypatch.setattr(
        compiler_mod, "compile_wiki", lambda *, incremental=True: _fake_compile_result()
    )

    result = CliRunner().invoke(cli, ["compile", "--clear-stale-markers"])

    assert result.exit_code == 0, result.output
    assert calls == [None]
    assert "Cleared 2 stale in_progress marker(s):" in result.output
    assert "raw/articles/stale1.md" in result.output
    assert "raw/articles/stale2.md" in result.output


def test_cli_compile_clear_stale_markers_flag_no_markers(monkeypatch):
    monkeypatch.setattr(compiler_mod, "clear_stale_markers", lambda manifest_path=None: [])
    monkeypatch.setattr(
        compiler_mod, "compile_wiki", lambda *, incremental=True: _fake_compile_result()
    )

    result = CliRunner().invoke(cli, ["compile", "--clear-stale-markers"])

    assert result.exit_code == 0, result.output
    assert "No stale in_progress markers found." in result.output


def test_cli_compile_without_flag_never_clears(monkeypatch):
    def _boom(manifest_path=None):  # pragma: no cover — must not run
        raise AssertionError("clear_stale_markers must not be called without the flag")

    monkeypatch.setattr(compiler_mod, "clear_stale_markers", _boom)
    monkeypatch.setattr(
        compiler_mod, "compile_wiki", lambda *, incremental=True: _fake_compile_result()
    )

    result = CliRunner().invoke(cli, ["compile"])

    assert result.exit_code == 0, result.output
    assert "Cleared" not in result.output
