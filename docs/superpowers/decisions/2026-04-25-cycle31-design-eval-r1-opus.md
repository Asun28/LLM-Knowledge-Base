# Cycle 31 — R1 Opus Design Review

**Date:** 2026-04-25
**Reviewer:** R1 Opus (design gate)
**Scope:** 3 ACs cover wrappers (AC1-AC3), AC4 helper, AC5/AC6 tests, AC7 docs. 10 open Qs.

---

## 1. Per-symbol verification table

| Symbol | File:line | Status |
|--------|-----------|--------|
| `kb_read_page(page_id: str) -> str` | `src/kb/mcp/browse.py:86` | EXISTS |
| `kb_affected_pages(page_id: str) -> str` | `src/kb/mcp/quality.py:265` | EXISTS |
| `kb_lint_deep(page_id: str) -> str` | `src/kb/mcp/quality.py:130` | EXISTS |
| `_validate_page_id(page_id, *, check_exists=True)` | `src/kb/mcp/app.py:250` | EXISTS |
| `_error_exit(exc, *, code=1)` | `src/kb/cli.py:60` | EXISTS |
| `_is_mcp_error_response` | `src/kb/cli.py` | NEW (to be added) |
| `_strip_control_chars` | `src/kb/mcp/quality.py:31` | EXISTS |
| `_CTRL_CHARS_RE` | `src/kb/mcp/app.py:188` | EXISTS |
| `ERROR_TAG_FORMAT` | `src/kb/mcp/app.py:17` | EXISTS |
| `error_tag()` | `src/kb/mcp/app.py:97` | EXISTS |
| `"Page not found:"` return | `src/kb/mcp/browse.py:125` | EXISTS |
| `"Error: Could not read page"` | `src/kb/mcp/browse.py:139` | EXISTS |
| `"Error checking fidelity for"` | `src/kb/mcp/quality.py:149,152` | EXISTS (both) |
| `"Error computing affected pages"` | `src/kb/mcp/quality.py:290` | EXISTS |
| Validator calls in targets | `browse.py:92`, `quality.py:140,279` | EXISTS (all 3) |
| Cycle 27/30 `startswith("Error:")` lines | `cli.py:640,669,690,724,751,779,799,827` | EXISTS — exactly 8 |
| `_format_search_results` caller | `cli.py:594` (search only) | EXISTS (bound) |
| `_audit_token` caller | `cli.py:544,558,559` (rebuild-indexes only) | EXISTS (bound) |
| CLI `@cli.command` count | `cli.py` (19 entries) | EXISTS — matches "19 commands" claim |

All symbols cited by requirements + threat model resolve to current source. No semantic mismatches detected.

---

## Analysis

Cycle 31's core proposition is a mechanical replay of the cycle-27/cycle-30 CLI-thin-wrapper pattern, with one genuine novelty: the three target MCP tools emit **heterogeneous** error-prefix shapes, which breaks the `output.startswith("Error:")` discriminator that shipped cycle 27 and cycle 30 relied on. Grep confirms the threat model's claim is precise — `src/kb/mcp/browse.py:125` returns `"Page not found: ..."` (no "Error" prefix at all), `src/kb/mcp/quality.py:149,152,290` all emit `"Error <verb> ..."` (no colon after "Error"), and `src/kb/mcp/browse.py:139` emits `"Error: Could not read page ..."` (colon form). A naive `startswith("Error:")` wrapper would exit 0 on the first two shapes, silently printing error text to stdout — a real regression for shell pipelines. The proposed `_is_mcp_error_response` helper is therefore not over-engineering; it is the minimum-correct boundary because the three target tools' output surface is genuinely irregular. The brainstorm's Approach A (additive helper, cycle 27/30 wrappers untouched) is the right shape — Approach B (copy-paste inline) violates DRY across three new sites, and Approach C (retrofit existing 9 wrappers) fails T8 by construction.

