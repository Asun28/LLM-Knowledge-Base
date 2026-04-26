# Cycle 35 Threat Model

Generated 2026-04-26 by Opus subagent. Becomes the Step 11 verification checklist.

## Baseline summary

- **Dependabot open alerts (`gh api .../dependabot/alerts` 2026-04-26 13:25):** 6 — 3 high (GitPython 3.1.46 ×2 fix=3.1.47; litellm 1.83.0 ×2 + 1 high), 1 critical (litellm GHSA-r75f-5x8p-qvmc fix=1.83.7), 1 low (ragas GHSA-95ww-475f-pr4f fix=null)
- **pip-audit live-env (`pip-audit --format json` 2026-04-26):** 4 vulns — diskcache 5.6.3 CVE-2025-69872 (no upstream fix); litellm 1.83.0 GHSA-xqmj-j6mv-4862 (fix=1.83.7 blocked by click<8.2 transitive); pip 26.0.1 CVE-2026-3219 (no upstream fix); ragas 0.4.3 CVE-2026-6587 (no upstream fix)
- **PR-introduced advisories expected at Step 11:** 0 (no dependency changes planned in cycle 35 ACs)
- **Class-A opportunistic patch (Step 11b) candidates:** GitPython 3.1.46 → 3.1.47 (patched fix available, NOT in BACKLOG narrow-role exception list — must bump). litellm/ragas/diskcache/pip remain narrow-role-exception per BACKLOG M4/M5/M6/M7.

## Analysis

### File group A — `utils/sanitize.py` UNC bypass (M12)

**Output flow.** `sanitize_text` is called from three sites: `kb.lint._safe_call.sanitize_error_text` (lint failure rows in `verdicts.jsonl`), `kb.mcp.app._sanitize_error_str` (MCP `Error[partial]:` strings returned to the client AND written to `wiki/log.md` via `_emit_ingest_jsonl`), and `kb.ingest.pipeline.sanitize_text` (refine telemetry). Every Windows `OSError.filename` flows through `_rel(Path(fn_str))` first which slash-normalises `\\server\share\path` to `//server/share/path` BEFORE the regex sweep. The current `_ABS_PATH_PATTERNS` UNC alternative is backslash-only, so the slash-normalised form survives.

**Other slash-normalised shapes the regex misses.** The forward-slash UNC long-path `//?/UNC/server/share/...` does NOT match either current alternative. AC1 must add `(?://[^\s'\"?/]+/[^\s'\"]+(?:/[^\s'\"]*)?)`. The slash UNC long-path is a **T1b** follow-up if the Step-11 REPL probe confirms a leak.

### File group B — `ingest/pipeline.py` RMW races (M11) + empty-list (M13) + backtick (M14)

**Concurrency model.** `_update_sources_mapping` and `_update_index_batch` are called ONLY from `_write_index_files` (pipeline.py:884-888). `_write_index_files` is invoked from `ingest_source`. `kb.cli.compile` and the MCP `kb_ingest_content` / `kb_ingest` tools both invoke `ingest_source`. Concurrent runs race the read-modify-write window on `wiki/_sources.md` and `wiki/index.md`.

**Empty-list & backtick threats.** `source_ref` content originates from `raw/<subdir>/<file>.md` paths the user types via `kb ingest`. Backticks in raw filenames are unusual but legal on POSIX; on re-ingest the membership check `if f"\`{source_ref}\`" not in content` succeeds against the escaped-backtick form already in the file, defeating dedup. Empty `wiki_pages` writes a syntactically valid bullet that pollutes `_sources.md` and confuses any parser that splits on `→`.

### File group C — `mcp/core.py` filename validator parity (M15)

**Threat surface.** `kb_ingest_content(filename)` and `kb_save_source(filename)` accept free-form filenames at the MCP boundary. Both flow through `slugify(filename) or "untitled"` then build `type_dir / f"{slug}.md"` — a real filesystem path. `slugify` preserves Cyrillic and CJK via `\w`, so a Cyrillic homoglyph creates a different bytestring than the visually-identical ASCII. NUL bytes pass too: `os.open` truncates at NUL on POSIX. Windows-reserved names (`CON.md`, `NUL`) cause `os.open` to either fail with confusing errors or address the device.

