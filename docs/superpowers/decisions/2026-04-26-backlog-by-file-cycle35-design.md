# Cycle 35 — Step 5 Design Decision Gate

Date: 2026-04-26
Inputs: requirements / threat-model / brainstorm / R1-Opus / R2-Codex evals.
Mode: autonomous (no human gate per `feedback_auto_approve`).

## VERDICT

**PROCEED-WITH-CONDITIONS.** All 13 questions resolved below; 18 ACs proceed (some amended), no ACs dropped, T1b ADDED in-scope (data-driven REPL probe converts to PROACTIVE include given R2 surfaced concrete miss). Lower-blast-radius option chosen everywhere except where R2 evidence (file_lock non-reentrance, URI overmatch, Windows trim aliasing) overrides cost-of-defer.

## DECISIONS

### Q1: AC1 regex form — two-pattern URI-guard + slash-UNC-long-path?
- OPTIONS: A) ship simple `(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)` only; B) ship R2's two-pattern (`(?<!:)` URI-guard + separate `(?://\?/UNC/...)` long-path).
- ## Analysis
  R2 (`r2-codex-eval.md:7-11`) flagged a critical regression: the simple slash-UNC pattern matches `https://host/path` because `://` ends with two slashes followed by host/path. Without `(?<!:)` lookbehind every URL in `wiki/log.md` and lint verdicts becomes `<path>` — a serious false-redact that destroys evidence in MCP `Error[partial]:` strings (cite: `src/kb/utils/sanitize.py:34` `_ABS_PATH_PATTERNS.sub("<path>", s)` is single-pass, so once a URL collides it's gone). Option A's blast radius is HIGH (corrupts every log line containing a URL); Option B's blast radius is LOW (one extra lookbehind + one new alternative).
  
  Reversibility: both options are single-line regex edits, so revert cost is symmetric. Failure mode comparison: Option A fails silently on production logs (no test catches it because cycle 33's xfail tests only assert UNC-redacts-correctly, not URL-stays-intact). Option B's two-pattern shape is well-tested by R2 Q6's recommended URL/comment negatives (Q11 below). Option B is strictly safer; the marginal complexity cost is one Python `(?<!:)` lookbehind that any reviewer reads in 5 seconds.
- DECIDE: **B** — ship R2's two-pattern form (URI-guard + slash-UNC-long-path).
- RATIONALE: URI overmatch is a self-inflicted production data-loss bug; the lookbehind cost is negligible and well-tested.
- CONFIDENCE: HIGH

### Q2: T1b inclusion — close `//?/UNC/...` slash form same-cycle?
- OPTIONS: A) Approach C "data-driven via Step 11 REPL probe"; B) proactive close in Step 9 same-cycle (R2 Q1).
- ## Analysis
  Approach C in `brainstorm.md:51-60` was data-driven precisely because the brainstorm wasn't sure the leak existed. R2 Q1 (`r2-codex-eval.md:7-11`) now provides concrete evidence: the slash-normalized long-path `//?/UNC/server/share/...` is a known shape produced by `_rel(Path(fn_str))` for Windows long-path UNCs and bypasses BOTH current alternatives. The data-driven uncertainty has resolved to "yes, leaks." Deferring to Step 11 REPL would just re-confirm what R2 already confirmed and force a mid-cycle scope add (cycle-23 L3 deferred-promise discipline applies).
  
  Blast radius of including T1b now: one additional alternative `r"|(?://\?/UNC/[^\s'\"]+/[^\s'\"]+(?:/[^\s'\"]*)?)"` in `_ABS_PATH_PATTERNS` (line `src/kb/utils/sanitize.py:11-19`). Plus one positive test. This is symmetric to AC1's diff size. Reversibility identical. Including-now removes the Step-11 REPL coupling and makes the regex the single locus of all-UNC-shape coverage — better cohesion. Decision: bundle.
- DECIDE: **B** — include T1b same-cycle as new AC1b.
- RATIONALE: R2 already confirmed the leak; data-driven uncertainty has resolved; including-now ships one cohesive regex change instead of two.
- CONFIDENCE: HIGH

