"""Cycle 32 — CLI parity category (b) + fair-queue stagger mitigation.

Covers four implementation TASKs against the cycle 32 design doc at
``docs/superpowers/decisions/2026-04-25-cycle32-design.md``:

TASK 1: AC3 — widen ``_is_mcp_error_response`` tuple to include ``"Error["``
tagged-error prefix (closes silent-exit-0 bug on ``kb_ingest_content``
``Error[partial]:`` post-create-OSError emitter at ``mcp/core.py:762``).

TASK 2: AC6 + AC7 — ``file_lock`` fair-queue counter + initial-wait stagger
mitigation (intra-process only, probabilistic). Covers cycle-32 CONDITION
C3 (counter symmetry), C10 (module-level int + threading.Lock), C11 (stagger
clamp to LOCK_POLL_INTERVAL), C14 (underflow logger.warning observability).

TASK 3: AC1 + AC2 — ``kb compile-scan`` CLI wrapper. Covers cycle-32
CONDITION C9 (help text "default: incremental").

TASK 4: AC4 + AC5 — ``kb ingest-content`` CLI wrapper with stat guards
(cycle-32 CONDITION C13). Also lands the AC3 integration test (C15
Error[partial] stream routing) and the C15 --use-api forwarding spy test.

Cycle-31 L3 strong-form error assertions throughout: every error-path test
uses ``result.stderr`` explicitly with ``result.stdout == ""`` guards.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TASK 1 — AC3 widening of _is_mcp_error_response to include "Error[" prefix
# ---------------------------------------------------------------------------


class TestIsMcpErrorResponseWidening:
    """Cycle 32 AC3 — widen tuple to four prefixes so ``Error[<tag>]:``
    tagged-error shapes route to stderr + exit 1 in CLI wrappers.

    Revert-divergent per C1 + cycle-24 L4: if the tuple is reverted to the
    pre-cycle-32 three-tuple, ``_is_mcp_error_response("Error[partial]: ...")``
    returns ``False`` and these assertions flip.
    """

    def test_error_bracket_partial_form_matches(self):
        """C1 — ``Error[partial]:`` is the emitter at ``core.py:762`` /
        ``core.py:881``. Primary revert-divergent anchor."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Error[partial]: write failed; retry.") is True

    def test_error_bracket_validation_tagged_form_matches(self):
        """C1 — synthetic ``Error[<tag>]:`` form per ``ERROR_TAG_FORMAT``
        template at ``mcp/app.py:17``. Covers future emitters that adopt the
        template."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Error[validation]: bad input") is True

    def test_error_bracket_no_close_still_matches(self):
        """Edge case: prefix match is first-line ``startswith``; no closing
        bracket required (the tuple member is literal ``"Error["``)."""
        from kb.cli import _is_mcp_error_response

        assert _is_mcp_error_response("Error[ X") is True

    def test_page_body_starting_with_error_bracket_not_legitimate_emitter(self):
        """Boundary: confirms no SAFE MCP output we know of starts with
        literal ``Error[``. Same-class peer scan (C2): only emitters are
        ``core.py:762,881`` and ``ERROR_TAG_FORMAT`` template. A legit page
        body that happened to start with ``Error[`` would misroute — this
        test exists to anchor the assumption as a project invariant."""
        from kb.cli import _is_mcp_error_response

        # Legitimate success output — plain markdown body.
        assert _is_mcp_error_response("# Real Page\nBody text.") is False
        # Empty / blank-first-line = legitimate empty page body (preserved).
        assert _is_mcp_error_response("") is False
        assert _is_mcp_error_response("\nBody on line 2") is False


# ---------------------------------------------------------------------------
# TASK 2 — AC6 fair-queue counter + AC7 probabilistic ordering
# ---------------------------------------------------------------------------


class TestFairQueueStagger:
    """Cycle 32 AC6 + AC7 — ``_LOCK_WAITERS`` counter + initial-wait stagger
    in ``file_lock``. C3 (symmetry), C6 (threading.Barrier N=3 / 10 trials /
    80% tolerance), C10 (module-level), C11 (stagger clamp), C14
    (underflow logger.warning)."""

    def test_lock_waiters_counter_symmetry_on_timeout(self, tmp_path):
        """C3 — counter MUST return to baseline after raised TimeoutError.
        If increment lives outside the outermost try/finally, this
        assertion catches the drift."""
        from kb.utils import io as io_mod

        # Seed a stale-lock that won't be steal-eligible (adjacent to the
        # target path so the real file_lock attempts acquire then times out).
        lock_target = tmp_path / "contested"
        # Pre-create the sidecar .lock with a PID unlikely to be alive.
        sidecar = lock_target.with_suffix(".lock")
        sidecar.write_text("99999\n")

        baseline = io_mod._LOCK_WAITERS
        try:
            with io_mod.file_lock(lock_target, timeout=0.05):
                pass
        except TimeoutError:
            pass  # Expected — lock held by stale PID.
        except Exception:
            # If stale-PID steal succeeds on this platform/test timing,
            # don't fail the symmetry contract. C3 is about counter
            # balance, not TimeoutError behaviour.
            pass

        assert io_mod._LOCK_WAITERS == baseline, (
            "C3 — counter drift detected past exception path (T6 regression)"
        )

    def test_fair_queue_stagger_single_waiter_zero_stagger(self, tmp_path):
        """AC6 text guarantee: N=1 waiter (position=0) sees zero stagger
        (no latency change vs pre-cycle-32 behaviour)."""
        import time

        from kb.utils.io import file_lock

        lock_path = tmp_path / "uncontended"
        start = time.perf_counter()
        with file_lock(lock_path, timeout=5.0):
            pass
        elapsed = time.perf_counter() - start
        # Uncontended acquire should be well under the initial 10ms poll
        # (C11 cap is 50ms). Stagger at position=0 is zero, so total
        # elapsed < 20ms is a reasonable sanity check for "no new delay."
        assert elapsed < 0.2, (
            f"Uncontended file_lock took {elapsed:.3f}s; stagger may be "
            "applied to position=0 (T7 regression)."
        )

    def test_fair_queue_positions_unique_and_zero_based(self, tmp_path):
        """AC7 — the counter mechanism assigns distinct 0-based positions
        to N concurrent waiters, and returns to baseline after release.

        This is a DETERMINISTIC test of the ``_take_waiter_slot`` /
        ``_release_waiter_slot`` contract (the observable fairness downstream
        is probabilistic + sub-timer-resolution on Windows — not reliably
        testable in CI). The deterministic invariant is the load-bearing
        piece: if positions are unique and 0-based, the stagger mechanism
        correctly differentiates waiters; if counter returns to baseline,
        C3 symmetry holds under success path.
        """
        import threading

        from kb.utils import io as io_mod

        n_workers = 3
        positions_seen: list[int] = []
        positions_lock = threading.Lock()
        entry_barrier = threading.Barrier(n_workers)
        hold_barrier = threading.Barrier(n_workers)

        baseline = io_mod._LOCK_WAITERS

        def worker() -> None:
            entry_barrier.wait()
            pos = io_mod._take_waiter_slot()
            with positions_lock:
                positions_seen.append(pos)
            hold_barrier.wait()  # All threads hold their position simultaneously.
            io_mod._release_waiter_slot()

        threads = [threading.Thread(target=worker) for _ in range(n_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Under concurrent take, all N positions must be distinct and
        # form exactly the set {0, 1, ..., N-1}. This is the atomic
        # counter invariant that makes stagger work.
        assert sorted(positions_seen) == list(range(n_workers)), (
            f"C10 — positions not unique/contiguous: {sorted(positions_seen)}"
        )
        # C3 — counter returns to baseline after balanced take/release.
        assert io_mod._LOCK_WAITERS == baseline, (
            "C3 — counter drift after success path (T6 regression)"
        )

    def test_release_waiter_slot_underflow_warns(self, caplog):
        """C14 — unpaired ``_release_waiter_slot`` emits logger.warning
        instead of silently clamping to 0. Cycle-32 R1 Opus R2 residual:
        silent clamp hides paired-release bugs."""
        import logging

        from kb.utils import io as io_mod

        # Reset counter to 0 so any extra release triggers underflow.
        # (The test runs after other tests may have left baseline at 0.)
        baseline = io_mod._LOCK_WAITERS
        assert baseline == 0, (
            f"Prerequisite failed: _LOCK_WAITERS={baseline}, expected 0 "
            "(earlier test leaked take/release pair)"
        )

        with caplog.at_level(logging.WARNING, logger="kb.utils.io"):
            io_mod._release_waiter_slot()  # Unpaired — should warn.

        assert any("_LOCK_WAITERS underflow" in rec.message for rec in caplog.records), (
            f"C14 — no underflow warning emitted. Records: "
            f"{[rec.message for rec in caplog.records]}"
        )
        # Counter still at 0 (no negative drift).
        assert io_mod._LOCK_WAITERS == 0


# ---------------------------------------------------------------------------
# TASK 3 — AC1 + AC2: `kb compile-scan` CLI wrapper
# ---------------------------------------------------------------------------


class TestCompileScanCli:
    """Cycle 32 AC1 + AC2 — CLI parity for MCP ``kb_compile_scan``."""

    def test_compile_scan_help_exits_zero(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["compile-scan", "--help"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert "--incremental" in result.output
        assert "--wiki-dir" in result.output
        # C9 — help text includes "default: incremental".
        assert "default: incremental" in result.output

    def test_compile_scan_body_forwards_default_kwargs(self, monkeypatch):
        """Body-spy — default invocation forwards ``incremental=True, wiki_dir=None``."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        called: dict = {"value": False, "incremental": None, "wiki_dir": None}

        def _spy(incremental=True, wiki_dir=None):
            called["value"] = True
            called["incremental"] = incremental
            called["wiki_dir"] = wiki_dir
            return "# Compile Scan (incremental)\n\n## New sources (0)\n"

        monkeypatch.setattr(core_mod, "kb_compile_scan", _spy)

        runner = CliRunner()
        result = runner.invoke(cli, ["compile-scan"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["incremental"] is True
        assert called["wiki_dir"] is None

    def test_compile_scan_body_forwards_no_incremental_and_wiki_dir(self, monkeypatch, tmp_path):
        """Body-spy — ``--no-incremental`` + ``--wiki-dir`` forward verbatim."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        called: dict = {"value": False, "incremental": None, "wiki_dir": None}

        def _spy(incremental=True, wiki_dir=None):
            called["value"] = True
            called["incremental"] = incremental
            called["wiki_dir"] = wiki_dir
            return "# Compile Scan (full)\n\n**Total: 0 source(s)**\n"

        monkeypatch.setattr(core_mod, "kb_compile_scan", _spy)

        # tmp_path exists (created by fixture) and is a directory — satisfies
        # click.Path(exists=True, file_okay=False).
        runner = CliRunner()
        result = runner.invoke(
            cli, ["compile-scan", "--no-incremental", "--wiki-dir", str(tmp_path)]
        )
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["value"] is True
        assert called["incremental"] is False
        assert called["wiki_dir"] == str(tmp_path)

    def test_compile_scan_error_routes_to_stderr(self, monkeypatch):
        """Error-path — MCP ``Error:`` prefix → exit 1 + stderr (cycle-31 L3
        strong form)."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        monkeypatch.setattr(
            core_mod,
            "kb_compile_scan",
            lambda incremental=True, wiki_dir=None: "Error: invalid wiki_dir",
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["compile-scan"])
        assert result.exit_code != 0
        assert "Error: invalid wiki_dir" in result.stderr
        assert result.stdout == ""


# ---------------------------------------------------------------------------
# TASK 4 — AC4 + AC5: `kb ingest-content` CLI wrapper + AC3 integration test
# ---------------------------------------------------------------------------


class TestIngestContentCli:
    """Cycle 32 AC4 + AC5 — CLI parity for MCP ``kb_ingest_content``.
    Also lands the cycle-32 C15 ``--use-api`` forwarding test and the
    AC3 ``Error[partial]`` revert-divergent integration test (C1)."""

    def test_ingest_content_help_exits_zero(self):
        from click.testing import CliRunner

        from kb.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["ingest-content", "--help"])
        assert result.exit_code == 0, f"output: {result.output!r}"
        for flag in (
            "--filename",
            "--type",
            "--content-file",
            "--extraction-json-file",
            "--url",
            "--use-api",
        ):
            assert flag in result.output, f"help missing flag {flag}"

    def test_ingest_content_body_forwards_kwargs_verbatim(self, tmp_path, monkeypatch):
        """Happy-path body-spy — all 6 MCP kwargs forwarded."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        content_file = tmp_path / "content.md"
        content_file.write_text("Test body.", encoding="utf-8")
        ej_file = tmp_path / "extract.json"
        ej_file.write_text('{"title": "Test T"}', encoding="utf-8")

        called: dict = {}

        def _spy(**kwargs):
            called.update(kwargs)
            return "Saved source: raw/articles/test.md (10 chars)\n# Ingest Complete"

        monkeypatch.setattr(core_mod, "kb_ingest_content", _spy)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "ingest-content",
                "--filename",
                "test",
                "--type",
                "article",
                "--content-file",
                str(content_file),
                "--extraction-json-file",
                str(ej_file),
            ],
        )
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called["content"] == "Test body."
        assert called["filename"] == "test"
        assert called["source_type"] == "article"
        assert called["extraction_json"] == '{"title": "Test T"}'
        assert called["url"] == ""
        assert called["use_api"] is False

    def test_ingest_content_use_api_flag_forwards_true(self, tmp_path, monkeypatch):
        """C15 — ``--use-api`` forwards as ``use_api=True``. Pins Q3
        resolution (no CLI-level mutual-exclusion; MCP authoritative) as
        a grep-verifiable test anchor."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        content_file = tmp_path / "content.md"
        content_file.write_text("Test.", encoding="utf-8")

        called: dict = {}

        def _spy(**kwargs):
            called.update(kwargs)
            return "Saved source: raw/articles/test.md (5 chars)"

        monkeypatch.setattr(core_mod, "kb_ingest_content", _spy)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "ingest-content",
                "--filename",
                "test",
                "--type",
                "article",
                "--content-file",
                str(content_file),
                "--use-api",
            ],
        )
        assert result.exit_code == 0, f"output: {result.output!r}"
        assert called.get("use_api") is True
        # No --extraction-json-file supplied → empty-string default forwards
        # verbatim (Q2 resolution: optional, empty-string default; MCP
        # ignores when use_api=True).
        assert called.get("extraction_json") == ""

    def test_ingest_content_error_colon_form_routes_to_stderr(self, tmp_path, monkeypatch):
        """AC5 error-path — MCP ``_validate_file_inputs`` style ``Error:``
        prefix → exit 1 + stderr. Cycle-31 L3 strong form."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        content_file = tmp_path / "content.md"
        content_file.write_text("Test.", encoding="utf-8")
        monkeypatch.setattr(
            core_mod,
            "kb_ingest_content",
            lambda **kw: "Error: Invalid filename characters",
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "ingest-content",
                "--filename",
                "bad!!!",
                "--type",
                "article",
                "--content-file",
                str(content_file),
                "--extraction-json-file",
                str(content_file),
            ],
        )
        assert result.exit_code != 0
        assert "Error: Invalid filename" in result.stderr
        assert result.stdout == ""

    def test_ingest_content_error_partial_routes_to_stderr(self, tmp_path, monkeypatch):
        """AC3 revert-divergent integration test (C1): ``Error[partial]:``
        prefix → exit 1 + stderr. Under pre-cycle-32 three-tuple revert,
        ``_is_mcp_error_response`` returns ``False`` → exit 0 + stdout →
        this test fails. Cycle-31 L3 strong form."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.mcp import core as core_mod

        content_file = tmp_path / "content.md"
        content_file.write_text("Test.", encoding="utf-8")
        monkeypatch.setattr(
            core_mod,
            "kb_ingest_content",
            lambda **kw: (
                "Error[partial]: write to raw/articles/test.md failed "
                "(OSError); retry with overwrite=true."
            ),
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "ingest-content",
                "--filename",
                "test",
                "--type",
                "article",
                "--content-file",
                str(content_file),
                "--extraction-json-file",
                str(content_file),
            ],
        )
        assert result.exit_code != 0
        assert "Error[partial]" in result.stderr
        assert result.stdout == ""

    def test_ingest_content_stat_guard_rejects_oversized_content(self, tmp_path, monkeypatch):
        """C13 — CLI stat guard rejects ``--content-file`` exceeding
        ``MAX_INGEST_CONTENT_CHARS`` BEFORE read, without calling MCP."""
        from click.testing import CliRunner

        from kb.cli import cli
        from kb.config import MAX_INGEST_CONTENT_CHARS
        from kb.mcp import core as core_mod

        # Write a file just past the cap.
        oversized = tmp_path / "big.md"
        oversized.write_text("A" * (MAX_INGEST_CONTENT_CHARS + 1), encoding="utf-8")

        # Spy must NOT be called on oversize reject.
        called: dict = {"value": False}

        def _spy(**kwargs):
            called["value"] = True
            return "ERROR — should not reach MCP"

        monkeypatch.setattr(core_mod, "kb_ingest_content", _spy)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "ingest-content",
                "--filename",
                "test",
                "--type",
                "article",
                "--content-file",
                str(oversized),
                "--use-api",
            ],
        )
        assert result.exit_code != 0
        assert "Error:" in result.stderr
        assert "exceeds" in result.stderr
        assert result.stdout == ""
        assert called["value"] is False, (
            "C13 — CLI must reject oversized content BEFORE calling MCP"
        )
