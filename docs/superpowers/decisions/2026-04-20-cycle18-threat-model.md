# Cycle 18 — Threat Model (Step 2)

**Date:** 2026-04-20
**Companion to:** `2026-04-20-cycle18-requirements.md`
**Scope:** 16 ACs across 5 files (`tests/conftest.py`, `src/kb/utils/wiki_log.py`, `src/kb/compile/linker.py`, `src/kb/ingest/pipeline.py`, `tests/test_workflow_e2e.py`).

## 1. Per-symbol verification table (cycle-15 L1)

| Symbol | Expected location | Status | Notes |
|---|---|---|---|
| `_rotate_log_if_oversized` | `kb.utils.wiki_log:16` | EXISTS | Called at line 109 BEFORE `file_lock` acquisition (line 126). Target of AC4 move. |
| `append_wiki_log` | `kb.utils.wiki_log:52` | EXISTS | AC10 does NOT modify signature; request_id prefix added on caller side only. |
| `file_lock` | `kb.utils.io:226` | EXISTS | `@contextmanager`, `yields` no value, PID-stamped stale-lock detection, 5s default timeout, documented lock-order convention. |
| `atomic_text_write` | `kb.utils.io:93` | EXISTS | temp+fsync+rename. Used by `_emit_ingest_jsonl` (AC11) — BUT JSONL is append-only, so the writer should use `file_lock + open("a") + write` NOT `atomic_text_write` (whose rename semantics destroy append chains). Flagged in T7 / implementer-risk below. |
| `atomic_json_write` | `kb.utils.io:58` | EXISTS | Not used by cycle 18. Kept for completeness. |
| `inject_wikilinks` | `kb.compile.linker:166` | EXISTS | Scalar per-page loop at 203-263 — target of AC7 per-page lock wrap. |
| `_update_sources_md` | N/A | **SEMANTIC-MISMATCH** | **AC14 / AC15 reference this name but the actual helper is `_update_sources_mapping` at `kb.ingest.pipeline:641`.** Implementer must either rename or re-spec the AC to the real symbol. See §9 action item. |
| `_update_index_md` | N/A | **SEMANTIC-MISMATCH** | **Same — actual symbol is `_update_index_batch` at `kb.ingest.pipeline:681`.** |
| `_update_sources_mapping` | `kb.ingest.pipeline:641` | EXISTS | Two existing monkeypatch sites (see §2). |
| `_update_index_batch` | `kb.ingest.pipeline:681` | EXISTS | Two existing monkeypatch sites (see §2). |
| `ingest_source` | `kb.ingest.pipeline:819` | EXISTS | Entry at 819; append to `wiki/log.md` at 1091-1096; HASH_MANIFEST write at 1076-1086. |
| `HASH_MANIFEST` | `kb.compile.compiler:25` | EXISTS | `PROJECT_ROOT / ".data" / "hashes.json"`. Read by 4 call-sites in kb src, patched by 20 test sites across 10 files. |
| `_TMP_KB_ENV_PATCHED_NAMES` | `tests/conftest.py:14` | EXISTS | 21-entry tuple; `HASH_MANIFEST` currently absent (AC1 target). |
| `tmp_kb_env` | `tests/conftest.py:127` | EXISTS | Mirror-rebind loop at line 224-231 uses `== original_values[name]` guard; AC2 extension picks up `HASH_MANIFEST` automatically once added to `_TMP_KB_ENV_PATCHED_NAMES` AND `patched` dict. |
| `sanitize_error_text` | `kb.utils.sanitize:30` | EXISTS | Signature: `(exc: BaseException, *paths: Path \| None) -> str`. Uses `_ABS_PATH_PATTERNS` regex for `C:\`, `D:\`, UNC, `/home/`, `/Users/`, `/opt/`, `/var/`, `/srv/`, `/tmp/`, `/mnt/`, `/root/`. AC13 should extract a sibling `sanitize_text(s: str) -> str` rather than synthesizing fake exceptions — see §9 action item. |
| `_sanitize_error_str` | `kb.mcp.app:134` | EXISTS | Thin wrapper around `sanitize_error_text`. Already re-imported in `quality.py`, `browse.py`, `health.py`, `core.py` — safe to import from `kb.utils.sanitize` directly in `pipeline.py` for AC13. |
| `LOG_SIZE_WARNING_BYTES` | `kb.utils.wiki_log:13` | EXISTS | 500_000. AC12 reuses for `.data/ingest_log.jsonl` threshold. |
| `PROJECT_ROOT` | `kb.config` | EXISTS | Used by AC11 for JSONL path anchor. |

## 2. Monkeypatch-target enumeration (cycle-17 L1)

Existing attribute-monkeypatch sites for each symbol the cycle modifies or relocates:

| Symbol | Test sites | Files | Risk flag |
|---|---|---|---|
| `HASH_MANIFEST` | 20 occurrences across 10 test files | `test_backlog_by_file_cycle4.py` (1), `test_cycle10_extraction_validation.py` (2), `test_cycle10_validate_wiki_dir.py` (1), `test_cycle11_ingest_coerce.py` (2), `test_cycle13_frontmatter_migration.py` (1), `test_cycle17_mcp_tool_coverage.py` (2, both comments/docstrings), `test_ingest.py` (1), `test_v0915_task03.py` (3), `test_v099_phase39.py` (6), `test_v5_lint_augment_orchestrator.py` (1) | **FLAG — >5 sites but non-breaking.** Fixture-bundled patch in AC1/AC2 is ADDITIVE: existing tests continue to patch `HASH_MANIFEST` explicitly and the second patch is a no-op redirect to the same tmp path. Narrowing to fixture-only is cycle-19 cleanup work. |
| `_update_sources_mapping` | 1 site (`test_v01008_ingest_pipeline_fixes.py:99`) | | OK — `_write_index_files` MUST keep this helper callable as `kb.ingest.pipeline._update_sources_mapping` (do NOT inline). |
| `_update_index_batch` | 1 site (`test_v01008_ingest_pipeline_fixes.py:98`) | | OK — same constraint as above. |
| `append_wiki_log` | 6 sites across 5 files (`test_compiler_mcp_v093.py` (2), `test_v01008_ingest_pipeline_fixes.py` (1), `test_v0912_phase393.py` (1), `test_v0913_phase394.py` (1), `test_v0914_phase395.py` (1)) | | OK — AC10 prefixes on caller side only; does NOT rename or resignature `append_wiki_log`. |
| `inject_wikilinks` | 2 sites (both in `test_review_fixes_v099b.py`) | | OK — AC7 adds `file_lock` INSIDE the function body. Tests that replace the whole function remain unaffected. |
| `_rotate_log_if_oversized` | 0 sites | | OK — AC5 wraps around a new generic helper; internal shim is invisible. |
| `rotate_if_oversized` (new) | 0 sites | | N/A — new helper. |
| `_emit_ingest_jsonl` (new) | 0 sites | | N/A — new. |
| `_write_index_files` (new) | 0 sites | | N/A — new. |

**Scope risk assessment**: `HASH_MANIFEST` is the only symbol over the 5-site threshold. Cycle 18's fixture bundling is additive-compatible (both patches resolve to the same tmp path); no per-test migration required this cycle. R3 review must confirm (a) `_update_sources_mapping` + `_update_index_batch` remain importable attributes after `_write_index_files` refactor, and (b) no test that currently does NOT patch `HASH_MANIFEST` becomes a false-positive pass because the fixture now covers it transparently (i.e., a test that SHOULD have patched and didn't, and was relying on luck).

## 3. Trust boundaries

- **User-supplied text into `ingest_source`.** `source_path` is path-traversal-validated at `pipeline.py:880-885`; `source_type` is enum-validated. `extraction` dict flows from either (a) LLM output validated by `_pre_validate_extraction` or (b) caller-supplied JSON from the MCP client. `raw_content` is decoded bytes; it is NEVER serialized into `.data/ingest_log.jsonl` (AC13 explicit).
- **`.data/ingest_log.jsonl` readers.** Future debugging workflows will `cat`/`tail` this file into chat or pipe it to an `kb log-inspect` CLI. MUST NOT contain: (a) raw source content, (b) absolute filesystem paths (Windows `C:\…`, POSIX `/home/…`), (c) API keys from error strings (secret-scanner in `kb.capture` already rejects raw input containing keys, but error strings from the Anthropic SDK can reference model names, not keys — document as residual risk), (d) PII from ingested content.
- **`wiki/log.md` readers.** Operator reads a live log. `[req=<16-hex>]` prefix is ASCII-safe by construction. The existing `_escape_markdown_prefix` at `wiki_log.py:72-81` already neutralizes `#`/`-`/`>`/`!`/`|`/`[[`/`]]` and control chars; the `[req=` prefix starts with `[` (non-special) so it flows through untouched. Injection-forgeability: `request_id` is a uuid4 hex — a malicious source filename cannot produce a colliding `[req=…]` substring that would confuse a grep-based log-correlation tool because the prefix is emitted by the pipeline BEFORE caller-controlled content.
- **`HASH_MANIFEST` test-vs-prod boundary.** Today, 10 test files individually monkeypatch `kb.compile.compiler.HASH_MANIFEST`. Any new test that forgets to patch, uses `tmp_kb_env`, and calls `ingest_source` or `kb_compile_scan` today writes to the real `PROJECT_ROOT/.data/hashes.json`. AC1/AC2 closes this hole at the fixture level; AC3 is the regression pin.