### Q3: AC12 helper signature — `tuple[str, str | None]` or `str | None`?
- OPTIONS: A) `tuple[str, str | None]` (R2, matches `_validate_save_as_slug` precedent); B) `str | None` (R1, simpler).
- ## Analysis
  R1 (`r1-opus-eval.md:31`) recommended `str | None` for minimum surface. R2 (`r2-codex-eval.md:30-34`) reversed to `tuple[str, str | None]` to match `_validate_save_as_slug`'s existing signature in `src/kb/mcp/core.py:188-217`. The trade-off is whether future callers will benefit from a returned canonical-form string. Looking at `_validate_save_as_slug`'s signature, the first element is the slugified form (canonical), the second is the error message. For `_validate_filename_slug`, the canonical form would be the same input filename (no slug-equality enforced per the helper's looser semantic in AC12 line `requirements.md:42`). So the first element is essentially redundant for the helper's current single caller (`_validate_file_inputs`).
  
  HOWEVER: precedent matching reduces cognitive overhead for reviewers and gives future callers (e.g. a hypothetical CLI `kb capture --filename`) a uniform shape. The marginal complexity is one tuple-unpack at the single call site (`_, err = _validate_filename_slug(filename)`). Public contract preservation (R2 condition #5) is satisfied by both — `_validate_file_inputs` still returns `str | None`. Choosing the precedent-matching tuple form is a senior-engineer-friendly decision (consistency over micro-simplicity) that doesn't violate the "would a senior call this overcomplicated?" test because the existing peer already uses tuples.
- DECIDE: **A** — `tuple[str, str | None]` matching `_validate_save_as_slug`.
- RATIONALE: precedent consistency wins; one-line tuple unpack is trivial overhead and future-proofs additional callers.
- CONFIDENCE: MEDIUM

### Q4: AC12 trailing dot/space rejection?
- OPTIONS: A) REJECT (R2 Q4, Windows trim aliasing); B) ALLOW (R1, out-of-scope).
- ## Analysis
  Windows silently trims trailing dot and space from filenames at the filesystem layer: `foo.md.` becomes `foo.md`, `foo.md ` becomes `foo.md`. This creates an aliasing attack surface: a user can submit `CON.md.` (trailing dot) which slugify might preserve but Windows opens as `CON.md` (reserved device). Or `legitimate.md ` and `legitimate.md` collide on Windows but not POSIX. R2 Q4 (`r2-codex-eval.md:24-28`) flagged this as a Windows-specific defense. R1's "out-of-scope" framing was based on minimal-helper conservatism but did not account for the Windows-reserved-name evasion path.
  
  Blast-radius of rejecting: one `filename.strip() == filename` check; rejects edge inputs that no legitimate user produces (trailing whitespace in a content filename is always a typo). Blast-radius of allowing: enables Windows trim-aliasing attacks AND lets `CON.md.` evade the `_is_windows_reserved` check (which inspects basename without trailing dot). The cost asymmetry strongly favors rejection. This is the same shape as cycle-19's stricter slug-equality enforcement — defense-in-depth at the boundary.
- DECIDE: **A** — REJECT trailing dot/space.
- RATIONALE: Windows trim-aliasing is a concrete evasion path for the Windows-reserved-name check; rejection is one line, allowance is an attack vector.
- CONFIDENCE: HIGH

### Q5: AC12 leading dot / leading dash rejection?
- OPTIONS: A) REJECT (defensive); B) ALLOW (POSIX legitimate).
- ## Analysis
  Leading dot (`.env`, `.gitignore`) is a legitimate POSIX hidden-file convention — these are real filenames the wiki may need to ingest as raw sources (e.g. capturing a `.env.example` content). Leading dash (`-foo`) is unusual but POSIX-legal; rejecting it would surprise CLI users porting filenames from `find` output. The scope of `_validate_filename_slug` per AC12 (`requirements.md:42`) is explicitly: "Windows-reserved-name + homoglyph + NUL-byte + path-separator + length checks." Leading dot/dash are NEITHER Windows-reserved NOR homoglyph NOR NUL NOR path-separator NOR length — they fall outside the helper's stated remit.
  
  Adding leading-dot/dash rejection would be scope creep against the requirements doc. R2 did not flag this; R1 explicitly classified it as out-of-scope. The principle of minimal change applies: every rejected character that a legitimate user might submit creates a friction point that must be documented and supported. Allow leading dot/dash and let the existing `slugify(filename) or "untitled"` (line `src/kb/mcp/core.py:695`) handle the slug-form derivation.
