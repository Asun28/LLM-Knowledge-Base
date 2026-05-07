"""Cycle 68 — AC11 regression pins for cli_backend Popen refactor.

These tests exercise the AC01 contract (subprocess.run → Popen + 2 daemon
reader threads + separate stdin write thread). FW-1: stdin write MUST run on
a separate thread from the stdout/stderr readers; otherwise large stdin +
large stdout deadlocks when OS pipe buffers fill (typically 64 KB Linux,
8 KB Windows).

Sub-conditions covered:
  C-AC03-stdin    — large stdin + large stdout completes without deadlock.
  C-AC03-platform — wait-after-terminate grace is 2.0s POSIX / 0.5s Windows.
  C-AC03-stderr   — stderr is capped at MAX_CLI_STDERR_BYTES with
                    daemon-reader chunked accumulation (NOT a single read).
  C-AC03-error-kinds — LLMError(kind=...) preserved across not_installed /
                    timeout / non-zero exit paths.
"""

from __future__ import annotations

import io
import subprocess
import sys
import time

import pytest

from kb.config import MAX_CLI_STDERR_BYTES, MAX_CLI_STDOUT_BYTES
from kb.utils.llm import LLMError, call_llm

# ── Real-subprocess deadlock-prevention test ─────────────────────────────────


def _build_python_backend_script(stdin_consumes: bool, stdout_bytes: int, stderr_bytes: int) -> str:
    """Build a python -c script that simulates a CLI backend.

    Output is `b'x\\n'` chunks so neither LONG_HEX nor LONG_B64 redaction
    matches consecutively (newline breaks the run).
    """
    parts = ["import sys"]
    if stdin_consumes:
        parts.append("sys.stdin.buffer.read()")
    if stdout_bytes:
        parts.append(f"sys.stdout.buffer.write(b'x\\n' * {stdout_bytes // 2})")
        parts.append("sys.stdout.buffer.flush()")
    if stderr_bytes:
        parts.append(f"sys.stderr.buffer.write(b'e\\n' * {stderr_bytes // 2})")
        parts.append("sys.stderr.buffer.flush()")
    return "; ".join(parts)


def test_cli_backend_popen_large_stdin_plus_large_stdout(monkeypatch):
    """FW-1: separate stdin/reader threads prevent buffer-fill deadlock.

    Backend writes ~3× MAX_CLI_STDOUT_BYTES (~6 MB) to stdout while
    consuming a 4 MB stdin. With subprocess.run(input=...) this deadlocks
    once the OS pipe buffer fills (~64 KB) because the parent process is
    writing stdin with no concurrent reader draining stdout.

    Real subprocess is essential here — a stubbed Popen with BytesIO can't
    reproduce OS-level pipe-buffer backpressure.
    """
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")

    stdout_bytes_target = MAX_CLI_STDOUT_BYTES * 3
    script = _build_python_backend_script(
        stdin_consumes=True,
        stdout_bytes=stdout_bytes_target,
        stderr_bytes=0,
    )

    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: sys.executable)
    monkeypatch.setattr(
        "kb.utils.cli_backend._build_cmd",
        lambda backend, model: [sys.executable, "-c", script],
    )

    big_prompt = "p" * (4 * 1024 * 1024)

    start = time.monotonic()
    result = call_llm(big_prompt, tier="write")
    elapsed = time.monotonic() - start

    # If FW-1 is violated, the call deadlocks until the test harness kills it.
    # Generous bound: 30s covers slow Windows file-IO; deadlock would hit
    # the LLM-layer 120s timeout instead.
    assert elapsed < 30, f"suspected deadlock — call took {elapsed:.1f}s"

    # Returned text capped at MAX_CLI_STDOUT_BYTES (post-redaction may shrink).
    assert len(result.encode("utf-8", errors="replace")) <= MAX_CLI_STDOUT_BYTES


def test_cli_backend_popen_stderr_capped(monkeypatch):
    """C-AC03-stderr: stderr accumulates in chunks, capped at MAX_CLI_STDERR_BYTES.

    Backend writes 4× MAX_CLI_STDERR_BYTES to stderr and exits non-zero so
    cli_backend reads stderr in the LLMError message path. The test asserts
    the LLMError message length is bounded — which only holds if the
    reader thread enforces the cap during accumulation.
    """
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")

    stderr_bytes_target = MAX_CLI_STDERR_BYTES * 4
    script = (
        f"import sys; "
        f"sys.stderr.buffer.write(b'e\\n' * {stderr_bytes_target // 2}); "
        f"sys.stderr.buffer.flush(); "
        f"sys.exit(1)"
    )

    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: sys.executable)
    monkeypatch.setattr(
        "kb.utils.cli_backend._build_cmd",
        lambda backend, model: [sys.executable, "-c", script],
    )

    with pytest.raises(LLMError) as exc_info:
        call_llm("trigger non-zero exit")

    # The LLMError message contains stderr (post-redaction). Assert the
    # underlying stderr capture was capped — envelope is the literal
    # "CLI backend 'ollama' exited with code 1: " prefix (~45 bytes); 200
    # bytes is generous coverage. Cycle 68 R1 Sonnet m1 closed: tightened
    # from +1024 to +200 so a future 2× cap drift would FAIL this assertion
    # (cycle-22 L5 vacuous-test envelope).
    msg = str(exc_info.value)
    assert len(msg) <= MAX_CLI_STDERR_BYTES + 200, (
        f"stderr cap appears bypassed — LLMError message is {len(msg)} bytes"
    )


# ── Platform-aware terminate+wait grace ───────────────────────────────────────


