"""Cycle 21 — CLI subprocess backend tests (AC17-AC30).

Cycle 68 AC01 — migrated from ``subprocess.run`` mocks to ``subprocess.Popen``
factories. Test intent is unchanged; the stub now adheres to the AC01 contract
(separate stdin write thread + chunked stdout/stderr readers).
"""

import io
import subprocess
from unittest.mock import MagicMock

import pytest

from kb.config import get_cli_backend, get_cli_model
from kb.utils.cli_backend import (
    _extract_json_from_text,
    check_cli_available,
)
from kb.utils.llm import LLMError, call_llm, call_llm_json

# ── AC01 Popen-stub helpers (cycle 68 migration) ─────────────────────────────


class _FakePopen:
    """Minimal Popen stub for AC01 contract.

    Mimics ``subprocess.Popen`` interface used by ``cli_backend.call_cli``:
    stdin/stdout/stderr (file-like), poll(), wait(timeout), terminate(),
    kill(), returncode.
    """

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        wait_raises: type[BaseException] | None = None,
    ):
        self.returncode = returncode if wait_raises is None else None
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.stdin = io.BytesIO()
        self._wait_raises = wait_raises
        self._terminated = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self._wait_raises and not self._terminated:
            raise self._wait_raises("fake", timeout)
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self._terminated = True
        if self.returncode is None:
            self.returncode = -15

    def kill(self):
        self._terminated = True
        if self.returncode is None:
            self.returncode = -9


def _make_popen(captured, *, returncode=0, stdout=b"", stderr=b"", wait_raises=None):
    """Build a Popen factory that records cmd/env/shell/input into ``captured``."""

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["shell"] = kwargs.get("shell")
        captured["env"] = kwargs.get("env")
        proc = _FakePopen(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            wait_raises=wait_raises,
        )
        original_write = proc.stdin.write

        def tracked_write(data):
            captured["input"] = (captured.get("input") or b"") + data
            return original_write(data)

        proc.stdin.write = tracked_write
        return proc

    return fake_popen


# ── AC17: Anthropic path unchanged when KB_LLM_BACKEND unset ─────────────────


def test_anthropic_path_unchanged(monkeypatch):
    """subprocess.Popen must never be called on the default anthropic path."""
    monkeypatch.delenv("KB_LLM_BACKEND", raising=False)

    def _raise(*args, **kwargs):
        raise AssertionError("subprocess.Popen was called on the anthropic path")

    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", _raise)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="hello")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    monkeypatch.setattr("kb.utils.llm.get_client", lambda: mock_client)

    result = call_llm("test prompt")
    assert result == "hello"
    mock_client.messages.create.assert_called_once()


# ── AC18: stdin path for ollama ───────────────────────────────────────────────


def test_call_cli_stdin_path(monkeypatch):
    """call_llm with KB_LLM_BACKEND=ollama delivers prompt via stdin."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b"result text\n"),
    )

    result = call_llm("hello world", tier="write")
    assert result == "result text"
    assert captured["input"] == b"hello world"
    assert "--prompt" not in captured["cmd"]


# ── AC19: --prompt arg path for gemini ───────────────────────────────────────


def test_call_cli_arg_path_gemini(monkeypatch):
    """call_llm with KB_LLM_BACKEND=gemini delivers prompt via --prompt arg, not stdin."""
    monkeypatch.setenv("KB_LLM_BACKEND", "gemini")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/gemini")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b"gemini says hi\n"),
    )

    result = call_llm("my prompt", tier="write")
    assert result == "gemini says hi"
    assert "--prompt" in captured["cmd"]
    assert "my prompt" in captured["cmd"]
    # No stdin written: gemini path uses DEVNULL (no stdin write thread).
    assert captured.get("input") is None


def test_call_cli_codex_exec_jsonl_path(monkeypatch):
    """Codex CLI uses `codex exec --json` and returns only the agent message."""
    monkeypatch.setenv("KB_LLM_BACKEND", "codex")
    monkeypatch.setenv("KB_CLI_MODEL_WRITE", "gpt-5.4-mini")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/codex")

    captured = {}
    stdout = (
        b'{"type":"thread.started","thread_id":"t1"}\n'
        b'{"type":"item.completed","item":{"type":"agent_message",'
        b'"text":"KB_CODEX_BACKEND_OK"}}\n'
        b"Reading additional input from stdin...\n"
    )
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=stdout),
    )

    result = call_llm("Reply exactly KB_CODEX_BACKEND_OK.", tier="write")
    assert result == "KB_CODEX_BACKEND_OK"
    assert captured["cmd"][1:4] == ["exec", "--json", "--ephemeral"]
    assert "-q" not in captured["cmd"]
    assert "--model" in captured["cmd"]
    assert "gpt-5.4-mini" in captured["cmd"]
    assert captured["input"] == b"Reply exactly KB_CODEX_BACKEND_OK."
    assert captured["shell"] is False


# ── AC20: LLMError(kind="not_installed") when binary missing ─────────────────


def test_call_cli_not_installed(monkeypatch):
    """LLMError(kind="not_installed") raised without spawning subprocess."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: None)

    def _raise(*args, **kwargs):
        raise AssertionError("subprocess.Popen should not be called")

    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", _raise)

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    assert exc_info.value.kind == "not_installed"
    assert "ollama" in str(exc_info.value).lower()