- DECIDE: **B** — ALLOW leading dot and leading dash.
- RATIONALE: out of AC12's stated rejection-set; both are legitimate POSIX filenames that real users submit.
- CONFIDENCE: HIGH

### Q6: AC12 non-ASCII rejection — strict any-non-ASCII or non-ASCII-letter only?
- OPTIONS: A) strict `[^\x00-\x7F]` blocks ALL non-ASCII (R2); B) non-ASCII-letter only (target only `\p{L}` outside ASCII).
- ## Analysis
  The threat in `threat-model.md:28` is Cyrillic homoglyphs (`а` U+0430 vs `a` U+0061) — `slugify` preserves Cyrillic via `\w` and creates a different bytestring that visually identifies as ASCII. The minimum mitigation targets non-ASCII letters only (Option B). However, Option B requires importing the `unicodedata` module or a `regex` library with `\p{L}` support — the project currently uses stdlib `re` (line `src/kb/utils/sanitize.py:6`). Option A is one stdlib regex pattern with no new dependency.
  
  Trade-off: Option A also blocks legitimate non-ASCII non-letter characters (e.g. emoji `📄.md`, en-dash `foo–bar.md`). Are these legitimate filename inputs for a personal wiki? Practically: if a user wants to ingest an emoji-titled article, the wiki convention is to slugify it human-readably anyway (slugify strips emoji to `_` in current behavior — verified by reading `src/kb/utils/sanitize.py` neighbors). Option A is a stricter baseline that prevents an entire category of non-ASCII Trojan attacks (RTL-override `‮`, zero-width-space `​`, full-width digits, mixed-script confusables) at zero false-positive cost for the wiki's actual use case (English-language sources from raw/articles/, raw/papers/). Option A is also self-documenting: `[^\x00-\x7F]` is one line any reviewer reads.
- DECIDE: **A** — strict `[^\x00-\x7F]` blocks any non-ASCII.
- RATIONALE: stdlib-only, prevents homoglyph + RTL-override + zero-width attacks; project's actual filename inputs are ASCII English; one-line check.
- CONFIDENCE: HIGH

### Q7: AC4/AC5 wrapper-level lock in `_write_index_files`?
- OPTIONS: A) NO wrapper lock (R2 Q2); B) ADD wrapper lock.
- ## Analysis
  R2 Q2 (`r2-codex-eval.md:13-17`) provides hard evidence: `file_lock` in `src/kb/utils/io.py:294,321,355,392` is `os.O_EXCL`-based, NOT `threading.RLock`-based. Same-PID re-acquisition self-deadlocks until timeout. If the wrapper `_write_index_files` (line `src/kb/ingest/pipeline.py:866-890`) acquires `file_lock(sources_file)`, then calls `_update_sources_mapping(...)` which also acquires `file_lock(sources_file)`, the inner call blocks itself.
  
  Blast radius of adding a wrapper lock: production deadlocks on every ingest. Reversibility: would require a hotfix release. Option A (no wrapper lock) puts the lock at the lowest correct level — the function whose RMW window needs protection. AC4 and AC5 each protect their OWN file (sources_file vs index_path), so there's no cross-file ordering hazard either. The brainstorm Q6 (`brainstorm.md:72`) already independently concluded "lock at the CALLEE level so each index file's read-write is independent." R1's C3 also confirms (`r1-opus-eval.md:68`).
- DECIDE: **A** — NO wrapper lock; lock only inside the two callees.
- RATIONALE: `file_lock` is non-reentrant; wrapper lock would self-deadlock on every ingest.
- CONFIDENCE: HIGH

