# MiMo Coding (Xiaomi Token Plan) — Captured Reference (2026-05-02)

**Captured:** 2026-05-02 from user-supplied vendor documentation (Token Plan / Subscription / Coding flow)
**Source:** User prompt to Claude Code session on 2026-05-02 (no public URL provided by vendor at capture time)
**Purpose:** Frozen copy of the Token Plan / MiMo Coding pricing, model lineup, endpoint, and acceptable-use docs used to design the `mimocoding-cli.py` + `mimocoding-rescue.md` wrapper. Use this for future troubleshooting and for the next-time the vendor changes pricing or endpoints.

> **Disambiguation note.** Xiaomi has at least two Anthropic-compatible offerings:
> - **MiMo Chat** — per-token billing, endpoint `https://api.xiaomimimo.com/anthropic/v1/messages`. Captured separately in `2026-05-02-mimochat-api-reference.md`.
> - **MiMo Coding (Token Plan)** — subscription billing, endpoint `https://token-plan-{sgp,cn}.xiaomimimo.com/anthropic`. This document.
>
> Token Plan API keys are prefixed `tp-` and **must not be used against the MiMo Chat endpoint** — Xiaomi's TOS treats it as abuse and reserves the right to suspend the key.

> **Note:** The text below is a verbatim copy of what the user pasted into the brainstorming session. Headers, fields, and pricing are preserved exactly. Do not edit unless the user re-supplies updated docs (in which case append a dated update section rather than overwriting earlier capture).

---

## Token Plan

### Subscription Instructions

Token Plan is a dedicated subscription plan launched for AI programming scenarios. You can use the cost-effective subscription resource package to call the MiMo flagship large model in various mainstream AI development tools.

### Core Advantages

**Covers flagship models** — Supports MiMo-V2.5-Pro, MiMo-V2.5, MiMo-V2.5-TTS-VoiceClone, MiMo-V2.5-TTS-VoiceDesign, MiMo-V2.5-TTS, including a total of 8 models in the V2 series. It adopts a Token conversion mechanism, with transparent and controllable quotas.

**Elastic Subscription Plan** — Four-tier Gradient Package, meeting the needs from individual development to enterprise-level development.

**Multi-ecosystem Out Of The Box** — Compatible with mainstream development toolchains such as OpenCode, OpenClaw, and Claude Code.

### Usage Quota

#### Monthly Package

| Tier | Lite | Standard | Pro | Max |
|---|---|---|---|---|
| Pricing | $6/month, ¥39/month | $16/month, ¥99/month | $50/month, ¥329/month | $100/month, ¥659/month |
| Monthly Fixed Credit Limit | 60,000,000 (60M) Credits | 200,000,000 (200M) Credits | 700,000,000 (700M) Credits | 1,600,000,000 (1600M) Credits |

#### Annual Package

| Tier | Lite | Standard | Pro | Max |
|---|---|---|---|---|
| Pricing | $63.36/year, ¥411.84/year | $168.96/year, ¥1045.44/year | $528.00/year, ¥3474.24/year | $1056.00/year, ¥6959.04/year |
| Yearly Fixed Credit Limit | 720,000,000 (720M) Credits | 2,400,000,000 (2400M) Credits | 8,400,000,000 (8400M) Credits | 19,200,000,000 (19200M) Credits |

### Applicable Scenarios

| Tier | Description |
|---|---|
| Lite | Suitable for first-time lobster-tasting users. Using MiMo-V2.5/MiMo-V2-Omni as a benchmark, it can execute approximately **120 rounds** of medium to complex tasks. |
| Standard | Suitable for work enthusiasts who often use AI to improve their efficiency. Using MiMo-V2.5/MiMo-V2-Omni as a benchmark, it can execute approximately **400 rounds** of medium to complex tasks. |
| Pro | Suitable for developers and professional efficiency enthusiasts who use AI frequently every day. Using MiMo-V2.5/MiMo-V2-Omni as a baseline, approximately **1400 rounds** of medium to complex tasks can be executed. |
| Max | Suitable for high-intensity, hardcore users who use AI as a core productivity tool. Using MiMo-V2.5/MiMo-V2-Omni as a baseline, it can execute approximately **3200 rounds** of medium to complex tasks. |

