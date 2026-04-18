# Cycle 10 Design Eval — Round 1 (Scope / Framing / Assumptions)

**Date:** 2026-04-18
**Reviewer role:** R1, eval against Step 1 acceptance criteria.
**Inputs read:** requirements.md (28 ACs), threat-model.md (CHECKLIST + 15 threats), brainstorm.md
(8+1 commit shape), plus grep-verified source: `mcp/app.py`, `lint/_safe_call.py`, `mcp/browse.py`,
`mcp/health.py`, `mcp/quality.py`, `capture.py`, `query/hybrid.py`, `ingest/pipeline.py`,
`BACKLOG.md` Phase 4.5 sections.

## Analysis

The requirements doc and the threat-model doc are **not internally consistent** — a show-stopper
for the Step 5 gate if not resolved. The requirements doc defines 28 ACs across 13 files;
the threat-model header declares "33 ACs across 16 files" and its CHECKLIST cites AC numbers
up to AC33 (T8 references AC28/AC29 for wiki_log torn-line tests, T9 references AC32/AC33,
T14 references a new `_safe_call` in `kb.mcp.app`). None of those ACs exist in the 28-item
set I was asked to score. The requirements doc *explicitly* declares `wiki_log.py` torn-line
"STALE. Dropped from AC set" (see the Grep-verified baseline at lines 31-34), yet the
threat-model treats it as AC12/AC13/AC28/AC29. Either the threat-model was written against
an older draft or the requirements doc stripped ACs without updating the threat-model. Both
docs must renumber before plan gate, because otherwise Step 7 plan items will reference
non-existent ACs and Step 11 verification will hunt for ghost tests.

On scope framing: the cycle is correctly sized at 28 ACs / 8-9 commits — roughly matching
cycle 9's 18 and cycle 8's 11 — and the "close cycle-9 `_validate_wiki_dir` scope-out on
the 4 remaining MCP tools" framing is exactly the pattern I was asked to watch for under
the cycle-8 same-class-completeness Red Flag. Grep confirms `_validate_wiki_dir` exists at
`mcp/app.py:187`, is already used by `core.py:624` and `health.py:56,116`, and the 4 migration
targets (`kb_stats` at `browse.py:319`, `kb_graph_viz` at `health.py:150`,
`kb_verdict_trends` at `health.py:185`, `kb_detect_drift` at `health.py:210`) are the
complete residual set per BACKLOG.md:285-286 (cycle 9 deferred exactly these four).
Same-class-completeness is satisfied here: no fifth `wiki_dir`-accepting tool exists
(grepped `def kb_[a-z_]+` + `wiki_dir: str | None` — returns exactly the 4 migration targets
plus the 2 already-migrated tools). That is a clean batched close of the cycle-9 gap.

However, two other ACs carry a *new* same-class-completeness gap that should be flagged.
AC1 applies `_safe_call` at `quality.py:103-110` (the `build_backlinks` try/except), but
BACKLOG.md:256 explicitly lists TWO other silent-degradation sites: `mcp/core.py:108-117`
and `mcp/quality.py:282-283` (the latter in `kb_save_lint_verdict`). The AC1 scope-out
mirrors cycle 7 → cycle 10 exactly: cycle 7 addressed `verdict_history` + `feedback_flagged_pages`
only, cycle 10 now addresses `build_backlinks` only, leaving `mcp/core.py:108-117` and
`quality.py:282-283` as a cycle-11 deferred item. Similarly, AC13's `_coerce_str_field`
is explicitly scoped to `_build_summary_content` only, leaving "10+ read sites" per
BACKLOG.md:229 unmigrated. The requirements doc itself calls out this scope-out at
lines 196-198 ("Scope is INTENTIONALLY LIMITED … Phase 4.5 MEDIUM's '10+ read sites' is
tracked for follow-up"). Intentional is better than accidental, but the Red Flag question
is whether the gap is a *security gap* (must close now) vs a *correctness/coverage gap*
(deferrable). AC13's scope-out is correctness-class (malformed extraction at non-summary
sites still crashes mid-ingest, same state-store fan-out hazard) — that argues for
widening. AC1's scope-out is observability-class (still silently degrades at `mcp/core.py`)
— deferrable. Document the reasoning in the AC text so a future reviewer doesn't have to
reverse-engineer it.