**Helper split.** AC12's `_validate_filename_slug` should reject NUL / path-separator / Windows-reserved / non-ASCII letters / oversized — but NOT enforce `slugify(slug) == slug` (a free-form filename like `My Document.md` legitimately differs from its slug). `_validate_save_as_slug` keeps the strict round-trip.

### File group D — `docs/architecture/` v0.11.0 sync (M21)

Pure documentation drift; no security threat surface. Auditors trust the embedded PNG (referenced from `README.md`); HTML diagram is the source-of-truth that re-renders the PNG.

## Threat model checklist

```
T1: sanitize.py — UNC slash-normalize bypass leaks server/share names
  Trust boundary: OSError.filename -> sanitize_text -> MCP Error[partial]: + wiki/log.md + verdicts.jsonl
  Data classification: internal; secret-bearing if share name encodes infra (e.g. \\corp\backup-prod-keys$)
  Authn/authz: MCP boundary returns Error[partial]: to any client; log.md is committed to git
  Logging/audit: must redact server / share / file basename to <path>
  Verification:
    - rg -n "_ABS_PATH_PATTERNS" src/kb/utils/sanitize.py — confirm forward-slash UNC alternative present
    - python -c "from kb.utils.sanitize import sanitize_text; print(sanitize_text('//corp.example.com/share$/secret.md'))" — must print "<path>" only
    - pytest tests/test_cycle33_mcp_core_path_leak.py::TestSanitizeErrorTextUNCAndLongPath -v — xfail marker REMOVED + new positive test passes
    - mentally revert AC1: confirm test_forward_slash_unc_redacts_via_extended_pattern would FAIL
  Same-class peers: kb.lint._safe_call (verdicts.jsonl), kb.mcp.app:_sanitize_error_str, kb.ingest.pipeline:_emit_ingest_jsonl, _update_sources_mapping warning
  T1b (defer-able): //?/UNC/server/share/... slash-normalised long-path UNC — REPL-probe at Step 11; add as same-cycle fix if leaks

T2: pipeline.py — _sources.md RMW race lost-update
  Trust boundary: concurrent ingest_source callers (MCP + CLI) -> shared wiki/_sources.md
  Data classification: internal (source mapping)
  Authn/authz: n/a — local FS
  Logging/audit: file_lock acquire/release already logged via existing infrastructure
  Verification:
    - rg -n "with file_lock\(sources_file\)" src/kb/ingest/pipeline.py — confirm lock spans read_text + atomic_text_write for BOTH branches (new-entry + dedup-merge)
    - pytest tests/test_cycle35_*::test_update_sources_mapping_holds_file_lock_across_rmw -v
    - revert AC4 → test fails (call-order spy confirms lock NOT acquired before read)
  Same-class peers: T3; HASH_MANIFEST writes already locked

T3: pipeline.py — index.md RMW race lost-update
  Trust boundary: concurrent ingest_source callers -> shared wiki/index.md
  Verification:
    - rg -n "with file_lock\(index_path\)" src/kb/ingest/pipeline.py — single span covers read_text + atomic_text_write
    - early-return at entries==[] MUST stay BEFORE the lock acquisition (no point locking a no-op)
    - pytest tests/test_cycle35_*::test_update_index_batch_holds_file_lock_across_rmw -v
  Same-class peers: T2

T4: pipeline.py — empty wiki_pages writes malformed "→ \n" line
  Verification:
    - rg -n "if not wiki_pages" src/kb/ingest/pipeline.py — guard appears immediately after docstring, BEFORE pages_str line
    - pytest tests/test_cycle35_*::test_update_sources_mapping_skips_empty_wiki_pages -v
    - byte-equal snapshot before/after assertion in test (per AC10)
  Same-class peers: _update_index_batch already has not-entries guard (precedent — same pattern applied here)

T5: pipeline.py — backtick in source_ref defeats dedup
  Trust boundary: user-controlled raw/ filename -> source_ref -> _update_sources_mapping membership check
  Verification:
    - rg -n "escaped_ref|source_ref" src/kb/ingest/pipeline.py — both membership check AND per-line scan use escaped_ref
    - pytest tests/test_cycle35_*::test_update_sources_mapping_dedups_backtick_in_source_ref -v
    - revert AC7 → test produces 2 lines instead of 1

T6a: mcp/core.py — NUL-byte in filename truncates server-side path
  Trust boundary: MCP client -> kb_ingest_content/kb_save_source(filename) -> os.open(file_path)
  Data classification: secret-bearing (filename can be silently renamed to attacker prefix)
  Verification:
    - rg -n "_validate_filename_slug" src/kb/mcp/core.py — helper exists, called from _validate_file_inputs
    - pytest tests/test_cycle35_*::test_validate_file_inputs_rejects_nul -v
    - python -c "from kb.mcp.core import _validate_file_inputs; print(_validate_file_inputs('foo\\x00.md', 'x'))" — returns Error string

T6b: mcp/core.py — Cyrillic homoglyph filename creates lookalike file
  Verification:
    - python -c "from kb.mcp.core import _validate_file_inputs; print(_validate_file_inputs('а.md', 'x'))" — Cyrillic а U+0430 returns Error
    - pytest tests/test_cycle35_*::test_validate_file_inputs_rejects_homoglyph -v

T6c: mcp/core.py — Windows-reserved filename (CON, PRN, NUL, AUX, COM1-9, LPT1-9)
  Verification:
    - rg -n "_is_windows_reserved" src/kb/mcp/core.py — imported, used in helper
    - pytest tests/test_cycle35_*::test_validate_file_inputs_rejects_windows_reserved -v with parametrize CON.md, PRN.txt, NUL, AUX, com1.md

T6d: mcp/core.py — path separator in filename allows directory traversal
  Trust boundary: MCP client -> filename containing / or \ -> type_dir / slug builds escaped path
  Data classification: secret-bearing (write outside type_dir)
  Verification:
    - python -c "from kb.mcp.core import _validate_file_inputs; print(_validate_file_inputs('../escape.md', 'x'))" returns Error; same for foo/bar.md and foo\\bar.md
    - pytest tests/test_cycle35_*::test_validate_file_inputs_rejects_path_separators -v

T6e: mcp/core.py — false-positive regression on legitimate ASCII filenames
  Verification:
    - pytest tests/test_cycle35_*::test_validate_file_inputs_accepts_valid -v with karpathy-llm-knowledge-bases.md, my_doc.md, file-2026-04-26.md
    - existing tests/test_mcp_*ingest_content* and *kb_save_source* test suites pass (no false reject)

T7: docs/architecture/ — version drift between HTML / PNG / pyproject.toml
  Trust boundary: doc reviewer -> embedded PNG (README) or HTML source
  Data classification: public (doc artifacts)
  Verification:
    - rg -n "v0\.10\.0|v0\.11\.0" docs/architecture/architecture-diagram.html docs/architecture/architecture-diagram-detailed.html — only v0.11.0 present
    - ls docs/architecture/*.png — confirm single architecture-diagram.png
    - file modification time on architecture-diagram.png is newer than commit baseline
    - manual: open the PNG, confirm visible v0.11.0 in the rendered title block

T8: pipeline.py — early-return ordering for empty-list AC6 must precede sources_file.exists() check
  Verification:
    - rg -n "if not wiki_pages" src/kb/ingest/pipeline.py — guard appears BEFORE sources_file.exists()
    - test asserts NO warning fires when sources_file is missing AND wiki_pages is empty (no log capture of "_sources.md not found")
  Same-class peers: T4 (sister AC); T3 already has the equivalent early-return

T9 (Step-11b opportunistic): GitPython 3.1.46 → 3.1.47 fixes 2 high-sev Dependabot alerts
  Trust boundary: dependency tree -> kb runtime
  Note: GitPython is NOT in BACKLOG narrow-role exception list. Patched fix exists. Step 11b MUST bump.
  Verification:
    - rg -n "^GitPython" requirements.txt — pin >= 3.1.47
    - pip-audit --format json post-bump — GitPython advisories absent
    - gh api .../dependabot/alerts post-bump — GitPython alerts auto-close
```

## Step 11 same-class peer scan (preview)

The cycle 35 changes do NOT introduce new path-containment / regex-escape / secret-redaction sites beyond T1's `_ABS_PATH_PATTERNS` extension. Step 11 must still grep:
- `rg "str.startswith\(str\(" src/kb` — no new instances (cycle-16 L1 anti-pattern peer scan)
- `rg "\.startswith\(str\(Path" src/kb` — no new instances
- `rg "with file_lock\(" src/kb/ingest src/kb/utils src/kb/compile` — confirm T2/T3 sites added; no peer site missed elsewhere in pipeline (`_write_index_files`, `_update_existing_page`, `_write_wiki_page` — last two already locked per cycle-19; verify before Step 12 docs)
