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
import threading

import jsonschema

from kb.config import (
    CLI_BACKEND_ENV_INJECT,
    CLI_INSTALL_HINTS,
    CLI_MAX_CONCURRENCY,
    CLI_PROMPT_VIA_ARG,
    CLI_SAFE_ENV_KEYS,
    CLI_TOOL_COMMANDS,
    MAX_CLI_STDOUT_BYTES,
)

logger = logging.getLogger(__name__)

# Max bytes to scan for a balanced JSON object in free-form CLI output.
MAX_CLI_JSON_SCAN_BYTES: int = 65_536

# Pattern to detect token-shaped secrets in argv elements (T8).
_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    r"sk-[A-Za-z0-9_\-]{10,}|Bearer\s+\S+|ghp_[A-Za-z0-9]{10,}"
)

# Model name placeholder — only [A-Za-z0-9._:/-] chars are legal (T1).
_MODEL_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:/-]*$")

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
    binary = CLI_TOOL_COMMANDS[backend][0]
    return shutil.which(binary) is not None


def _build_cmd(backend: str, model: str) -> list[str]:
    """Build the subprocess argv for ``backend`` with ``model`` substituted."""
    if not _MODEL_RE.match(model):
        from kb.utils.llm import LLMError  # local import avoids circular dep

        raise LLMError(
            f"Invalid model name {model!r} for backend {backend!r}: "
            "only [A-Za-z0-9._:/-] chars are allowed (T1).",
            kind="invalid_request",
        )
    return [tok.replace("{model}", model) for tok in CLI_TOOL_COMMANDS[backend]]


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
    """Raise LLMError if any argv element looks like a secret token (T8)."""
    for elem in argv:
        if _TOKEN_PATTERN.search(elem):
            from kb.utils.llm import LLMError  # local import avoids circular dep

            raise LLMError(
                "Refusing to place a token-shaped string on subprocess argv (T8).",
                kind="invalid_request",
            )


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
    try:
        try:
            result = subprocess.run(
                cmd,
                input=stdin_input,
                capture_output=True,
                timeout=timeout,
                shell=False,
                env=_scrub_env(backend),
            )
        except subprocess.TimeoutExpired:
            raise LLMError(
                f"CLI timeout after {timeout}s for backend {backend!r}",
                kind="timeout",
            )
    finally:
        sem.release()

    # Redact stderr before any logging (T3).
    stderr_text = result.stderr[:500].decode("utf-8", errors="replace")
    stderr_safe = _redact_secrets(stderr_text)

    if result.returncode != 0:
        raise LLMError(
            f"CLI backend {backend!r} exited with code {result.returncode}: {stderr_safe}"
        )

    if stderr_safe:
        logger.debug("cli_backend %s stderr: %s", backend, stderr_safe)

    # Cap and redact stdout before returning (T3, T5).
    # Accepted risk: subprocess.run buffers all stdout before this slice runs.
    # The 2 MB cap limits downstream processing cost; OOM from a giant response
    # before the slice is the residual risk accepted in cycle-21 plan gate (gap 8).
    raw_stdout = result.stdout[:MAX_CLI_STDOUT_BYTES]
    stdout_text = raw_stdout.decode("utf-8", errors="replace")
    return _redact_secrets(stdout_text).strip()


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
    stripped = text.strip()
    try:
        return _validate(json.loads(stripped))
    except (json.JSONDecodeError, LLMError):
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
        except (json.JSONDecodeError, LLMError):
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
