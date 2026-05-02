# Cycle 56 — Self-review (Step 24)

**Date:** 2026-05-02
**Merge commit:** `d77f582` (PR #78 squash → main)
**Branch state at merge:** 10 commits on `cycle-56-batch` (9 cycle-56 commits + 1 merge), file count 219 → 214, test count preserved 3026.
**Trial context:** First cycle dispatched via the new `dev-mimo-opus` skill — May 2026 Xiaomi MiMo trial.

---

## Step-by-step scorecard

| Step | Executed? | First-try? | Surprised by anything? |
|------|-----------|------------|------------------------|
| 1 — Requirements + ACs | yes | yes | — |
| 2 — Threat model + dep-CVE baseline | yes | no | `MIMOCODING_API_KEY`/`MIMOCHAT_API_KEY` exist in User-scope env via `setx`, NOT in current bash shell. PowerShell rehydration via `[System.Environment]::GetEnvironmentVariable("...","User")` was needed. |
| 3 — Brainstorming | yes (in-doc) | yes | — |
| 4 — Design eval R1 / R2 | R1 only (R2 trivially-skipped per fold-cycle rule) | yes | — |
| 5 — Design decision gate | yes (8 questions inline) | yes | — |
| 6 — Context7 verification | skipped (no third-party API) | n/a | — |
| 7 — Implementation plan | yes (primary session per C14-L1 + C37-L5) | yes | — |
| 8 — Plan gate | yes (primary session per C21-L1) | yes | — |
| 9 — Implementation (5 folds) | yes | **NO — primary-session deviation** | AC1, AC2, AC3a authored in primary session before user surfaced "should be MiMo Coding per the trial." Switched to mimocoding-rescue from AC3b onward. **C56-L1 lesson candidate.** |
| 10 — /simplify | skipped (zero src/ diff) | n/a | — |
| 11 — SAST / secrets scan | skipped (no code diff) | n/a | — |
| 12 — CI hard gate | yes | no | Local pytest crashes mid-suite with Windows STATUS_ACCESS_VIOLATION (-1073741819) in pyreadline3 — pre-existing, reproduces on main. CI on ubuntu-latest unaffected (per cycle-36 single-OS gate). Workaround `pytest -p no:capture -p no:debugging` partially helps but not for full suite. **C56-L2 lesson candidate.** |
| 13 — Coverage delta | skipped (test-fold exemption) | n/a | — |
| 14 — Security verify + Class-B CVE diff | yes | yes | Class-B diff empty, all threat items implemented. |
| 15 — Existing-CVE re-confirm | yes | yes | Same 4 unresolved Class-A advisories; no new arrivals. |
| 16 — IaC/container/SBOM | skipped (no deployable artifacts) | n/a | — |
| 17 — Doc update | yes (mimochat-rescue, 3.3s) | no | MiMo Chat verdict had a phrasing-suggestion artifact ("trailing t" misread) caused by PowerShell box-drawing-char mangling in the prompt. Defensive — used Out-String pipe on later calls. **C56-L3 lesson candidate.** |
| 18 — Branch finalise + PR | yes | yes | PR #78 opened. |
| 19 — Signing | skipped (no signing policy) | n/a | — |
| 20 R1 | yes (DeepSeek + Sonnet parallel) | no | DeepSeek APPROVE; Sonnet REQUEST-CHANGES → 1 BLOCKER (vacuous test pre-existing on main, fold preserved the bug). **C56-L4 lesson candidate.** |
| 20 R1 fix | yes (mimocoding-rescue, ~30s) | yes | Owner-module patch + spy + `assert calls`. Revert-verify FAIL→restore green. |
| 20 R2 | yes (Codex + Sonnet parallel) | yes | Both APPROVE. |
| 20 R3 | not-triggered per cycle-17 L4 (11 ACs / 8 design-gate Qs / no new write-surface) | n/a | — |
| 21 — Merge + late-arrival CVE warn | yes | yes | Merged at `d77f582`; no late-arrival CVEs. |
| 22 — Deploy gate | skipped (no deployable) | n/a | — |
| 23 — Post-deploy smoke | skipped (no deploy) | n/a | — |
| 24 — Self-review + skill patches | yes (this doc) | yes | — |

**Clean rows:** 14/24. **Surprises:** 4 (sized appropriately for a first-trial-cycle).

---

## MiMo trial telemetry (input for 2026-05-31 writeup)

| Step | Subagent | Model | Latency | Outcome |
|------|----------|-------|---------|---------|
| Step 2 baseline | direct CLI | n/a | — | pip-audit live env, 4 vulns same as cycle 55 |
| Step 4 R2 | mimochat-rescue | mimo-v2.5-pro | n/a (skipped) | trivial-collapse rule fired |
| Step 7 plan | (primary session) | n/a | n/a | C14-L1 / C37-L5 sizing heuristic — primary session faster |
| Step 8 plan-gate | (primary session) | n/a | n/a | C21-L1 inline resolution |
| Step 9 AC1 | (primary session) | n/a | n/a | **Trial deviation** — should have been mimocoding-rescue |
| Step 9 AC2 | (primary session) | n/a | n/a | **Trial deviation** |
| Step 9 AC3a | (primary session) | n/a | n/a | **Trial deviation** — user correction landed mid-AC3 |
| Step 9 AC3b | mimocoding-rescue | mimo-v2.5-pro | 12.5s | PASS verbatim fold |
| Step 9 AC4 | mimocoding-rescue | mimo-v2.5-pro | 13.8s | PASS (1 false-positive concern: missing-import flag from limited file context) |
| Step 9 AC5 | mimocoding-rescue | mimo-v2.5-pro | 8.8s + 11.9s redispatch | PASS (PowerShell `$verdict.Substring` bug in subagent — non-fatal, captured) |
| Step 17 doc-sync | mimochat-rescue | mimo-v2-flash | 3.3s | PASS (5 phrasing suggestions, 2 incorporated) |
| R1 fix | mimocoding-rescue | mimo-v2.5-pro | ~30s | PASS (vacuous test repaired) |
| Step 20 R1 DeepSeek | deepseek-rescue | deepseek-v4-pro | 204s | APPROVE (architecture lens) |
| Step 20 R1 Sonnet | everything-claude-code:code-reviewer | sonnet | 412s | REQUEST-CHANGES (1 BLOCKER) |
| Step 20 R2 Codex | codex:codex-rescue | codex | 208s | APPROVE |
| Step 20 R2 Sonnet | everything-claude-code:code-reviewer | sonnet | 120s | APPROVE |

**Token-Plan TOS adherence:** all coding folds + R1-fix routed through mimocoding (tp- key). Step 17 docs routed through mimochat (sk- key). Zero TOS violations. Zero 401s.

**Identity-confusion rate:** 0/4 MiMo Coding dispatches confused identity. Wrapper auto-anchor effective.

**Subagent failure rate:** 1 transient (AC5 PowerShell substring bug, re-dispatched cleanly). 0 fatal.

**Average MiMo Coding latency:** ~12s (3 successful coding folds + 1 R1-fix). MiMo Chat: ~3s for short doc-sync. Both well within human-pace budget.

---

## Skill-patch lessons

### C56-L1 — Sizing-heuristic must NOT short-circuit a trial-purpose dispatch

**Rule:** When operating under a trial-skill (e.g. `dev-mimo-opus`, `dev-codexds`, `dev-ds-codex-gate`), the skill's Step 9 owner contract is BINDING regardless of the C13-L2 / C37-L5 sizing heuristics that would normally route small folds to the primary session. The whole purpose of a trial is to gather telemetry on the trial-vendor's behaviour; falling through to primary session because "it's only 30 LoC" defeats the trial.

**Why:** Cycle 56 AC1, AC2, AC3a were authored in primary session before the user surfaced this. Net effect: 3 of 6 fold commits had ZERO MiMo telemetry, which is precisely the data the May 2026 writeup needs.

**How to apply:** When the skill's Step 9 prose names a specific subagent owner (e.g. "MiMo Coding implements"), treat that as a HARD requirement when the cycle is being run under that skill. The C13-L2 sizing heuristic still applies for `feature-dev` (non-trial), but for trial skills, dispatch is mandatory. Step 24 self-review should explicitly flag any deviations as trial-data gaps.

**refines:** none — net-new for trial-skill workflows.

### C56-L2 — Windows pyreadline3 STATUS_ACCESS_VIOLATION blocks Step 12 local CI proxy

**Rule:** When local pytest crashes with exit `-1073741819` (STATUS_ACCESS_VIOLATION 0xC0000005), it's a pyreadline3 / Windows interop issue that affects specific Python paths invoking `logging.warning` (notably `kb.utils.text.yaml_sanitize` and `kb.utils.io.sweep_orphan_tmp`). The `pytest -p no:capture -p no:debugging` workaround helps for SINGLE-FILE runs but not for full-suite. CI on ubuntu-latest is unaffected (cycle-36 strict-gate). Step 12 local CI proxy must be approximated via per-receiver pytest + ruff + pip-audit, with the full-suite check delegated to the GHA workflow.

**Why:** Cycle 56 Step 12 local pytest crashed mid-suite. Wasted ~5 min trying alternate flags before realizing it reproduces on main and is pre-existing.

**How to apply:** When local Windows pytest crashes mid-suite with -1073741819, do NOT debug locally. Run: (a) per-receiver pytest with `-p no:capture -p no:debugging` for the cycle's touched files, (b) `pytest --collect-only -q` to verify count, (c) ruff check + format check, (d) defer full-suite green to the GHA CI artifact. File a cycle-N+ BACKLOG entry for the root-cause investigation.

**refines:** cycle-22 L3 (full-suite must be green at Step 12) — extends with Windows-specific exemption when CI handles the gate authoritatively.

### C56-L3 — PowerShell `$variable.Substring` and box-drawing chars in prompts

**Rule:** When piping prompts to `mimocoding.cmd` / `mimochat.cmd` via PowerShell `here-string | & .cmd` pattern: (a) box-drawing characters (`──`, `─`, `│`) in prompt text get mangled by PowerShell's stdout encoding under some console-host states; (b) calling `.Substring(0, N)` on a returned response without first piping through `Out-String` can hit a "method not found on array" if the response was multiline (PowerShell wraps multiline output in `string[]`).

**Why:** Cycle 56 AC5 dispatch hit `$verdict.Substring` failure on first call (~11.9s wasted), succeeded on re-dispatch with `Out-String`. Step 17 MiMo Chat verdict had a "trailing t" character from a mangled section-header drawing-char.

**How to apply:** In any subagent that wraps `mimocoding.cmd` / `mimochat.cmd` via PowerShell:
- Pipe response through `Out-String` before `.Substring` calls: `($response | Out-String).Substring(0, [Math]::Min(100, $response.Length))`.
- For prompts containing box-drawing chars in section comments, either ASCII-fy them before sending OR pre-encode the prompt as UTF-8 bytes via temp file: `[IO.File]::WriteAllText("$env:TEMP\mimo-prompt.txt", $prompt, [System.Text.Encoding]::UTF8)` then pipe that file in.

**refines:** cycle-22 L2 (Codex dispatch hygiene — bare-token wrapping) — extends to PowerShell-piped wrappers in general.

### C56-L4 — Vacuous tests inherited from pre-fold sources are R1-BLOCKER fodder

**Rule:** Fold cycles must include a "vacuous-test pre-flight scan" of the source file BEFORE folding. Specifically: grep the source for `monkeypatch.setattr(.*raising=False)` AND `inspect.getsource` AND `re.findall(.*\.py)` patterns. ANY hit must be either (a) repaired in the fold commit (per cycle-15 L2 DROP-with-test-anchor — keep the test, make it actually exercise production), or (b) explicitly flagged as a KNOWN-WEAK fold migration with a cycle-N+ BACKLOG upgrade candidate before the fold commit lands.

**Why:** Cycle 56 AC1 folded `test_kb_detect_drift_none_changed_sources` verbatim from `test_v01012_mcp_validation.py`. The source test was vacuous on main (consumer-side `monkeypatch.setattr(_h, "X", ..., raising=False)` against a function-local-import target). R1 Sonnet caught it as BLOCKER, forcing an R1-fix commit. Pre-flight scan would have surfaced this at design time — either fold-with-fix in same commit OR explicit deferral.

**How to apply:** Add to the dev-mimo-opus skill's Step 7 implementation plan template: for every fold AC, list the source file's `raising=False` count + `inspect.getsource` count + source-scan-test count. Zero on all three = clean fold. Non-zero on any = either repair in fold commit (citing cycle-15 L2) or file BACKLOG upgrade candidate per cycle-52 L1 / cycle-53 L1 precedent.

**refines:** cycle-23 L2 (inspect-source tests) + cycle-15 L2 (DROP-with-test-anchor) — extends the discipline upstream into fold pre-flight.

### C56-L5 — User-scope `setx` env vars don't propagate to current bash session

**Rule:** Windows User-scope environment variables set via `setx` (or system Properties → Advanced → Environment Variables) are read into NEW shells, NOT the currently-running shell. The current bash session inherits its env from Claude Code's spawn-time env; `setx` updates the User registry which is read by NEW `cmd.exe` / `powershell.exe` / `bash.exe` invocations.

**Why:** Cycle 56 Step 2 hit "MIMOCODING_API_KEY UNSET" from bash, even though the user had set it via `setx`. PowerShell `[System.Environment]::GetEnvironmentVariable("...","User")` reads the registry directly and works around the inheritance gap.

**How to apply:** For any project that depends on `setx`-style env vars (MIMOCODING_API_KEY / MIMOCHAT_API_KEY / GITHUB_TOKEN sometimes / etc.), the dispatch wrapper script MUST re-hydrate via `[System.Environment]::GetEnvironmentVariable($name,"User")` before invocation. Document this in the dispatch hygiene block at the top of dev-mimo-opus / dev-codexds / dev-ds skills. The `mimocoding-rescue` and `mimochat-rescue` subagent definitions should embed this hydration pattern in their PowerShell invocation examples.

**refines:** none — net-new for Windows-on-Claude-Code workflows.

---

## Index entries to add to dev-mimo-opus SKILL.md

Under "Accumulated rules index":

- **C56-L1** — Trial-skill Step 9 dispatch is binding even for small folds (overrides C13-L2 / C37-L5 sizing for trial cycles).
- **C56-L2** — Windows pyreadline3 STATUS_ACCESS_VIOLATION on full-suite local pytest; per-receiver + ruff + CI artifact substitutes for Step 12 local proxy.
- **C56-L3** — PowerShell `Out-String` + UTF-8 temp-file for box-drawing prompts feeding `mimocoding.cmd` / `mimochat.cmd`.
- **C56-L4** — Fold pre-flight scan for vacuous tests (`raising=False`, `inspect.getsource`, source-scan): repair-in-fold OR BACKLOG cycle-N+ upgrade candidate, NOT inherit-and-pray.
- **C56-L5** — User-scope `setx` env vars need PowerShell `[System.Environment]::GetEnvironmentVariable($name,"User")` rehydration; current bash session does NOT inherit.

(Five lessons; one above the typical cycle-cadence count, reflecting that this was the first cycle of a new trial skill.)

---

## Cycle 56 close-out

- Cycle complete; PR #78 merged at `d77f582`.
- Picks marker `cycle-56-batch` at SHA `29d3e35` (which still points to the design+plan commit) is preserved in branch history for parallel-cycle visibility — do NOT prune until cycles 53 and 54 also merge.
- Trial telemetry captured in this doc + commit-message bodies. Hand off to the 2026-05-31 MiMo writeup pipeline.
- Suggested follow-ups (cycle-57+):
  - The Windows pyreadline3 BACKLOG entry (filed at Step 17).
  - Vacuous-test repair candidate: AC1's `test_kb_detect_drift_none_changed_sources` was the ONLY vacuous test discovered in cycle 56's 5 folds. Other cycle-56 folds were behaviorally clean. But the cycle-52+ KNOWN-WEAK upgrade list (in BACKLOG) should be re-scanned with the C56-L4 pre-flight rule.
