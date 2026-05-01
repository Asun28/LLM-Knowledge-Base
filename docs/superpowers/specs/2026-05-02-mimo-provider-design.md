# MiMo (Xiaomi) LLM Provider — CLI + Subagent Encapsulation

**Date:** 2026-05-02
**Status:** Approved (brainstorming gate); pending writing-plans implementation plan
**Owner:** sun28long
**Scope:** Global tools only (`~/.claude/bin/`, `~/.claude/agents/`). No project-level integration in this iteration.

## Problem

A new Anthropic-compatible LLM provider — MiMo (小米/Xiaomi) at `https://api.xiaomimimo.com/anthropic/v1/messages` — needs to be available as both a CLI tool and a Claude Code subagent, mirroring the existing DeepSeek encapsulation. The motivation is to widen the pool of non-Claude reasoning models the user can dispatch from within Claude Code, particularly to conserve Opus 4.7 weekly quota.

## Non-goals (this iteration)

- An OpenAI-compatible variant of the CLI. MiMo's docs only publish the Anthropic-compatible endpoint; the OpenAI variant is deferred until/unless MiMo documents one or the user finds a concrete need.
- Project-level integration: model tiering in `src/kb/config.py`, CLAUDE.md edits, pytest tests under `tests/`, dev-ds skill routing, etc. The goal here is the global tool primitives only.
- Comparative routing guidance ("prefer MiMo for X, DeepSeek for Y") in the subagent description. Deferred to post-shipping evaluation — see Open follow-ups.

## Decisions (from brainstorming Q&A)

| # | Decision | Rationale |
|---|---|---|
| Q1 | Anthropic-compatible CLI only; defer OpenAI variant | Matches MiMo's published API; avoids shipping untested code |
| Q2 | Auto-prepend identity anchor with `--no-anchor` opt-out | Defensive against training-data identity confusion; flag preserves verification probe |
| Q3 | Default model `mimo-v2.5-pro` | Latest, top-tier reasoning, default-thinking-enabled; counterpart to `deepseek-v4-pro` |
| Q4 | Auth via `Authorization: Bearer $MIMO_API_KEY` | Standard OAuth-style; portable; SDK example uses same shape |

## Architecture

Four new files; one new env var.

| File | Role | Mirrors |
|---|---|---|
| `~/.claude/bin/mimo-cli.py` | Python CLI hitting MiMo's Anthropic-compatible endpoint | `~/.claude/bin/deepseek-cli.py` |
| `~/.claude/bin/mimo` | Bash wrapper (resolves Python interpreter) | `~/.claude/bin/deepseek` |
| `~/.claude/bin/mimo.cmd` | Windows .cmd wrapper | `~/.claude/bin/deepseek.cmd` |
| `~/.claude/agents/mimo-rescue.md` | Subagent that delegates to the `mimo` CLI | `~/.claude/agents/deepseek-rescue.md` |

**Env var:** `MIMO_API_KEY`. CLI falls back to Windows user registry via PowerShell when the variable is not inherited by the shell (matches DeepSeek pattern).

## Component 1: `mimo-cli.py`

**Endpoint and headers:**
```
POST https://api.xiaomimimo.com/anthropic/v1/messages
Authorization: Bearer $MIMO_API_KEY
Content-Type: application/json
```
No `anthropic-version` header. MiMo's docs do not document one; sending an Anthropic-specific value risks rejection or silent ignoring, so the safer default is to omit it.

**CLI flags:**