The threat-model's T3 verification is the single most important gate: the helper must classify by **first-line prefix only** (`split("\n", 1)[0]`), and must not use substring `in` checks. Without first-line anchoring, a legitimate page body whose second line contains `Error:` mid-sentence would misfire. The helper's docstring must enumerate exactly three shapes — `"Error:"`, `"Error "`, `"Page not found:"` — and must document (per T9) that the tagged `"Error[category]: ..."` form from `src/kb/mcp/app.py:17` is NOT matched because none of the three target tools emit it. Every AC cites the correct precedent lines (cycle 27/30 wrappers at `cli.py:622-832`, `_error_exit` at `cli.py:60`, boot-lean short-circuit at `cli.py:15-19`), and the T8 peer-drift verification is achievable: my grep returned exactly 8 matches for `output.startswith("Error:")` at the expected line numbers `640, 669, 690, 724, 751, 779, 799, 827`. This is an APPROVE with one minor amendment around test coverage of the byte-identity parity claim.

---

## 2. Per-AC scoring

### AC1 — `kb read-page <page_id>` subcommand — APPROVE
- Target `kb_read_page` EXISTS at `src/kb/mcp/browse.py:86` with correct `(page_id: str) -> str` signature.
- Validator-at-MCP-boundary pattern verified: `browse.py:92` calls `_validate_page_id(page_id, check_exists=False)`, then the tool does its own existence fallback (`browse.py:124-125`).
- Function-local-import pattern matches cycle 27/30 precedent (see `cli.py:636, 665, 686, 720, 747, 775, 795, 823`).
- Body-spy + kwarg-forward requirement is consistent with AC5 enforcement.
- **Must contain:** `@cli.command("read-page")`, `@click.argument("page_id")`, function-local `from kb.mcp.browse import kb_read_page  # noqa: PLC0415`, single call `output = kb_read_page(page_id)`, branch on `_is_mcp_error_response(output)`, `click.echo(output, err=True); sys.exit(1)` on error, `click.echo(output)` on success, outer `try/except Exception → _error_exit(exc)`.

### AC2 — `kb affected-pages <page_id>` subcommand — APPROVE
- `kb_affected_pages` EXISTS at `src/kb/mcp/quality.py:265`, calls `_validate_page_id(page_id, check_exists=True)` at `quality.py:279`, returns `"Error computing affected pages: ..."` at `quality.py:290`.
- Empty-state `"No pages are affected by changes to X"` is NOT an error — correctly documented as exit 0. Matches cycle-30 `reliability-map` empty-state precedent at `cli.py:787-804`.
- **Must contain:** thin-wrapper shape per AC1, importing `kb.mcp.quality.kb_affected_pages` function-local.

### AC3 — `kb lint-deep <page_id>` subcommand — APPROVE
- `kb_lint_deep` EXISTS at `src/kb/mcp/quality.py:130`, validator at `quality.py:140`, runtime errors at `quality.py:149,152`.
- `_strip_control_chars` runs inside the MCP tool at `quality.py:139` — CLI wrapper must NOT duplicate.
- **Must contain:** thin-wrapper shape; function-local import of `kb.mcp.quality.kb_lint_deep`; zero-option signature (per Q8).

### AC4 — Shared `_is_mcp_error_response` helper — APPROVE-WITH-AMENDS
- Design correctly anchors on three prefix shapes AND first-line-only matching.
- **Amendment 1:** the sample code in AC4 does NOT include `output.split("\n", 1)[0]` — it applies `startswith` to the full `output` string. This contradicts T3's mandatory first-line-anchoring invariant. The brainstorm's Approach A code block at lines 55-56 has it correct (`first_line = output.split("\n", 1)[0]`); the requirements doc at lines 68-85 omits the split. **Step-5 MUST reconcile — implementer MUST use the brainstorm's version.**
- **Amendment 2:** helper docstring MUST cite file:line for each prefix shape (per T3 "Docstring MUST enumerate the three prefix shapes with file:line citations") and MUST include the T9 `"Error["` annotation (`# NOT matched; tagged form not emitted by cycle-31 tools`).
- **Positive requirements:** helper MUST be placed near `_error_exit` at `cli.py:~60-70` (per Q5); MUST use `startswith` not substring `in` checks; MUST hardcode the 3-tuple (per Q1); MUST return `bool`.

