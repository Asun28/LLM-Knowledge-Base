# Cycle 17 — Design Gate (Step 5)

**Date:** 2026-04-20
**Cycle:** 17 (backlog-by-file; 21 ACs across 14 files)
**Inputs:** requirements, threat-model, R1-Opus design eval, R2-Codex design eval
**Gate output:** consolidated decisions on 13 open questions + revised AC text for six ACs with line-number / semantic drift.

## VERDICT

APPROVE with 9 amendments, 0 open questions escalated.

All 13 open questions resolved autonomously. Two ACs (AC5 / AC7) downgrade from "new fix" to "regression pin" because R1 grep found the deferment already in place; tests still ship to lock in the invariant per cycle-15 L2 ("keep paired test ACs"). AC18 reframes as a regression pin for the same reason. AC9 / AC10 / AC11 / AC12 / AC13 / AC21 all get concrete line/placeholder/regex fixups. No ACs drop.

---

## DECISIONS (Q1–Q13)

### Q1. AC9 `capture_prompt.txt` location — `templates/` vs `templates/prompts/` subdir? Cached or re-read?

- **OPTIONS:**
  - **(a)** `templates/capture_prompt.txt` alongside the 10 YAML extraction templates. Loader: `TEMPLATES_DIR / "capture_prompt.txt"`. Read once at module import, stored in module-level constant.
  - **(b)** `templates/prompts/capture_prompt.txt` in a new subdir. Reserves `templates/prompts/*.txt` namespace for future prompt files. Cached the same way.
  - **(c)** `templates/capture_prompt.txt`, but read lazily inside `_render_prompt` on every call so `kb` code-reloaders pick up edits without process restart.

**## Analysis**

The existing `templates/` directory holds YAML extraction schemas consumed by `load_template(source_type)` from `kb.ingest.extractors`. The loader there validates that `source_type in SOURCE_TYPE_DIRS` — a closed set. A loose `.txt` sibling is structurally distinct (different extension, different loader) and cannot collide with the YAML enumeration. Moving to `templates/prompts/` reserves a namespace we do not yet need; the cycle-17 budget has one prompt file. Premature dir-creation now means a cycle-18 decision ("do I move the YAMLs too?") that we currently have no evidence supports. Option (a) is the minimal change.

On caching: `load_template` uses `@functools.lru_cache(maxsize=16)` and documents that on-disk edits are not picked up until restart. Capture's prompt is hotter (every `kb_capture` call) and smaller (~2KB text). Reading on every call is wasteful; reading once at module import is the pattern set by the YAML loader and keeps parity. The threat-model T11 flags path-traversal risk if the loader path were caller-controlled — option (a) hardcodes the filename (`"capture_prompt.txt"`) so there is no caller-supplied path, satisfying T11 by construction. Option (c) reintroduces per-call I/O without a restart-reload upside worth that cost.

- **DECIDE:** Option (a) — `templates/capture_prompt.txt`, loaded once at module init via `TEMPLATES_DIR / "capture_prompt.txt"` stored in `_PROMPT_TEMPLATE = _load_capture_prompt()` at module scope.
- **RATIONALE:** minimal change, reuses the existing `templates/` loader convention, and hardcoded filename eliminates T11 traversal surface.
- **CONFIDENCE:** HIGH.

---

### Q2. AC10 rollback scope — per-item commit (current) or all-or-nothing (new)?

- **OPTIONS:**
  - **(a)** Per-item commit (current): Phase C writes each file, partial failure returns `(written, error_msg)` with `written` containing the pre-failure successes. `raw/captures/` accumulates partial batches.
  - **(b)** All-or-nothing: Phase 1 `O_EXCL`-reserves ALL N slugs (writes placeholder content); Phase 2 computes `alongside_for` from finalized slugs; Phase 3 does `atomic_text_write` to replace placeholders. On ANY Phase 1 failure, unlink previously-reserved placeholders and surface error with `written=[]`.

**## Analysis**

Threat T4 in the threat model is explicit: a cross-process Phase 1 collision where writer A holds slugs 1-2-4-5 and loses slug 3 must roll back the other four, or orphaned reservations accumulate. The existing per-item commit is tolerable in the single-writer case (each `kb_capture` owns its 20-item cap, no cross-call contention on slugs because the 20-item cap caps per-call), but concurrent MCP invocations from two Claude Code windows violate that assumption — the bug AC10 names explicitly. Option (a) preserves the bug; the question is whether to keep it or fix it.

All-or-nothing aligns with the cycle's atomicity theme: AC3 locks the compile manifest RMW (all-or-nothing save), AC16 introduces opt-in isolation (all-or-nothing test state). Diverging on capture would create a rare "some items committed, some rolled back" semantic that is hard to document coherently. The engineering cost is modest: a single `try` block around Phase 1 with `unlink(missing_ok=True)` cleanup in the `except` branch. The reversibility argument also favors (b): a future operator who sees `CaptureError: partial reservation` knows nothing committed; per-item reporting forces them to inspect the directory. Align with the design bias toward atomicity.

- **DECIDE:** Option (b) — Phase 1 reserves all N slugs first; any failure triggers `unlink(missing_ok=True)` on already-reserved paths; return `(written=[], error_msg)`.
- **RATIONALE:** closes T4 and matches the cycle's all-or-nothing atomicity theme.
- **CONFIDENCE:** HIGH.

---

### Q3. AC16 `_kb_sandbox` fixture surface — paths only, or also clear LRU caches?

- **OPTIONS:**
  - **(a)** Paths only: monkeypatch the 6 config path constants, no cache clearing.
  - **(b)** Paths + LRU clear: after monkeypatch, clear `load_purpose.cache_clear()`, `_load_template_cached.cache_clear()`, `_build_schema_cached.cache_clear()`; repeat on teardown.

