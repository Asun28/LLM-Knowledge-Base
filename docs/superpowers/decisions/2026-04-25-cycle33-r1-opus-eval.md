# Cycle 33 — R1 Opus Design Eval (verbatim)

agentId: a1cd2989375c67a00 — completed in ~140s.

## Final verdict

**PROCEED.**

The design is tight, defensible, and revert-fail compliant. The path-leak fix is a 5-line swap exploiting an already-imported helper that handles every leak shape the threat model enumerates. The idempotency pin is docstring + regression tests against an already-correct implementation — zero production-code change. Blast radius is minimal (5 line-level swaps + docstrings + ~70-100 LOC test code + 2 BACKLOG deletions + 3 CHANGELOG entries).

## Per-AC scoring (1-5)

| AC | scoring | notes |
|---|---|---|
| AC1 | 5 | Helper imported, exact shape, revert-fail via 3-arg OSError |
| AC2 | 5 | Same as AC1 for kb_save_source |
| AC3 | 5 | caplog T10 mitigation called out |
| AC4 | 5 | kb_query.save_as asymmetry close |
| AC5 | 5 | Two-platform fixture, 3-arg OSError mandated |
| AC6 | 4 | Docstring-only — soft; tests do heavy lifting |
| AC7 | 5 | Behaviour-over-signature |
| AC8 | 5 | Both dedup AND merge branches pinned |
| AC9 | 5 | Lifecycle rule explicit |
| AC10 | 5 | Same |

Average 4.9/5.

## Symbol verification

All 10 cited symbols (`_sanitize_error_str`, `sanitize_error_text`, `_rel`, `_update_sources_mapping`, `_update_index_batch`, `_write_index_files`, `WIKI_SOURCES`, `WIKI_INDEX`, `atomic_text_write`, `tmp_wiki`) EXIST at cited file/line. Zero MISSING / SEMANTIC-MISMATCH.

## Open questions for Step 5 decision gate

**Q1.** Pre-compute `_sanitize_error_str(write_err, file_path)` into a local var and reuse, or compute twice? *(optional — impl time)*

**Q2.** AC4 — line 281 already calls `_sanitize_error_str(exc)` without `target` path arg. Should the return string ALSO be upgraded to pass `target` for symmetry, or only the log line at 280? *(answer required at Step 5)*

**Q3.** AC3 — single pre-formatted message via `logger.warning("%s", msg)`, or multi-arg `logger.warning("...%s: %s; client must retry", _rel(file_path), sanitized_err)`? *(optional — impl time)*

**Q4.** AC5 — does "two platforms" mean conditional `pytest.mark.skipif(sys.platform != "win32")`, or both fixtures run unconditionally? *(answer required at Step 5)*

**Q5.** AC8 step (b) — explicit manifest-write failure simulation needed, or just NOT call manifest-save (since `_update_sources_mapping` doesn't touch manifest)? *(optional — impl time)*

**Q6.** Test file naming — `test_cycle33_*` cycle-prefix convention? *(optional — impl time)*

**Q7.** AC3 caplog needs `propagate=True` verified for `kb.mcp.core` logger? *(optional — impl time but verify Step 9)*

## Same-class peer scan summary

`Error[<tag>]:` emitters across `src/kb/mcp/`: exactly 2 — both in core.py at 762 + 881 (AC1+AC2 cover both).

Raw `{exception}` interpolation in MCP-tool returns:
- IN-CYCLE: core.py:281 (already sanitised, log line at 280 needs matching fix per AC4)
- OUT-OF-SCOPE-WITH-RESIDUAL-RISK: quality.py:216,396,596,642 — generic `except Exception as e` where exception may carry path. Regex sweep adequate today; future cycle candidate.
- OUT-OF-SCOPE: ~15 other sites — all pre-formatted helper output, JSONDecodeError, or value-parse errors with no path attribute.

## Concrete next-step commitments

(a) resolve Q2 and Q4 at Step 5 decision gate before implementation;
(b) pre-compute `_sanitize_error_str(write_err, file_path)` once per OSError site and reuse for both log + return string;
(c) ensure AC7 + AC8 tests read actual file content (not `inspect.getsource()`);
(d) AC3 + AC4 tests must use `caplog.set_level(logging.WARNING, logger="kb.mcp.core")` per T10;
(e) Step 11 verification must include the revert-fail check.
