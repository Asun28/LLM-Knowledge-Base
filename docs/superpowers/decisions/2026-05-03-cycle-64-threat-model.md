# Cycle 64 — Threat Model

**Date:** 2026-05-03
**Author:** Opus 4.7 subagent (Step 2 dispatch)
**Requirements ref:** `docs/superpowers/decisions/2026-05-03-cycle-64-requirements.md` (21 ACs across 6 file domains, Tier 2)
**Branch:** `feat/cycle-64` (worktree `D:/Projects/llm-wiki-flywheel/.claude/worktrees/cycle-64`)
**Base:** `main` @ `d7a98b7`
**Tier:** 2 (standard feature batch — no auth/IAM/crypto/migration; classifier final)

---

## Scope

Cycle 64 touches the following code surfaces. None of these create new EXTERNAL trust boundaries (no new network, IPC, or authn/authz endpoints); all changes are internal to the personal-KB process model. Surfaces marked `*` are existing internal boundaries with NEW behaviour.

**Cluster A — `tests/conftest.py` autouse sandboxing (AC1–AC4, NEW internal boundary):**
- `tests/conftest.py` — new autouse fixture `_isolate_wiki_constants_per_test` redirecting 8 `kb.config.WIKI_*` / `RAW_DIR` / `PROJECT_ROOT` constants per-test.
- `tests/conftest.py` — new opt-in fixture `real_project_root` and CLI option `--use-real-paths`.
- `tests/test_cycle64_conftest_leak.py` (NEW) — 3 regression cases.
- Existing test sites migrated: `tests/test_cli.py:61-63`, write-paths in `test_pipeline.py` / `test_compile.py`, `load_purpose()` reads.

**Cluster B — `src/kb/query/embeddings.py` dim-mismatch auto-rebuild (AC5–AC8):**
- `VectorIndex._derive_wiki_dir()` (NEW method) — promotes the existing line-678 derivation to a primary path with explicit `.tmp` rejection contract.
- `VectorIndex.query()`* — adds an auto-rebuild side effect on dim-mismatch (currently returns `[]` only; AC6 adds a synchronous `rebuild_vector_index(wiki_dir)` call gated on `KB_DISABLE_VECTOR_AUTO_REBUILD`).
- New module-level counter `_dim_mismatch_auto_rebuilds_seen` + getter `get_dim_mismatch_auto_rebuild_count()`.
- `tests/test_cycle64_dim_mismatch_autorebuild.py` (NEW) — 4 cases.

**Cluster C — `src/kb/graph/cache.py` graph cache (AC9–AC12, NEW module):**
- `src/kb/graph/cache.py` (NEW) — `_GLOBAL_CACHE: dict[(wiki_dir_str, max_mtime), nx.DiGraph]`, `_CACHE_LOCK: RLock`, `_MAX_CACHE_SIZE = 4`, `get_graph()`, `invalidate()`, `get_cache_stats()`.
- `src/kb/lint/checks/cycles.py:20`*, `src/kb/lint/checks/orphan.py:27`*, `src/kb/lint/semantic.py:140`*, `src/kb/lint/augment/collector.py:49`*, `src/kb/lint/runner.py:59,96`* — fallback `build_graph(wiki_dir)` calls migrated to `get_graph()`.
- `src/kb/ingest/pipeline.py::ingest_source` — invalidation hook (one-line call before return).
- `src/kb/refine/refiner.py::refine_page` — invalidation hook (one-line call before return).
- `tests/test_cycle64_graph_cache.py` (NEW) — 5 cases.

**Cluster D — `src/kb/compile/publish.py` auto-publish hook + manifest cleanup (AC13–AC17):**
- `src/kb/compile/publish.py::auto_publish_after_compile` (NEW function) — orchestrates 5 existing builders to `wiki_dir.parent / "_publish"`.
- `src/kb/compile/compiler.py::compile_wiki`* — appends one call to `auto_publish_after_compile` at function tail, gated on `KB_DISABLE_COMPILE_AUTO_PUBLISH`.
- `src/kb/compile/publish.py::build_per_page_siblings`* — manifest-based incremental cleanup at `<wiki_dir>.parent/.data/publish-siblings-manifest.json`.
- `tests/test_cycle64_auto_publish.py` (NEW) — 4 cases.
- `tests/test_cycle64_publish_manifest.py` (NEW) — 3 cases.

**Cluster E — Snapshot infrastructure (AC18–AC20):**
- `requirements-dev.txt` — append `syrupy>=4.6.0` (single new dependency).
- `tests/test_cycle64_snapshots.py` (NEW) — 3 snapshot subjects (evidence-trail / Mermaid export / lint report).
- `tests/__snapshots__/test_cycle64_snapshots/` (NEW dir) — committed initial snapshots.

**Cluster F — Doc sync (AC21):** `CHANGELOG.md` / `CHANGELOG-history.md` / `BACKLOG.md` / `CLAUDE.md` / `docs/reference/architecture.md` / `docs/reference/testing.md` — text-only, no executable surface.

---

## Methodology

