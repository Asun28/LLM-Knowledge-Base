# Cycle 30 — Design Decision (Step 5)

**Date:** 2026-04-24
**Role:** Step-5 design gate — resolves Q1-Q13 from brainstorm + R1 Opus amendment + R2 primary-session fallback.
**Inputs:** requirements (AC1-AC7), threat model (T1-T8 in-scope), brainstorm (Approach A), R1 APPROVE-WITH-AMENDS, R2 converging APPROVE-WITH-AMENDS.

---

## DECISIONS (Q1-Q13)

### Q1 — AC1 truncate limit value: **500**

**OPTIONS:** (A) `limit=500` per BACKLOG; (B) `limit=600` per `truncate` default.

**Analysis:** BACKLOG explicitly suggested 500; `truncate` default is 600 (calibrated for CLI error strings elsewhere). A 500-char budget yields a 40-char head + 40-char tail floor (`half = max(40, (500-40)//2) = 230`) — preserving the load-bearing `"vector=cleared (warn: tmp:"` prefix (27 chars) at the head with ~203 slack before the marker fires. Both R1 and R2 confirmed existing audit-grep assertions (`test_cycle23_rebuild_indexes.py:273`, `test_cycle29_rebuild_indexes_hardening.py:102/184/212`) anchor at short head substrings <60 chars — these survive both 500 and 600 cleanly.

The deciding factor is total log-line budget: in a worst-case compound clear where both manifest and vector trip the cap, 2×540 + ~70 static static = ~1150 chars per line. 600 would push this to ~1340. Since `append_wiki_log` does not re-truncate and `wiki/log.md` is human-audited, tighter is better. 500 also creates clearer divergence from the `truncate` default, signaling this is an opinionated audit-specific cap rather than an inherited default — future readers will see the explicit kwarg and know why.

**DECIDE:** `truncate(str(block["error"]), limit=500)`.
**RATIONALE:** Matches BACKLOG; bounds worst-case log-line at ~1150 chars; preserves head anchors with ample slack.
**CONFIDENCE:** HIGH.

### Q2 — `truncate` import in `_audit_token`: **function-local**

**OPTIONS:** (A) function-local inside `_audit_token`; (B) module-top in `compile/compiler.py`.

**Analysis:** `compile/compiler.py` already module-imports heavy helpers at top (not an MCP boot path). The cycle-23 AC4 boot-lean contract technically does not bind here. However, the project-wide pattern at `cli.py:592-595` + all cycle-27 wrappers use function-local imports inside the decorated command body, documented with `# noqa: PLC0415` and the comment "Function-local imports preserve cycle-23 AC4 boot-lean contract." Uniformity of pattern beats micro-optimization of import cost.

Additionally, `_audit_token` is a ~14-line private helper — scoping the import next to the single call site makes the dependency visually obvious to the next reader and makes the mutation one self-contained diff. No downside: `truncate` is a pure ~20-line function; repeated-call import cost is negligible in the audit path (called twice per `rebuild_indexes`, not in a hot loop).

**DECIDE:** Function-local `from kb.utils.text import truncate` inside `_audit_token`.
**RATIONALE:** Pattern uniformity with cycle-27 wrappers; self-contained diff; zero performance concern at call-site frequency.
**CONFIDENCE:** HIGH.

### Q3 — AC1 test coverage: **unit + e2e pair**

**OPTIONS:** (A) single unit test on `_audit_token`; (B) unit + e2e pair (unit on `_audit_token`, e2e through `rebuild_indexes` + monkeypatched `Path.unlink` → `wiki/log.md` inspection).

**Analysis:** Single-unit tests pin contract but drift from integration. The R2 fallback doc §T5 confirmed that existing cycle-23/29 audit-grep assertions sit at the HEAD of the token and survive truncation — but that's a prediction based on the static `half` arithmetic, not a behavioral assertion. An e2e test that exercises the full `rebuild_indexes` → `_audit_token` → `append_wiki_log` chain verifies the whole pipeline, including confirming the cap survives the sanitizer and the compound-line math (`manifest=... vector=... caches_cleared=...`) ends up bounded. This catches regressions where a future refactor moves the cap to the wrong layer.

