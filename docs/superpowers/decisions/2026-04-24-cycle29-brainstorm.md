# Cycle 29 — Brainstorm (structured approach generator)

**Date:** 2026-04-24
**Mode:** Non-interactive (auto-approve per `feedback_auto_approve`). Step 4 parallel eval + Step 5 Opus decision gate will resolve.

Open design questions for AC1 + AC2 (AC3/AC4/AC5 are trivial 1-line edits with no branching decisions).

---

## Q1 (AC1) — Audit token when `cleared=True AND error` truthy

Options:

- **A. `cleared (warn: <error>)`** — compound token, single log line. Human-readable prose. Existing log format is "prose after `=`"; this stays prose-compatible. Grep for `cleared (warn:` pins the compound case.
- **B. `cleared;error=<error>`** — structured-ish, semicolon separator. More machine-parseable but mixes prose with pseudo-k=v.
- **C. Two log entries** — one "rebuild-indexes" success + one "rebuild-indexes-warn" tmp-leftover. Separates success from warn. Breaks `append_wiki_log("rebuild-indexes", msg, ...)` single-call contract. High blast radius.
- **D. JSON sidecar** — emit structured record to `wiki/log.md` alongside prose. Overkill; no other log line uses JSON sidecar.

**Recommendation:** A. Minimal change, readable, greppable. Matches existing prose-after-`=` convention used elsewhere in `wiki/log.md`.

---

## Q2 (AC1) — Symmetric rendering for `manifest=`

Options:

- **A. Mirror the rule to manifest** — `manifest=cleared (warn: <error>)` if ever `cleared=True AND error`. Symmetric; future-proofs against a cycle that adds manifest-tmp cleanup. Dead code today (lines 672-680 set `cleared=True` only inside the success branch; `error` is set only on exceptions where `cleared=False`).
- **B. Leave manifest rendering unchanged** — tighter diff, strict YAGNI. Accept asymmetry.

**Recommendation:** A. The code cost is ~3 lines (shared helper or repeated ternary), the clarity cost is low, and the symmetry preserves reviewer-mental-model for a future maintainer extending `rebuild_indexes` to add manifest-tmp cleanup. Cycle-16 L1 same-class-peer rule favours symmetric treatment.

---

## Q3 (AC2) — Validation helper factoring

Options:

- **A. Inline validation for each override** — copy-paste the existing `wiki_dir` dual-anchor block twice more (once for `hash_manifest`, once for `vector_db`). 18 lines × 3 = 54 lines of near-duplicate.
- **B. Extract `_validate_path_under_project_root(path, field_name) -> Path`** — shared helper returning the resolved path (or raising `ValidationError`). Callable 3× (wiki_dir, hash_manifest, vector_db). ~12 lines of helper + 3 × 2 lines of call = ~18 lines total. Single point of truth for the dual-anchor contract.
- **C. Keep `wiki_dir` inline; factor only for the overrides** — hybrid. Half-done.

**Recommendation:** B. Extraction reduces cycle-24 L1 `Edit(replace_all=true)` risk (one pattern to maintain, not three). Pre-existing `wiki_dir` block becomes the first caller of the new helper; no behavior change for `wiki_dir`. Helper name: `_validate_path_under_project_root` — imperative, matches project's `kb.utils.io` style.

---

## Q4 (AC2) — `ValidationError` message form

Options:

- **A. Match existing** — `"hash_manifest must be inside project root"` / `"vector_db must be inside project root"`. Consistent with `"wiki_dir must be inside project root"` on line 650 + 656.
- **B. Include the offending path** — `"hash_manifest must be inside project root: <path>"`. More debuggable. But then the `__str__` of `StorageError` (cycle-20) redacts paths; `ValidationError` does not. The path IS caller-controlled, so echoing it back is information the caller already has. Minor privacy surface if logged, but the `wiki/log.md` audit line does not echo `ValidationError` messages (the helper raises BEFORE any audit write).

**Recommendation:** A. Strict consistency with existing `wiki_dir` error message. The caller's traceback already shows the offending Path object via Python's default exception rendering — extra echo in the message is redundant.

---

## Q5 (AC2) — Relative override handling

Options:

- **A. Mirror existing `wiki_dir` policy** — skip the pre-check (literal-absolute anchor) for relative inputs; still apply the resolve() anchor. Rationale: `resolve()` absolutifies against CWD which may legitimately differ from PROJECT_ROOT in dev.
- **B. Reject all relative overrides** — stricter; prevents CWD-dependent behavior. But breaks the existing `wiki_dir` contract if applied uniformly.
- **C. Resolve against PROJECT_ROOT (not CWD) for overrides** — treat relative overrides as `PROJECT_ROOT / path`. Changes semantic; no caller uses relative overrides today so feasible.

