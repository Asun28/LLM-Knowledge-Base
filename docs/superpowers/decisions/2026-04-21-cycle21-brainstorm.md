# Cycle 21 — Brainstorm: CLI Subprocess Backend

**Date:** 2026-04-21

## Three Approaches

### A — Thin subprocess wrapper (CHOSEN)
New `src/kb/utils/cli_backend.py` with `call_cli()` + `call_cli_json()`. `call_llm` /
`call_llm_json` gain a routing gate (`if get_cli_backend() != "anthropic"`). Per-backend
command templates in `config.py`. Config-only additions + one new module + routing stubs
in `llm.py`. Zero change to callers.

**Pros:** Minimal blast radius; independent testability; future API adapters can be added
alongside without touching this module; clean error surface.
**Cons:** JSON extraction from free-form CLI output is inherently less reliable than Anthropic
tool_use; requires jsonschema fallback discipline.

### B — Abstract Provider class
`LLMProvider(ABC)` → `AnthropicProvider` + `CLIProvider`. Registry pattern.

**Pros:** Extensible OOP. **Cons:** Requires refactoring all existing `call_llm` callers to
use `provider.call()`. Too large a blast radius for this cycle. Deferred.

### C — Middleware transform pipeline
Inject pre/post transforms around the existing Anthropic path.

**Pros:** No new module. **Cons:** Confusing indirection, harder to test in isolation. Rejected.

## Selected: Approach A

Rationale: matches Step 1 ACs 1:1, zero change to existing callers, cleanest path.

## Key Design Decisions Made

1. **stdin vs argv**: Prompt via stdin by default; `gemini` is the only backend using `-p arg`
   (documented as weaker-isolation; CLI_PROMPT_VIA_ARG constant).
2. **JSON extraction strategy**: Whole-output-is-JSON OR single fenced block — no heuristic
   first-brace-scan. jsonschema validation before return (T4 mitigation).
3. **Concurrency**: Per-backend `threading.Semaphore` with `CLI_MAX_CONCURRENCY` defaults.
4. **Lazy import of cli_backend**: Function-local inside `call_llm`'s non-anthropic branch
   to avoid import-time side effects (cycle-18 L1 snapshot rule).
5. **Timeout**: Mandatory kwarg passed to `subprocess.run`, clamped at 600s max.
