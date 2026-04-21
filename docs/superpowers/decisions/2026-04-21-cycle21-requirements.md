# Cycle 21 — CLI Tool Subprocess Backend

**Date:** 2026-04-21
**Feature:** Add CLI tool subprocess backend so the KB system can use Ollama, Gemini CLI,
OpenCode, Codex CLI, Kimi Code CLI, QWEN CODE CLI, DeepSeek CLI, GLM/ZAI CLI as LLM
backends via subprocess (stdin/stdout), NOT via API. API integration is deferred.

---

## Problem

The KB system is hard-wired to Anthropic Claude via the `anthropic` SDK. Users who prefer to
run local models (Ollama) or use alternative AI coding CLIs (Gemini CLI, OpenCode, etc.) as
the KB's LLM brain cannot do so without forking the codebase. This cycle adds a subprocess
"CLI backend" so that `call_llm` and `call_llm_json` can dispatch prompts to any installed
CLI tool that accepts text on stdin (or as a positional argument) and returns text on stdout.

API-level integration (LiteLLM, OpenAI SDK, Gemini SDK, etc.) is explicitly **NOT** in scope
this cycle — it is deferred to a later roadmap entry in BACKLOG.md.

---

## Supported CLI Tools

| Key | Tool | Invocation Pattern |
|---|---|---|
| `ollama` | Ollama local inference | `ollama run <model> [--nowordwrap]` + stdin |
| `gemini` | Google Gemini CLI | `gemini` + stdin or `-p "prompt"` |
| `opencode` | OpenCode AI agent | `opencode ask` + stdin |
| `codex` | OpenAI Codex CLI | `codex -q` + stdin |
| `kimi` | Kimi Code CLI (Moonshot) | `kimi` + stdin |
| `qwen` | QWEN CODE CLI (Alibaba) | `qwen` + stdin |
| `deepseek` | DeepSeek Coder CLI | `deepseek` + stdin |
| `zai` | ZAI CLI (Zhipu AI / GLM) | `zai` + stdin |

---

## Non-Goals