## 4. Data classification — `.data/ingest_log.jsonl` fields

| Field | Example | Classification | Handling requirement |
|---|---|---|---|
| `ts` | `"2026-04-20T15:22:31Z"` | Public | Emit UTC ISO-8601 with `Z` suffix. |
| `request_id` | `"a1b2c3d4e5f67890"` | Non-sensitive | 16 lowercase hex, 64-bit entropy. Correlation key only. |
| `source_ref` | `"raw/articles/karpathy-blog.md"` | Internal | Relative path from `RAW_DIR`. Never absolute. Never contains tokens like `C:\…`. |
| `source_hash` | `"a0b1c2…` (64 hex) | Non-sensitive | SHA-256 of source bytes. |
| `stage` | `"start"` \| `"success"` \| `"duplicate_skip"` \| `"failure"` | Public | Enum — do NOT allow free-form values. |
| `outcome.pages_created` | integer | Non-sensitive | Count only, not slugs (page slugs may echo title — safer as counts per cycle-18 scope; slugs can be added in a later cycle behind a feature flag). |
| `outcome.pages_updated` | integer | Non-sensitive | Count only. |
| `outcome.pages_skipped` | integer | Non-sensitive | Count only. |
| `outcome.error_summary` | string | **REDACTION REQUIRED** | Pass through `sanitize_error_text`-style regex sweep. Absolute paths → `<path>`. See §9 for the clean extraction recommendation. |