Per `feedback_test_behavior_over_signature.md`, regression tests must exercise the production code path — not just signature-shape. A single unit test on `_audit_token` passes even if the truncate call is reverted, provided someone mocks the wrong spot. The e2e test via `rebuild_indexes` + monkeypatched `Path.unlink(side_effect=OSError("X"*2000))` + `wiki/log.md` read + length assert is revert-intolerant: reverting the truncate call produces a 2000-char log line, e2e fails. Both tests land in `test_cycle30_audit_token_cap.py` (per requirements §Blast radius).

**DECIDE:** Two tests: (1) unit on `_audit_token` with synthetic 2000-char error, (2) e2e through `rebuild_indexes` with monkeypatched unlink.
**RATIONALE:** Unit pins contract; e2e pins behavior; together they are revert-intolerant per feedback memory.
**CONFIDENCE:** HIGH.

### Q4 — `kb_lint_consistency` `page_ids`: **raw-string passthrough**

**OPTIONS:** (A) CLI splits on comma + passes `list[str]`; (B) CLI passes `--page-ids TEXT` raw string through.

**Analysis:** MCP tool at `quality.py:173-180` receives `page_ids: str = ""` and internally splits on `,`, strips, caps at 50 IDs, calls `_validate_page_id(pid, check_exists=True)` per ID. Splitting in CLI would mean reimplementing this logic, creating two split/validate sites with inevitable drift — the cycle-20 L3 class of bug. Raw-string passthrough preserves single-source-of-truth: MCP is the one place that parses `page_ids`.

Click accepts `--page-ids "a,b,c"` as a single string argument naturally. Empty-string default `""` preserves MCP's "no ids → auto-select" semantics (brainstorm §edge-case 7). The CLI wrapper stays a pure thin passthrough — no new input-validation surface in `cli.py`.

**DECIDE:** `--page-ids TEXT` defaults to `""`, forwarded raw to `kb_lint_consistency(page_ids=...)`.
**RATIONALE:** Single source of truth for split+validate; zero new CLI surface; matches cycle-27 thin-wrapper contract.
**CONFIDENCE:** HIGH.

### Q5 — AC1 branch coverage: **both branches**

**OPTIONS:** (A) cap only `cleared (warn: {error})` branch; (B) cap both the warn-suffix branch AND the fallback `str(block["error"])` branch.

**Analysis:** Reading `_audit_token` verbatim (R1 symbol verify table): the warn-suffix branch is `return f"cleared (warn: {block['error']})"` and the fallback is `return str(block["error"]) if block["error"] else "unknown"`. Both splice `block["error"]` verbatim. Capping only the warn branch leaves a silent 2KB-leak path through the fallback branch (which fires when `cleared=False` and an error was captured — e.g., lock-busy timeout with a compound error msg).

Path asymmetry is a future-regression trap. The BACKLOG item specifically targets "audit-log bloat" — scoped by condition, not by branch. Uniformly applying the cap to every path that emits `block["error"]` honors the spirit of the ticket.

**DECIDE:** Apply `truncate(..., limit=500)` to BOTH branches — the f-string interpolation AND the fallback `str(block["error"])` return path.
**RATIONALE:** Fallback branch is equally exposed; asymmetric caps create silent-regression vectors.
**CONFIDENCE:** HIGH.

### Q6 — Commit plan: **5 code + 1 doc = 6 total**

**OPTIONS:** (A) 5 code + 1 self-referential doc commit = 6 total; (B) compress to 4 total.

**Analysis:** Per cycle-26 L1 the self-referential doc-update commit counts itself in the tally. Cycle-28 AC8 + cycle-29 pattern all used the "N code + 1 doc = N+1" shape. Cycle 30 has 7 ACs, grouped by file per Q7 — compression below 5 would force unrelated ACs into single commits (e.g., AC1 compiler.py + AC6 cli.py in one commit), violating batch-by-file semantics.