## Scope verdict

**APPROVE-WITH-REVISIONS.** The batch is well-shaped and the 4-tool `_validate_wiki_dir`
closure is genuinely security-positive. Three issues block APPROVE outright: (1) requirements
doc vs threat-model AC numbering divergence, (2) AC1 silent-degradation scope-out leaves two
other sites open with no stated rationale, (3) AC13 extraction-validation scope-out risks
repeating the cycle-9 pattern of "helper applied at 1 site, 10 sites still at risk". All
three are fixable pre-plan-gate.

## Per-AC notes

- **AC1** (silent-degradation at `quality.py`): scope-out is unmotivated. BACKLOG.md:256
  lists 2 other sites (`mcp/core.py:108-117`, `quality.py:282-283 kb_save_lint_verdict`).
  Revision: either split into AC1a (`kb_refine_page`), AC1b (`mcp/core.py`), AC1c
  (`kb_save_lint_verdict`) — all 3 get `_safe_call` — or add one sentence to AC1 stating
  the other 2 sites are observability-class and deferred to cycle 11 with a BACKLOG line
  pinning the deferral. My preference: split, because `_safe_call` is already imported
  in the package (`health.py:8` uses it); adding 2 more call sites is a one-line diff
  per site.

- **AC1** (error-surface sanitisation): threat T1 flags that `_safe_call` returns raw
  `str(exc)` which can leak absolute paths / API keys. AC1 as written does NOT require
  running the error through `_sanitize_error_str`. Revision: add a sentence — "the `err`
  string returned by `_safe_call` MUST pass through `_sanitize_error_str(exc)` in the
  caller before interpolation into the response string". Alternatively, upgrade
  `kb.lint._safe_call._safe_call` itself to route the exception through `_sanitize_error_str`
  before building the error message (centralised fix). Either works; pick one.

- **AC8** (`hybrid_search` vector-score floor): the requirements doc's dependency
  section at lines 344-348 explicitly flags that if `vector_fn`'s `score` field is
  *distance* rather than *similarity* the threshold comparison direction must flip.
  This ambiguity is load-bearing and unresolved. Revision: Step 7 plan MUST include a
  grep task against `kb.query.embeddings.VectorIndex.query` to confirm the `score` field
  is cosine similarity (higher = better). If it is distance (lower = better), AC8 text
  must flip `>=` to `<=` and AC22/AC23 must swap expected values. Don't merge until
  verified.

- **AC9** (detect_source_drift docstring): the fix is documentation-only, but the
  underlying issue per BACKLOG.md:246-247 is that the function *violates its advertised
  read-only contract*. AC9 accepts the side-effect as intentional and documents it, which
  is a valid choice, but it means the `save_hashes=False` kwarg becomes misleading.
  Revision: consider renaming the kwarg to `save_template_hashes` in a follow-up AC, OR
  include a `prune_deleted=True` default-true kwarg in the docstring so readers see both
  knobs. The doc-only fix is acceptable for cycle 10; flag the rename as a BACKLOG item
  so it doesn't get forgotten.

- **AC10** (UUID boundary): the `CaptureError` raise after 3 regenerations is correct
  but the threat-model T6 notes that under tests that monkeypatch `secrets.token_hex` to
  a deterministic value, the collision-retry loop will deterministically loop until the
  cap. Revision: AC24's test mocks `secrets.token_hex`; ensure the mock returns a value
  that does NOT appear in the content so the loop never retries. If the intent is to
  test the retry path, add an explicit AC10b test that forces collision and asserts the
  raise.

- **AC11** (`captured_at` at submission time): the fix location per the requirements doc
  is "immediately after `_resolve_provenance(...)` at line 668". Grep of `capture.py`
  confirms `_resolve_provenance` is at line 668 and `captured_at` is currently at line
  726. BUT between 668 and 726 there are FOUR early-return paths (empty input,
  secret-scan, rate-limit, none-check) — each of those currently returns a `CaptureResult`
  with NO `captured_at` field. If AC11 moves `captured_at` to line 669, those early
  returns don't use it, which is fine. However the AC text should note: `captured_at` is
  only consumed by `_write_item_files` (line 728), so moving it earlier has no
  side-effect on the rejection paths. Verify and document.