**## Analysis**

The threat model T13 flags "opt-in fixture leakage into non-using tests" as LOW, but does not address the inverse — LEAKAGE INTO the fixture from prior test state. `load_purpose` has `maxsize=4` and is keyed on the `Path` argument, so theoretically switching `WIKI_DIR` via monkeypatch would result in a cache miss for the new path. But production code calls `load_purpose(WIKI_DIR)` only through `query_wiki` and the extractor code path, both of which receive the effective `wiki_dir` explicitly — so the cache key differs and there is no actual leakage. Similarly `_load_template_cached(source_type)` is keyed on source type, not path; patching config paths does not affect it.

However, the fixture's contract is "production code sees `tmp_path` for all config constants". Leaving stale caches intact means a test that imports `kb.utils.pages` and calls `load_purpose(old_wiki_dir)` BEFORE setup, then calls it AFTER setup with the tmp path, would still get the stale value if by coincidence the `maxsize=4` has not evicted it. This is pathological (tests should never call `load_purpose` without the sandboxed path), but a fixture that silently fails to deliver the documented contract is exactly the leak surface cycle-15 L2 warns against. The cost to clear three caches is ~3 lines of Python per setup + teardown, zero runtime impact (caches are process-local). Option (b) is cheap insurance that closes the only remaining leak class the threat model did not explicitly enumerate.

- **DECIDE:** Option (b) — clear all three LRU caches on setup AND teardown.
- **RATIONALE:** closes a latent cache-leak class at trivial cost; matches the fixture's documented contract.
- **CONFIDENCE:** HIGH.

---

### Q4. AC21 ReDoS mitigation — `re.escape` sufficient, or also bounded `MAX_INJECT_TITLES_PER_BATCH`?

- **OPTIONS:**
  - **(a)** `re.escape` only: each title goes through `re.escape` before alternation join. Python `re` is NFA-based and handles large alternations (`foo|bar|baz|...`) without catastrophic backtracking when there is no nested quantifier.
  - **(b)** `re.escape` + soft cap `MAX_INJECT_TITLES_PER_BATCH = 200`: above the cap, split into multiple passes. Defense in depth against pathological inputs we have not anticipated.

**## Analysis**

The threat-model T9 explicitly calls out batch alternation ReDoS but concedes "alternation without anchoring is safe in practice". The `inject_wikilinks` pattern today is `left + re.escape(title) + right` where left/right are `\b` or lookbehind/lookahead `(?<![a-zA-Z0-9_])` — no nested quantifier, no backreferences, no `.*` fallback. Joining 100 such subpatterns into an alternation yields an NFA of size ~100·avg_title_len with a single unified lookahead wrapper. Python's `re` module handles this linearly — I've measured comparable patterns in prior cycles. The ReDoS threat is notional.

However, AC21's stated target is 100 titles × N pages. A 200-cap leaves 2× headroom for growth without forcing a "batch-of-batches" architecture. The cap is also a defense against future regressions where someone adds a new title-normalization step that introduces a quantifier (e.g. optional plural `s?`). The cost is one constant + a `for chunk in batched(titles, cap)` loop — 5 lines. The time spent debating this is larger than the time spent implementing it. Applying the cap sets a regression-testable ceiling.

- **DECIDE:** Option (b) — `re.escape` + soft cap `MAX_INJECT_TITLES_PER_BATCH = 200` with a chunked loop for larger inputs.
- **RATIONALE:** cheap defense-in-depth against future nested-quantifier regressions; ceiling is regression-testable.
- **CONFIDENCE:** MEDIUM. (Option (a) is arguably sufficient today; the cap is pure hedging.)

---

### Q5. AC5 + AC7 — fold into one `test_mcp_lazy_imports.py` file or keep separate?

- **OPTIONS:**
  - **(a)** One file `tests/test_mcp_lazy_imports.py` covering all four modules (core, browse, health, quality) with one test function per module.
  - **(b)** Four separate files — one per MCP submodule.

**## Analysis**

The four tests share the same structure: `import importlib; importlib.import_module("kb.mcp.<name>"); assert "<heavy_dep>" not in sys.modules`. Parametrizing or sharing a helper is trivial. One file means a single place to maintain the denylist of heavy deps (anthropic, kb.query.engine, kb.ingest.pipeline, kb.graph.export, kb.compile.compiler, kb.review.refiner, kb.lint.augment, kb.lint.checks, networkx, trafilatura). Changing the denylist in cycle-18 requires one edit, not four.

The counter-argument is test isolation: `import kb.mcp.core` may mutate `sys.modules` in a way that affects the next test's assertion. Parametrized tests run in one process and sequentially — once `kb.mcp.core` has loaded `kb.query.engine` (even through a helper's call), the `browse` test fails spuriously. This is solvable with a `monkeypatch.delitem(sys.modules, "kb.query.engine", raising=False)` fixture that runs per-test, or with `subprocess.run([sys.executable, "-c", "import kb.mcp.browse; ..."])` to get a clean process. The subprocess approach is 4× slower but rock-solid; the monkeypatch approach is fast but requires care. Both work in one file. Separating into four files does not help — pytest collects all tests in one process anyway.

- **DECIDE:** Option (a) — one `tests/test_mcp_lazy_imports.py` with one test per MCP submodule, each using a `reset_sys_modules` fixture that strips the heavy deps before the `importlib.import_module` call.
- **RATIONALE:** single denylist source of truth; isolation handled by per-test `sys.modules` reset.
- **CONFIDENCE:** HIGH.

---

### Q6. AC18 reframing — ship as regression pin or drop?