Six commits keep each logical unit atomic: revertable in isolation, reviewable independently, with clean history that future cycles can cherry-pick learnings from. The marginal cost of 2 extra commits vs. 4 is zero.

**DECIDE:** 6 commits total: (1) AC1 + AC1-tests, (2) AC2+AC3 CLI health, (3) AC4+AC5 CLI health, (4) AC6 CLI quality + tests, (5) AC7 BACKLOG, (6) Step-12 doc update.
**RATIONALE:** Cycle-26 L1 convention; batch-by-file atomicity; revert-friendly history.
**CONFIDENCE:** HIGH.

### Q7 — Batch-by-file grouping: **grouped**

**OPTIONS:** (A) one commit per AC (7 total + doc = 8); (B) grouped per Q6 shape above.

**Analysis:** Per user `feedback_batch_by_file.md` memory: "Group backlog fixes by file (HIGH+MED+LOW together), not by severity." AC2-AC6 all touch `cli.py` as pure additions (5 new `@cli.command` blocks appended at EOF). Within `cli.py`, grouping by tool-category (browse vs. health vs. quality) is the next-finest granularity — AC2 (`graph-viz`) and AC3 (`verdict-trends`) are both `kb.mcp.health` forwards; AC4 (`detect-drift`) and AC5 (`reliability-map`) are the next pair (detect-drift is health, reliability-map is quality but zero-arg); AC6 (`lint-consistency`) has `--page-ids` arg and its own test class.

Tests follow the same batching: each CLI commit includes its own test class within `test_cycle30_cli_parity.py`. Per Q8, the test file is single with multiple classes, so "commit includes its test class" maps cleanly.

**DECIDE:** Group per Q6: AC1+tests, AC2+AC3+tests, AC4+AC5+tests, AC6+tests, AC7, docs.
**RATIONALE:** Batch-by-file user convention; same-file same-category atomicity; still atomic within each group.
**CONFIDENCE:** HIGH.

### Q8 — Test-file split: **one file, one class per subcommand**

**OPTIONS:** (A) one file `test_cycle30_cli_parity.py` with 5 classes; (B) one file per AC.

**Analysis:** Cycle-27 precedent at `tests/test_cycle27_cli_parity.py` landed all 4 new subcommands in a single file with one `TestXxx` class per subcommand. The class-per-command grouping gives each test-suite its own setup/fixture scope without fragmenting the cycle file list. AC1 (audit-token cap) is a different concern class (compiler, not CLI) — it earns its own file `test_cycle30_audit_token_cap.py` per requirements §Blast radius.

So the split is: (1) `test_cycle30_audit_token_cap.py` — AC1 unit + e2e tests (~2 tests); (2) `test_cycle30_cli_parity.py` — AC2-AC6 with one class per command, `--help` smoke + body-executing spy test per class (~2 per class × 5 = ~10 tests). Projected total: ~12 new tests, matching requirements estimate.

**DECIDE:** Two files: `test_cycle30_audit_token_cap.py` (AC1) + `test_cycle30_cli_parity.py` (AC2-AC6, one class per subcommand).
**RATIONALE:** Cycle-27 precedent; category separation between compiler and CLI concerns.
**CONFIDENCE:** HIGH.

### Q9 — AC2 `--max-nodes` help text: **document "1-500; 0 rejected"**

**OPTIONS:** (A) help text `"Max nodes in graph (default 30)."`; (B) help text `"Max nodes in graph (default 30; 1-500; 0 rejected)."`.

**Analysis:** R1 Opus's sole amendment. The MCP tool's range contract (rejects `0` with error string, clamps negatives to 1, caps at 500) is static but opaque at the CLI surface. Pure passthrough means operators see the behavior only by trying invalid inputs. Annotating the help text self-documents the contract — `kb graph-viz --help` tells the operator the valid range without requiring an experiment. This matches the cycle-27 pattern where `--limit` help text mentions `MAX_SEARCH_RESULTS`.