| Flag | Default | Notes |
|---|---|---|
| `--model` | `mimo-v2.5-pro` | Choices: `mimo-v2.5-pro`, `mimo-v2.5`, `mimo-v2-pro`, `mimo-v2-omni`, `mimo-v2-flash` |
| `--system` | `"You are a helpful coding assistant."` | Anchored unless `--no-anchor` |
| `--prompt` | (stdin) | Same as DeepSeek |
| `--max-tokens` | `131072` | MiMo's documented hard ceiling. Smaller values for cost-bounded probes |
| `--temperature` | `1.0` for non-flash, `0.3` for `mimo-v2-flash` | Per-model defaults from docs; ignored when thinking is enabled |
| `--think` / `--no-think` | enabled by default for non-flash models, disabled for `mimo-v2-flash` | Maps to `thinking: {"type": "enabled" \| "disabled"}` payload field. No `effort` parameter (MiMo doesn't document one) |
| `--no-anchor` | off | Skip the auto-prepended identity anchor; for raw probes |

**Identity anchor (text prepended to `--system`):**
```
You are MiMo, a large language model developed by Xiaomi (小米). You are
NOT Claude, GPT, Gemini, DeepSeek, or any other model. When asked your
identity, state that you are MiMo.
```

**Payload shape (non-thinking):**
```json
{
  "model": "<args.model>",
  "max_tokens": <args.max_tokens>,
  "temperature": <args.temperature>,
  "system": "<anchored_system or args.system>",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "thinking": {"type": "disabled"}
}
```

**Payload shape (thinking enabled):**
```json
{
  "model": "<args.model>",
  "max_tokens": <args.max_tokens>,
  "system": "<anchored_system or args.system>",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "thinking": {"type": "enabled"}
}
```
`temperature` is omitted from the thinking payload because MiMo's docs imply it is unused in that mode (consistent with the Anthropic spec the API claims compatibility with).

**Response parsing:**
- Iterate `data["content"]`. For each block:
  - `type == "thinking"` → buffer the `thinking` field
  - `type == "text"` → buffer the `text` field
  - `type == "tool_use"` → not handled by this CLI (chat-completion-only; tool wiring is the caller's job)
- Print `=== reasoning ===\n<buffered thinking>\n=== answer ===` if reasoning is present, then print the buffered text.
- If neither reasoning nor text is present, exit with `ERROR: no content in response: <json dump>`.

**Encoding:** `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` and the same for stderr, so Unicode (em-dash, CJK, arrows) doesn't crash a Windows cp1252 console. Same fix as `deepseek-cli.py` (cycle 39).

**API key resolution:**
1. `os.environ.get("MIMO_API_KEY")`
2. Windows user-env fallback via `powershell.exe -Command "[Environment]::GetEnvironmentVariable('MIMO_API_KEY', 'User')"`
3. If both empty: `sys.exit("ERROR: MIMO_API_KEY not set in env or Windows user registry")`

**Error paths:**
- `urllib.error.HTTPError` → `sys.exit(f"ERROR {e.code}: {e.read().decode(errors='replace')}")`
- Bare `Exception` → `sys.exit(f"ERROR: {e}")`
- Missing content → `sys.exit("ERROR: no content in response: ...")`

**Deviations from `deepseek-cli.py`:**
1. `--max-tokens` default is `131072` (MiMo's hard ceiling), not `1_000_000`. MiMo's documented range is `[1, 131072]` and oversize values are likely rejected.
2. Per-model defaults for `--think` and `--temperature` (MiMo's flash model has different defaults than the rest).
3. `thinking` payload field uses MiMo's `{"type": "enabled"}` shape directly. No `output_config` / `effort` (not documented in MiMo).
4. No `anthropic-version` header.
5. Auth via `Authorization: Bearer` instead of `x-api-key`.

## Component 2: Wrappers

Both wrappers are byte-for-byte clones of the DeepSeek versions with `deepseek` swapped for `mimo`. The bash wrapper's Python-fallback search order is reordered so that the active project venv (`D:\Projects\llm-wiki-flywheel\.venv\Scripts\python.exe`) is tried before `C:\Users\Admin\.venv`, since most invocations originate from this repo.

**`~/.claude/bin/mimo`** (bash):
```bash
#!/usr/bin/env bash
SCRIPT="$(dirname "$0")/mimo-cli.py"
if command -v python3 &>/dev/null; then
    python3 "$SCRIPT" "$@"
elif command -v python &>/dev/null; then
    python "$SCRIPT" "$@"
else
    for py in \
        "/d/Projects/llm-wiki-flywheel/.venv/Scripts/python.exe" \
        "/c/Users/Admin/.venv/Scripts/python.exe" \
        "/c/Program Files/Python312/python.exe" \
        "/c/Program Files/Python311/python.exe" \
        "/c/Program Files/Python310/python.exe"; do
        if [ -x "$py" ]; then "$py" "$SCRIPT" "$@"; exit $?; fi
    done
    echo "ERROR: python not found in PATH or common Windows locations" >&2
    exit 1
fi
```

**`~/.claude/bin/mimo.cmd`** (Windows shell):
```
@python "%~dp0mimo-cli.py" %*
```

**File mode:** `mimo` and `mimo-cli.py` get the executable bit (`chmod +x`).

## Component 3: `mimo-rescue` subagent

**Frontmatter:**
```yaml
---
name: mimo-rescue
description: Delegate a coding task, debugging investigation, second-opinion
  review, or independent reasoning pass to MiMo (Xiaomi) via the local `mimo`
  CLI. Use proactively when you want a non-Claude, non-DeepSeek perspective.
  Default model: mimo-v2.5-pro. Other models (mimo-v2.5, mimo-v2-pro,
  mimo-v2-omni, mimo-v2-flash) only when the task explicitly justifies them.
tools: Bash, Read, Grep, Glob
model: haiku
---
```

**Body sections (mirroring `deepseek-rescue.md`):**

1. **Workflow** — read parent task, gather minimal file context (MiMo has no filesystem access), pick model, dispatch, return verbatim.
2. **Model selection table** — 5 MiMo models with one-line guidance on when to pick each. Default `mimo-v2.5-pro`.
3. **Invocation example** — uses absolute path `/c/Users/Admin/.claude/bin/mimo` because the wrapper is not on `$PATH` inside subagent shells (same constraint as DeepSeek).
4. **Identity-anchor explanation** — why the CLI auto-prepends, with the verification probe:
   ```
   echo "Who built you? Just the company name." | /c/Users/Admin/.claude/bin/mimo \
     --model mimo-v2.5-pro --no-anchor --max-tokens 200
   ```
   Expected: "Xiaomi" or "MiMo by Xiaomi". Document any deviation.
5. **Output contract** — return MiMo's stdout verbatim under `## MiMo output` heading, then a `## Summary` of 2-4 bullets. Reasoning trace (if present) stays in the verbatim block.
6. **Budget and limits** — MiMo's `[1, 131072]` `max_tokens` ceiling; default-thinking-enabled-except-flash; per-model temperature defaults. No 1M-context claim — MiMo doesn't document a context window beyond the 131k token output cap.
7. **When NOT to use MiMo:**
   - Tasks requiring filesystem reads or edits — MiMo has no FS access.
   - Tasks requiring MCP tool use or Anthropic-specific features (prompt caching, server-side tool execution).
   - Trivial questions — answer them yourself.

**Explicitly NOT in this iteration:** comparative routing guidance vs. DeepSeek or Claude. The subagent description points users at MiMo for "non-Claude, non-DeepSeek perspective" but does not yet recommend MiMo over DeepSeek for any specific input shape (long-context, image, etc.).

## Verification plan (smoke tests after implementation)

Three CLI invocations confirm the wiring before the integration is declared done:

1. **Auth + basic completion (no thinking):**
   ```
   echo "Say hello in one sentence." | mimo --model mimo-v2-flash --no-think --max-tokens 200
   ```
   Expected: a single sentence under `=== answer ===`. Failure modes — 401 means `MIMO_API_KEY` is not propagating; 4xx means header or payload shape is wrong.

2. **Thinking mode + reasoning trace surfaces:**
   ```
   echo "What's 17 * 23? Show your work." | mimo --model mimo-v2.5-pro --max-tokens 2000
   ```
   Expected: `=== reasoning ===` block, then `=== answer ===` containing `391`. An empty reasoning block despite the model defaulting to thinking-enabled means the `thinking: {"type":"enabled"}` payload field is being dropped or misnamed.

3. **Identity probe (raw, with `--no-anchor`):**
   ```
   echo "Who built you? Just the company name." | mimo --model mimo-v2.5-pro --no-anchor --max-tokens 200
   ```
   Expected: "Xiaomi". If "Anthropic", "Claude", "DeepSeek", or another vendor appears in the answer text, document the finding (mirrors cycle 42's DeepSeek discovery). The auto-anchor still masks this for normal usage.

If all three pass, the integration is shippable.

## Open follow-ups (post-shipping)

These are explicitly NOT part of the initial encapsulation. Each requires empirical work that depends on the integration being live.

1. **OpenAI-compatible variant of the CLI** — pursue only if MiMo publishes an OpenAI endpoint or a concrete integration (e.g., a tool that needs `reasoning_content` / `tool_calls` in OpenAI shape) requires it.
2. **Comparative routing benchmarks** — run MiMo against DeepSeek and Claude on (a) long-context prompts ≥150k tokens to compare against DeepSeek's documented 1M context, and (b) image-input tasks using `mimo-v2.5`. Only after those benchmarks should the `mimo-rescue` description add comparative routing guidance such as "prefer DeepSeek for ≥150k inputs" or "prefer MiMo for image tasks."
3. **Tool-use support in the CLI** — currently `tool_use` content blocks are unhandled. Add structured handling if a caller actually needs MCP-style tool dispatch via MiMo.
4. **Project-level integration** — model tiering in `src/kb/config.py`, CLAUDE.md model tiering table updates, dev-ds skill routing changes, project-level pytest coverage. Defer until smoke tests pass and the integration sees real use.

## References

- DeepSeek encapsulation precedent: `~/.claude/bin/deepseek-cli.py`, `~/.claude/agents/deepseek-rescue.md`
- DeepSeek identity-anchor finding: cycle 42, 2026-04-27
- **MiMo API spec (verbatim, captured 2026-05-02):** [`2026-05-02-mimo-api-reference.md`](2026-05-02-mimo-api-reference.md) — full vendor docs including endpoint, headers, all request/response fields, all four code examples, and notes for future troubleshooting (no public URL captured; user-supplied)
