"""CLI subprocess backend for KB LLM calls.

Dispatches prompts to locally-installed AI CLI tools (Ollama, Gemini CLI,
OpenCode, Codex CLI, Kimi, QWEN, DeepSeek, ZAI) via subprocess stdin/stdout.
Never uses shell=True. Prompt delivered via stdin for all backends except
Gemini (--prompt arg, documented as weaker isolation per T8).
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading

import jsonschema

from kb.config import (
    CLI_BACKEND_ENV_INJECT,
    CLI_INSTALL_HINTS,
    CLI_MAX_CONCURRENCY,
    CLI_PROMPT_VIA_ARG,
    CLI_SAFE_ENV_KEYS,
    CLI_TOOL_COMMANDS,
    MAX_CLI_STDERR_BYTES,
    MAX_CLI_STDOUT_BYTES,
)

# Reader-thread chunk size — small enough to drain pipes promptly, large enough
# to avoid per-byte syscall overhead on multi-MB outputs (cycle-68 AC01).
_READ_CHUNK_BYTES: int = 64 * 1024

logger = logging.getLogger(__name__)

# Max bytes to scan for a balanced JSON object in free-form CLI output.
MAX_CLI_JSON_SCAN_BYTES: int = 65_536

# Model name placeholder — only [A-Za-z0-9._:/-] chars are legal (T1).
_MODEL_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:/-]*$")

# Derived from CLI_BACKEND_ENV_INJECT plus 4 standalone keys (Anthropic /
# Firecrawl / MiMo wrappers don't go through the backend registry). Safe to
# capture at import: CLI_BACKEND_ENV_INJECT is a module-literal dict with no
# os.environ read in its definition (cycle-19 L2 IR-1).
_SCRUB_KEYS: frozenset[str] = frozenset(
    {"ANTHROPIC_API_KEY", "FIRECRAWL_API_KEY", "MIMOCODING_API_KEY", "MIMOCHAT_API_KEY"}
    | {key for keys in CLI_BACKEND_ENV_INJECT.values() for key in keys}
)

# ── Semaphore pool (T6) ───────────────────────────────────────────────────────
_semaphore_lock = threading.Lock()
_backend_semaphores: dict[str, threading.Semaphore] = {}


def _get_semaphore(backend: str) -> threading.Semaphore:
    if backend not in _backend_semaphores:
        with _semaphore_lock:
            if backend not in _backend_semaphores:
                _backend_semaphores[backend] = threading.Semaphore(CLI_MAX_CONCURRENCY)
    return _backend_semaphores[backend]


# ── Public helpers ────────────────────────────────────────────────────────────


def check_cli_available(backend: str) -> bool:
    """Return True if the CLI binary for ``backend`` is on PATH."""
    binary = _backend_executable(backend)
    return shutil.which(binary) is not None


def _backend_executable(backend: str) -> str:
    """Return the executable name to pass to ``subprocess.Popen``."""
    binary = CLI_TOOL_COMMANDS[backend][0]
    if backend == "codex" and os.name == "nt":
        return "codex.cmd"
    return binary


def _build_cmd(backend: str, model: str) -> list[str]:
    """Build the subprocess argv for ``backend`` with ``model`` substituted."""
    if not _MODEL_RE.match(model):
        from kb.utils.llm import LLMError  # local import avoids circular dep

        raise LLMError(
            f"Invalid model name {model!r} for backend {backend!r}: "
            "only [A-Za-z0-9._:/-] chars are allowed (T1).",
            kind="invalid_request",
        )
    cmd = [tok.replace("{model}", model) for tok in CLI_TOOL_COMMANDS[backend]]
    cmd[0] = _backend_executable(backend)
    if backend == "codex" and model:
        cmd.extend(["--model", model])
    return cmd


def _postprocess_stdout(backend: str, stdout_text: str) -> str:
    """Extract model text from backend-specific structured output."""
    if backend != "codex":
        return stdout_text.strip()

    last_agent_text = None
    for line in stdout_text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            last_agent_text = item["text"]
    return last_agent_text.strip() if last_agent_text is not None else stdout_text.strip()


def _scrub_env(backend: str) -> dict[str, str]:
    """Build a scrubbed subprocess environment (T3).

    Allowlist-only: CLI_SAFE_ENV_KEYS from the current process env, plus
    any per-backend secret keys defined in CLI_BACKEND_ENV_INJECT.
    """
    env: dict[str, str] = {}
    for key in CLI_SAFE_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    for key in CLI_BACKEND_ENV_INJECT.get(backend, ()):
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    return env


def _check_no_secrets_on_argv(argv: list[str]) -> None:
    """Raise LLMError if any actual env secret value appears in argv (T8, AC16).

    Scrub keys come from ``_SCRUB_KEYS`` (module top).

    Substring vs exact-match: cycle-65 Step 09 background review surfaced that
    secrets.compare_digest equality alone misses the embedded-secret leak (e.g.,
    `["kb", "--header", f"Authorization: Bearer {ANTHROPIC_API_KEY}"]` would slip
    past an equality check because no argv element EQUALS the bare secret).
    Substring containment catches both the bare-equality and embedded-in-flag
    cases. Timing leak via `in`-search is acceptable in the CLI subprocess
    threat model (no remote attacker observes argv-construction timing).
    """
    from kb.utils.llm import LLMError  # local import avoids circular dep

    for key in _SCRUB_KEYS:
        secret_value = os.environ.get(key, "")
        if not secret_value:
            continue

        for elem in argv:
            if secret_value in elem:
                raise LLMError(
                    f"Refusing to place env secret {key!r} on subprocess argv (T8, AC16).",
                    kind="invalid_request",
                )


def _read_stream_capped(stream, cap: int) -> bytes:
    """Read from a Popen pipe, accumulate up to ``cap`` bytes.

    Cycle 68 AC01 / FW-1: continues reading-and-discarding past the cap so the
    child process never blocks on a full pipe buffer. Without this, a child
    that produces > cap stdout would deadlock the moment the parent's pipe
    buffer (~64 KB) fills.

    Returns the accumulated bytes (length ≤ cap). Errors during read (e.g.,
    closed pipe after kill) are swallowed — the caller surfaces real failure
    via returncode.
    """
    chunks: list[bytes] = []
    accumulated = 0
    while True:
        try:
            chunk = stream.read(_READ_CHUNK_BYTES)
        except (OSError, ValueError):
            break
        if not chunk:
            break
        if accumulated < cap:
            take = min(cap - accumulated, len(chunk))
            chunks.append(chunk[:take])
            accumulated += take
        # past cap: drop chunk, keep draining so producer doesn't block
    return b"".join(chunks)


def _write_stdin_close(proc: subprocess.Popen, data: bytes | None) -> None:
    """Write ``data`` to ``proc.stdin`` on a separate thread (FW-1).

    Closes stdin when done OR if the child has already exited (BrokenPipeError
    is an OSError subclass and is caught by the OSError clauses below).
    Cycle 68 R1 Sonnet M2 closed: catch ValueError on write too — real pipes
    raise BrokenPipeError (OSError subclass), but BytesIO-backed test stubs
    raise ValueError on writes after close, which would otherwise propagate.
    """
    if proc.stdin is None:
        return
    try:
        if data is not None:
            proc.stdin.write(data)
    except (OSError, ValueError):
        pass
    finally:
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass


def call_cli(
    prompt: str,
    *,
    backend: str,
    model: str,
    timeout: float,
) -> str:
    """Call a CLI tool subprocess and return its stdout.

    Prompt is delivered via stdin for all backends except those in
    CLI_PROMPT_VIA_ARG (currently just ``gemini``, which uses ``--prompt``).

    Args:
        prompt: The prompt text to send to the CLI tool.
        backend: Backend key (e.g. "ollama", "gemini").
        model: Model name; empty string for single-model CLIs.
        timeout: Hard timeout in seconds.

    Returns:
        Decoded, stripped stdout string.

    Raises:
        LLMError(kind="not_installed"): CLI binary not found on PATH.
        LLMError(kind="timeout"): Subprocess exceeded timeout.
        LLMError: On non-zero exit code.
    """
    from kb.utils.llm import LLMError, _redact_secrets  # local to avoid circular

    if not check_cli_available(backend):
        hint = CLI_INSTALL_HINTS.get(backend, "")
        raise LLMError(
            f"CLI backend {backend!r} binary not found on PATH. {hint}".strip(),
            kind="not_installed",
        )

    cmd = _build_cmd(backend, model)
    # T8: check model-override and other static argv elements for secrets before
    # any prompt delivery (covers all backends, not just Gemini --prompt path).
    _check_no_secrets_on_argv(cmd)

    # Determine stdin vs argv prompt delivery.
    if backend in CLI_PROMPT_VIA_ARG:
        cmd = cmd + ["--prompt", prompt]
        stdin_input: bytes | None = None
        # T8: also check the prompt itself when placed on argv.
        _check_no_secrets_on_argv(["--prompt", prompt])
    else:
        stdin_input = prompt.encode("utf-8")

    sem = _get_semaphore(backend)
    sem.acquire()
    raw_stdout: bytes = b""
    raw_stderr: bytes = b""
    returncode: int | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin_input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=_scrub_env(backend),
        )

        stdout_holder: dict[str, bytes] = {}
        stderr_holder: dict[str, bytes] = {}

        def _drain_stdout() -> None:
            stdout_holder["data"] = _read_stream_capped(proc.stdout, MAX_CLI_STDOUT_BYTES)

        def _drain_stderr() -> None:
            stderr_holder["data"] = _read_stream_capped(proc.stderr, MAX_CLI_STDERR_BYTES)

        stdout_thread = threading.Thread(target=_drain_stdout, daemon=True)
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        stdin_thread: threading.Thread | None = None
        if stdin_input is not None:
            # FW-1: stdin write on a SEPARATE thread, never proc.communicate().
            stdin_thread = threading.Thread(
                target=_write_stdin_close, args=(proc, stdin_input), daemon=True
            )
            stdin_thread.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            grace = 0.5 if sys.platform == "win32" else 2.0
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    pass  # truly hung; reader threads are daemonized
            # Cycle 68 R2 Codex M3 closed: explicitly close pipes from the
            # main thread so any blocked writer/reader surfaces an error and
            # exits before we join. Without this, a writer mid-write to a
            # buffered pipe could survive past the raised LLMError.
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            # Drain readers/writer briefly; they exit on EOF after kill.
            if stdin_thread is not None:
                stdin_thread.join(timeout=0.5)
            stdout_thread.join(timeout=0.5)
            stderr_thread.join(timeout=0.5)
            raise LLMError(
                f"CLI timeout after {timeout}s for backend {backend!r}",
                kind="timeout",
            )

        # Process exited normally — join threads to collect their accumulated bytes.
        if stdin_thread is not None:
            stdin_thread.join(timeout=1.0)
        stdout_thread.join(timeout=5.0)
        stderr_thread.join(timeout=5.0)

        raw_stdout = stdout_holder.get("data", b"")
        raw_stderr = stderr_holder.get("data", b"")
        returncode = proc.returncode
    finally:
        sem.release()

    # Redact stderr before any logging (T3).
    stderr_text = raw_stderr.decode("utf-8", errors="replace")
    stderr_safe = _redact_secrets(stderr_text)

    if returncode != 0:
        raise LLMError(f"CLI backend {backend!r} exited with code {returncode}: {stderr_safe}")

    if stderr_safe:
        logger.debug("cli_backend %s stderr: %s", backend, stderr_safe)

    # Cap is enforced inside the reader thread (cycle-68 AC01 / R1-F6); the
    # cycle-21 OOM-on-giant-response residual risk is now retired — Popen
    # streams chunks rather than buffering the entire stdout.
    stdout_text = raw_stdout.decode("utf-8", errors="replace")
    return _redact_secrets(_postprocess_stdout(backend, stdout_text)).strip()


# ── JSON extraction ───────────────────────────────────────────────────────────


def _extract_json_from_text(text: str, schema: dict) -> dict:
    """Extract and validate a JSON object from free-form CLI output.

    Three-stage extraction followed by jsonschema validation:
    1. Try json.loads on the full text.
    2. Strip a single Markdown code fence (```json ... ``` or ``` ... ```).
    3. Depth-bounded balanced brace scan (stack, capped at MAX_CLI_JSON_SCAN_BYTES).

    Raises:
        LLMError(kind="json_parse_error"): if all stages fail or schema mismatch.
    """
    from kb.utils.llm import LLMError  # local import avoids circular dep

    preview = text[:300]

    def _validate(candidate: object) -> dict:
        if not isinstance(candidate, dict):
            raise LLMError(
                f"CLI JSON extraction: expected dict, got {type(candidate).__name__}. "
                f"Preview: {preview!r}",
                kind="json_parse_error",
            )
        try:
            jsonschema.validate(candidate, schema)
        except jsonschema.ValidationError as exc:
            raise LLMError(
                f"CLI JSON schema validation failed: {exc.message}. Preview: {preview!r}",
                kind="json_parse_error",
            ) from exc
        return candidate

    # Stage 1: try whole response as JSON.
    # Only catch JSONDecodeError here — a schema-validation LLMError means the
    # JSON was valid but wrong; surfacing it immediately is more actionable than
    # falling through to a "no parseable JSON" fallback error.
    stripped = text.strip()
    try:
        return _validate(json.loads(stripped))
    except json.JSONDecodeError:
        pass

    # Stage 2: strip a single Markdown code fence (bounded input, T4).
    fence_match = re.fullmatch(
        r"```(?:json)?\s*\n?([\s\S]*?)\n?```",
        stripped[:MAX_CLI_JSON_SCAN_BYTES],
        re.IGNORECASE,
    )
    if fence_match:
        try:
            return _validate(json.loads(fence_match.group(1).strip()))
        except json.JSONDecodeError:
            pass

    # Stage 3: depth-bounded balanced brace scan (capped at MAX_CLI_JSON_SCAN_BYTES).
    # Unmatched closing braces are ignored (depth never goes below 0) so that
    # free-form text like "done}" before a valid JSON object doesn't poison the scan.
    scan_text = text[:MAX_CLI_JSON_SCAN_BYTES]
    depth = 0
    start = -1
    for i, ch in enumerate(scan_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                candidate_str = scan_text[start : i + 1]
                try:
                    return _validate(json.loads(candidate_str))
                except (json.JSONDecodeError, LLMError):
                    start = -1  # reset and continue scanning

    raise LLMError(
        f"CLI backend returned no parseable JSON. Preview: {preview!r}",
        kind="json_parse_error",
    )


def call_cli_json(
    prompt: str,
    *,
    backend: str,
    model: str,
    timeout: float,
    schema: dict,
) -> dict:
    """Call a CLI tool and extract structured JSON matching ``schema``.

    Calls call_cli, then extracts and validates JSON from the text response.

    Raises:
        LLMError(kind="json_parse_error"): if JSON cannot be extracted or validated.
        LLMError(kind="not_installed"): see call_cli.
        LLMError(kind="timeout"): see call_cli.
    """
    text = call_cli(prompt, backend=backend, model=model, timeout=timeout)
    return _extract_json_from_text(text, schema)