**Recommendation:** A. Mirror existing `wiki_dir` policy for consistency; the helper MUST behave identically to today's wiki_dir block to preserve backward compatibility for relative-path test fixtures.

---

## Q6 (AC1) — Shared rendering helper?

Options:

- **A. Inline ternary** in the message construction (lines 752-756). Two ternaries (manifest + vector). Small diff.
- **B. Local helper** `_audit_token(block: dict) -> str` — takes `{"cleared": bool, "error": str | None}` returns `"cleared"` or `"cleared (warn: ...)"` or `"<error>"`. One caller per block. ~6 lines.

**Recommendation:** B. DRY for the compound-token rule; single test surface. Pure function, easy to unit-test in isolation IF we want — but primary testing is integration through `rebuild_indexes` end-to-end.

---

## Q7 (AC2 test) — Symlink-escape test portability

Options:

- **A. `os.symlink` with Windows fallback** — on Windows, requires admin-mode or "developer mode" for non-admin symlinks. Pytest `skip` if `OSError` during symlink create. Most cycle-23 tests take this approach.
- **B. `os.link` (hardlink)** — hardlinks don't escape through `.resolve()` so they cannot exercise the dual-anchor's symlink-escape path. WRONG test for T2.
- **C. Monkeypatch `Path.resolve`** — inject a resolve target outside PROJECT_ROOT. Exercises the dual-anchor divergence WITHOUT requiring filesystem symlink privileges. Cycle-16 L2 L4 "position-divergent" pattern.

**Recommendation:** C. Monkeypatching `Path.resolve` is the cycle's idiomatic pattern (cycle-24 L4 position-assertion rule) — divergent inputs between literal-path and resolve-target are exactly what the dual-anchor catches. No Windows-privilege skip required. Symlink-on-disk is optional redundant coverage (can add as `@pytest.mark.skipif(os.name == 'nt' and not has_symlink_priv, ...)`).

---

## Q8 (AC5) — BACKLOG delete scope for HIGH #6

Options:

- **A. Delete the HIGH bullet entirely** (lines 95-96). HIGH-Deferred at line 109 is the authoritative remainder.
- **B. Move the HIGH bullet under HIGH-Deferred with annotation** — preserves the historical R3 context.
- **C. Leave as-is with "RESOLVED per cycle 26/28" strike-through** — BACKLOG lifecycle says DELETE on resolve (never strike-through).

**Recommendation:** A. BACKLOG hygiene rule is explicit: resolved items get DELETED. HIGH-Deferred line 109 already captures the true-deferred residue.

---

## Q9 — Test-count deltas

- AC1 adds 3 regression tests (one per branch: cleared+error, cleared-only, main-error).
- AC2 adds 5 regression tests (manifest outside / vector_db outside / symlink-escape-via-resolve / inside succeeds / None defaults).
- AC3 adds 1 source-scan comment-presence test.
- AC4 + AC5 add 2 source-scan BACKLOG-hygiene tests.

**Total cycle-29 tests:** 11 new tests in `tests/test_cycle29_rebuild_indexes_hardening.py` + `tests/test_cycle29_backlog_hygiene.py`.

**Full-suite count projection:** 2809 + 11 = 2820 tests. Will verify post-Step-9 via `pytest --collect-only -q | tail -1` per cycle-26 L2 rule.

---

## Q10 — File split

Options:

- **A. One test file** `tests/test_cycle29_rebuild_indexes_hardening.py` with nested classes per AC. Cycle precedent.
- **B. Two test files** — `tests/test_cycle29_rebuild_indexes_hardening.py` for AC1/AC2 + `tests/test_cycle29_backlog_hygiene.py` for AC3/AC4/AC5 source-scan. Cleaner test-type separation.

**Recommendation:** B. Source-scan tests are a different shape (open-file-grep) than integration tests (monkeypatch + invoke); keeping them separate clarifies reviewer mental model and isolates any reload-leak surface (cycle-19 L2) to the scan file only.

---

## Summary of recommendations

| Q | Recommendation | Rationale |
|---|---|---|
| Q1 | A — `cleared (warn: <error>)` | Readable, greppable, matches convention |
| Q2 | A — symmetric manifest rendering | Future-proofs + cycle-16 L1 |
| Q3 | B — `_validate_path_under_project_root` helper | DRY + single contract |
| Q4 | A — match existing message | Consistency |
| Q5 | A — mirror wiki_dir policy | Backward compat |
| Q6 | B — `_audit_token(block)` helper | DRY + pure fn |
| Q7 | C — monkeypatch `Path.resolve` | Portable + divergent-fail |
| Q8 | A — delete HIGH bullet | BACKLOG lifecycle |
| Q9 | — | 11 new tests; 2820 total |
| Q10 | B — two test files | Separate shapes |

Hand off to Step 4 parallel design eval (Opus symbol-verify + Codex edge cases).