STRIDE applied per surface listed above. Each new behaviour is examined for Spoofing, Tampering, Repudiation, Information-disclosure, Denial-of-service, and Elevation-of-privilege exposure. The project's threat model is a **local-only personal KB** with no untrusted users, no network exposure (FastMCP listens on stdio), and a single-developer trust domain — so threats default to **low likelihood** unless a specific code path widens the attack surface. Severity is rated against impact-on-correctness (test isolation, query results, lint output, publish artifacts) more than confidentiality. Style precedent: cycle 47's STRIDE-table threat model (`docs/superpowers/decisions/2026-04-28-cycle-47-batch-threat-model.md`); cycle 45's correctness-invariant precedent (`docs/superpowers/decisions/2026-04-27-cycle-45-threat-model.md`). The cycle-64 deliverable is more substantive than cycle 47/45 because cycle 64 introduces new BEHAVIOUR (auto-rebuild side effect, auto-publish hook) rather than pure refactor. Material threats (≥HIGH severity AND ≥medium likelihood) are detailed in §Material threats.

---

## Threats

| ID | Surface | Category | Threat | Severity | Likelihood | Mitigation | AC ref |
|---|---|---|---|---|---|---|---|
| T1 | `tests/conftest.py::_isolate_wiki_constants_per_test` | T | A test calls `monkeypatch.delattr(kb.config, "WIKI_DIR")` AFTER the autouse fixture sets it, leaving the codebase to AttributeError or fall through to a stale module-top constant — masking real bugs. | MEDIUM | low | AC1 sets `monkeypatch.setattr(kb.config, "WIKI_DIR", tmp_path/"wiki")`; pytest's `monkeypatch` undoes per-test, and `delattr` after `setattr` is a test-author error that should be caught at code review. AC4's regression cases assert positive redirect (write lands in `tmp_path`), not negative `delattr` resilience. | AC1, AC4 |
| T2 | `tests/conftest.py::_isolate_wiki_constants_per_test` | I | The autouse fixture misses a `WIKI_*` constant the codebase actually reads (e.g. `WIKI_ENTITIES`, `WIKI_CONCEPTS`, `WIKI_COMPARISONS`, `WIKI_SUMMARIES`, `WIKI_SYNTHESIS` — see `src/kb/config.py:62-66`), causing a test to silently write to the developer's REAL wiki tree. | HIGH | medium | AC1 enumerates 8 constants but the project defines 13+ `WIKI_*`-shaped constants in `kb/config.py` (`WIKI_DIR`, `WIKI_INDEX`, `WIKI_SOURCES`, `WIKI_LOG`, `WIKI_CONTRADICTIONS`, `WIKI_PURPOSE`, `WIKI_ENTITIES`, `WIKI_CONCEPTS`, `WIKI_COMPARISONS`, `WIKI_SUMMARIES`, `WIKI_SYNTHESIS`). **Step 14 must run** `Grep "kb\.config\.(WIKI_|RAW_|PROJECT_ROOT)"` over `src/kb/` and confirm every read-site's constant is in AC1's monkeypatch list. If any subdir constant is read but not redirected, AC1 must extend before merge. | AC1 + Step 14 verify |
| T3 | `tests/conftest.py::real_project_root` + `--use-real-paths` | E | A test inadvertently uses `pytest.mark.usefixtures("real_project_root")` without the flag and gets a `RuntimeError`, OR — worse — a developer runs the full suite with `--use-real-paths` (e.g. for one debugging case) and ALL tests now use real paths, leaking writes to the live wiki. | MEDIUM | low | AC2's flag is global per-pytest-invocation, so the privilege escalation is opt-in by the human at the CLI. AC4's `test_real_project_root_fixture_yields_real_path_with_flag` confirms the gate works. CLAUDE.md tmp_wiki/tmp_kb_env conventions still apply — those fixtures are unaffected by `--use-real-paths`. | AC2, AC4 |
| T4 | `VectorIndex.query()` auto-rebuild path (AC6) | D | Under FastMCP's 40-thread pool, a coordinated dim-mismatch storm (e.g. all 40 threads see mismatch after a model upgrade) could enqueue 40 rebuild attempts. Each rebuild reads ALL pages, encodes, and writes a new sqlite_vec DB — sustained CPU/IO pressure. | HIGH | medium | AC6 calls `rebuild_vector_index(wiki_dir)` which has TWO layers of double-checked locking (embeddings.py:302–307: `if not _is_rebuild_needed(wiki_dir): return False` outside lock, then inside `_rebuild_lock` again). After thread-1 commits, thread-2's inside-lock re-check sees the new dim and returns False. AC8 case `test_concurrent_query_during_rebuild_idempotent` proves the outermost rebuild body executes ≤1 time across N=4 concurrent callers. Risk-7 in requirements doc references the same mitigation. | AC6, AC8 |
| T5 | `VectorIndex._derive_wiki_dir()` (AC5) | T | `_derive_wiki_dir` returns the `.tmp` rebuild artifact's path (e.g. `<wiki>/.data/vector_index.db.tmp`) and the auto-rebuild fires WHILE a rebuild is already in progress, recursing into `rebuild_vector_index` from a tmp-suffixed VectorIndex instance. | MEDIUM | low | AC5 contract explicitly returns `None` when `self.db_path` ends in `.tmp` (rebuild-in-progress sentinel). AC8 case `test_auto_rebuild_disabled_when_db_path_is_tmp_suffix` enforces this. The contract also returns `None` when `db_path is None`, isolating empty/uninitialized VectorIndex instances. | AC5, AC8 |
| T6 | `VectorIndex.query()` rebuild path (AC6) | E | The auto-rebuild path uses `wiki_dir = self._derive_wiki_dir()` then calls `rebuild_vector_index(wiki_dir)`. If `_derive_wiki_dir` somehow returns a path OUTSIDE `PROJECT_ROOT` (e.g. via a malicious symlink or a constructed `db_path` from a test), the rebuild reads/writes outside the project sandbox. | MEDIUM | low | `rebuild_vector_index` already calls `_vec_db_path(wiki_dir)` and `vec_path.parent.mkdir(parents=True, exist_ok=True)` (embeddings.py:313) — it would create an unexpected directory if `wiki_dir` were an attacker-controlled path. Mitigation: `_derive_wiki_dir` is called from `VectorIndex.query()` whose `db_path` was set at construction time by the kb codebase itself (no untrusted input). Per CLAUDE.md path-safety convention, library calls should use `_validate_path_under_project_root(wiki_dir, "wiki_dir")` before invoking rebuild. **Step 14 should add** a `_validate_path_under_project_root(wiki_dir, "vector_auto_rebuild_target")` call to AC6's rebuild-trigger branch — dual-anchor enforcement consistent with `kb rebuild-indexes` containment validation referenced in embeddings.py:677. | AC6 + Step 14 verify |
| T7 | `kb.graph.cache._GLOBAL_CACHE` (AC9) | I | The cache key includes `wiki_dir.resolve().as_posix()` — if `get_cache_stats()` is exposed via MCP or logged, the resolved filesystem path leaks the developer's directory layout (e.g. `/home/asun28/projects/...`). | LOW | low | AC9's `get_cache_stats()` returns counts only (`{"hits", "misses", "invalidations", "size"}`), NOT the keys themselves. The dict keys live only in process memory; no logging path emits them. **Step 14 should grep** `logger.*_GLOBAL_CACHE` and `logger.*get_cache_stats` to confirm no path-leaking log emerged in implementation. | AC9 + Step 14 verify |
| T8 | `kb.graph.cache.get_graph()` (AC9, AC10) | T | The mtime-keyed cache misses an invalidation — e.g. an external file write between two consecutive `get_graph` calls within a single second on Windows (FAT32 2s mtime granularity); both calls return the SAME cached graph and lint emits a stale verdict that the human treats as authoritative. | HIGH | low | AC9 keys on `max((p.stat().st_mtime for p in (wiki_dir/sub).rglob("*.md")), default=0.0)` over canonical WIKI_SUBDIRS. NTFS gives 100ns mtime resolution (well below problematic). FAT32 isn't a documented project surface. AC11's invalidation hooks at `ingest_source` and `refine_page` cover the in-process mutator paths. **External writes** (a human editing wiki pages with vim while the MCP server runs) are out-of-scope for cache invalidation — operators should call `kb rebuild-indexes` after manual edits, per existing project convention. | AC9, AC11 |
| T9 | `kb.graph.cache._MAX_CACHE_SIZE = 4` (AC9) | D | An attacker (or a misbehaving test loop) calls `get_graph(wiki_dir_<n>)` for `n in range(1_000_000)`, evicting cache entries faster than they can be reused — cache-thrash defeating the optimisation. | LOW | low | AC9's LRU eviction-by-oldest-mtime bounds memory at 4 entries × graph size. Each graph for a small KB is ≤MB-class; total ≤4 MB worst case. The "attack" is actually just inefficient — cache miss rate goes to 100% but correctness is unaffected (each call falls through to `build_graph` = the pre-AC9 baseline). AC12 case `test_cache_size_bound_lru_eviction` exercises the bound. | AC9, AC12 |
| T10 | `auto_publish_after_compile` `out_dir` (AC13) | T | The default `out_dir = wiki_dir.parent / "_publish"` writes outside `wiki_dir` but inside the project tree. If `wiki_dir.parent` is somehow not under `PROJECT_ROOT` (e.g. a test passes a `tmp_path/wiki`), the publish artifacts land outside the test's tmp tree, leaking across tests OR overwriting a developer's `_publish` dir. | MEDIUM | low | AC13's contract mandates `out_dir = wiki_dir.parent / "_publish"`. Under cycle-64's AC1 conftest sandboxing, `wiki_dir.parent` is per-test `tmp_path` — `_publish` lands at `tmp_path/_publish`, well-isolated. The publish module's existing T1 path-containment comment (`src/kb/compile/publish.py:18-19` "T1 (path containment): enforced by the CLI wrapper `kb publish`") notes that the CLI is the canonical containment gate; AC13 is invoked from `compile_wiki` (not the CLI), so the **mitigation must be inside `auto_publish_after_compile`**. **Step 14 must verify** `auto_publish_after_compile` calls `_validate_path_under_project_root(out_dir, "publish_out_dir")` before invoking any builder (consistent with CLAUDE.md path-safety conventions; dual-anchor literal + resolved). | AC13 + Step 14 verify |
| T11 | `auto_publish_after_compile` (AC13, AC14) | D | A broken builder (e.g. `build_llms_full_txt` raising on a malformed page) inside `auto_publish_after_compile` is caught at the `compile_wiki` level (AC14's try/except logs WARNING) — but if the builder crashes mid-write leaving a partial `_publish/llms-full.txt`, the next `kb publish` reads stale truncated output. | MEDIUM | low | AC13 documents best-effort builder isolation (errors logged at WARNING, function continues). The existing publish builders all use `atomic_text_write` (`src/kb/compile/publish.py:44`), which writes to tempfile + `os.replace` — partial writes never reach the final path. AC15 case `test_publish_failure_does_not_fail_compile` covers compile-time isolation. | AC13, AC14, AC15 |
| T12 | `auto_publish_after_compile` (AC13) | I | The published `<out_dir>/_publish/sitemap.xml` lists every wiki page-id slug (per `src/kb/compile/publish.py::build_sitemap_xml`). If a deleted page's slug remained in the manifest from a prior publish (AC16's manifest), the sitemap would advertise a no-longer-existing slug. | LOW | low | AC16's manifest tracks SIBLING paths, NOT sitemap entries; the sitemap is regenerated from `scan_wiki_pages(wiki_dir)` each call. Deleted pages are removed from the next sitemap pass. The publish module's T2 (epistemic filter) at `publish.py:20-22` already excludes retracted/contradicted/speculative pages from sitemap — so deletion timing matters less. | AC13 |
| T13 | `KB_DISABLE_COMPILE_AUTO_PUBLISH` (AC14) | E | A subprocess (`subprocess.run(["python", "-c", "..."], env={...})` in a test) inherits `KB_DISABLE_COMPILE_AUTO_PUBLISH=0` from the parent test runner but the parent meant to disable. Test runs auto-publish unintentionally and writes to the test's `tmp_path/_publish`, creating spurious files but not escaping the sandbox. | LOW | low | AC1's sandbox redirects `WIKI_DIR` to `tmp_path/wiki` for the parent test; `wiki_dir.parent / "_publish"` = `tmp_path/_publish` — still under per-test `tmp_path`. The kill-switch precedence is documented in AC14 ("defaults to False"). AC15 case `test_kill_switch_env_disables_auto_publish` confirms behaviour. | AC14, AC15 |
| T14 | `publish-siblings-manifest.json` (AC16) | T | The manifest at `<wiki_dir>.parent/.data/publish-siblings-manifest.json` is loaded with `json.load` — a malformed manifest (truncated, malicious test fixture) could cause the publish to crash mid-cleanup, leaving sibling files in inconsistent state. | MEDIUM | low | AC17 case `test_manifest_corrupted_falls_back_to_full_cleanup` MANDATES that JSON-parse errors trigger fallback to the cycle-16 unconditional unlink semantics — not a crash. The manifest is owned by the project (no untrusted writer) so this is defense-in-depth against test/dev corruption, not adversarial injection. AC16 saves the manifest via `atomic_json_write` so partial-write corruption is structurally prevented. | AC16, AC17 |
| T15 | `tests/__snapshots__/test_cycle64_snapshots/` (AC19, AC20) | I | A snapshot file commits a path under `tmp_path` that includes the developer's USER_HOME prefix (e.g. `/home/asun28/...` or `C:\Users\Admin\...`), leaking the dev's filesystem layout into the public git history. | MEDIUM | low | AC1's autouse sandboxing redirects `WIKI_DIR` to per-test `tmp_path` BEFORE the snapshot subjects (`evidence-trail`, `mermaid-export`, `lint-report`) execute. If any of those subjects emit an absolute path containing `tmp_path`, the snapshot will contain a per-test-random path and `pytest --snapshot-update` will fail the second run (idempotency check in AC20). **Step 14 must grep** the committed snapshots for `/Users/`, `/home/`, `C:\\`, `/tmp/pytest-of-` substrings before merge. If found, the snapshot subject must be normalized to relative paths or inputs/outputs only (no environment-revealing strings). | AC19, AC20 + Step 14 verify |
| T16 | `--snapshot-update` flag in CI (AC18, AC20) | T | A CI job inadvertently runs `pytest --snapshot-update` (e.g. via a developer's accidental commit, or a bot misuse) — silently rewrites all snapshots to match current output, removing the regression-detection value of the entire snapshot suite. | MEDIUM | low | `syrupy` only updates snapshots when `--snapshot-update` is explicitly passed; default `pytest` invocations FAIL on snapshot drift (idempotency). The project's `.github/workflows/ci.yml` calls `python -m pytest` without flags. **Step 14 must verify** the CI workflow does not enable `--snapshot-update` and AC20's `docs/reference/testing.md` workflow note explicitly warns "never run --snapshot-update in CI". | AC20 + Step 14 verify |
| T17 | `requirements-dev.txt` (AC18) | I/D | New dep `syrupy>=4.6.0` could carry an as-yet-undisclosed vulnerability (typosquat attack, supply-chain compromise) that a Step 11 SCA scan would catch. | MEDIUM | low | Cycle-22 L4 late-arrival CVE hazard (referenced in requirements doc Risk 4). Step 11 PR-CVE diff explicitly includes `syrupy` since it is a Class B (PR-introduced) dep. The fallback `pytest-snapshot>=0.9.0` is documented in AC18. **Step 11 SCA must check** both `syrupy` and any of its transitive deps for advisories surfaced after 2026-05-03. | AC18 + Step 11 SCA |
| T18 | `kb.graph.cache.get_graph` calls in lint (AC10) | T | Cycle-18 L1 snapshot-binding hazard — if a test does `monkeypatch.setattr("kb.graph.cache.get_graph", spy)` but the 5 caller modules do `from kb.graph.cache import get_graph` (binding the function at import time), the patch fails to intercept and the test passes vacuously even though the cache contract is broken. | HIGH | medium | Risk-2 in requirements doc explicitly addresses this: callers MUST use `import kb.graph.cache` + `kb.graph.cache.get_graph(...)` (attribute lookup), OR each caller's regression test patches both forms. **Step 14 must verify** all 5 caller sites (`lint/checks/cycles.py`, `lint/checks/orphan.py`, `lint/semantic.py`, `lint/augment/collector.py`, `lint/runner.py`) use the attribute-lookup form, AND the regression test in AC12 patches `kb.graph.cache.get_graph` AND each caller-side `<module>.get_graph` rebinding (cycle-18 L1 belt-and-braces). Per cycle-18 L1, the safer pattern is monkey-patching the OWNER module's attribute. | AC10, AC12 + Step 14 verify |

---

## Material threats

The following threats meet the bar of `Severity ≥ HIGH AND Likelihood ≥ medium`. Each merits Step 14 verifier work or AC-level scrutiny.

### M1 — T2 (HIGH / medium): conftest sandbox misses a `WIKI_*` constant

**Attack scenario:** AC1 enumerates 8 constants for redirect: `WIKI_DIR, WIKI_LOG, WIKI_CONTRADICTIONS, RAW_DIR, PROJECT_ROOT, WIKI_PURPOSE, WIKI_INDEX, WIKI_SOURCES`. But `src/kb/config.py:62-66` defines five MORE wiki subdir constants: `WIKI_ENTITIES`, `WIKI_CONCEPTS`, `WIKI_COMPARISONS`, `WIKI_SUMMARIES`, `WIKI_SYNTHESIS`. Plus `RAW_ARTICLES`, `RAW_PAPERS`, `RAW_REPOS`, `RAW_VIDEOS`, `RAW_PODCASTS`, `RAW_BOOKS`, `RAW_DATASETS`, `RAW_CONVERSATIONS`, `RAW_ASSETS`, `CAPTURES_DIR`, plus the `.data/` paths (`FEEDBACK_PATH`, `REVIEW_HISTORY_PATH`, `VERDICTS_PATH` at config.py:178-180), plus `OUTPUTS_DIR`. If a test reads `kb.config.WIKI_ENTITIES` (e.g. `tests/test_compile.py` exercising the entity-page path), the autouse fixture leaves it pointing at the developer's REAL `wiki/entities/` and the test silently writes there.

**Why this cycle does/doesn't reduce surface:** AC1 does redirect `WIKI_DIR` itself, but if the codebase reads `kb.config.WIKI_ENTITIES` directly (rather than `WIKI_DIR / "entities"`), the redirect doesn't propagate. Whether this is a concrete leak surface depends on whether the codebase reads the subdir constants directly — answered by `Grep "kb\.config\.(WIKI_ENTITIES|WIKI_CONCEPTS|WIKI_COMPARISONS|WIKI_SUMMARIES|WIKI_SYNTHESIS|RAW_ARTICLES|RAW_PAPERS|RAW_REPOS|RAW_VIDEOS|RAW_PODCASTS|RAW_BOOKS|RAW_DATASETS|RAW_CONVERSATIONS|RAW_ASSETS|CAPTURES_DIR|FEEDBACK_PATH|REVIEW_HISTORY_PATH|VERDICTS_PATH|OUTPUTS_DIR)" src/kb/`.

**Step 14 check:** Run that grep. For every read-site found, EITHER (a) AC1 must extend its monkeypatch list to cover that constant, OR (b) verify the read-site computes its path lazily from `WIKI_DIR` / `RAW_DIR` / `PROJECT_ROOT` (which AC1 already redirects) and not via the subdir constant directly. If neither holds, AC1 must extend before merge. AC4's regression cases must add a 4th case asserting that a write to the missing constant lands inside `tmp_path`.

### M2 — T4 (HIGH / medium): dim-mismatch rebuild storm under FastMCP thread pool

**Attack scenario:** A model-version upgrade changes the embedding dimension from D1 to D2. The next FastMCP request fires N=40 concurrent `kb_query` calls, each instantiating `VectorIndex` and hitting `query()`. All 40 detect mismatch (stored=D1 vs. fresh=D2). Without protection, all 40 call `rebuild_vector_index(wiki_dir)`, each doing a full `load_all_pages` + `model.encode(texts)` + sqlite_vec build. The rebuild storm bottlenecks on the embedding model and writes 40× the same DB to `<vec>.tmp` paths — though `os.replace` is atomic, the thrash is real.

**Why this cycle does/doesn't reduce surface:** `rebuild_vector_index` ALREADY has a two-layer mitigation:
1. Outer-lock-free `_is_rebuild_needed(wiki_dir)` mtime check (embeddings.py:302) returns False once the rebuild commits — subsequent threads short-circuit.
2. Inside `_rebuild_lock`, a re-check (embeddings.py:307) — only ONE thread runs the encoder + build.

So AC6's auto-trigger inherits this discipline. However, AC8 case `test_concurrent_query_during_rebuild_idempotent` only spawns N=4 threads — not the FastMCP-realistic N=40. And the in-test thread setup may or may not exercise the same lock contention pattern as a real ThreadPool.

**Step 14 check:** (a) Confirm AC8's test asserts `_is_rebuild_needed` is called at most once per concurrent burst (the current test asserts the OUTERMOST body; ensure `rebuild_vector_index` returns the first-thread's result to all threads). (b) Confirm AC6's call site does NOT hold `_conn_lock` while invoking `rebuild_vector_index` — if it did, the rebuild would deadlock with VectorIndex's per-instance connection lock. The trigger must release before invoking. (c) Verify `KB_DISABLE_VECTOR_AUTO_REBUILD` is documented in `docs/reference/error-handling.md` (per AC6) so an operator can silence the storm without redeploying.