### Q8: AC8/AC9 spy mechanism — monotonic timestamps or call_args_list ordering?
- OPTIONS: A) `time.monotonic()` timestamps recorded in spy callbacks; B) `unittest.mock.call_args_list` ordering against `read_text` + `atomic_text_write` mocks.
- ## Analysis
  Option A (monotonic timestamps) is robust against test framework concurrency but adds a custom recording fixture and timing-comparison logic. Option B (call_args_list) leverages stdlib `unittest.mock` ordering semantics — `mock.call_args_list` preserves insertion order, and a single test thread guarantees monotonic insertion. Option B is the standard pattern in the existing test suite (cycle-17 L4 lessons in user memory: spy callbacks are an anti-pattern when call-order suffices).
  
  Per the AC8/AC9 wording (`requirements.md:35`): "this is a call-order assertion (not a real concurrency race)." That phrasing maps directly to Option B's semantic. Option B's failure mode under AC4 revert: if the lock is removed, the mocked `file_lock.__enter__` is never invoked, so `mock_file_lock.call_args_list` is empty → assertion `assert mock_file_lock.call_count == 1` fails cleanly. Option A would require asserting `lock_acquire_time < read_time < write_time < lock_release_time`, which is more brittle (requires patching multiple callsites) and doesn't even verify the lock was held for the right file — only the timing.
- DECIDE: **B** — `unittest.mock.call_args_list` ordering against the three mocks.
- RATIONALE: stdlib pattern, matches existing spy conventions (cycle-17 L4), cleaner failure mode under AC4 revert.
- CONFIDENCE: HIGH

### Q9: AC10 — assert NO `_sources.md not found` warning when wiki_pages empty?
- OPTIONS: A) YES, assert no warning fires (T8 verification); B) NO, only assert no atomic_text_write call.
- ## Analysis
  Threat-model T8 (`threat-model.md:124-128`) explicitly says: "test asserts NO warning fires when sources_file is missing AND wiki_pages is empty (no log capture of `_sources.md not found`)." This is the verification anchor for AC6's early-return placement. Without this assertion, an implementer could place `if not wiki_pages: return` AFTER the `sources_file.exists()` check — the test would still pass (no atomic_text_write), but a spurious warning would fire on every empty-pages call when sources_file happens to be missing (e.g. fresh wiki, before first ingest).
  
  R2 Q3 (`r2-codex-eval.md:21-23`) confirms the warning must stay for the non-empty missing case (legitimate signal). The assertion-target is specifically: empty `wiki_pages` AND missing `sources_file` should be silent (no log spam). The assertion uses pytest's `caplog` fixture — standard pattern, ~3 lines. Adding it locks in the early-return ordering invariant; omitting it leaves T8 unverified and risks regressions.
- DECIDE: **A** — assert NO warning fires.
- RATIONALE: T8 explicitly requires it; locks in AC6 early-return ordering invariant.
- CONFIDENCE: HIGH

### Q10: AC11 single-call invariant assertion?
- OPTIONS: A) ADD third assertion (R1 Q8) that call 1's escaped form is in content; B) leave as two-call dedup-only assertion.
- ## Analysis
  The risk Option A guards against: the implementer over-fixes by also changing the WRITE path (line 786-787 `entry = f"- \`{escaped_ref}\` → ..."`) in a way that drops the escaped backtick from disk. The two-call dedup test would still pass (both calls write the same broken form, dedup matches), but the on-disk content would be wrong. Adding a single-call invariant `assert "\\`" in content` after the first invoke pins the write-format.
  
  Blast radius: one extra assertion line in one test. Failure mode: catches a real over-fix regression that the dedup test alone misses. R1 Q8 explicitly recommended this. The "would a senior engineer say this is overcomplicated?" test passes — adding a third assert in a regression test for a multi-axis property (write-format AND dedup) is normal TDD discipline (cycle-24 L4 dual-anchor pattern).
- DECIDE: **A** — ADD single-call invariant assertion.
- RATIONALE: pins write-format alongside dedup-format; catches over-fix regressions the two-call test would miss.
- CONFIDENCE: HIGH

### Q11: AC3 expansion — add R2 Q6 positive + 2 negatives?
- OPTIONS: A) ADD all three (positive `//server/share/path.md` redacts; negative `https://example.com/path` unchanged; negative `//comment text` unchanged); B) ADD only the positive.
- ## Analysis
  The two negative tests are the verification anchors for Q1's URI-guard decision. Without `https://example.com/path` unchanged, AC1's `(?<!:)` lookbehind is silently testable-only; without `//comment text` unchanged, the slash-UNC pattern's hostname requirement (must contain `/` after host segment per `(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)`) is unverified — a single-segment `//x` would be ambiguous.
  
  Adding both negatives is essential to lock Q1's decision in test code (cycle-24 L4: every defensive choice needs a test that fails when reverted). The cost is two pytest one-liners. R2 Q6 (`r2-codex-eval.md:36-40`) explicitly listed all three. Without negatives, future maintainers tweaking the regex could introduce URI-overmatch and the test suite would not catch it. This is non-negotiable for Q1's safety claim.
