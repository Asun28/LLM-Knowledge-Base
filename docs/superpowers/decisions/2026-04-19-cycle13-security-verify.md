# Cycle 13 — Step 11 Security Verification

**Date:** 2026-04-20
**Verifier:** Codex (`codex:codex-rescue`)
**Verdict:** **PASS**

## Threat-model item status

| T# | Threat | Status | Evidence |
|---|---|---|---|
| T1 | CLI-boot sweep deletes in-flight tmp | IMPLEMENTED | `src/kb/cli.py:108-110` calls `sweep_orphan_tmp(target)` with default `max_age_seconds=3600.0` (`src/kb/utils/io.py:154`); fresh-tmp retention tested at `tests/test_cycle13_sweep_wiring.py:65-79`. |
| T2 | `wiki_dir.parent / "raw"` directory escape | IMPLEMENTED | Lexical resolver at `src/kb/lint/augment.py:1014-1033`; `run_augment` routes through it at `src/kb/lint/augment.py:570-571`; four branches tested at `tests/test_cycle13_augment_raw_dir.py:28-67`. |
| T3 | Graph-export string `path` type mismatch | IMPLEMENTED | `Path(path)` wrap inside broad `try` at `src/kb/graph/export.py:127-135`; tested with `path=str(target)` at `tests/test_cycle13_frontmatter_migration.py:226-236`. |
| T4 | Cached helper stale on coarse-mtime FS | IMPLEMENTED | Write-back/read-after-write sites stay uncached (augment.py:1044-1046, 1064-1066, 1093-1095, 1123-1129); cache invalidation tested at `tests/test_cycle13_frontmatter_migration.py:80-100`. |
| T5 | Symlink traversal via NetworkX `path` | IMPLEMENTED | No new write site; helper reads via `stat()` + cached load (`src/kb/utils/pages.py:64-74`). |
| T6 | `WIKI_DIR` sweep deletes 3rd-party tmp | IMPLEMENTED | CLI sweeps only `{PROJECT_ROOT/.data, WIKI_DIR}` at `src/kb/cli.py:106-110`; helper scope is non-recursive `directory.glob("*.tmp")` at `src/kb/utils/io.py:157-160`; dedup tested at `tests/test_cycle13_sweep_wiring.py:81-111`. |
| T7 | Cache stale after out-of-process edit | IMPLEMENTED | Wrapper keys cache by `(str(page_path), mtime_ns)`; all migrated sites use wrapper, not the cached delegate. |

## New-vulnerability scan

- **Path traversal:** No new unsafe attacker-controlled write paths. New `Path()` uses are config-derived sweep targets and non-fatal graph title reads.
- **Injection:** No new shell/SQL construction in the modified sources.
- **Secrets:** No hard-coded tokens or keys found.
- **Input bounds:** Graph `Path(path)` wrapped in non-fatal try/except; raw-dir resolver is typed `Path` and lexical.
- **Same-class peers:** No unmigrated production peer found. Remaining `frontmatter.load` calls are in the helper itself or the 3 explicitly-out-of-scope augment write-back sites (AC6).

## Dep-CVE diff

- **Class A (existing on main):** 0 open Dependabot alerts (per Step 2 baseline). `diskcache==5.6.3` CVE-2025-69872 remains unpatched/upstream-unfixed and tracked in BACKLOG.
- **Class B (PR-introduced):** Empty. No `requirements.txt` / `pyproject.toml` changes in this cycle. `pip-audit` diff: branch advisory IDs minus baseline advisory IDs = ∅.

## Verdict

**PASS** — all 7 threat-model items implemented; 0 PR-introduced CVEs; no new vulnerability classes surfaced. Step 11.5 (existing-CVE patch) is a NO-OP this cycle (0 open alerts). Proceed to Step 12 (docs).