Deliberately excluded (never written): raw source content, wiki page bodies, extraction JSON, LLM prompts or responses, caller-supplied `extraction` dict, `ANTHROPIC_API_KEY` or any env-derived secret.

## 5. Authn / authz

- `file_lock` is **cooperative advisory locking only** — a lock file at `<path>.lock` with the holder's PID. A third-party tool (ad-hoc shell script, an external indexer, a rogue process) that ignores the `.lock` sibling and opens `wiki/log.md` or `.data/ingest_log.jsonl` directly in append mode will still interleave writes with the cycle 18 rotate-in-lock path. The cycle 18 guarantees are against concurrent `ingest_source` processes running under the same cooperative protocol, NOT against arbitrary filesystem clients.
- Stale-lock detection (`io.py:298-346`) uses `os.kill(pid, 0)`. On Windows, PID recycling means a stale lock from a dead holder with a re-used PID can appear live and delay steal-over-deadline by the full `LOCK_TIMEOUT_SECONDS`. Documented at `io.py:240-246`.
- No authz gate between `ingest_source` and the `.data/ingest_log.jsonl` writer — the library trusts any in-process caller. If a future CLI flag or MCP tool surface emits arbitrary strings into `stage` or `outcome.error_summary`, the redaction layer (AC13) is the sole defense.