### AC5 — Body-execution tests per subcommand — APPROVE
- Matches cycle-27 L2 skill patch (body-spy instead of `--help`-only smoke tests).
- `monkeypatch.setattr(kb.cli, "kb_<tool>", spy)` + `assert spy_called["kwargs"] == {"page_id": "<arg>"}` is the correct shape; the function-local import means the patch target is the module where the import happens (inside `kb.cli`'s function scope, rebinding via monkeypatch works because the import re-resolves on each invocation).
- Cycle-30 L3 parallel-assertion discipline applies: all three subcommand body-spy tests MUST use identical assertion shape.

### AC6 — Integration-boundary tests per subcommand — APPROVE
- Path-traversal `..` input → exit 1, stderr `"Error: ..."` validator message — this pins the MCP-tool `_validate_page_id` contract (cycle-30 L2 precedent).
- Note: for `kb_read_page` specifically, `_validate_page_id` runs with `check_exists=False` (`browse.py:92`), so the validator still rejects `..` via the path-containment check at `mcp/app.py` (NOT via existence). Verification must not assume the validator path is identical across the three tools.

### AC7 — BACKLOG cleanup — APPROVE
- Line 146 currently reads "Remaining gap ≈ 12" and explicitly lists cluster (b) as `kb_read_page`/`kb_affected_pages`/`kb_lint_deep` — cycle 31 must remove (b) and reduce count to ≈ 9. Verified by reading `BACKLOG.md:146`.
- CLAUDE.md test-count bump (2850 → post-cycle) should use `pytest --collect-only | tail -1` AFTER R1/R2 fix commits (cycle-15 L4).
- CLI-count bump from 19 → 22 matches the current 19 `@cli.command` entries plus 3 new.

---

## 3. Per-Q scoring

- **Q1 — Hardcoded vs parameterised prefix set — CONFIRM.** Hardcoded tuple inside helper. Callers must not tweak prefix set; any widening is a deliberate cycle-level decision.
- **Q2 — kebab-case `read-page` / `affected-pages` / `lint-deep` — CONFIRM.** Matches cycle 27/30 hyphenation (`list-pages`, `list-sources`, `graph-viz`, `verdict-trends`, `detect-drift`, `reliability-map`, `lint-consistency`).
- **Q3 — `click.echo(output, err=True); sys.exit(1)` — CONFIRM.** Matches existing precedent at `cli.py:641-642, 670-671, 691-692, 725-726, 752-753, 780-781, 800-801, 828-829`. MCP output already sanitized via `_sanitize_error_str`.
- **Q4 — CLI forwards raw, no pre-validation — CONFIRM.** T7 requires verbatim forwarding; defence-in-depth would be divergence.
- **Q5 — Helper placement near `_error_exit` at ~cli.py:72 — CONFIRM.** Clusters with existing error helpers (`_truncate`, `_is_debug_mode`, `_error_exit`, `_setup_logging`).
- **Q6 — Test file name `test_cycle31_cli_parity.py` — CONFIRM.** Matches `test_cycle27_cli_parity.py` / `test_cycle30_cli_parity.py` naming.
- **Q7 — Full test matrix (help + body-spy + integration-boundary + parity) — AMEND.** Recommendation is 12 wrapper tests + 6 helper tests = 18 minimum. I recommend explicitly requiring a **CLI/MCP byte-identity parity** test per T7 — which is listed but must be a *named* test in the spec, not "one-of" the matrix items. **Step-5 must make the parity test mandatory, not optional.** Absent parity tests were a cycle-17 gap noted in prior retros.
- **Q8 — Zero options beyond positional page_id — CONFIRM.** MCP tools take only `page_id`; adding CLI flags would diverge.
- **Q9 — Don't re-verify diskcache/ragas CVEs — CONFIRM.** Cycle-25 AC9 + cycle-30 baseline cover it. Scope creep avoided.
- **Q10 — Defer `--format=json` structured output — CONFIRM.** Cross-surface concern; separate cycle.

---

## 4. T8 peer-drift specific verification

**Grep:** `output.startswith("Error:")` in `src/kb/cli.py` — **exact count: 8**. Line numbers: **640, 669, 690, 724, 751, 779, 799, 827**. Matches threat-model claim verbatim.

Mapping to cycle/command:
- `640` — `stats` (cycle 27 AC2)
- `669` — `list-pages` (cycle 27 AC3)
- `690` — `list-sources` (cycle 27 AC4)
- `724` — `graph-viz` (cycle 30 AC2)
- `751` — `verdict-trends` (cycle 30 AC3)
- `779` — `detect-drift` (cycle 30 AC4)
- `799` — `reliability-map` (cycle 30 AC5)
- `827` — `lint-consistency` (cycle 30 AC6)

The cycle 27 AC1 `search` command at `cli.py:568-621` does NOT use `startswith("Error:")` because it returns structured search results (not a string error); this is NOT a peer-drift concern.

T8 is achievable. Step-11 security-verify must re-run this grep post-implementation and confirm count is still exactly 8 at the same line numbers (offsets may shift if the new wrappers are added above existing wrappers — spec implies append-at-tail placement, preserving offsets).

---

## 5. Same-class MCP tool enumeration

All MCP tools accepting `page_id: str` as first argument (source: `Grep "^def kb_" src/kb/mcp`):

| Tool | File:line | Cycle-31 status |
|------|-----------|-----------------|
| `kb_review_page(page_id)` | `quality.py:37` | (a) deferred — write-path |
| `kb_refine_page(page_id, updated_content, revision_notes)` | `quality.py:63` | (a) deferred — write-path |
| `kb_lint_deep(page_id)` | `quality.py:130` | **IN SCOPE** — AC3 |
| `kb_affected_pages(page_id)` | `quality.py:265` | **IN SCOPE** — AC2 |
| `kb_save_lint_verdict(page_id, ...)` | `quality.py:346` | (a) deferred — write-path |
| `kb_create_page(page_id, ...)` | `quality.py:408` | (a) deferred — write-path |
| `kb_read_page(page_id)` | `browse.py:86` | **IN SCOPE** — AC1 |

Other peers that DO NOT take `page_id` as first arg but share the validator-at-MCP-boundary discipline (out of cycle 31 scope; must not be touched):
- `kb_lint_consistency(page_ids: str)` — cycle 30 AC6 already wrapped; plural input.
- `kb_query_feedback(question, rating, cited_pages, notes)` — cluster (a) write-path.
- `kb_ingest(source_path, ...)`, `kb_ingest_content(...)`, `kb_save_source(...)`, `kb_compile_scan`, `kb_compile`, `kb_capture` — cluster (c) deferred.

**Cycle-31 MUST NOT:** accidentally retrofit `_is_mcp_error_response` into the 4 deferred write-path page_id tools (`kb_review_page`, `kb_refine_page`, `kb_save_lint_verdict`, `kb_create_page`). The helper is additive to 3 new wrappers only. Step-11 grep should count call sites: `_is_mcp_error_response` used in exactly 4 places (1 definition + 3 calls).

No same-class tools are silently touched by cycle-31 scope. Deferred write-path tools have different validation contracts (notes-length cap, verdict-type enum, ingest content-hash dedup) that justify their deferral.

---

## 6. Final overall VERDICT: APPROVE-WITH-AMENDS

Design is sound, precedent-aligned, and minimum-scope. Two amendments required for Step-5 decision gate.

---

## 7. Amendments for Step-5 decision gate

1. **AC4 sample code bug (BLOCKING).** Requirements doc `2026-04-25-cycle31-requirements.md` lines 68-85 show a helper body `return output.startswith((...))` that omits `output.split("\n", 1)[0]`. This contradicts T3 "first line only" invariant and the brainstorm's correct Approach A at lines 55-56. **Step 5 must reconcile to the brainstorm version; implementer ref: first line extraction via `output.split("\n", 1)[0]` before the tuple `startswith`.** File: `src/kb/cli.py` (new helper, ~line 72).

2. **Q7 byte-identity parity test mandate (non-blocking but strong recommendation).** The spec mentions a CLI/MCP byte-identity parity test but does not elevate it to required. Given T7's severity and the cycle-17 gap lesson, make the parity test **explicitly required per subcommand** (3 tests), not "one-of" the matrix. Test file: `tests/test_cycle31_cli_parity.py`. Shape: invoke `CliRunner().invoke(cli, ["<subcmd>", "<pid>"])` AND call `kb_<tool>("<pid>")` directly; assert `result.stdout == mcp_output + "\n"` on success and `result.stderr == mcp_output + "\n"` + `result.exit_code == 1` on error.

3. **Docstring T9 annotation requirement (minor).** The helper docstring MUST include the literal string `Error[` and a note like `# NOT matched — tagged form not emitted by cycle-31 tools; T9 future refactor`. The threat-model verification greps for this annotation at `_is_mcp_error_response.__doc__`.

No REJECT triggers. Cycle is shippable after amendments 1 and 2 are resolved at Step-5 decision.