### M3 — T18 (HIGH / medium): cycle-18 L1 snapshot-binding hazard in cache-caller tests

**Attack scenario:** AC10 wires `from kb.graph.cache import get_graph` at the top of 5 caller modules (lint/checks/cycles.py, lint/checks/orphan.py, lint/semantic.py, lint/augment/collector.py, lint/runner.py). At import time, each module's `get_graph` symbol is bound to the function object at that moment. A test then does `monkeypatch.setattr("kb.graph.cache.get_graph", spy)` to verify cache-hit behaviour — but the 5 callers' bound names still point to the ORIGINAL `get_graph`. The spy never fires. AC12 cases (e.g. `test_get_graph_caches_within_one_lint_pass`) might still pass if they directly invoke `kb.graph.cache.get_graph` rather than going through a caller module, but the END-TO-END contract (lint pipeline uses cache) is unverified.

**Why this cycle does/doesn't reduce surface:** Cycle-18 L1 is a well-known foot-gun — the requirements doc Risk 2 explicitly flags it. The mitigation is well-understood: callers use `import kb.graph.cache` then `kb.graph.cache.get_graph(...)` (attribute lookup at call time), not `from kb.graph.cache import get_graph` (binding at import). Or alternately, EACH caller-side regression test patches BOTH the owner-module symbol AND each caller's local rebinding.