- **OPTIONS:**
  - **(a)** Ship as a regression pin. `load_purpose(wiki_dir=tmp)` already requires `wiki_dir` (R1 confirmed the PROJECT_ROOT/env fallback is gone), so the test asserts the current invariant holds under `monkeypatch.setenv("KB_PROJECT_ROOT", "/elsewhere")`.
  - **(b)** Drop — production code path is already fixed, test adds no coverage.

**## Analysis**

Cycle-15 L2 says: "Keep DROPPED production ACs' paired test ACs as regression pins regardless of whether their production fix was a no-op." The whole point is that *future* refactoring could silently reintroduce the bug — a PROJECT_ROOT fallback added "as a convenience" would re-open the test/prod cross-talk class that cycle-4 closed. A regression test is cheap (one function, ~15 lines) and catches that revert. Dropping saves ~15 lines of code and gains zero defense; the ROI on keeping the pin is strictly positive.

The specific test: `def test_load_purpose_ignores_project_root_env(tmp_path, monkeypatch)` writes `tmp_path / "purpose.md"`, sets `KB_PROJECT_ROOT=/elsewhere`, clears `load_purpose.cache_clear()` (necessary per Q3 reasoning), and asserts `load_purpose(tmp_path)` reads the tmp file. This also implicitly pins that `load_purpose` does not consult `os.environ` internally — a second invariant worth regression-pinning independently.

- **DECIDE:** Option (a) — ship as a regression pin.
- **RATIONALE:** cycle-15 L2 mandates it; cost is negligible; defense is real if a future refactor re-adds a fallback.
- **CONFIDENCE:** HIGH.

---

### Q7. AC2 regression strength — parametrize non-default `raw_dir.name`?

- **OPTIONS:**
  - **(a)** Three parametrize cases: default `raw_dir=RAW_DIR`, relative `raw_dir=Path("raw")`, absolute `raw_dir=tmp_path/"raw"`. All three must yield identical `make_source_ref == _canonical_rel_path`.
  - **(b)** Three parametrize cases above PLUS one case where `raw_dir.name` differs from `"raw"` (e.g. `raw_dir=tmp_path/"sources"`). Pins the invariant that the contract does not depend on the directory name.

**## Analysis**

AC1's bug is specifically about `raw_dir.parent` mis-resolving under a relative path. The current test plan (option a) covers that exact bug. Option (b) extends the contract to "the name of `raw_dir` does not matter" — which is true of the current implementation but is not a user-facing claim. `ingest_source` does accept `raw_dir=None` (default) and operators typically use the project's `raw/`. The only non-default case in the codebase is test fixtures.

The extra parametrize case is cheap (one extra row in a pytest.mark.parametrize), but it also pins a stronger contract than the bug requires. If a future cycle introduces custom `raw_dir.name` semantics (e.g. for multi-project support), the test would need to update. Given the small cost and the fact that pinning stronger invariants is the whole point of the regression, option (b) shades ahead. But the marginal value is lower than Q3 / Q4 — this is a judgment call.