Downside: help text drift if MCP tool range changes. Mitigation: the MCP tool's range is part of its public contract (documented in `health.py:191-197`); any change would be a coordinated cycle, at which point CLI help text updates in lockstep.

**DECIDE:** Help text: `"Max nodes in graph (default 30; 1-500; 0 rejected)."`.
**RATIONALE:** R1 Opus amendment; self-documents contract; matches cycle-27 help-text precedent.
**CONFIDENCE:** HIGH.

### Q10 — Step 7 plan: **draft in primary session**

**OPTIONS:** (A) draft plan in primary session; (B) dispatch writing-plans subagent.

**Analysis:** Cycle-14 L1 heuristic: dispatch the planning subagent only when (a) AC count >8, (b) cross-file coordination is non-trivial, or (c) novel patterns require fresh-eyes synthesis. Cycle 30 has 7 ACs, 5 of which replay cycle-27 cookie-cutter, AC1 is a 3-line compiler fix, AC7 is pure BACKLOG text. Primary session holds full context from Steps 1-5 plus the grep-verified symbol table (R1 Opus produced it at Step 4). Dispatching a subagent would re-gather context that's already held.

Per the cycle-13 sizing heuristic, a primary-session plan on a cycle-27-pattern replay + one surgical compiler fix can be drafted in ~10 minutes with higher accuracy than a subagent re-gathering context. The plan will be a linear TaskList mirroring Q6's 6-commit structure.

**DECIDE:** Draft Step 7 plan in primary session. Use zero-padded task IDs per `feedback_taskcreate_zero_pad.md` (e.g., `Step 01 — AC1`, `Step 02 — AC2+AC3`).
**RATIONALE:** Cycle-14 L1 thresholds not met; primary session holds full context; re-gathering cost > drafting cost.
**CONFIDENCE:** HIGH.

### Q11 — R3 PR review: **SKIP**

**OPTIONS:** (A) trigger R3 adversarial review; (B) skip — Step 11 + standard Step 12 review sufficient.

**Analysis:** Cycle-17 L4 thresholds for R3 trigger: `≥25 ACs` OR `≥15 new-security-surface points` OR `≥10 design-gate-Qs`. Cycle 30: 7 ACs (below), 0 new security enforcement points (AC1-AC6 are passthrough + truncate; AC7 pure text), 11 design-gate questions (Q1-Q13, with Q10/Q11 being process questions not code questions — effective code-question count is 9). All three triggers are below threshold.

Per `feedback_3_round_pr_review.md`: "For batches >25 items, run 3 independent review rounds." Cycle 30 is 7. Standard Step 11 (verification checklist) + Step 12.5 CVE re-audit + Step 13 PR review is sufficient. Document the explicit decision here so Step 13 doesn't re-deliberate.

**DECIDE:** SKIP R3. Single PR review round at Step 13 per standard pipeline.
**RATIONALE:** All three cycle-17 L4 thresholds below trigger; cookie-cutter replay with grep-verified symbols.
**CONFIDENCE:** HIGH.

### Q12 — AC6 scoping: **confirmed — no `--wiki-dir`**

**OPTIONS:** (A) add `--wiki-dir` to `kb lint-consistency`; (B) omit per MCP contract.

**Analysis:** R1 Opus symbol verification table confirmed `kb.mcp.quality.kb_lint_consistency` signature is `(page_ids: str = "")` — NO `wiki_dir` parameter. Adding `--wiki-dir` to the CLI would create an option with no downstream plumbing, either silently dropping it (user confusion) or forcing a signature change to the MCP tool (out of scope per requirements §Non-goals). Cycle-27 `list-pages` / `list-sources` precedent (lines 648-695) already established the pattern of omitting `--wiki-dir` from CLI wrappers whose MCP tools don't accept it.

**DECIDE:** AC6 CLI wrapper omits `--wiki-dir`. Only `--page-ids TEXT` option.
**RATIONALE:** MCP tool contract; cycle-27 precedent; no silent-drop surface.
**CONFIDENCE:** HIGH.

### Q13 — Same-class MCP-tool peer scan