The above is the scope of scenarios for the monthly package. The order of magnitude of task processing for the annual package is approximately **12x** that of the monthly package.

### Discount Offer

> 0.8x consumption at night, 12% discount on the first purchase of a package, 30% discount (for existing users) or 23% discount (for new users) on the first activation of auto-renewal, 12% discount on consecutive annual subscriptions, and existing users of the Token Plan exclusively enjoy the "Credits Usage Refresh and Reset" event once after the launch of the V2.1 model.

**Package Usage Refresh and Reset:** To celebrate the official launch of MiMo-V2.5, users who purchased the Token Plan before 22:00 on April 22, Beijing Time, will have their consumed Credits completely reset, regardless of the current usage of their package, with the validity period remaining unchanged.

**First Purchase Discount:** Enjoy 12% off on your first purchase, available only once per account.

**First-time auto-renewal discount:** New users who have never subscribed to a package before enjoy a 23% discount (77% of the original price) when they first activate auto-renewal, while existing users who have subscribed to a package before enjoy a 30% discount (70% of the original price) when they first activate auto-renewal. The first-time auto-renewal discount is mutually exclusive with the first-purchase discount, and each account can only enjoy it once.

**Continuous annual subscription:** Enjoy a 12% discount compared to continuous monthly subscription; the first purchase / first activation auto-renewal discount does not apply to annual subscriptions.

**Nighttime discount rate:** During off-peak hours (0:00–8:00 Beijing Time, i.e., 16:00–24:00 UTC), the consumption coefficient is 0.8x.

### Supported Models

All packages support a total of 8 models, including MiMo-V2.5-Pro, MiMo-V2.5, MiMo-V2.5-TTS-VoiceClone, MiMo-V2.5-TTS-VoiceDesign, MiMo-V2.5-TTS, MiMo-V2-Pro, MiMo-V2-Omni, and MiMo-V2-TTS.

### Credit Consumption

Credit is deducted according to the number of tokens, and the credit of Pro and Omni is consumed in parallel at a 1:2 ratio, not independently. **TTS series models are free for a limited time and do not consume package tokens.**

For example, if you have subscribed to the Lite plan, you can call the MiMo-V2.5 series models individually or in combination. After using 10M Tokens of MiMo-V2.5-Pro, it is equivalent to consuming 20M Credits, and you can still enjoy 40M Tokens of MiMo-V2.5 (equivalent to 40 Credits). You can view the quota and usage of your current plan in **Subscription Management**.

#### V2.5 series

- **MiMo-V2.5:** 1x (equivalent to the original Token consumption rate)
- **MiMo-V2.5-Pro:** 2x (equivalent to 2 times the Token consumption rate)
- **MiMo-V2.5-TTS-VoiceClone, MiMo-V2.5-TTS-VoiceDesign, MiMo-V2.5-TTS:** 0x (limited-time free, no Credit consumption)

#### V2 series

- **MiMo-V2-Omni:** 1x (equivalent to the original Token consumption rate)
- **MiMo-V2-Pro:** 2x (equivalent to 2 times the Token consumption rate)
- **MiMo-V2-TTS:** 0x (limited-time free, no Credit consumption)

### Quota Exhausted

When the monthly total quota of the package is exhausted, the system will stop service and will not continue to consume your bonus or account balance.

**If you need to continue using it:** Please purchase an upgrade package to unlock new package resources; or switch to the regular API, which is billed at the per-token unit price, and you can continue using it without usage limits.

### Base URL

Subsequently, one of the following Base URLs needs to be configured in the AI programming tool (protocol varies by tool, Base URL is subject to the display on the Subscription page). For specific operations, please refer to the corresponding AI programming tool user-guide document.

---

## Package Usage (Acceptable Use Policy)

The Token Plan package quota can **only be used in programming tools** (such as OpenClaw, OpenCode, etc.), and it is **prohibited** to use it in the form of API calls for request behaviors in clearly non-Coding scenarios such as automated scripts and custom application backends.

If an API Key corresponding to a package is used for calls that exceed the permitted scope, it will be considered a **violation or abuse**, and the platform has the right to take measures such as **suspending service and banning the API Key** against the relevant subscription.

---

## Quick Guide

Quick Start Token Plan, from subscribing to a package to using the MiMo model in coding tools.

### Subscribe to Token Plan