**Step 14 check:** (a) `Grep "from kb\.graph\.cache import" src/kb/lint/` — should return zero hits for `get_graph`; should be `import kb.graph.cache` instead. (b) Run AC12's `test_get_graph_caches_within_one_lint_pass` test under `monkeypatch.setattr(kb.graph.cache, "get_graph", spy)` AND also as a behavioural integration test that calls `lint.runner.run_all_checks(wiki_dir)` and asserts `build_graph` was invoked exactly once across the whole lint pass. (c) Per CLAUDE.md "Patch the owner module" guidance — verify the test patches `kb.graph.cache.get_graph` (owner module attribute) consistently.

### M4 — T6 (MEDIUM elevated to material because the surface is novel): auto-rebuild path safety

**Attack scenario:** Conceptually weaker than M1–M3 but worth lifting because it's a NEW surface. The auto-rebuild path in AC6 uses `wiki_dir = self._derive_wiki_dir()` — a value derived from `self.db_path.parent.parent`. If a test (or a deliberately-malicious construction) sets `db_path = Path("/etc/passwd/.data/foo.db")`, then `_derive_wiki_dir()` returns `Path("/etc")` and `rebuild_vector_index(Path("/etc"))` proceeds to `_vec_db_path(Path("/etc"))` → `Path("/etc/.data/vector_index.db")` and tries to `mkdir(parents=True, exist_ok=True)`. On most systems this fails on permissions; on a misconfigured dev setup it could create files outside the project tree.

