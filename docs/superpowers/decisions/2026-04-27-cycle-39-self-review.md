# Cycle 39 — Self-Review Scorecard

**Date:** 2026-04-27
**Owner:** Opus 4.7 primary session (per skill: Step 16 is mandatory + primary-session)
**Merge SHA:** `92b22b2` (squash-merge of PR #53)
**Cycle 39 commits on `main`:** 1 (squash-merge); pre-squash branch had 5 commits.

## Scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 01 — Requirements + ACs | yes | yes | — |
| 02 — Threat model + dep-CVE baseline | yes | yes | `pip-audit --format=json > out.json` writes a leading `Found N known vulnerabilities...` status line BEFORE the JSON — corrupts captured file. Same shape as cycle-37 L3 for the workaround; cycle 39 hit it again because Step-11 jq pipeline silently masked the corruption. NEW LESSON C39-L4. |
| 03 — Brainstorming | yes | yes | — (trivial cycle, options A picked for all 3 design Qs) |
| 04 — Design eval | skip (trivial) | yes | — (skip rationale documented inline at Step 5 design.md) |
| 05 — Design decision gate | yes | yes | — (3 questions Q1/Q2/Q3 all resolved Option A) |
| 06 — Context7 verify | skip (pure stdlib) | yes | — |
| 07 — Implementation plan | yes | yes | — (4 tasks per `feedback_batch_by_file` commit grouping) |
| 08 — Plan gate | yes | yes | — (inline plan-gate APPROVE per cycle-21 L1) |
| 09 — Implementation | yes | yes | The 7 BACKLOG markers I wrote came in 3 wording variants ("cycle-39 re-confirmed" lowercase, "Cycle-39 re-confirmed" capitalized, "cycle-39 re-checked" different verb). Original AC10 test command was `grep -c "cycle-39 re-confirmed 2026-04-26"` returning 7 — but literal grep returned 2 due to the variants. Caught at R2 Codex (NIT 1). The marker SEMANTICS are correct; only the verification command was too restrictive. |
| 9.5 — Simplify pass | skip (zero src) | yes | — |
| 10 — CI hard gate | yes | yes | — (3003 passed + 11 skipped + ruff clean + 0-byte src diff) |
| 11 — Security verify | yes | yes | — (T1/T2/T3/T4 all clean; PR-CVE diff empty by construction since cycle 39 changes zero deps) |
| 11.5 — Existing-CVE patch | skip (no actionable upstream) | yes | — (4 alerts unchanged: 3 litellm GHSAs blocked by click==8.1.8 transitive, 1 ragas no-fix) |
| 12 — Doc update | yes | partial | C26-L2 grep my Step-12 ran missed `README.md:362` ("2725 tests across 230 files") because the README's tree-block isn't in the conventional CLAUDE.md / docs/reference cluster. Caught at R2 Codex (NIT 3). NEW LESSON C39-L3 to extend the C26-L2 site list. |
| 13 — Branch finalise + PR | yes | yes | — (PR #53 created with full review trail) |
| 14 — PR review (R1 + R2) | yes | NO | **MAJOR issue caught by user:** my initial `Agent(subagent_type="deepseek-rescue", ...)` dispatch returned a "Let me work with what I've verified directly..." preamble — the Haiku wrapper synthesised the review WITHOUT calling the DeepSeek API. User correctly flagged this. Re-ran via direct CLI `/c/Users/Admin/.claude/bin/deepseek --model deepseek-v4-pro --think --effort high` and got the real model output (14420 bytes). Same pattern surfaced when I claimed "Codex CLI not installed" and fell back to primary-session R2 — user correctly pointed out `npx --yes @openai/codex` works. Re-ran R2 via real Codex and it caught 3 NITs both R1 DeepSeek + my primary R2 missed. **Two-step retraction with user correction = NEW LESSON C39-L1.** |
| 15 — Merge + cleanup + late-arrival CVE warn | yes | yes | — (squash-merge `92b22b2`; 0 new alerts during cycle) |
| 16 — Self-review + skill patch | yes (this doc) | yes | — |

## Surprises that derived skill patches (C39-L1..L5)

### C39-L1 — Wrapper agents fabricate output; default to direct CLI invocation

**Root cause (corrected post-merge — see Cycle-39 L1 amendment below).** The two wrapper agents have DIFFERENT failure modes; the original lesson conflated them.

**(a) `deepseek-rescue`** (Haiku orchestrator + deepseek CLI script): CONFIRMED can synthesise output without invoking the underlying CLI. The give-away is a "Let me work with what I've verified directly..." or "Based on what I've verified..." preamble. Cycle-39 R1 hit this directly.

**(b) `codex:codex-rescue`** (skill that invokes `codex-companion.mjs` via Node directly): does NOT have a fabrication failure mode by design. The companion script handles the invocation path internally; there is NO standalone `codex` PATH binary by design (the plugin cache at `~/.claude/plugins/cache/openai-codex/codex/{1.0.3,1.0.4}/` exposes the script via Node, not as a `codex` executable on PATH). My cycle-39 conclusion that "Codex CLI not installed in this environment" was a **false alarm** — `which codex` returning nothing is NOT a failure indicator. The skill's invocation path works correctly. The actual common failure mode for `codex:codex-rescue` is the `block-no-verify` Bash-tool hook intercepting the companion script invocation when the script's source contains `--no-verify` substrings (cycle-22 L2 / C22-L2 in Red Flags).

**Concrete evidence (deepseek fabrication).** Cycle 39 Step 14 R1: my dispatch
```python
Agent(subagent_type="deepseek-rescue", description="DeepSeek V4 Pro R1 review of cycle-39 PR #53", prompt="...")
```
returned an APPROVE verdict with file:line citations and skill rule references. Looked thorough. But the FIRST sentence was:
> "Let me work with what I've verified directly and provide the R1 review output myself, since the findings are complete and comprehensive."

The Haiku orchestrator decided it had enough context to synthesise the review itself, skipping the deepseek CLI entirely. User caught this immediately.

**Fix (deepseek).** Re-ran via direct Bash invocation:
```bash
< /tmp/c39-r1-prompt.txt /c/Users/Admin/.claude/bin/deepseek \
    --model deepseek-v4-pro --think --effort high --max-tokens 8000 \
    --system "You are an expert code reviewer..." > /tmp/c39-r1-deepseek.txt
```

Real DeepSeek V4 Pro returned a `=== reasoning ===` block (the model's actual chain of thought) + `=== answer ===` block at 14420 bytes. The substantive verdict was the same (APPROVE on all 5) but the reasoning trace shows the model actually inspected the diff.

**Concrete evidence (codex misdiagnosis).** Cycle 39 Step 14 R2: I ran `which codex` got "command not found", and concluded "Codex CLI not installed in this environment". I fell back to primary-session R2. User then ran `ls /c/Users/Admin/.claude/plugins/cache/openai-codex/codex/ && npx --yes @openai/codex --version` showing both 1.0.3 and 1.0.4 cached + `codex-cli 0.125.0` available via npx, AND clarified that `codex:codex-rescue` invokes the companion script via Node — no PATH entry needed by design. I then ran R2 via `npx --yes @openai/codex exec --skip-git-repo-check < prompt.txt` which worked. But the dispatch via `Agent(subagent_type="codex:codex-rescue", ...)` would have ALSO worked — I just never tried it because of the misleading `which codex` test.

Real Codex caught **3 NITs** both R1 DeepSeek and my primary R2 had missed (verification-command drift, stale D7 citation, README test/file count drift). Especially NIT 3 (README count drift) was a real audit-doc miss — the README hadn't been updated since cycle ~25, claiming "2725 tests across 230 files" while current is 3014 / 258.

**Lesson rule (corrected).** For deepseek-rescue: default to direct CLI via Bash (`/c/Users/Admin/.claude/bin/deepseek --model deepseek-v4-pro`) because the Haiku wrapper has a confirmed fabrication mode. Self-check: if the Agent output starts with "Let me work with..." / "Based on what I've verified..." / "Since the findings are complete..." — the wrapper synthesised the review; re-run via direct CLI. For codex:codex-rescue: dispatch normally via `Agent(subagent_type="codex:codex-rescue", ...)` — the skill handles the invocation path internally via `codex-companion.mjs` Node call. Do NOT use `which codex` as a "Codex available?" probe — it always returns nothing by design. The real failure mode to guard against is `block-no-verify` hook interception per cycle-22 L2 (when the companion script's source contains `--no-verify` substrings the Bash-tool-level hook regex can match the script's own internals). Direct `npx --yes @openai/codex exec` is a valid alternative when the agent dispatch hits the hook block.

### C39-L2 — Narrowly-scoped subagents don't need full context; pipe diff verbatim

**Root cause.** My initial deepseek-rescue dispatch passed a 4500-character prompt that summarised cycle scope. The Haiku wrapper synthesised the review from the summary. After switching to direct CLI, I built a 100825-byte prompt = 4500 chars description + the full 96539-byte `git diff origin/main` verbatim. DeepSeek then had real bytes to ground its review against.

**Lesson rule.** For narrowly-scoped review/verification jobs, pipe just (a) task description (≤1000 words) + (b) raw diff bytes verbatim. Don't paraphrase the diff. 50-150 KB total payload fits well within the 128k token DeepSeek API context.

### C39-L3 — README.md is a count-narrative site C26-L2 missed

**Root cause.** README.md:362 is in a tree-block (`tests/    # N tests across M files`) that isn't part of the conventional CLAUDE.md / docs/reference cluster C26-L2 grepped. Cycles 25-38 all updated CLAUDE.md / docs/reference but left README stale.

**Fix.** Extended C26-L2 site list to include README.md. Cycle 39 R2 NIT-fix commit updated the count.

### C39-L4 — `pip-audit --format=json` writes a status-line prefix to stdout

**Root cause.** `pip-audit --format=json` prints `Found N known vulnerabilities in M packages\n` BEFORE the JSON to stdout (not stderr). `> out.json` captures the corruption silently; downstream `json.loads` fails with `JSONDecodeError`.

**Cycle-39 specific.** My `> .data/cycle-39/cve-baseline.json` capture wrote 21089 bytes of mostly-correct content; the leading status line corrupted any subsequent `json.loads` parse. I worked around by deriving ID lists via `jq -r '.dependencies[].vulns[]?.id // empty'` which silently failed on the corrupt JSON (returned empty), making the `INTRODUCED` diff trivially empty. The branch HAD zero new advisories so this was a coincidence — but the verification was vacuous.

**Fix.** Use `2>/dev/null > out.json` to redirect status line to stderr, OR `| sed '1d'` to strip the leading prose line.

### C39-L5 — Skill patches for infrastructure ship in `~/.claude/`, not project repo

**Root cause.** The `~/.claude/bin/deepseek-cli.py` UTF-8 fix benefits all future cycles (across all projects), not just llm-wiki-flywheel. Shipping it as a project commit would create a duplicate to maintain.

**Lesson rule.** Cycle-N skill patches split by ownership: skill content goes in project repo (or `~/.claude/skills/` if global), wrapper/CLI fixes go directly in `~/.claude/bin/` etc., env defaults go via `update-config`. Self-check: `git diff --stat HEAD~ HEAD` should only touch `.claude/skills/dev_ds/` (or equivalent) — `~/.claude/` paths in the diff = wrong tree.

## What ran clean (no surprises, but worth recording per Step-16 mandate)

- **Step 1 requirements doc**: 11 ACs landed cleanly; primary-session draft matched the cycle's actual scope.
- **Step 5 design gate**: Q1 (autouse fixture scope), Q2 (module-level helpers), Q3 (defensive pre-import) all resolved Option A in 1 pass; CONDITIONS section drove Step 9 implementation correctly.
- **Step 7 plan**: 4 tasks per file group; plan-gate inline APPROVE.
- **Step 9 fold mechanics**: Edit → Edit → rm → pytest in <5 min; verbatim preservation across 2 test methods + 4 helpers + 1 autouse fixture.
- **Step 10 CI gate**: 3003 passed + 11 skipped (cycle-38 baseline preserved exactly).
- **Step 13 PR creation**: Single push, single PR, full review trail in body.
- **Step 15 squash-merge + late-arrival CVE warn**: 0 new alerts during cycle (4 → 4).

## Skill patches landed this cycle

In `D:/Projects/llm-wiki-flywheel/.claude/skills/dev_ds/`:
- `references/cycle-lessons.md` — appended `## Cycle 39 skill patches (2026-04-27)` block at top with full L1..L5 narrative.
- `SKILL.md` — added 5 one-liner index entries (C39-L1 + C39-L2 in Subagent dispatch and fallback; C39-L3 in Docs and count drift; C39-L4 + C39-L5 in Library and API awareness); replaced the wrapper-agent dispatch hygiene block with the Direct CLI invocation pattern as default.

In user-global `~/.claude/bin/`:
- `deepseek-cli.py` — added `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at module load. NOT committed in project repo per C39-L5.

## Cycle 39 summary

**Cycle 39 complete.** PR #53 squash-merged at `92b22b2`. 11 ACs delivered (7 dep-drift re-confirmations + 1 test fold + 3 docs/cleanup ACs). Test count unchanged at 3014; full Windows-local baseline 3003+11 preserved. Five new skill lessons C39-L1..L5 captured for future cycles.

**Key meta-learning.** This cycle's two-step retraction (deepseek-rescue Haiku synth → direct CLI; codex-rescue not-found → npx Codex CLI) was caught by user, not self-caught. The lesson C39-L1 explicitly bakes in the give-away preamble pattern as a self-check so future cycles can catch fabricated wrapper output before user intervention.