Visit Token Plan, select and purchase the appropriate subscription plan as needed.

### Obtain the Base URL and API Key exclusive to the package

After successful subscription, you can go to the **Subscription page** to obtain the Base URL and API Key exclusive to the package.

**API Key:** On the Subscription page, obtain your exclusive API Key (in the format of **`tp-xxxxx`**).

**Base URL:** Subsequently, one of the following Base URLs needs to be configured in the AI programming tool (protocol varies by tool, Base URL is subject to the display on the Subscription page). For specific operations, please refer to the corresponding AI programming tool user-guide document.

#### OpenAI Compatibility Protocol

- **China Cluster:** `https://token-plan-cn.xiaomimimo.com/v1`
- **Singapore Cluster:** `https://token-plan-sgp.xiaomimimo.com/v1`

#### Anthropic Compatibility Protocol

- **China Cluster:** `https://token-plan-cn.xiaomimimo.com/anthropic`
- **Singapore Cluster:** `https://token-plan-sgp.xiaomimimo.com/anthropic`

> **Wrapper default (project-specific):** Our `mimocoding` CLI hardcodes the **Singapore Cluster** as its only endpoint. The `--region` flag was removed on 2026-05-02 after a smoke test confirmed that Singapore-issued Token Plan keys do not authenticate against the China cluster (region-lock; see Notes #8 below). To support both regions, the user would need separate subscriptions per region; at that point the flag could be reintroduced.

---

## Recommended Identity Anchor (vendor-supplied via user)

```
You are MiMo Coding, supporting AI Agent and Programming Tools developed by Xiaomi
```

Our wrapper auto-prepends this exact text (with a trailing period and space) to every `--system` prompt unless `--no-anchor` is passed.

---

## Notes for Future Troubleshooting

1. **API key prefix `tp-` is the disambiguator.** A `tp-`-prefixed key is a Token Plan key for MiMo Coding; non-prefixed keys are for the per-token MiMo Chat product. Routing them to the wrong endpoint is a TOS violation that the platform may police via key suspension.
2. **401 "Invalid API Key" on a `tp-` key** has at least three plausible causes: (a) key was suspended for prior misuse against `api.xiaomimimo.com` (MiMo Chat endpoint), (b) the subscription's monthly Credit Limit is exhausted, (c) the wrong cluster (try `--region cn` if `sgp` fails or vice versa).
3. **The 8-model count includes 4 TTS models** (`MiMo-V2.5-TTS-VoiceClone`, `MiMo-V2.5-TTS-VoiceDesign`, `MiMo-V2.5-TTS`, `MiMo-V2-TTS`) which are **out of scope** for our chat-completion CLI. The chat-completion subset is 4 models: `mimo-v2.5-pro`, `mimo-v2.5`, `mimo-v2-pro`, `mimo-v2-omni`. `mimo-v2-flash` is **not** a Token Plan model.
4. **Credit consumption is metered server-side.** The `_CREDIT_MULTIPLIER` table in `mimocoding-cli.py` is informational only — it doesn't affect what's billed; it just helps the user pick a tier (1x for V2.5 / V2-Omni, 2x for V2.5-Pro / V2-Pro).
5. **Monthly reset:** when monthly quota exhausts, the API stops responding successfully. The user must wait for the next billing cycle, upgrade the package, or fall back to the per-token MiMo Chat API for unlimited (paid per token) use.
6. **Off-peak window (0.8x credit cost):** 16:00–24:00 UTC (= 0:00–8:00 Beijing). Schedule heavy bulk reasoning during this window if cost-sensitive.
7. **Beware the "lobster" quirk in vendor docs.** The Lite tier's "lobster-tasting users" phrase appears to be a translation artifact from the vendor's Chinese marketing copy ("尝鲜用户" = "first-tasters", literally "lobster tasters" in some idioms). Not actually about lobsters.
8. **Region-locked keys (empirical, 2026-05-02).** A Token Plan API key issued for the Singapore cluster returned `401 Invalid API Key` when re-routed to the China cluster (`token-plan-cn.xiaomimimo.com/anthropic/v1/messages`). The vendor's docs do not explicitly state region-locking, but treat the `--region {sgp,cn}` flag as a hint about which subscription you hold, not as a runtime fallback option. If a user subscribes in both regions, they receive separate keys per region.
