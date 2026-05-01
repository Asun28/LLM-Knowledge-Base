# MiMo Provider (CLI + Subagent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new global LLM provider (MiMo / Xiaomi) accessible from Claude Code as both a `mimo` CLI and a `mimo-rescue` subagent, mirroring the existing DeepSeek encapsulation.

**Architecture:** Anthropic-compatible HTTP CLI in Python (`~/.claude/bin/mimo-cli.py`) wrapped by a bash script (`mimo`) and Windows `.cmd`. Subagent (`~/.claude/agents/mimo-rescue.md`) dispatches via the CLI, returns output verbatim. No project-repo code changes; verification by three live smoke tests.

**Tech Stack:** Python 3.12+ stdlib only (`urllib`, `argparse`, `json`), bash, Windows `cmd`, MiMo Anthropic-compatible HTTP API at `https://api.xiaomimimo.com/anthropic/v1/messages`.

**Reference docs:**
- Design spec: [`docs/superpowers/specs/2026-05-02-mimo-provider-design.md`](../specs/2026-05-02-mimo-provider-design.md)
- Captured MiMo API reference: [`docs/superpowers/specs/2026-05-02-mimo-api-reference.md`](../specs/2026-05-02-mimo-api-reference.md)
- DeepSeek precedent: `~/.claude/bin/deepseek-cli.py`, `~/.claude/agents/deepseek-rescue.md`

**Files created (all outside the project repo):**
- `~/.claude/bin/mimo-cli.py` — Python CLI
- `~/.claude/bin/mimo` — bash wrapper
- `~/.claude/bin/mimo.cmd` — Windows wrapper
- `~/.claude/agents/mimo-rescue.md` — subagent

**Files committed to project repo:**
- `docs/superpowers/specs/2026-05-02-mimo-provider-design.md` (already committed: `3242417`)
- `docs/superpowers/specs/2026-05-02-mimo-api-reference.md` (commit with this plan)
- `docs/superpowers/plans/2026-05-02-mimo-provider.md` (this file)

---

### Task 1: Pre-flight — confirm `MIMO_API_KEY` is set

**Files:** none (env-var check only)

- [ ] **Step 1: Check whether the env var is visible to the current shell**

Run in PowerShell:
```
$env:MIMO_API_KEY
```

Expected: a non-empty string starting with the vendor's key prefix. If empty, proceed to Step 2; if non-empty, skip to Step 3.

- [ ] **Step 2: If unset, set the user-scoped env var via setx**

Run in PowerShell (replace `<KEY>` with the actual key — do NOT paste it into chat):
```
setx MIMO_API_KEY "<KEY>"
```

Open a new shell so the var is inherited. The CLI also has a Windows-registry fallback that reads the User scope directly via PowerShell, so even unrefreshed shells will work.

- [ ] **Step 3: Verify CLI-level visibility**

