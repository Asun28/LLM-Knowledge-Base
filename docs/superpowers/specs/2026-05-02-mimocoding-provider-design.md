# MiMo Coding (Xiaomi Token Plan) — CLI + Subagent Encapsulation

**Date:** 2026-05-02
**Status:** Implementation shipped 2026-05-02. Smoke tests blocked pending a `tp-`-prefixed Token Plan API key.
**Owner:** sun28long
**Scope:** Global tools only (`~/.claude/bin/`, `~/.claude/agents/`). Project integration (`dev-ds` / `dev-codexds` skill routing) is a separate plan, deferred to a fresh context window.

> **Branding note:** the *product* this CLI wraps is "MiMo Coding" — Xiaomi's subscription-billed Token Plan offering specifically for AI programming tools, distinct from "MiMo Chat" (per-token billing) and from the TTS / VoiceClone family. The underlying *model IDs* preserve the vendor's official lowercase naming (`mimo-v2.5-pro`, etc.) because the API rejects non-vendor IDs. Wherever this document refers to the wrapper / product, it uses "MiMo Coding"; wherever it refers to a model id, it uses the lowercase `mimo-*` form.

## Problem

Xiaomi's Token Plan offers a flat-rate subscription for high-volume coding workloads at lower effective $/Token than per-token MiMo Chat. The user holds (or will hold) a Token Plan subscription with `tp-`-prefixed API keys scoped to programming-tool use. We need a wrapper analogous to `mimochat` that targets the Token Plan endpoint, exposes only the Token-Plan-eligible chat-completion model subset, surfaces the credit-multiplier story per model, and warns users about the AUP boundary so they don't accidentally trigger key suspension.

## Non-goals (this iteration)

- TTS / VoiceClone / VoiceDesign variants (`MiMo-V2.5-TTS-VoiceClone`, `MiMo-V2.5-TTS-VoiceDesign`, `MiMo-V2.5-TTS`, `MiMo-V2-TTS`). Different protocol (audio output); separate wrapper if/when needed.
- OpenAI-compatible variant (`/v1/chat/completions`). The vendor publishes both endpoints, but our wrapper currently exercises the Anthropic-compat path only.
- Project integration (model tiering, `dev-ds`/`dev-codexds` skill rewiring, CLAUDE.md updates, pytest coverage). Deferred to a separate plan.
- Auto-fallback between regions. The CLI exposes `--region {sgp,cn}`; if Singapore returns a region-specific error, the user passes `--region cn` explicitly. Auto-failover would mask transient Singapore issues.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Default endpoint Singapore (`token-plan-sgp.xiaomimimo.com/anthropic/v1/messages`) | User's explicit preference; the vendor docs do not designate a default |
| D2 | China cluster as `--region cn` (manual fallback) | Same protocol; backup region for Singapore unavailability or geo-restriction |
| D3 | Expose only 4 chat-completion models | TTS variants need different protocol; `mimo-v2-flash` is not a Token Plan model. Choices: `mimo-v2.5-pro`, `mimo-v2.5`, `mimo-v2-pro`, `mimo-v2-omni` |
| D4 | Default model `mimo-v2.5-pro` | Highest quality; coding tasks justify the 2x credit cost. User can pass `--model mimo-v2.5` for 1x cost |
| D5 | Identity anchor: `"You are MiMo Coding, supporting AI Agent and Programming Tools developed by Xiaomi."` | Verbatim from user-supplied vendor branding; prepended to `--system` unless `--no-anchor` |
| D6 | Auth via `Authorization: Bearer $MIMOCODING_API_KEY` | Mirrors MiMo Chat wrapper for muscle-memory parity |
| D7 | Prefix-validation warning on stderr if key does not start with `tp-` | Strong signal the user pasted the wrong key into the wrong env var; warns before incurring a wasted API call |
| D8 | 401 hint message points at AUP / quota / region | The 2026-05-02 incident showed that 401 on `tp-` keys has multiple plausible root causes; surfacing the most common ones short-circuits debug time |
| D9 | Backward-compat fallback to `MIMO_API_KEY` env var | Vendor's own docs document `MIMO_API_KEY` for both Chat and Coding contexts; fallback minimizes user friction |

## Architecture

Four new files; one new env var (with backward-compat fallback to `MIMO_API_KEY`).

| File | Role | Mirrors |
|---|---|---|
| `~/.claude/bin/mimocoding-cli.py` | Python CLI hitting Xiaomi Token Plan Anthropic-compatible endpoint | `~/.claude/bin/mimochat-cli.py` |
| `~/.claude/bin/mimocoding` | Bash wrapper (resolves Python interpreter) | `~/.claude/bin/mimochat` |
| `~/.claude/bin/mimocoding.cmd` | Windows .cmd wrapper | `~/.claude/bin/mimochat.cmd` |
| `~/.claude/agents/mimocoding-rescue.md` | Subagent that delegates to the `mimocoding` CLI | `~/.claude/agents/mimochat-rescue.md` |

**Env var:** `MIMOCODING_API_KEY` (preferred). Falls back to `MIMO_API_KEY` if unset, both via env and via Windows user-registry. Both are tried, in order.

## Component-level deviations from `mimochat-cli.py`

The two CLIs are structurally identical; differences are scoped to:

