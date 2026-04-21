# Cycle 19 PR #33 R1 — Edge-case, Concurrency & Security Review

**Date:** 2026-04-21
**Reviewer:** R1 (Sonnet 4.6 — edge cases, concurrency, security, test gaps)
**Scope:** 8 commits (`81f5b01..d1d6a08`), 5 source files, 7 test files
**Verdict:** APPROVE-WITH-NITS

---

## Vacuous-Test Gate

### T-1c null-byte test (test_cycle19_inject_wikilinks_batch.py)

**Status: PROVES the sanitizer. Not vacuous.**

The test body (`"A\x00deadbeef\x00B"`) sanitizes to `"AdeadbeefB"`, then
matches `"AdeadbeefB literally"` in the host page body and injects
`[[concepts/ab|AdeadbeefB]]`. If `replace("\x00", "")` is removed from
`inject_wikilinks_batch`, the clean_title becomes `"A\x00deadbeef\x00B"`,
the word-boundary regex matches nothing in the host body (which contains
the plain string, not the null-byte form), and `result["concepts/ab"]` is
`[]` — assertion on line 360 fails. The test genuinely fails on revert.

**One NIT**: the comment in the test says "Sanitized title should match
`AdeadbeefB`" but the production title after sanitization is `AdeadbeefB`
(the null bytes are stripped, not their surrounding chars). The body was
written with the exact string `"AdeadbeefB literally"` intentionally. This
is correct but slightly confusing; the comment could clarify that the
null-bytes-only are stripped, not the adjacent chars.

### T-12b dual-write test (test_cycle19_manifest_key_consistency.py)

**Status: PROVES the Phase-1 usage. Partial proof for Phase-2.**

The spy intercepts `_check_and_reserve_manifest` and asserts `reserved_ref
== custom_key`. Phase-2 is checked by asserting `custom_key in
load_manifest(HASH_MANIFEST)` after the call. However: `HASH_MANIFEST`
here is the real project `.data/hashes.json`, NOT the `tmp_kb_env`-scoped
manifest. The `tmp_kb_env` fixture redirects `kb.compile.compiler.HASH_MANIFEST`
to `<tmp>/.data/hashes.json` (cycle-18 D6). The test imports
`HASH_MANIFEST` directly from `kb.compile.compiler` at test collection
time, which — under `tmp_kb_env` — should already point to the tmp path.

**Verify**: `HASH_MANIFEST` is imported at the top of the test body (inside
the function, line 154: `from kb.compile.compiler import HASH_MANIFEST,
load_manifest`), so it reads the currently-patched value from the module.
This is correct. If `manifest_ref = manifest_key if manifest_key is not
None else source_ref` is removed and Phase-2 falls back to `source_ref`,
then `custom_key` would NOT appear in the manifest and assertion at line
195 fails. Test is non-vacuous for Phase-2 as well.

**NIT**: the test imports `HASH_MANIFEST` inside the function (not at
module level), which is correct, but this is not immediately obvious to a
reader. A one-line comment explaining "inside function to get the patched
value from tmp_kb_env" would aid future auditors.

### T-9 KeyboardInterrupt test (test_cycle19_refiner_two_phase.py)

**Status: EXERCISES the post-page-write window. Not vacuous.**

The test patches `save_review_history` such that the first call (pending
write) succeeds and the second call (applied flip) raises
`KeyboardInterrupt`. Looking at `refiner.py` lines 265 and 282-287: the
page write is `atomic_text_write(new_text, page_path)` at line 270, which
is BETWEEN the two `save_review_history` calls. So: pending row written
→ page written → KeyboardInterrupt raised on the flip. The test asserts
that `"New body content"` appears in the page (line 139) AND the history
has `status="pending"`. This correctly exercises the crash window between
Phase-2 page write and Phase-3 flip.

**One genuine concern (NIT level)**: `atomic_text_write` calls an OS-level
temp-file+rename, which is not the crash scenario the test simulates —
`KeyboardInterrupt` in Python falls between save_review_history calls, but
a real process crash (SIGKILL) between rename and the next save would leave
the page written but the flip pending. The test simulates a Python-level
interrupt, not a signal-level crash; this is the best available option in
unit tests and is clearly documented. No action needed.

### T-15a MCP monkeypatch test (test_cycle19_mcp_monkeypatch_migration.py)

**Status: PROVES owner-module call style. Not vacuous — with a caveat.**

