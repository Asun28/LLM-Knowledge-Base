I have enough context. I'm noting the deferred-tools and skills reminders but they're not relevant to this Step 5 decision-gate task. Now I'll resolve all 12 questions.

# Cycle 33 — Step 5 Decision Gate (Design)

---

## Q1 — Pre-compute `_sanitize_error_str(write_err, file_path)` once vs compute twice?

**OPTIONS**
- (A) Compute once, bind to a local `sanitized = _sanitize_error_str(write_err, file_path)`, reuse in both the `logger.warning` and the `Error[partial]:` return string.
- (B) Compute twice — call inline in the logger and again inline in the return.

## Analysis

The two call sites are adjacent (5–8 lines apart at `core.py:756-764` and `core.py:875-883`). The helper is pure: same `(exc, path)` inputs always yield the same redacted string. Computing twice is wasted work, but more importantly it creates a **divergence risk** — if a future patch passes `file_path` to one call but forgets to add it to the other, the symmetry the threat model demands (T3 + T5: log line and return string must agree) silently breaks. Cycle-32 lesson L3 is exactly about asymmetric redaction creeping in between paired sites.

R1 Opus already commits to this in concrete next-step (b): "pre-compute `_sanitize_error_str(write_err, file_path)` once per OSError site and reuse for both log + return string." The only counter-argument is microscopic — that a local var adds one line of code. Against that: a single binding documents intent ("this is the redacted form everyone uses"), pins symmetry by construction, and makes a future grep `grep _sanitize_error_str.*write_err` return one hit per site rather than two, which simplifies the Step-11 verification checklist. Blast radius is identical either way; the local-var form is strictly cleaner.

**DECIDE: (A) — Pre-compute once into local `sanitized_err`, reuse for both log + return.**

**RATIONALE.** CLAUDE.md "Two tests before declaring done" #2 says "would a senior engineer say this is overcomplicated?" — computing the same redaction twice with the same args is exactly the kind of duplication a reviewer flags. Cycle-32 lesson L3 (asymmetric-redaction drift) makes the symmetry argument load-bearing. R1 Opus's concrete commitment (b) already locks the design here.

**CONFIDENCE: HIGH.**

---

## Q2 — AC4: Should the RETURN string at `core.py:281` also be upgraded to pass `target` for symmetry?

**OPTIONS**
- (A) Upgrade both — `logger.warning(..., _sanitize_error_str(exc, target))` AND `return f"\n[warn] save_as failed: {_sanitize_error_str(exc, target)}"`.
- (B) Upgrade only the log line at 280; leave 281 as `_sanitize_error_str(exc)` (status quo).

## Analysis

Both Opus (Q2) and Codex (R1-02 MAJOR) flag this as the same defect. The current return string at line 281 calls `_sanitize_error_str(exc)` with no `target` Path — this means it depends ENTIRELY on the regex sweep (`_ABS_PATH_PATTERNS`) to catch any path leak, with no `OSError.filename` substitution happening because `paths` is empty when `target` is not passed. That regex covers Windows drive-letter, UNC long-path, ordinary UNC, and a fixed list of POSIX prefixes — but as Codex R1-01 separately notes, `_rel(Path(fn_str))` slash-normalises filename attributes BEFORE the regex sees them, so a UNC path that gets converted from `\\server\share\foo` to `//server/share/foo` falls through the cracks. Passing `target` upgrades the helper from regex-only to "full path-substitution + filename-attr scan + regex sweep" — a strict superset.

The asymmetry between line 280 (log: raw `exc`) and line 281 (return: regex-only `_sanitize_error_str(exc)`) is exactly threat T5. Fixing only line 280 and leaving line 281 on the weaker regex-only path means we close the log-leak but leave the operator-facing return string on a thinner mitigation than the kb_ingest_content / kb_save_source returns get from AC1/AC2. That's a cross-tool inconsistency: three Error[partial]/[warn] returns from the same family of failure modes, two pass `target`, one doesn't. Future readers will infer "save_as is special" when it isn't. The fix is one keyword arg; blast radius is zero.

**DECIDE: (A) — Upgrade BOTH the log line at 280 AND the return string at 281 to `_sanitize_error_str(exc, target)`.**

**RATIONALE.** Threat T5 (asymmetric redaction) and Codex R1-02 demand symmetric treatment. Cycle-18 AC13 established "exception-attribute scan + regex sweep" as the redaction discipline; passing `target` engages both layers. Same-class peer scan reasoning from R1 Opus puts these three sites in one bucket — they should redact identically.

**CONFIDENCE: HIGH.**

---

## Q3 — AC3 logger.warning shape: pre-formatted single-message vs multi-arg?

**OPTIONS**
- (A) Pre-formatted: `logger.warning("kb_ingest_content partial write to %s: %s; client must retry", _rel(file_path), sanitized_err)` — keep multi-arg, just swap the second `%s` source from `write_err` to the pre-computed `sanitized_err` string.
- (B) Single-message: `msg = f"kb_ingest_content partial write to {_rel(file_path)}: {sanitized_err}; client must retry"; logger.warning("%s", msg)`.

## Analysis

The existing call at `core.py:756-760` is already in multi-arg form (`logger.warning("...%s: %s; ...", _rel(file_path), write_err)`). Option (A) is a one-symbol swap — replace `write_err` with `sanitized_err`. Option (B) requires introducing a new local string variable and changing the log call shape. Both produce identical caplog output text; both test the same way (`caplog.records[0].message` after `record.getMessage()`).

The argument for (B) would be "lazy-formatting with `%s` is a no-op when the var is already a string, so we lose nothing by pre-formatting." The argument against (B) is that lazy logging via multi-arg `%s` is the Python logging-module idiom — handlers can choose not to format if the level is filtered out, and structured-logging extractors (if ever added) can pull `record.args` rather than re-parsing the formatted message. Option (A) preserves that idiom and is a one-line patch; option (B) is a 2-line refactor that throws away the `record.args` structure. Q1 already commits to a `sanitized_err` local — the marginal change in (A) is just swapping which name appears in the existing argument list.

**DECIDE: (A) — Keep multi-arg `logger.warning(..., %s, sanitized_err)` shape; only swap the variable.**

**RATIONALE.** CLAUDE.md "Working Principles" — "would a senior engineer say this is overcomplicated?" Option (B) reformats existing code that doesn't need reformatting; option (A) is the minimal diff that closes the leak. Python logging convention (lazy `%s` formatting) is preserved, which is what `record.args`-based caplog assertions can introspect if a future test ever needs that.

**CONFIDENCE: HIGH.**

---

## Q4 — AC5: `pytest.mark.skipif(sys.platform != "win32")` for Windows-shape OSError, or both fixtures unconditional?

**OPTIONS**
- (A) Both fixtures unconditional on every platform — POSIX OSError tests run on Windows CI, Windows OSError tests run on POSIX CI.
- (B) Skip Windows-shape tests on POSIX (`@pytest.mark.skipif(sys.platform != "win32", ...)`) and POSIX-shape tests on Windows.
- (C) Both unconditional, but use OS-agnostic path strings that exercise the regex (e.g. `"D:\\\\test\\\\fake.md"` is just a string regardless of running platform).

## Analysis

Crucial detail: `OSError(13, "Access is denied", "D:\\Projects\\test\\fake.md")` constructs a python OSError object whose `.filename = "D:\\Projects\\test\\fake.md"` and whose `__str__` returns `"[Errno 13] Access is denied: 'D:\\\\Projects\\\\test\\\\fake.md'"`. The Path/string handling is **purely Python-level** — Python doesn't validate that the third argument is a real path on the running OS. So a "Windows-shape" OSError fixture is just an OSError carrying a Windows-style string; it doesn't need a Windows kernel. The `_sanitize_error_str` helper does string substitution and regex matching on whatever string is in the exception — it doesn't call `os.path.exists` or any platform syscall. Same for "POSIX-shape": `OSError(13, "Permission denied", "/tmp/test/fake.md")` is just an OSError with a POSIX-looking string.