- DECIDE: **A** — ADD all three (positive + 2 negatives).
- RATIONALE: negatives lock in Q1's URI-guard semantic; cycle-24 L4 dual-anchor discipline.
- CONFIDENCE: HIGH

### Q12: Step-11b GitPython 3.1.46 → 3.1.47 — bundle or separate PR?
- OPTIONS: A) bundle into cycle 35 PR same-day (R1 Q7); B) separate PR.
- ## Analysis
  GitPython is at line 82 of `requirements.txt` (verified via grep). It is NOT imported anywhere in `src/kb/` (verified: `rg "^\s*(import git\b|from git\b)" src/kb` returns no matches). It is therefore a transitive dependency (likely via pre-commit / a tooling library) with zero runtime exposure. Bumping 3.1.46 → 3.1.47 is a security-only patch with a published fix; it is in the BACKLOG class-A opportunistic patch list (`threat-model.md:10`).
  
  Bundling into the cycle 35 PR: one-line `requirements.txt` change + Step-12 `CHANGELOG.md` entry. Doc update happens in a single Codex pass (per `feedback_dependabot_pre_merge`'s 4-gate model — Step-11b dep diff is the appropriate gate for GitPython). Separate PR doubles CI time, fragments the audit trail, and leaves the Dependabot alert open longer. The user's `feedback_cve_patch_before_docs` memory makes the Step-12.5 ordering explicit: patch BEFORE docs in the same cycle. Bundling is the project convention.
- DECIDE: **A** — bundle into cycle 35 PR (Step-11b commit, Step-12 doc-pass covers both diffs).
- RATIONALE: zero runtime exposure (no import); class-A opportunistic patch; project's 4-gate model and `feedback_cve_patch_before_docs` mandate same-cycle bundling.
- CONFIDENCE: HIGH

### Q13: AC18 Playwright canonical command — also add to `docs/reference/conventions.md`?
- OPTIONS: A) YES, add R2 Q7's exact snippet to conventions.md for future cycles; B) NO, keep it inline-in-design-doc only.
- ## Analysis
  Cycle 34 deferred AC4e (this exact same task) explicitly because the Playwright invocation was ambiguous in the project docs. The only canonical reference today is the prose in `docs/reference/conventions.md` "Architecture Diagram Sync (MANDATORY)" rule which describes parameters but doesn't ship runnable code. Future cycles will hit the same ambiguity. Adding R2 Q7's tested snippet (`r2-codex-eval.md:42-57`) to conventions.md as a fenced code block converts mandatory discipline into copy-paste discipline.
  
  Blast radius: one prose-doc edit (additive, no breaking change). Reversibility: trivial. The "would a senior engineer call this overcomplicated?" test: a senior would call the OMISSION overcomplicated — re-deriving the snippet every cycle is the actual overcomplication. This is the second cycle hitting this exact issue; codifying it now prevents a third deferral. Plus this resolves a `docs/reference/` source-of-truth gap (per CLAUDE.md "source of truth for its topic").
- DECIDE: **A** — add the snippet to `docs/reference/conventions.md` Architecture Diagram Sync section.
- RATIONALE: cycle 34 deferred this same AC for ambiguity; codifying the snippet prevents a third deferral.
- CONFIDENCE: HIGH

## CONDITIONS (Step 9 must satisfy)

Aggregating R1 C1-C13, R2 1-8, plus Q-derived conditions:

1. **AC1 regex** — insert TWO new alternatives in `_ABS_PATH_PATTERNS` (line `src/kb/utils/sanitize.py:11-19`): (a) `r"|(?://\?/UNC/[^\s'\"]+/[^\s'\"]+(?:/[^\s'\"]*)?)"` for slash-UNC long-path; (b) `r"|(?<!:)(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)"` for ordinary slash-UNC with URI-overmatch guard. Both AFTER the existing backslash UNC alternatives. Comment cites T1+T1b+AC1.
2. **AC2** — `@pytest.mark.xfail(strict=True)` decorator REMOVED from `tests/test_cycle33_mcp_core_path_leak.py:477-486` in same commit as AC1.
3. **AC3** — three sub-tests in the same class: (a) positive `sanitize_text("//corp.example.com/share$/secret.md")` → `<path>`; (b) negative `sanitize_text("https://example.com/path")` returns input unchanged; (c) negative `sanitize_text("//comment text")` returns input unchanged. Hostname must contain a dot (R1 C2).
4. **AC4/AC5** — sequential locks (sources released BEFORE index acquired); NO wrapper-level lock in `_write_index_files` (R2 Q2; R1 C3). Lock spans `read_text` + `atomic_text_write` for BOTH branches inside each function.
5. **AC6** — early-return placed AFTER docstring + BEFORE `sources_file = ...` line; uses `logger.debug` (R1 C4).
6. **AC7** — change BOTH membership check (line 792) AND per-line scan (line 799) to `escaped_ref` (verify with grep `f"\`{source_ref}\`"` returns ZERO matches in `_update_sources_mapping` after edit; R1 C5).
7. **AC8/AC9** — spy `kb.ingest.pipeline.file_lock` (NOT `kb.utils.io.file_lock`); use `unittest.mock.call_args_list` ordering against `read_text` + `atomic_text_write` mocks (Q8; R1 C6).
8. **AC10** — assert NO `_sources.md not found` warning fires when sources_file absent AND wiki_pages empty (T8; Q9).
9. **AC11** — raw string `r"raw/has\`backtick.md"`; ADD single-call invariant assertion (Q10; R1 C7) that escaped backtick form `` \`raw/has\\\`backtick.md\` `` appears in content after first invoke.
10. **AC12** — helper signature `_validate_filename_slug(filename: str) -> tuple[str, str | None]` (Q3); rejection set: NUL byte, path separators (`/`, `\`), `..`, non-ASCII `[^\x00-\x7F]` (Q6), Windows-reserved via existing `_is_windows_reserved` import, length cap, **trailing dot/space** (Q4 — `filename.strip() == filename`); leading dot and leading dash ALLOWED (Q5).
11. **AC13** — wiring placed AFTER existing empty/length checks in `_validate_file_inputs`: `_, slug_err = _validate_filename_slug(filename); if slug_err: return slug_err` (R1 C9; R2 #5 — public return type stays `str | None`).
12. **AC14** — NUL test uses `"\x00"` literal in source (R1 C10); homoglyph test uses Cyrillic `"а.md"` (U+0430); Windows-reserved parametrize over `CON.md`, `PRN.txt`, `NUL`, `AUX`, `com1.md`; path-separator parametrize over `../escape.md`, `foo/bar.md`, `foo\\bar.md`.
13. **AC15** — parametrize over `karpathy-llm-knowledge-bases.md`, `my_doc.md`, `file-2026-04-26.md`.
14. **AC16/AC17** — grep verifies `v0\.10\.0` returns ZERO matches in `docs/architecture/architecture-diagram*.html` after edit (R1 C11).
15. **AC18** — Playwright invocation per R2 Q7 snippet: `viewport={"width": 1440, "height": 900}, device_scale_factor=3, full_page=True, type="png"` (R1 C12); also add the snippet to `docs/reference/conventions.md` Architecture Diagram Sync section (Q13).
16. **Step 11 same-class peer scan** — `rg "with file_lock(" src/kb/ingest src/kb/utils src/kb/compile` confirms T2/T3 sites added; no peer site missed elsewhere (R1 C13; R2 #9 confirms `wiki_log.py:149` already locked, no `_categories.md` writer in pipeline).
17. **Step-11b GitPython** — pin `requirements.txt` line 82 to `GitPython>=3.1.47`; pip-audit post-bump shows GitPython advisories absent; verify `rg "^\s*(import git\b|from git\b)" src/kb` returns ZERO matches before commit (R2 Q10; Q12). NOTE: verified pre-design that current src/kb has zero `import git` — bump is decoupled from production code.
18. **Step 12 doc-update** — single Codex pass covers cycle 35 cycle work + Step-11b dep bump; CHANGELOG entry follows `feedback_cve_patch_before_docs` ordering.

## FINAL DECIDED DESIGN

### File group A — `utils/sanitize.py` (M12 + T1b)
- **AC1** AMENDED — add TWO new alternatives to `_ABS_PATH_PATTERNS`: slash-UNC long-path `(?://\?/UNC/...)` AND URI-guarded ordinary slash-UNC `(?<!:)(?://...)`. Inserted as alternatives #4 and #5 (AFTER existing backslash UNC patterns).
- **AC2** PROCEED — remove `xfail(strict=True)` decorator at `tests/test_cycle33_mcp_core_path_leak.py:477-486`.
- **AC3** AMENDED — three sub-tests (1 positive + 2 negatives per Q11): UNC redacts, URL stays intact, C-comment stays intact.
- **AC1b** ADDED — T1b proactively closed in-cycle as part of AC1's two-pattern form (rationale: R2 confirmed leak; data-driven uncertainty resolved per Q2).

### File group B — `ingest/pipeline.py` (M11 + M13 + M14)
- **AC4** AMENDED — wrap `_update_sources_mapping` RMW in `file_lock(sources_file)`; NO wrapper lock in `_write_index_files` (Q7).
- **AC5** AMENDED — wrap `_update_index_batch` RMW in `file_lock(index_path)`; same no-wrapper-lock condition. Early-return at `if not entries:` STAYS BEFORE lock acquisition (no point locking a no-op).
- **AC6** AMENDED — early-return AFTER docstring + BEFORE `sources_file = ...`; `logger.debug` not warning (Q9 ordering invariant verified by AC10).
- **AC7** PROCEED — both membership check (line 792) AND per-line scan (line 799) use `escaped_ref`.
- **AC8** AMENDED — `unittest.mock.call_args_list` ordering against `kb.ingest.pipeline.file_lock` + `read_text` + `atomic_text_write` mocks (Q8).
- **AC9** AMENDED — same shape as AC8 for `_update_index_batch`.
- **AC10** AMENDED — also assert NO `_sources.md not found` warning fires (Q9; T8 verification).
- **AC11** AMENDED — raw string `r"raw/has\`backtick.md"`; THREE assertions: (1) two-call dedup → single line, (2) single-call invariant → escaped backtick form on disk after call 1 (Q10), (3) call-2 doesn't double-write.

### File group C — `mcp/core.py` (M15)
- **AC12** AMENDED — helper signature `tuple[str, str | None]` (Q3); rejection set: NUL + path-separators + non-ASCII `[^\x00-\x7F]` (Q6) + Windows-reserved (via existing import) + length cap + trailing dot/space (Q4); allow leading dot and leading dash (Q5).
- **AC13** PROCEED — wire after existing checks; public return stays `str | None`.
- **AC14** PROCEED — NUL via `"\x00"`; Cyrillic via `"а.md"` U+0430; parametrize Windows-reserved (`CON.md`, `PRN.txt`, `NUL`, `AUX`, `com1.md`) + path-separators (`../escape.md`, `foo/bar.md`, `foo\\bar.md`).
- **AC15** PROCEED — parametrize positive cases.

### File group D — `docs/architecture/` (M21, AC4e from cycle 34)
- **AC16** PROCEED — `architecture-diagram.html:501` v0.10.0 → v0.11.0; grep verifies no other v0.10.0 survives.
- **AC17** PROCEED — `architecture-diagram-detailed.html:398` v0.10.0 → v0.11.0; same grep verification.
- **AC18** AMENDED — Playwright re-render per R2 Q7 snippet (Q13); also add snippet to `docs/reference/conventions.md` Architecture Diagram Sync section as canonical reference.

### Step-11b — GitPython dep bump
- **AC-Dep1** ADDED — pin `requirements.txt` line 82 to `GitPython>=3.1.47`; bundle into cycle 35 PR (Q12). Pre-verified: zero `import git` in `src/kb/` so no runtime impact.

### Documentation (Step 12)
- **AC-Doc1** ADDED — CHANGELOG.md, CHANGELOG-history.md, BACKLOG.md updates per project doc-checklist; single Codex pass covers cycle work + Step-11b diff.

**Total ACs: 20** (18 original + AC1b proactive T1b + AC-Dep1 GitPython bump). Zero ACs DROPPED. Doc-update AC-Doc1 is procedural (not counted in design-AC count).