class _StubPopen:
    """Minimal Popen stub for platform-branch and error-kind tests.

    Tracks wait(timeout=...) calls so the platform branch can be verified
    without spawning real subprocesses.
    """

    def __init__(
        self,
        *,
        returncode: int | None = 0,
        stdout_bytes: bytes = b"",
        stderr_bytes: bytes = b"",
        wait_raises: type[BaseException] | None = None,
        wait_after_terminate_raises: bool = False,
    ):
        self.returncode = returncode if not wait_raises else None
        self.stdout = io.BytesIO(stdout_bytes)
        self.stderr = io.BytesIO(stderr_bytes)
        self.stdin = io.BytesIO()
        self._wait_raises = wait_raises
        self._wait_after_terminate_raises = wait_after_terminate_raises
        self._terminated = False
        self._killed = False
        self.wait_calls: list[float | None] = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self._wait_raises and not self._terminated:
            raise self._wait_raises("fake", timeout)
        if self._terminated and self._wait_after_terminate_raises:
            raise subprocess.TimeoutExpired("fake", timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def communicate(self, input=None, timeout=None):  # pragma: no cover — should not be used
        raise AssertionError(
            "FW-1 violation: cli_backend must NOT call proc.communicate() "
            "(use separate stdin write thread + reader threads instead)"
        )

    def terminate(self):
        self._terminated = True
        self.terminate_calls += 1
        if not self._wait_after_terminate_raises:
            self.returncode = -15

    def kill(self):
        self._killed = True
        self.kill_calls += 1
        self.returncode = -9


@pytest.mark.parametrize(
    ("platform_value", "expected_grace"),
    [
        ("linux", 2.0),
        ("darwin", 2.0),
        ("win32", 0.5),
    ],
)
def test_cli_backend_popen_platform_kill_branch(monkeypatch, platform_value, expected_grace):
    """C-AC03-platform: wait-after-terminate grace is 2.0s POSIX / 0.5s Windows.

    Stub Popen with a process that times out the initial wait(timeout=...).
    Cli_backend must terminate(), then wait again with the platform-specific
    grace, then kill() if still alive. Assert the second wait call's
    timeout argument matches the platform.
    """
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("sys.platform", platform_value)
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    stub = _StubPopen(
        returncode=None,
        wait_raises=subprocess.TimeoutExpired,
        wait_after_terminate_raises=False,
    )
    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", lambda *a, **kw: stub)

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt", tier="write")
    assert exc_info.value.kind == "timeout"

    # First wait fires TimeoutExpired (the call_llm 120s budget). Second
    # wait is the platform-aware terminate-grace.
    assert stub.terminate_calls >= 1, "expected terminate() after timeout"
    assert len(stub.wait_calls) >= 2, f"expected ≥2 wait() calls, got {stub.wait_calls}"
    grace_call = stub.wait_calls[1]
    assert grace_call == expected_grace, (
        f"platform={platform_value!r}: expected wait grace {expected_grace}s, got {grace_call!r}"
    )


# ── LLMError kind preservation across error paths ─────────────────────────────


def test_cli_backend_popen_preserves_error_kind_not_installed(monkeypatch):
    """C-AC03-error-kinds: kind=not_installed when binary is absent."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: None)

    def _no_popen(*args, **kwargs):
        raise AssertionError("subprocess.Popen must not be called when binary missing")

    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", _no_popen)

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    assert exc_info.value.kind == "not_installed"


def test_cli_backend_popen_preserves_error_kind_timeout(monkeypatch):
    """C-AC03-error-kinds: kind=timeout when wait() raises TimeoutExpired."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    stub = _StubPopen(
        returncode=None,
        wait_raises=subprocess.TimeoutExpired,
        wait_after_terminate_raises=False,
    )
    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", lambda *a, **kw: stub)

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    assert exc_info.value.kind == "timeout"


def test_cli_backend_popen_preserves_error_kind_nonzero_exit(monkeypatch):
    """C-AC03-error-kinds: generic LLMError on non-zero exit (no kind)."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    stub = _StubPopen(
        returncode=2,
        stdout_bytes=b"",
        stderr_bytes=b"backend reported failure",
    )
    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", lambda *a, **kw: stub)

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    # Generic non-zero exit: no kind set (matches existing AC22 behavior).
    assert "backend reported failure" in str(exc_info.value)
    assert exc_info.value.kind != "timeout"
    assert exc_info.value.kind != "not_installed"


def test_cli_backend_popen_kill_cascade_after_terminate_grace_timeout(monkeypatch):
    """C-AC03-platform: terminate→grace→kill→pass cascade when child is truly hung.

    Forces the deepest timeout branch:
      1. initial wait → TimeoutExpired (caller timeout fired)
      2. terminate() called
      3. wait(grace) → TimeoutExpired (process didn't honour SIGTERM)
      4. kill() called
      5. wait(grace) → TimeoutExpired (truly hung — caught + pass)
      6. LLMError(kind=timeout) raised

    Without this branch, a wedged child + a bug in the wait/kill cascade
    would silently leak the LLMError raise and surface as a non-timeout
    exception class. Covers production lines 308-313.
    """
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    stub = _StubPopen(
        returncode=None,
        wait_raises=subprocess.TimeoutExpired,
        wait_after_terminate_raises=True,
    )
    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", lambda *a, **kw: stub)

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt", tier="write")
    assert exc_info.value.kind == "timeout"
    # The full cascade must run: terminate, then kill (because grace-wait raised).
    assert stub.terminate_calls >= 1
    assert stub.kill_calls >= 1
    # Three waits total: caller timeout, terminate-grace, post-kill grace.
    assert len(stub.wait_calls) >= 3, f"expected ≥3 wait calls, got {stub.wait_calls}"