This means option (B) — skipping by platform — would skip half the regression coverage on each CI runner for no good reason. The redaction logic is the same code path on both platforms. Option (C) is essentially what (A) collapses to in practice: both shapes run on all platforms, the path string is just inert text from the helper's perspective. The only real-platform consideration would be if the test mocked `os.fdopen` to raise an OSError that the OS itself constructed, but the threat-model T4 mitigation explicitly mandates a 3-arg manually-constructed OSError, which is platform-agnostic. R1 Opus's "two platforms means both fixtures unconditional" reading aligns with the helper's actual contract.

**DECIDE: (A) — Both fixtures unconditional on every platform. No `skipif`.**

**RATIONALE.** The OSError under test is constructed manually (T4 mitigation), so the "Windows-style" and "POSIX-style" labels refer to the path-string shape carried by the exception, not to OS syscall behaviour. Skipping by platform would halve regression coverage on both CI runners with zero correctness benefit. Cycle-22 L5 ("load-bearing tests must run on every CI invocation") aligns: skipping a redaction regression on the basis of a string format is a false economy.

**CONFIDENCE: HIGH.**

---

## Q5 — AC8 step (b): explicit manifest-write failure simulation OR just NOT call manifest-save?

**OPTIONS**
- (A) Explicit simulation — monkeypatch `kb.compile.compiler.save_hashes` (or whichever manifest-save the ingest path actually calls) to raise OSError between the `_sources.md` write and the manifest write, exercising the full crash path.
- (B) Just NOT call manifest-save — call `_update_sources_mapping` directly twice (no surrounding ingest pipeline), since `_update_sources_mapping` doesn't touch the manifest.
- (C) Hybrid: test `_update_sources_mapping` re-call directly (per AC7's structure), and document in the AC8 docstring that the "crash before manifest-save" scenario is functionally equivalent to "two consecutive direct calls" because `_update_sources_mapping` is a self-contained write.

## Analysis

`_update_sources_mapping` is the unit under test for the idempotency contract. Its signature is `(source_ref, wiki_pages, wiki_dir)` — it does not know about the manifest, does not import the manifest module, and its dedup contract is "if the source-ref is already in the file, no-op or merge; otherwise append." Whether the surrounding ingest pipeline did or did not save a manifest after the first call is **invisible to the function**. The crash-recovery semantic that matters for AC8 is: the FILESYSTEM STATE of `_sources.md` after the second call must be identical to the state after the first (for the no-new-pages case) or merged (for the added-pages case). Calling `_update_sources_mapping(...)` twice in a row, with the manifest never touched, produces exactly the filesystem state a real crash-then-re-ingest would produce. Adding a manifest-save mock adds noise without exercising any new code path.

Option (A) would be appropriate if the dedup contract somehow depended on manifest state (it doesn't — line 777 reads `_sources.md` content directly), or if the threat model named a manifest-related failure mode (it doesn't — T7/T8 are about index-file dedup and merge-branch). Option (C) is what the test implicitly does anyway, but the docstring framing helps a future reader understand WHY the test doesn't simulate manifest failure. Option (B) is the cleanest implementation; a one-line comment in the test ("manifest never updated → equivalent to crash before manifest-save") closes the documentation gap.

**DECIDE: (B) — Call `_update_sources_mapping` twice directly without invoking manifest save; add a one-line test docstring noting "second call simulates re-ingest after a crash that aborted before manifest-save (manifest is not consulted by `_update_sources_mapping`)."**

**RATIONALE.** CLAUDE.md "Goal-Driven Execution" — the goal is "pin the dedup-on-recall behaviour", and the unit under test is one function that is manifest-agnostic. Cycle-19 lesson on signature-only tests applies inversely here: the test must exercise the production code path, but must not invent additional state machinery (manifest mock) that the function doesn't read. Test what the function actually does, with documentation of the equivalence.

**CONFIDENCE: HIGH.**

---

## Q6 — Test file naming convention `tests/test_cycle33_*.py`?

**OPTIONS**
- (A) `test_cycle33_mcp_core_path_leak.py` + `test_cycle33_ingest_index_idempotency.py` — cycle-prefixed, matching cycles 19/20/22/24/27/30/31/32 precedent.
- (B) Drop the cycle prefix — `test_mcp_core_path_leak.py` + `test_ingest_index_idempotency.py`.

## Analysis

CLAUDE.md §Testing explicitly states: "New tests per cycle go in versioned files (e.g. `test_cycle20_errors_taxonomy.py`)." This is a settled convention. The `test_cycle19_lint_redundant_patches.py` file is even AST-scanned for fixture-rule enforcement, which is a meta-signal that cycle-prefix is load-bearing for the test infrastructure. The latest cycle (32) ships `test_cycle32_*.py` files per `CHANGELOG-history.md`. Dropping the prefix would be a unilateral break with established convention for no benefit.

The counter-argument might be "tests should be organised by feature, not cycle" — but the project has chosen cycle-organisation deliberately, and changing that mid-stream would create inconsistency. The cycle-prefix gives every test file a unique-by-construction filename, makes per-cycle revert workflows trivial (`git revert tests/test_cycle33_*.py`), and matches the cycle-32 just-shipped lesson on `test_cycle32_file_lock_stagger.py` being added by R1 Codex MAJOR 2.

**DECIDE: (A) — Use `tests/test_cycle33_mcp_core_path_leak.py` and `tests/test_cycle33_ingest_index_idempotency.py`.**

**RATIONALE.** CLAUDE.md §Testing explicitly mandates `test_cycleNN_*.py` naming. Established convention across cycles 19-32 with no reason to deviate.

**CONFIDENCE: HIGH.**

---

## Q7 — AC3 caplog `propagate=True` for `kb.mcp.core` logger?

**OPTIONS**
- (A) Verify with `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` at the top of every redaction test — pytest's `LogCaptureHandler` is attached at this level explicitly.
- (B) Rely on default propagation — `caplog` defaults attach to the root logger, and `kb.mcp.core` logger does not set `propagate=False` anywhere.
- (C) Both — set explicit logger level AND verify by grep that `kb.mcp.core` does not disable propagation.

## Analysis

The threat model T10 explicitly names this: "caplog-handler attachment asymmetry under pytest-xdist." Without `caplog.set_level(logging.WARNING, logger="kb.mcp.core")`, two failure modes are possible: (1) some other test in the suite reduces propagation or attaches a non-pytest handler that swallows the record before caplog sees it; (2) the logger's effective level is WARNING by default, but if any prior test left it at ERROR via `logging.getLogger("kb.mcp.core").setLevel(logging.ERROR)`, the WARNING never propagates. Option (B) leaves both holes open. Option (A) is the standard pytest pattern recommended for any `caplog`-based assertion that targets a named logger.

Option (C) adds a grep verification step ("`logger.propagate = False` is not set anywhere in `kb.mcp`") — but searching the codebase to confirm propagation isn't disabled is verification work that belongs in Step 11, not in test setup. The test itself should be self-contained and explicit. Setting the level on the named logger is also defence against pytest-xdist test ordering: each worker gets its own process state, and if test ordering puts a logger-mutation test before this one, our test inherits the mutation. Explicit `caplog.set_level` on the named logger isolates us from that.

**DECIDE: (A) — Mandate `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` at the top of every AC3/AC4 redaction test.**

**RATIONALE.** Threat T10 explicitly mitigated; pytest-xdist isolation discipline; cycle-32 L3 (test-state hygiene under parallel execution). R1 Opus's concrete commitment (d) already names this requirement.

**CONFIDENCE: HIGH.**

---

## Q8 — AC5: Add UNC + long-path + UNC-long-path test fixtures?

**OPTIONS**
- (A) Add three additional fixture cases — `"\\\\server\\share\\secret.md"` (ordinary UNC), `"\\\\?\\C:\\test\\fake.md"` (long-path), `"\\\\?\\UNC\\server\\share\\test\\fake.md"` (UNC long-path) — for AC1/AC2 returns AND AC3/AC4 logs.
- (B) Drop these out-of-scope; document in AC docstring as known-limited coverage.
- (C) Add only the long-path form (`"\\\\?\\C:\\..."`) since that's the most common Windows behaviour; defer UNC and UNC-long-path.
- (D) Add all three but test against `sanitize_error_text` directly as unit tests (without the MCP integration plumbing) — narrower fixture, tests the helper's regex coverage.

## Analysis

Codex R1-01 raises a real concern: `_rel(Path(fn_str))` at `sanitize.py:30-31` slash-normalises (replaces `\\` with `/`) BEFORE returning. For an OSError whose `filename` is `"\\?\C:\\Projects\\foo.md"` (a long-path that's outside `PROJECT_ROOT` or fails `relative_to`), the helper hits the `ValueError` branch at line 30, then `str(path).replace("\\", "/")` returns `"//?/C:/Projects/foo.md"` — and the `_ABS_PATH_PATTERNS` regex at sanitize.py:13-17 only matches the BACKSLASH-form of long-path/UNC. So the substitution at line 74 in `sanitize_error_text` would then look for `"\\?\C:\\Projects\\foo.md"` in the error string but find `"//?/C:/Projects/foo.md"` after `_rel` — no match, original path stays. Then the final regex sweep at line 81 (`sanitize_text`) would scan the string but its UNC patterns expect backslashes, so nothing matches. The path leaks.

That said, this is a sanitizer-helper bug, and the cycle-33 scope explicitly says "out of scope" for production code changes to `sanitize.py`. Three options: defer entirely (B — accept the residual risk), add tests that document the gap as known-failing (a `pytest.xfail` is misleading because the test would fail under revert too — it's not a regression for cycle 33's production fix), or write the tests as ASSERTIONS that the helper handles these shapes (which it currently doesn't, so the tests would fail). Option (D) — add unit tests against `sanitize_error_text` directly with these three shapes — is the cleanest way to surface the gap: if it currently fails, we have a documented test that demonstrates the bug, and we file a BACKLOG entry instead of deleting the BACKLOG path-leak entry per Q12.

But this expands cycle-33 scope significantly. The original scope is "five line swaps + docstrings + ~70-100 LOC test code." Adding three new path shapes per AC1/AC2/AC3/AC4 = 12 new test cases, plus 3 unit tests against `sanitize_error_text`, plus likely a `sanitize.py` fix to make them pass = scope creep into a cycle-34 candidate. Codex's "out of scope" wording in R1-01's mitigation column ("either fix sanitize.py (out of scope) or test that the existing helper handles these (defensive)") leaves room for the test-only path. Compromise: add ONE unit test in `tests/test_cycle33_mcp_core_path_leak.py` that exercises the long-path filename attribute against `sanitize_error_text`, document in BACKLOG that UNC/UNC-long-path forms remain partially uncovered, and gate AC9 deletion on that residual entry being filed.

**DECIDE: (D-narrowed) — Add ONE parametrised unit test in `tests/test_cycle33_mcp_core_path_leak.py` against `sanitize_error_text` directly with the three Windows long-path/UNC shapes carrying the path in `filename=` arg. If the test fails on current `sanitize.py`, mark with `pytest.mark.xfail(reason="sanitize.py UNC/long-path slash-normalization bug — see BACKLOG cycle-34 candidate", strict=True)` so reverting the cycle-33 fix doesn't accidentally turn xfail into pass. File a NEW BACKLOG entry under MEDIUM: "`sanitize.py` UNC/long-path filename attribute not redacted after slash-normalize" with the exact reproduction shapes. This documents the gap, doesn't expand cycle-33 scope, and lets Q12 keep AC9 lifecycle deletion clean (the entry being deleted is the kb/core.py path-leak entry, not the new sanitize.py entry).**

**RATIONALE.** Codex R1-01 names a real cross-platform leak shape that the cycle-33 fix doesn't fully cover. CLAUDE.md "Working Principles — Think Before Coding" — "if a simpler approach exists, say so" applies inversely: don't pretend the bug doesn't exist. Cycle-32 lesson on documenting residual risk via BACKLOG entries (rather than silently shipping incomplete coverage) maps directly. xfail-strict pins the gap as a known-failing regression target without polluting the suite with red.

**CONFIDENCE: MEDIUM.** (Reduced from HIGH because the xfail strategy depends on the test correctly demonstrating the helper bug; if the helper actually does handle these via some path I missed, the test should be a regular passing assertion. Step 9 should verify by writing the test FIRST and observing pass/fail.)

---

## Q9 — AC5 fixture: monkeypatch `SOURCE_TYPE_DIRS` vs `tmp_kb_env` vs `tmp_path` already?

**OPTIONS**
- (A) Use the `tmp_kb_env` fixture which redirects SOURCE_TYPE_DIRS root paths to a tmp tree.
- (B) Explicit `monkeypatch.setattr(kb.mcp.core.SOURCE_TYPE_DIRS, ...)` to a tmp raw tree.
- (C) Pass a `file_path` argument that's already inside `tmp_path` — don't redirect, just construct the right path string.
- (D) Combine `tmp_kb_env` + assertion that `file_path` resolves under the tmp tree.

## Analysis

Codex R1-04 names the real risk: `kb_ingest_content` at `core.py:685-698` and `kb_save_source` at `core.py:816-847` execute `type_dir.mkdir(parents=True, exist_ok=True)` BEFORE the failure point. `type_dir` resolves from `SOURCE_TYPE_DIRS[source_type]`, which by default points at `<PROJECT_ROOT>/raw/articles`. Without redirection, an AC5 test that mocks `os.fdopen` to raise OSError will: (1) successfully create a directory under real `raw/articles/`; (2) attempt to open the file; (3) hit the mocked OSError; (4) try to `file_path.unlink(missing_ok=True)` (which may or may not work depending on whether the open even reached file creation). Even with `unlink`, the directory creation persists.

Option (C) doesn't help — `file_path` is computed inside the function from `SOURCE_TYPE_DIRS`, not passed in. We can't change where the test writes by passing a different `file_path` because the MCP tool computes the path itself from `slug` + `SOURCE_TYPE_DIRS`. Option (B) is direct but requires knowing the SOURCE_TYPE_DIRS shape (it's a dict of `{source_type: Path}`). Option (A) is the project-blessed fixture per CLAUDE.md fixture rules: "Writing tests: use `tmp_wiki` / `tmp_project` / `tmp_kb_env` only — never touch the real `wiki/` or `raw/`." `tmp_kb_env` already redirects HASH_MANIFEST and (per the project conventions) the raw tree. Option (D) adds a defence-in-depth assertion (`assert tmp_path in file_path.parents`) which catches a fixture regression where the redirection silently breaks.

The fixture rule from CLAUDE.md is unambiguous: never touch real `raw/`. Even with the OSError mock, side effects like directory creation are real-disk mutations that violate cycle-19's AST-scan contract. This is non-negotiable.

**DECIDE: (D) — Use `tmp_kb_env` fixture (per CLAUDE.md fixture rule), AND add an explicit assertion in the test that `file_path` resolves under the tmp_path subtree to catch fixture regression. Also explicitly `monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", {...tmp paths...})` if `tmp_kb_env` does not already redirect SOURCE_TYPE_DIRS — Step 9 checks fixture content first.**

**RATIONALE.** CLAUDE.md fixture rules forbid writes to real `raw/` directly; `tmp_kb_env` is the project-blessed fixture for this exact case. Codex R1-04's mitigation explicitly names it as the right fix. Cycle-19 AST-scan enforcement means a test that pollutes real `raw/` would be caught by CI anyway, so we may as well do it right the first time. Defence-in-depth assertion is cycle-22 L5 standard.

**CONFIDENCE: HIGH.**

---

## Q10 — Cycle-33 scope: wrap `_update_sources_mapping` + `_update_index_batch` in `file_lock` to fix RMW concurrency?

**OPTIONS**
- (A) Wrap each in `file_lock(target_file)` for full concurrency safety.
- (B) Document non-concurrent semantics in AC6 docstring + file/keep BACKLOG entry for the concurrency fix; close cycle-33 scope at re-entrant idempotency only.
- (C) Wrap only one of them (whichever has higher contention probability).

## Analysis

The current cycle-33 scope is unambiguous in `requirements.md` non-goals: "NOT modifying production code in `_update_sources_mapping` / `_update_index_batch` semantics — only docstrings + tests." Wrapping these in `file_lock` IS a production-code semantic change. It would: (1) introduce a new lock-ordering invariant (cycle-32 R1 already shipped one for stagger-counter handling); (2) potentially deadlock if any caller already holds an outer lock on the index/sources file; (3) change the failure mode from "racing writes corrupt the file" to "blocked writes timeout and emit `StorageError(kind=...)`"; (4) require tests for the new lock contention behaviour, not just dedup; (5) interact with the existing `_write_index_files` helper at `pipeline.py:838-862`, which has its own per-call try/except that would now wrap a lock acquire.

The scope-expansion case is real (R1-06 names it) but the BACKLOG fix-recipe says the right design is an `IndexWriter` abstraction wrapping all four index-file writes (`_sources.md`, `index.md`, `_categories.md`, `log.md`) with a documented order. Adding ad-hoc locks to two of those four writes would partially close one symptom while leaving the other two undefended — and would create exactly the kind of "now `_sources.md` and `index.md` are locked, but `_categories.md` and `log.md` are still racing" inconsistency that the IndexWriter design is meant to avoid. The right cycle-33 move is: keep `IndexWriter` deferred (cycle-34/35 candidate per the existing BACKLOG), and either (1) keep the existing BACKLOG entry alive (replacing AC10's deletion with a NARROWING that says "duplication-on-recall is now pinned by tests; concurrency racing is still open") OR (2) accept the residual risk and document it in the docstring.

Option (A) breaks cycle-33's stated scope, ships a partial fix, and risks shipping a deadlock. Option (C) is even worse — asymmetric locking is harder to reason about than no locking. Option (B) is what the design says and what R1-06's mitigation second clause names as acceptable: "OR document AC6 as crash-reingest-only / explicitly non-concurrent + file a BACKLOG item."

**DECIDE: (B) — Keep production-code semantics unchanged. Strengthen AC6 docstring to state "Idempotency holds for serial re-calls (e.g., re-ingest after crash). Concurrent calls without external synchronisation may race — see BACKLOG entry for IndexWriter abstraction." File explicit BACKLOG entry "`pipeline._update_sources_mapping` / `_update_index_batch` lack RMW lock — concurrent ingest races." Modify Q12 plan: AC10 deletion is REPLACED by a narrowed BACKLOG entry covering the concurrency residual.**

**RATIONALE.** CLAUDE.md "Working Principles" — "If a simpler approach exists, say so. Push back when warranted." Cycle 33 was scoped to docstring-and-test; expanding to production code change requires its own design cycle for the IndexWriter abstraction. Cycle-32 lesson L1-L3 (scope discipline, stagger-counter complexity) reinforces: don't ship partial concurrency fixes.

**CONFIDENCE: HIGH.**

---

## Q11 — AC7/AC8: add `atomic_text_write` spy + `call_count == 0` assertion on second identical call?

**OPTIONS**
- (A) Add the spy — `monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)` and assert `spy.call_count == 1` after two identical calls (only the first wrote).
- (B) Skip the spy — assert only on final file content (status quo design).
- (C) Add the spy ONLY for the no-merge case (AC7 step c), not for the merge case (AC8 step e) which DOES write.

## Analysis

Codex R1-07 names the real risk: AC7 asserts "_sources.md contains exactly ONE line referencing raw/articles/x.md (no duplicates)" — that's about FINAL FILE STATE. A future refactor that, say, reads + re-sorts + re-writes the file even when the content is identical would still produce a one-line file with no duplicates and PASS the test. But the docstring contract being added in AC6 says "second call is a no-op for already-present entries" — explicit no-op semantics. Final-state assertions don't pin no-op semantics; they pin no-duplicate semantics, which is a strict subset.

The behavioural pinning Codex asks for (`atomic_text_write` call_count) is the correct way to prove no-op-ness. It's also straightforward: `monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", call_counter_wrapper)`. If the function is supposed to early-return without writing, the spy will see exactly 1 call (first invocation). Cycle-19 lesson is that signature-only / final-state-only tests pass after revert; the spy makes the test exercise the actual short-circuit code path at `pipeline.py:777-779` (where the early-`return` happens after the dedup check).

The merge case (AC8 step e — adding new pages) DOES write a second time, so the spy assertion changes: `spy.call_count == 2` for that case. Option (C) sidesteps that complexity but the merge case is well-served by a `call_count == 2` assertion (matches the docstring contract that merge-on-new-pages writes a second time). Adding the spy uniformly with case-specific call counts is cleanest. Cost: ~3 lines of test code per case.

**DECIDE: (A) — Add `atomic_text_write` spy with case-specific assertions: AC7 dedup case = `spy.call_count == 1`; AC8 no-new-pages case = `spy.call_count == 1`; AC8 merge-on-new-pages case = `spy.call_count == 2`. This pins the docstring no-op contract behaviourally, not just by final state.**

**RATIONALE.** Cycle-19 L4 (signature-only tests pass after revert) and feedback `feedback_test_behavior_over_signature.md` (regression tests must exercise the production code path). Codex R1-07's mitigation is the textbook fix. Spy adds three lines, prevents an entire class of refactor regressions.

**CONFIDENCE: HIGH.**

---

## Q12 — AC9/AC10: gate BACKLOG deletion on R1-01/R1-04/R1-06/R1-07 fixes, OR replace with narrower residual items?

**OPTIONS**
- (A) Gate AC9/AC10 deletion on ALL R1-01/R1-04/R1-06/R1-07 mitigations landing in cycle 33.
- (B) Replace AC9/AC10 deletions with NARROWING — keep the BACKLOG entries alive but rewritten to describe the residual unfixed surface.
- (C) Hybrid: AC9 stays as deletion (path-leak entry is fully closed by the cycle's fixes given Q1-Q4 + Q8-Q9 decisions); AC10 narrowed to a residual concurrency entry per Q10 decision.

## Analysis

Per the decisions above:
- **Q2** elevates AC4 to fix the return string too — eliminates R1-02 residual. AC9 deletion target (`mcp/core.py:762,881` MEDIUM entry) is fully closed for the LEAK path.
- **Q8** documents the UNC/long-path gap as a NEW BACKLOG entry (under sanitize.py, not under mcp/core.py:762,881). The original entry being deleted is exactly the path-leak in `Error[partial]:`, which IS closed; the new entry is for sanitize.py helper — separate concern.
- **Q9** addresses R1-04 fixture pollution in tests, not in BACKLOG. No residual.
- **Q10** rewrites AC10 — the dedup-on-reingest contract IS pinned, but the concurrency-RMW concern is OPEN. AC10's BACKLOG deletion is not appropriate; it must be REPLACED by a narrowed entry for the concurrency surface.
- **Q11** tightens AC7/AC8 behavioural coverage — supports Q10's narrowing because the test now proves the dedup contract (which is what BACKLOG referred to as "duplicate entries on re-ingest").

So the net answer is hybrid: AC9 deletion stays (path-leak symptoms fully closed for the named sites; sanitize.py UNC gap is a NEW separate BACKLOG entry from Q8). AC10 deletion is REPLACED by a narrowing that converts the existing BACKLOG entry from "crash-then-re-ingest can duplicate" to "concurrent ingest can race index-file RMW writes (IndexWriter abstraction deferred to cycle 34+)."

**DECIDE: (C) — AC9 stays as DELETE (the cited entry's failure mode `mcp/core.py:762,881` raw OSError interpolation IS closed by Q1+Q2+Q3+Q4+Q8 fixes for the named sites; a new BACKLOG entry is FILED for the sanitize.py UNC/long-path helper gap surfaced by Q8). AC10 is REPLACED — keep the BACKLOG `ingest/pipeline.py` entry alive but REWRITE to describe ONLY the residual concurrency surface ("concurrent ingest RMW races on `_sources.md` / `index.md`; serial re-ingest dedup contract is now pinned by cycle-33 tests"). Both changes documented in the cycle-33 CHANGELOG entry as "lifecycle: closed `mcp/core.py:762,881` leak; opened `sanitize.py` UNC long-path; narrowed `ingest/pipeline.py` index-file entry to concurrency-only."**

**RATIONALE.** CLAUDE.md "BACKLOG.md lifecycle" rule says delete-on-close, but only when the failure mode is closed. The mcp/core.py leak entry's named failure mode IS closed; the sanitize.py UNC residual is a SEPARATE failure mode that legitimately deserves its own entry. The pipeline.py entry's named failure mode (crash-reingest dup) IS closed; the concurrency residual is partial — narrowing is honest. Cycle-32 lesson on narrowing-vs-deleting (cycle 32 showed a similar pattern with the "category (b) parity" deletion).

**CONFIDENCE: HIGH.**

---

## MINOR findings (R1-03, R1-05, R1-08, R1-09, R1-10, R1-11)

- **R1-03 (single OSError shape).** **DECISION: IN-CYCLE (narrowed).** Add ONE parametrised `sanitize_error_text` unit test in `tests/test_cycle33_mcp_core_path_leak.py` covering: 3-arg form (already in AC5), `filename=None`, no-`filename` attribute, `filename2` attr (Windows MoveFile-style), and path text in `args[1]` only. Five parametrize cases, ~20 LOC. Closes the false-positive-pass risk that AC5's single shape leaves open. **Rationale:** the helper is the load-bearing redaction primitive; covering its OSError-attribute shapes here is defensive AND cheap.

- **R1-05 (caplog xdist pollution).** **DECISION: IN-CYCLE.** Already covered by Q7 decision (`caplog.set_level` named-logger filter). Also add a slug-unique substring (`"cycle33-redact-fixture-A1B2"`) to test fixture filenames so cross-test pollution becomes detectable in caplog assertions. **Rationale:** zero-cost defence, names threat T10 directly.

- **R1-08 (`wiki_pages=[]` empty list).** **DECISION: DEFER-TO-BACKLOG.** Empty-list behaviour ("source-mapping line with no page refs") is a separate semantic question that needs a design call (should we emit the line? skip it? error?). File a BACKLOG MINOR entry. Cycle 33 stays focused on dedup contract. **Rationale:** scope discipline; semantic ambiguity needs design not test.

- **R1-09 (`_sources.md` missing-file early-out).** **DECISION: IN-CYCLE.** Add ONE test that calls `_update_sources_mapping` against a non-existent `_sources.md` and asserts `logger.warning` matches the existing `pipeline.py:774` message + `_sources.md` is NOT created. ~10 LOC. **Rationale:** the missing-file path IS in scope (it's part of the function's contract) and the test pins existing behaviour cheaply. Sets us up for the Q10 IndexWriter design later.

- **R1-10 (backtick in `source_ref`).** **DECISION: DEFER-TO-BACKLOG.** R1-10's own assessment is "low risk for normal slugified MCP inputs." Slugified source_refs cannot contain backticks (slugify's character set excludes them). File a BACKLOG MINOR entry. **Rationale:** out-of-scope; defensible to defer.

- **R1-11 (filename validation weaker for `kb_ingest_content` / `kb_save_source`).** **DECISION: DEFER-TO-BACKLOG.** This is a separate threat surface (homoglyphs, NUL bytes, CON/NUL Windows reserved names) that cycle-33's path-leak scope doesn't touch. File a BACKLOG MEDIUM entry. **Rationale:** legitimate gap, separate cycle.

---

# VERDICT

**PROCEED with AMENDMENTS to AC4, AC5, AC6, AC7, AC8, AC9, AC10.**

The design is sound at its core — all 12 questions resolve to choices that strengthen rather than rebuild the design. Path-leak fix (AC1-AC5) is approved with two strengthening edits (Q2 fix `_sanitize_error_str(exc, target)` in return string too; Q8 add unit test for sanitize.py UNC/long-path with xfail-strict). Idempotency contract (AC6-AC8) is approved with strengthening (Q10 narrows AC6 docstring; Q11 adds atomic_text_write spy). Lifecycle (AC9-AC10) is approved with the AC10 deletion REPLACED by a narrowed concurrency residual entry per Q10/Q12. Two MINORS go IN-CYCLE (R1-03 OSError-shape unit suite; R1-05 caplog xdist via Q7; R1-09 missing-file path); three DEFER-TO-BACKLOG (R1-08 empty list; R1-10 backtick; R1-11 filename validation hardening).

# DECISIONS

1. **Q1**: Pre-compute `_sanitize_error_str(write_err, file_path)` once into local `sanitized_err`; reuse for log + return.
2. **Q2**: AC4 — upgrade BOTH log line at `core.py:280` AND return string at `core.py:281` to `_sanitize_error_str(exc, target)`.
3. **Q3**: Keep multi-arg `logger.warning(..., %s, sanitized_err)` shape; only swap the variable.
4. **Q4**: Both fixtures unconditional on every platform; no `pytest.mark.skipif`.
5. **Q5**: Direct `_update_sources_mapping` calls without manifest-save mock; one-line test docstring noting "manifest-agnostic by construction."
6. **Q6**: `tests/test_cycle33_mcp_core_path_leak.py` + `tests/test_cycle33_ingest_index_idempotency.py` (cycle-prefix per CLAUDE.md).
7. **Q7**: `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` mandatory at top of every redaction test.
8. **Q8**: ONE parametrised `sanitize_error_text` unit test for 3 Windows long-path/UNC shapes, marked `xfail(strict=True)` if helper currently leaks; FILE new BACKLOG entry "sanitize.py UNC/long-path filename slash-normalize bug."
9. **Q9**: Use `tmp_kb_env` fixture; ALSO add explicit `monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", ...)` if `tmp_kb_env` does not redirect it; assert `file_path` resolves under tmp_path subtree (defence-in-depth per cycle-22 L5).
10. **Q10**: NO production-code lock changes in cycle 33; AC6 docstring strengthens with "concurrent calls may race" disclaimer; concurrency residual filed/kept as BACKLOG entry.
11. **Q11**: Add `atomic_text_write` spy with case-specific call_count assertions (1 for dedup/no-new-pages; 2 for merge-on-new-pages).
12. **Q12**: AC9 deletes the path-leak entry as planned; AC10 REPLACED — keep `ingest/pipeline.py` BACKLOG entry alive but rewritten to describe ONLY the concurrency residual; CHANGELOG names this transition explicitly.

Plus MINORS: R1-03 IN-CYCLE (parametrised unit suite ~20 LOC); R1-05 IN-CYCLE (already covered by Q7); R1-08 DEFER-TO-BACKLOG; R1-09 IN-CYCLE (missing-file test); R1-10 DEFER-TO-BACKLOG; R1-11 DEFER-TO-BACKLOG.

# CONDITIONS — Step 09 must satisfy

These are the cycle-22 L5 load-bearing test/grep mandates derived from the decisions above. Each is NON-OPTIONAL.

**Production-code grep mandates:**
- `grep -n "_sanitize_error_str(write_err, file_path)" src/kb/mcp/core.py` returns EXACTLY 2 matches (lines ~756-760 and ~875-879 OSError blocks, AC1+AC2+AC3).
- `grep -n "_sanitize_error_str(exc, target)" src/kb/mcp/core.py` returns EXACTLY 2 matches (line 280 logger AND line 281 return — Q2 symmetric upgrade).
- `grep -nE "logger\\.warning.*write_err\\)" src/kb/mcp/core.py` returns ZERO matches in the kb_ingest_content / kb_save_source / kb_query.save_as blocks (no raw exception interpolation remains).
- `grep -nE "logger\\.warning.*, exc\\)" src/kb/mcp/core.py` returns ZERO matches in kb_query block (line 280 fixed by Q2).
- `grep -nc "Idempotency" src/kb/ingest/pipeline.py` returns >=2 (one per docstring per AC6).
- `grep -n "concurrent calls may race" src/kb/ingest/pipeline.py` returns >=1 (Q10 docstring strengthen).

**Test mandates:**
- `tests/test_cycle33_mcp_core_path_leak.py` exists, contains `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` in every redaction test (Q7).
- That file contains parametrised tests with at least 5 OSError shapes for `sanitize_error_text` unit coverage (R1-03 IN-CYCLE).
- That file contains at least ONE test for kb_ingest_content (AC1+AC3), ONE for kb_save_source (AC2+AC3), ONE for kb_query.save_as (AC4) — three integration tests minimum.
- That file uses `tmp_kb_env` and asserts `file_path` resolves under `tmp_path` subtree (Q9 defence-in-depth).
- That file marks UNC/long-path tests with `xfail(strict=True, reason=...)` (Q8) — `pytest --runxfail` would catch a fix landing.
- `tests/test_cycle33_ingest_index_idempotency.py` exists, uses `tmp_wiki` fixture, calls `_update_sources_mapping` with `wiki_dir=tmp_wiki` keyword (cycle-19 fixture rule).
- That file monkeypatches `kb.ingest.pipeline.atomic_text_write` with a spy and asserts `call_count == 1` on AC7 dedup case (Q11).
- That file asserts `call_count == 2` on AC8 step (e) merge-on-new-pages case (Q11).
- That file asserts `call_count == 1` on AC8 step (a)+(c) no-new-pages re-call case (Q11).
- That file contains a test for `_sources.md` missing-file early-out at `pipeline.py:773-775` asserting `logger.warning` fires and the file is not created (R1-09).
- Both new test files PASS on `pytest tests/test_cycle33_*.py -v`.

**Revert-fail mandate (cycle-24 L4):**
- `git stash push src/kb/mcp/core.py && python -m pytest tests/test_cycle33_mcp_core_path_leak.py -v` produces AT LEAST 4 failures (one per AC1, AC2, AC3, AC4 site); restore via `git stash pop`.
- `git stash push src/kb/ingest/pipeline.py && python -m pytest tests/test_cycle33_ingest_index_idempotency.py -v` is run for completeness, expecting tests to still pass since pipeline.py is docstring-only — but the spy-based behavioural tests should DETECT a manual `atomic_text_write` removal-of-early-return (manual patch + revert-fail check at Step 11).

**BACKLOG mandates (Q12):**
- `BACKLOG.md` deletes the `mcp/core.py:762,881` MEDIUM entry (AC9).
- `BACKLOG.md` REWRITES the `ingest/pipeline.py` index-file write order entry to describe ONLY the concurrency-RMW residual; keep entry alive (AC10 amended).
- `BACKLOG.md` ADDS new MEDIUM entry "sanitize.py UNC/long-path filename attribute leaks after slash-normalize" with the three Windows path shapes named (Q8).
- `BACKLOG.md` ADDS three MINOR entries: R1-08 (empty wiki_pages list semantics), R1-10 (backtick in source_ref), R1-11 (filename validation hardening for kb_ingest_content / kb_save_source).
- `CHANGELOG.md [Unreleased]` Quick Reference contains a cycle-33 row noting "closed: mcp/core.py:762,881 path-leak; opened: sanitize.py UNC residual; narrowed: pipeline.py to concurrency-only."

**Suite + ruff mandates:**
- Full `python -m pytest -q` is GREEN (target ~2901-2920 tests after additions; cycle 33 expected to add ~12-18 new tests across the two new files).
- `ruff check src/ tests/` and `ruff format --check src/ tests/` clean.
- `dependabot/alerts` baseline diff (Step-2 baseline gate) is empty — no new alerts.

# AC AMENDMENTS

### AC4 — BEFORE → AFTER

**BEFORE:**
> **AC4.** Same-class peer at `core.py:279-281` (kb_query `save_as` write-failure path) — `logger.warning("save_as write failed for slug=%r: %s", slug, exc)` swapped to `_sanitize_error_str(exc, target)` so the captured log line is consistent with the already-sanitised return string at line 281.

**AFTER:**
> **AC4.** Same-class peer at `core.py:279-281` (kb_query `save_as` write-failure path) — BOTH the `logger.warning(..., %s, exc)` at line 280 AND the `return f"\n[warn] save_as failed: {_sanitize_error_str(exc)}"` at line 281 swapped to `_sanitize_error_str(exc, target)`. Reason: the existing return string passes only the exception, not the path, so it depends solely on the regex sweep — passing `target` engages the full exception-attribute scan + regex sweep, matching the redaction depth applied to AC1/AC2 sites. Per Q2 + Codex R1-02, the log-line-only fix would leave the operator-facing return on a thinner mitigation than the kb_ingest_content/kb_save_source return strings receive. PASS = both `caplog` records and the returned string contain neither `D:\\` nor `/tmp/`/`/Users/`/`/home/` literals under a forced-OSError fixture targeting `target`.

### AC5 — BEFORE → AFTER

**BEFORE:**
> **AC5.** Regression tests in a new versioned test file (`tests/test_cycle33_mcp_core_path_leak.py`) cover AC1, AC2, AC3, AC4 with TWO platforms each:
> - (a) Windows-style: monkeypatch `os.fdopen` (or the `f.write` call) to raise `OSError(13, "Access is denied", "D:\\\\Projects\\\\test\\\\fake.md")` and assert returned-string + caplog contain neither `D:\\` nor `D:/Projects/test/fake.md` raw form;
> - (b) POSIX-style: same fixture but with `OSError(13, "Permission denied", "/tmp/test/fake.md")` and assert neither `/tmp/test/fake.md` nor `Permission denied: '/tmp/test/fake.md'` literal appears.
>
> Tests must FAIL when the production fix is reverted (revert-fail check per cycle-24 L4).

**AFTER:**
> **AC5.** Regression tests in a new versioned test file (`tests/test_cycle33_mcp_core_path_leak.py`) cover AC1, AC2, AC3, AC4. Fixture isolation: tests use the `tmp_kb_env` fixture (per CLAUDE.md fixture rule). If `tmp_kb_env` does not redirect `kb.mcp.core.SOURCE_TYPE_DIRS`, tests `monkeypatch.setattr("kb.mcp.core.SOURCE_TYPE_DIRS", {...tmp_path-rooted dict...})` defensively, and assert `file_path` resolves under `tmp_path` before the OSError mock is applied (Q9 defence-in-depth). Caplog setup: every test that asserts on captured warnings calls `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` (Q7 + threat T10).
>
> Each AC1/AC2/AC3/AC4 site gets BOTH path shapes RUN UNCONDITIONALLY ON ALL PLATFORMS (Q4 — the OSError-shape carries the path string but the redaction is platform-agnostic):
> - (a) Windows-style: monkeypatch `os.fdopen` to raise `OSError(13, "Access is denied", "D:\\\\Projects\\\\test\\\\fake.md")`. Assert returned string + caplog text contain NEITHER `D:\\Projects\\test\\fake.md` NOR `D:/Projects/test/fake.md` raw form.
> - (b) POSIX-style: same fixture with `OSError(13, "Permission denied", "/tmp/test/fake.md")`. Assert NEITHER `/tmp/test/fake.md` NOR `Permission denied: '/tmp/test/fake.md'` literal appears.
>
> ADDITIONAL parametrised unit-suite tests (R1-03 IN-CYCLE, ~5 cases, ~20 LOC) against `sanitize_error_text` directly:
> - 3-arg OSError (already covered);
> - `OSError("Access is denied")` (no `filename` attr) — assert original (no-path) string returned unchanged;
> - `OSError(13, "Permission denied", "/home/user/secret.md")` `filename=` only;
> - `OSError(13, "MoveFile failed", "C:\\\\src.md", None, "C:\\\\dst.md")` `filename2=` form;
> - path appears in `args[1]` text only (not in `filename` attr).
>
> ADDITIONAL UNC/long-path xfail-strict tests (Q8 documents helper gap, scope-managed):
> - `OSError(13, "Access is denied", "\\\\?\\C:\\\\Projects\\\\foo.md")` (Windows long-path);
> - `OSError(13, "Access is denied", "\\\\server\\share\\secret.md")` (ordinary UNC);
> - `OSError(13, "Access is denied", "\\\\?\\UNC\\server\\share\\foo.md")` (UNC long-path).
>
> If any of these tests currently fail on the existing `sanitize_error_text` implementation, mark `pytest.mark.xfail(strict=True, reason="sanitize.py UNC/long-path slash-normalize bug — see BACKLOG cycle-34 candidate")`. If they pass, leave as regular assertions.
>
> Tests must FAIL when the production fix is reverted (revert-fail check per cycle-24 L4); xfail-strict tests inverted-fail on revert-as-fix.

### AC6 — BEFORE → AFTER

**BEFORE:**
> **AC6.** Add a `## Idempotency` paragraph to `_update_sources_mapping` and `_update_index_batch` docstrings stating: "Safe to re-call after a crash that aborted the ingest before manifest-save. The first call's effect is preserved; the second call is a no-op for already-present entries (sources: identical-ref + identical-pages, index: same `[[subdir/slug]]` already in section)."

**AFTER:**
> **AC6.** Add a `## Idempotency` paragraph to `_update_sources_mapping` and `_update_index_batch` docstrings stating:
> > "Safe to re-call after a crash that aborted the ingest before manifest-save. The first call's effect is preserved; the second call is a no-op for already-present entries (sources: identical-ref + identical-pages, index: same `[[subdir/slug]]` already in section). **Idempotency holds for serial re-calls only.** Concurrent invocations (e.g. two parallel ingests writing the same source-ref simultaneously) are NOT synchronised — the read-modify-write window is unguarded. See BACKLOG `IndexWriter` abstraction entry for the open concurrency surface."
>
> The strengthened "concurrency disclaimer" sentence is mandatory per Q10 (AC10 narrowing).

### AC7 — BEFORE → AFTER

**BEFORE:**
> **AC7.** Add a regression test in `tests/test_cycle33_ingest_index_idempotency.py` that:
> - (a) seeds an empty `_sources.md` and `index.md` via the `tmp_wiki` fixture;
> - (b) calls `_update_sources_mapping("raw/articles/x.md", ["entities/foo", "concepts/bar"], wiki_dir=tmp_wiki)` twice;
> - (c) asserts `_sources.md` contains exactly ONE line referencing `raw/articles/x.md` (no duplicates);
> - (d) calls `_update_index_batch([("entity", "foo", "Foo Title"), ("concept", "bar", "Bar Title")], wiki_dir=tmp_wiki)` twice;
> - (e) asserts `index.md` contains exactly ONE entry per `[[entities/foo|Foo Title]]` / `[[concepts/bar|Bar Title]]` (no duplicates).

**AFTER:**
> **AC7.** Add a regression test in `tests/test_cycle33_ingest_index_idempotency.py` that:
> - (a) seeds an empty `_sources.md` and `index.md` via the `tmp_wiki` fixture;
> - (b) `monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)` where `spy = mock.MagicMock(wraps=atomic_text_write)` (Q11);
> - (c) calls `_update_sources_mapping("raw/articles/x.md", ["entities/foo", "concepts/bar"], wiki_dir=tmp_wiki)` twice;
> - (d) asserts `_sources.md` contains exactly ONE line referencing `raw/articles/x.md` (no duplicates);
> - (e) **asserts `spy.call_count == 1`** — the second call short-circuits without writing (Q11 behavioural pin per docstring);
> - (f) reset spy; calls `_update_index_batch([("entity", "foo", "Foo Title"), ("concept", "bar", "Bar Title")], wiki_dir=tmp_wiki)` twice;
> - (g) asserts `index.md` contains exactly ONE entry per `[[entities/foo|Foo Title]]` / `[[concepts/bar|Bar Title]]` (no duplicates);
> - (h) **asserts `spy.call_count == 1`** for the index path too;
> - (i) ALSO add a missing-file test (R1-09 IN-CYCLE): seed `tmp_wiki` WITHOUT `_sources.md`, call `_update_sources_mapping(...)`, assert the file is NOT created and `caplog` contains "_sources.md not found — skipping source mapping for ..." matching `pipeline.py:774`.

### AC8 — BEFORE → AFTER

**BEFORE:**
> **AC8.** Crash-recovery scenario test:
> - (a) call `_update_sources_mapping(...)` with a NEW source-ref (write succeeds);
> - (b) simulate manifest-save failure by NOT updating the manifest;
> - (c) call `_update_sources_mapping(...)` again with the SAME source-ref and the SAME pages (full re-ingest after crash);
> - (d) assert `_sources.md` content unchanged after step (c);
> - (e) call `_update_sources_mapping(...)` with the SAME source-ref but ADDED pages (e.g. concept added in re-ingest);
> - (f) assert the existing line is MERGED (not duplicated) and now contains all old + new page IDs.

**AFTER:**
> **AC8.** Crash-recovery scenario test (manifest-agnostic per Q5):
> - (a) `monkeypatch.setattr("kb.ingest.pipeline.atomic_text_write", spy)` (Q11);
> - (b) call `_update_sources_mapping("raw/articles/x.md", ["entities/foo", "concepts/bar"], wiki_dir=tmp_wiki)` (write succeeds);
> - (c) simulate manifest-save failure by NOT updating the manifest — note in test docstring: "second call below is functionally equivalent to a re-ingest after a crash that aborted before manifest-save; `_update_sources_mapping` does not consult the manifest" (Q5);
> - (d) call `_update_sources_mapping(...)` again with the SAME source-ref and the SAME pages (full re-ingest after crash);
> - (e) assert `_sources.md` content unchanged after step (d);
> - (f) **assert `spy.call_count == 1`** (no second write — Q11 no-op contract);
> - (g) call `_update_sources_mapping("raw/articles/x.md", ["entities/foo", "concepts/bar", "concepts/baz"], wiki_dir=tmp_wiki)` with the SAME source-ref but ADDED `concepts/baz`;
> - (h) assert the existing line is MERGED (not duplicated) and now contains all three page IDs;
> - (i) **assert `spy.call_count == 2`** — the merge-on-new-pages case DOES write a second time (Q11 merge-branch contract pin).

### AC9 — BEFORE → AFTER

**BEFORE:**
> **AC9.** After AC1-AC5 ship, DELETE the `mcp/core.py:762,881` MEDIUM entry from `BACKLOG.md` per the lifecycle rule. Add a brief entry to `CHANGELOG.md` `[Unreleased]` Quick Reference and the per-cycle detail to `CHANGELOG-history.md`.

**AFTER:**
> **AC9.** After AC1-AC5 ship:
> - DELETE the `mcp/core.py:762,881` MEDIUM entry from `BACKLOG.md` per lifecycle rule (the cited path-leak failure mode at named sites is fully closed by AC1+AC2+AC3+AC4 — Q12).
> - ADD new MEDIUM BACKLOG entry: "`sanitize.py` UNC/long-path filename attribute leaks after `_rel(Path(fn_str))` slash-normalize — `\\?\C:\...`, `\\server\share\...`, `\\?\UNC\server\share\...`. Three xfail-strict tests in `tests/test_cycle33_mcp_core_path_leak.py` document the gap; helper requires regex pattern union with forward-slash variants OR pre-normalize check before `_rel`" (Q8 spawn entry).
> - Add brief entry to `CHANGELOG.md` `[Unreleased]` Quick Reference: "cycle 33 — closed mcp/core.py:762,881 path-leak via _sanitize_error_str(write_err, file_path) at 4 sites; opened sanitize.py UNC residual; pinned ingest/pipeline.py dedup-on-recall contract by spy + missing-file regression."
> - Add per-cycle detail to `CHANGELOG-history.md`.

### AC10 — BEFORE → AFTER

**BEFORE:**
> **AC10.** After AC6-AC8 ship, DELETE the `ingest/pipeline.py` index-file write order MEDIUM entry from `BACKLOG.md` (the dedup contract is now both implemented AND pinned, which closes the failure mode the entry described). Same CHANGELOG / CHANGELOG-history entries as AC9.

**AFTER:**
> **AC10.** After AC6-AC8 ship:
> - **DO NOT DELETE** the `ingest/pipeline.py` index-file write order BACKLOG entry. Per Q10 + Q12, the entry's NAMED failure mode (crash-then-re-ingest duplication) is closed by AC6+AC7+AC8, but the underlying RMW concurrency surface (parallel ingests racing on the same source-ref) remains unfixed and is explicitly OUT OF SCOPE for cycle 33.
> - REWRITE the BACKLOG entry as: "`ingest/pipeline.py:761-791` `_update_sources_mapping` and `pipeline.py:801-829` `_update_index_batch` perform RMW (read full file → mutate in memory → atomic-write) without holding `file_lock(target_path)`. Concurrent ingests may produce lost-update races even though serial re-calls dedup correctly (cycle 33 pinned the serial contract). Fix-recipe: introduce `IndexWriter` helper (matches existing BACKLOG cycle-34 candidate) wrapping all four index-file writes (`_sources.md`, `index.md`, `_categories.md`, `log.md`) with a documented order and per-file `file_lock`. Until then, callers MUST serialise ingest manually."
> - Same CHANGELOG / CHANGELOG-history entries as AC9, framing this transition explicitly.

# FINAL DECIDED DESIGN — Full revised AC list

(For Step 7 plan input. All amendments above folded in.)

**AC1.** `kb_ingest_content` post-create OSError return at `core.py:761-764` interpolates `{sanitized_err}` (a pre-computed `_sanitize_error_str(write_err, file_path)` local — Q1) in place of raw `{write_err}`. After change, returned string contains neither `D:\\` Windows-drive literal nor `/Users/`/`/home/`/`/tmp/` POSIX-absolute prefix under a forced-OSError fixture.

**AC2.** `kb_save_source` post-create OSError return at `core.py:880-883` — same fix as AC1, same `sanitized_err` local pattern.

**AC3.** Paired `logger.warning(..., %s, write_err)` at `core.py:756-760` and `core.py:875-879` use the same pre-computed `sanitized_err` string instead of raw `write_err`. Multi-arg shape preserved (Q3); only the variable swaps. PASS = `caplog.records` for these lines contains no absolute-path literal under a forced-OSError fixture (with `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` set per Q7).

**AC4** [AMENDED]. `kb_query.save_as` peer at `core.py:279-281`: BOTH the `logger.warning(..., %s, exc)` at line 280 AND the `return f"\n[warn] save_as failed: {_sanitize_error_str(exc)}"` at line 281 swapped to `_sanitize_error_str(exc, target)`. Symmetric redaction depth match for AC1/AC2 sites (Q2, Codex R1-02).

**AC5** [AMENDED]. Regression tests in `tests/test_cycle33_mcp_core_path_leak.py` (cycle-prefix per CLAUDE.md, Q6):
- Use `tmp_kb_env` fixture; defensive `monkeypatch.setattr` on `kb.mcp.core.SOURCE_TYPE_DIRS` to tmp paths if not redirected; assert `file_path` resolves under tmp_path subtree (Q9).
- Every redaction test calls `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` (Q7).
- AC1/AC2/AC3/AC4 each get BOTH Windows-shape (`OSError(13, "Access is denied", "D:\\\\Projects\\\\test\\\\fake.md")`) AND POSIX-shape (`OSError(13, "Permission denied", "/tmp/test/fake.md")`) fixtures, run unconditionally on every platform (Q4). Assert returned-string + caplog contain neither raw path form.
- ADDITIONAL R1-03 IN-CYCLE: 5-case parametrised `sanitize_error_text` unit suite covering 3-arg, no-filename-attr, filename-only, filename2-form, path-in-args[1] OSError shapes.
- ADDITIONAL Q8: 3 xfail-strict tests for Windows long-path / ordinary UNC / UNC long-path filename attributes (xfail if helper currently leaks; regular pass otherwise).
- All tests must FAIL when production fix is reverted (revert-fail check per cycle-24 L4).

**AC6** [AMENDED]. Add `## Idempotency` paragraph to `_update_sources_mapping` and `_update_index_batch` docstrings, INCLUDING explicit "concurrency disclaimer" sentence (Q10): "Idempotency holds for serial re-calls only. Concurrent invocations are NOT synchronised — see BACKLOG `IndexWriter` abstraction entry."

**AC7** [AMENDED]. Regression test in `tests/test_cycle33_ingest_index_idempotency.py` (cycle-prefix per Q6) using `tmp_wiki` fixture:
- Spy `kb.ingest.pipeline.atomic_text_write` with `mock.MagicMock(wraps=atomic_text_write)` (Q11).
- Call `_update_sources_mapping(...)` twice with identical args; assert no duplicate AND `spy.call_count == 1`.
- Same pattern for `_update_index_batch(...)` — assert `call_count == 1` after two identical calls.
- ADD missing-file test (R1-09 IN-CYCLE): seed without `_sources.md`, call `_update_sources_mapping`, assert file not created + caplog matches `pipeline.py:774` warning.

**AC8** [AMENDED]. Crash-recovery scenario test:
- Spy `atomic_text_write` (Q11).
- Step (a)+(b)+(c)+(d): first call writes; second identical call no-op; assert content unchanged AND `spy.call_count == 1` (Q11 no-op pin per docstring).
- Step (e)+(f): third call with ADDED page; assert merge (not duplicate) AND `spy.call_count == 2` (Q11 merge-branch pin).
- One-line test docstring: "manifest never updated → equivalent to crash before manifest-save (function is manifest-agnostic by construction, Q5)."

**AC9** [AMENDED]. After AC1-AC5 ship:
- DELETE `mcp/core.py:762,881` MEDIUM entry from `BACKLOG.md`.
- ADD new MEDIUM `BACKLOG.md` entry for `sanitize.py` UNC/long-path filename slash-normalize gap (Q8 spawn).
- CHANGELOG entry per Q12.

**AC10** [AMENDED]. After AC6-AC8 ship:
- **DO NOT DELETE** `ingest/pipeline.py` BACKLOG entry.
- REWRITE entry to describe ONLY the residual concurrency-RMW surface; refer to existing `IndexWriter` cycle-34 candidate.
- CHANGELOG entry frames the transition (Q10, Q12).

**AC11 (NEW MINOR-side, R1-08/R1-10/R1-11 deferred-to-BACKLOG bookkeeping).** Add three NEW MINOR `BACKLOG.md` entries for the deferred MINOR findings: empty `wiki_pages=[]` semantic ambiguity (R1-08); backtick in `source_ref` low-risk dedup edge case (R1-10); filename validation hardening (homoglyphs, NUL bytes, CON/NUL) for `kb_ingest_content` and `kb_save_source` (R1-11). PASS = three new bullet entries grep-discoverable in `BACKLOG.md`.

---

## Summary

**VERDICT: PROCEED with AMENDMENTS to AC4, AC5, AC6, AC7, AC8, AC9, AC10 + new AC11 bookkeeping.**

Twelve questions resolved; six MINORs categorised (3 IN-CYCLE, 3 DEFER-TO-BACKLOG, 0 DROP). Net cycle-33 production code change remains 5 line-level swaps (4 in mcp/core.py per AC1+AC2+AC3 + 2 in core.py:280/281 per AC4); test code expands from ~70-100 to ~140-180 LOC across two cycle-prefixed test files; lifecycle is hybrid (1 entry deleted, 1 entry rewritten/narrowed, 4 new entries added). All decisions anchor to CLAUDE.md principles, cycle-19/22/24/32 lessons, or named threats from the threat-model doc. No escalation needed.