- **DECIDE:** Option (b) — parametrize 4 cases including a non-`"raw"` directory name.
- **RATIONALE:** pins the full "base path does not depend on directory name" contract; the extra row is essentially free.
- **CONFIDENCE:** MEDIUM. (Option (a) is sufficient for AC1's bug; (b) is stricter regression pin.)

---

### Q8. Run_id filename format — full id or 8-char prefix only?

- **OPTIONS:**
  - **(a)** Keep `augment-run-<run_id[:8]>.json` (current); validator enforces `^[0-9a-f]{6,8}$` for resume input (treating input as a short prefix). Operator sees 8-char IDs in proposals files and status messages.
  - **(b)** Expand filename to `augment-run-<full_run_id>.json` (36-char UUID with hyphens); validator enforces `^[0-9a-f-]{6,36}$`. Backwards compat broken for existing runs.
  - **(c)** Keep `augment-run-<run_id[:8]>.json` but validator enforces exact 8-char match (`^[0-9a-f]{8}$`), not a prefix. Eliminates the "first match wins" prefix ambiguity from R2 MAJOR.

**## Analysis**

R2 correctly identified that the `Manifest.start` site writes `augment-run-{run_id[:8]}.json` (src/kb/lint/_augment_manifest.py:76) while `Manifest.resume` globs `augment-run-{run_id_prefix}*.json`. If resume input is treated as a prefix shorter than 8 chars (e.g. `abc`), two runs sharing `abc*` collide and resume picks the first match arbitrarily. The threat-model T10 flags this as MEDIUM and recommends min-length 6.

Option (b) — expanding to full 36-char UUID — is the most robust but breaks backwards compat. Existing `.data/augment-run-<8hex>.json` files from cycle 15/16 would need migration or dual-read support. Cycle 17 is a batch-by-file cycle, not a schema migration; the operational cost outweighs the robustness gain.

Option (c) — exact 8-char match — eliminates prefix ambiguity entirely. Resume input must be the FULL 8-char ID as printed in proposals/status. No glob wildcarding against user input (the `*` still exists in the glob for matching, but the prefix is fully specified). Operator ergonomics: they copy-paste the 8-char ID from the proposals file header (`"# Augment Proposals - run `abc12345`"`). This is the cleanest fix for the stated collision.

Option (a) with min-length 6 leaves a 2-char window where two runs could collide (`abc123` matches both `abc1234` and `abc12345`). The birthday-paradox math for 6-hex prefixes over ~100 runs is ~1% collision rate — non-zero, and the failure mode is "resume silently loaded wrong manifest".

R2 additionally required: if glob returns >1 match, raise rather than silently pick the first. That fix applies independently of the format decision, and should be implemented regardless. Combined with (c), the >1-match raise is structurally unreachable for well-formed input but defends against corrupted `.data/` directories.

- **DECIDE:** Option (c) — keep 8-char filename prefix; resume input must be exactly 8 hex chars (`^[0-9a-f]{8}$`); `Manifest.resume` raises `ValueError("multiple incomplete runs match prefix")` when `list(glob)` returns >1 incomplete entry.
- **RATIONALE:** eliminates prefix collision at input layer, preserves existing filename format, and the >1-match raise is a free corruption-detector.
- **CONFIDENCE:** HIGH.

---

### Q9. AC10 placeholder naming — hidden temp suffix or `status: reserving` frontmatter guard?

- **OPTIONS:**
  - **(a)** Hidden temp suffix: Phase 1 reserves `_captures_dir / f".{slug}.reserving"` (leading dot hides on POSIX, `.reserving` extension excludes from `kb_ingest` glob `*.md`, `kb_search`, `_sources.md` scan). Phase 3 atomic-renames to `<slug>.md`.
  - **(b)** `.md` file with `status: reserving` frontmatter + ingest-path guard: Phase 1 writes `<slug>.md` with YAML `status: reserving`; ingest/compile paths add explicit skip for `status: reserving`.
  - **(c)** Temp filename with `.tmp-<slug>.md` prefix (matches temp-file convention but keeps `.md` extension).

**## Analysis**

R2 identified this as a BLOCKER: if Phase 1 reserves `<slug>.md` with placeholder content, a concurrent `kb_ingest` scanning `raw/captures/*.md` may pick up the reservation as a legitimate capture and produce a corrupt wiki page. Option (b) (frontmatter guard) requires adding `status: reserving` checks to every consumer of `raw/captures/`: `ingest_source`, `kb_compile_scan`, `lint.runner` stub detection, potentially `_sources.md` traceability. That's fragile; a new consumer added later will miss the guard.

Option (a) (hidden temp suffix) changes the Phase 1 write to a file that cannot match `*.md` globs. No consumer changes. The Phase 3 atomic-rename (POSIX) or `os.replace` (Windows) is the single point where the file becomes visible. This is the standard "temp-then-rename" pattern used throughout the codebase (`atomic_text_write` in `kb.utils.io`). The only concern is the leading dot on POSIX: Obsidian-like tools usually respect dotfile hiding, so operators see a clean captures dir; the suffix `.reserving` makes the temp purpose obvious if they list with `ls -a`.

Option (c) (`.tmp-<slug>.md`) keeps the `.md` extension, which would match `*.md` globs and re-introduce the concurrent-reader problem. Rejected.

Option (a) wins on: (1) single point of visibility atomicity, (2) no consumer changes needed, (3) matches existing atomic-write pattern. The implementation: Phase 1 does `fd = os.open(captures_dir / f".{slug}.reserving", O_CREAT | O_EXCL | O_WRONLY)`; Phase 3 does `os.replace(temp_path, final_path)` after writing the real content.

- **DECIDE:** Option (a) — Phase 1 reserves `.{slug}.reserving` hidden-temp files; Phase 3 atomic-renames to `<slug>.md`.
- **RATIONALE:** single-point visibility; no consumer-side frontmatter guards required; reuses the codebase's existing temp-then-rename atomicity pattern.
- **CONFIDENCE:** HIGH.

---

### Q10. AC3 exception path — include in same file_lock wrap?

- **OPTIONS:**
  - **(a)** Wrap ONLY the full-mode tail (lines 424-437) in `file_lock(manifest_path)`. The exception path at lines 414-419 (which also does `load_manifest → update → save_manifest` to record `failed:<hash>`) remains unlocked.
  - **(b)** Wrap BOTH the tail and the exception path's RMW in `file_lock(manifest_path)`. Exception handler becomes: `with file_lock(manifest_path): manifest = load_manifest(); manifest[rel] = f"failed:{h}"; save_manifest(manifest, path)`.

**## Analysis**

R2 identified this correctly: the exception path at compiler.py:414-419 has the same RMW race as the full-mode tail. A concurrent `kb_ingest` writing to the manifest while the exception handler is mid-way through `load → update → save` can lose the ingest's entry. The fix is symmetric: the lock must wrap both RMW sites.

The cost is minimal — one additional `with file_lock(manifest_path):` wrapper around the five-line exception block. Lock ordering is preserved (manifest_path is the last lock in the documented order; the compile-finalize tail comes after all per-source locks have been released). Deadlock-free by construction.

The alternative (option a) ships AC3 asymmetrically and leaves the exception handler as the only unlocked manifest RMW in the codebase post-cycle-17. That's exactly the "same-class peer scan" anti-pattern cycle-16 L1 flags as a regression-inviting shape. Grep `load_manifest` and verify every caller is inside `file_lock` — one unlocked site is as bad as all unlocked sites.

- **DECIDE:** Option (b) — wrap both the full-mode tail AND the exception handler in `file_lock(manifest_path)`.
- **RATIONALE:** symmetric fix closes T2 for both RMW sites; same-class-peer principle forbids leaving one unlocked.
- **CONFIDENCE:** HIGH.

---

### Q11. AC19 rotation race — add `file_lock` around rotate+append? And should `wiki_log.py` `_rotate_log_if_oversized` ALSO be retrofitted?

- **OPTIONS:**
  - **(a)** New `.data/ingest_log.jsonl` uses `file_lock(log_path)` around rotate+append as one atomic block. `wiki_log.py._rotate_log_if_oversized` is LEFT AS-IS (rotation outside lock).
  - **(b)** Same as (a) for new JSONL, PLUS retrofit `wiki_log.py` to move `_rotate_log_if_oversized` INSIDE the existing `file_lock(log_path)` block. One PR covers both.
  - **(c)** No rotation for `.data/ingest_log.jsonl` in cycle 17; accept unbounded growth + document operator responsibility for logrotate.

**## Analysis**

The threat-model T5 offers three choices: mirror 500KB rotation, accept unbounded, or cap-and-abort. Option (c) (accept unbounded) is reasonable for a personal KB — ingest throughput is bounded by human input, so the file grows slowly (~200 bytes per ingest × 100 ingests/day = 20KB/day = 7MB/year). But "document operator responsibility" is a weak contract; operators have to discover the file exists first.

Option (a) (rotation for new file only, leave `wiki_log.py` alone) closes T5 for the new surface without touching an existing file. `wiki_log.py`'s rotation-outside-lock has lived for many cycles without reported issues. The race window is narrow (rotate takes ~1ms, and rotation happens at ~500KB which is rare), and the existing `file_lock` around the append ensures two concurrent writers don't corrupt a line. The worst case today is: writer A rotates, writer B sees the oversize threshold between A's size check and A's rename, rotates a second time, producing `log.YYYY-MM.2.md`. Not ideal, but not data loss.

Option (b) is the principled fix — move rotation inside the lock in both new and existing code. But R2 flagged this as out-of-scope expansion: retrofitting `wiki_log.py` means changing the test infra that pins current behavior and coordinating with cycle-16 tests. This cycle already has 21 ACs across 14 files; adding a 22nd to `wiki_log.py` violates the "batch-by-file by intention" principle.

Practical stance: new surface gets the correct pattern from day one (option a implementation detail — rotate inside lock); existing surface gets flagged in BACKLOG as a cycle-18 nit. This avoids cycle-17 scope creep while preserving the principled design for new code. Document the divergence in the commit message so the cycle-18 fix has context.

- **DECIDE:** Option (a) — new `.data/ingest_log.jsonl` does rotate-inside-lock from day one (500KB threshold mirrors `wiki_log.py`); `wiki_log.py._rotate_log_if_oversized` is NOT retrofitted in cycle 17 — add to BACKLOG as MEDIUM nit for cycle 18.
- **RATIONALE:** closes T5 for the new surface; existing surface's race is known-LOW and retrofitting adds cross-cycle coordination cost; BACKLOG entry prevents the known issue from being forgotten.
- **CONFIDENCE:** HIGH.

---

### Q12. AC21 lock semantics — per-page `file_lock` in batch version?

- **OPTIONS:**
  - **(a)** Batch version mirrors current per-page `atomic_text_write` with NO new locking. Concurrent-clobber window stays the same size as today.
  - **(b)** Add per-page `file_lock(page_path)` around the read-modify-`atomic_text_write` sequence in the batch version. Closes the concurrent-ingest clobber window.
  - **(c)** Add per-page `file_lock` only when batch size > 1 (i.e., when the batch-mode risk multiplier kicks in). Keeps scalar-mode semantics identical.

**## Analysis**

R2 identified that `inject_wikilinks` today writes with `atomic_text_write` but no surrounding `file_lock`. Two concurrent `ingest_source` calls can both read page P, both inject their respective new-page wikilinks, and the second `atomic_text_write` clobbers the first's injection. This is a latent bug TODAY — not introduced by AC21. AC21 just batches, which multiplies the window (N pages × 1 ingest = 1 clobber opportunity each → N pages × K ingests = N·K in parallel).

Option (a) preserves parity with the current broken state. Cycle-17 is batch-by-file; adding locks to linker is scope creep, even if correct. Option (b) is the principled fix but means AC21 now owns a concurrency fix that is a separate HIGH-severity bug in its own right — and that bug should be filed, designed, and landed with its own regression test.

Option (c) is a compromise: the batch version (new code) takes per-page `file_lock`; the scalar version (existing code) remains unchanged. This bounds the cycle-17 scope to the new code path while giving batch a correct baseline. Pass/fail: regression test asserts that concurrent batch calls on overlapping target sets don't clobber. The scalar version keeps its known-pre-existing bug, which should be filed as a BACKLOG entry for a dedicated fix cycle.

The threat-model's T9 covers ReDoS (alternation regex) but not the clobber race. R2 correctly surfaced it. Given the cycle's goal ("preserves per-page atomic_text_write semantics; no locking regression"), option (c) delivers "no regression" (scalar unchanged) AND "improvement where new" (batch has locks). Net positive.

- **DECIDE:** Option (c) — batch version takes per-page `file_lock(page_path)` around the read-and-atomic-write sequence; scalar `inject_wikilinks` unchanged; add BACKLOG entry "MEDIUM: scalar inject_wikilinks lacks per-page file_lock" for a dedicated cycle.
- **RATIONALE:** batch gets correctness from day one; scalar preserves parity (no regression); pre-existing scalar race documented for follow-up.
- **CONFIDENCE:** MEDIUM. (Option (b) would be more correct but expands scope; option (c) is the cycle-aware compromise.)

---

### Q13. AC16 cache-clear set — exhaustive list of `@lru_cache` decorated callables to clear?

- **OPTIONS:**
  - **(a)** Clear only `load_purpose.cache_clear()` in `_kb_sandbox` (the one cache directly keyed on a path).
  - **(b)** Clear `load_purpose.cache_clear()`, `_load_template_cached.cache_clear()`, and `_build_schema_cached.cache_clear()` (the three `@lru_cache` decorated functions in `src/kb/`, per grep).
  - **(c)** Same as (b), plus add a `_CACHED_CALLABLES` tuple at module scope in `tests/conftest.py` that enumerates all currently-known caches so future additions can be appended in one place.

**## Analysis**

Grep found exactly three `@functools.lru_cache` decorators in `src/kb/`:
1. `kb/utils/pages.py:59` — unnamed (inner helper) — `_collect_page_data`.
2. `kb/utils/pages.py:185` — `load_purpose(wiki_dir)` — keyed on Path.
3. `kb/ingest/extractors.py:122` — `_load_template_cached(source_type)` — keyed on source type.
4. `kb/ingest/extractors.py:265` — `_build_schema_cached(source_type)` — keyed on source type.

So actually four caches. The first (`_collect_page_data`) is keyed on `(path, mtime)` — mtime differs across test setups, so cache leakage is structurally impossible. The second (`load_purpose`) is keyed on the Path — if a test runs `load_purpose(old_wiki)` before sandbox setup and `load_purpose(new_wiki)` after, the keys differ and there is no leak. Caches three and four are keyed on `source_type` which is "article" / "paper" / etc.; the cache doesn't care about filesystem paths at all. So NONE of the four can actually leak across a sandbox switch (the keys don't overlap).

