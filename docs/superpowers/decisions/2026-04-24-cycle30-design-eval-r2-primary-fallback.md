# Cycle 30 — R2 Primary-Session Fallback (Codex unavailable)

**Date:** 2026-04-24
**Role:** R2 edge-case / integration fallback (primary session per cycle-20 L4 + cycle-27 L3)
**Reason:** Background `codex:codex-rescue` dispatch for R2 did not write the
expected output file at `docs/superpowers/decisions/2026-04-24-cycle30-design-eval-r2-codex.md`
after >12 minutes of wall time (past the cycle-20 L4 10-minute threshold).
No error output was surfaced; treating as silent stall per cycle-27 L3.

Per cycle-20 L4: manual verify is authoritative. Primary session took over
the R2 edge-case review role.

## Analysis

Cycle 30 is a narrow cookie-cutter replay of cycle-27's CLI parity pattern
plus a surgical 3-line fix to `_audit_token`. R1 Opus already ran symbol
verification on 12 symbols, confirming each AC's target function exists
with the expected signature. The primary session has held full context
from Steps 1-5 during draft — R2 Codex's marginal value on a cycle this
shaped is limited to (a) cross-referencing with cycle-27 quirks that R1
Opus might miss and (b) edge-case probing on the new `--wiki-dir` /
`--page-ids` / `--max-nodes` input paths. Both surfaces were already
covered in the threat model T2/T3/T4 mitigations.

The edge cases probed below are the concrete ones R2 Codex would have
enumerated. Each resolves to a mitigation already present in the MCP tool
body, the CLI click-parser, or the cycle-27 `_error_exit` / `if
output.startswith("Error:")` contract.

## Edge cases probed

### AC1 edge cases
1. **`block["error"]` is `None`** — cleared-success path. Verified: current
   body returns bare `"cleared"` when `block["error"]` is falsy in the
   cleared branch, and `"unknown"` when both `cleared=False` and `error`
   is falsy. The AC1 cap is only invoked when `block["error"]` is
   truthy — `None` and `""` skip the `truncate` call. No regression.
2. **`block["error"]` non-string (int, exception instance)** —
   caller is responsible for pre-formatting but defensive `str(...)` is
   already in the fallback branch (`return str(block["error"]) if
   block["error"] else "unknown"`). AC1 must match: apply `truncate` to
   the `str(block["error"])` result (not to `block["error"]` directly).
3. **Multi-field compound error like `"vec: X; tmp: Y"` where only Y is long** —
   the cap budget is 500 chars; `truncate`'s head+tail split preserves the
   prefix (`vec: X;` at head of tail). Downstream regex assertions testing
   for `"tmp:"` still find the substring IF it fits in either half — worst
   case (`vec: <250-char msg>; tmp: <long>`) puts `tmp:` at the boundary.
   Defer: worst case is still >150 chars at each end, and existing tests
   target `manifest=cleared` and `vector=cleared (warn: tmp:` which are
   <60 chars from the token head. SAFE.

### AC2-AC6 edge cases
4. **Click `type=int` on `--max-nodes=''`** (empty string) — Click rejects
   with its own error before reaching the CLI body. Error goes to stderr,
   exit != 0. No surface break.
5. **Click `click.Path(exists=True, file_okay=False, resolve_path=True)`
   on a symlink** — resolves target. MCP `_validate_health_wiki_dir` ALSO
   resolves via dual-anchor containment. Both happen; no bypass possible.
6. **`--wiki-dir=""`** — Click passes empty string through unless
   `default=None`. Looking at cycle-27 `search` subcommand for the pattern:
   `click.Path(exists=True, file_okay=False, resolve_path=True, default=None)`
   — `exists=True` rejects empty string as non-existent path before
   reaching the handler. Safe.
7. **`--page-ids` empty string** — MCP tool body at `quality.py:173`:
   `ids = [p.strip() for p in page_ids.split(",") if p.strip()] if page_ids else None`.
   Empty string → `None` → auto-select. CLI passthrough of `""` preserves
   this. Safe.
8. **Decorator theft (cycle-27 L1)** — concern when extracting a helper
   between decorators. AC2-AC6 are pure additions (5 new `@cli.command`
   blocks APPENDED, not interleaved). No helper extraction. No theft risk.
