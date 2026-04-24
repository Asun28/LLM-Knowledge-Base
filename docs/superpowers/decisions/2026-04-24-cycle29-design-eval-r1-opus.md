# Cycle 29 — R1 Opus Design Eval

**Reviewer:** Opus 4.7 (1M context)
**Date:** 2026-04-24
**Scope:** AC1-AC5 as specified in `2026-04-24-cycle29-requirements.md`
**Prior-art inputs read:**
- `docs/superpowers/decisions/2026-04-24-cycle29-requirements.md`
- `docs/superpowers/decisions/2026-04-24-cycle29-threat-model.md`
- `docs/superpowers/decisions/2026-04-24-cycle29-brainstorm.md`
- `src/kb/compile/compiler.py` (lines 590-763)
- `src/kb/config.py` (line 80)
- `src/kb/capture.py` (lines 297-318)
- `src/kb/utils/wiki_log.py` (full)
- `src/kb/errors.py` (lines 40-75)
- `src/kb/cli.py` (lines 512-548)
- `tests/test_cycle23_rebuild_indexes.py`
- `tests/test_cycle25_rebuild_indexes_tmp.py`
- `BACKLOG.md` (lines 95-96, 125-129, 193-197)

---

## 1. Symbol-verification table

Per cycle-15 L1 "Symbol-verification gate" red flag: grepped every cited symbol before scoring.

| Symbol | File:line | Status |
|---|---|---|
| `rebuild_indexes` (def) | `src/kb/compile/compiler.py:590` | EXISTS |
| `rebuild_indexes` (CLI invoke) | `src/kb/cli.py:543` (`rebuild_indexes_cmd` at 528, lazy imports `rebuild_indexes`) | EXISTS |
| `rebuild_indexes` (test usage) | `tests/test_cycle23_rebuild_indexes.py:100,127,150,173,199,237`; `tests/test_cycle25_rebuild_indexes_tmp.py:16,48,74,106,141` | EXISTS |
| `HASH_MANIFEST` (declaration) | `src/kb/compile/compiler.py:26` | EXISTS |
| `HASH_MANIFEST` (use in rebuild_indexes) | `src/kb/compile/compiler.py:658` | EXISTS (`manifest_path = hash_manifest or HASH_MANIFEST`) |
| `_vec_db_path` (declaration) | `src/kb/query/embeddings.py:200` | EXISTS |
| `_vec_db_path` (use in rebuild_indexes) | `src/kb/compile/compiler.py:661` | EXISTS (`vector_path = vector_db or _vec_db_path(effective_wiki)`) |
| `PROJECT_ROOT` (imported in compiler) | `src/kb/compile/compiler.py` (via `from kb.config import PROJECT_ROOT`, used line 638) | EXISTS |
| `ValidationError` (def) | `src/kb/errors.py:52` | EXISTS |
| `ValidationError` (import in compiler) | `src/kb/compile/compiler.py:17` (`from kb.errors import ValidationError`) | EXISTS |
| `append_wiki_log` (def) | `src/kb/utils/wiki_log.py:71` | EXISTS |
| `append_wiki_log` (use in rebuild_indexes) | `src/kb/compile/compiler.py:758` | EXISTS |
| `file_lock` (use in rebuild_indexes) | `src/kb/compile/compiler.py:673` (`with file_lock(manifest_path, timeout=1.0)`) | EXISTS |
| `clear_template_cache` (use) | `src/kb/compile/compiler.py:728-731` | EXISTS |
| `_load_page_frontmatter_cached.cache_clear()` | `src/kb/compile/compiler.py:735-738` | EXISTS |
| `load_purpose.cache_clear()` | `src/kb/compile/compiler.py:742-745` | EXISTS |
| `CAPTURES_DIR` (decl) | `src/kb/config.py:80` (literal line cited by req) | EXISTS |
| `_get_prompt_template` (def) | `src/kb/capture.py:313` | EXISTS (req cites `capture.py:313-318`, which is a 1-line offset from the `~310-318` hint — the function body IS 313-318, EXISTS) |
| `capture_prompt.txt` (file) | Referenced at `src/kb/capture.py:317`; used in tests at `tests/test_cycle17_capture_prompt.py:20` | EXISTS (cycle-17 AC9) |
| BACKLOG line 95-96 (AC5 target) | `BACKLOG.md:95-96` (`query/embeddings.py _get_model (~32-41) cold load — measured 0.81s + 67 MB RSS...`) | EXISTS (matches req citation) |
| BACKLOG line 193-194 (AC4 target) | `BACKLOG.md:193-194` (`capture.py:209-238 _PROMPT_TEMPLATE inline string vs templates/ convention`) | EXISTS (matches req citation) |
| BACKLOG line 196-197 (AC3 cross-link) | `BACKLOG.md:196-197` (`config.py:40-53 + CLAUDE.md architectural contradiction`) | EXISTS — **see semantic-mismatch note below** |
| BACKLOG HIGH-Deferred (AC5 keeps) | `BACKLOG.md:105-109` | EXISTS |
| Audit rendering site (AC1 target) | `src/kb/compile/compiler.py:751-756` + call at 758 | EXISTS (req cites `752-756`; line 751 is `log_path = ...`; the `msg =` block is 752-756; call_site=758) |
| Override acceptance (AC2 target) | `src/kb/compile/compiler.py:658-661` | EXISTS |
| wiki_dir validation (AC2 mirror) | `src/kb/compile/compiler.py:637-656` | EXISTS (req cites 638-656; effective_wiki init is 637) |
| `is_relative_to` (dual-anchor) | `src/kb/compile/compiler.py:648,655` | EXISTS |