# ── AC21: LLMError(kind="timeout") on TimeoutExpired ─────────────────────────


def test_call_cli_timeout(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, wait_raises=subprocess.TimeoutExpired),
    )

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    assert exc_info.value.kind == "timeout"


# ── AC22: LLMError on nonzero exit ───────────────────────────────────────────


def test_call_cli_nonzero_exit(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=1, stderr=b"Error: model not found"),
    )

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    assert "Error: model not found" in str(exc_info.value)


# ── AC23: call_cli_json with bare JSON ───────────────────────────────────────


def test_call_cli_json_bare_json(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b'{"title": "foo"}'),
    )

    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    result = call_llm_json("prompt", schema=schema)
    assert result == {"title": "foo"}


# ── AC24: call_cli_json with fenced JSON ─────────────────────────────────────


def test_call_cli_json_fenced(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b'```json\n{"title":"bar"}\n```'),
    )

    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    result = call_llm_json("prompt", schema=schema)
    assert result == {"title": "bar"}


# ── AC25: call_cli_json schema validation failure ─────────────────────────────


def test_call_cli_json_schema_validated(monkeypatch):
    """Valid JSON that fails schema validation raises LLMError(kind="json_parse_error")."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    # Missing required field "title"
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b'{"body": "no title here"}'),
    )

    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }
    with pytest.raises(LLMError) as exc_info:
        call_llm_json("prompt", schema=schema)
    assert exc_info.value.kind == "json_parse_error"


# ── AC26: call_cli_json no JSON in response ───────────────────────────────────


def test_call_cli_json_no_json(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b"I cannot do that."),
    )

    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    with pytest.raises(LLMError) as exc_info:
        call_llm_json("prompt", schema=schema)
    assert exc_info.value.kind == "json_parse_error"
    assert "I cannot do that." in str(exc_info.value)


# ── AC27: get_cli_backend raises ValueError on unknown backend ────────────────


def test_get_cli_backend_invalid(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "unsupported_backend")
    with pytest.raises(ValueError) as exc_info:
        get_cli_backend()
    # Must NOT echo the raw value in the error message (T7)
    assert "unsupported_backend" not in str(exc_info.value)


# ── AC28: check_cli_available true/false ─────────────────────────────────────


def test_check_cli_available_true_false(monkeypatch):
    def fake_which(binary):
        return "/usr/bin/ollama" if binary == "ollama" else None

    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", fake_which)

    assert check_cli_available("ollama") is True
    assert check_cli_available("gemini") is False


# ── AC29: get_cli_model respects KB_CLI_MODEL_WRITE env override ──────────────


def test_cli_model_env_override(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setenv("KB_CLI_MODEL_WRITE", "mistral:latest")
    assert get_cli_model("write") == "mistral:latest"


def test_cli_model_env_override_scan(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.delenv("KB_CLI_MODEL_SCAN", raising=False)
    # Default for ollama scan tier
    assert get_cli_model("scan") == "llama3.2"


def test_get_cli_model_invalid_tier(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    with pytest.raises(ValueError):
        get_cli_model("invalid_tier")


# ── AC30: stderr secret redacted from LLMError message ───────────────────────


def test_stderr_redacted(monkeypatch):
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(
            captured,
            returncode=1,
            stderr=b"auth error key=sk-abc12345678901234567890",
        ),
    )

    with pytest.raises(LLMError) as exc_info:
        call_llm("prompt")
    assert "sk-abc12345678901234567890" not in str(exc_info.value)


# ── T8: argv token check for gemini --prompt ─────────────────────────────────


def test_no_token_on_gemini_argv(monkeypatch):
    """Gemini --prompt path must reject argv elements containing actual env-secret values.

    Cycle-65 AC16 replaced the cycle-21 regex-based prompt-content scan
    (``_TOKEN_PATTERN`` against ``sk-/Bearer/ghp_`` shapes) with a value-based
    scrub: argv elements are checked against the SIX env-secret values
    (ANTHROPIC_API_KEY, OPENAI_API_KEY, FIRECRAWL_API_KEY, DEEPSEEK_API_KEY,
    MIMOCODING_API_KEY, MIMOCHAT_API_KEY). Step-10 simplify pass added
    substring containment so embedded-secret leaks (Step-09 DeepSeek BLOCKER-1)
    are also caught.

    Test updated to reflect the new contract: setenv a fake secret value, then
    construct a prompt containing that value, then assert the gemini --prompt
    delivery refuses (LLMError) before subprocess.Popen.
    """
    monkeypatch.setenv("KB_LLM_BACKEND", "gemini")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/gemini")
    fake_secret = "sk-ant-test-fake-cycle21-token-not-real-9876543210"
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_secret)

    def _should_not_run(*args, **kwargs):
        raise AssertionError("subprocess.Popen should not be called after token check")

    monkeypatch.setattr("kb.utils.cli_backend.subprocess.Popen", _should_not_run)

    with pytest.raises(LLMError) as exc_info:
        call_llm(f"Here is my key {fake_secret} use it")
    assert exc_info.value.kind == "invalid_request"


# ── T3: stdout is also redacted ───────────────────────────────────────────────


def test_stdout_redacted(monkeypatch):
    """Secrets in stdout must be redacted before returning to caller."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(
            captured,
            returncode=0,
            stdout=b"result with sk-abc12345678901234567890 embedded",
        ),
    )

    result = call_llm("prompt")
    assert "sk-abc12345678901234567890" not in result
    assert "[REDACTED:" in result


