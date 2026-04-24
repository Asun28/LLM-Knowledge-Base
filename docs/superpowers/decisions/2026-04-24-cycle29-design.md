# Cycle 29 — Design Decision Gate

**Date:** 2026-04-24
**Reviewer:** Opus 4.7 (1M context)
**Inputs:** requirements, threat-model, brainstorm, R1 Opus eval (8 AMENDs), R2 Codex eval (7 gate Qs + 5 edge cases)

## VERDICT

**PROCEED**

All 15 open questions resolved autonomously. No ESCALATION: every question either (a) has a clear principle-based answer or (b) presents reversible internal choices where the lower-blast-radius option is obviously preferred.

## DECISIONS

- **Q1 (audit-token helper)** — B + docstring AMEND. Extract `_audit_token(block: dict) -> str` at module scope; docstring specifies `"Returns 'cleared (warn: {block['error']})' when cleared=True AND error truthy"` — never re-prepend `tmp:`.
- **Q2 (manifest= symmetric rendering)** — A. Mirror the compound rule; uses the same `_audit_token` helper.
- **Q3 (embedded-newline handling)** — A + AC1 regression test. Rely on `append_wiki_log`'s existing sanitizer; ADD a regression test pinning embedded-newline → single-line behavior.
- **Q4 (CLI status renderer mirror)** — A. Mirror the compound rendering to `src/kb/cli.py:550-560` using the same `_audit_token` helper (imported into `cli.py`); adds one CLI-render test.
- **Q5 (non-OSError append_wiki_log catch)** — A. Preserve existing `OSError`-only narrow catch.
- **Q6 (AC2 helper extraction scope)** — A. Extract `_validate_path_under_project_root(path, field_name) -> None` at module scope; refactor `wiki_dir` + both overrides to call it. Void return (raises-only). Helper includes the `except OSError` → `ValidationError(f"{field_name} cannot be resolved: {e}")` branch.
- **Q7 (empty-string handling)** — A. Explicit early `if Path(path) == Path(""): raise ValidationError(f"{field_name} must be non-empty")` INSIDE the helper.
- **Q8 (symlink-escape test strategy)** — D. Hybrid — monkeypatch `Path.resolve` via a subclass (option C mechanics) for the dual-anchor divergence test on any platform, PLUS a real `os.symlink` test guarded by `@pytest.mark.skipif(os.name == 'nt' and not _has_symlink_priv(), ...)` for on-disk coverage.
- **Q9 (test monkeypatch target)** — C. Patch BOTH `kb.compile.compiler.PROJECT_ROOT` AND `kb.config.PROJECT_ROOT` (matches existing cycle-23 pattern at `tests/test_cycle23_rebuild_indexes.py:90-93`; the compiler snapshots `PROJECT_ROOT` at import, so the compiler attribute is the load-bearing one — the config patch is belt-and-suspenders for fixture consistency per R2 finding 5).
- **Q10 (TOCTOU validation↔unlink)** — A. Accept residual. Document in threat-model amendment that `PROJECT_ROOT` containment is a defensive check against a future caller plumbing untrusted input, not a security guarantee against concurrent attacker-controlled edits.
- **Q11 (None-default validation)** — A. Skip validation when override is None. Rationale: `HASH_MANIFEST` is derived from `PROJECT_ROOT` at module import; `_vec_db_path(wiki_dir)` is derived from the already-validated `wiki_dir`. Validating defaults is academic; future cycle can revisit if a drift regression arises.
- **Q12 (existing-test fixture interaction)** — A. Plan-gate checkpoint at Step 11: grep all existing `rebuild_indexes(` callers in `tests/` BEFORE shipping AC2; verify each one monkeypatches `kb.compile.compiler.PROJECT_ROOT` so `tmp_wiki` (under tmp_path, outside real PROJECT_ROOT) still validates. Verified in this gate: `test_cycle23_rebuild_indexes.py:90` and `test_cycle25_rebuild_indexes_tmp.py` (per R2 finding 4 grep — all callers already patch correctly). No test-fixture migration required.
- **Q13 (AC3 scope expansion — delete BACKLOG:196-197)** — A. Expand AC3 scope to delete the BACKLOG bullet; AC3 delivers the full "carve out an explicit exception in CLAUDE.md AND the config comment" fix prescription. Matches AC4/AC5 delete-on-resolve pattern.
- **Q14 (test file split)** — B. Two files: `tests/test_cycle29_rebuild_indexes_hardening.py` (AC1 + AC2 integration tests) and `tests/test_cycle29_backlog_hygiene.py` (AC3 + AC4 + AC5 source-scan tests).
- **Q15 (test count projection)** — 2822. Starting 2809 + AC1(3) + AC2(5) + AC3(1) + AC4(1) + AC5(1) + Q3 embedded-newline regression(1) + Q4 CLI-render test(1) = 2822 total new-suite size.

### Q1 — AC1 audit-token helper location + docstring precision

#### Analysis

The brainstorm Q6 recommended option B (module-level helper `_audit_token`) and the R1 Opus eval concurred, adding a docstring AMEND: the caller already prepends `tmp:` / `vec:` inside the compound error string at lines 718-723, so the helper must render `"cleared (warn: {block['error']})"` verbatim — re-prepending `tmp:` would produce `cleared (warn: tmp: tmp: <msg>)`. The failure mode of inline ternaries is that a future maintainer copies one branch, forgets the other, and the symmetric rule drifts. A module-level helper with a single-source-of-truth contract makes the compound rule testable in isolation (though primary testing remains integration through `wiki/log.md` reads).

The docstring precision question is the load-bearing piece: the compound `result["vector"]["error"]` is already a `"; ".join` of `vec: <msg>` and `tmp: <msg>` tokens (lines 717-723), so the helper's job is PURE rendering of the stored error string — never transformation. Cycle-23 L2 stub-return-type lesson applies: the helper returns `str` unconditionally (never `None`, never `Optional`), so callers have no branch surface. The 3 AC1 tests cover all three branches end-to-end (cleared+error / cleared-only / main-error), and the Q3 embedded-newline regression adds a fourth covering sanitizer interaction.

#### DECIDE

