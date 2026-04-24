# Cycle 29 Threat Model (Backlog-by-file, 2026-04-24)

Scope: AC1+AC2 `rebuild_indexes` (compile/compiler.py); AC3 `config.py` doc; AC4+AC5 BACKLOG.md hygiene.

## Analysis

Only AC1 and AC2 touch executable code; both live inside the same destructive helper (`rebuild_indexes`). The helper already resolves to filesystem `unlink()` calls gated by dual-anchor `PROJECT_ROOT` containment on `wiki_dir`. The two live threats concern (a) post-unlink AUDIT rendering — the operator's sole durable signal about partial resets; and (b) the two keyword-only override parameters (`hash_manifest`, `vector_db`) that currently bypass the containment gate. The CLI does not yet plumb the overrides, but the Python-API surface is a real boundary: any future plugin or sub-command that accepts user input and forwards it would turn the gap into an arbitrary-file-unlink primitive scoped to the process user.

AC3/AC4/AC5 are inert: a config comment, one stale BACKLOG bullet, one stale HIGH bullet. No runtime behavior changes, no new network calls, no new logging sinks. They cannot create threats; they eliminate operator-confusion-at-audit risk.

No AC touches authentication, authorization, network egress, or LLM-prompt surfaces. No new dependencies. No change to serialization format, on-disk schema, or public function signatures (AC1 alters audit log STRING content only; AC2 adds validation but preserves return shape).

### Trust boundaries

- **AC1** — process → filesystem (`wiki/log.md`) → operator reading the audit line. The boundary is an informational one-way flow; the risk is misinformation (a cleared=True audit hides a surviving `.tmp` sibling), not code execution.
- **AC2** — Python-API caller → `rebuild_indexes` → filesystem (`unlink()`). The trust boundary is the function's public signature: `hash_manifest` and `vector_db` are keyword-only override paths. Today only tests pass them; any future caller plumbing user-controlled input would cross a privilege boundary into filesystem-write scope.
- **AC3/AC4/AC5** — none (documentation only).

### Data classification

- AC1 — `wiki/log.md` audit-line string (INTERNAL; operator-readable; no secrets). `result["vector"]["error"]` substrings may contain filesystem paths (local, non-sensitive; already written by existing cycle-25 code path).
- AC2 — `hash_manifest` / `vector_db` `Path` objects (UNTRUSTED if ever plumbed from user input). Target files: `.data/hashes.json`, `.data/*.db` / `.tmp`.
- AC3 — `src/kb/config.py` source comment (PUBLIC).
- AC4/AC5 — `BACKLOG.md` text (PUBLIC).

### Authn/authz

N/A. No AC in this cycle touches authentication, authorization, capability checking, role boundaries, or token handling. The `PROJECT_ROOT` dual-anchor check in AC2 is a containment guard, not an authz check.

### Logging / audit requirements

**AC1 is the audit-logging fix.** Invariant: `wiki/log.md`'s `vector=` field MUST NEVER render the word `cleared` alone when `result["vector"]["error"]` is truthy. Required rendering: `cleared (warn: tmp: <msg>)` or equivalent compound token when cleared=True AND error truthy, mirrored symmetrically for `manifest=`. Cycle-25 CONDITION 1 established that a `.tmp` cleanup failure must not blank `cleared=True` in the returned `result` dict — AC1 extends the same invariant to the PERSISTED audit rendering so operators see the partial-state signal.

### Threat list

**T1 — Audit log silently omits tmp-unlink failure (AC1)**

Description: Under the current renderer at `compile/compiler.py:752-756`, `vector=` emits `cleared` whenever `result["vector"]["cleared"]` is True, discarding `result["vector"]["error"]` even when `.tmp` cleanup failed. An operator tailing `wiki/log.md` after `kb rebuild-indexes` believes the reset was total; a stale `<vec_db>.tmp` remains on disk and may be reused by the next rebuild's AC6 entry-cleanup but survives any intervening diagnostic.

Mitigation in this cycle: render `vector=cleared (warn: tmp: <msg>)` when cleared=True AND error truthy; apply the same pattern to `manifest=` for symmetry (even though manifest currently has no tmp-sibling, symmetry future-proofs the renderer against a future manifest-tmp scheme).

Cross-link: AC1.

Step 11 checklist item: YES — grep `wiki/log.md` output in a tmp-unlink-failure test harness to confirm the warn substring appears.

**T2 — Override paths bypass `PROJECT_ROOT` containment (AC2)**

Description: `rebuild_indexes(hash_manifest=..., vector_db=...)` accepts absolute `Path` overrides and passes them directly to `unlink()` without the dual-anchor containment check applied to `wiki_dir` (lines 638-656). A future plugin, MCP tool, or CLI flag that threads user input into these kwargs becomes an arbitrary-file-unlink primitive scoped to the process user. Symlink-escape is also unguarded: a caller-supplied path whose literal form looks clean but whose `.resolve()` target lies outside `PROJECT_ROOT` would pass any single-anchor check.

Mitigation in this cycle: apply the identical dual-anchor check (literal absolute path under `PROJECT_ROOT` AND `.resolve()` target under `PROJECT_ROOT`) to each override when absolute; `None` (default) and relative paths skip validation per the existing `wiki_dir` policy. Raise `ValidationError` on failure. Validation fires BEFORE `file_lock` acquisition and BEFORE `unlink()`.

Cross-link: AC2.

Step 11 checklist item: YES — grep for callers of `rebuild_indexes(hash_manifest=` / `vector_db=` to confirm no existing test or production caller passes an out-of-root path; add a negative test proving `ValidationError` fires on `/tmp/evil.json` override.

**T3 — Documentation-only ACs (AC3/AC4/AC5)**

Description: None. Pure text changes to `config.py` comment, two BACKLOG bullets. No code path, no data flow, no new trust boundary.

Mitigation in this cycle: N/A.

Step 11 checklist item: NO.

---

Dep-CVE baseline (2026-04-24): **pip-audit** — 2 advisories on installed venv: `diskcache CVE-2025-69872` (no upstream fix), `ragas CVE-2026-6587` (no upstream fix). Both pre-existing, tracked in BACKLOG §Phase 4.5 MEDIUM. **Dependabot open alerts** — 1 alert: `ragas GHSA-95ww-475f-pr4f` sev=low, first_patched=null. Baseline at `.data/cycle-29/cve-baseline.json` + `.data/cycle-29/alerts-baseline.json`. Step-11 PR-introduced-CVE diff will compare against these.