## 6. Logging & audit requirements

- **Correlation invariant.** Every `wiki/log.md` line for an ingest event carries `[req=<hex>]` as the FIRST token of the `message` field (after the operation pipe). The SAME `<hex>` appears as the `request_id` field in the corresponding `.data/ingest_log.jsonl` row. `test_request_id_prefix_in_log_md` (AC15) pins this.
- **Rotation audit chain.** Both `wiki_log._rotate_log_if_oversized` (existing, `wiki_log.py:40-45`) and the new JSONL rotation path MUST emit `logger.info("Rotating %s (%d bytes) → %s", …)` BEFORE `Path.rename()`. Existing wiki-log rotation already satisfies this; cycle 18's generic `rotate_if_oversized` helper MUST preserve the same pre-rename log, so a mid-rotate crash leaves a trail ("about to rotate X to Y") even if rename fails and the archive is missing.
- **Emission ordering per `ingest_source` call.** Sequence: (1) generate `request_id`, (2) emit JSONL `stage=start`, (3) all ingest work, (4) emit JSONL `stage=success`/`duplicate_skip`/`failure`, (5) append wiki/log.md message with `[req=<hex>]`. If step 4 fails (e.g., disk full), step 5 still runs (best-effort; mirrors existing `OSError` swallow at `pipeline.py:1097`).

## 7. Threat items (Step 11 verification checklist)

- **T1 — `.data/ingest_log.jsonl` leaking raw source content / secrets / absolute paths.**
  - Mitigation: AC13 redaction via reused `sanitize_error_text` regex; field allowlist in AC11 restricts payload to `source_ref` (relative), `source_hash`, counts, enum `stage`, and a redacted `error_summary`. Raw source bytes never enter the writer. Regression test `test_jsonl_redacts_absolute_paths` (AC15).
  - Residual risk: LLM error strings from the Anthropic SDK can embed model names and request IDs; not sensitive but worth noting. If a future caller passes an `extraction` dict with an absolute path in a free-text field, that field never reaches the JSONL (AC11 schema locks payload fields). If a custom exception type shadows the `_ABS_PATH_PATTERNS` regex with a Unicode-normalized absolute path, the redaction misses it — LOW likelihood but documented.
- **T2 — `wiki/log.md` rotate-append race (POSIX handle-holding-stale-file).** Two processes concurrently append. Process A enters `append_wiki_log`, sees file over threshold, calls `_rotate_log_if_oversized` (outside lock today), renames file to `log.2026-04.md`. Process B, between the rotate check and the file_lock acquire, opens `log.md` by inode — on POSIX writes silently go to the renamed-away `log.2026-04.md`. Cycle 18 fix: AC4 moves the rotate call INSIDE `file_lock(log_path)`. Regression: `test_rotate_inside_lock` call-order spy (AC6) — NOT simulated concurrency.
  - Residual risk: rotation logic runs under the lock, so two concurrent rotators cannot both resolve the same ordinal. BUT the lock is per-path — if the rotation target filename (e.g. `log.2026-04.2.md`) doesn't exist when process A checks but EXISTS when process B checks because A's rename just landed, both processes correctly pick distinct ordinals. See T6 for the adjacent JSONL scenario.
- **T3 — `inject_wikilinks` cross-process page clobber.** `linker.py:203-263` reads, match-checks, and `atomic_text_write`s without a lock. Two concurrent ingests creating new pages `concepts/X` and `concepts/Y` that BOTH match inside page `entities/foo` race: each reads pre-inject content, each produces a one-link output, the second `replace()` wins, one wikilink is lost. Cycle 18 fix: AC7 wraps the per-page RMW in `file_lock(page_path)`. Fast-path: pages that will not be modified (no match, already-linked, self) MUST NOT acquire the lock; AC8 test asserts zero lock acquisitions for no-match pages.
  - Residual risk: lock overhead on large wikis — see T8. If a third-party editor holds the page open for write while `inject_wikilinks` tries to lock, the acquire times out after 5s and the ingest surfaces `TimeoutError`. Documented in existing `file_lock` contract.