However, the `_kb_sandbox` fixture's documented contract is "production code sees `tmp_path` for all config constants". A future change to `load_purpose` that adds environment-dependent behavior (e.g. reads `KB_PROJECT_ROOT` when the passed wiki_dir is None — a regression AC18 guards against) would break the contract silently. Clearing caches is cheap insurance.

Option (c) over-engineers: a `_CACHED_CALLABLES` tuple in conftest couples test infrastructure to `src/kb/` internals in a way that future refactoring will forget to update. The better practice is to clear in the fixture body, discover-broken-at-test-time, and fix point-by-point. Option (b) gives the needed hedge without the registry overhead.

- **DECIDE:** Option (b) — clear `load_purpose.cache_clear()`, `_load_template_cached.cache_clear()`, `_build_schema_cached.cache_clear()` on fixture setup AND teardown. `_collect_page_data` (inner pages.py helper) is not cleared because it is keyed on (path, mtime) which cannot leak.
- **RATIONALE:** covers all path/type-keyed caches that production code uses; trivial cost; no cross-module registry coupling.
- **CONFIDENCE:** HIGH.

---

## REVISED AC TEXT

### AC5 (reframed as regression pin)

**AC5** (HIGH regression pin, NOT a new fix): R1 grep confirms `mcp/browse.py` already defers `kb.query.engine` via function-local import (line 48); `kb.ingest.pipeline` and `kb.graph.export` are not imported at module scope. Cycle-15 L2 dictates keeping the paired test AC as a regression pin. Add `tests/test_mcp_lazy_imports.py::test_browse_cold_boot` that asserts `import kb.mcp.browse` does NOT load `kb.query.engine`, `kb.ingest.pipeline`, or `kb.graph.export` into `sys.modules`.
- Pass/fail: cold-boot test asserts named heavy deps NOT in `sys.modules` after `importlib.import_module("kb.mcp.browse")` following a `sys.modules`-reset fixture.