**SEMANTIC-MISMATCH notes:**
1. AC3 requirements line says "config.py line 80" (which is correct for the current file). The BACKLOG entry at line 196 says `config.py:40-53`, which is STALE — the actual declaration is at line 80. This is a pre-existing BACKLOG drift and not an AC3 blocker, but the AC3 fix can optionally correct the line-number reference in the BACKLOG carve-out resolution. **Flag** for Step-5.
2. AC1 line citation "audit line at lines 752-756" is the `msg =` f-string block; the actual `append_wiki_log(...)` CALL is at 758. Both are correct; the fix edits lines 752-756 (the message template). **No blocker.**

---

## 2. Per-AC scoring

### AC1 — `rebuild_indexes` audit status reflects partial clears

**Verdict: APPROVE (with one AMEND note for the `_audit_token` helper contract).**

**What the AC says:** replace the ternary at lines 752-756 so that when `result["vector"]["cleared"]=True AND result["vector"]["error"]` is truthy, the rendered token becomes `cleared (warn: tmp: <msg>)` (or symmetric form) rather than `cleared`. Mirror to `manifest=`.

**Evidence of real bug:** Lines 716-723 CORRECTLY store the compound error in `result["vector"]["error"]` — so the RETURN shape already preserves the signal. The lines 752-756 `msg =` template is the REGRESSION site — `cleared if X else error` emits `cleared` alone when both are set, discarding the `tmp: ...` tail. Confirmed by reading the source.

**Risks:**
- *Test-hole risk* — Brainstorm Q6 proposes a `_audit_token(block)` helper (APPROVE). If kept inline, the renderer is tested only end-to-end via `wiki/log.md` read — fine as long as the 3 tests cover all 3 branches. If extracted, a unit test on `_audit_token` itself is additive, not a replacement (cycle-11 L2 source-scan hazard is AVOIDED because the integration tests read the actual persisted log file, not the function body).
- *Naming inconsistency* — the existing `result["vector"]["error"]` IS already a compound string (`"vec: ...; tmp: ..."`). The AC proposes `cleared (warn: tmp: <msg>)`. Under the `cleared=True AND tmp_error only` branch, the stored error is `"tmp: <msg>"` (with `tmp:` already prepended). So the rendered token becomes `cleared (warn: tmp: <msg>)` — note the DOUBLE `tmp:` prefix does NOT arise because the `tmp:` comes from the error string itself. The AC's proposed format `cleared (warn: tmp: <msg>)` in the requirements example is actually `cleared (warn: ${existing_error_string})` — the literal `tmp:` in the example is incidental. This is CORRECT but the helper docstring must state this clearly. **AMEND: Q6 helper docstring must say `"Returns 'cleared (warn: ${block['error']})' when cleared=True AND error truthy"` — NOT `"returns 'cleared (warn: tmp: ...)' "`. The `tmp:` prefix is already baked in by the caller (lines 718-723).**
- *Cycle-11 L2 source-scan hazard* — NONE. Tests read the persisted `wiki/log.md` file, which IS the documented output. This is a BEHAVIORAL assertion, not an `inspect.getsource` scan.
- *Cycle-12 L1 scope creep* — NONE. AC1 is strictly an audit-rendering edit within 5 lines.
- *Cycle-23 L2 stub-return-type hazard* — Worth a glance. `_audit_token(block)` would take a dict (`{"cleared": bool, "error": str | None}`) and return `str`. No Optional/Union return. Clean.

