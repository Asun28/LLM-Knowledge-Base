# Contradictions

Explicit tracker for conflicting claims across sources.

| Claim A | Source A | Claim B | Source B | Status |
|---------|----------|---------|----------|--------|
| Cycle is "Ingest → Query → Lint" (3 ops) | raw/papers/karpathy-llm-wiki-gist.md | Project extends to "Ingest → Compile → Query → Lint → Evolve" (5 ops) | CLAUDE.md | reconciled — gist is the minimal pattern; this project adds `compile` and `evolve` as explicit stages |