### AC7 (reframed as regression pin)

**AC7** (HIGH regression pin, NOT a new fix): R1 grep confirms `mcp/quality.py` already defers `kb.review.refiner` via function-local import (line 94); `kb.lint.augment` is not imported at module scope; `kb.lint.checks` similarly deferred. Cycle-15 L2 keeps the paired test AC. Add `tests/test_mcp_lazy_imports.py::test_quality_cold_boot` that asserts `import kb.mcp.quality` does NOT load `trafilatura` (transitively pulled by `lint.augment`), `kb.review.refiner`, `kb.lint.augment`, or `kb.lint.checks`.
- Pass/fail: cold-boot test asserts named heavy deps NOT in `sys.modules`.

### AC9 (line-number fix)

**AC9** (MEDIUM): `src/kb/capture.py::_PROMPT_TEMPLATE` at **line 295** (R1 correction; was incorrectly reported as 209-238) — move from module-level string literal to `templates/capture_prompt.txt` loaded via `Path.read_text(encoding="utf-8")` at module init. Loader path is hardcoded as `TEMPLATES_DIR / "capture_prompt.txt"` (no caller-supplied component, satisfying T11). Document in module docstring that `.txt` is distinct from YAML JSON-schema templates in `templates/*.yaml`.
- Pass/fail: `_PROMPT_TEMPLATE` becomes `_PROMPT_TEMPLATE = (TEMPLATES_DIR / "capture_prompt.txt").read_text(encoding="utf-8")`; unit test asserts rendering parity with pre-fix literal; `templates/capture_prompt.txt` exists with the current prompt body verbatim.

### AC10 (line-number + placeholder naming + two-phase atomicity)

**AC10** (CRITICAL): `src/kb/capture.py::_write_item_files` at **lines 555-651** (R1 correction; was 341-372) — restructure into a two-phase all-or-nothing write:
- **Phase 1 (reserve ALL slugs):** For each resolved slug, `os.open(captures_dir / f".{slug}.reserving", O_CREAT | O_EXCL | O_WRONLY)`. Hidden-temp suffix `.reserving` (per Q9) prevents concurrent `kb_ingest` from ingesting the placeholder. On ANY `FileExistsError` during Phase 1, re-scan dir + re-resolve slug (Phase 1-retry, up to 10 attempts). On non-retriable `OSError` or retry exhaustion, unlink all previously-reserved `.{slug}.reserving` temp files and return `(written=[], error_msg)`.
- **Phase 2 (compute `alongside_for` from FINALIZED slugs):** After all N slugs reserved, compute `alongside_for[i] = [s for j, s in enumerate(slugs) if j != i]` using the Phase-1-finalized list. This closes the bug where `alongside_for` was frozen from the initial resolve before Phase-C reassignment.
- **Phase 3 (atomic rename):** For each item, write real content to the temp path, then `os.replace(temp_path, captures_dir / f"{slug}.md")`. `os.replace` is atomic on POSIX and on Windows for same-directory moves.
- Pass/fail: concurrent-capture monkeypatch test — two processes race on 3 overlapping titles; BOTH terminate with either full success or `(written=[], error_msg)`; no orphan `.reserving` or `.md` files remain; all `captured_alongside` lists match finalized slugs (no stale references).

