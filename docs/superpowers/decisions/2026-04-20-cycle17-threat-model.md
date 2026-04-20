# Cycle 17 — Threat Model (Opus subagent, Step 2)

**Date:** 2026-04-20
**Scope:** 21 ACs across 14 files (see `2026-04-20-cycle17-requirements.md`).
**Baseline reference:** Dependabot 0 alerts as of cycle 16; pip-audit 1 informational (`diskcache==5.6.3` CVE-2025-69872 unpatched upstream, documented). No new third-party deps introduced.

---

## Analysis

Cycle 17 is a batch-by-file cycle with **no architectural surface change**, so the threat profile is dominated by **existing enforcement patterns that must not regress** and **three net-new attacker-influenceable inputs**.

Four distinct attack classes map to specific ACs:

- **Resume-ID as filesystem directory name (AC11/AC12/AC13).** `run_augment(resume=...)` takes a user-controllable string, and `_augment_manifest.Manifest.resume(run_id_prefix=...)` feeds it directly to `resolved.glob(f"augment-run-{run_id_prefix}*.json")`. `Path.glob()` treats `*`/`?`/`[...]` as glob wildcards and lets the caller traverse up via `..` components embedded in the format-string prefix. This is the **primary new attack surface**. The cycle-4 `_validate_page_id` helper in `src/kb/mcp/app.py` is the reference pattern — any looser check (only a length cap, trusting slugify alone, or trusting that `{run_id_prefix}*.json` "can't" escape because it's a fixed suffix) is exploitable, because `f"augment-run-../../../etc*.json"` is a perfectly valid string that resolves against `resolved.parent.parent.parent/`. AC12 (CLI) and AC13 (MCP) MUST share a single regex validator with identical character class, length cap, and reject-ordering, applied BEFORE the string ever reaches `Path.glob`, `_augment_manifest`, or any log message.

- **Correlation ID as log/markdown/JSON field (AC19).** `request_id = uuid.uuid4().hex[:16]` is machine-generated and not attacker-controlled at this site, **but** the threat model must pin the invariant that it stays generated locally (never seeded from a HTTP header or environment variable). The log prefix `[req=<id>] <existing>` enters `wiki/log.md` (markdown audit ledger), a new `.data/ingest_log.jsonl` file (JSON per-line), and `logger.warning(...)` prefixes. Each surface has different injection semantics: markdown attack = heading/list/callout injection (already defended by `_escape_markdown_prefix` in `src/kb/utils/wiki_log.py:70-81`); JSONL attack = ensure `json.dumps(..., ensure_ascii=False)` + `json.dumps` of the whole record, not concatenation; logger attack = CRLF splitting (Python stdlib `logger.warning` does not auto-escape). AC19 must use `json.dumps` for the full record line and must NOT f-string interpolate `request_id` into non-escaped contexts.

- **Concurrency races (AC3 + AC10).** AC3 wraps the full-mode tail "reload + prune + save" in `file_lock(manifest_path)`. The threat is a **missing lock** that lets a concurrent `kb_ingest` have its entry pruned between the load and save. AC10 is capture's two-pass write — the CRITICAL R3 bug: Phase 1 must `O_EXCL`-reserve all N slugs BEFORE Phase 2 computes `alongside_for`. The threat is a **partial reservation** — if any slug reservation fails, the code must roll back all previously-reserved slugs (otherwise a race leaves orphaned 0-byte `.md` files in `raw/captures/`). Both ACs touch lock-ordering convention documented in `src/kb/utils/io.py:5-12`.

- **Resource exhaustion from unbounded append-only files (AC19).** `.data/ingest_log.jsonl` is append-only per call with no rotation. The existing `wiki/log.md` has `_rotate_log_if_oversized` at 500KB threshold. AC19 introduces an unbounded-growth surface — if 100k ingests run, the file can reach ~50MB and degrade subsequent write performance. Design gate must decide: (a) add the same 500KB rotation to `.jsonl`, (b) accept as bounded by ingest throughput and document, or (c) document that external tooling (logrotate) owns retention.

Other concerns (lazy imports, dead code, helper extraction) are **reversibility-safe refactors** without new attack surface. The lazy-import ACs (AC4-AC7) can only regress availability, not security — pytest import-absence assertions are the safety net.

Cycle-16 L1 ("same-class peer scan"): any fix that adds a path-containment check MUST be grepped across all three boundaries (`src/kb/mcp/app.py`, `src/kb/mcp/core.py`, `src/kb/lint/augment.py`) to avoid leaving asymmetric validators. Same for the resume-ID regex (two call sites: CLI + MCP).

---

## 1. Trust boundaries

| # | Boundary | Input enters at | Produced by | Current validation | Cycle 17 adds |
|---|---|---|---|---|---|
| TB1 | MCP tool call → library | `kb_lint(resume=...)` in `src/kb/mcp/health.py` | MCP client (Claude Code, or any local HTTP client that can reach FastMCP) | Empty-string sentinel only (new surface; current `kb_lint` has no resume param) | AC13 — must add regex validator + length cap before forwarding |
| TB2 | CLI arg → library | `kb lint --resume <id>` in `src/kb/cli.py` | Shell / invoking user | None (new surface) | AC12 — same regex validator as AC13, shared module constant |
| TB3 | `Manifest.resume()` → filesystem glob | `run_id_prefix` in `src/kb/lint/_augment_manifest.py:100-113` | `run_augment(resume=...)` caller chain | None — `Path.glob(f"augment-run-{prefix}*.json")` | Input must be pre-validated by AC11 before reaching this line |
| TB4 | `ingest_source()` start-of-body | New `request_id = uuid.uuid4().hex[:16]` at `src/kb/ingest/pipeline.py:819` | Locally generated — `uuid.uuid4()` (OS CSPRNG) | N/A (locally generated, not attacker-controlled) | AC19 — MUST stay locally generated; never seeded from env/headers |
| TB5 | `wiki/log.md` append | `append_wiki_log(operation, message, log_path)` in `src/kb/utils/wiki_log.py` | `ingest_source` + callers | `_escape_markdown_prefix` strips/ZWSP-prefixes `#`/`-`/`>`/`!`/`[[` | AC19 — correlation ID becomes part of `message`; existing escape covers it (no new filter needed), but regression risk if the ID is appended AFTER escape |
| TB6 | `.data/ingest_log.jsonl` append | New at `ingest_source` tail | Locally generated record dict (no user content?) | N/A (new surface) | AC19 — MUST `json.dumps` the full record; must NOT concatenate attacker-influenceable fields (source_ref is derived from validated `source_path`; record body includes source_ref) |
| TB7 | Compile manifest RMW | `compile_wiki(incremental=False)` tail at `src/kb/compile/compiler.py:424-437` | Compile runner | Per-source `file_lock` at ingest, NONE at full-mode tail prune | AC3 — add `file_lock(manifest_path)` around reload+prune+save |
| TB8 | `raw/captures/<slug>.md` | `_write_item_files` in `src/kb/capture.py:555-651` | `capture_items` → scan-tier LLM extraction | `_is_path_within_captures` resolve+containment; `_exclusive_atomic_write` O_EXCL | AC10 — Phase 1 reservation for ALL slugs before Phase 2; must roll back on partial failure |

**No new cross-process / cross-user boundaries** introduced by cycle 17. All boundaries are local/single-user.

---

## 2. Data classification

| New filesystem write | Path | Classification | Retention | Contains |
|---|---|---|---|---|
| **Ingest correlation log** (AC19) | `.data/ingest_log.jsonl` | **Local-only** (gitignored under `.data/`) | Unbounded unless rotation added (see Design gate) | `request_id`, timestamp, `source_ref` (relative path), `pages_created/updated/skipped`, `affected_pages`, `wikilinks_injected`, `contradictions` count, `duplicate` bool |
| **Augment run manifest** (already exists, AC11 re-activates) | `.data/augment-run-{run_id[:8]}.json` | Local-only | Per-run, kept for audit | run state machine per gap |
| **Augment runs index** (already exists) | `.data/augment_runs.jsonl` | Local-only | Unbounded (existing surface) | summary line per completed run |

No new (c) credentials/PII channels. The `ingest_log.jsonl` may contain `source_ref` which reveals filenames operators placed in `raw/` — no different sensitivity from `.data/hashes.json` which already stores the same refs.

**Retention policy (DESIGN GATE required):** `.jsonl` growth is unbounded. Three choices:
- (a) Mirror `_rotate_log_if_oversized` at 500KB threshold (matches `wiki/log.md` behavior).
- (b) Accept unbounded; document that external logrotate owns retention.
- (c) Cap file size and abort writes when exceeded.

Recommendation: **(a)** for parity with existing audit file. Step-5 design gate decides.

---

## 3. AuthN / AuthZ

Project has **no user authentication** — MCP server binds localhost (FastMCP default stdio transport or HTTP local). Trust model is: the local process owner has full rights over all KB state.

| Guarantee | Source | Cycle 17 change |
|---|---|---|
| Local-process-only trust | No network auth; FastMCP stdio/local binding | Unchanged |
| Input authenticity from the MCP/CLI client | None — any client reaching the transport can call any tool | Unchanged |
| Per-tool input validation | `_validate_page_id`, `_validate_wiki_dir`, `_validate_notes`, `_validate_file_inputs` | Must add `_validate_run_id` (new) shared across CLI + MCP |
| Path traversal refusal | `_validate_page_id` rejects `..`, abs paths; `_rel` redacts; `_is_path_within_captures` resolve-check | Must extend to AC12/AC13 run-id input before it reaches `Path.glob` |

**Threat model stance on compromised MCP client:** If an attacker gains arbitrary MCP tool access (e.g. by compromising Claude Code or injecting tool calls via prompt injection in a page), they can trigger `kb_lint(resume="<payload>")`. Therefore **server-side validation at TB1 is load-bearing** — the MCP client cannot be trusted to pre-validate.

---

## 4. Logging / audit

AC19 introduces **three logging surfaces** for the correlation ID:

1. **`wiki/log.md` markdown prefix** (`[req=<id>] <existing message>`).
   - Injection class: markdown (headings, list, callouts, wikilinks).
   - Existing defense: `_escape_markdown_prefix` in `src/kb/utils/wiki_log.py:70-81` strips `|\n\r\t` and ZWSP-prefixes leading markers.
   - **Cycle 17 invariant:** The correlation ID is hex16 from `uuid.uuid4()` — structurally cannot contain markdown metachars. Regression risk: if a future edit lets a caller override `request_id` (e.g. from an HTTP header), the escape must still run. **Verification checklist:** confirm no code path writes `[req=<caller-controlled>]` without going through `_escape_markdown_prefix`.

2. **`.data/ingest_log.jsonl` JSON per-line**.
   - Injection class: JSON (field injection, newline in string).
   - Defense: `json.dumps(record, ensure_ascii=False)` + `"\n"` terminator (one record per line). `json.dumps` handles quote/backslash/newline escaping.
   - **Verification checklist:** the write MUST be `fh.write(json.dumps(record) + "\n")`, NOT `fh.write(f'{{"request_id": "{request_id}", ...}}')` (string concat defeats escaping).

3. **Python logger warning prefix** (`[req=<id>] msg`).
   - Injection class: log-injection via CRLF in format args.
   - Defense: `request_id` is hex16, so CRLF is structurally impossible. Regression risk: if future edits format `message` too, and `message` contains user content, CRLF injection becomes possible.
   - **Verification checklist:** correlation ID is prepended to the format string, not user input.

**Correlation-ID-as-log-injection assessment:** LOW severity as-designed (uuid4.hex is opaque hex), HIGH severity if the ID ever becomes caller-overridable. Step-11 must verify `uuid.uuid4().hex[:16]` is hardcoded at the generation site and the parameter does not accept a kwarg override.

---

## 5. Top threats (ranked by severity)

### HIGH severity

#### T1 — Resume ID path traversal via `Path.glob` (AC11/AC12/AC13) — HIGH
**Attack:** `kb lint --resume "../../../"` or `kb_lint(resume="..")` reaches `Manifest.resume(run_id_prefix="..")`, where `resolved.glob(f"augment-run-..*.json")` iterates files matching the literal `augment-run-..*.json` pattern in `.data/`. More critically, a slash-containing input like `resume="../secret/run"` hits `f"augment-run-../secret/run*.json"` which `Path.glob` interprets relative to `.data/` and can escape (`glob` traverses `..` in patterns on POSIX; on Windows the behavior is path-dependent).
**Which AC introduces:** AC11 opens the surface; AC12 + AC13 expose it.
**Verification checklist:**
- Input validation: shared regex `^[a-zA-Z0-9_-]{1,64}$` applied in CLI AND MCP BEFORE forwarding.
- Path traversal: verify `resume` rejected if it contains `..`, `/`, `\\`, or any glob metachar (`*`, `?`, `[`, `]`).
- Consistent rejection across both surfaces (same error prefix).
- Length cap at 64 chars (manifest run_id is 36-char UUID; prefix max is full UUID).
- Empty-string sentinel = "no resume" (not validated; forwarded as `None` to library).

#### T2 — Full-mode prune RMW race drops live manifest entries (AC3) — HIGH
**Attack:** Concurrent `kb_ingest` during `compile_wiki(incremental=False)` finalize. Ingest writes `manifest[X] = hash`; compile-finalize loads manifest, iterates `stale_keys` (X not yet in its snapshot's files-on-disk map — or more subtly, prune logic at line 431 uses `raw_dir.parent / k` which fails path resolution under relative `raw_dir`), deletes X, writes.
**Which AC introduces:** Already-open bug; AC3 closes it.
**Verification checklist:**
- Concurrency races: `file_lock(manifest_path)` wraps the load+prune+save block.
- Lock ordering: manifest_path is last in the documented order (`VERDICTS → FEEDBACK → REVIEW_HISTORY → ... → manifest`), so no deadlock.
- Regression test: `threading.Thread` performs ingest reservation while main thread runs full-mode compile-finalize; both writes survive.

#### T3 — AC1 prune base off-by-one: relative `raw_dir` produces false-positive prune-all (AC1) — HIGH
**Attack:** Caller passes `raw_dir = Path("raw")` (relative). Line 431 computes `raw_dir.parent / k` = `. / "raw/articles/foo.md"` = `raw/articles/foo.md`. On any CWD that isn't PROJECT_ROOT, `.exists()` returns False → ALL manifest entries get pruned. Data-integrity attack achievable via misconfiguration, not adversarial, but impact is catastrophic (next compile re-ingests everything, potentially corrupting pages with re-extraction drift).
**Which AC introduces:** Existing bug; AC1 closes it.
**Verification checklist:**
- Input validation: verify `raw_dir.resolve().parent / k` on line 431.
- Output encoding: resolved path matches `_canonical_rel_path`'s base.
- AC2 regression test pins `make_source_ref == _canonical_rel_path` contract.

#### T4 — Capture two-pass partial-reservation leaves orphan `.md` reservations (AC10) — HIGH
**Attack:** Cross-process collision during Phase 1 O_EXCL: writer A reserves slugs 1..5, writer B races on slug 3. A must retry slug 3 OR roll back slugs 1-2-4-5. If rollback is missing, orphan `.md` reservations accumulate in `raw/captures/`.
**Which AC introduces:** AC10 CRITICAL R3.
**Verification checklist:**
- Concurrency races: Phase 1 reserves ALL N slugs BEFORE Phase 2; on ANY Phase 1 failure, previously-reserved slugs are unlinked.
- Atomicity: `_exclusive_atomic_write` already combines `O_EXCL` + temp-rename; preserve that.
- Post-AC10: `captured_alongside` in every file points at only finalized slugs (no stale references to reassigned ones).
- Regression test: monkeypatched collision forces Phase C reassignment and asserts all final `captured_alongside` lists match written slugs.

### MEDIUM severity

#### T5 — `.data/ingest_log.jsonl` unbounded growth (AC19) — MEDIUM
**Attack:** 100k ingests over time → 50MB JSONL file → slow appends, filesystem bloat. Not remote-triggerable, but degrades local UX.
**Which AC introduces:** AC19.
**Verification checklist:**
- Resource exhaustion: design-gate choice of rotation policy documented.
- If rotation chosen: reuses `_rotate_log_if_oversized` pattern at 500KB threshold.
- If not: TOP-OF-FILE comment documents operator responsibility.

#### T6 — Correlation ID overridable → log injection (AC19) — MEDIUM
**Attack:** A future edit adds `request_id` as a kwarg to `ingest_source`; caller passes `request_id="evil\n> [!HEADER_INJECT]"`. Downstream log surface gets markdown injection.
**Which AC introduces:** AC19 creates the parameter surface.
**Verification checklist:**
- Injection: correlation ID must be generated inside `ingest_source`, not accepted as parameter.
- Signature check: `def ingest_source(source_path, source_type=None, extraction=None, *, defer_small=False, wiki_dir=None, raw_dir=None, _skip_vector_rebuild=False)` — NO new `request_id` kwarg.
- If future ACs need overridability, require `_escape_markdown_prefix` coverage first.

#### T7 — `.data/ingest_log.jsonl` JSON injection via source_ref (AC19) — MEDIUM
**Attack:** Filename with embedded newline + quote passes through `make_source_ref`. If the AC19 write uses f-string concat instead of `json.dumps`, the record line becomes malformed JSON and downstream tooling (jq, kb_stats) may crash or misparse.
**Which AC introduces:** AC19.
**Verification checklist:**
- Injection: write is `fh.write(json.dumps(record, ensure_ascii=False) + "\n")`.
- Schema: record has fixed keys; no f-string interpolation of any field.
- Regression test: ingest a source with `"test\nevil"` filename; assert the jsonl line is valid JSON via `json.loads`.

#### T8 — MCP cold-boot lazy-import regression breaks lint availability (AC4-AC7) — MEDIUM
**Attack:** N/A (reversibility threat, not adversarial). Wrong deferment order breaks MCP tool at first call instead of at import.
**Which AC introduces:** AC4-AC7.
**Verification checklist:**
- Import validation: `import kb.mcp.<module>` does NOT load `anthropic`, `kb.query.engine`, `kb.ingest.pipeline`, `kb.graph.export`, `trafilatura`, `networkx`.
- Per-tool smoke tests continue passing (tool body imports still resolve).
- No circular-import regression introduced.

#### T9 — AC21 batch linker ReDoS via large alternation regex — MEDIUM
**Attack:** 100 new titles × hostile page body with unicode alternates → compiled alternation pattern with catastrophic backtracking. Python `re` is NFA; alternation without anchoring is safe in practice but bears verification.
**Which AC introduces:** AC21.
**Verification checklist:**
- Input validation: each title passed to `re.escape` before joining.
- No greedy `.*` appended.
- Regression test with 100 titles × 10k-char body asserts completion under 5 sec.

#### T10 — Resume manifest file-glob content mismatch enables cross-run collision (AC11) — MEDIUM
**Attack:** Operator supplies `resume="abc"`; two unrelated runs have run_ids starting with `abc` (birthday paradox at 16 hex chars is negligible, but at 4-char prefix becomes realistic). Wrong manifest gets resumed.
**Which AC introduces:** AC11.
**Verification checklist:**
- Input validation: `Manifest.resume` iterates and picks the FIRST match with `ended_at is None`. Document: "if two incomplete runs share a prefix, behavior is undefined; operator must supply a longer prefix."
- Minimum prefix length: enforce `len(resume) >= 6` in the validator to reduce collision risk.

### LOW severity

#### T11 — AC9 capture prompt template path traversal — LOW
**Attack:** `templates/capture_prompt.txt` moved to `templates/../evil.txt` via operator error. Impact = loaded as prompt.
**Which AC introduces:** AC9.
**Verification checklist:**
- Path containment: loader uses `TEMPLATES_DIR / "capture_prompt.txt"` (hardcoded filename, no caller override).
- No user-supplied template-name parameter.

#### T12 — AC8 decision-gate delete cascades test breakage — LOW
**Attack:** N/A (engineering risk). Removing `WikiPage`/`RawSource` dataclasses may break downstream imports.
**Which AC introduces:** AC8.
**Verification checklist:**
- Dep CVEs: none.
- Signature audit: zero non-test callers confirmed via grep.
- Decision documented in module docstring OR deletion PR includes test migration.

#### T13 — AC16 opt-in fixture leakage into non-using tests — LOW
**Attack:** N/A (test infrastructure). If `_kb_sandbox` is accidentally made autouse, existing 2000+ tests break.
**Which AC introduces:** AC16.
**Verification checklist:**
- Fixture is NOT autouse.
- Non-using tests still see `kb.config.WIKI_DIR == production WIKI_DIR`.
- Fixture monkeypatching uses `monkeypatch.setattr` (auto-reverts on test exit).

---

## 6. Verification checklist (Step 11 input)

Per-AC verification table. Step-11 Codex subagent ticks each item: **IMPLEMENTED / PARTIAL / MISSING**.

| AC | Threat items to verify | Step-11 check |
|---|---|---|
| **AC1** | Prune base uses `raw_dir.resolve().parent`, not `raw_dir.parent`; relative raw_dir no longer false-prunes | Read `compiler.py:431`; grep for any remaining `raw_dir.parent / k`; run `test_cycle17_compile_prune_base.py` |
| **AC2** | Regression test asserts `make_source_ref == _canonical_rel_path` for default/relative/absolute raw_dir | Grep `make_source_ref` and `_canonical_rel_path` in new test; 3 parametrize cases pass |
| **AC3** | Full-mode tail wrapped in `file_lock(manifest_path)`; threading test survives concurrent writer | Read `compiler.py:424-437`; assert `with file_lock(...)` guards reload+prune+save; run threading regression test |
| **AC4** | `import kb.mcp.core` does NOT bring anthropic / kb.query.engine / kb.ingest.pipeline into `sys.modules` | Run `tests/test_mcp_lazy_imports.py::test_core_cold_boot` |
| **AC5** | Same for `kb.mcp.browse` — kb.query.engine / kb.ingest.pipeline / kb.graph.export absent | Run equivalent test for browse |
| **AC6** | Same for `kb.mcp.health` — networkx / kb.graph.export / kb.compile.compiler / kb.lint.runner absent | Run equivalent test for health |
| **AC7** | Same for `kb.mcp.quality` — trafilatura / kb.review.refiner / kb.lint.augment / kb.lint.checks absent | Run equivalent test for quality |
| **AC8** | Zero non-test callers of `WikiPage`/`RawSource`; decision documented in module docstring OR deleted with test migration | Grep `from kb.models.page import`, `WikiPage(`, `RawSource(` across src/; count = 0 in production code |
| **AC9** | `_PROMPT_TEMPLATE` replaced by loader; template path hardcoded under `TEMPLATES_DIR`; test asserts equivalent rendering | Grep `_PROMPT_TEMPLATE =` in capture.py (should only be loader, not string literal); templates/capture_prompt.txt exists |
| **AC10** | **Phase 1 reserves ALL N slugs before Phase 2 computes alongside_for**; partial-failure rollback unlinks reserved slugs; `captured_alongside` matches finalized slugs under collision | Read `_write_item_files`; verify two-phase separation; run two-concurrent-captures regression test |
| **AC11** | `resume: str \| None = None` kwarg re-added; when non-None, `Manifest.resume(run_id_prefix=resume)` called; Phase A skipped; only `incomplete_gaps()` run | Grep `resume=None` in `run_augment` signature; trace through to manifest.resume call; run resume regression test |
| **AC12** | CLI `--resume <id>` with regex validator `^[a-zA-Z0-9_-]{6,64}$`; `..`/`/`/glob-metachars rejected; error message consistent with AC13 | Run `kb lint --resume "../etc"`; assert UsageError; run `kb lint --resume "valid-run-id"`; help output includes `--resume` |
| **AC13** | MCP `kb_lint(resume: str = "")`; same validator as AC12 (SHARED regex constant, not duplicated); `resume="../etc"` returns `"Error: ..."` string (never raises); empty-string sentinel = no resume | Check validator is imported from a shared module (not redefined); run both MCP and CLI against same payloads |
| **AC14** | Purpose-threading integration test: `wiki/purpose.md` under `tmp_wiki`; call `query_wiki(question, wiki_dir=tmp)`; spy asserts `<kb_purpose>` and purpose content in prompt | Read new test; verify spy intercepts `call_llm` at synthesis site |
| **AC15** | `tests/test_workflow_e2e.py` — 3 scenarios pass: ingest→query, ingest→refine→re-query, shared-entity backlinks; `call_llm`/`call_llm_json` mocked at boundary | Run file; 3 test functions pass without real API |
| **AC16** | `_kb_sandbox` fixture **NOT autouse**; monkeypatches all named config paths; documented with usage notes; unused tests unaffected | `pytest tests/conftest.py --collect-only` (if any new autouse appeared, catch here); grep `autouse=True` additions |
| **AC17** | `tests/test_mcp_tool_coverage.py` — 15 tests (5 tools × {happy, validation-error, missing-file}) pass | Run file; count assertions |
| **AC18** | `load_purpose(tmp)` ignores `KB_PROJECT_ROOT` env; test sets env to `/elsewhere` and asserts only `tmp/purpose.md` read | Run regression test |
| **AC19** | `request_id = uuid.uuid4().hex[:16]` generated at entry, NOT an accepted kwarg; `.data/ingest_log.jsonl` append via `json.dumps(record, ensure_ascii=False) + "\n"`; `wiki/log.md` prefix `[req=<id>]` runs through `_escape_markdown_prefix`; logger warnings tagged | Read `ingest_source`; grep `request_id=` in signature — MUST NOT match (structural prevention of T6); verify json.dumps usage; run monkeypatched uuid4 regression test |
| **AC20** | `_write_index_files(wiki_dir, index_entry, sources_entry)` helper extracted; documented ordering (index.md first, then _sources.md); top-of-module comment on recovery semantics; existing `test_ingest.py` full-pipeline test continues passing | Grep helper name; verify callers use helper; existing tests green |
| **AC21** | `inject_wikilinks_batch(new_titles_and_ids, pages)` reads each page once via mock patching counter; pipeline.py:712-721 switches to batch call; per-page `atomic_text_write` semantics preserved | Run regression test with 100 titles × N pages asserting `read_text` call count == N |

---

## 7. Same-class peer scan anchors (cycle-16 L1)

For each threat requiring a fix, grep ALL sibling surfaces for the same anti-pattern. Step-11 MUST scan these anchors across the whole diff:

### Anchor A — Run-ID / slug validator (T1 / AC11-AC13)
**Pattern to grep:** Any new `re.fullmatch(...)` or `.startswith(...)` applied to a user-controllable string that downstream reaches `Path.glob`, `Path.resolve`, or filesystem operations.
**Same-class peers:**
- `src/kb/mcp/app.py::_validate_page_id` (reference pattern — char class, length, `..` reject, Windows-reserved reject)
- `src/kb/mcp/core.py::_validate_save_as_slug` (cycle-16 reference — belt-and-suspenders slug regex + slugify(x)==x)
- `src/kb/mcp/app.py::_validate_wiki_dir` (absolute path + `is_relative_to` PROJECT_ROOT)
- `src/kb/mcp/core.py::kb_ingest` path validation (normcase + relative_to)
- `src/kb/capture.py::_is_path_within_captures` (resolve + relative_to)
- `src/kb/lint/augment.py:561-571` (`_resolve_raw_dir` — wiki_dir/raw_dir derivation convention)
**Enforcement:** AC12 and AC13 MUST import the validator from a single module (recommendation: add `_validate_run_id` to `src/kb/mcp/app.py` alongside `_validate_page_id`). No duplicated regex.

### Anchor B — file_lock around RMW on `.data/*.json*` (T2 / AC3)
**Pattern to grep:** `load_manifest(...)` followed by `save_manifest(...)` WITHOUT a surrounding `file_lock`.
**Same-class peers:**
- `src/kb/compile/compiler.py:424-437` (AC3 site — currently unlocked)
- `src/kb/ingest/pipeline.py:1075-1082` (Phase-2 confirmation — already `file_lock`)
- `src/kb/ingest/pipeline.py::_check_and_reserve_manifest` (Phase-1 reservation — already `file_lock`)
- `src/kb/lint/_augment_manifest.py::advance/close` (already `file_lock`)
- `src/kb/feedback/store.py` (similar pattern; verify)
- `src/kb/lint/verdicts.py` (similar pattern; verify)
**Enforcement:** Step-11 greps `load_manifest|load_feedback|load_verdicts` and verifies every call is either (a) inside `with file_lock(...)`, or (b) read-only with documented exception.

### Anchor C — `json.dumps(..., ensure_ascii=False)` for audit lines (T7 / AC19)
**Pattern to grep:** `.jsonl` writes using f-string concatenation instead of `json.dumps`.
**Same-class peers:**
- `src/kb/lint/_augment_manifest.py:174` (`fh.write(json.dumps(entry) + "\n")` — reference pattern)
- NEW: `ingest_log.jsonl` append site in `ingest/pipeline.py`
**Enforcement:** Grep `fh.write(f'` and `fh.write("{` across all `.jsonl`-writing modules; zero matches.

### Anchor D — Markdown prefix escape coverage (T6 / AC19)
**Pattern to grep:** Writes to `wiki/log.md` that bypass `append_wiki_log` or don't run `_escape_markdown_prefix`.
**Same-class peers:**
- `src/kb/utils/wiki_log.py::append_wiki_log` (reference)
- All call sites: `ingest/pipeline.py`, `compile/compiler.py`, `mcp/quality.py`, `cli.py`, `review/refiner.py`
**Enforcement:** Grep `log.md` writes; all writers go through `append_wiki_log`; none bypass the escape.

### Anchor E — Two-phase atomic reservation (T4 / AC10)
**Pattern to grep:** Any multi-file write that computes cross-references (alongside, backlinks) before the files are finalized.
**Same-class peers:**
- `src/kb/capture.py::_write_item_files` (AC10 site)
- `src/kb/ingest/pipeline.py::_write_index_files` (AC20 extraction — verify ordering is documented)
- `src/kb/compile/linker.py::inject_wikilinks_batch` (AC21 — atomicity per-page; verify batch doesn't introduce new cross-page state)
**Enforcement:** Step-11 verifies each multi-file writer either (a) commits all-or-nothing, or (b) documents partial-failure behavior in docstring.

### Anchor F — Lazy imports to avoid cold-boot heavy load (T8 / AC4-AC7)
**Pattern to grep:** `from kb.<heavy> import ...` at module top in `src/kb/mcp/*.py`.
**Same-class peers:**
- `src/kb/mcp/core.py` (AC4 — currently loads `kb.query.engine`, `kb.ingest.pipeline` at top)
- `src/kb/mcp/browse.py` (AC5)
- `src/kb/mcp/health.py` (AC6 — currently loads `kb.graph.export` at line 7)
- `src/kb/mcp/quality.py` (AC7)
- **Precedent:** `src/kb/mcp/core.py::kb_capture` and other tool bodies already do function-local imports for `kb.feedback`, `kb.compile`, etc.
**Enforcement:** Step-11 compares `sys.modules` after `import kb.mcp.<module>` against a denylist (anthropic, kb.query.engine, kb.ingest.pipeline, kb.graph.export, kb.compile.compiler, kb.review.refiner, kb.lint.augment, kb.lint.checks, networkx, trafilatura).

---

**Threat summary:** 13 threats total — 4 HIGH, 6 MEDIUM, 3 LOW.

**Top-3 items requiring Step-5 design-gate attention:**

1. **T1 (HIGH) — Resume-ID validator design.** Must be shared between AC12 (CLI) and AC13 (MCP). Regex, length cap, empty-sentinel semantics, and error message format must be locked in one module constant. Design question: min-length (6? 8?) to prevent prefix collision (T10). Recommend placing in `src/kb/mcp/app.py::_validate_run_id` (consistent with existing `_validate_page_id`).

2. **T5 (MEDIUM) — `.data/ingest_log.jsonl` rotation policy.** Three options; recommend mirroring `wiki/log.md`'s 500KB rotation (Option a) for consistency. Design must pick one; Step-11 verifies the choice is implemented.

3. **T2 + T3 (HIGH) — Lock + base-path fix ordering in `compile/compiler.py`.** AC3 and AC1 modify the same code block (`compile_wiki` full-mode tail). Design must specify the final shape: `with file_lock(manifest_path):` wraps the entire `load → use resolve().parent prune base → save` block. Verify AC2 regression test covers both changes.