Option B with docstring AMEND. Signature: `def _audit_token(block: dict) -> str`. Docstring: `"""Render the audit token for a rebuild_indexes result block. Returns 'cleared' when cleared=True AND error is None, 'cleared (warn: {error})' when cleared=True AND error truthy, or '{error}' otherwise. The error string is passed through verbatim — callers must pre-format compound tokens like 'tmp: <msg>'."""`. Module-level (file-private via leading underscore).

#### RATIONALE

Cycle-16 L1 same-class-peer rule favours a shared helper over 2 ternaries. Cycle-23 L2 stub-return-type lesson is satisfied by the `str`-only return contract.

#### CONFIDENCE

HIGH

### Q2 — AC1 manifest= symmetric rendering

#### Analysis

The two options are (A) mirror the compound rule to the `manifest=` token, using the same `_audit_token` helper, versus (B) leave `manifest=` with its current ternary and accept rendering asymmetry. Today the manifest block's `cleared=True` branch never sets `error` (lines 672-680: `error` is assigned only on `OSError` or `TimeoutError`, both of which leave `cleared=False`). So option B is DEAD-CODE-EQUIVALENT — the compound token for manifest would never fire today. But the brainstorm's rationale is cycle-16 L1: if a future cycle adds manifest-tmp cleanup (mirroring cycle-25 AC1 for the vector block), the renderer must already be compound-aware or the same silent-swallow bug reoccurs.

The cost of option A is nearly zero because the `_audit_token` helper already exists for the vector case; calling it for manifest is one line. The clarity cost is negative (symmetric treatment is easier to read than divergent treatment). The only real concern is cycle-12 L1 scope creep — but the scope creep here is ~1 line and the requirement's §"Required behavior" explicitly mandates "Same rule MIRRORED to the manifest block for symmetry". So option A is already in-scope.

#### DECIDE

Option A. Apply `_audit_token` to both `manifest` and `vector` blocks.

#### RATIONALE

Cycle-16 L1 same-class-peer rule + requirement-mandated.

#### CONFIDENCE

HIGH

### Q3 — AC1 embedded-newline / control-char handling

#### Analysis

R2 Codex edge case 3 observed that `append_wiki_log`'s existing sanitizer at `wiki_log.py:91-104` normalizes `|`, `\n`, `\r`, `\t` to spaces or forward slashes BEFORE writing the markdown log entry. So an embedded newline in `result["vector"]["error"]` (e.g., a multi-line OSError message) becomes a single physical line automatically. The question is whether AC1's renderer should pre-sanitize, or rely on the sanitizer downstream. Pre-sanitizing inside the renderer would duplicate the logic (cycle-24 L1 `Edit(replace_all=true)` risk — two places to maintain); relying on the downstream contract keeps the renderer pure (cycle-23 L2).

However, R2 also correctly flagged that the deterministic one-line contract is currently ASSUMED, not TESTED. A future refactor to `append_wiki_log` could break the sanitizer without any AC1 test firing. The defensive move is to ADD a regression test that simulates an embedded-newline OSError and asserts the persisted `wiki/log.md` line contains no raw `\n` between `rebuild-indexes` and the next entry delimiter. This pins the contract at the RIGHT LAYER (integration through the real `append_wiki_log` code path), not by duplicating sanitizer logic upstream.

#### DECIDE

Option A + add one regression test. Renderer stays pure. New test `test_audit_renders_embedded_newline_as_single_line` in AC1 harness: simulate `OSError("line1\nline2")`, assert the log line contains `line1 line2` (space-joined by sanitizer) and no raw `\n` between the `rebuild-indexes |` prefix and the EOL.

#### RATIONALE

Trust the existing sanitizer contract (cycle-4 L-style "trust the contract") but pin it with a regression test (cycle-11 L-style "assumed contracts need tests").

#### CONFIDENCE

HIGH

### Q4 — AC1 CLI status renderer mirror

#### Analysis

R2 Codex gate question 3 surfaced that `src/kb/cli.py:550-560` renders `vector_status` with the SAME `cleared if X else error` ternary that AC1 is replacing in `compiler.py:752-756`. If AC1 only fixes the `wiki/log.md` audit line but leaves the CLI status narrower, an operator running `kb rebuild-indexes` interactively sees `vector=cleared` while `wiki/log.md` contains `vector=cleared (warn: tmp: <msg>)`. That's a rendering divergence between two user-facing surfaces of the same result dict — exactly the class of drift cycle-16 L1 same-class-peer is meant to prevent.

The options are (A) mirror the compound rendering to CLI using the same helper, (B) leave CLI narrower (accept the divergence as cycle-12 L1 scope creep risk), or (C) defer to BACKLOG. Option B concedes real operator-facing drift for a weak scope argument — the edit is literally two lines if the `_audit_token` helper is importable. Option C creates BACKLOG debt for a fix that costs less than the BACKLOG entry itself. Option A is the simplest AND the principle-aligned choice: both surfaces render from the same dict, so they should render identically. Cycle-12 L1 concerns about scope creep apply to unrelated additions, not to propagating a fix to a sibling surface.

#### DECIDE

Option A. Mirror compound rendering to CLI. Import `_audit_token` from `kb.compile.compiler` into `cli.py` (function-local import inside `rebuild_indexes_cmd` per cycle-23 AC4 boot-lean contract). Add 1 CLI-render test (`test_cli_rebuild_indexes_shows_compound_vector_status`) in the AC1 file asserting `click.testing.CliRunner` captures the compound token on a simulated tmp-error failure.

#### RATIONALE

Cycle-16 L1 same-class-peer rule applies to the two user-facing renderers of the same `result` dict. Cost is 2 lines + 1 test.

#### CONFIDENCE

HIGH

### Q5 — AC1 non-OSError append_wiki_log catch breadth

#### Analysis

R2 Codex edge case 7 observed that the current audit call at `compiler.py:757-761` catches ONLY `OSError` from `append_wiki_log`. A non-`OSError` (e.g., a future refactor raising `ValueError` from the sanitizer) would propagate up through `rebuild_indexes` and mask the successful unlinks. The question is whether to broaden to `Exception` or preserve the narrow catch. Broadening is safer against future refactors but risks swallowing programmer errors (e.g., a bug in the renderer). Narrowing is stricter but exposes the current contract (the `append_wiki_log` implementation only raises `OSError` after its internal retry-once loop at `wiki_log.py:154-158`).