### AC11 (run_id format alignment + glob ambiguity raise)

**AC11** (MEDIUM): `src/kb/lint/augment.py::run_augment` — re-add `resume: str | None = None` kwarg; at entry, when non-None, validate with the shared `_validate_run_id` helper (see AC12/AC13) and call `Manifest.resume(run_id_prefix=resume)`. Skip Phase A (no new proposals written) and restart iteration from `manifest.incomplete_gaps()`. In `_augment_manifest.Manifest.resume`, when `list(resolved.glob(f"augment-run-{run_id_prefix}*.json"))` returns >1 entry with `ended_at is None`, raise `ValueError(f"multiple incomplete runs match prefix {run_id_prefix!r}; supply exact 8-char id")` instead of silently taking the first match.
- Pass/fail: (1) test writes a partial manifest, invokes `run_augment(resume="<8-hex>")`, asserts Phase A skipped + only incomplete gaps ran; (2) regression test writes TWO partial manifests with the same input prefix, asserts `Manifest.resume(run_id_prefix="<exact-8-hex-of-one>")` returns that one (exact match); (3) corrupt-state test creates two files with the same 8-char stem (impossible in practice but legal on disk) and asserts `ValueError` raised.

### AC12 (--resume + --augment coupling + shared validator)

**AC12** (MEDIUM): `src/kb/cli.py::lint` command — new `--resume <id>` Click option. Validation via a shared `_validate_run_id(id: str) -> str | None` helper defined in `src/kb/mcp/app.py` (alongside `_validate_page_id`). Validator regex: `^[0-9a-f]{8}$` (exactly 8 hex chars — see Q8). Empty string is sentinel for "no resume" and bypasses the regex. Additionally, `--resume` without `--augment` raises `click.UsageError("--resume requires --augment")` (per R2 MAJOR).
- Pass/fail: (1) `kb lint --resume "../etc"` raises UsageError with the shared validator's error string; (2) `kb lint --resume "abc12345" --augment` forwards to `run_augment(resume="abc12345", ...)`; (3) `kb lint --resume "abc12345"` without `--augment` raises UsageError; (4) `kb lint --help` includes `--resume` entry.

### AC13 (MCP kb_lint resume + shared validator)

**AC13** (MEDIUM): `src/kb/mcp/health.py::kb_lint` — add `resume: str = ""` keyword-only parameter. Empty-string sentinel = no resume (matches MCP stringiness convention). Non-empty values validated via the SHARED `_validate_run_id` helper from `kb.mcp.app` (same constant, not duplicated). Invalid values return `"Error: Invalid resume id: <reason>"` string (never raise). Forwards valid value to `run_augment(resume=resume or None, ...)`.
- Pass/fail: (1) `kb_lint(resume="../etc")` returns `"Error: ..."` string containing "Invalid resume id"; (2) `kb_lint(resume="abc12345", augment=True)` forwards; (3) `kb_lint(resume="abc12345")` without `augment=True` returns `"Error: resume requires augment=true"` (mirror of CLI UsageError semantics); (4) validator grep confirms exactly ONE `_validate_run_id` definition in the codebase (single source of truth).

### AC18 (reframed as regression pin)

**AC18** (HIGH regression pin, NOT a new fix): R1 grep confirms `load_purpose(wiki_dir)` at `src/kb/utils/pages.py:186` already requires `wiki_dir` explicitly; the historical `PROJECT_ROOT/env` fallback is already removed. Cycle-15 L2 keeps the paired test. Add `tests/test_v0p5_purpose.py::test_load_purpose_ignores_project_root_env` that: writes `tmp_path / "purpose.md"` with known content, calls `load_purpose.cache_clear()`, sets `monkeypatch.setenv("KB_PROJECT_ROOT", "/elsewhere")`, calls `load_purpose(tmp_path)`, asserts the return equals the tmp file content. Guards against a future refactor that re-adds an env-var fallback.
- Pass/fail: test passes; if a future commit adds `os.environ.get("KB_PROJECT_ROOT")` fallback inside `load_purpose`, the test fails.

### AC21 (line-number + ReDoS + per-page lock + soft cap)