**OPTIONS:** (A) confirm scope-outs complete; (B) expand scope to include scanned peers.

**Analysis:** Cycle-11 L3 / cycle-20 L3 mandate: when shipping a batch in a class, scan same-class peers and document why each is scoped-out. Peers without CLI surface in the read-only-health/quality/browse class:

| Tool | Class | Status | Rationale |
|---|---|---|---|
| `kb_lint_deep` | quality | out-of-scope | Takes `page_id: str`; validation via `_validate_page_id` couples it to the deferred page-id-input cycle. |
| `kb_read_page` | browse | out-of-scope | Body-bearing (50+KB cap, UTF-8 decode fallback, ambiguous page_id); requirements §Non-goals defers it. |
| `kb_affected_pages` | quality | out-of-scope | Takes `page_id`; runs backlink computation (more logic than thin wrapper); requirements §Non-goals defers it. |
| `kb_capture`, `kb_save_source`, `kb_refine_page`, `kb_save_lint_verdict`, `kb_query_feedback` | write-path | out-of-scope | Requirements §Non-goals defers all write-path CLI wrappers pending write-path-specific cycle. |
| `kb_create_page`, `kb_refine_list_stale`, `kb_refine_sweep` | write/mutating | out-of-scope | Same write-path deferral. |

Per R1 probe result: `kb_lint_deep` IS a thin wrapper but its `_validate_page_id` coupling makes it belong with `kb_read_page` / `kb_affected_pages` in the page-id-input cycle. The "one-line rationale per peer" discipline flags the deferred cycle explicitly so the next planner starts from a well-defined scope.

**DECIDE:** Scope-outs confirmed complete. Rationale documented per peer in CONDITIONS below.
**RATIONALE:** Cycle-11 L3 / cycle-20 L3 peer-scan discipline; three defer buckets (page-id-input, body-bearing, write-path) cleanly separated.
**CONFIDENCE:** HIGH.

---

## VERDICT

**APPROVE-WITH-CONDITIONS** — ship AC1-AC7 with R1 amendment (Q9) folded in. All 13 questions resolved; no escalation; all confidences HIGH. R3 SKIP documented (Q11).

---

## DESIGN-AMEND — R2 Codex late-arrival findings (2026-04-24, post-initial decision)

R2 Codex subagent returned ~14 min after primary-session fallback had been written. Its output is at `docs/superpowers/decisions/2026-04-24-cycle30-design-eval-r2-codex.md`. Three substantive findings; two applied as design amendments below:

**R2-A1 (AC identity drift):** R2 mismatched AC3/AC4/AC6 names vs requirements. Cross-check: requirements.md lines 97/104/111/119/128 correctly specify `graph-viz` / `verdict-trends` / `detect-drift` / `reliability-map` / `lint-consistency`. R2's `evolve`/`stats`/`affected_pages` drift is an artifact of R2 misreading its own prompt, NOT a gap in the requirements. **DISMISS.**

**R2-A2 (AC1 truthiness branch):** R2 correctly flagged that `_audit_token` must branch on truthiness of `block["error"]` BEFORE calling `str(...)` and `truncate(...)` — otherwise `None` becomes the string `"None"` and breaks the clean `"cleared"` assertion in existing tests. **APPLY** as addendum to C1:
  - C1 (amended): The `truncate(str(block["error"]), limit=500)` call MUST be inside the truthiness-guarded branch. `_audit_token({'cleared': True, 'error': None})` returns bare `"cleared"` (no `"warn:"` suffix). `_audit_token({'cleared': False, 'error': None})` returns `"unknown"`. The cap is invoked ONLY when `block["error"]` is truthy.
  - Test addendum (C3): add `test_audit_token_clean_path_preserves_bare_cleared` pinning `_audit_token({'cleared': True, 'error': None}) == "cleared"` — flips to fail under AC1 revert that naively wraps `str(None)`.

