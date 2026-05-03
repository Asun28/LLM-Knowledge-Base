# Cycle 62 Design

## Decision
Use a pure freeze-and-fold test hygiene design: move the selected tests into
existing canonical receivers, keep assertions intact, apply only small helper
renames/import fixes needed for receiver compatibility, then delete the source
files.

## Selected Folds
| # | Source | Receiver |
|---:|---|---|
| 1 | `tests/test_v0917_rewriter.py` | `tests/test_query.py` |
| 2 | `tests/test_v0917_raw_fallback.py` | `tests/test_query.py` |
| 3 | `tests/test_v5_augment_config.py` | `tests/test_config.py` |
| 4 | `tests/test_v5_verdict_augment_type.py` | `tests/test_lint_verdicts.py` |
| 5 | `tests/test_v01002_consolidated_constants.py` | `tests/test_config.py` |
| 6 | `tests/test_v0917_layered_context.py` | `tests/test_query.py` |
| 7 | `tests/test_v0917_hybrid.py` | `tests/test_query.py` |
| 8 | `tests/test_v5_autogen_prefixes.py` | `tests/test_lint.py` |
| 9 | `tests/test_v0917_embeddings.py` | `tests/test_query.py` |
| 10 | `tests/test_v0917_contradiction.py` | `tests/test_ingest.py` |
| 11 | `tests/test_v01004_query_correctness.py` | `tests/test_query.py` |
| 12 | `tests/test_v01005_query_perf_docs.py` | `tests/test_query.py` |
| 13 | `tests/test_v01006_compile_fixes.py` | `tests/test_compile.py` |
| 14 | `tests/test_v0917_stale_query.py` | `tests/test_query.py` |
| 15 | `tests/test_v01010_lint_fixes.py` | `tests/test_lint.py` |
| 16 | `tests/test_v0917_dedup.py` | `tests/test_query.py` |
| 17 | `tests/test_v4_11_cli.py` | `tests/test_cli.py` |
| 18 | `tests/test_v0917_evidence_trail.py` | `tests/test_ingest.py` |
| 19 | `tests/test_v4_11_markdown.py` | `tests/test_query.py` |
| 20 | `tests/test_v4_11_mcp.py` | `tests/test_mcp_core.py` |

## Why
- Directly advances the open coverage-visibility backlog.
- All selected source tests pass before folding.
- Existing receivers avoid adding a new top-level test file, so the file-count
  reduction is the full 20.
- No runtime behavior or dependency surface changes.

## Rejected Alternatives
- Implement production backlog items: higher risk and not aligned with the
  20-item test-fold request.
- Create `tests/test_query_formats.py`: cohesive for v4.11 format tests, but
  would reduce file count by 19 instead of 20 and is not needed for this cycle.
- Fold larger lint-augment/rate files: valid future work, but lower priority
  than the current smallest green-baseline slice.

## Risk Controls
- Preserve tests rather than rewriting behavior.
- Rename only collision-prone helpers.
- Avoid rebinding existing globals in receivers.
- Run targeted receiver tests, ruff, full pytest, docs verifier, and PR review.

Design status: APPROVED.