**AC21** (MEDIUM): `src/kb/compile/linker.py::inject_wikilinks_batch(new_titles_and_ids: list[tuple[str, str]], wiki_dir: Path | None = None)` — new batch scanner. `src/kb/ingest/pipeline.py:1113-1120` (R1 correction; was 712-721) replaces its per-title loop with one batch call.
- Each title goes through `re.escape` before joining into a single alternation pattern with the same word-boundary wrapper (`\b` or lookbehind/lookahead) used by scalar `inject_wikilinks`.
- Soft cap `MAX_INJECT_TITLES_PER_BATCH = 200` (Q4 decision): if `len(new_titles_and_ids) > 200`, iterate in chunks of 200.
- Per-page `file_lock(page_path)` around the read-modify-`atomic_text_write` sequence (Q12 decision — batch version gets locks; scalar version unchanged and BACKLOG'd).
- Each target page is read ONCE per batch (not per-title). Regression test asserts `Path.read_text` call count equals `N_PAGES` for `K_TITLES=100` × `N_PAGES=any`.
- Pass/fail: (1) `read_text` counter test passes; (2) ReDoS regression test with 100 titles × 10KB page body completes under 5 sec; (3) concurrent-batch test with two workers targeting the same pages does not clobber; (4) scalar `inject_wikilinks` unchanged (grep diff confirms no changes to its body).

---

## CONDITIONS

- **Step 7 plan MUST use revised AC text above** (AC5 / AC7 / AC9 / AC10 / AC11 / AC12 / AC13 / AC18 / AC21). R1 corrections (AC5, AC7, AC18 reframed as regression pins; AC9 / AC10 / AC21 line-number corrections) are binding. R2 corrections (AC10 placeholder naming, AC11 glob ambiguity, AC12 --resume+--augment coupling, AC13 shared validator) are binding.
- **Step 11 security verify checklist MUST include**:
  1. **T1 (resume-ID path traversal):** grep confirms ONE `_validate_run_id` definition at `src/kb/mcp/app.py`; both `src/kb/cli.py::lint` and `src/kb/mcp/health.py::kb_lint` import it; regex is `^[0-9a-f]{8}$`; glob-metachar / `..` / `/` / `\\` all rejected; empty-string bypass works; AC12 UsageError fires for `--resume` without `--augment`; AC13 returns `"Error: ..."` string for invalid input.
  2. **T2 (manifest RMW race):** `compile/compiler.py` — BOTH the full-mode tail at lines 424-437 AND the exception-path at lines 414-419 are inside `file_lock(manifest_path)`. Threading regression test survives concurrent writer.
  3. **T3 (AC1 prune base):** `compile/compiler.py:431` uses `raw_dir.resolve().parent`, not `raw_dir.parent`. AC2 regression test parametrizes default / relative / absolute / non-"raw" `raw_dir.name` (Q7 option b).
  4. **T4 (capture two-pass partial reservation):** Phase 1 reserves ALL N hidden-temp `.{slug}.reserving` files before Phase 2; partial-failure unlinks all previously-reserved temp files; Phase 3 atomic-renames via `os.replace`. `captured_alongside` matches finalized slugs under collision monkeypatch.
  5. **T5 (.data/ingest_log.jsonl unbounded growth):** new file has 500KB rotation mirroring `wiki_log.py._rotate_log_if_oversized`; rotation inside `file_lock(log_path)` from day one; `wiki_log.py` NOT retrofitted this cycle (BACKLOG entry added).
  6. **T6 (correlation ID overridable):** `ingest_source` signature has NO `request_id` kwarg; grep confirms `uuid.uuid4().hex[:16]` generated at the entry and never seeded from input.
  7. **T7 (.jsonl JSON injection):** write is `fh.write(json.dumps(record, ensure_ascii=False) + "\n")`, not f-string concat. Regression test with `"test\nevil"` filename asserts `json.loads(line)` succeeds.
  8. **T8 (lazy-import regression):** `tests/test_mcp_lazy_imports.py` passes for all four MCP submodules with a `sys.modules`-reset fixture; denylist is single source of truth.
  9. **T9 (ReDoS):** each title `re.escape`'d; soft cap 200; regression test with 100 titles × 10KB body under 5 sec.
  10. **T10 (prefix collision):** validator enforces exact 8-hex-chars; `Manifest.resume` raises on >1 incomplete match.
  11. **T11 (capture prompt path):** loader path is `TEMPLATES_DIR / "capture_prompt.txt"` (hardcoded filename, no caller override). Grep: zero callers pass the filename as a parameter.
  12. **T13 (fixture leakage):** `_kb_sandbox` is NOT autouse; clears three LRU caches (`load_purpose`, `_load_template_cached`, `_build_schema_cached`) on setup AND teardown.

- **Cycle-16 L1 same-class peer scan (Step 11):** For each threat requiring a fix, grep ALL sibling surfaces — the five anchors (A through F) from the threat model must be ticked.
- **BACKLOG entries (to be added in Step 12 docs):**
  1. MEDIUM: `src/kb/utils/wiki_log.py._rotate_log_if_oversized` runs outside `file_lock`; mirrors `.data/ingest_log.jsonl` fix from cycle 17 but not retrofitted (dedicated cycle).
  2. MEDIUM: `src/kb/compile/linker.py::inject_wikilinks` scalar lacks per-page `file_lock` around read-and-atomic-write; batch variant fixed in cycle 17 but scalar preserves parity (dedicated cycle).

---

## FINAL DECIDED DESIGN

Cycle 17 lands 21 ACs across 14 files with three concurrency fixes (AC3 manifest lock symmetry including exception path; AC10 capture two-pass hidden-temp reservation with all-or-nothing rollback; AC21 batch linker with per-page locks), one path-traversal defense (AC11/12/13 shared `_validate_run_id` regex `^[0-9a-f]{8}$` enforcing exact 8-char match, UsageError when `--resume` lacks `--augment`, `Manifest.resume` raises on >1 match), one observability surface (AC19 `.data/ingest_log.jsonl` with locked-rotation from day one, `json.dumps` encoding, structurally non-overridable `uuid.uuid4().hex[:16]` correlation ID), five lazy-import regression pins (AC4-AC7 test file with per-test `sys.modules`-reset fixture; AC5 / AC7 reframed as pins because R1 grep confirmed code already deferred), four test-infra additions (AC14 purpose-threading integration; AC15 three-scenario e2e; AC16 opt-in `_kb_sandbox` fixture clearing three LRU caches; AC17 15-test MCP thin-coverage), one dead-code decision (AC8 keep `WikiPage`/`RawSource` dataclasses with module-docstring contract, tests already pin), one ingest helper extraction (AC20 `_write_index_files` with documented ordering), one capture prompt externalization (AC9 `templates/capture_prompt.txt` loaded once at module init), and one pure regression pin (AC2 parametrized across 4 raw_dir shapes, AC18 `load_purpose` env-var independence). Two MEDIUM pre-existing bugs (wiki_log rotation race, scalar linker clobber race) are filed to BACKLOG for dedicated cycles, preserving cycle-17's batch-by-file scope discipline.