**R2-A3 (AC7 arithmetic):** R2 correctly flagged that "14 remaining → 9 after cycle 30" is wrong. BACKLOG line 149 prose says "~14" but enumerates 16 items, including the non-tool `kb_save_synthesis` (which is the `save_as=` parameter on `kb_query`, not an MCP tool). Correct enumeration of MCP tools WITHOUT CLI surface after cycle 30:
  - **Write-path (7):** `kb_review_page`, `kb_refine_page`, `kb_query_feedback`, `kb_save_source`, `kb_save_lint_verdict`, `kb_create_page`, `kb_capture`
  - **Read-bearing / page_id-input (3):** `kb_read_page`, `kb_affected_pages`, `kb_lint_deep`
  - **Ingest/compile variants (2):** `kb_ingest_content`, `kb_compile_scan`
  - **Total remaining:** 12 (not 9)

  **APPLY:** AC7 narrow prose updates to "Remaining gap ≈ 12" with explicit enumeration. CONDITION C13 revised accordingly. `kb_save_synthesis` is NOT enumerated — acknowledged as non-tool in BACKLOG narrow text.

**R2-A4 (Spy-target verification):** R2 noted requirements.md line 99 incorrectly says the test "monkeypatches `kb_graph_viz` in `kb.cli`" — cycle-27 precedent is to patch the MCP source module (`kb.mcp.health`) because the CLI uses function-local imports that resolve-at-call-time. Requirements prose is slightly wrong but the PLAN at TASK 2 correctly patches `health_mod`. **DISMISS at requirements-prose level; the plan and CONDITIONS C11 are authoritative.** Plan wins over requirements prose on implementation detail (per cycle-22 L5 on CONDITION literalism).

**Verdict after amendments:** Still APPROVE-WITH-CONDITIONS. AC1 test suite gains 1 test (truthiness-branch pin). AC7 prose updated to "≈ 12" with enumeration. Commit count unchanged at 6. No Step-5 re-run needed — these are clarifications, not scope changes.

---

## CONDITIONS (Step 9 must satisfy)

**C1 — AC1 cap applied with `limit=500` to BOTH branches (Q1, Q5; R2-A2 amendment).**
(a) `_audit_token` body preserves truthiness-guarded branching: `truncate(str(block["error"]), limit=500)` MUST be inside `if block["error"]:` blocks only. `None` error on cleared path returns bare `"cleared"`; `None` error on non-cleared path returns `"unknown"`.
(b) Both truthy branches wrap: `f"cleared (warn: {truncate(str(block['error']), limit=500)})"` AND `truncate(str(block["error"]), limit=500) if block["error"] else "unknown"`.
(c) Grep enforcement: `grep -c "truncate(str(block" src/kb/compile/compiler.py` → ≥ 2.

**C2 — `truncate` imported function-local (Q2).**
(a) Import statement INSIDE `_audit_token` body, AFTER the docstring closes.
(b) Grep: `grep -n "from kb.utils.text import truncate" src/kb/compile/compiler.py` → exactly 1 hit, INSIDE `_audit_token`.

**C3 — AC1 has two tests: unit + e2e (Q3, Q8).**
(a) Unit test: `_audit_token({'cleared': True, 'error': 'X'*2000})` → `len(result) <= 540`, head contains original prefix.
(b) E2E test: `rebuild_indexes` with monkeypatched `Path.unlink(side_effect=OSError("X"*2000))`, read `wiki/log.md`, assert last line length ≤ 1200 chars AND contains `"...chars elided..."` marker.
(c) File: `tests/test_cycle30_audit_token_cap.py`.

**C4 — Existing audit-grep tests still pass (T5).**
(a) `tests/test_cycle23_rebuild_indexes.py::test_audit_log` AND `tests/test_cycle29_rebuild_indexes_hardening.py::*` unchanged, green post-AC1.
(b) Grep: `grep -rn "vector=cleared (warn: tmp:" tests/` → survives unchanged.

**C5 — AC2 help text (Q9).**
(a) Literal help string: `"Max nodes in graph (default 30; 1-500; 0 rejected)."`.
(b) Grep: `grep "1-500; 0 rejected" src/kb/cli.py` → exactly 1 hit.