**Why this cycle does/doesn't reduce surface:** `_derive_wiki_dir`'s contract (AC5) returns `None` for invalid layouts via "a basic `<dir>/.data/<file>` heuristic" — but the heuristic is not specified beyond `parent.parent` being non-None. CLAUDE.md mandates `_validate_path_under_project_root(path, field_name)` for library calls.

**Step 14 check:** Add `_validate_path_under_project_root(wiki_dir, "vector_auto_rebuild_target")` to AC6's rebuild-trigger branch — between `wiki_dir = self._derive_wiki_dir()` and `rebuild_vector_index(wiki_dir)`. This is dual-anchor (literal + resolved) per CLAUDE.md and matches the `kb rebuild-indexes --wiki-dir <that>` containment validator already running on the explicit-rebuild path (referenced at embeddings.py:677). If validation fails, the auto-rebuild branch must skip silently (returning `[]` from query, same as AC6's first-query contract).

---

## CVE baseline interpretation

Captured via `D:/Projects/llm-wiki-flywheel/.venv/Scripts/python.exe -m pip_audit --format=json --output .data/cycle-64/cve-baseline.json` (319 deps audited; 4 advisories on 4 packages — exact match to cycles-47..58 baseline; no drift, no new).

### Pip-audit summary

| Package | Version | Advisory ID | Aliases | Fix Available | BACKLOG-known? |
|---|---|---|---|---|---|
| diskcache | 5.6.3 | CVE-2025-69872 | GHSA-w8v5-vhqr-4h9v | `[]` | YES — Phase 4.5 MEDIUM; dev-only via trafilatura robots.txt cache; `grep "diskcache\|DiskCache\|FanoutCache" src/kb` returns zero direct kb imports |
| litellm | 1.83.0 | GHSA-xqmj-j6mv-4862 | (no CVE alias surfaced) | `['1.83.7']` BLOCKED by `click==8.1.8` transitive | YES — narrow-role exception per BACKLOG; cycle-55 attempted patch + reverted (introduces python-dotenv 1.0.1 PR-class-B); zero `import litellm` in src/kb |
| pip | 26.0.1 | CVE-2026-3219 | GHSA-58qw-9mgm-455v | `[]` (advisory has `patched_versions:null`) | YES — tooling-only; cycle-22 L4 conservative posture |
| ragas | 0.4.3 | CVE-2026-6587 | GHSA-95ww-475f-pr4f | `[]` | YES — dev-eval-only; zero direct kb imports |