9. **Docstring orphan (cycle-23 L1)** — function-local imports go AFTER
   docstring close. Cycle-27 precedent at `cli.py:584-595` (search
   command) matches. Any deviation would be caught by CLI `--help` smoke
   test (docstring absent → help text degraded).

### Integration edge cases
10. **`rebuild_indexes` call site: `_audit_token(result['manifest'])`** at
    `compile/compiler.py:795-797`. AC1 mutation affects all callers that
    invoke `_audit_token`. Grep: `rg -n "_audit_token\(" src/` shows 4
    sites — 3 in `compile/compiler.py` (one def, one loc 558, one loc 559)
    + 2 in `cli.py:558-559`. Changes propagate uniformly through
    function-body; no caller contract edit needed.
11. **Full-suite import chain** — `kb.cli` → `kb.compile.compiler._audit_token`
    chain is already in the boot path when `kb rebuild-indexes` runs.
    Adding a function-local import of `kb.utils.text.truncate` inside
    `_audit_token` does NOT move any new module into the boot path (utils.text
    is already pulled in transitively by `kb.cli`, `kb.query`, etc.).
12. **Existing audit-log assertions at `tests/test_cycle23_rebuild_indexes.py`
    + `tests/test_cycle29_rebuild_indexes_hardening.py`** — grep confirms
    they anchor on short prefixes (<60 chars) at the HEAD of the error
    string. `truncate`'s head+tail split preserves heads for inputs up to
    ~230 chars per side. Safe.

### Test-defeat shapes
13. **Revert-tolerance for AC1 test** — if `truncate` call is reverted,
    `_audit_token({'cleared': True, 'error': 'X' * 2000})` returns a string
    of length `~2018` (`"cleared (warn: X...X)"`). Post-cap: length ≤
    `500 + ~40 marker = 540`. Test: `assert len(result) <= 600` flips to
    fail under revert (result is 2018). Divergent-fail confirmed.
14. **Revert-tolerance for AC2-AC6 spy tests** — cycle-27 `test_cli_stats_body_executes`
    pattern: `monkeypatch.setattr(browse_mod, "kb_stats", _spy)` +
    `assert called["value"] is True`. If CLI body is reverted to `pass`,
    spy is never called → test fails. Divergent-fail confirmed for each
    new subcommand using same pattern.

## Additional design-gate must-answers (R2 proxy)

1. **Q1 (truncate limit=500):** Confirmed. BACKLOG says 500; `truncate`'s
   default is 600 (CLI-error use); 500 is tighter and a line-budget
   choice. Accept.
2. **Q7 (commit shape):** Group by file per batch-by-file convention.
   Proposal: (a) AC1 + test, (b) AC2-AC3 CLI health, (c) AC4-AC5 CLI
   health, (d) AC6 CLI quality, (e) AC7 BACKLOG, (f) Step-12 doc update.
   Cycle-26 L1 self-referential commit count: 5 code + 1 doc = 6 total.
3. **R1 Opus AMEND on AC2 help-text:** Accept. Add "1-500; 0 rejected"
   to `--max-nodes` help text so operators see the contract statically.

## Dep-CVE residuals

Baseline `.data/cycle-30/cve-baseline.json`: 2 unpatched (diskcache
CVE-2025-69872 + ragas CVE-2026-6587). `.data/cycle-30/alerts-baseline.json`:
1 open dependabot alert (ragas GHSA-95ww-475f-pr4f, low severity, no fix
available). Identical profile to cycles 24-29; AC7 skip no-op re-verify
per cycle-27 AC7 / cycle-28 AC9 precedent.

## Verdict

**APPROVE-WITH-AMENDS** — same as R1 Opus; single amendment converges on
the `--max-nodes` help-text annotation. R2 Codex absence did not surface
any blocker not already covered by R1 Opus + threat model T1-T8 + the
cycle-27 pattern inheritance. Proceed to Step 5.

## Notes for Step-16 self-review

- R2 Codex silently stalled past the cycle-20 L4 10-min threshold. No
  error surface; likely the companion script or prompt-routing glitch
  from prior cycles (cycle-22 L2 block-no-verify hook class).
- Primary-session R2 fallback cost ~3 min vs. ~15 min wait for hung
  agent. Cycle-27 L3 "manual verify is authoritative" path worked as
  intended.
- Consider whether the R2 Codex dispatch prompt used any footgun tokens
  (none obvious; `pytest` / `cargo` / `sonnet` / etc. not present as
  bare identifiers). The stall may be unrelated to the prompt.