The design principle from cycle-4 L-style is "trust the contract" — if `append_wiki_log` raises only `OSError`, the caller should catch only `OSError`. Broadening to `Exception` would be a defensive-coding anti-pattern (swallow-all): a `ValueError` or `TypeError` from a bug in the sanitizer becomes a silent audit failure that operators never see. The caller already handles the only documented failure mode; broadening has negative value. If a future cycle extends `append_wiki_log` to raise new exception classes, the caller update is a deliberate contract change that deserves a cycle of its own.

#### DECIDE

Option A. Preserve `OSError`-only narrow catch.

#### RATIONALE

Cycle-4 L-style "trust the contract". Broadening risks silent bug-swallowing.

#### CONFIDENCE

HIGH

### Q6 — AC2 helper extraction scope

#### Analysis

The options are (A) extract a shared helper and apply to all 3 sites (wiki_dir + 2 overrides), (B) inline 3 near-duplicate blocks, or (C) hybrid. The brainstorm Q3 and R1 Opus eval both recommend option A with the AMEND that the helper must include the `except OSError as e: raise ValidationError(f"{field_name} cannot be resolved: {e}")` branch that the current `wiki_dir` code uses (`compiler.py:651-654`). R1 Opus also AMEND'd that the return type should be void (raises-only) to avoid cycle-23 L2 stub-return-type ambiguity — if the helper returned the resolved path, callers might confuse "unlink the resolved target" with "unlink the literal input", where the existing code uses the LITERAL path for unlink.

Option B (inline) produces ~18 lines × 3 = 54 lines of near-duplicate validation logic — cycle-24 L1 `Edit(replace_all=true)` is the maintenance horror story this creates. Option C (hybrid) creates asymmetry: two call sites use the helper, one uses inline; future readers cannot tell which is canonical. Option A is the DRY choice, and the scope-creep concern (touching pre-existing `wiki_dir` code) is bounded because (i) the refactor is mechanical, (ii) existing cycle-23 tests `test_rebuild_indexes_rejects_wiki_dir_outside_project` and `test_rebuild_indexes_rejects_symlinked_wiki_dir_outside_project` already pin the behaviour and will fail loudly if the refactor drifts, and (iii) the Step-11 caller-grep checkpoint per feedback_signature_drift_verify catches any breakage before merge.

#### DECIDE

Option A with R1 Opus AMEND. Signature: `def _validate_path_under_project_root(path: Path, field_name: str) -> None` (void return, raises-only). Body: (i) explicit empty-path check (see Q7), (ii) dual-anchor check (literal-abs + resolve-target), (iii) `except OSError` → `ValidationError(f"{field_name} cannot be resolved: {e}") from e`. Callers: `wiki_dir` block (existing), `hash_manifest` (new, only when caller supplied non-None), `vector_db` (new, only when caller supplied non-None).

#### RATIONALE

Cycle-16 L1 (DRY same-class-peer) + cycle-23 L2 (void return avoids stub-type ambiguity) + cycle-24 L1 (reduces Edit-risk surface).

#### CONFIDENCE

HIGH

### Q7 — AC2 empty-string / `Path("")` handling

#### Analysis

R1 Opus AMEND 3 raised this: `Path("")` is not absolute (skips the pre-check) but `.resolve()` to `Path.cwd()`, so if CWD is under `PROJECT_ROOT` (typical dev case), the dual-anchor check passes and the unlink at `compiler.py:675/689/710` gets `Path("")`, which errors at OS level as `IsADirectoryError` or `PermissionError`. Fail-closed is preserved but the error message is noisy and the caller gets an OS error rather than the clean `ValidationError("X must be inside project root")` contract. Cycle-19 L3 empty-input validator hazard explicitly names this failure mode: a validator that accepts `""` and relies on a downstream layer to reject it produces confusing error chains.

Option A (explicit early check) fails-fast with a crisp `ValidationError("{field_name} must be non-empty")`. Option B (fall through) accepts the degraded message. Option C (treat `Path("")` as `None` → use default) is SILENT CORRECTION of bad input, violating principle-of-least-surprise — a caller passing `Path("")` clearly meant to pass a path, not to defer to defaults; silently using the default would hide a bug. Option A is the clear winner: one line inside the helper, consistent error shape with other containment violations, no failure-mode drift.

#### DECIDE

Option A. Inside `_validate_path_under_project_root`, first statement: `if path == Path(""): raise ValidationError(f"{field_name} must be non-empty")`.

#### RATIONALE

Cycle-19 L3 empty-input validator hazard. Principle-of-least-surprise rejects option C (silent correction).

#### CONFIDENCE

HIGH

### Q8 — AC2 symlink-escape test strategy

#### Analysis

The brainstorm Q7 recommended option C (monkeypatch `Path.resolve`). R1 Opus AMEND 1 pushed back: monkeypatching `Path.resolve` globally risks contaminating other tests that happen to call `.resolve()` — cycle-16 L2/L4 "position-divergent" pattern is the GOAL, but the implementation needs isolation. R1 Opus recommended a hybrid: real `os.symlink` with Windows skipif for on-disk coverage (cycle-23 precedent), plus optional `Path` subclass for the divergence-only dimension. R2 Codex edge case 2/6 noted UNC path and junction-following behaviour for `Path.resolve()` is not specified in the repo, so claiming equivalence across POSIX symlinks, Windows symlinks, and junctions without explicit test coverage is risky.

The safest hybrid is: (i) a `Path` subclass (not a monkeypatch of `Path.resolve` globally) for the dual-anchor divergence test — exercises "literal-abs IS in-root, but `.resolve()` target is OUT-of-root" portably on any platform; (ii) a real `os.symlink` test guarded by `@pytest.mark.skipif(os.name == 'nt' and not _has_symlink_priv(), reason="Windows symlinks require admin or developer mode")` for on-disk coverage. Option D (hybrid) is the idiomatic cycle-23 precedent and closes the portability gap.

#### DECIDE

Option D. Hybrid: (i) `class _ResolvingPath(Path)` subclass with overridden `.resolve()` for the divergence-only test (one class defined inside the test file scope, no global monkeypatch leakage); (ii) real `os.symlink` test with `@pytest.mark.skipif` guard.