**Drift notes:**
- pip-audit surfaces ONE litellm advisory (`GHSA-xqmj-j6mv-4862`); BACKLOG also tracks `GHSA-r75f-5x8p-qvmc` (critical) and `GHSA-v4p8-mg3p-g94g` (high) reported via Dependabot but NOT yet in pip-audit's data (cycle-36+ documented drift). No change in cycle 64.
- All 4 advisories match BACKLOG state at cycle-58 / cycle-56-audit-correction. **No late-arrival CVE** within the cycle's wall-clock window so far. Step 11.5 will re-audit immediately before merge per cycle-22 L4.

### Class A vs Class B for cycle 64

- **Class A** (existing on `main`): the 4-vuln baseline above. No bumps planned; all known items have either no upstream patch, a blocked transitive, or a conservative-posture caveat. BACKLOG.md timestamp refresh under AC21 (mechanical).
- **Class B** (PR-introduced by cycle 64): cycle 64 introduces ONE new dep — `syrupy>=4.6.0` (AC18). Step 11 PR-CVE diff MUST scan `syrupy` and its transitive closure for advisories. If a `syrupy` advisory surfaces, the AC18 fallback is `pytest-snapshot>=0.9.0` (documented in AC18 + Risk 4). **No other deps introduced** (AC9's `kb.graph.cache` uses stdlib `threading` + the existing `networkx` already pinned; AC13 uses existing publish builders). T17 in §Threats covers the Class B exposure surface.

### Class A vs Class B for cycle 64

- **Class A** (existing on `main`): expected to mirror cycle 47's 4-vuln baseline UNLESS late-arrival shows up. No bumps planned; all 4 known items have either no upstream patch, a blocked transitive, or a conservative-posture caveat. Refresh timestamps in BACKLOG.md (mechanical).
- **Class B** (PR-introduced by cycle 64): cycle 64 introduces ONE new dep — `syrupy>=4.6.0` (AC18). Step 11 PR-CVE diff MUST scan `syrupy` and its transitive closure for advisories. If a `syrupy` advisory surfaces, the AC18 fallback is `pytest-snapshot>=0.9.0` (documented in AC18 + Risk 4). **No other deps introduced** (AC9's `kb.graph.cache` uses stdlib `threading` + the existing `networkx` already pinned; AC13 uses existing publish builders). T17 in §Threats covers the Class B exposure surface.

---

## Mitigations summary

**AC-driven (will land in Step 9 implementation):**
- AC1 — autouse `WIKI_*` redirect (mitigates T2 partially; M1 calls for extension).
- AC2 — opt-in `real_project_root` + `--use-real-paths` flag (mitigates T3).
- AC4 — regression cases for default-isolation positive-redirect (asserts T1 + T2 mitigation works).
- AC5 — `_derive_wiki_dir()` `.tmp` suffix rejection (mitigates T5).
- AC6 — `KB_DISABLE_VECTOR_AUTO_REBUILD` kill-switch + double-checked locking inheritance (mitigates T4).
- AC8 — concurrent-rebuild idempotency test (covers T4, T5).
- AC9 — `_MAX_CACHE_SIZE = 4` LRU bound + RLock (mitigates T9; T1 reload-leak hazard).
- AC11 — invalidate at ingest + refine (mitigates T8 in-process mutator paths).
- AC12 — cache-hit / cache-miss / invalidate / LRU eviction tests (covers T8, T9, T18 — but see M3 Step 14 check).
- AC13 — `out_dir = wiki_dir.parent / "_publish"` containment (mitigates T10 partially; M4 calls for `_validate_path_under_project_root` addition).
- AC14 — `KB_DISABLE_COMPILE_AUTO_PUBLISH` kill-switch + try/except wrapper (mitigates T11, T13).
- AC15 — `test_publish_failure_does_not_fail_compile` + artifacts-outside-walk test (covers T11, T12).
- AC16 — manifest-based incremental cleanup with `atomic_json_write` (mitigates T14 partially).
- AC17 — manifest-corruption fallback to cycle-16 unconditional cleanup (mitigates T14).
- AC18 — `syrupy>=4.6.0` with `pytest-snapshot` fallback (mitigates T17 fallback path).
- AC20 — committed initial snapshots + idempotency check (mitigates T15 detection).

**Step 14 verifier-only (no AC adds the check; security-verify must add):**
- T2 / M1 — Grep `kb\.config\.(WIKI_ENTITIES|WIKI_CONCEPTS|WIKI_COMPARISONS|WIKI_SUMMARIES|WIKI_SYNTHESIS|RAW_ARTICLES|...)` over `src/kb/`; verify every read-site is either (a) covered by AC1's monkeypatch or (b) lazily-derived from `WIKI_DIR`/`RAW_DIR`. Extend AC1 if leaks remain.
- T6 / M4 — Add `_validate_path_under_project_root(wiki_dir, "vector_auto_rebuild_target")` to AC6's rebuild-trigger branch; dual-anchor (literal + resolved) per CLAUDE.md.
- T7 — Grep `logger.*(_GLOBAL_CACHE|get_cache_stats)` to confirm no resolved-path leak in implementation.
- T10 — Verify `auto_publish_after_compile` calls `_validate_path_under_project_root(out_dir, "publish_out_dir")` before invoking any builder.
- T15 — Grep committed snapshots for `/Users/`, `/home/`, `C:\\`, `/tmp/pytest-of-` substrings; fail merge if found.
- T16 — Verify `.github/workflows/ci.yml` does NOT pass `--snapshot-update`; verify `docs/reference/testing.md` snapshot-update note explicitly warns CI.
- T17 — Step 11 SCA must scan `syrupy>=4.6.0` and transitive closure for advisories surfaced after 2026-05-03.
- T18 / M3 — Grep `from kb\.graph\.cache import` in `src/kb/lint/`; verify zero hits for `get_graph` (must use `import kb.graph.cache` + attribute lookup). Verify AC12 patches both forms.
- CVE baseline — Re-run `pip-audit` with venv activated; fill the baseline interpretation section.

---

## Out-of-scope (cycle 64)

Threat classes that exist in the codebase or that could plausibly be raised, but which cycle 64 does NOT address (deferred to other cycles or remain BACKLOG items):

1. **`compile/compiler.py::compile_wiki` per-source rollback** — cycle-25 partially addressed; remaining sub-items are tracked in BACKLOG.md and will not be touched here. Cycle 64's only `compile_wiki` edit is a tail-of-function single-line call to `auto_publish_after_compile` — does NOT alter the existing rollback semantics.
2. **CLI ↔ MCP write-path parity** (4-7 new CLI commands per BACKLOG MEDIUM) — explicitly non-goal in requirements doc. Defer to cycle-65+. Threats from MCP-only mutator paths (e.g. an MCP client invoking `kb_ingest` with no CLI counterpart) remain in current state.
3. **Cross-process graph cache persistence** — explicitly non-goal (`No kb.graph.cache cross-process persistence` in requirements doc). Cycle 64 keeps the cache in-process. A separate process running `kb compile` does NOT see another process's cache, so no cross-process invalidation contract exists. Cycles 53/61's `kb_rebuild_indexes` MCP-tool wiring and any future shared-cache work would need to explicitly model cross-process invalidation.
4. **Snapshot-subject coverage breadth** — AC19 ships 3 snapshot subjects (evidence-trail / Mermaid / lint-report) per Q6 in the requirements doc. Other format-drift surfaces — `_build_summary_content` page-rendering, `kb publish --format graph` JSON-LD output, `auto_publish_after_compile`'s `_publish/llms-full.txt` body — are deferred to cycle-65+ to keep snapshot maintenance churn manageable. Format-drift bugs in those surfaces remain undetected by cycle 64's snapshot infrastructure.

---

## References

- `docs/superpowers/decisions/2026-05-03-cycle-64-requirements.md` — authoritative ACs + Risks list.
- `docs/superpowers/decisions/2026-04-28-cycle-47-batch-threat-model.md` — STRIDE-table precedent + dep-CVE baseline format.
- `docs/superpowers/decisions/2026-04-27-cycle-45-threat-model.md` — correctness-invariant precedent for refactor-class cycles.
- `CLAUDE.md` — path-safety conventions: `_validate_page_id` at MCP boundary; library calls use `_validate_path_under_project_root(path, field_name)` (dual-anchor: literal + resolved both under `PROJECT_ROOT`).
- `src/kb/query/embeddings.py:250-348` (`rebuild_vector_index` double-checked locking) and `src/kb/query/embeddings.py:660-689` (existing `wiki_dir_hint` derivation that AC5 promotes).
- `src/kb/compile/publish.py:18-35` (existing T1–T10 threat-mitigation comment; cycle 64 extends with auto-publish-time T1 path containment per M4).
- `src/kb/config.py:48-180` (full `WIKI_*` / `RAW_*` / `.data/` constant list referenced by T2 / M1).
- BACKLOG.md known-conflicts list — `diskcache`, `ragas`, `litellm`, `pip` no-upstream-fix items (basis for CVE baseline expectations).