- **T4 — `request_id` correlation break under fork() or spawn().** `uuid.uuid4()` draws from `os.urandom`, which is reseeded after `fork` on Linux (Python 3.12+ behaviour). Two children of the same parent each get independent uuid4 streams; cross-fork collision probability is 2^-64 per call. Not a real risk; documented so a future reader doesn't second-guess threading.
  - Residual risk: none beyond the birthday-paradox bound.
- **T5 — `tmp_kb_env HASH_MANIFEST` escape.** A test using `tmp_kb_env` but failing to patch `HASH_MANIFEST` today writes to `<PROJECT_ROOT>/.data/hashes.json`, polluting the developer's real manifest. Cycle 18 fix: AC1/AC2 add `HASH_MANIFEST` to the patched-names tuple and the mirror-rebind loop picks it up across `kb.*` modules. AC3 regression test pins the contract.
  - Residual risk: a test using `tmp_kb_env` that also imports `kb.compile.compiler.HASH_MANIFEST` into its own namespace (e.g. `from kb.compile.compiler import HASH_MANIFEST as _hm`) BEFORE `tmp_kb_env` runs can still hold the pre-patch value. The mirror loop only rebinds `kb.*` modules; test modules are `tests.*`. Not a production risk; noted for future test-author guidance.
- **T6 — Rotation-event ordinal collision.** Two processes concurrently calling `_emit_ingest_jsonl` with an oversized file BOTH compute next ordinal as `2` before either rename lands. Second rename can either fail (POSIX `rename` onto existing file overwrites silently; Windows raises `FileExistsError`) or silently truncate the first archive.
  - Mitigation: AC11 wraps the JSONL append (and rotation per AC12) inside `file_lock(jsonl_path)`. The helper `rotate_if_oversized` (AC5) is ONLY called under a lock in both call sites (AC4 wiki-log and AC11 ingest-log). The `while archive.exists(): ordinal += 1` loop at `wiki_log.py:36-39` then runs single-threaded within the lock scope.
  - Residual risk: non-kb processes bypassing the lock (see §5) can still trigger ordinal collision.
- **T7 — JSONL parseability under partial writes.** A crash between `write()` and `flush()` can leave a torn line in `.data/ingest_log.jsonl`. Downstream consumers doing `json.loads` per line will crash on the torn row.
  - Mitigation: AC11 uses `open("a", encoding="utf-8", newline="\n")` + `json.dumps(row, ensure_ascii=False) + "\n"` + `flush()` + `os.fsync()`. Append-mode POSIX writes of <=PIPE_BUF bytes (~4KB) are atomic at the filesystem level; a row that fits in one write is either fully present or absent. Line-sized `json.dumps` output is ~300 bytes for cycle 18's field set — well under PIPE_BUF. Docs MUST note: "consumers should skip malformed lines with `try: json.loads(line) except json.JSONDecodeError: continue`" rather than crashing.
  - **IMPLEMENTER WARNING**: do NOT use `atomic_text_write` for the JSONL writer — its temp+rename semantics would replace the whole file on each append, destroying history. Use direct `open("a") + write + fsync` under `file_lock`. See §9 action item.
  - Residual risk: on Windows, append-mode atomicity is weaker; a mid-write crash can leave a torn line. Downstream consumers' defensive `try/except` line parsing is the mitigation.
- **T8 — Lock overhead on `inject_wikilinks` SLO concern (not security).** A wiki with 5000 pages, 20 wikilink-candidate pages per ingest, acquires + releases 20 `file_lock` instances per ingest IF the fast-path is correctly wired. Without the fast-path, 5000 lock round trips per ingest — each is a `.lock` file create + unlink (~1-2ms on SSD, slower on network mounts). Target: inject_wikilinks stays under 500ms on a 5000-page wiki, matching current baseline. AC8 fast-path test pins zero-lock no-op contract.
  - Residual risk: on OneDrive/SMB mounts, even 20 lock acquisitions can add 500ms+ latency. Not cycle 18's problem but noted for future batch form (cycle 17 AC21 deferred `inject_wikilinks_batch`).