**C6 — AC6 passes `page_ids` raw (Q4).**
(a) CLI body: `kb_lint_consistency(page_ids=page_ids)` — NO `.split(",")` in `cli.py`.
(b) Grep: `grep -n "page_ids.split" src/kb/cli.py` → zero hits.

**C7 — No `--wiki-dir` on AC6 (Q12).**
(a) `lint-consistency` Click group has NO `@click.option("--wiki-dir", ...)` decorator.
(b) AST scan: `grep -A2 "def lint_consistency" src/kb/cli.py` shows no `wiki_dir` parameter in signature.

**C8 — AC2-AC6 wrappers: function-local imports AFTER docstring (T7).**
(a) For each of 5 new commands, the `from kb.mcp.<mod> import <tool>` statement sits AFTER the triple-quoted docstring closes.
(b) Pattern check: `grep -B1 "from kb.mcp" src/kb/cli.py | grep '"""'` shows closing `"""` preceding each MCP import.

**C9 — No raw `Path(wiki_dir)` coercion in AC2-AC5 (T2).**
(a) All `--wiki-dir` values forwarded raw to MCP tool; no pre-`Path()` wrapping.
(b) Grep: `grep "Path(wiki_dir)" src/kb/cli.py` in new AC2-AC5 blocks → zero hits.

**C10 — `except Exception as exc: _error_exit(exc)` outer wrap on all 5 wrappers (T8).**
(a) Each new command ends with the cycle-27 wrap pattern.
(b) Grep: `grep -c "_error_exit(exc)" src/kb/cli.py` → cycle-27 baseline + 5.

**C11 — Test file naming + class-per-command (Q8).**
(a) File: `tests/test_cycle30_cli_parity.py` with 5 classes: `TestGraphVizCli`, `TestVerdictTrendsCli`, `TestDetectDriftCli`, `TestReliabilityMapCli`, `TestLintConsistencyCli`.
(b) Each class has BOTH a `--help` smoke test AND a body-executing spy test (cycle-27 L2).

**C12 — Commit plan follows Q6/Q7 shape (6 commits).**
(a) Order: (1) AC1+tests, (2) AC2+AC3+tests, (3) AC4+AC5+tests, (4) AC6+tests, (5) AC7 BACKLOG, (6) Step-12 docs.
(b) No `--no-verify`; no commit amending.

**C13 — AC7 BACKLOG edits confined (Q-N/A, requirements AC7; R2-A3 amendment applied).**
(a) Delete cycle-29 `_audit_token` MEDIUM entry; narrow "Remaining gap ~14" prose to "Remaining gap ~12" + enumerate the 12 by category (7 write-path, 3 read-bearing/page_id-input, 2 ingest/compile variants). Note `kb_save_synthesis` is not an MCP tool.
(b) `git diff BACKLOG.md` shows ONLY deletions + parity-narrow; zero unrelated edits.

**C14 — Step-11 verification per threat model checklist.**
(a) Full pytest + ruff check + ruff format + AST scan of `cli.py` for exactly 5 new `click.Command` objects.
(b) `python -c "from kb.compile.compiler import _audit_token; assert len(_audit_token({'cleared': True, 'error': 'X'*2000})) <= 600"` → passes.

**C15 — R3 SKIP decision documented (Q11).**
(a) Step 13 PR body includes one-line note: "R3 SKIP per cycle-30 design gate Q11 (7 ACs, 0 new security surface, 9 code Qs — below cycle-17 L4 thresholds)."

---

## FINAL DECIDED DESIGN

### AC1 — Audit error-string length cap (`compile/compiler.py::_audit_token`)

Inside `_audit_token`, add function-local `from kb.utils.text import truncate`. Both the `cleared (warn: ...)` branch AND the fallback `{error}` branch wrap `str(block["error"])` with `truncate(..., limit=500)`. Preserves head+tail diagnostic anchors via `kb.utils.text.truncate`'s cycle-3 M17 marker. Both `_audit_token` call sites inside `rebuild_indexes` (manifest + vector) inherit automatically via same function. CLI mirror in `rebuild_indexes_cmd` inherits via same helper.