- **AC13** (`_coerce_str_field` at `_build_summary_content` only): Red Flag per cycle-8
  same-class-completeness. BACKLOG.md:229 says "reuse for all 10+ read sites". AC13
  deliberately scopes to `_build_summary_content` (~10 sites narrow to 3: title, author,
  core_argument) and defers the rest. This is the cycle-9 pattern repeating. Revision:
  split AC13 into AC13a (cycle 10: `_build_summary_content` sites) and AC13b (BACKLOG
  item: migrate remaining sites with pointer to `_build_item_content` at pipeline.py:395
  + 10 extraction-field read sites at pipeline.py:157, 162-163, 180, 186-188). At
  minimum AC13 text needs an inline note in `CHANGELOG.md` linking the deferral so R1 of
  cycle 11 doesn't have to re-discover it.

- **AC22/AC23** (vector-score tests): these tests build a fake `vector_fn` returning
  `{"score": 0.1}` etc. They do NOT exercise the real `VectorIndex.query` backend. If
  AC8's threshold direction is wrong (distance vs similarity, see AC8 note), these
  tests pass under the wrong threshold because the test data is synthetic. Revision:
  add an AC23b integration test that runs `hybrid_search` with a real `VectorIndex`
  seeded with 2 known-cosine-similarity vectors and asserts the threshold behaviour
  against the REAL scoring semantics. Without this, AC22/AC23 are signature-only tests
  per the `feedback_inspect_source_tests` Red Flag.

- **AC26** (non-string extraction field rejection): the test asserts `os.listdir(tmp_wiki
  / "summaries")` is empty after the exception. But AC13 only migrates the
  `_build_summary_content` sites — the validation happens DURING summary rendering,
  AFTER `raw_dir` source hash checks + BEFORE entity/concept page writes. If entity
  writes happen before summary (check pipeline.py ordering), the empty-summaries check
  passes but entity pages might already be written. Revision: extend AC26 to assert
  BOTH `summaries/` AND `entities/` AND `concepts/` are empty after the exception.

- **AC28** (CHANGELOG/BACKLOG/CLAUDE.md doc pass): note that the stale BACKLOG lines per
  requirements.md:31-36 ("torn-last-line under concurrent append"; "kb_search stale flag
  NOT surfaced"; kb_search length cap) must be DELETED (per `automation/backlog-lifecycle`
  convention), not marked resolved. The AC28 text says "deletes the resolved items" but
  does not enumerate the STALE-but-not-fixed items. Revision: explicitly list in AC28
  that BACKLOG lines about torn-last-line + `kb_search` stale + `kb_search` cap are
  deleted with a CHANGELOG note that they were discovered STALE during cycle 10 scope
  review (so the audit trail is visible).

## Open questions

1. **Requirements vs threat-model numbering divergence.** Threat-model cites AC28/AC29/
   AC32/AC33 and a new `_safe_call` in `mcp/app.py` that don't exist in the 28-AC set.
   Options: (a) regenerate threat-model against the final 28-AC requirements doc before
   Step 7 plan, (b) expand requirements doc to 33 ACs to match threat-model, (c) accept
   the mismatch and have Step 7 plan explicitly note which threat-model items map to
   which AC. My preference: (a). The requirements doc is canonical per the Step 1 gate.

2. **`_safe_call` home: `kb.lint._safe_call` vs new `kb.mcp.app._safe_call`.** Threat T14
   flags potential import drift if two helpers exist. The requirements doc AC1 imports
   from the existing `kb.lint._safe_call`. Threat-model analysis paragraph 2 discusses
   adding to `mcp/app.py`. Options: (a) use existing `kb.lint._safe_call` at quality.py
   (requirements doc position), (b) create new `kb.mcp.app._safe_call` that wraps
   `_sanitize_error_str` and re-export from `kb.lint._safe_call`, (c) upgrade
   `kb.lint._safe_call` to take an optional `sanitize_paths: tuple[Path, ...]` kwarg
   that routes through `_sanitize_error_str`. My preference: (c) — single helper,
   opt-in sanitisation, no import drift.