- **T9 (new) — `wiki/log.md` pipe-format injection via `[req=…]` prefix.** `request_id = uuid.uuid4().hex[:16]` is hex-only so cannot contain `|`/`\n`/`[`/`#`. The `[req=<hex>]` prefix is emitted before the caller-supplied `message` and the existing `_escape_markdown_prefix` only scans for leading `#`/`-`/`>`/`!` which `[req=` does not start with. Safe by construction.
  - Residual risk: if a future change makes `request_id` non-hex (e.g., switching to a url-safe base64 `uuid.uuid4().bytes` encoding), `+` / `/` / `=` characters could collide with markdown or pipe tokens. Keep the `hex[:16]` contract unless explicitly re-threat-modeled.
- **T10 (new) — AC14 spec-vs-reality symbol drift.** Requirements doc names `_update_sources_md` + `_update_index_md`; actual helpers are `_update_sources_mapping` + `_update_index_batch`. If implementer follows the doc literally and adds NEW functions by those names, the existing helpers are orphaned and the 2 test monkeypatches at `test_v01008_ingest_pipeline_fixes.py:98-99` silently bypass the new wrapper. See §9 action item.
  - Mitigation: Step 5 design-gate reconciles AC14/AC15 to use actual symbol names `_update_sources_mapping` + `_update_index_batch` (OR renames both with a full caller-grep pass per `feedback_signature_drift_verify`).

## 8. One-line CVE baseline summary

`Baseline: 0 open Dependabot alerts (S=0, M=0, L=0); 1 pip-audit advisory (diskcache CVE-2025-69872).`

Source files: `/tmp/cycle-18-alerts-baseline.json` (empty array), `/tmp/cycle-18-cve-baseline.json` (1 vuln total across 100+ deps).

## 9. Action items surfaced by this threat model

1. **AC14/AC15 symbol-name reconciliation (MUST resolve at Step 5 design gate)**: Requirements doc references `_update_sources_md` + `_update_index_md`; actual symbols are `_update_sources_mapping` + `_update_index_batch`. Recommended decision: rewrite AC14/AC15 in-place to reference the real symbols. Renaming the helpers would require a cycle-19 caller-grep pass (10-site monkeypatch update) per `feedback_signature_drift_verify` — out of scope for cycle 18.
2. **AC13 redaction helper shape (MUST resolve at Step 5)**: `sanitize_error_text(exc, *paths)` takes an exception, not a string. Extract sibling `sanitize_text(s: str) -> str` in `kb.utils.sanitize` that shares the `_ABS_PATH_PATTERNS` regex sub. `_emit_ingest_jsonl` calls the string form; `sanitize_error_text` calls the string form internally after exception-attribute sweep. No behavior change for existing callers.
3. **AC11 writer mechanics (implementer note)**: Do NOT use `atomic_text_write` for the JSONL append path — its temp+rename semantics replace the file and destroy history. Use `file_lock(jsonl_path)` + `open("a", encoding="utf-8", newline="\n")` + `f.write(json.dumps(row, ensure_ascii=False) + "\n")` + `f.flush()` + `os.fsync(f.fileno())`. Consumers must use defensive line parsing (`try/except json.JSONDecodeError`).
4. **AC12 rotation call-site (implementer note)**: The `rotate_if_oversized` call in `_emit_ingest_jsonl` MUST run INSIDE `file_lock(jsonl_path)`, symmetric with AC4's wiki-log fix. Do not repeat the existing "rotate outside lock" anti-pattern that AC4 is explicitly removing.
5. **R3 mandatory** per requirements §R3 — three of four triggers fire (new FS write surface, vacuous-test regression risk, new security enforcement point). Plan 3-round PR review per `feedback_3_round_pr_review`.