**Missing threat-model coverage:** None. T1 is cleanly covered; T3 correctly excludes AC1 from further threat analysis.

**Open question that brainstorm did not address:**
- If `vector=cleared (warn: ...)` contains a `;` from the compound error (`"vec: X; tmp: Y"` — but this branch has `cleared=False` per the `if vec_error` arm setting error while `if main unlink succeeded`), does the existing `append_wiki_log` pipe/newline neutralizer at `wiki_log.py:91-100` interfere with the `(` or `;` characters? **Grep confirms it does NOT touch `(` or `;` — only `|`, `\n`, `\r`, `\t`, and markdown prefix chars. The `(warn: ...)` form is safe.**

**Verdict reasoning:** The bug is real, the fix is mechanical, and the 3 tests cover all 3 branches (cleared+error / cleared-only / main-error). Symmetric manifest treatment (Q2 Option A) is defensible future-proofing with minimal cost. Approve with the docstring AMEND noted above.

---

### AC2 — `rebuild_indexes` validates `hash_manifest` + `vector_db` overrides under PROJECT_ROOT

**Verdict: APPROVE (with two AMEND notes — see Q2/Q4 below).**

**What the AC says:** apply the dual-anchor containment check at lines 647-656 to each override when caller supplies absolute `hash_manifest` / `vector_db`; raise `ValidationError` before any `unlink()`.

**Evidence of real gap:** Grep confirms overrides at lines 658-661 pass directly to `unlink()` at lines 675, 689, 710 with zero containment check. Only `wiki_dir` is validated.

