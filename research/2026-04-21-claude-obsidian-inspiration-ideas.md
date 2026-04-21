# claude-obsidian Inspiration Ideas

Date: 2026-04-21

Source: https://github.com/AgriciDaniel/claude-obsidian

Purpose: collect high-value ideas from `claude-obsidian` that fit `llm-wiki-flywheel` without copying its implementation or weakening this project's stronger Python engine, test suite, MCP layer, publishing pipeline, and quality controls.

## Summary

`claude-obsidian` is strongest as workflow and product packaging around an Obsidian vault. `llm-wiki-flywheel` is stronger as a rigorous Python engine: ingest, query, lint, evolve, MCP tools, publishing, tests, and quality controls already exist.

The best opportunities are therefore not core ingest/query/lint rewrites. They are onboarding, vault UX, dashboards, session memory, capture ergonomics, and cross-project integration.

## Highest-Value Ideas

### 1. First-Run Wiki Onboarding

`claude-obsidian` uses `/wiki` as the main entry point: check setup, scaffold a vault, or continue an existing one.

Possible fit:

```bash
kb init
kb doctor
kb setup-obsidian
```

Possible MCP phrasing:

```text
Set up this folder as a wiki flywheel.
```

Why this fits:

- Reduces the gap between a powerful engine and a daily usable system.
- Can wrap existing config, template, raw/wiki directory, and MCP checks.
- Helps users avoid reading the full README before first value.

### 2. Mode-Based Vault Scaffolding

`claude-obsidian` offers modes such as Website, GitHub, Business, Personal, Research, and Book/Course.

Possible fit:

```bash
kb init --profile research
kb init --profile codebase
kb init --profile business-intel
kb init --profile course
kb init --profile personal
```

Each profile could generate:

- `wiki/purpose.md`
- starter folders
- source-type defaults
- query/lint thresholds
- templates
- dashboard pages
- recommended raw directories

Why this fits:

- The project already has source types, templates, `purpose.md`, and publishing.
- Profiles make the system easier to understand without hard-coding one use case.

### 3. Hot Cache / Session Memory

`claude-obsidian` maintains `wiki/hot.md` as recent context for future sessions.

Possible fit:

```bash
kb hot update
kb hot show
```

Potential `wiki/hot.md` contents:

- recently ingested sources
- recently changed pages
- open contradictions
- stale or high-value pages
- current project purpose
- top unresolved gaps from `kb evolve`

Why this fits:

- Small feature with high daily workflow value.
- Helps MCP and agent clients quickly regain project context.
- Complements existing logs, lint, query, and evolve features.

### 4. Conversation Save Workflow

`claude-obsidian` has `/save` and `/save [name]` for filing conversations as wiki notes.

`llm-wiki-flywheel` already has `kb_capture`, but the UX could be more direct.

Possible fit:

```bash
kb save-session --title "Cycle 21 design review" transcript.md
kb capture --as decision
kb capture --as gotcha
```

Possible MCP phrasing:

```text
Save this conversation into the wiki as a design decision.
```

Why this fits:

- Most core machinery already exists.
- A polished workflow would turn captures into an obvious user behavior.
- Useful for design decisions, gotchas, corrections, and discoveries.

### 5. Obsidian Dashboard Files

`claude-obsidian` creates dashboard files for Obsidian.

Possible fit:

```bash
kb dashboard
kb dashboard --write wiki/meta/dashboard.md
```

Dashboard sections could include:

- recent sources
- pages by type
- open contradictions
- stale pages
- low-trust pages
- orphan pages
- top PageRank pages
- recent captures
- evolve suggestions

Why this fits:

- Makes existing quality and graph data visible in Obsidian.
- Turns CLI/MCP output into persistent wiki-native operational state.
- Low algorithmic risk compared with adding new extraction logic.

### 6. Vault Health Report

`claude-obsidian` markets lint as a clear vault health check.

`llm-wiki-flywheel` already has stronger lint machinery, but it could expose a more productized report.

Possible fit:

```bash
kb health
kb health --write wiki/meta/health.md
kb health --json
```

Why this fits:

- Repackages existing lint, stats, trust, and graph signals.
- Gives non-technical users a single place to inspect wiki condition.
- Can become the main dashboard input.

### 7. Autonomous Research Loop

`claude-obsidian` has `/autoresearch [topic]`: search, fetch, synthesize, and file.

Possible fit:

```bash
kb research "topic" --rounds 3 --profile academic
```

Possible pipeline:

1. Query the existing wiki.
2. Detect gaps.
3. Search and fetch sources.
4. Save sources to `raw/`.
5. Ingest them.
6. Generate a synthesis page.
7. Record confidence and unresolved gaps.

Why this fits:

- Builds on existing `lint --augment`, raw saving, ingestion, query formats, and research folders.
- High product value for research users.

Risks:

- Network behavior, source quality, citation trust, and repeatability need careful constraints.
- Should be opt-in and conservative.

### 8. Obsidian Setup Polish

`claude-obsidian` ships Obsidian graph colors, snippets, templates, and recommended plugins.

Possible fit:

```bash
kb obsidian configure
```

Could generate or update:

- graph filters
- folder colors
- useful CSS snippets
- dashboard note
- template folder
- recommended plugin list

Why this fits:

- Makes the generated wiki feel like a product instead of loose markdown files.
- Leverages Obsidian without making it mandatory.

### 9. Cross-Project Knowledge Base Instructions

`claude-obsidian` suggests adding a wiki knowledge-base section to other projects' agent instructions.

Possible fit:

```bash
kb integration claude --wiki-dir D:\path\to\wiki
kb integration codex --wiki-dir D:\path\to\wiki
```

Generated guidance could tell agents:

1. Read `wiki/hot.md` first.
2. Read `wiki/index.md` if needed.
3. Query via MCP when available.
4. Avoid using the wiki for unrelated coding tasks.
5. Cite wiki page IDs.

Why this fits:

- Turns the project into a shared local knowledge substrate across coding projects.
- Supports Claude Code, Codex, Cursor, and other agent clients.

### 10. Friendlier Workflow Aliases

`claude-obsidian` emphasizes simple verbs like `/wiki`, `ingest`, `/save`, `/autoresearch`, and natural-language linting.

Possible fit:

```bash
kb add <file-or-url>
kb ask "..."
kb check
kb remember <file>
kb research "..."
kb dashboard
```

Why this fits:

- Can wrap existing commands with minimal implementation risk.
- Makes the CLI easier for non-expert users.

## Suggested Priority

1. `kb init --profile ...` plus `kb doctor`
2. `wiki/hot.md` generation
3. `wiki/meta/dashboard.md` health dashboard
4. `kb save-session` / polished capture workflow
5. cross-project agent instruction generator
6. Obsidian setup polish
7. autonomous research loop

## What Not To Copy

Do not copy `claude-obsidian`'s core repo structure or skill-command layout wholesale.

`llm-wiki-flywheel` already has a stronger engine layer:

- Python package structure
- CLI and MCP surfaces
- extensive tests
- lint and contradiction systems
- publishing pipeline
- query formats
- backlog and changelog discipline

The useful move is to borrow the workflow patterns and user-facing packaging while keeping the existing engine architecture.

## Product Direction

The strategic direction is:

> Make `llm-wiki-flywheel` feel like a self-maintaining knowledge product, not only a library or CLI.

The next most practical step is to promote one or two ideas from this note into `BACKLOG.md` with narrow acceptance criteria.