#### RATIONALE

Cycle-23 precedent + cycle-16 L2/L4 position-divergent pattern + cross-platform portability.

#### CONFIDENCE

HIGH

### Q9 — AC2 test monkeypatch target

#### Analysis

R2 Codex edge case 5 flagged that `compiler.py:9-16` snapshot-imports `PROJECT_ROOT` from `kb.config`, so at function-call time `kb.compile.compiler.PROJECT_ROOT` is the binding read by the dual-anchor check — not `kb.config.PROJECT_ROOT`. Patching only `kb.config.PROJECT_ROOT` is insufficient after import. The existing cycle-23 tests at `test_cycle23_rebuild_indexes.py:90-93` patch BOTH attributes, which is belt-and-suspenders correctness. R2 finding 5 also notes `tmp_kb_env` mirror-rebinds `kb.*` globals that still match original config values, but this mirror loop may not catch every downstream consumer under full-suite orderings.

Option A (compiler only) is MINIMALLY CORRECT — the load-bearing patch for `rebuild_indexes`. Option B (config only + mirror-rebind) is INCORRECT because the snapshot-import is already resolved. Option C (both) matches existing precedent and defends against any future code path that reads `kb.config.PROJECT_ROOT` directly during validation (e.g., a nested helper that imports at call time). Option C is strictly safer; the cost is one extra `monkeypatch.setattr` line per test. Also, requirement's AC2 test examples don't specify the patch target; the plan step must codify option C.

#### DECIDE

Option C. Patch BOTH `kb.compile.compiler.PROJECT_ROOT` AND `kb.config.PROJECT_ROOT` in every AC2 test. Matches `test_cycle23_rebuild_indexes.py:90-93` verbatim.

#### RATIONALE

Cycle-18 L1 snapshot-import lesson + cycle-23 precedent. Compiler patch is load-bearing; config patch is defensive.

#### CONFIDENCE

HIGH

### Q10 — AC2 TOCTOU validation↔unlink window

#### Analysis

R2 Codex edge case 1 raised that `rebuild_indexes` serializes only the manifest unlink through `file_lock`; vector DB and `.tmp` unlinks are unlocked, and AC2 validation fires BEFORE the lock/unlink at `compiler.py:670-690`. A concurrent attacker with write access to the caller's process memory could theoretically mutate the override Path between validation and unlink. The threat-model T2 language describes the defensive containment as closing "a Python-API caller plumbing user-controlled input" — the threat model is about a future CALLER, not about concurrent-mutation after validation.

The options are (A) accept residual TOCTOU, (B) narrow via pre-unlink revalidation, or (C) wrap validation + unlink in a file-lock span. Option B doubles the validation code and closes a window that's not actually in the threat model (a caller able to mutate Path objects in-flight has already compromised the process). Option C adds lock contention for a scenario not in the threat model. Option A is the correct design choice: document explicitly that the containment check defends against a future caller plumbing untrusted input (e.g., a new MCP tool or CLI flag), NOT against in-process attacker-controlled concurrent override edits. This matches the requirement's §"Mitigation in this cycle" language: "apply the identical dual-anchor check... BEFORE `file_lock` acquisition and BEFORE `unlink()`" — the lock order is deliberate.

#### DECIDE

Option A. Accept residual. Add threat-model amendment documenting that `PROJECT_ROOT` containment is a defensive check against a future caller plumbing untrusted input, NOT a security guarantee against concurrent in-process override-edit attacks.

#### RATIONALE

The threat model in §T2 scopes the defence to "a future plugin, MCP tool, or CLI flag that threads user input into these kwargs". Concurrent in-process edits are out of scope — principle of minimum viable guard.

#### CONFIDENCE

HIGH

### Q11 — AC2 None-default validation

#### Analysis

R2 Codex gate question 6 asked whether `None` overrides (default path via `HASH_MANIFEST` and `_vec_db_path(wiki_dir)`) should skip validation. Today `HASH_MANIFEST` is defined in `kb.compile.compiler` as `PROJECT_ROOT / ".data" / "hashes.json"` — always in-root by construction. `_vec_db_path(wiki_dir)` derives from the already-validated `wiki_dir`. Validating defaults is academic: if the defaults drifted to an out-of-root location, that's a config-module bug, not a `rebuild_indexes` bug, and the appropriate fix is in `kb.config` with a cycle of its own.

Option A (skip on None) keeps the validation layer focused on the untrusted-input surface. Option B (validate defaults too) adds 2 `.resolve()` calls per `rebuild_indexes` invocation for zero behavioural improvement today. Option A also matches the requirement's §"Required behavior" explicitly: "None overrides (the default case using HASH_MANIFEST / _vec_db_path(wiki_dir)) skip validation entirely." Option B would change the requirement, which is out of scope for the design gate. Add a test `test_none_override_uses_default_without_validation_drift` (already specified in AC2 test #5) to prove zero extra `Path.resolve()` calls against the defaults.

#### DECIDE

Option A. Skip validation when override is None. Requirement AC2 test #5 already pins this.

#### RATIONALE

Defaults are derived from `PROJECT_ROOT` by construction; validating is academic. Matches requirement-mandated behaviour.

#### CONFIDENCE

HIGH

### Q12 — AC2 existing-test fixture interaction

#### Analysis

R2 Codex finding 4 enumerated existing `rebuild_indexes` test callers: `test_cycle23_rebuild_indexes.py` (7 call sites) and `test_cycle25_rebuild_indexes_tmp.py` (5 call sites). R2 observed that these tests pass `tmp_wiki` (under `tmp_path`, OUTSIDE the real project root) and pass today because `tmp_kb_env` + per-test monkeypatches of `kb.compile.compiler.PROJECT_ROOT` to the tmp root make the validation accept `tmp_wiki`. The concern is that AC2 adds validation to `hash_manifest` and `vector_db` overrides; if any existing test passes an override that's NOT under the per-test-patched PROJECT_ROOT, the new validation would fail the test.