The test patches `mcp_core.ingest_pipeline.ingest_source` (line 57), NOT
`kb.ingest.pipeline.ingest_source`. This is subtly correct: it patches the
attribute on the module object held by `mcp_core.ingest_pipeline`, which IS
the same object `kb.mcp.core` calls at `ingest_pipeline.ingest_source(...)`.
If `kb.mcp.core` were reverted to `from kb.ingest.pipeline import
ingest_source` (legacy style), then `mcp_core.ingest_pipeline.ingest_source`
would no longer be the call site — patching the module would not intercept
the local name binding — and `fake.called` would be `False`. Test is
non-vacuous.

**MAJOR concern**: T-15b uses `with patch("kb.query.engine.query_wiki",
fake):` (line 84) rather than `monkeypatch.setattr(mcp_core.query_engine,
"query_wiki", fake)`. The `patch` context manager patches the canonical
module's attribute (`kb.query.engine.query_wiki`). Because
`mcp_core.query_engine` IS the `kb.query.engine` module object, this works
correctly. However T-15a and T-15d use `monkeypatch.setattr(mcp_core.<attr>,
...)` style while T-15b and T-15c use `patch("kb.query.engine.X")`. Mixed
styles work but are inconsistent. Not a bug; NIT.

---

## Concurrency Edges

### inject_wikilinks_batch: file_lock is per-page-path

**Status: Correct. Lock is per-page-path, not global.**

`file_lock(page_path, timeout=_INJECT_LOCK_TIMEOUT)` in
`_process_inject_chunk` (linker.py line 494) uses the individual page path.
Disjoint-page batches — e.g., two concurrent ingest calls on
`entities/alice.md` and `entities/bob.md` — acquire different locks and do
not block each other. The only shared lock is the batch-level try/except;
that is call-stack-level, not a mutex. Concurrency semantics are correct.

### refine_page: history_lock serializes concurrent refines

**Status: Accepted per AC9/T4 design decision. Well-documented.**

`file_lock(resolved_history_path)` at refiner.py line 249 is a single
shared JSON file. Concurrent `refine_page` calls on DIFFERENT pages serialize
under this one lock for the duration of the page-write window (~5ms per
`atomic_text_write`). No deadlock risk in the current call graph (no caller
holds history-lock before asking for page-lock, and page-locks are per-page).
The design doc explicitly accepts this liveness cost and the module docstring
documents it. No action needed.

### manifest_key dual-write: concurrent reservation window

**Status: Not a new race; pre-existing by design.**

Between Phase-1 reservation (`_check_and_reserve_manifest`) and Phase-2
confirmation (`manifest[manifest_ref] = source_hash`), a third concurrent
ingest that calls `_check_and_reserve_manifest` with the same `manifest_ref`
would see the Phase-1-written value (`source_hash`) and return a "duplicate"
signal. This is CORRECT behavior — if the same content is being ingested
concurrently, the second caller should be treated as a duplicate. The Phase-1
reservation is the guard; Phase-2 is idempotent confirmation. No issue.

---

## Boundary Cases

### inject_wikilinks_batch with empty new_pages

**Status: Correct. Returns `{}` immediately (linker.py line 373).**

The `if not new_pages: return {}` guard fires before any I/O or allocation.
No test explicitly covers this (the existing T-7 uses `pages=[]`, not
`new_pages=[]`). This is a trivial fast-path; the guard is obvious in code.

**NIT**: a micro-test for `inject_wikilinks_batch([], wiki_dir=tmp_wiki) ==
{}` would lock in this contract, but it's low priority.

### inject_wikilinks_batch where ALL titles are overlength

**Status: Correct. Returns `{}` via the `if not sanitized_pages: return {}`
guard (linker.py line 397-398).**

After the sanitization loop filters all overlength titles, `sanitized_pages`
is empty, and the function returns `{}` immediately. The existing T-4b only
tests a mixed batch (one short, one long). An all-overlength batch falls into
this path. No crash risk.

### refine_page with history_path=None and wiki_dir=None

**Status: Correct.**

At refiner.py lines 240-245, the resolution chain is:
1. `history_path is not None` → use directly
2. `elif wiki_dir is not None` → derive from wiki_dir parent
3. `else` → fallback to `REVIEW_HISTORY_PATH`

This is correct under the two-phase write; the fallback is the module-level
constant which points to the real `.data/review_history.json`. No regression.

### manifest_key with empty string `""`