Run in PowerShell (this mimics the CLI's resolution path):
```
powershell.exe -Command "[Environment]::GetEnvironmentVariable('MIMO_API_KEY', 'User')"
```

Expected: the same non-empty key. If empty, the registry fallback will fail too — re-run Step 2.

---

### Task 2: Create `mimo-cli.py`

**Files:**
- Create: `~/.claude/bin/mimo-cli.py`

- [ ] **Step 1: Write the full Python script**

Write this exact content to `C:/Users/Admin/.claude/bin/mimo-cli.py`:

```python
#!/usr/bin/env python3
"""Minimal MiMo (Xiaomi) CLI via Anthropic-compatible API. Reads --prompt or stdin, prints to stdout.

Usage:
  mimo --model mimo-v2.5-pro --system "You are a reviewer." --prompt "..."
  mimo --model mimo-v2-flash --no-think --prompt "..."
  echo "..." | mimo --model mimo-v2.5-pro
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# UTF-8 stdout/stderr so Unicode chars (em-dash, CJK, arrows) don't crash
# Windows cp1252 console. Same fix as deepseek-cli.py (cycle 39).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


# Identity anchor: defensive prepend to avoid potential identity confusion.
# DeepSeek showed (cycle 42) that vendors trained on Claude data may
# default-claim Anthropic identity. MiMo's vendor docs prescribe this anchor
# pattern in every example, so we apply the same defensively. --no-anchor
# opts out for raw probes.
_IDENTITY_ANCHOR = (
    "You are MiMo, a large language model developed by Xiaomi (小米). "
    "You are NOT Claude, GPT, Gemini, DeepSeek, or any other model. "
    "When asked your identity, state that you are MiMo. "
)

_MODELS = ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-omni", "mimo-v2-flash"]


def _per_model_defaults(model):
    """Return (think_default_bool, temperature_default_float) for the given model."""
    if model == "mimo-v2-flash":
        return False, 0.3
    return True, 1.0


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        default="mimo-v2.5-pro",
        choices=_MODELS,
        help="MiMo model id. mimo-v2.5-pro is default.",
    )
    p.add_argument(
        "--system",
        default="You are a helpful coding assistant.",
        help=(
            "Caller-supplied role. A MiMo identity anchor is auto-prepended "
            "unless --no-anchor is set."
        ),
    )
    p.add_argument("--prompt", default=None, help="If omitted, reads stdin.")
    p.add_argument(
        "--max-tokens",
        type=int,
        default=131072,
        help=(
            "Max output tokens. MiMo's documented hard ceiling is 131072. "
            "Reduce for cost-bounded probes."
        ),
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=None,
        help=(
            "Sampling temperature [0, 1.5]. Defaults to 1.0 (or 0.3 for "
            "mimo-v2-flash). Ignored when thinking is enabled."
        ),
    )
    think_group = p.add_mutually_exclusive_group()
    think_group.add_argument(
        "--think",
        dest="think",
        action="store_true",
        help="Enable thinking mode (overrides per-model default).",
    )
    think_group.add_argument(
        "--no-think",
        dest="think",
        action="store_false",
        help="Disable thinking mode (overrides per-model default).",
    )
    p.set_defaults(think=None)
    p.add_argument(
        "--no-anchor",
        action="store_true",
        help="Skip the auto-prepended identity anchor; for raw probes.",
    )
    args = p.parse_args()

    # Resolve API key: env, then Windows user-registry fallback
    key = os.environ.get("MIMO_API_KEY")
    if not key:
        try:
            import subprocess
            result = subprocess.run(
                ["powershell.exe", "-Command",
                 "[Environment]::GetEnvironmentVariable('MIMO_API_KEY', 'User')"],
                capture_output=True, text=True, timeout=5,
            )
            key = result.stdout.strip()
        except Exception:
            pass
    if not key:
        sys.exit("ERROR: MIMO_API_KEY not set in env or Windows user registry")

    # Resolve prompt
    prompt = args.prompt if args.prompt is not None else sys.stdin.read()
    if not prompt.strip():
        sys.exit("ERROR: empty prompt")

    # Apply per-model defaults for think + temperature
    default_think, default_temp = _per_model_defaults(args.model)
    thinking_active = default_think if args.think is None else args.think
    temperature = default_temp if args.temperature is None else args.temperature

    # Build system prompt with optional anchor
    system_prompt = args.system if args.no_anchor else _IDENTITY_ANCHOR + args.system

    # Build payload
    payload = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "enabled" if thinking_active else "disabled"},
    }
    if not thinking_active:
        payload["temperature"] = temperature

    # Dispatch
    req = urllib.request.Request(
        "https://api.xiaomimimo.com/anthropic/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR {e.code}: {e.read().decode(errors='replace')}")
    except Exception as e:
        sys.exit(f"ERROR: {e}")

    # Parse response
    thinking_text = None
    answer_text = None
    for block in data.get("content", []):
        if block.get("type") == "thinking":
            thinking_text = block.get("thinking", "")
        elif block.get("type") == "text":
            answer_text = block.get("text", "")

    if thinking_text:
        print("=== reasoning ===")
        print(thinking_text)
        print("=== answer ===")
    if answer_text:
        print(answer_text)
    elif not thinking_text:
        sys.exit(f"ERROR: no content in response: {json.dumps(data)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the file is parseable Python**

Run in PowerShell:
```
python -c "import ast; ast.parse(open('C:/Users/Admin/.claude/bin/mimo-cli.py', encoding='utf-8').read())"
```

Expected: no output, exit code 0. If a `SyntaxError` is raised, re-paste the file content from Step 1.

- [ ] **Step 3: Set executable bit (no-op on Windows but tracked by git-bash)**

Run in git-bash (or skip on pure PowerShell):
```
chmod +x /c/Users/Admin/.claude/bin/mimo-cli.py
```

Expected: no output, exit code 0.

---

### Task 3: Create the bash wrapper

**Files:**
- Create: `~/.claude/bin/mimo`

- [ ] **Step 1: Write the bash wrapper**

Write this exact content to `C:/Users/Admin/.claude/bin/mimo`:

```bash
#!/usr/bin/env bash
SCRIPT="$(dirname "$0")/mimo-cli.py"
if command -v python3 &>/dev/null; then
    python3 "$SCRIPT" "$@"
elif command -v python &>/dev/null; then
    python "$SCRIPT" "$@"
else
    # Windows fallback: search common Python locations.
    # Project venv is checked FIRST since most invocations originate from this repo.
    for py in \
        "/d/Projects/llm-wiki-flywheel/.venv/Scripts/python.exe" \
        "/c/Users/Admin/.venv/Scripts/python.exe" \
        "/c/Program Files/Python312/python.exe" \
        "/c/Program Files/Python311/python.exe" \
        "/c/Program Files/Python310/python.exe"; do
        if [ -x "$py" ]; then
            "$py" "$SCRIPT" "$@"
            exit $?
        fi
    done
    echo "ERROR: python not found in PATH or common Windows locations" >&2
    exit 1
fi
```

- [ ] **Step 2: Set executable bit**

Run in git-bash:
```
chmod +x /c/Users/Admin/.claude/bin/mimo
```

Expected: no output, exit code 0.

- [ ] **Step 3: Smoke-check that the wrapper finds Python**

Run in git-bash (use `--help` to avoid making an API call):
```
/c/Users/Admin/.claude/bin/mimo --help
```

Expected: argparse help text listing `--model`, `--system`, `--prompt`, `--max-tokens`, `--temperature`, `--think`, `--no-think`, `--no-anchor`. If `python not found in PATH`, ensure `python` or `python3` is on PATH or that one of the fallback paths in Step 1 exists.

---

### Task 4: Create the Windows `.cmd` wrapper

**Files:**
- Create: `~/.claude/bin/mimo.cmd`

- [ ] **Step 1: Write the .cmd wrapper**

Write this exact content to `C:/Users/Admin/.claude/bin/mimo.cmd`:

```
@python "%~dp0mimo-cli.py" %*
```

(Single line; no trailing blank lines. Mirror of `deepseek.cmd`.)

- [ ] **Step 2: Smoke-check via PowerShell**

Run in PowerShell:
```
mimo --help
```

(Or, if `~/.claude/bin/` is not on PATH from PowerShell, run with full path: `C:/Users/Admin/.claude/bin/mimo.cmd --help`.)

Expected: argparse help text. If "python is not recognized", `python` is not on PATH from this shell — set up a Python launcher or rely on the bash wrapper from git-bash subagent shells instead.

---

### Task 5: Smoke test 1 — auth + basic completion (no thinking)

**Files:** none (live API call)

- [ ] **Step 1: Run the test**

Run in git-bash:
```
echo "Say hello in one sentence." | /c/Users/Admin/.claude/bin/mimo --model mimo-v2-flash --no-think --max-tokens 200
```

- [ ] **Step 2: Verify expected output**

Expected: a single sentence directly to stdout (no `=== reasoning ===` block since `--no-think` suppresses thinking). Example shape:
```
Hello! Nice to meet you — how can I help today?
```

**Failure modes:**
- `ERROR 401: ...` → API key not propagating. Re-run Task 1.
- `ERROR 4xx: ...` with "Authorization" message → header format wrong; verify the script uses `Authorization: Bearer ...`.
- `ERROR 4xx: ...` with "thinking" or "max_tokens" message → payload shape wrong; diff against [`2026-05-02-mimo-api-reference.md`](../specs/2026-05-02-mimo-api-reference.md).
- Empty output → response parsing missed a block type; print `data` directly to debug.

---

### Task 6: Smoke test 2 — thinking mode + reasoning trace

**Files:** none (live API call)

- [ ] **Step 1: Run the test**

Run in git-bash:
```
echo "What's 17 * 23? Show your work." | /c/Users/Admin/.claude/bin/mimo --model mimo-v2.5-pro --max-tokens 2000
```

- [ ] **Step 2: Verify expected output**

Expected output shape:
```
=== reasoning ===
<some chain-of-thought computing 17 * 23>
=== answer ===
<final answer that contains "391">
```

The exact text varies; the structural requirement is (a) `=== reasoning ===` header is present, (b) `=== answer ===` header is present, (c) the answer text contains `391`.

**Failure modes:**
- No `=== reasoning ===` block → `thinking: {"type":"enabled"}` is being dropped or the model defaulted to disabled. Verify by adding a print of `payload` before the request.
- Truncated output (`stop_reason: "max_tokens"` would be implied) → bump `--max-tokens 8000`. The default `131072` is plenty; `2000` is the per-test budget.

---

### Task 7: Smoke test 3 — identity probe (raw, with `--no-anchor`)

**Files:** none (live API call)

- [ ] **Step 1: Run the probe**

Run in git-bash:
```
echo "Who built you? Just the company name." | /c/Users/Admin/.claude/bin/mimo --model mimo-v2.5-pro --no-anchor --max-tokens 200
```

- [ ] **Step 2: Record the result**

Expected: the answer mentions "Xiaomi" or "MiMo by Xiaomi". Note the EXACT verbatim answer text — it goes into the cycle/memory record below.

**Possible findings:**
- "Xiaomi" / "MiMo, developed by Xiaomi" → no anchor needed; auto-anchor is purely defensive. Keep auto-anchor on by default anyway (matches DeepSeek precedent).
- "Anthropic" / "Claude" / "DeepSeek" / other vendor → identity confusion confirmed (mirrors cycle 42's DeepSeek discovery). The auto-anchor masks this in normal usage. Document the finding in the run notes / memory store; do NOT change the CLI default.

- [ ] **Step 3: Re-run with anchor enabled to confirm anchor works**

Run in git-bash:
```
echo "Who built you? Just the company name." | /c/Users/Admin/.claude/bin/mimo --model mimo-v2.5-pro --max-tokens 200
```

Expected: "Xiaomi" / "MiMo by Xiaomi" regardless of the no-anchor result. If this still claims another vendor, the anchor is being ignored — verify that the CLI is prepending it to `system_prompt`.

---

### Task 8: Create `mimo-rescue` subagent

**Files:**
- Create: `~/.claude/agents/mimo-rescue.md`

- [ ] **Step 1: Write the subagent definition**

Write this exact content to `C:/Users/Admin/.claude/agents/mimo-rescue.md`:

```markdown
---
name: mimo-rescue
description: Delegate a coding task, debugging investigation, second-opinion review, or independent reasoning pass to MiMo (Xiaomi) via the local `mimo` CLI. Use proactively when you want a non-Claude, non-DeepSeek perspective. Default model: mimo-v2.5-pro. Other models (mimo-v2.5, mimo-v2-pro, mimo-v2-omni, mimo-v2-flash) only when the task explicitly justifies them.
tools: Bash, Read, Grep, Glob
model: haiku
---

You are an orchestrator that delegates work to MiMo and returns its output to the parent session. You are advisory only — never edit files.

## Workflow

1. **Read the parent's task carefully.** Use Read/Grep/Glob to gather only the minimal file context MiMo needs. MiMo has no filesystem access, so paste relevant snippets inline in the prompt.

2. **Pick the model:**
   - `mimo-v2.5-pro` (default) — strong reasoning, default thinking enabled. Use for design evaluation, second-opinion reviews, threat-model brainstorming.
   - `mimo-v2.5` — multimodal (image input via URL); the only MiMo model the vendor demos with image content blocks.
   - `mimo-v2-pro` — previous-generation pro. Use only if the user explicitly asks for it.
   - `mimo-v2-omni` — omni-modal previous-gen.
   - `mimo-v2-flash` — fast, cheap; default thinking disabled. Use for routine doc drafts and short Q&A.

3. **Call MiMo via Bash.** The `mimo` wrapper is NOT on PATH inside subagent bash shells; always invoke via the absolute path:

   ```
   /c/Users/Admin/.claude/bin/mimo --model mimo-v2.5-pro --system "You are a senior code reviewer." <<'EOF'
   <task description>

   Relevant code:
   ```python
   <pasted snippets>
   ```

   Question: <what you want MiMo to answer>
   EOF
   ```

   Use `--prompt "..."` for short prompts. The Python interpreter is found via the bash wrapper's fallback chain (project venv first, then user venv, then Program Files Python).

   **Identity-anchor behavior:** the CLI auto-prepends a MiMo identity statement to every `--system` prompt. Do NOT add identity language to your `--system` argument. To run a raw identity probe, pass `--no-anchor`.

   **Verification probe** if a result looks identity-confused (model claims to be Claude/DeepSeek/etc. in its OWN response, not in your prompt's reasoning):
   ```
   echo "Who built you? Just the company name." | /c/Users/Admin/.claude/bin/mimo \
     --model mimo-v2.5-pro --no-anchor --max-tokens 200
   ```
   Expected: "Xiaomi" or "MiMo by Xiaomi". Document any deviation in the parent's run notes.

4. **Return MiMo's output verbatim** under a `## MiMo output` heading, then add a short `## Summary` (2–4 bullets) capturing the key recommendations or findings. If MiMo emits a reasoning trace (CLI prefixes it with `=== reasoning ===`), keep it — the parent may want to see it.

5. **Do NOT edit files.** You are advisory. The parent session decides what to apply.

## Budget and limits

**Max output tokens:** documented range `[1, 131072]`. The CLI defaults to `131072` (no truncation in practice).

**Context window (input):** not explicitly documented by MiMo. Treat conservatively — keep pasted code/diffs under ~50k tokens until empirically benchmarked.

**Per-model defaults:**
- Thinking: enabled for `mimo-v2.5-pro`, `mimo-v2.5`, `mimo-v2-pro`, `mimo-v2-omni`; disabled for `mimo-v2-flash`. Override with `--think` / `--no-think`.
- Temperature: 1.0 (most), 0.3 (`mimo-v2-flash`); range [0, 1.5]; ignored when thinking is enabled.

**Output sizing via `--max-tokens`:** default `131072` is the documented hard ceiling. There is NO 1M-context claim for MiMo — do not assume DeepSeek-scale long-context tolerance.

| Task type | `--max-tokens` |
|---|---|
| Default for any task | (omit — uses 131072 ceiling) |
| Identity probe / 1-line answer | `100-200` |
| Cost-explicitly-bounded background reviewer | `8000-16000` |

There is no cost penalty for a generous ceiling — billing is per actual output token, not per ceiling. Reasoning is hard to suppress in thinking-enabled modes; plan for it.

- If `mimo` exits with a non-zero status, report stderr verbatim and stop. Do not retry blindly.
- If `MIMO_API_KEY` is unset, tell the parent to run `setx MIMO_API_KEY "<key>"` and restart Claude Code.

## When NOT to use MiMo

- Tasks requiring filesystem reads or edits — MiMo has no FS access. Use Read/Grep/Glob locally.
- Tasks requiring MCP tool use or Anthropic-specific features (prompt caching, server-side tool execution).
- Trivial questions — just answer them yourself.

Comparative routing guidance vs. DeepSeek or Claude is intentionally not provided here. Defer until benchmarks land (see open follow-ups in the design spec).
```

- [ ] **Step 2: Verify the file is well-formed YAML frontmatter + markdown**

Run in git-bash:
```
head -5 /c/Users/Admin/.claude/agents/mimo-rescue.md
```

Expected output:
```
---
name: mimo-rescue
description: Delegate a coding task, debugging investigation, second-opinion review, or independent reasoning pass to MiMo (Xiaomi) via the local `mimo` CLI. Use proactively when you want a non-Claude, non-DeepSeek perspective. Default model: mimo-v2.5-pro. Other models (mimo-v2.5, mimo-v2-pro, mimo-v2-omni, mimo-v2-flash) only when the task explicitly justifies them.
tools: Bash, Read, Grep, Glob
model: haiku
```

If the frontmatter looks corrupted (missing leading `---`, wrong key names), re-paste the file content from Step 1.

- [ ] **Step 3: Confirm Claude Code recognises the new subagent**

After saving, the next time Claude Code lists agents, `mimo-rescue` should appear. The user can verify by running `/agents` or by referring to the subagent in a future Agent tool dispatch.

---

### Task 9: Final verification

**Files:** none

- [ ] **Step 1: Confirm all four files exist and are non-empty**

Run in git-bash:
```
ls -la /c/Users/Admin/.claude/bin/mimo /c/Users/Admin/.claude/bin/mimo-cli.py /c/Users/Admin/.claude/bin/mimo.cmd /c/Users/Admin/.claude/agents/mimo-rescue.md
```

Expected: four lines, each showing a non-zero file size. The bash wrapper and Python script should have the executable bit (`x`) set.

- [ ] **Step 2: Confirm Tasks 5–7 smoke tests all passed (or findings recorded)**

Quick checklist against the actual run output:
- Smoke 1 (Task 5): basic completion succeeded → ✅
- Smoke 2 (Task 6): thinking + reasoning trace surfaced, answer contains `391` → ✅
- Smoke 3 (Task 7): identity result recorded (Xiaomi or other-vendor finding noted) → ✅

If any failed without a clear root cause, do NOT proceed to Task 10 — investigate using the failure-mode hints in each task and the captured API reference.

---

### Task 10: Verify the documentation commit landed

The plan, API reference, and spec edit are committed by the writing-plans skill BEFORE execution begins, so this task is a sanity check only — no new commits required.

**Files (already committed at writing-plans time):**
- `docs/superpowers/specs/2026-05-02-mimo-provider-design.md` (initial: `3242417`; reference link added in follow-up commit)
- `docs/superpowers/specs/2026-05-02-mimo-api-reference.md`
- `docs/superpowers/plans/2026-05-02-mimo-provider.md`

- [ ] **Step 1: Confirm the docs are committed and the working tree is clean for `docs/superpowers/`**

Run from project root:
```
git status --short docs/superpowers/
```

Expected: empty output. If anything appears, it indicates an uncommitted edit that should be folded in or reverted.

- [ ] **Step 2: Confirm the recent log shows the docs commits**

Run from project root:
```
git log --oneline -4 -- docs/superpowers/
```

Expected: top entries include the writing-plans commit ("docs(mimo): add API reference + implementation plan…") and the brainstorming commit ("docs(spec): add MiMo provider encapsulation design…").

---

## Notes for executor

- **No project-repo `pytest` changes.** Per the design's Q1=C scope, this implementation does NOT add tests under `tests/`. Verification is by live smoke tests of the global CLI only.
- **`~/.claude/` is not under git version control.** Implementation files in `~/.claude/bin/` and `~/.claude/agents/` cannot be committed; rely on the project-repo plan + spec + reference as the durable record.
- **If a smoke test fails with a payload-shape error**, diff against [`docs/superpowers/specs/2026-05-02-mimo-api-reference.md`](../specs/2026-05-02-mimo-api-reference.md) — that's the captured vendor spec. The reference's "Notes for Future Troubleshooting" section pre-flags 7 known divergence points (no `anthropic-version` header, `signature: ""` in thinking blocks, `131072` hard cap, `call_*` tool-use IDs, etc.).
- **If the user later asks for project integration** (model tiering in `src/kb/config.py`, CLAUDE.md updates, dev-ds skill rewiring), that's a separate plan — not this one.