Tests (`tests/test_cycle30_audit_token_cap.py`): (1) unit — 2000-char synthetic error through `_audit_token` bounds to ≤540 chars with marker present; (2) e2e — `rebuild_indexes` + monkeypatched `Path.unlink(side_effect=OSError("X"*2000))`, inspect `wiki/log.md` last line bounded.

### AC2 — `kb graph-viz` CLI subcommand

Thin wrapper over `kb_graph_viz`. Options: `--max-nodes INT default=30` with help text **"Max nodes in graph (default 30; 1-500; 0 rejected)."** (R1 amendment), `--wiki-dir PATH`. Function-local import of `kb_graph_viz` after docstring. Forward args raw. `if output.startswith("Error:"): sys.exit(1)`. `except Exception as exc: _error_exit(exc)` wrap.

### AC3 — `kb verdict-trends` CLI subcommand

Thin wrapper over `kb_verdict_trends(wiki_dir)`. Option: `--wiki-dir PATH`. Cycle-27 shape.

### AC4 — `kb detect-drift` CLI subcommand

Thin wrapper over `kb_detect_drift(wiki_dir)`. Option: `--wiki-dir PATH`. Cycle-27 shape.

### AC5 — `kb reliability-map` CLI subcommand

Thin wrapper over `kb_reliability_map()` (zero args). No options. "No feedback recorded yet" does NOT prefix `Error:` → exit 0 on that message.

### AC6 — `kb lint-consistency` CLI subcommand

Thin wrapper over `kb_lint_consistency(page_ids)`. Option: `--page-ids TEXT default=""`. NO `--wiki-dir` (MCP tool has no such param). Raw-string passthrough — MCP tool does split + validate + cap at 50.

### AC7 — BACKLOG hygiene

(a) Delete cycle-29 `_audit_token` error-string MEDIUM entry (closed by AC1). (b) Narrow Phase 4.5 MEDIUM "CLI ↔ MCP parity" prose from "~14" to "~9" + enumerate the 5 shipped. (c) Skip no-op CVE re-verify per cycle-27 AC7 / cycle-28 AC9 / cycle-29 AC9 precedent.

### Test files

- `tests/test_cycle30_audit_token_cap.py` — AC1 unit + e2e (~2 tests)
- `tests/test_cycle30_cli_parity.py` — one class per AC2-AC6 subcommand, each with `--help` smoke + body-spy test (~10 tests)

Projected: 2826 + ~12 = ~2838 tests.

---

## Scope-outs (same-class peer rationale per Q13)

- **`kb_lint_deep` (quality)** — takes `page_id: str` + validates via `_validate_page_id`; coupled to deferred page-id-input cycle alongside `kb_read_page` / `kb_affected_pages`. OUT.
- **`kb_read_page` (browse)** — body-bearing (50+KB cap, UTF-8 decode fallback, ambiguous page_id); requirements §Non-goals defers. OUT.
- **`kb_affected_pages` (quality)** — runs backlink computation, not a thin wrapper; requirements §Non-goals defers. OUT.
- **Write-path tools (`kb_capture`, `kb_save_source`, `kb_refine_page`, `kb_query_feedback`, `kb_save_lint_verdict`, `kb_create_page`, `kb_refine_list_stale`, `kb_refine_sweep`)** — requirements §Non-goals explicitly defers write-path CLI wrappers pending a write-path input-validation cycle. OUT.
- **Compile / ingest tools (`kb_compile`, `kb_compile_scan`, `kb_ingest`, `kb_ingest_content`)** — already have CLI surface (`kb compile`, `kb ingest`). N/A.
- **`kb_evolve`, `kb_lint`, `kb_stats` (health)** — already have CLI surface from prior cycles. N/A.

Remaining CLI-less MCP tools after cycle 30: 9 (down from 14) — the 3 deferred-page-id-centric + 6 write-path tools.
