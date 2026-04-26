# Phase 2 Workflows

> **Part of [CLAUDE.md](../../CLAUDE.md)** — detail for the "Phase 2 Workflows" section. Pairs with [mcp-servers.md](mcp-servers.md) (kb tool catalogue).

## Standard Ingest (with Self-Refine)

1. `kb_ingest(path)` — get extraction prompt
2. Extract JSON — `kb_ingest(path, extraction_json)`
3. For each created page: `kb_review_page(page_id)` — self-critique
4. If issues: `kb_refine_page(page_id, updated_content)` (max 2 rounds)

## Thorough Ingest (with Actor-Critic)

1-4. Same as Standard Ingest
5. Spawn wiki-reviewer agent with created page_ids
6. Review findings — fix or accept
7. `kb_affected_pages` — flag related pages

## Deep Lint

1. `kb_lint()` — mechanical report
2. For errors: `kb_lint_deep(page_id)` — evaluate fidelity
3. Fix issues via `kb_refine_page`
4. `kb_lint_consistency()` — contradiction check
5. Re-run `kb_lint()` to verify (max 3 rounds)

## Query with Feedback

1. `kb_query(question)` — synthesize answer
2. After user reaction: `kb_query_feedback(question, rating, pages)`