Grep verification (performed in this gate via the R1/R2 reads): `test_cycle23_rebuild_indexes.py:100-104` passes `manifest = tmp_project / ".data" / "hashes.json"` and `vec = tmp_project / ".data" / "vec.db"` — both under the patched `PROJECT_ROOT = tmp_project`. `test_cycle23_rebuild_indexes.py:237-240` same. `test_cycle25_rebuild_indexes_tmp.py:141` passes `vec_db = tmp_project / ".data" / "vec.db"` — same. All existing call sites already place overrides under the patched PROJECT_ROOT. No migration needed. Option A (verify + plan-gate checkpoint) is the right risk-adjusted choice: lock the grep result into a Step-11 CONDITION so a future override pattern that fails the invariant is caught before merge.

#### DECIDE

Option A. Plan-gate CONDITION at Step 9/11: grep `rebuild_indexes(` in `tests/` and verify each call site places overrides under the patched `PROJECT_ROOT`. Verified in this gate via R1/R2 findings. No test-fixture migration required.

#### RATIONALE

Empirical grep confirms no migration needed; lock the invariant as a Step-11 checkpoint.

#### CONFIDENCE

HIGH

### Q13 — AC3 scope expansion: also delete BACKLOG:196-197?

#### Analysis

R1 Opus Q6 flagged this: the BACKLOG entry at `BACKLOG.md:196-197` describes the `config.py:40-53 + CLAUDE.md architectural contradiction` with the stated fix "carve out an explicit exception in CLAUDE.md and the config comment". AC3 delivers the config-comment half; CLAUDE.md already has the carve-out in its `raw/` bullet ("sole LLM-written output directory inside raw/ — atomised via kb_capture, then treated as raw input for subsequent ingest"). So AC3 closes the full fix-prescription of the BACKLOG entry. Leaving the BACKLOG bullet open after shipping the fix creates BACKLOG drift — exactly the problem AC4/AC5 address for other stale entries.

The scope-creep concern is minimal: deleting one BACKLOG bullet is one-line edit + one source-scan test (matching AC4/AC5 pattern). Option A aligns AC3 with the AC4/AC5 delete-on-resolve protocol per BACKLOG lifecycle rule ("Resolved items are DELETED, not strikethrough"). Option B preserves BACKLOG drift for no operational benefit.

#### DECIDE

Option A. Expand AC3 scope: delete BACKLOG.md:196-197 AND add a source-scan regression test `test_captures_backlog_carveout_entry_deleted` asserting `"config.py:40-53"` substring NOT present in BACKLOG. Updated test count: AC3 now adds 2 tests (1 comment-presence + 1 BACKLOG-delete) instead of 1.

#### RATIONALE

BACKLOG lifecycle rule explicit. AC3 closes the full fix-prescription; leaving the bullet creates drift.

#### CONFIDENCE

HIGH

### Q14 — Test file split

#### Analysis

The brainstorm Q10 recommended option B (two files). The rationale is that source-scan tests (`open file, grep substring`) have a different shape than integration tests (`monkeypatch + invoke + assert persisted state`). Mixing shapes in one file muddies the reviewer mental model and couples reload-leak surfaces: if a source-scan test accidentally imports and reloads a `kb.*` module, the subsequent integration test in the same file inherits the leak. Splitting by shape isolates reload leaks to the scan file only (cycle-19 L2).

Option A (one file) has minor convenience (one file to open) but creates real coupling hazards. The file-split also matches the AC-group split: AC1/AC2 are integration (real `rebuild_indexes` invocation, real `wiki/log.md` read, real unlink spy); AC3/AC4/AC5 are source-scan (read `config.py` / `BACKLOG.md` and assert substring presence/absence). Naming matches cycle precedent: `tests/test_cycle29_rebuild_indexes_hardening.py` and `tests/test_cycle29_backlog_hygiene.py`.

#### DECIDE

Option B. Two files: `tests/test_cycle29_rebuild_indexes_hardening.py` (AC1 integration + AC2 integration, including Q3 embedded-newline regression and Q4 CLI-render test) and `tests/test_cycle29_backlog_hygiene.py` (AC3 comment-presence + AC3 BACKLOG-delete + AC4 + AC5 source-scan tests).

#### RATIONALE

Cycle-19 L2 reload-leak isolation + test-shape clarity.

#### CONFIDENCE

HIGH

### Q15 — Test count projection

#### Analysis

Baseline: 2809 full suite. AC1 specifies 3 regression tests. AC2 specifies 5 regression tests. AC3 per Q13 expansion specifies 2 tests (1 comment-presence + 1 BACKLOG-carveout-delete). AC4 specifies 1 BACKLOG-delete test. AC5 specifies 1 BACKLOG-delete test. Q3 embedded-newline regression adds 1 test. Q4 CLI-render test adds 1 test. Total new tests: 3 + 5 + 2 + 1 + 1 + 1 + 1 = 14. Projected full-suite count: 2809 + 14 = 2823.