# ── T1.4: token-shaped prompt round-trips via stdin (not argv) ───────────────


def test_token_shaped_prompt_via_stdin(monkeypatch):
    """A prompt containing a sk-... token must arrive in stdin, not in cmd argv."""
    monkeypatch.setenv("KB_LLM_BACKEND", "ollama")
    monkeypatch.setattr("kb.utils.cli_backend.shutil.which", lambda _: "/usr/bin/ollama")

    captured = {}
    monkeypatch.setattr(
        "kb.utils.cli_backend.subprocess.Popen",
        _make_popen(captured, returncode=0, stdout=b"ok"),
    )

    prompt = "Analyse the key sk-ant-abc123def456ghi789jkl (it is benign test text)"
    result = call_llm(prompt, tier="write")
    assert result == "ok"
    # Prompt must be in stdin bytes, not in any argv element.
    assert captured["input"] is not None
    assert b"sk-ant-abc123def456ghi789jkl" in captured["input"]
    assert all("sk-ant-abc123def456ghi789jkl" not in elem for elem in captured["cmd"])
    assert captured["shell"] is False


# ── JSON extraction: brace scan stage ────────────────────────────────────────


def test_extract_json_brace_scan():
    """Stage 3 brace scan must extract JSON embedded in surrounding text."""
    schema = {
        "type": "object",
        "properties": {"val": {"type": "integer"}},
        "required": ["val"],
        "additionalProperties": False,
    }
    text = 'Here is the output: {"val": 42} — done.'
    result = _extract_json_from_text(text, schema)
    assert result == {"val": 42}


def test_extract_json_no_valid_candidate():
    schema = {
        "type": "object",
        "properties": {"val": {"type": "integer"}},
        "required": ["val"],
        "additionalProperties": False,
    }
    with pytest.raises(LLMError) as exc_info:
        _extract_json_from_text("no json here at all", schema)
    assert exc_info.value.kind == "json_parse_error"


def test_extract_json_unmatched_close_brace_before_valid():
    """Unmatched } before a valid JSON object must not poison the brace scanner."""
    schema = {
        "type": "object",
        "properties": {"val": {"type": "integer"}},
        "required": ["val"],
        "additionalProperties": False,
    }
    # The leading "done}" contains an unmatched } — brace scanner must still find the JSON
    text = 'done} some text {"val": 7} end'
    result = _extract_json_from_text(text, schema)
    assert result == {"val": 7}