**Risks:**
- *Test-hole risk* — Brainstorm Q7 recommends monkeypatching `Path.resolve` to simulate symlink escape. This is cycle-16 L2/L4 "position-divergent" pattern. Good. BUT — `Path` is an immutable type; monkeypatching `Path.resolve` globally risks contaminating other ongoing tests that happen to call `.resolve()`. **AMEND: prefer either (a) a real `os.symlink` with Windows skip (cycle-23 precedent at `tests/test_cycle23_rebuild_indexes.py:153`, which uses `Path(tmp_project.drive + os.sep + "some_other_root").resolve()` for the literal-form anchor and doesn't need a real symlink) OR (b) a subclass of Path that overrides `resolve()`. The `tests/test_cycle23_rebuild_indexes.py:171` pattern already demonstrates that absolute-path outside PROJECT_ROOT is enough to cover the literal-anchor case. For the resolve-anchor case (literal-clean → resolved-outside), a real `os.symlink` with @pytest.mark.skipif is the idiomatic path.**
- *Signature-drift risk* — Brainstorm Q3 recommends extracting `_validate_path_under_project_root(path, field_name) -> Path`. This factoring IS desirable but requires a caller-grep checkpoint per `feedback_signature_drift_verify` memory. Grep confirms the current `wiki_dir` block at 647-656 is the ONLY caller today; extracting it + routing `wiki_dir` through the same helper IS non-trivial because the `wiki_dir` block has an extra `except OSError` around the `resolve()` call (line 653) which overrides and hash_manifest paths do NOT need (they are only passed to `unlink()` which accepts OSError directly). **AMEND: the extracted helper should include the `except OSError as e: raise ValidationError(f"{field_name} cannot be resolved: {e}") from e` branch so all three callers share the same behavior.**
- *Cycle-11 L2 source-scan hazard* — NONE. Tests exercise real production path (raise `ValidationError` before unlink). Use `unittest.mock.patch.object(Path, 'unlink')` as a SPY to verify unlink never fires per requirement AC2 test #1 language ("assert ... BEFORE any unlink call (spy on `Path.unlink`)").
- *Cycle-12 L1 scope creep* — BORDERLINE. Q3 Option B (`_validate_path_under_project_root` helper) technically refactors the pre-existing `wiki_dir` block, which is OUT of the AC2 stated scope ("validate overrides"). Brainstorm justifies it as DRY, but a conservative reviewer would APPROVE with a note: the existing `wiki_dir` block's behavior MUST be unchanged (verified by existing tests at `test_cycle23_rebuild_indexes.py:136, 153`). **AMEND: add a Step-11 checklist item explicitly re-running `test_rebuild_indexes_rejects_wiki_dir_outside_project` + `test_rebuild_indexes_rejects_symlinked_wiki_dir_outside_project` after the helper extraction.**
- *Cycle-19 L3 empty-input validator hazard* — YES, RELEVANT. The dual-anchor check at line 647 starts with `if effective_wiki.is_absolute() and not ...`. For an override, `Path("")` is NOT absolute → skips the pre-check AND also is NOT really resolvable (empty string Path resolves to CWD). `Path("").resolve() == Path.cwd().resolve()` — if CWD is under PROJECT_ROOT, validation PASSES → then the `unlink()` at line 675/689/710 gets `Path("")`, which POSIX will error on (`IsADirectoryError` or `PermissionError`), and Windows will error too. So the FAIL-CLOSED behavior is preserved at the `unlink` layer, but the error message is less clean than `ValidationError("hash_manifest must be inside project root")`. **AMEND: brainstorm Q5 ("relative override handling") should explicitly cover the empty-string case. Recommend adding `if hash_manifest == Path(""): raise ValidationError("hash_manifest must be non-empty")` inside the helper, OR accept the degraded error message as non-blocking. Either is defensible; prefer the explicit check for operator friendliness.**
- *Cycle-20 L1 reload-drift hazard* — YES, RELEVANT. Existing tests at `test_cycle23_rebuild_indexes.py:139-146` demonstrate the correct pattern: `from kb.compile import compiler; ValidationError = compiler.ValidationError` (late-bind from the production module, NOT `from kb.errors import ValidationError`). **AMEND: AC2 tests MUST follow the cycle-23 pattern — late-bind via `compiler.ValidationError`, NEVER import `ValidationError` directly from `kb.errors`. The requirements file does not spell this out; the plan step MUST.**
- *Cycle-23 L2 stub-return-type hazard* — MINOR. `_validate_path_under_project_root(path, field_name) -> Path` returns the RESOLVED path. If it simply returns the input `path` argument unchanged, callers may assume it is `.resolve()`-ed. If it returns the resolve()-result, callers who intended to unlink the LITERAL caller path (not the resolved one) get a surprise. **AMEND: the helper should EITHER return `None` (raising on failure, no return value) OR return the resolved Path — and the `unlink` sites at 675/689/710 should then be audited for whether they want literal or resolved. Current code uses the literal (`manifest_path`, `vector_path`) for unlink. Safest: helper is void-return (raises or passes). Callers continue to use the literal path.**

**Missing threat-model coverage:** Threat model's T2 is thorough. One micro-gap: the T2 description says "arbitrary-file-unlink primitive scoped to the process user" but does NOT explicitly name the `.lnk` / reparse-point on Windows as an alternative escape vector. The brainstorm Q7 glosses over this; `os.path.realpath` on Windows follows directory junctions but NOT `.lnk` shortcuts. This is low priority because `rebuild_indexes` uses `Path.resolve()` which DOES follow junctions, and `.lnk` files are not a Python path primitive. **No blocker.**

**Verdict reasoning:** Real security-hardening AC with clean additive semantics. The helper extraction is defensible but adds 3 amend notes (late-bind ValidationError, empty-input handling, helper return-type). Approve.

---

### AC3 — `config.py` CAPTURES_DIR architectural carve-out comment

**Verdict: APPROVE.**

**What the AC says:** add a 3-5 line comment block above `CAPTURES_DIR = RAW_DIR / "captures"` at `config.py:80` citing (a) carve-out, (b) `kb_capture` atomisation, (c) raw-input-for-ingest, (d) CLAUDE.md cross-ref.

**Risks:**
- *Cycle-11 L2 source-scan hazard* — YES, BY DESIGN. The AC3 test IS a source-scan (`open config.py`, grep tokens). The AC explicitly acknowledges this ("lightweight source-scan test — acceptable because the assertion IS the documentation presence check; reverting the comment MUST fail this test — divergent-fail property preserved"). This is the correct escape-hatch pattern. **No blocker.**
- *Cycle-12 L1 scope creep* — NONE.
- *Naming inconsistency* — The AC says "at least 3 of the preceding 6 lines contain one of these tokens: `LLM-written`, `carve-out`, `kb_capture`, `raw input for subsequent ingest`". That's 4 tokens. Requirement of "at least 3 of the preceding 6 lines contain ONE of these tokens" is ambiguous — does it mean "at least 3 of the 4 tokens appear across the preceding 6 lines" or "at least 3 lines each contain at least one of the 4 tokens"? **AMEND: plan step should disambiguate — recommend "at least 3 DISTINCT tokens from {LLM-written, carve-out, kb_capture, raw input for subsequent ingest} appear in the 6 lines above `CAPTURES_DIR =`".**
- *Cycle-20 L1 reload-drift hazard* — NONE.

**Missing threat-model coverage:** T3 correctly marks AC3 as inert. No threat surface.

**Open question not addressed:**
- Does the new comment block also need to update the BACKLOG entry at `config.py:40-53` (line number in BACKLOG is stale — actual line is 80)? **Recommendation:** since AC3 closes the carve-out-comment gap, the entire BACKLOG bullet at line 196-197 can be DELETED (it's a Phase-5-pre-merge item whose stated fix was "carve out an explicit exception in CLAUDE.md and the config comment"). AC3 delivers the config-comment half; CLAUDE.md already has the carve-out in the `raw/` bullet. **AMEND: add to AC3 scope "also delete BACKLOG.md:196-197" — otherwise we ship the fix but leave the BACKLOG drift open. This is coherent with AC4 and AC5 style.**

**Verdict reasoning:** Trivial comment add, but scope should include the BACKLOG bullet deletion to match AC4/AC5 pattern.

---

### AC4 — Delete stale `_PROMPT_TEMPLATE` BACKLOG entry

**Verdict: APPROVE.**

**What the AC says:** delete BACKLOG.md line 193-194 (the `capture.py:209-238 _PROMPT_TEMPLATE inline string vs templates/ convention` bullet). No code change.

**Risks:**
- *Stale-claim verification* — Verified:
  - `capture.py:313-318` shows `_get_prompt_template()` function (lazy loader, as cycle-19 AC15).
  - `templates/capture_prompt.txt` exists and is tested by `tests/test_cycle17_capture_prompt.py:19-22`.
  - The original inline string `_PROMPT_TEMPLATE = """..."""` is NOT present in `capture.py` (verified by grep — only loader pattern at line 317).
  - CLAUDE.md `Feedback: Ruff-format vs Edit order` memory is a separate concern; not relevant here.
  - CLAUDE.md `feedback_ruff_unused_import_monkeypatch` is also not relevant.
- *Cycle-11 L2 source-scan hazard* — YES, BY DESIGN. `test_captures_backlog_entry_deleted` reads BACKLOG.md and asserts `_PROMPT_TEMPLATE` NOT present. Divergent-fail preserved (re-adding the bullet fails). **No blocker.**
- *Cycle-12 L1 scope creep* — NONE.
- *Regression risk* — NONE. No code change.

**Missing threat-model coverage:** T3 correctly inert.

**Open question:**
- The req says "assert `_PROMPT_TEMPLATE` substring NOT present in any MEDIUM or below section". What if a future cycle adds a DIFFERENT bullet about `_PROMPT_TEMPLATE` (e.g., a new reload-leak regression)? The test would false-fail. **AMEND: scope the substring check tighter — e.g., `_PROMPT_TEMPLATE inline string` (the 2-word phrase unique to the stale bullet) rather than just `_PROMPT_TEMPLATE`.**

**Verdict reasoning:** Clean doc-hygiene delete. Approve with tighter substring match.

---

### AC5 — Narrow stale Phase 4.5 HIGH #6 cold-load BACKLOG entry

**Verdict: APPROVE.**

**What the AC says:** delete BACKLOG.md line 95-96 (the `query/embeddings.py _get_model (~32-41) cold load — measured 0.81s + 67 MB RSS delta...` bullet). HIGH-Deferred line 109 survives.

**Risks:**
- *Stale-claim verification* — Verified:
  - CLAUDE.md cites cycle-26 AC1-AC5 shipped `maybe_warm_load_vector_model` + MCP-boot wiring + `_get_model` latency instrumentation + `get_vector_model_cold_load_count()`.
  - CLAUDE.md cites cycle-28 AC1-AC5 shipped `_ensure_conn` sqlite-vec latency instrumentation + `BM25Index.__init__` latency instrumentation + corresponding counters.
  - HIGH-Deferred at line 109 correctly summarises shipped work and identifies the true-deferred residue: "dim-mismatch AUTO-rebuild".
  - The HIGH bullet at 95-96 describes unmitigated 0.81s cold-load + "hybrid silently degrades to BM25" — BOTH concerns are addressed by cycle-26 (warm-load gate on `vec_path.exists()`) and cycle-26/28 observability.
- *Cycle-11 L2 source-scan hazard* — YES, BY DESIGN. Acceptable.
- *Cycle-12 L1 scope creep* — NONE.
- *Double-delete risk* — The AC says "assert no HIGH-level bullet contains the substring `0.81s + 67 MB` OR `cold load — measured`". The HIGH-Deferred at line 109 contains the phrase "cold-load latency" and "cold-load count" but NOT the exact substring `cold load — measured`. Verified — substrings are distinct. **No blocker, but the plan should document that the `cold-load latency` phrase in HIGH-Deferred must NOT match the test's substring list.**

**Missing threat-model coverage:** T3 correctly inert.

**Open question:**
- Should the AC also grep for `0.81s` globally in the repo for drift, to catch any stale citation in plans/designs/specs? **Recommendation:** No. Only BACKLOG.md governs open work. Plans/designs are historical artifacts.

**Verdict reasoning:** Clean delete. Approve.

---

## 3. Cycle-lesson cross-check summary

| Lesson | AC where relevant | Coverage |
|---|---|---|
| Cycle-11 L2 source-scan hazard | AC3, AC4, AC5 | All 3 use source-scan tests BY DESIGN (divergent-fail property preserved). Acceptable escape hatch per precedent. |
| Cycle-12 L1 scope creep | AC2 (helper extraction), AC3 (BACKLOG delete add) | Minor. AMEND notes added. |
| Cycle-15 L1 symbol-verification gate | ALL | Satisfied by the table in §1. |
| Cycle-16 L1 same-class-peer rule | AC1 (symmetric manifest) | Satisfied. |
| Cycle-16 L2/L4 position-divergent pattern | AC2 (symlink-escape test) | Brainstorm Q7 Option C chosen; AMEND prefers real symlink with skipif. |
| Cycle-19 L2 reload-leak | AC2 tests | No test reloads `kb.compile.compiler`; safe. |
| Cycle-19 L3 empty-input validator | AC2 override validation | AMEND: explicit empty-string check recommended. |
| Cycle-20 L1 reload-drift on exception classes | AC2 tests | AMEND: tests MUST late-bind `ValidationError` via `compiler.ValidationError`, following `tests/test_cycle23_rebuild_indexes.py:139-146` pattern. |
| Cycle-23 L2 stub-return-type | AC2 helper | AMEND: helper return-type should be explicitly void (raises-only) to avoid "resolved vs literal" ambiguity. |
| Cycle-24 L1 `Edit(replace_all=true)` risk | AC2 helper factoring | Reduced by the DRY helper (Q3). |
| `feedback_inspect_source_tests` | AC3, AC4, AC5 | The tests read the FILE CONTENTS (not `inspect.getsource` of a module) — subtly different. Re-adding the deleted comment or the deleted BACKLOG bullet WILL make the test fail. Divergent-fail preserved. Acceptable. |
| `feedback_test_behavior_over_signature` | AC1, AC2 | Satisfied — tests exercise the `wiki/log.md` persisted output and `unlink` spy, not function-signature inspection. |

---

## 4. Open questions for Step-5 decision gate

**Q1: AC1 — `_audit_token` helper location and docstring precision**

- Option A: inline 2 ternaries at lines 753-754 (no helper, 2-line diff).
- Option B: module-level helper `_audit_token(block: dict) -> str` (~6 lines + 2 callers).
- **Recommendation:** Option B per brainstorm Q6 BUT with the docstring AMEND from AC1 above: the helper renders `"cleared (warn: {block['error']})"` verbatim — the existing `tmp:` / `vec:` prefix is baked in by the caller.

**Q2: AC2 — helper extraction `_validate_path_under_project_root`**

- Option A: apply to all 3 sites (wiki_dir + 2 overrides) per brainstorm Q3. Pros: DRY, single contract. Cons: minor scope-creep touching wiki_dir.
- Option B: apply only to the 2 overrides. Pros: strict scope. Cons: 3-way duplication (22 lines each × 3 = 66 lines of near-dupe).
- Option C: hybrid — extract helper, call from overrides only; leave wiki_dir inline. Pros: true additive. Cons: weird asymmetry.
- **Recommendation:** Option A (per brainstorm). Requires Step-11 caller-grep checkpoint (per `feedback_signature_drift_verify`) and re-run of the two cycle-23 wiki_dir tests after refactor.

**Q3: AC2 — symlink-escape test portability**

- Option A: real `os.symlink` with `@pytest.mark.skipif(os.name == 'nt' and not has_symlink_priv, ...)`. Matches cycle-23 precedent at line 153 which uses LITERAL-form-outside-PROJECT_ROOT with real paths.
- Option B: monkeypatch `Path.resolve` globally (brainstorm Q7 C). Risk: contamination.
- Option C: subclass Path with custom `.resolve()`. Cleanest isolation, but boilerplate.
- **Recommendation:** Option A for the literal-anchor case (already covered by cycle-23 pattern); add a thin Option C subclass-Path for the resolve-anchor case on Linux CI, guarded by skipif on Windows. Hybrid.

**Q4: AC2 — `ValidationError` message form for overrides**

- Option A: match existing — `"hash_manifest must be inside project root"`, `"vector_db must be inside project root"` (brainstorm Q4 A).
- Option B: include the offending path — less private but more debuggable.
- Option C: include field name + path suffix only — `"hash_manifest ... <basename>"`.
- **Recommendation:** Option A. Consistency with the existing `wiki_dir` messages wins; caller traceback shows the offending Path anyway.

**Q5: AC2 — empty-string / empty-Path handling**

- Option A: treat `Path("")` the same as `Path(".")` (CWD-relative) — falls through to resolve-anchor check; if CWD is under PROJECT_ROOT, validation passes and `unlink(Path(""))` errors at OS level.
- Option B: explicit check — `if override == Path(""): raise ValidationError(f"{field_name} must be non-empty")`.
- Option C: treat `hash_manifest=Path("")` as equivalent to `hash_manifest=None` (use default HASH_MANIFEST).
- **Recommendation:** Option B. Explicit, fails fast, consistent error message. Option C silently "corrects" bad input which violates the principle-of-least-surprise.

**Q6: AC3 — also delete BACKLOG.md:196-197 as part of AC3 scope?**

- Option A: YES — AC3 closes the "carve out an explicit exception in CLAUDE.md and the config comment" fix prescription. Matches AC4/AC5 delete pattern.
- Option B: NO — keep AC3 strictly a comment-add, leave BACKLOG bullet for a future cycle.
- **Recommendation:** Option A. Closing the fix without deleting the BACKLOG entry creates BACKLOG drift — the exact problem AC4/AC5 address. Scope is still tight (one-line comment-add test + one-line BACKLOG delete test).

**Q7: AC2 — cycle-20 L1 reload-drift pattern enforcement in tests**

- Option A: tests import `from kb.errors import ValidationError` at top.
- Option B: tests late-bind via `compiler.ValidationError` per cycle-23 precedent.
- **Recommendation:** Option B. Matches proven pattern; no risk if `kb.compile.compiler` is reloaded mid-test.

**Q8: Overall — single PR commit plan vs split?**

- Option A: 4 impl commits (AC1, AC2, AC3, AC4+AC5) + 1 doc commit + up to 2 review-fix commits (per brainstorm Q10 + requirements plan).
- Option B: 1 monolithic commit "cycle 29 backlog-by-file cleanup".
- **Recommendation:** Option A. Per `feedback_taskcreate_zero_pad` and batch-by-file memory, commit-per-AC-group preserves git-bisectability. 5-7 total commits is within the cycle-scale norm.

---

## 5. Summary

| AC | Verdict | Blockers | AMENDs |
|---|---|---|---|
| AC1 | APPROVE | 0 | 1 (helper docstring precision) |
| AC2 | APPROVE | 0 | 4 (symlink-test portability, helper extraction grep-check, empty-input, late-bind ValidationError) |
| AC3 | APPROVE | 0 | 2 (token count disambiguation, include BACKLOG:196-197 delete) |
| AC4 | APPROVE | 0 | 1 (tighter substring match `_PROMPT_TEMPLATE inline string`) |
| AC5 | APPROVE | 0 | 0 |

**Cycle is SHIP-READY after the 8 AMEND notes are captured in the design doc / plan.** Total test-count delta 11 new tests → 2820 total per brainstorm Q9. No HIGH-severity risks; two MEDIUM-severity risks (AC2 helper extraction testing + AC2 empty-input) require explicit plan-step coverage.

Hand off to R1 Codex and Step-5 Opus decision gate.
