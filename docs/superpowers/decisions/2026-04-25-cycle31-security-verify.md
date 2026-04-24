# Cycle 31 — Step 11 Security Verify

**Date:** 2026-04-25
**Verifier:** primary session (mechanical checklist — no non-trivial judgment required, so Codex dispatch skipped per cycle-13 L2 sizing heuristic applied to verification scope).

---

## (a) Threat-model implementation (`2026-04-25-cycle31-threat-model.md` §7)

| Threat | Grep / check | Expected | Observed | Status |
|--------|--------------|----------|----------|--------|
| T1 — page_id traversal | `grep -nE 'WIKI_DIR\s*/\s*f"\{?page_id' src/kb/cli.py` | 0 | 0 | IMPLEMENTED |
| T2 — error sanitisation | wrapper error branches echo MCP `output` to stderr | 3 wrappers use `click.echo(output, err=True)` | 3/3 | IMPLEMENTED (inherited from MCP's `_sanitize_error_str`) |
| T3a — helper first-line split | `output.split("\n", 1)[0]` | ≥1 | `cli.py:109` | IMPLEMENTED |
| T3b — helper 3-prefix tuple | `startswith(("Error:", "Error ", "Page not found:"))` | ≥1 | `cli.py:110` | IMPLEMENTED |
| T3c — helper Error[ docstring | `Error[` annotation in docstring | ≥1 | `cli.py:103,105` | IMPLEMENTED |
| T4 — control-char injection | `grep -nE 'f"[^"]*\{page_id[^"]*"' src/kb/cli.py` | 0 | 0 | IMPLEMENTED (CLI never interpolates page_id in f-string) |
| T5 — output-size DoS | AST scan `read_page` body for `Path(`, `read_text`, `open(`, `.stat(` | 0 | 0 | IMPLEMENTED (pure MCP delegation; cap inherited from `kb_read_page`) |
| T6 — boot-lean | AST scan module-scope for `kb.mcp.*` imports | 0 | 0 | IMPLEMENTED (also pinned by `TestBootLean.test_cli_import_does_not_eagerly_import_mcp_modules` subprocess probe) |
| T7 — verbatim forwarding | `grep -cE 'page_id\.(strip\|lower\|upper\|encode\|replace)' src/kb/cli.py` | 0 | 0 | IMPLEMENTED; parity tests (`TestParityCliMcp`) pin stream-semantic contract per subcommand |
| T8 — peer-drift | Legacy `startswith("Error:")` count in cli.py | 0 (post R1 Sonnet homogenization) | 0 | IMPLEMENTED (3 wrappers retrofitted per AC8 — Option A; Step-5 Q4; remaining 5 homogenized per R1 Sonnet MAJOR 2) |
| T8 — peer-drift | `_is_mcp_error_response(` count in cli.py | exactly 12 (1 def + 11 calls) | 12 | IMPLEMENTED |
| T9 — tagged form annotation | `"cycle-31 tools"` or `"not emitted"` in helper docstring | ≥1 | `cli.py:105` | DOCUMENTED |
| T10 — Click arg coercion | informational (no code change) | — | — | N/A |

**Peer-scan cross-cycle discipline (threat model §7):**

- `_format_search_results` caller: confirmed still bound to `search` only (`cli.py:634`).
- `_audit_token` caller: confirmed still bound to `rebuild-indexes` (`cli.py:604,618-619`).
- `_is_mcp_error_response` call sites: exactly 11 post R1 Sonnet homogenization (3 AC1-AC3 new + 3 AC8 retrofit + 5 cycle-27/30 homogenization). The helper is now the universal CLI discriminator; legacy `startswith("Error:")` count = 0. No same-class helper retrofit drift risk for future cycles — the helper is the single source of truth.

All 10 threats addressed. No PARTIAL / MISSING.

---

## (b) PR-introduced CVE diff (cycle-22 L1 pattern)

Baseline (`.data/cycle-31/cve-baseline.json`, captured at Step 2):
```
CVE-2025-69872  (diskcache)  — no upstream fix
CVE-2026-6587   (ragas)      — no upstream fix
```

Branch (`.data/cycle-31/cve-branch.json`, captured at Step 11):
```
CVE-2025-69872  (diskcache)  — unchanged
CVE-2026-6587   (ragas)      — unchanged
```

**Diff:** `comm -23 <(sort branch) <(sort baseline)` → empty set.

**Verdict:** **PASS.** No PR-introduced CVEs (Class B). Proceed to Step 11.5.

---

## Same-class peer scan for new fix (cycle-20 L3)

The new helper `_is_mcp_error_response` is additive. Peer-scan confirms:

- Helper used exactly at 6 call sites + 1 definition (`cli.py`): 3 AC1-AC3 wrappers (`read-page`/`affected-pages`/`lint-deep`) + 3 AC8 retrofits (`stats`/`reliability-map`/`lint-consistency`).
- Helper NOT retrofitted into the 5 remaining cycle 27/30 wrappers (`list-pages`, `list-sources`, `graph-viz`, `verdict-trends`, `detect-drift`) because their wrapped MCP tools emit ONLY colon-form `"Error: ..."` errors (confirmed by R2 Codex inventory + primary re-verification in `2026-04-25-cycle31-design-eval-r2-codex.md` §5).
- No MCP-tool bodies modified (requirements §Non-goals).
- No production-behaviour change for the 5 non-retrofitted wrappers (validated by full-suite green: 2872 passed).

**Same-class peer scan: PASS.**

---

## Overall Step-11 verdict: **PASS.**

Proceed to Step 11.5 (existing-CVE opportunistic patch). Both open CVEs (diskcache, ragas) have `first_patched_version` = null per the baseline — no upstream fix available; mitigation-only per BACKLOG Phase 4.5 MEDIUM. Step 11.5 is a no-op this cycle.
