# Cycle 33 — R1 Codex Edge-Cases Eval (verbatim)

agentId: a439bfe961a0ce725 — completed in ~444s (~7.4min).

## Verdict: APPROVE-WITH-FIXES (AC1, AC2, AC4, AC5, AC6, AC7, AC8, AC9, AC10)

## MAJOR findings

| ID | AC | category | finding | mitigation |
|---|---|---|---|---|
| **R1-01** | AC1, AC2, AC5 | CROSS-PLATFORM / SECURITY | UNC + long-path filename attrs can be slash-normalised before the regex catches them. `_rel(Path(fn_str))` at `sanitize.py:30-31` replaces `\\` with `/`; `_ABS_PATH_PATTERNS` at `sanitize.py:13-17` only covers backslash UNC/long-path forms. AC5 only requires drive-letter + `/tmp` cases. | Add tests for `\\server\share\secret.md`, `\\?\C:\...`, `\\?\UNC\server\share\...`. For filename attrs outside PROJECT_ROOT prefer `<path>` redaction or sanitize before slash normalisation. |
| **R1-02** | AC4 | FAILURE-MODE | AC4 fixes only the `save_as` logger; the returned `[warn]` string at `core.py:281` calls `_sanitize_error_str(exc)` without `target` — relies only on whitespace-limited regex. Same Q2 Opus flagged. | Change return path to `_sanitize_error_str(exc, target)` too; add a save_as return-string regression. |
| **R1-04** | AC5 | TEST-FIXTURE POLLUTION | `kb_ingest_content` and `kb_save_source` create dirs/files under `SOURCE_TYPE_DIRS` BEFORE the failure point (`core.py:685-698, 816-847`). T9 only covers `wiki_dir=tmp_wiki` for index tests, not raw-source MCP tests. | Require `tmp_kb_env` or monkeypatch `kb.mcp.core.SOURCE_TYPE_DIRS` to a tmp raw tree before invoking AC5 tests; assert forced path is under tmp. |
| **R1-06** | AC6, AC7, AC8 | CONCURRENCY | `_update_sources_mapping` + `_update_index_batch` are RMW without lock. Concurrent calls can lose updates even though serial re-calls dedup correctly. | Either wrap each in `file_lock`, OR document AC6 as crash-reingest-only / explicitly non-concurrent + file a BACKLOG item. |
| **R1-07** | AC6, AC7, AC8 | DOCSTRING-ONLY RISK | AC6 promises second identical call is a NO-OP (no write), but AC7/AC8 only assert final file state. A refactor that writes the same content after dedup reordering would pass while breaking the no-op contract. | Spy/monkeypatch `kb.ingest.pipeline.atomic_text_write` and assert call count == 0 on second identical call. |
| **R1-12** | AC9, AC10 | LIFECYCLE | If R1-01/R1-04/R1-06/R1-07 are accepted as residual risks (not fixed), AC9/AC10 deletion would erase the audit-trail work. | Gate BACKLOG deletion on MAJOR fixes; OR replace deleted entries with narrower residual BACKLOG items + mention limitation in changelog. |

## MINOR findings

| ID | finding | mitigation |
|---|---|---|
| R1-03 | AC5 only exercises one 3-arg `OSError` shape — not `filename=None`, no `filename` attr, `filename2`, multi-arg, WinError 5/32/33, path text in `args[1]`. | Add parametrised `sanitize_error_text` unit suite + 1 MCP-integration custom-subclass case. |
| R1-05 | AC3 caplog assertion can be polluted by concurrent MCP calls in same process. | Filter caplog by logger + slug-unique substring; keep redaction tests serial. |
| R1-08 | `wiki_pages=[]` produces a source-mapping line with no page refs on first call (`pages_str` empty at `pipeline.py:770`); AC7/AC8 use only non-empty lists. | Specify behaviour for empty list and test it (likely no-op or validation). |
| R1-09 | AC8 doesn't cover `_sources.md` missing-file early-out at `pipeline.py:773-775`. | Add missing-file test OR clarify docstring guarantee assumes file exists. |
| R1-10 | `source_ref` containing backticks: `escaped_ref` written at line 771, raw lookup at lines 777/784 — repeat calls could duplicate (low risk for normal slugified MCP inputs). | Use `escaped_ref` for matching OR validate. Add direct-helper regression if helper remains callable. |
| R1-11 | Filename validation for `kb_ingest_content` / `kb_save_source` is weaker than `save_as` (no ASCII/reserved-name check; just empty + length + content size). | File BACKLOG item + tests for homoglyphs, null bytes, trailing dots, CON/NUL. |