3. **AC8 vector score semantics: similarity vs distance.** Requirements doc flags this
   as "plan step 1 must grep `VectorIndex.query`". Options: (a) block plan until the
   grep lands, (b) ship AC8 with a `VECTOR_MIN_SIMILARITY` guard expressed as
   `>= 0.3` and write a plan step 1 task to verify empirically (if empirical shows
   distance, flip the constant to `VECTOR_MAX_DISTANCE` and invert the comparison),
   (c) make the gate configurable — both `VECTOR_MIN_SIMILARITY` and
   `VECTOR_MAX_DISTANCE` exist, and `hybrid_search` picks based on the backend's
   declared semantics. My preference: (a) — don't merge code until the semantics are
   confirmed, this is an auditable 5-line grep.

4. **AC13 scope-out: defer vs widen.** 3 sites migrated, 10+ remain. Options: (a) accept
   the scope-out, add a BACKLOG entry pinning the 10+ remaining sites as a cycle-11
   followup (cycle-9 pattern), (b) widen AC13 to all 10+ read sites this cycle (doubles
   the diff but closes the class), (c) add AC13 `isinstance` assertion in a module-level
   `_validate_extraction_dict(extraction)` front-door helper that runs once at top of
   `ingest_source` and validates ALL string fields — one site, complete coverage. My
   preference: (c) — single-point validation before any filesystem write, which is the
   spirit of "fail-fast" per threat T9.

5. **AC11 `captured_at` moves vs early-return paths.** Requirements says move the
   timestamp to line 669 (right after `_resolve_provenance`), but 4 early-return paths
   (empty input, secret, rate-limit, none-check) build `CaptureResult` between 669 and
   726 without using `captured_at`. Options: (a) accept that `captured_at` is only on
   the success path (no change to rejection results), (b) add `captured_at` to ALL
   return paths so `CaptureResult.items[*]["captured_at"]` is always populated, (c)
   rename to `submitted_at` on the top-level `CaptureResult` (not per-item) so the
   semantic is obviously submission-time. My preference: (a) — the AC is about the
   success-path timestamp, rejections already have `rejected_reason` as the evidence
   of when the decision was made.

## Recommended additions

- **New AC (BACKLOG one-line fix, cycle-10 candidate):** `compile/linker.py:219-220`
  `inject_wikilinks` silent pipe→em-dash substitution (BACKLOG.md:138-139). This is a
  data-loss-class bug (title `"A|B"` silently becomes `"A—B"` on ingest); it's a one-line
  diff (replace `.replace("|", "\u2014")` with either a raise or a bracket-escape helper).
  Low blast radius, same-file as cycle 10's `compiler.py` docstring touch. Would fit
  between AC9 and AC10 at zero additional risk.

- **New AC (threat model gap):** threat-model does not cover the case where
  `_validate_wiki_dir` is called with a `wiki_dir` that is a SYMLINK to outside
  `PROJECT_ROOT`. Current implementation at `app.py:200` calls `.resolve()` which follows
  symlinks — so `wiki_dir=/tmp/evil_symlink` where `evil_symlink -> /etc/passwd` would
  resolve to `/etc/passwd` and pass the `is_dir()` check if `/etc/passwd` were a dir.
  The existing implementation accepts this (`.resolve()` is correct; the symlink target
  is what matters), but the threat-model should document that reliance on `.resolve()`
  means the security boundary is the resolved target, not the input string. Not a code
  change, just a threat-model addition so future readers don't "harden" by removing
  `.resolve()`.

- **New threat (missed by threat-model):** AC11's move of `captured_at` to line 669
  means that if `_extract_items_via_llm` fails with an exception (LLMError, network),
  `captured_at` was already computed but no `CaptureResult` carrying it is produced —
  the exception propagates. Currently, captured_at is post-LLM, so a rejected-via-
  exception capture has no timestamp at all, which is fine. After AC11, the timestamp
  exists in a local variable that never surfaces. No bug, but if a future AC wants to
  log `captured_at` in the exception path (say, for rate-limiting telemetry), the
  timestamp is now available — document this as a forward-compatibility win.

- **BACKLOG pickup suggestion (NOT for cycle 10, for cycle 11):** `review/refiner.py`
  write-then-audit ordering (BACKLOG.md:160). This has been deferred from Phase 4.5
  HIGH cycle 1 and cycle 10 doesn't touch it. Flag as next-cycle priority because
  it's a data-integrity bug (page mutated without audit record on OSError).