**MINOR concern (not a blocker)**: The validation at pipeline.py lines
1015-1021 checks for `".." in manifest_key`, leading `"/"`/`"\\"`,
`"\x00"`, and `len > 512`. An empty string `""` passes all four checks:
`".." not in ""`, `"".startswith(...)` is False, `"\x00" not in ""`, `len("") =
0 <= 512`. An empty manifest_key would be used as `manifest_ref = ""`, and
`manifest[""] = source_hash` is a valid JSON dict entry. On the next ingest
of any source, `manifest.get("")` would return the hash and could
false-positive as a duplicate if the source hash happens to match. In
practice, callers are `compile_wiki` (which derives the key from
`_canonical_rel_path`, never empty) and direct library users. But since the
AC says "opaque string produced by `manifest_key_for`", an empty string
represents a canonicalization failure, not a valid key.

**Suggested fix (NIT)**: Add `or not manifest_key` to the validation
condition: `if manifest_key is not None and (not manifest_key or ".." in
manifest_key or ...)`.

---

## Log Injection Analysis (AC20 / T5)

### Does `_escape_markdown_prefix` neutralize multi-line injection?

**Status: YES, but with a scope caveat.**

At wiki_log.py line 92: `field = field.replace("|", "/").replace("\n", " ")
.replace("\r", " ").replace("\t", " ")`. Newlines (`\n`, `\r`) are collapsed
to spaces BEFORE the leading-marker check. A title `"# Evil\n## SECTION
INJECTION"` becomes `"# Evil ## SECTION INJECTION"` — a single line starting
with `#`, which gets the ZWSP prefix. The final log entry is:
`- 2026-04-21 | inject_wikilinks_batch | injected N link(s): ​#
Evil ## SECTION INJECTION`

This prevents markdown rendering of the injected section. The `## SECTION
INJECTION` substring in the middle of the line does not render as a heading.

**One residual gap (NIT)**: The 100-char cap at pipeline.py line 1410
(`injected_summary = injected_summary[:100] + "..."`) truncates the page-ID
list, not the title text itself. The page IDs passed to `append_wiki_log`
are the WINNING page IDs (e.g., `"entities/alice"`), which are slugified and
safe. The title text never appears directly in the batch log line (only the
count and page IDs). So log injection via malicious titles is blocked at this
call site by the fact that titles are NOT included in the log message.
The T5 threat model is correctly mitigated; no title text reaches
`append_wiki_log` from the batch log line.

---

## Additional Findings

### NIT: T-9 third save_review_history call

The test at line 118-121 raises on the SECOND call. Looking at refiner.py:
Call 1 = pending write (line 265), Call 2 = applied flip after OSError check
(line 282) or success flip (line 287). But wait — there is NO save between
pending write and page write for the success path. For T-9, the page write
succeeds (line 270, no patch on atomic_text_write), and the next
`save_review_history` at line 282-287 (the flip) is call #2. The
`KeyboardInterrupt` fires here. The assertion that the page has `"New body
content"` (line 139) is valid because `atomic_text_write` ran in line 270.
Correct. The OSError path (T-8a) writes the failed-flip on call #2 too (line
272-278). T-9 is correctly targeted.

### NIT: AC18 lint guard skips its own file (correct)

Line 46 of test_cycle19_lint_redundant_patches.py: `if py.name ==
"test_cycle19_lint_redundant_patches.py": continue`. This prevents the self-
reference. Correct.

### NIT: T-13a is a smoke test, not a real divergence test

The Windows tilde short-path test (T-13a) at lines 323-333 only asserts
`Path(os.getcwd()).resolve().exists()`, which does not actually demonstrate
manifest_key_for canonicalization of a tilde-form path. It is labeled as a
"smoke check" in the test comment. This is intentional (as documented in
design.md) — the real platform-neutral divergence is covered by T-13b and
T-13c. No action needed.

---

## Security Findings Summary

| Finding | Severity | File | Suggested fix |
|---------|----------|------|---------------|
| Empty string manifest_key passes validation | NIT | pipeline.py:1015 | Add `or not manifest_key` guard |
| T-12b imports HASH_MANIFEST inside function without comment | NIT | test_cycle19_manifest_key_consistency.py:154 | Add one-line comment |
| T-15b/c use `patch()` while T-15a/d use `monkeypatch` | NIT | test_cycle19_mcp_monkeypatch_migration.py:84 | Unify to one style |

All five threats (T1-T5) from the threat model are implemented and verified.
The security-verify subagent confirmed all grep checks pass. No BLOCKERs or
MAJORs found.

---

## Verdict: APPROVE-WITH-NITS

All 23 production ACs are implemented. The four vacuous-gate revert checks
are non-vacuous. Concurrency semantics are correct and documented. The three
NITs (empty manifest_key validation, test comment clarity, mixed patch
styles) do not block merge. Ship cycle 19.