Correction: the question statement listed 11 new tests + Q3 (+1 = 12) + Q4 (+1 = 13). My breakdown of AC3 expansion (+1 vs question's +1) diverges — Q13 added 1 test (BACKLOG-carveout-delete), making AC3 2 tests instead of 1. So total is 13 + 1 (Q13 expansion) = 14. Projected full-suite: 2823.

#### DECIDE

Projected full-suite count: 2823 (2809 + 14 new tests). Locked as Step-11 verification target via `pytest --collect-only -q | tail -1`.

#### RATIONALE

Mechanical addition. The +1 from Q13 expansion brings the total from the question's 2822 to 2823.

#### CONFIDENCE

HIGH

## CONDITIONS (Step 9 must satisfy)

- **C1** — `_audit_token(block: dict) -> str` helper exists at module scope in `src/kb/compile/compiler.py` with the docstring specified in Q1 (verbatim: `"""Render the audit token for a rebuild_indexes result block. Returns 'cleared' when cleared=True AND error is None, 'cleared (warn: {error})' when cleared=True AND error truthy, or '{error}' otherwise. The error string is passed through verbatim — callers must pre-format compound tokens like 'tmp: <msg>'."""`). Callers at lines 752-756 pass `result["manifest"]` and `result["vector"]` blocks; no inline ternaries remain. Grep verification: `rg -n '_audit_token' src/kb/compile/compiler.py` must show exactly 1 def + 2 callsites.
- **C2** — `_validate_path_under_project_root(path: Path, field_name: str) -> None` helper exists at module scope in `src/kb/compile/compiler.py`. Body contains (in order): (i) `if path == Path(""): raise ValidationError(f"{field_name} must be non-empty")`, (ii) the dual-anchor check, (iii) `except OSError` → `ValidationError(f"{field_name} cannot be resolved: {e}") from e`. Three call sites: `wiki_dir` block (replaces lines 647-656), `hash_manifest` block (new, only when `hash_manifest is not None`), `vector_db` block (new, only when `vector_db is not None`). Grep verification: `rg -n '_validate_path_under_project_root' src/kb/compile/compiler.py` must show exactly 1 def + 3 callsites.
- **C3** — `src/kb/cli.py:550-560` imports `_audit_token` from `kb.compile.compiler` (function-local import inside `rebuild_indexes_cmd` per cycle-23 AC4 boot-lean contract) and uses it for both `manifest_status` and `vector_status`. Grep verification: `rg -n '_audit_token' src/kb/cli.py` must show at least 2 callsites.
- **C4** — All AC2 tests monkeypatch BOTH `kb.compile.compiler.PROJECT_ROOT` AND `kb.config.PROJECT_ROOT`. Grep verification: `rg -n 'kb.compile.compiler.PROJECT_ROOT' tests/test_cycle29_rebuild_indexes_hardening.py` must show AT LEAST 5 hits (one per AC2 test).
- **C5** — All AC2 tests late-bind `ValidationError` via `compiler.ValidationError` (NOT `from kb.errors import ValidationError`), matching `tests/test_cycle23_rebuild_indexes.py:146` pattern. Grep verification: `rg -n 'from kb.errors import ValidationError' tests/test_cycle29_rebuild_indexes_hardening.py` must return zero hits.
- **C6** — Symlink-escape test uses hybrid strategy: (i) a `_ResolvingPath(Path)` subclass defined IN THE TEST FILE for the divergence-only test, AND (ii) a separate test using real `os.symlink` guarded by `@pytest.mark.skipif`. Grep verification: `rg -n 'class _ResolvingPath' tests/test_cycle29_rebuild_indexes_hardening.py` and `rg -n 'os\.symlink' tests/test_cycle29_rebuild_indexes_hardening.py` must each return at least 1 hit.
- **C7** — Test file split honored: `tests/test_cycle29_rebuild_indexes_hardening.py` contains ONLY AC1 + AC2 integration tests (no BACKLOG scans); `tests/test_cycle29_backlog_hygiene.py` contains ONLY AC3 + AC4 + AC5 source-scan tests (no `rebuild_indexes(` invocation). Grep verification: `rg -n 'rebuild_indexes' tests/test_cycle29_backlog_hygiene.py` must return zero hits AND `rg -n 'BACKLOG.md' tests/test_cycle29_rebuild_indexes_hardening.py` must return zero hits.
- **C8** — Step-11 caller-grep checkpoint executed: `rg -n 'rebuild_indexes\(' tests/ | grep -v 'test_cycle29'` produces the 12 existing call sites from `test_cycle23_*.py` + `test_cycle25_*.py`; each visually inspected to confirm overrides (when present) are under `tmp_project` (the patched PROJECT_ROOT). Result documented in commit message.
- **C9** — AC3 comment block above `CAPTURES_DIR = RAW_DIR / "captures"` at `src/kb/config.py:80` contains at least 3 DISTINCT tokens from the set `{LLM-written, carve-out, kb_capture, raw input for subsequent ingest}`. AC3 test uses DISTINCT-token count (not per-line count), disambiguating the requirement's ambiguous language per R1 Opus AMEND.
- **C10** — AC3 scope expansion applied: `BACKLOG.md:196-197` bullet (`config.py:40-53 + CLAUDE.md architectural contradiction`) DELETED. Regression test `test_captures_backlog_carveout_entry_deleted` in `tests/test_cycle29_backlog_hygiene.py` asserts substring `"config.py:40-53"` NOT present in BACKLOG.md.
- **C11** — AC4 regression test uses tighter substring `"_PROMPT_TEMPLATE inline string"` (NOT just `_PROMPT_TEMPLATE`) per R1 Opus AMEND — defends against a future cycle legitimately adding a `_PROMPT_TEMPLATE` reference.
- **C12** — AC5 regression test uses BOTH substrings in the assertion: `"0.81s + 67 MB"` AND `"cold load — measured"`. HIGH-Deferred bullet at `BACKLOG.md:109` explicitly verified to contain NEITHER substring (it uses `"cold-load latency"` which does NOT match).
- **C13** — Full-suite count after Step 9: 2823 (2809 + 14 new tests). Verified via `pytest --collect-only -q | tail -1` per cycle-26 L2 rule.
- **C14** — Renderer purity preserved: `_audit_token` is side-effect-free (no logging, no filesystem, no `append_wiki_log` call). Grep verification: `rg -n '_audit_token' src/kb/compile/compiler.py -A 10` body contains no `append_wiki_log`, no `logger.`, no `open(`.
- **C15** — `OSError`-only catch preserved around `append_wiki_log(...)` at `compiler.py:757-761`. Grep verification: `rg -n 'except OSError' src/kb/compile/compiler.py | wc -l` matches pre-cycle-29 count + any new count added by AC2 helper body.

## FINAL DECIDED DESIGN

### AC1 — `rebuild_indexes` audit status reflects partial clears

**Implementation:**

1. Add module-level helper in `src/kb/compile/compiler.py` (placement: above `rebuild_indexes`, after the module's existing helpers):

```python
def _audit_token(block: dict) -> str:
    """Render the audit token for a rebuild_indexes result block.

    Returns 'cleared' when cleared=True AND error is None,
    'cleared (warn: {error})' when cleared=True AND error truthy,
    or '{error}' otherwise. The error string is passed through
    verbatim — callers must pre-format compound tokens like
    'tmp: <msg>'.
    """
    if block["cleared"]:
        if block["error"]:
            return f"cleared (warn: {block['error']})"
        return "cleared"
    return str(block["error"]) if block["error"] else "unknown"
```

2. Replace `compiler.py:752-756` with:

```python
msg = (
    f"manifest={_audit_token(result['manifest'])} "
    f"vector={_audit_token(result['vector'])} "
    f"caches_cleared={len(result['caches_cleared'])}"
)
```

3. Preserve existing `OSError`-only narrow catch at lines 757-761 (no broadening).

4. Mirror to CLI: in `src/kb/cli.py:rebuild_indexes_cmd` (lines 528-561), replace the inline ternaries at 550-555 with function-local import + `_audit_token` calls:

```python
from kb.compile.compiler import _audit_token  # noqa: PLC0415

manifest_status = _audit_token(result["manifest"])
vector_status = _audit_token(result["vector"])
```

**Tests (in `tests/test_cycle29_rebuild_indexes_hardening.py`):**

- `test_audit_renders_vector_cleared_with_tmp_error` — monkeypatch `Path.unlink` to fail ONLY on `.tmp` path (main vector unlink succeeds); assert `wiki/log.md` last line contains substring `vector=cleared (warn: tmp:` AND the error-message tail. Patch BOTH `kb.compile.compiler.PROJECT_ROOT` and `kb.config.PROJECT_ROOT`.
- `test_audit_renders_vector_cleared_clean_when_no_error` — happy path; assert log line contains `vector=cleared ` (trailing space) with NO `(warn:` substring.
- `test_audit_renders_vector_error_when_main_unlink_fails` — monkeypatch so `vector_path.unlink` raises; assert log line contains the error WITHOUT `cleared`.
- `test_audit_renders_embedded_newline_as_single_line` (Q3) — simulate `OSError("line1\nline2")` on `.tmp` unlink; assert log line contains `line1 line2` (space-joined by `append_wiki_log` sanitizer) and NO raw `\n` between `rebuild-indexes |` prefix and EOL. Use `log_path.read_text(encoding='utf-8').splitlines()[-1]` to isolate the final entry (cycle-24 design §8 "last log entry" rule).
- `test_cli_rebuild_indexes_shows_compound_vector_status` (Q4) — use `click.testing.CliRunner` to invoke `rebuild_indexes_cmd` with monkeypatched `Path.unlink` (tmp fails); assert `result.output` contains `vector=cleared (warn: tmp:`.

Test count delta: **5 tests** (3 base + 1 Q3 + 1 Q4).

### AC2 — `rebuild_indexes` validates `hash_manifest` + `vector_db` overrides under PROJECT_ROOT

**Implementation:**

1. Add module-level helper in `src/kb/compile/compiler.py` (placement: above `rebuild_indexes`):

```python
def _validate_path_under_project_root(path: Path, field_name: str) -> None:
    """Dual-anchor PROJECT_ROOT containment check.

    Raises ValidationError if path fails containment. Void return
    (raises-only) to avoid stub-return-type ambiguity (cycle-23 L2):
    callers MUST NOT assume the path is resolved by this helper —
    use the literal caller-supplied path for downstream unlink.
    """
    if path == Path(""):
        raise ValidationError(f"{field_name} must be non-empty")
    root_resolved = PROJECT_ROOT.resolve()
    if path.is_absolute() and not (
        path == root_resolved or path.is_relative_to(root_resolved)
    ):
        raise ValidationError(f"{field_name} must be inside project root")
    try:
        resolved = path.resolve()
    except OSError as e:
        raise ValidationError(f"{field_name} cannot be resolved: {e}") from e
    if not (resolved == root_resolved or resolved.is_relative_to(root_resolved)):
        raise ValidationError(f"{field_name} must be inside project root")
```

2. Refactor `rebuild_indexes` to call the helper:

   - Replace `compiler.py:637-656` (existing wiki_dir block) with:
     ```python
     effective_wiki = Path(wiki_dir).expanduser() if wiki_dir else WIKI_DIR
     _validate_path_under_project_root(effective_wiki, "wiki_dir")
     ```
   - After line 658 (`manifest_path = hash_manifest or HASH_MANIFEST`), insert:
     ```python
     if hash_manifest is not None:
         _validate_path_under_project_root(Path(hash_manifest), "hash_manifest")
     ```
   - After line 661 (`vector_path = vector_db or _vec_db_path(effective_wiki)`), insert:
     ```python
     if vector_db is not None:
         _validate_path_under_project_root(Path(vector_db), "vector_db")
     ```

3. `None` overrides skip validation (defaults are derived from PROJECT_ROOT by construction — verified in Q11).

**Tests (in `tests/test_cycle29_rebuild_indexes_hardening.py`):**

All tests patch BOTH `kb.compile.compiler.PROJECT_ROOT` and `kb.config.PROJECT_ROOT`; all tests late-bind `ValidationError = compiler.ValidationError` (cycle-20 L1).

- `test_hash_manifest_override_outside_project_raises` — `hash_manifest=Path("C:/Windows/system32/secret.txt")` on Windows (`Path("/etc/passwd")` on POSIX); assert `ValidationError` raised BEFORE any `Path.unlink` call (spy via `unittest.mock.patch.object(Path, 'unlink')`).
- `test_vector_db_override_outside_project_raises` — mirror for `vector_db`.
- `test_hash_manifest_override_symlink_to_outside_raises` — hybrid test strategy:
  - Sub-test (a): use `_ResolvingPath(Path)` subclass (defined inside the test file) that returns an out-of-root resolve target while the literal path looks in-root; assert `ValidationError` (dual-anchor catches the divergence).
  - Sub-test (b): `@pytest.mark.skipif(os.name == 'nt' and not _has_symlink_priv(), reason="Windows symlinks require admin")`; create real `os.symlink(outside_target, <proj>/wiki/.lnk)`; pass `<proj>/wiki/.lnk` as `hash_manifest`; assert `ValidationError`.
- `test_hash_manifest_override_inside_project_succeeds` — pass `proj/.data/custom-hashes.json`; assert no `ValidationError`, manifest unlinked per normal flow.
- `test_none_override_uses_default_without_validation_drift` — pass `hash_manifest=None`, `vector_db=None`; assert defaults used; spy on `Path.resolve` confirms no extra calls beyond the `wiki_dir` validation (backward-compat pin).

Test count delta: **5 tests** (matches requirement AC2 test list; Q8 hybrid splits the symlink test into a sub-test structure but counts as 1 for suite-total purposes).

### AC3 — `config.py` CAPTURES_DIR architectural carve-out comment

**Implementation:**

Add comment block above `src/kb/config.py:80` (`CAPTURES_DIR = RAW_DIR / "captures"`):

```python
# Carve-out from the "LLM never modifies raw/" invariant: raw/captures/
# is the SOLE LLM-written output directory inside raw/. Items are atomised
# via kb_capture (scan-tier LLM extraction) from unstructured text, then
# treated as raw input for subsequent ingest. See CLAUDE.md §raw/ bullet
# for the architectural contract and the Phase 5 pre-merge resolution.
CAPTURES_DIR = RAW_DIR / "captures"
```

**Tests (in `tests/test_cycle29_backlog_hygiene.py`):**

- `test_captures_dir_has_carve_out_comment` — open `src/kb/config.py`, locate `CAPTURES_DIR = RAW_DIR / "captures"` via grep; assert at least 3 DISTINCT tokens from `{LLM-written, carve-out, kb_capture, raw input for subsequent ingest}` appear in the 6 lines above (C9: distinct-token count, disambiguating the requirement per R1 Opus AMEND).
- `test_captures_backlog_carveout_entry_deleted` (Q13 expansion) — open `BACKLOG.md`, assert substring `"config.py:40-53"` NOT present anywhere.

AC3 scope now DELETES `BACKLOG.md:196-197` (Q13 decision).

Test count delta: **2 tests** (1 comment-presence + 1 BACKLOG-delete).

### AC4 — Delete stale `_PROMPT_TEMPLATE` BACKLOG entry

**Implementation:** Delete `BACKLOG.md:193-194` entry (`capture.py:209-238 _PROMPT_TEMPLATE inline string vs templates/ convention`).

**Tests (in `tests/test_cycle29_backlog_hygiene.py`):**

- `test_captures_backlog_entry_deleted` — open `BACKLOG.md`; assert substring `"_PROMPT_TEMPLATE inline string"` (tighter 2-word phrase per R1 Opus AMEND, C11) NOT present.

Test count delta: **1 test**.

### AC5 — Narrow stale Phase 4.5 HIGH #6 cold-load BACKLOG entry

**Implementation:** Delete `BACKLOG.md:95-96` entry entirely. HIGH-Deferred at line 109 survives.

**Tests (in `tests/test_cycle29_backlog_hygiene.py`):**

- `test_cold_load_high_entry_deleted` — open `BACKLOG.md`, assert NO HIGH-level bullet (section-scoped search) contains substring `"0.81s + 67 MB"` OR `"cold load — measured"`. Verified in-gate: HIGH-Deferred at line 109 contains neither (it uses `"cold-load latency"`) — distinct per C12.

Test count delta: **1 test**.

### Test file layout

- `tests/test_cycle29_rebuild_indexes_hardening.py` — AC1 (5 tests) + AC2 (5 tests) = 10 integration tests.
- `tests/test_cycle29_backlog_hygiene.py` — AC3 (2 tests) + AC4 (1) + AC5 (1) = 4 source-scan tests.

Total new tests: 14. Full-suite projection: 2809 + 14 = **2823**.

### Implementation commit plan

1. TASK 1 — AC1 tests → AC1 impl (`_audit_token` helper in `compiler.py` + CLI mirror in `cli.py`) → commit.
2. TASK 2 — AC2 tests → AC2 impl (`_validate_path_under_project_root` helper + 3 callers refactored) → commit.
3. TASK 3 — AC3 test + `config.py` comment + BACKLOG:196-197 deletion + BACKLOG-carveout-delete test → commit.
4. TASK 4 — AC4 + AC5 BACKLOG deletions + their regression tests → commit.
5. Step-12 doc update (`CHANGELOG.md`, `CHANGELOG-history.md`, `CLAUDE.md`, `BACKLOG.md`) → commit.
6. Any R1/R2 fixes → commits.

Target: 4 implementation commits + 1 doc commit + up to 2 review-fix commits = ~5-7 commits.

## AMENDMENTS TO THREAT MODEL

**T2 clarification (Q10 decision):** The dual-anchor `PROJECT_ROOT` containment check on `hash_manifest` and `vector_db` overrides is a DEFENSIVE BOUNDARY against a future Python-API caller plumbing untrusted input (e.g., a new MCP tool accepting user-controlled path kwargs, or a new CLI flag). It is NOT a security guarantee against concurrent in-process attacker-controlled mutation of the override `Path` object between validation and `unlink()` — an attacker with write access to the caller's process memory has already compromised the process and the containment check is out of scope for that threat model. Document this scope in the Step-11 security review section.

**T1 scope (Q3 + Q4 decisions):** AC1 now mirrors the compound rendering to BOTH `wiki/log.md` audit (primary) AND `kb rebuild-indexes` CLI stdout (operator-interactive surface). The invariant "partial clears must not render as `cleared` alone" applies to all user-facing surfaces of the `rebuild_indexes` result dict.

## AMENDMENTS TO REQUIREMENTS

- **AC1 scope expanded (Q3):** Add regression test for embedded-newline sanitizer interaction. New test: `test_audit_renders_embedded_newline_as_single_line`.
- **AC1 scope expanded (Q4):** Mirror compound rendering to `src/kb/cli.py:550-560`. New test: `test_cli_rebuild_indexes_shows_compound_vector_status`. New AC1 test count: 5 (was 3).
- **AC3 scope expanded (Q13):** Delete `BACKLOG.md:196-197` bullet in addition to adding the `config.py` comment. New test: `test_captures_backlog_carveout_entry_deleted`. New AC3 test count: 2 (was 1).
- **AC2 test count (Q15 correction):** 5 tests unchanged; Q8 hybrid subdivides the symlink test into sub-tests but the suite count remains 5.
- **Test-file split (Q14):** Requirement §"Measured commit plan" implies one test file; AMEND to two files per Q14 decision: `tests/test_cycle29_rebuild_indexes_hardening.py` (AC1 + AC2) and `tests/test_cycle29_backlog_hygiene.py` (AC3 + AC4 + AC5).
- **Full-suite projection (Q15):** 2823 (was 2820 in brainstorm Q9).
