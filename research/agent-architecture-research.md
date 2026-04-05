# Agent Architecture Research for LLM Knowledge Base

*Researched 2026-04-06. Focused on practical, implementable patterns for the ingest/compile/query/lint cycle.*

---

## 1. Agent Orchestration Patterns

### 1A. LangGraph: Supervisor, Swarm, and Pipeline Topologies

LangGraph offers three fundamental multi-agent topologies. The right choice depends on coordination needs, not model choice.

**Supervisor Pattern**
A central supervisor agent receives all requests and delegates to specialized worker agents. All results flow back through the supervisor. Provides strong auditability (single audit point), error recovery, and task-completion verification. Higher token consumption due to routing overhead.

**Swarm Pattern**
Agents hand off directly to each other without a central coordinator. The active agent responds to the user. ~40% reduction in response time and LLM calls vs supervisor. Better for open-ended, exploratory work. Harder to audit.

**Pipeline Pattern**
Agents arranged sequentially: Agent A's output feeds Agent B, whose output feeds Agent C. Best for strict dependencies like document processing chains. Maps cleanly to our ingest -> compile -> lint cycle.

**Decision Framework** (from [paperclipped.de](https://www.paperclipped.de/en/blog/multi-agent-architecture-patterns-design/)):
1. Subtask independence? Independent -> fan-out; strict dependencies -> pipeline; mixed -> hybrid
2. Known task categories? Predictable -> coordinator/router; open-ended -> swarm
3. Auditability needs? Regulated/traceable -> supervisor; exploratory -> swarm
4. Agent count? Minimize. Google research shows 39-70% performance degradation with unnecessary agents

**Production reality**: Most successful systems are hybrids. Example: three agents research in parallel, a fourth orchestrator validates contradictions and decides when analysis is complete.

**Critical anti-pattern**: "You cannot prompt your way out of a system-level failure." When agents produce contradictory results, the fix is coordination redesign, not better prompts.

**How it maps to our cycle**:
- **Pipeline** for the core cycle: Ingest -> Compile -> Lint (strict sequential dependencies)
- **Supervisor** for Compile (orchestrator reads index, identifies affected pages, dispatches per-page updates)
- **Fan-out** for Query (search wiki pages in parallel, synthesize)
- Overall: a **hybrid pipeline-supervisor** architecture

Sources:
- [Multi-Agent Architecture Patterns Guide 2026](https://www.paperclipped.de/en/blog/multi-agent-architecture-patterns-design/)
- [LangGraph Supervisor vs Swarm Patterns](https://focused.io/lab/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture)
- [LangGraph Subgraphs: Compose Reusable Workflows](https://machinelearningplus.com/gen-ai/langgraph-subgraphs-composing-reusable-workflows/)
- [Autonomous AI Agents: Cyclic Workflows with LangGraph](https://learnwithneeraj.com/ai-gen-ai/agentic-ai/building-autonomous-ai-agents-the-agentic-brain-with-langgraph)

---

### 1B. LangGraph: Cyclical Workflows with Conditional Routing

The key LangGraph pattern for iterative refinement: **conditional edges** that dynamically route execution based on state evaluation. After a Critic node processes content, the system evaluates constraints and decides whether to loop back for revision or advance.

```python
def review_routing(state):
    needs_revision = state.get("feedback") is not None
    under_loop_limit = state.get("revision_count", 0) < 3
    return "writer_node" if needs_revision and under_loop_limit else "next_node"
```

Key architectural elements:
- **AgentState TypedDict** enforces a strict schema between nodes (prevents hallucinated keys)
- **revision_count** implements cost security (prevents infinite loops draining API budgets)
- **Sequential finalization** prevents race conditions in downstream nodes

**How it maps to our cycle**:
- Compile operation: Writer (generates wiki page) -> Critic (checks source fidelity, consistency) -> conditional route back to Writer if issues found
- Lint operation: iterative pass with capped revision rounds
- Each lint check (orphans, dead links, staleness) could be a separate node in the graph

Source: [Autonomous AI Agents with LangGraph](https://learnwithneeraj.com/ai-gen-ai/agentic-ai/building-autonomous-ai-agents-the-agentic-brain-with-langgraph)

---

### 1C. DSPy: Structured LLM Pipelines

DSPy (Declarative Self-improving Python) from Stanford NLP treats LLMs as programmable layers rather than prompt endpoints. Three core concepts:

**Signatures**: Input/output contracts for LLM calls. Declare *what* flows in/out; DSPy generates optimized prompts. Like type annotations for LLM behavior.

**Modules**: Reusable building blocks — `ChainOfThought`, `ReAct`, `ProgramOfThought`, `MultiChainComparison`. Compose these like neural network layers.

**Optimizers**: Algorithms that automatically refine entire pipelines by selecting optimal instructions and few-shot examples. `BootstrapFewShot` and `MIPROv2` need as few as 10-20 examples.

**Teacher-Student Pattern** ([KazKozDev/dspy-optimization-patterns](https://github.com/KazKozDev/dspy-optimization-patterns)):
1. Expensive teacher model (Opus) optimizes instructions + few-shot examples against a metric
2. Compiled optimizations saved as versioned JSON artifacts
3. Cheap student model (Haiku) loads artifacts for production inference
4. Claimed 50x inference cost reduction

**How it maps to our cycle**:
- Define `IngestSignature(source_text -> summary, entities, claims)` as a typed contract
- Define `CompileSignature(source_summary, existing_page -> updated_page, diff)` for wiki compilation
- Use Optimizer to automatically find best prompts for each operation given a small labeled set of good wiki pages
- Teacher-Student: Opus optimizes the pipeline offline; Sonnet/Haiku runs it daily
- Each source-type template (paper, article, video, repo) could be a separate DSPy Module

Sources:
- [DSPy on AgentWiki](https://agentwiki.org/dspy)
- [DSPy Teacher-Student Optimization](https://github.com/KazKozDev/dspy-optimization-patterns)
- [DSPy 3: Build, Evaluate, Optimize](https://amirteymoori.com/dspy-3-build-evaluate-optimize-llm-pipelines/)
- [Beyond Prompt Engineering with DSPy](https://medium.com/@vsanmed/beyond-prompt-engineering-building-maintainable-and-high-performing-llm-pipelines-with-dspy-73e0caac948a)

---

### 1D. Claude Code's Own Agent/Subagent Patterns

Claude Code supports three sub-agent execution modes:

**Parallel Execution**: Deploy multiple independent sub-agents simultaneously. Requires: 3+ unrelated tasks, no shared state, clear file boundaries. Typical setup: Opus main session, Sonnet sub-agents (via `CLAUDE_CODE_SUBAGENT_MODEL`).

**Sequential Execution**: Chain sub-agents when downstream work depends on upstream output. Task B requires Task A's results, shared files create merge conflict risk.

**Background Execution**: Async agents for research/analysis while work continues. Documentation lookups, security audits, non-blocking exploration.

**Worktree Isolation**: Git worktrees provide separate filesystem contexts for parallel work, preventing interference between concurrent agents.

**Agent Definition**: Define specialist agents as markdown files in `.claude/agents/` with YAML frontmatter. These inherit the project's CLAUDE.md context automatically.

**Critical lesson**: Most sub-agent failures stem from poor invocation quality, not execution limits. "Fix authentication" wastes tokens. "Fix OAuth redirect loop where successful login redirects to /login instead of /dashboard. Reference auth middleware in src/lib/auth.ts" succeeds.

**How it maps to our cycle**:
- **Ingest**: Sequential — read source -> extract entities -> write summary -> update index
- **Compile**: Parallel sub-agents for independent page updates (each page gets its own agent with focused context)
- **Query**: Background agent for search while user continues working
- **Lint**: Parallel sub-agents for independent checks (orphans, dead links, staleness, contradictions)
- Define `ingest-agent.md`, `compile-agent.md`, `query-agent.md`, `lint-agent.md` in `.claude/agents/`

Sources:
- [Claude Code Multi-Agent Advanced Guide](https://claudelab.net/en/articles/claude-code/claude-code-multi-agent-advanced)
- [Claude Code Sub-Agent Patterns](https://claudefa.st/blog/guide/agents/sub-agent-best-practices)
- [Parallel Sub-Agents in Claude Code](https://proofsource.ai/2025/12/parallel-sub-agents-in-claude-code-multiplying-your-development-speed/)

---

### 1E. Compiler Agents Maintaining Documentation

**Ars Contexta** ([agenticnotetaking/arscontexta](https://github.com/agenticnotetaking/arscontexta)) — 2.9k stars. Claude Code plugin that generates individualized knowledge systems through conversation.

Architecture:
- **Three-space separation**: `self/` (agent identity, slow growth), `notes/` (knowledge graph, steady accumulation), `ops/` (operational state, fluctuating)
- **6R Processing Pipeline**: Record -> Reduce -> Reflect -> Reweave -> Verify -> Rethink
- **"Reweave" is the key insight**: When new knowledge arrives, propagate context *backward* through existing notes, not just forward. This is what makes the system self-improving.
- Each pipeline phase spawns fresh subagents with their own context windows (attention quality preservation)
- Four hooks enforce quality: SessionStart (inject structure), PostToolUse/Write (validate schema), PostToolUse/Write async (auto-commit), Stop (persist session state)
- 249 interconnected research claims grounding structural decisions in cognitive science

**Remember.md** ([remember-md/remember](https://github.com/remember-md/remember)) — Simpler approach. Extracts knowledge from past Claude Code sessions. Retroactive processing scans old sessions. Uses YAML frontmatter + wikilinks for Obsidian compatibility.

**Cursor's Background Agents for Documentation** — Cursor enables background agents that automatically update documentation after code changes. Ships features while docs stay current.

**How it maps to our cycle**:
- Adopt Ars Contexta's **Reweave** concept: during Compile, don't just create new pages — propagate new knowledge backward through affected existing pages
- Adopt the **subagent-per-phase** pattern: each pipeline phase gets a fresh context window
- Adopt **hook-based enforcement**: PostToolUse hooks validate wiki page schema on every write
- The three-space separation (`self/notes/ops/`) is analogous to our `CLAUDE.md / wiki/ / wiki/log.md` layering

Sources:
- [Ars Contexta](https://github.com/agenticnotetaking/arscontexta)
- [Remember.md](https://github.com/remember-md/remember)
- [Cursor Background Agents](https://markaicode.com/cursor-background-agents-documentation/)

---

## 2. Quality Gate Patterns

### 2A. Multi-Loop Document Supervision (LangGraph)

The most sophisticated quality gate pattern found. From [tha.la](https://www.tha.la/editing/2026-01-08-multi-loop-supervision-system-langgraph):

Five sequential supervision loops, each targeting a specific quality dimension with strategically matched models:

| Loop | Target | Model | Rationale |
|------|--------|-------|-----------|
| 1 | Theoretical depth | Opus | Deep reasoning for conceptual gaps |
| 2 | Literature base | Opus | Missing foundational works |
| 3 | Structure | Opus + Sonnet | Opus analyzes, Sonnet executes |
| 4 | Section editing | Sonnet + Opus | Parallel refinement + holistic review |
| 4.5 | Cohesion check | Sonnet | Quick inter-section coherence; conditional route back to Loop 3 (max 2 repeats) |
| 5 | Fact-check | Haiku | Cost-effective citation verification |

**Key architectural insight**: Loops run sequentially because of content dependencies (Loop 2 excludes papers from Loop 1; Loop 3 needs stable content from 1 and 2). Parallelism occurs *within* loops, not across them.

**Quality tier configuration**: Configurable from "quick" (1 stage) to "high_quality" (5 stages).

**How it maps to our cycle**:
- Directly applicable to Lint operation: source fidelity check (Loop 1 equivalent), coverage check (Loop 2), structure check (Loop 3), per-page editing (Loop 4), fact-check (Loop 5)
- The conditional routing (Loop 4.5 -> Loop 3) maps to our "lint finds problems -> targeted re-compile" feedback loop
- Model tiering: Opus for reasoning about what's wrong, Sonnet for fixing it, Haiku for mechanical checks

---

### 2B. Multi-Model Convergence (Actor-Critic Pattern)

From [Zylos Research](https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence):

Five distinct multi-model review architectures:

1. **Actor-Critic**: Separate generation and review agents. Critical: the Critic operates in a *separate session* with no access to the Builder's conversation history. Isolation prevents inherited biases.

2. **Parallel Ensemble with Voting**: Multiple review passes over the same content with randomized ordering. Majority voting filters noise. Cursor's BugBot: 8 parallel passes, 70% resolution rate across 2M+ PRs/month.

3. **Multi-Review Aggregation**: Independent LLM passes feed an aggregator model. F1 improved 43.67% over single-pass. Returns plateau at 5-10 iterations.

4. **Specialist Routing**: Task-specific models handle distinct concerns (security, style, consistency). Reduced false positives by 51%.

5. **Hybrid Pipeline-Agentic**: Static analysis + AST graphs + semantic indexing *before* LLM prompting. Grounds LLM findings in reproducible evidence.

**Convergence trajectory**: 3-5 rounds typical. Documented case: 7 issues -> 4 -> 2 -> 1 -> 0 over 8 rounds.

**Oscillation prevention**: Role asymmetry (Critic flags, Actor fixes), context isolation, explicit termination tools, hard round limits, human escalation for unresolvable issues.

**Inter-model communication**: Structured JSON (severity, category, confidence, boundary_owner), not freeform text. Single-pass findings treated as noise.

**Foundational principle**: "Code review and code generation should be performed by distinct model instances." Self-review inherits *agreeableness bias*.

**How it maps to our cycle**:
- **Actor-Critic for Compile**: Compile agent writes wiki page; separate Lint agent (fresh context, no shared history) reviews it
- **Specialist routing for Lint**: Source fidelity checker, consistency checker, coverage checker, link validator as separate specialists
- **Structured findings**: Lint produces JSON-structured issues, not prose, enabling systematic tracking
- **Confidence thresholds**: Only flag issues that appear in multiple lint passes (parallel ensemble principle)

---

### 2C. Veritas Acta / Cryptographic Accountability

[VeritasActa/Acta](https://github.com/VeritasActa/Acta) — 1 star, very early. Open protocol for signed, independently verifiable machine decisions. Hash-chained ledger, typed contributions, VOPRF anonymous authorship.

Too immature to adopt directly, but the **concept** is valuable: every wiki modification should be traceable to a specific agent invocation, source file, and timestamp. Git already provides this if we commit on every operation.

**How it maps to our cycle**:
- Each ingest/compile operation produces a git commit (already planned in log.md)
- Commit messages include: source file, pages affected, model used, confidence level
- Git history becomes the audit chain; no need for a separate cryptographic layer at our scale

---

### 2D. RAGAS for Epistemic Quality Evaluation

RAGAS (Retrieval Augmented Generation Assessment) provides four metrics that map to knowledge base integrity:

| RAGAS Metric | Score | Knowledge Base Analog |
|---|---|---|
| **Faithfulness** | Is output grounded in sources? | Every wiki claim traceable to raw/ files |
| **Answer Relevancy** | Does output address the question? | Wiki pages stay on-topic for their entity/concept |
| **Context Precision** | Are retrieved sources useful? | Are the right raw/ files being used for compilation? |
| **Context Recall** | Were all necessary sources found? | Were all relevant raw/ files consulted? |

Uses "LLM-as-a-Judge" scoring where a separate evaluator model grades each dimension (0.0-1.0).

**How it maps to our cycle**:
- Adapt Faithfulness metric for Lint: for each wiki claim, can we trace it to a specific raw/ source? Score the page.
- Adapt Context Recall for coverage checking: for each raw/ source, are all key claims represented in wiki/?
- Run as automated quality gates during Compile, with threshold-based pass/fail
- Use a different model (e.g., GPT-4o or Gemini) as evaluator to avoid agreeableness bias

Sources:
- [RAGAS Testing Guide 2026](https://aitestingguide.com/what-is-ragas/)
- [RAGAS on DeepEval](https://www.deepeval.com/docs/metrics-ragas)

---

## 3. Incremental/Differential Compilation

### 3A. Content-Hash-Based Change Detection

The `rvk7895/llm-knowledge-bases` repo (already analyzed in tooling-research.md) pioneered **hash-based incremental compile**: store SHA-256 hashes of compiled-from sources in `_index.md`. On each compile, diff against stored hashes, only process new/changed/deleted files.

The **content-hash-cache-pattern** Claude Code skill (from Everything Claude Code) formalizes this:
- SHA-256 hash of file content (not path) as cache key
- Path-independent: moving a file doesn't invalidate the cache
- Auto-invalidating: content change -> new hash -> cache miss
- Service layer separation: hash computation separate from cache storage

**How it maps to our cycle**:
- Store `content_hash: sha256(raw_source_content)` in wiki page frontmatter
- On ingest: compute hash of new/changed raw/ file
- On compile: compare hash to stored hashes in wiki pages that reference this source
- If hash unchanged: skip. If changed: re-compile only affected pages
- Track in `wiki/_sources.md`: `raw/articles/foo.md -> sha256:abc123 -> [wiki/page1.md, wiki/page2.md]`

Sources:
- [rvk7895/llm-knowledge-bases](https://github.com/rvk7895/llm-knowledge-bases)
- [content-hash-cache-pattern skill](https://lobehub.com/skills/royaluniondesign-sys-claude-os-content-hash-cache-pattern)
- [markdown-vault-mcp hash-based change detection](https://github.com/pvliesdonk/markdown-vault-mcp/issues/6)

---

### 3B. Git-Diff-Aware Agent Processing

**lean-ctx** ([yvgude/lean-ctx](https://github.com/yvgude/lean-ctx)) — 327 stars. Hybrid Context Optimizer that reduces LLM token consumption by 89-99%. Key techniques applicable to our system:

- **Diff mode**: Only send changed lines to LLM, not full files. Myers diff algorithm sends only changed hunks.
- **Map mode**: File structure/signatures at ~5-15% of full size (dependencies, exports, API surface)
- **Cached reads**: First read costs full tokens; re-reads cost ~13 tokens regardless of file size (99% reduction)
- **Cross-file deduplication**: TF-IDF + cosine similarity detects shared imports/boilerplate

**GitHub Copilot's Memory System** ([github.blog](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot)):
- **Just-in-time verification**: Store memories with citations to specific code locations, validate in real-time before use (not expensive offline curation)
- **Self-healing**: When agents encounter outdated memories, they verify citations against current state. Contradictions trigger automatic replacement.
- **Tool-based memory creation**: Agents invoke memory storage as a callable tool during tasks (organic, not forced)

**GitNexus** ([rywalker.com/research/gitnexus](https://rywalker.com/research/gitnexus)):
- Indexes codebase into a knowledge graph (imports, calls, defines, implements, extends)
- `detect_changes` MCP tool maps git-diff lines to affected processes
- Limitation: No incremental indexing — full re-index on every change. This is the exact problem we need to avoid.

**How it maps to our cycle**:
- **Diff-based compilation**: When a raw/ source changes, compute the diff and send *only the diff* to the compile agent along with the existing wiki pages. Agent updates pages based on what changed, not the full source.
- **Copilot's just-in-time verification**: Instead of pre-validating all wiki pages, verify citations on access (during Query). Flag stale citations for the next Lint pass.
- **Self-healing pattern**: When a query reveals a stale wiki page, automatically queue it for re-compilation rather than returning stale results.

Sources:
- [lean-ctx](https://github.com/yvgude/lean-ctx)
- [GitHub Copilot Memory System](https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot)
- [GitNexus](https://rywalker.com/research/gitnexus)
- [Precision Dissection of Git Diffs for LLM Consumption](https://medium.com/@yehezkieldio/precision-dissection-of-git-diffs-for-llm-consumption-7ce5d2ca5d47)

---

### 3C. Incremental Compilation Algorithm

Combining the above patterns into a concrete algorithm:

```
INCREMENTAL_COMPILE(new_source):
  1. hash = sha256(new_source.content)
  2. IF hash in source_index AND source_index[hash].pages unchanged:
       RETURN "no changes"
  3. affected_pages = source_index.get_pages_referencing(new_source)
  4. diff = compute_diff(old_source, new_source)  # if update, not new
  5. FOR each page in affected_pages (PARALLEL):
       a. Read existing page
       b. Send (diff OR full_source, existing_page, index) to compile_agent
       c. Agent returns proposed_changes as structured diff
       d. Quality_gate(proposed_changes)  # supervisor review
       e. IF approved: apply changes, update page frontmatter (hash, updated date)
  6. Identify NEW pages needed (entities/concepts in source not yet in wiki)
  7. FOR each new_page needed:
       a. Create page from template
       b. Quality_gate(new_page)
  8. Update source_index, wiki/index.md, wiki/log.md
  9. Git commit with structured message
```

---

## 4. Self-Improving Knowledge Systems

### 4A. Microsoft ACE: Agentic Context Engineering

[Microsoft Research, ICLR 2026](https://www.microsoft.com/en-us/research/publication/agentic-context-engineering-evolving-contexts-for-self-improving-language-models/):

Treats contexts as "evolving playbooks that accumulate, refine, and organize strategies" through generation, reflection, and curation.

Solves two critical problems:
- **Brevity Bias**: Previous methods sacrifice domain-specific insights for concise summaries
- **Context Collapse**: Iterative rewriting gradually erodes detailed knowledge over time

ACE prevents deterioration through "structured, incremental updates that preserve detailed knowledge." Optimizes contexts using *natural execution feedback* (no labeled supervision).

Results: +10.6% on agent tasks, +8.6% on finance domain. Matches top production agents using smaller open-source models.

**How it maps to our cycle**:
- Query feedback as execution signal: when queries succeed (user finds answer useful), reinforce the wiki pages that contributed. When queries fail (user says answer is wrong/incomplete), flag those pages for revision.
- Incremental context updates: add new knowledge to wiki pages without rewriting (prevents context collapse / knowledge erosion)
- The wiki itself IS the evolving context that improves through use

---

### 4B. Self-Refine Pattern

From [agentwiki.org](https://agentwiki.org/self_refine): The same model generates output, critiques it, and refines it based on that feedback. No external training or RL needed.

**How it maps to our cycle**:
- After Compile writes a wiki page, a Self-Refine loop:
  1. Generate: Write the page
  2. Critique: "What claims in this page cannot be traced to a specific raw/ source? What's missing?"
  3. Refine: Update the page based on self-critique
- Bounded by iteration count (1-3 rounds) for cost control
- More effective when Critique uses a different model than Generate (per the multi-model findings)

---

### 4C. Query Feedback Loop Architecture

Synthesized from multiple sources:

```
QUERY_WITH_FEEDBACK(question):
  1. Search wiki/ for relevant pages (BM25 + wikilink traversal)
  2. Synthesize answer with inline citations to wiki pages AND raw/ sources
  3. Present answer with confidence score
  4. User rates: useful / wrong / incomplete
  5. IF useful AND novel insight:
       Suggest filing as new wiki page (with "Smart Filing Gate" — only if genuinely new)
  6. IF wrong:
       Flag cited wiki pages for priority re-lint
       Log the failure in wiki/log.md with the specific wrong claim
  7. IF incomplete:
       Log coverage gap; suggest raw/ sources to ingest
  8. Over time: build reliability map (pages frequently cited in successful queries = high trust)
```

**Compile Your Knowledge, Don't Search It** ([dev.to/rotiferdev](https://dev.to/rotiferdev/compile-your-knowledge-dont-search-it-what-llm-knowledge-bases-reveal-about-agent-memory-32pg)):
- "Every query is also a contribution" — using the system improves it
- Three evolutionary stages: human-directed -> semi-autonomous -> autonomous
- Quality pressure through fitness functions (accuracy, usefulness, consistency)

---

## 5. Obsidian + Claude Code Integration

### 5A. Obsidian Skills (Kepano)

[kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) — 19k+ stars. Five skills that teach AI agents to work with Obsidian:

| Skill | Purpose |
|-------|---------|
| **obsidian-markdown** | Wikilinks, embeds, callouts, YAML frontmatter, LaTeX, Mermaid |
| **obsidian-bases** | `.base` database-like views with YAML config, filters, formulas |
| **json-canvas** | `.canvas` visual diagrams (nodes + edges for knowledge graphs) |
| **obsidian-cli** | Commands against running Obsidian instance |
| **defuddle** | Web page -> clean Markdown (token-optimized ingestion) |

**Installation for Claude Code**: Copy repository to `/.claude` folder in vault root. Skills auto-load when Claude encounters relevant keywords.

**Key patterns taught**:
- `[[Note Name]]` for internal linking, `[[Note#Heading]]` for sections
- `![[Note]]` for transclusion (embed content from one page in another)
- `> [!type]` for callouts (13 built-in types)
- YAML frontmatter for metadata (tags, aliases, cssclasses)
- Canvas JSON for visual knowledge graph construction

**How it maps to our cycle**:
- We already have obsidian-skills installed (it's listed in the available skills). The `obsidian-markdown` and `obsidian-cli` skills are directly relevant.
- `defuddle` skill replaces `trafilatura` for lighter-weight web -> markdown conversion
- `obsidian-bases` could power the `wiki/index.md` as a dynamic database view
- `json-canvas` could generate visual knowledge maps as part of the Evolve operation
- **Critical**: Our wiki pages should use Obsidian-flavored markdown exclusively. Obsidian Skills ensures Claude generates correct syntax.

Sources:
- [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)
- [DeepWiki: obsidian-skills overview](https://deepwiki.com/kepano/obsidian-skills/1-overview)
- [Obsidian Skills Review 2026](https://vibecoding.app/blog/obsidian-skills-review)

---

### 5B. Obsidian MCP Servers (Deferred)

As noted in tooling-research.md, revisit at 50+ wiki pages:

| Server | Stars | Best For |
|--------|-------|----------|
| **@bitbonsai/mcpvault** | 1,002 | BM25 search, frontmatter-safe writes |
| **Epistates/turbovault** | 104 | Link graph analysis, vault health |
| **AdrianV101/obsidian-pkm-plugin** | 4 | 20 tools for knowledge management |

Claude Code's built-in tools cover 90% of needs. The differentiated value is **link graph analysis** (orphans, broken links, hubs, cycles) — useful for Lint at scale.

---

## 6. Claude Code Skills/Plugins for Knowledge Management

### 6A. Already Available Skills (Installed)

From our installed skills inventory, directly relevant:

| Skill | Relevance |
|-------|-----------|
| **obsidian:obsidian-markdown** | Wiki page creation with correct Obsidian syntax |
| **obsidian:obsidian-bases** | Database views for index management |
| **obsidian:json-canvas** | Visual knowledge graph generation |
| **obsidian:obsidian-cli** | Vault operations against running Obsidian |
| **obsidian:defuddle** | Web -> Markdown for raw/ ingestion |
| **everything-claude-code:content-hash-cache-pattern** | SHA-256 hash caching for incremental compile |
| **everything-claude-code:deep-research** | Multi-source research via firecrawl and exa |
| **everything-claude-code:continuous-learning** | Extract patterns from sessions, save as instincts |
| **everything-claude-code:continuous-learning-v2** | Instinct-based learning via hooks |
| **everything-claude-code:verification-loop** | Comprehensive verification system |
| **everything-claude-code:santa-method** | Multi-agent adversarial verification (convergence loop) |
| **llm-application-dev:langchain-agent** | LangGraph-based agent creation |
| **llm-application-dev:rag-implementation** | RAG patterns (for hybrid approach later) |
| **llm-application-dev:llm-evaluation** | Evaluation strategies (RAGAS integration) |
| **llm-application-dev:prompt-optimize** | CoT, few-shot, constitutional AI patterns |

### 6B. Most Valuable Skills to Actually Use

1. **obsidian:obsidian-markdown** — Invoke on every wiki page write to ensure correct Obsidian syntax
2. **content-hash-cache-pattern** — Foundation for incremental compilation
3. **santa-method** — Two independent reviewers for quality gate on Compile output
4. **verification-loop** — Automated verification for Lint operation
5. **continuous-learning-v2** — Extract patterns from ingest/compile sessions, improve over time

### 6C. External Plugins Worth Tracking

| Plugin | Stars | What It Does |
|--------|-------|-------------|
| **arscontexta** | 2,917 | Knowledge system generation from conversation |
| **remember-md** | 17 | Session knowledge extraction to auto-organized markdown |
| **mcdow-webworks/productivity-skills** | — | Note-taking second brain with conversational capture |

---

## 7. Agentic Patterns for Wiki-Like Structures

### 7A. CLAUDE.md / AGENTS.md as Schema Layer

The Karpathy pattern uses CLAUDE.md as the schema defining structure and workflows. This has become a cross-tool standard:

- **CLAUDE.md**: Claude Code specific — project instructions, conventions, workflow definitions
- **AGENTS.md**: Cross-tool standard (Linux Foundation's Agentic AI Foundation) — works with Codex CLI, Copilot, Cursor, Windsurf
- **.cursorrules**: Cursor-specific

**Key insight from the ecosystem**: The schema file IS the most important file. It determines the quality of every agent operation. Treating it as documentation is a mistake — it should be treated like code: versioned, tested, iterated.

Our CLAUDE.md already defines the four operations well. What to add:
- Per-operation agent definitions with specific model tiers
- Structured output schemas for each operation
- Quality gate thresholds
- Example good/bad wiki pages for few-shot context

Sources:
- [CLAUDE.md, AGENTS.md Guide](https://www.sotaaz.com/post/ai-coding-rules-guide-en)
- [AGENTS.md Complete Guide](https://vibecoding.app/blog/agents-md-guide)

---

### 7B. The Model Tiering Pattern

Consistent across nearly all successful implementations:

| Task | Model | Rationale |
|------|-------|-----------|
| Scanning (index reads, file diffs, link checks) | Haiku | Mechanical, low-reasoning |
| Extraction and page writing | Sonnet | Quality-cost balance |
| Orchestration, synthesis, quality gates | Opus | Highest reasoning needed |
| Fact-checking, citation verification | Haiku | Cost-effective at scale |

This pattern appears in: rvk7895, the multi-loop supervision system, the DSPy Teacher-Student pattern, and Claude Code sub-agent best practices.

**How it maps to our cycle**:
- Ingest: Sonnet (extraction) with Haiku (metadata/frontmatter parsing)
- Compile: Sonnet (page writing) with Opus (orchestration of which pages to update)
- Query: Opus (synthesis and reasoning)
- Lint: Haiku (mechanical checks) + Opus (contradiction detection, gap analysis)

---

### 7C. The Evolve Operation (5th Cycle Phase)

From rvk7895/llm-knowledge-bases: beyond Ingest/Compile/Query/Lint, add **Evolve**:
- Gap analysis — what topics lack coverage?
- Connection discovery — what concepts should be linked but aren't?
- Missing data — what raw sources would fill knowledge gaps?
- Interesting questions — what could be explored deeper?

This turns the wiki from passive repository to proactive research assistant. User picks from suggestions, LLM executes.

Combined with Ars Contexta's **Reweave** concept: when new knowledge arrives, propagate context *backward* through existing notes. Don't just add — restructure.

---

## Summary: Recommended Architecture

### Phase 1: Foundation (Now)

```
raw/ --> [Ingest Agent (Sonnet)] --> wiki/draft/
                                       |
wiki/draft/ --> [Compile Agent (Sonnet, orchestrated by Opus)]
                                       |
                    [Quality Gate (Actor-Critic, separate context)]
                                       |
                              wiki/ (approved pages)
                                       |
                    [Lint Agent (Haiku mechanical + Opus reasoning)]
                                       |
                              lint-report.md
```

Key patterns to adopt immediately:
1. **Content-hash incremental compile** — SHA-256 hashes in frontmatter
2. **Three index files** — `_index.md`, `_sources.md`, `_categories.md`
3. **Model tiering** — Haiku/Sonnet/Opus per task
4. **Structured lint output** — JSON findings with severity/category/confidence
5. **Hook-based enforcement** — Validate frontmatter schema on every wiki write

### Phase 2: Quality (At 50+ wiki pages)

6. **Multi-loop supervision** — Sequential quality loops for Lint
7. **Actor-Critic compile** — Separate context for reviewer
8. **Query feedback loop** — User ratings improve wiki reliability map
9. **Self-Refine on Compile** — Generate/Critique/Refine bounded loop

### Phase 3: Autonomy (At 200+ wiki pages)

10. **DSPy optimization** — Teacher-Student for cost-efficient compilation
11. **Evolve operation** — Proactive gap and connection discovery
12. **RAGAS evaluation** — Automated faithfulness/recall scoring
13. **Reweave** — Backward propagation of new knowledge through existing pages

---

## Key Repos and URLs

| Resource | URL | Relevance |
|----------|-----|-----------|
| Karpathy's LLM Wiki gist | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f | Original pattern |
| rvk7895/llm-knowledge-bases | https://github.com/rvk7895/llm-knowledge-bases | Reference implementation |
| kepano/obsidian-skills | https://github.com/kepano/obsidian-skills | Obsidian agent skills (19k stars) |
| agenticnotetaking/arscontexta | https://github.com/agenticnotetaking/arscontexta | Knowledge system generator (2.9k stars) |
| remember-md/remember | https://github.com/remember-md/remember | Session knowledge extraction |
| KazKozDev/dspy-optimization-patterns | https://github.com/KazKozDev/dspy-optimization-patterns | Teacher-Student optimization |
| yvgude/lean-ctx | https://github.com/yvgude/lean-ctx | Context optimization (327 stars) |
| Multi-loop supervision (LangGraph) | https://www.tha.la/editing/2026-01-08-multi-loop-supervision-system-langgraph | Quality gate architecture |
| Multi-model convergence (Zylos) | https://zylos.ai/research/2026-03-01-multi-model-ai-code-review-convergence | Actor-Critic, ensemble patterns |
| MS ACE paper (ICLR 2026) | https://www.microsoft.com/en-us/research/publication/agentic-context-engineering-evolving-contexts-for-self-improving-language-models/ | Self-improving contexts |
| Multi-agent patterns guide | https://www.paperclipped.de/en/blog/multi-agent-architecture-patterns-design/ | Supervisor vs Swarm vs Pipeline |
| GitHub Copilot memory | https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot | Just-in-time verification |
| Claude Code sub-agents | https://claudefa.st/blog/guide/agents/sub-agent-best-practices | Parallel/sequential patterns |
| Claude Code multi-agent | https://claudelab.net/en/articles/claude-code/claude-code-multi-agent-advanced | Worktree isolation |
| Compile don't search | https://dev.to/rotiferdev/compile-your-knowledge-dont-search-it-what-llm-knowledge-bases-reveal-about-agent-memory-32pg | Agent memory philosophy |