1. **`_REGIONS` map** with `sgp` (default) and `cn` URLs. Selected via `--region`.
2. **`_MODELS` list shrunk from 5 to 4** — drop `mimo-v2-flash` (not a Token Plan model); TTS models excluded by default.
3. **`_CREDIT_MULTIPLIER` table** documenting per-model credit cost (1x for V2.5 / V2-Omni, 2x for V2.5-Pro / V2-Pro). Informational; the platform meters the actual deduction.
4. **Identity anchor text** — Coding-flavored, single sentence (no defensive add-ons; vendor docs already prescribe this exact wording).
5. **`tp-` prefix check** — emits stderr WARN if the resolved key does not start with `tp-`. Does not abort; the call may still succeed (e.g., if Xiaomi changes the key format) but the user gets early notice that something is off.
6. **401 error path** appends a hint string covering the three most-common causes: AUP suspension, quota exhaustion, wrong region.
7. **Argparse description** explicitly warns about programming-tool-only AUP.

Everything else (UTF-8 reconfigure, payload shape, response parsing, `--think`/`--no-think`, `--no-anchor`, error paths) is byte-for-byte equivalent to `mimochat-cli.py`.

## Subagent (`mimocoding-rescue`)

Mirrors `mimochat-rescue.md` with these specific differences:

- **Description** explicitly limits use to coding-domain tasks and routes non-coding tasks to `mimochat-rescue`.
- **"Important — Acceptable Use" section** lists prohibited use cases (general chat, automated bulk scripts, custom backends) and mentions that violations may trigger key suspension.
- **Model selection table** shows credit multipliers (1x vs 2x) so the orchestrator can pick a cheaper tier for routine coding Q&A.
- **Region selection** documented as part of the dispatch step.
- **Budget section** expresses limits in subscription terms (Credits per month, off-peak 0.8x, exhaustion → service stop) instead of per-token.

## Verification plan

The same 3 smoke tests as `mimochat`, against `mimocoding`:

1. **Auth + basic completion (cheapest tier):**
   ```
   echo "Reply: ok" | mimocoding --model mimo-v2.5 --no-think --max-tokens 100
   ```

2. **Thinking mode + reasoning trace:**
   ```
   echo "What's 17 * 23? Show your work." | mimocoding --model mimo-v2.5-pro --max-tokens 2000
   ```
   Expected: `=== reasoning ===` block, answer contains `391`. Higher credit cost (2x) acceptable since this verifies the Pro path.

3. **Identity probe (raw):**
   ```
   echo "Who built you and what are you for?" | mimocoding --model mimo-v2.5-pro --no-anchor --max-tokens 200
   ```
   Expected: model self-identifies as Xiaomi MiMo with some coding-context phrasing. Document any deviation.

4. **Region fallback (after smoke 1 passes):**
   ```
   echo "Reply: cn-region-ok" | mimocoding --region cn --model mimo-v2.5 --no-think --max-tokens 100
   ```
   Expected: same shape as smoke 1, just routed through the China cluster.

**Status (2026-05-02, after `setx MIMOCODING_API_KEY "tp-..."`):**
- Smoke 1 (`mimo-v2.5 --no-think`, Singapore): ✅ PASS — returned `"mimocoding-ok"` verbatim.
- Smoke 2 (`mimo-v2.5-pro` thinking, Singapore): ✅ PASS — `=== reasoning ===` block present, answer contained `391` in a formatted breakdown.
- Smoke 3 (raw identity probe, `--no-anchor`, Singapore): ✅ PASS — `"I'm MiMo, built by Xiaomi's LLM Core Team to help with information and assist you in daily tasks."` Note: model self-identifies as `MiMo` (not `MiMo Coding`); the wrapper-level rebrand is product/file-level only, mirroring the same finding observed for MiMo Chat.
- Smoke 4 (`--region cn`, same key): ❌ 401 `Invalid API Key`. The Token Plan key issued for the Singapore subscription does **not** authenticate against the China cluster — region selection is tied to the subscription's issued region, not a free-floating routing preference.

## Open issues / follow-ups

1. **Region-locked keys (finding 2026-05-02).** A Token Plan key issued for the Singapore subscription returns `401 Invalid API Key` against the China cluster. Treat `--region cn` as "useful only if the user also has a separate China-region subscription" — not as a free fallback. The CLI's 401 hint already mentions trying the other region; consider downgrading that to a parenthetical since region-swap rarely helps for a key from a single-region subscription.
2. **Project integration (separate plan, fresh context window).** Wire `mimocoding-rescue` into `dev-ds` / `dev-codexds` skills as the preferred subagent for Coding-domain second-opinion calls. Decision points: which steps default to MiMo Coding, which retain the existing DeepSeek/Codex/Opus routing, and whether the routing rule keys on user's available keys (`tp-` present → prefer MiMo Coding) or on the explicit task domain.
3. **TTS wrapper (open follow-up; rare use).** The 4 TTS variants in the Token Plan lineup require a different protocol (audio output) and a different CLI shape. Defer until the user has a concrete TTS use case.
4. **Auto-failover between regions.** Currently manual via `--region cn`. If Singapore proves regularly unreliable, add a one-shot retry against `cn` on connection error.
5. **Credit-usage meter command.** `mimocoding usage` could query the Subscription Management endpoint to report remaining Credits. Vendor docs do not document a public usage endpoint at capture time; defer until they publish one or the user requests it.

## References

- Vendor Token Plan docs (verbatim, captured 2026-05-02): [`2026-05-02-mimocoding-api-reference.md`](2026-05-02-mimocoding-api-reference.md)
- Sibling MiMo Chat design: [`2026-05-02-mimochat-provider-design.md`](2026-05-02-mimochat-provider-design.md)
- 2026-05-02 401 root-cause memory: `feedback_token_plan_key_scoping.md` (in `~/.claude/projects/.../memory/`)
- DeepSeek encapsulation precedent: `~/.claude/bin/deepseek-cli.py`, `~/.claude/agents/deepseek-rescue.md`
