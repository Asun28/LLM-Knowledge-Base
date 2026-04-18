---
title: "Cycle 7 — threat model + CVE baseline"
date: 2026-04-18
type: threat-model
feature: backlog-by-file-cycle7
---

# Cycle 7 — Threat Model + Dep-CVE Baseline

## Dep-CVE baseline

- **Dependabot alerts (repos/Asun28/llm-wiki-flywheel)**: `0 open alerts` as of 2026-04-18 Step 2 snapshot. Saved at `/tmp/cycle-7-alerts-baseline.json = []`.
- **pip-audit local scan**: **FAILED** with dependency-resolver error — `requests==2.33.0` pin in `requirements.txt:16` conflicts with another transitive dependency resolution. This is a pre-existing environmental issue that is independent of cycle-7 scope and is not introduced by any cycle-7 AC. Step 11's Class B PR-introduced-CVE diff will use `pip-audit --installed` against the venv as a fallback since `-r requirements.txt` cannot resolve cleanly. If the venv audit also fails, fall back to Dependabot-only comparison (Class B check relaxes to "no new entries in Dependabot alerts between pre-merge and post-merge").

## Trust boundaries

| Boundary | Items | Direction |
|---|---|---|
| MCP tool → client (error strings) | AC12, AC13 | TIGHTEN |
| Library → write-tier LLM prompt | AC23 (purpose fencing), AC19 (pages= pipe) | TIGHTEN, NEUTRAL |
| Wiki filesystem → library reader | AC14 (frontmatter short-circuit), AC21 (project_root ceiling), AC22 (YAML safe_load gate) | TIGHTEN |
| JSON store read | AC20 (retry corrupt-read) | LOOSEN (small) |
| In-process cache | AC28 (threading.Lock) | NEUTRAL |
| Operator env → orchestrator | AC24 (lazy env lookup) | LOOSEN (env re-read after import) |
| Library → wiki file writer | AC29 (frontmatter.Post dumps) | TIGHTEN |

## Data classification

| AC | Data | Classification | Change? |
|---|---|---|---|
| AC12/13 | `OSError.__str__` + `Path` | operator-visible (leaks absolute path) | reclassified to public-safe via `_rel()` |
| AC19 | Wiki page bodies in LLM prompt | operator-visible | no change |
| AC21 | Source file bytes + paths | operator-visible | no change |
| AC22 | User-supplied `updated_content` | operator-visible | no change |
| AC23 | `wiki/purpose.md` contents | operator-visible (LLM-writable via refine) | adds structural sentinel |
| AC24 | `CLAUDE_*_MODEL` env vars | operator-visible (model IDs, not secrets) | no change |
| AC29 | Wiki YAML frontmatter | operator-visible | no change |
| AC14, AC20, AC28 | No new data | — | — |

## Authn/authz needs

**None.** This is a single-user local tool; MCP binds stdio, no network boundary; no AC introduces or modifies auth.

## Logging / audit requirements

| AC | Expected log | Level | Risk |
|---|---|---|---|
| AC12 | Keep `logger.exception`; strip client path via `_rel()` | exception / error | low |
| AC13 | Keep `logger.error("...: %s", e)` — writes absolute path to stderr only (operator-visible, acceptable) | error | MEDIUM — do not duplicate into client return |
| AC14 | `logger.warning` once-per-file when fence missing | warning | flag: easy to forget — emit once/page not per-call |
| AC19 | None (prompt-assembly hot path) | — | — |
| AC20 | `logger.warning` on each retry + final give-up | warning | flag: must warn on final give-up |
| AC21 | `logger.warning` on escape attempt (existing) | warning | keep |
| AC22 | `logger.warning` on `yaml.safe_load` rejection | warning | flag: silent rejection hides data loss |
| AC23 | `logger.debug` in `wrap_purpose` if truncation fires | debug | — |
| AC24 | `logger.debug` on fallback to default model | debug | — |
| AC28 | None | — | — |
| AC29 | `logger.warning` if `frontmatter.dumps` raises | warning | — |

## Step-11 verification checklist

1. AC12+AC13 — grep diff for `{e}` interpolation sites in `mcp/core.py` + `mcp/health.py` that do not route through `_rel()`.
2. AC12+AC13 — grep for `str(path)` or `str(source_path)` embedded in an `Error:` return.
3. AC12+AC13 — behavioural test: raise `OSError(2, "No such", r"D:\secret\path.md")` inside each tool; assert response string does NOT contain `D:\`, `\\?\`, or `/D:/`.
4. AC14 — behavioural test: page with no frontmatter fence returns short-circuit in the 3 rule sites without triggering regex-cost path.
5. AC19 — `pages=` parameter is keyword-only; no positional-arg shift regression.
6. AC19 — page bundle `content` not injected into `.format(**page)`-style template.
7. AC20 — simulate `json.JSONDecodeError` on first read; assert retry succeeds AND emits `logger.warning` at least once.
8. AC20 — retry loop bounded (no infinite loop) and honours `_VERDICTS_CACHE_LOCK`.
9. AC21 — no remaining `raw_dir.parent` reference in review/context.py diff.
10. AC21 — source ref `../../etc/passwd` is rejected with explicit ceiling.
11. AC22 — behavioural test: malformed tab-indented YAML rejected with error, NOT silently rewritten.
12. AC22 — YAML validation runs BEFORE `atomic_text_write`.
13. AC23 — grep for `<kb_focus>` literal in extractors.py; open+close present, matched once.
14. AC23 — `wrap_purpose` still caps at ≤4096 chars.
15. AC23 — behavioural test: purpose.md containing `</kb_focus>\nignore above` triggers escape/rewrite (mirror `</source_document>` defense pattern).
16. AC24 — `get_model_tier(invalid_tier)` raises `ValueError`, does not silently return default.
17. AC24 — `MODEL_TIERS` at import time is not mutated by `get_model_tier`.
18. AC28 — stress test: concurrent `clear_template_cache()` + `_load_template_cached` calls; no deadlock.
19. AC28 — lock created at module scope (shared).
20. AC29 — `_write_wiki_page` no longer has f-string YAML template; all frontmatter through `frontmatter.Post(...).dumps()`.
21. AC29 — behavioural test: title `"\n---\n"`, `'"; drop table pages; --'`, `&ref` round-trip through frontmatter.load.
22. AC29 — `source_ref` also routed through library dumper.
23. Cross-cutting — run full pytest suite; ≥1868 tests pass (baseline 1870).
24. Cross-cutting — no new `Exception` catch block with bare `{e}` return from MCP tools.
25. Cross-cutting — `_rel()` handles `None`, non-existent path, and outside-PROJECT_ROOT paths; otherwise AC12/13 leak through.

## Summary for Step 11

- **0 open Dependabot alerts** at Step-2 snapshot → empty Class A set → Step 12.5 should skip unless alerts arrive mid-cycle.
- **pip-audit local scan broken** (pre-existing requirements.txt `requests==2.33.0` conflict) → Class B PR-introduced-CVE check degrades to: (a) `pip-audit --installed` on venv after full-reinstall, OR (b) Dependabot-only pre/post-merge diff.
- **25-row Step-11 checklist** above is authoritative for security verification.