- API integration for any of these providers (deferred to BACKLOG).
- Streaming output (current `call_llm` interface doesn't stream).
- Interactive / REPL / TUI mode support.
- Auto-detecting or installing missing CLI tools.
- Support for tools that require file-based I/O instead of stdin/stdout.
- Changing the Anthropic path (backward compat is mandatory).

---

## Acceptance Criteria

### Config (`src/kb/config.py`)

**AC1** `KB_LLM_BACKEND` env var (string, default `"anthropic"`) read at call time (not
import time — cycle-18 L1 snapshot rule). Valid values: `anthropic`, `ollama`, `gemini`,
`opencode`, `codex`, `kimi`, `qwen`, `deepseek`, `zai`. Any other value raises `ValueError`
from `get_cli_backend()` (not silently at import).

**AC2** `CLI_TOOL_COMMANDS: dict[str, list[str]]` constant in `config.py` maps each backend
key to a list of command tokens used to invoke the tool. Values:

```python
CLI_TOOL_COMMANDS = {
    "ollama":   ["ollama", "run", "{model}", "--nowordwrap"],
    "gemini":   ["gemini", "-p"],
    "opencode": ["opencode", "ask"],
    "codex":    ["codex", "-q"],
    "kimi":     ["kimi"],
    "qwen":     ["qwen"],
    "deepseek": ["deepseek"],
    "zai":      ["zai"],
}
```

`{model}` is a format-string placeholder replaced at call time from `CLI_TOOL_MODELS`.

**AC3** `CLI_TOOL_MODELS: dict[str, dict[str, str]]` constant in `config.py` maps each
backend to scan / write / orchestrate model names (used by Ollama; others ignore the model
flag):

```python
CLI_TOOL_MODELS = {
    "ollama":   {"scan": "llama3.2", "write": "qwen2.5-coder:7b", "orchestrate": "qwen2.5-coder:32b"},
    "gemini":   {"scan": "", "write": "", "orchestrate": ""},  # single model, no flag
    "opencode": {"scan": "", "write": "", "orchestrate": ""},
    "codex":    {"scan": "", "write": "", "orchestrate": ""},
    "kimi":     {"scan": "", "write": "", "orchestrate": ""},
    "qwen":     {"scan": "", "write": "", "orchestrate": ""},
    "deepseek": {"scan": "", "write": "", "orchestrate": ""},
    "zai":      {"scan": "", "write": "", "orchestrate": ""},
}
```

Each tier may be overridden via `KB_CLI_MODEL_<TIER>` env var (e.g.
`KB_CLI_MODEL_WRITE=mistral:latest`), read at call time.

**AC4** `get_cli_backend() -> str` helper reads `KB_LLM_BACKEND` env var at call time,
validates against `set(CLI_TOOL_COMMANDS) | {"anthropic"}`, and returns the value.
Raises `ValueError` with a human-readable message listing valid keys on unknown value.

**AC5** `get_cli_model(tier: str) -> str` helper returns the model name for the active
CLI backend + tier, respecting `KB_CLI_MODEL_<TIER>` env override. Returns empty string
for backends that have no per-model flag. Raises `ValueError` on unknown tier.

### CLI backend (`src/kb/utils/cli_backend.py`) — new module

**AC6** `check_cli_available(backend: str) -> bool` uses `shutil.which` to check whether
the first token of `CLI_TOOL_COMMANDS[backend]` is on PATH. Returns `True` if found.
Does NOT raise; callers decide what to do with `False`.

**AC7** `call_cli(prompt: str, *, backend: str, model: str, timeout: float) -> str`
builds the subprocess command from `CLI_TOOL_COMMANDS[backend]` with `{model}` substituted.
For `ollama`, appends the model token when the template contains `{model}`.
Writes `prompt` to subprocess stdin encoded as UTF-8. Reads stdout.
Returns decoded stdout string (stripped of leading/trailing whitespace).

**AC8** `call_cli` passes the prompt via **stdin** for all backends except `gemini`, which
uses a positional flag `-p <prompt>` (Gemini CLI does not accept stdin in non-interactive
mode). The dispatch logic in `call_cli` selects the method via
`CLI_PROMPT_VIA_ARG: set[str] = {"gemini"}` constant.

**AC9** `call_cli` enforces `timeout` (default `LLM_REQUEST_TIMEOUT`) via
`subprocess.run(..., timeout=timeout)`. On `subprocess.TimeoutExpired`, raises
`LLMError(f"CLI timeout after {timeout}s for {backend}", kind="timeout")`.

**AC10** `call_cli` raises `LLMError(kind="not_installed")` immediately when
`check_cli_available(backend)` is `False` — before spawning any subprocess.
Message includes which binary is missing and how to install it (one-line hint from
`CLI_INSTALL_HINTS: dict[str, str]` in `config.py`).

**AC11** `call_cli` captures `stderr` separately (not mixed with stdout). On non-zero exit
code, raises `LLMError` with the first 500 bytes of stderr (passed through `_redact_secrets`
from `kb.utils.llm`). On zero exit, any stderr content is emitted as `logger.debug`.

**AC12** `CLI_INSTALL_HINTS: dict[str, str]` in `config.py` provides a brief install hint
per backend, e.g.:
```python
CLI_INSTALL_HINTS = {
    "ollama":   "Install from https://ollama.com",
    "gemini":   "npm install -g @google/gemini-cli",
    "opencode": "npm install -g opencode-ai",
    "codex":    "npm install -g @openai/codex",
    "kimi":     "pip install kimi-cli",
    "qwen":     "pip install qwen-cli",
    "deepseek": "pip install deepseek-cli",
    "zai":      "pip install zhipuai-cli",
}
```

**AC13** `call_cli_json(prompt: str, *, backend: str, model: str, schema: dict, ...) -> dict`
calls `call_cli` to get a text response, then attempts to parse structured JSON from it
via `_extract_json_from_text(text: str, schema: dict) -> dict`:
1. Try `json.loads(text)` on the full response.
2. Try stripping a single Markdown code fence (` ```json ... ``` ` or ` ``` ... ``` `).
3. Try finding the first `{` … `}` balanced substring (depth-bounded at 50 levels,
   length-capped at 512 KB to avoid ReDoS).
4. Validate the parsed dict against `schema` using `jsonschema.validate`.
5. If any step fails, raises `LLMError(kind="json_parse_error")` with the first 300 chars
   of the raw response for debugging.

### LLM utils routing (`src/kb/utils/llm.py`)

**AC14** `call_llm` checks `get_cli_backend()` at call time. When the result is
`"anthropic"`, uses the existing `_make_api_call` path unchanged. For any other value,
delegates to `cli_backend.call_cli(prompt, backend=..., model=..., timeout=...)`.
No other changes to `call_llm`'s signature, defaults, or Anthropic path.

**AC15** `call_llm_json` checks `get_cli_backend()` at call time. When the result is
`"anthropic"`, uses the existing tool_use path unchanged. For any other value, delegates to
`cli_backend.call_cli_json(...)`.

**AC16** Both routing points import `cli_backend` as a **function-local import** inside
the non-anthropic branch (not at module top) to avoid snapshot-binding hazard (cycle-18 L1)
and to keep the Anthropic-only import footprint zero for users who never set `KB_LLM_BACKEND`.

### Tests (`tests/test_cycle21_cli_backend.py`)

**AC17** `test_anthropic_path_unchanged`: verifies that with `KB_LLM_BACKEND` unset (default
`anthropic`), `call_llm` calls `get_client().messages.create` and NOT any subprocess.
Monkeypatches `subprocess.run` to raise `AssertionError`; asserts it is never called.

**AC18** `test_call_cli_stdin_path`: with `KB_LLM_BACKEND=ollama`, monkeypatches
`subprocess.run` to return a `CompletedProcess(stdout=b"result text\n", returncode=0)`;
asserts `call_llm(prompt)` returns `"result text"` (stripped).

**AC19** `test_call_cli_arg_path_gemini`: with `KB_LLM_BACKEND=gemini`, verifies the
subprocess command includes the prompt as a positional arg after `-p`, NOT via stdin.

**AC20** `test_call_cli_not_installed`: monkeypatches `shutil.which` to return `None`;
asserts `call_llm` raises `LLMError(kind="not_installed")` without launching any subprocess.

**AC21** `test_call_cli_timeout`: monkeypatches `subprocess.run` to raise
`subprocess.TimeoutExpired("ollama", 120)`; asserts `LLMError(kind="timeout")` is raised.

**AC22** `test_call_cli_nonzero_exit`: monkeypatches `subprocess.run` to return
`CompletedProcess(stdout=b"", stderr=b"Error: model not found", returncode=1)`; asserts
`LLMError` is raised with the stderr content in the message.

**AC23** `test_call_cli_json_bare_json`: stub returns `'{"title": "foo"}'`; asserts
`call_llm_json(...)` returns `{"title": "foo"}`.

**AC24** `test_call_cli_json_fenced`: stub returns `'```json\n{"title":"bar"}\n```'`;
asserts `call_llm_json` returns `{"title": "bar"}`.

**AC25** `test_call_cli_json_schema_validated`: stub returns valid JSON that fails schema
validation (e.g. missing required field); asserts `LLMError(kind="json_parse_error")`.

**AC26** `test_call_cli_json_no_json`: stub returns `"I cannot do that."` (no JSON);
asserts `LLMError(kind="json_parse_error")` with the raw preview in the message.

**AC27** `test_get_cli_backend_invalid`: verifies `get_cli_backend()` raises `ValueError`
when `KB_LLM_BACKEND=unsupported`.

**AC28** `test_check_cli_available_true_false`: monkeypatches `shutil.which` to return a
path for one backend and `None` for another; asserts `check_cli_available` returns
`True` / `False` accordingly.

**AC29** `test_cli_model_env_override`: sets `KB_CLI_MODEL_WRITE=mistral:latest`;
asserts `get_cli_model("write")` returns `"mistral:latest"` regardless of
`CLI_TOOL_MODELS` defaults.

**AC30** `test_stderr_redacted`: stub produces `stderr=b"auth error key=sk-abc12345678901234567890"`;
asserts the `LLMError` message does NOT contain `sk-abc12345678901234567890` (redacted).

---

## Blast Radius

| File | Change |
|---|---|
| `src/kb/config.py` | AC1-AC5, AC10, AC12: backend/model/hint constants + helpers |
| `src/kb/utils/cli_backend.py` | AC6-AC13: new module, subprocess execution + JSON extraction |
| `src/kb/utils/llm.py` | AC14-AC16: routing to CLI backend, lazy import |
| `tests/test_cycle21_cli_backend.py` | AC17-AC30: new test file |
| `.env.example` | `KB_LLM_BACKEND`, `KB_CLI_MODEL_WRITE` etc. documentation |
| `CHANGELOG.md` | Unreleased section |
| `BACKLOG.md` | Add deferred API-integration roadmap entry |
| `CLAUDE.md` | CLI backend section in model tiering docs |

No changes to any existing caller of `call_llm` / `call_llm_json`.
