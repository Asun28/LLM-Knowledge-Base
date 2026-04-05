# Python Library Survey for LLM Knowledge Base

*Researched 2026-04-06. Comprehensive survey of Python libraries across 10 categories relevant to an LLM-maintained knowledge wiki.*

---

## 1. Markdown Link Analysis & Wikilink Parsing

### obsidiantools (RECOMMENDED)
- **Package:** `pip install obsidiantools`
- **GitHub:** [mfarragher/obsidiantools](https://github.com/mfarragher/obsidiantools) -- ~535 stars
- **What it does:** Python package for analyzing Obsidian.md vaults. Parses wikilinks (including header links and aliases), builds a NetworkX graph of the vault, extracts backlinks, tags (including nested), and provides vault metadata as Pandas DataFrames. Can detect orphan notes, find isolated clusters, and extract source/readable text from notes.
- **Project fit:** Directly supports the Lint operation -- find orphan pages, broken wikilinks, missing backlinks, and build link graphs. The `vault.graph` (NetworkX) integrates with the already-installed `networkx` and `pyvis` for visualization. The `vault.get_note_metadata()` DataFrame is perfect for health dashboards.
- **Duplicates:** Overlaps with `networkx` (already installed) but adds the Obsidian-specific parsing layer on top. Complementary, not redundant.

### obsidianmd-parser
- **Package:** `pip install obsidianmd-parser`
- **Source:** [Codeberg: paddyd/obsidianmd-parser](https://codeberg.org/paddyd/obsidianmd-parser)
- **What it does:** Parses Obsidian markdown vaults with support for wikilinks, aliases, tags, task lists, callouts, and Dataview queries. Provides `note.get_backlinks(vault)` and `note.get_forward_links(vault)` for relationship tracking. Can find broken links, hub notes, and orphaned notes. Latest version 0.4.0 released Jan 2026.
- **Project fit:** More recently updated than obsidiantools. The Dataview query parsing and note object model are useful for programmatic wiki operations. Good alternative if obsidiantools proves insufficient.
- **Duplicates:** Directly competes with obsidiantools. Choose one.

### Python-Markdown wikilinks extension (ALREADY AVAILABLE)
- **Package:** Built into `pip install markdown` (already a dependency of many installed packages)
- **Docs:** [python-markdown.github.io/extensions/wikilinks](https://python-markdown.github.io/extensions/wikilinks/)
- **What it does:** Built-in extension that converts `[[bracketed]]` words to HTML links. Lightweight, no extra install needed.
- **Project fit:** Useful for rendering wiki pages to HTML, but does NOT do link graph analysis. Complementary to obsidiantools.

### markdown-it-py
- **Package:** `pip install markdown-it-py` (likely already installed as dependency)
- **GitHub:** [executablebooks/markdown-it-py](https://github.com/executablebooks/markdown-it-py)
- **What it does:** Fast markdown parser with plugin architecture, AST support, and token manipulation. 100% CommonMark support. Can be extended with wikilink plugins.
- **Project fit:** Lower-level than obsidiantools. Only useful if you need custom markdown parsing beyond what obsidiantools provides. The AST/token manipulation could help with surgical wiki page edits.

---

## 2. Content Deduplication

### semhash (RECOMMENDED)
- **Package:** `pip install semhash`
- **GitHub:** [MinishLab/semhash](https://github.com/MinishLab/semhash) -- ~700+ stars
- **What it does:** Fast semantic deduplication using Model2Vec embeddings + ANN-based similarity search. Unlike MinHash/SimHash (character/word n-gram based), semhash operates on semantic similarity. Deduplicates 130K samples (SQuAD-2.0) in 7 seconds. Supports single-dataset dedup and cross-dataset dedup. MIT licensed.
- **Project fit:** Ideal for detecting semantically similar wiki pages that may need merging. The cross-dataset mode could compare `raw/` sources against `wiki/` pages to find redundant content. Lightweight (depends on Model2Vec + Vicinity).
- **Duplicates:** Does not overlap with anything installed. Complementary to deepdiff (which does structural diff, not semantic similarity).

### datasketch
- **Package:** `pip install datasketch`
- **GitHub:** [ekzhu/datasketch](https://github.com/ekzhu/datasketch) -- ~2.6K stars
- **What it does:** Probabilistic data structures including MinHash LSH for near-duplicate detection via Jaccard similarity. Also includes HyperLogLog, LSH Forest, LSH Ensemble, and HNSW. Supports Redis/Cassandra storage backends. Mature library, actively maintained.
- **Project fit:** Better for exact/near-exact text deduplication (copy-paste detection between wiki pages). Faster than semhash for character-level similarity but misses paraphrased duplicates. Good for the Lint operation to flag pages with overlapping verbatim content.
- **Duplicates:** Complementary to semhash (different dedup strategies).

### text-dedup
- **Package:** `pip install text-dedup`
- **GitHub:** [ChenghaoMou/text-dedup](https://github.com/ChenghaoMou/text-dedup) -- ~742 stars
- **What it does:** All-in-one text deduplication toolkit with MinHash, SimHash, Bloom Filter, Suffix Array, and RETSim/UniSim embedding-based methods. Config-driven via TOML files. Designed for large-scale dataset cleaning.
- **Project fit:** Overkill for a personal wiki (~100-1000 pages). Better suited for cleaning large training datasets. semhash or datasketch are more appropriate at this scale.
- **Duplicates:** Superset of datasketch's MinHash functionality.

---

## 3. Semantic Chunking

### chonkie (RECOMMENDED over semchunk for features)
- **Package:** `pip install chonkie`
- **GitHub:** [chonkie-inc/chonkie](https://github.com/chonkie-inc/chonkie) -- actively maintained, latest release Mar 2026
- **What it does:** Lightweight ingestion library with multiple chunking strategies: TokenChunker, SentenceChunker, RecursiveChunker, SemanticChunker, LateChunker, and NeuralChunker. 32+ integrations with tokenizers, embedding providers, and vector DBs. The SemanticChunker uses embeddings to find natural topic boundaries. Requires Python >= 3.10.
- **Project fit:** Useful during Ingest when processing large raw documents. The SemanticChunker would produce better summaries by splitting documents at topic boundaries rather than arbitrary character counts. The RecursiveChunker respects markdown structure (headings, paragraphs).
- **Duplicates:** Partially overlaps with semchunk (already installed). Chonkie offers more chunking strategies and integrations but semchunk has higher RAG correctness scores (15% better in benchmarks). Consider using both: semchunk for quality-critical chunking, chonkie for its broader strategy menu.

### semchunk (ALREADY INSTALLED)
- **Package:** `pip install semchunk`
- **GitHub:** [isaacus-dev/semchunk](https://github.com/isaacus-dev/semchunk)
- **What it does:** Fast, lightweight semantic chunking with AI-powered chunking mode. Works with any tokenizer. Used by Docling and Microsoft Intelligence Toolkit. Higher RAG correctness than competitors in benchmarks.
- **Project fit:** Already installed. The AI chunking mode (using Kanon 2 Enricher) is worth exploring for highest-quality chunks.

---

## 4. Citation & Reference Management

### papis
- **Package:** `pip install papis`
- **GitHub:** [papis/papis](https://github.com/papis/papis) -- ~1.3K stars
- **What it does:** CLI document and bibliography manager with Git-like interface. Stores bibliographic data in human-readable YAML files. Supports import/export to BibTeX and other formats. Extensible via plugins. Has Vim/Emacs integration.
- **Project fit:** Could manage the `raw/` directory as a bibliography -- each source gets a `.yaml` metadata file alongside the markdown. Supports searching, tagging, and linking documents. However, the wiki's YAML frontmatter already tracks sources via the `source:` field, so papis would add a parallel system.
- **Duplicates:** The project's YAML frontmatter convention already covers basic provenance tracking. Papis would be redundant unless you need BibTeX export or advanced bibliography features.

### python-frontmatter (ALREADY INSTALLED)
- **Project fit:** Already installed and designated for parsing/validating wiki page metadata. Combined with a custom provenance tracker (a simple Python dict mapping claims to raw source files + line numbers), this covers citation needs without additional libraries.

**Verdict:** Custom provenance tracking using python-frontmatter + a lightweight JSON/YAML mapping file is more aligned with the project than a full bibliography manager. Skip papis unless BibTeX interop becomes needed.

---

## 5. Text Quality Scoring

### textstat (RECOMMENDED -- lightweight)
- **Package:** `pip install textstat`
- **GitHub:** [textstat/textstat](https://github.com/textstat/textstat) -- ~2.2K stars
- **What it does:** Calculates readability statistics: Flesch-Kincaid Grade Level, Gunning Fog Index, SMOG, ARI, Dale-Chall, Coleman-Liau, and more. Pure Python, minimal dependencies. Supports multiple languages.
- **Project fit:** Quick readability scoring during Lint to flag wiki pages that are too complex or too simple. A one-liner per page: `textstat.flesch_reading_ease(text)`. Useful for ensuring wiki pages maintain consistent quality.
- **Duplicates:** No overlap with installed packages.

### TextDescriptives
- **Package:** `pip install textdescriptives`
- **GitHub:** [HLasse/TextDescriptives](https://github.com/HLasse/TextDescriptives) -- ~341 stars
- **What it does:** spaCy pipeline component that calculates readability, coherence (semantic similarity between sentences), dependency distance, POS proportions, information theory metrics, and quality filtering heuristics. Version 2.0 adds coherence component.
- **Project fit:** The coherence metric is particularly valuable -- it measures how well sentences in a wiki page flow together semantically. The quality filtering can flag low-quality pages (high stop-word ratio, short sentences, etc.). However, requires spaCy as a dependency, which adds ~500MB.
- **Duplicates:** Superset of textstat's readability features. The coherence and quality metrics go beyond textstat. But the spaCy dependency is heavy.

**Verdict:** Install textstat for lightweight readability checks. Add TextDescriptives only if coherence scoring becomes important enough to justify the spaCy dependency (which was deliberately skipped per `tooling-research.md`).

---

## 6. Obsidian Vault Tools

### obsidiantools (see Section 1 above -- RECOMMENDED)

Primary tool. Covers vault analysis, link graphs, metadata extraction.

### obsidian-html
- **Package:** `pip install obsidianhtml`
- **GitHub:** [obsidian-html/obsidian-html](https://github.com/obsidian-html/obsidian-html) -- ~500+ stars
- **What it does:** Converts Obsidian notes to standard markdown and optionally builds an HTML site. Handles wikilink conversion, image embedding, and cross-references.
- **Project fit:** Useful if you ever want to publish the wiki as a static site. Not needed for core operations (Ingest/Compile/Query/Lint).

---

## 7. Knowledge Graph Construction

### kg-gen (RECOMMENDED)
- **Package:** `pip install kg-gen`
- **GitHub:** [stair-lab/kg-gen](https://github.com/stair-lab/kg-gen) -- ~700+ stars (NeurIPS 2025 paper)
- **What it does:** Extracts knowledge graphs from plain text using LLMs. Produces entity-relation triplets. Clusters related entities to reduce sparsity. Supports API-based and local models via LiteLLM (OpenAI, Anthropic, Ollama, etc.). Uses DSPy for structured output.
- **Project fit:** Directly relevant for building a knowledge graph from wiki pages. Run kg-gen on compiled wiki pages to extract entities and relationships, then visualize with networkx/pyvis (already installed). The entity clustering is valuable for normalizing entity names across pages. Uses litellm (already installed) and dspy (already installed).
- **Duplicates:** Uses DSPy and LiteLLM which are already installed. Complements networkx/pyvis (graph storage/viz) rather than replacing them.

### Microsoft GraphRAG
- **Package:** `pip install graphrag`
- **GitHub:** [microsoft/graphrag](https://github.com/microsoft/graphrag) -- ~22K+ stars
- **What it does:** Full pipeline for extracting knowledge graphs from text using LLMs, then using the graph for RAG. Builds entity/relationship graphs, creates community summaries, and supports global/local queries.
- **Project fit:** Philosophically aligned but architecturally redundant. The project already compiles knowledge into wiki pages rather than using RAG. GraphRAG's community summarization is interesting but the full pipeline is heavy. kg-gen is lighter and more focused.
- **Duplicates:** Would add a parallel knowledge extraction system alongside the wiki compile cycle.

### kglab
- **Package:** `pip install kglab`
- **GitHub:** [DerwenAI/kglab](https://github.com/DerwenAI/kglab)
- **What it does:** Abstraction layer for building knowledge graphs atop Pandas, NetworkX, RDFLib, PyVis, and others. Supports RDF, SHACL validation, and graph algorithms.
- **Project fit:** Useful if you want formal RDF/semantic web representations. Overkill for a markdown wiki. The already-installed networkx + pyvis covers graph needs without the RDF overhead.

---

## 8. Contradiction Detection

### sentence-transformers CrossEncoder (RECOMMENDED)
- **Package:** `pip install sentence-transformers` (may already be partially available via other deps)
- **GitHub:** [UKPLab/sentence-transformers](https://github.com/UKPLab/sentence-transformers) -- ~16K+ stars
- **What it does:** Provides CrossEncoder models trained on NLI (Natural Language Inference) datasets. Given two sentences, classifies as entailment/contradiction/neutral. Pre-trained models like `cross-encoder/nli-deberta-v3-base` work out of the box.
- **Project fit:** Core tool for the Lint operation's contradiction detection. Extract claim pairs from wiki pages, run through the CrossEncoder, flag contradictions. Example: `CrossEncoder("cross-encoder/nli-deberta-v3-base").predict([("Page A says X", "Page B says Y")])` returns contradiction/entailment/neutral scores.
- **Duplicates:** Does not overlap with installed packages. The `transformers` library (installed via docling) provides the model backend, but sentence-transformers adds the high-level CrossEncoder API.

**Alternative approach:** Use the Anthropic API (already installed) to detect contradictions via prompting. This avoids installing a local model but costs API tokens. For batch Lint runs over many claim pairs, a local CrossEncoder is more cost-effective.

---

## 9. Incremental Processing

### watchdog (RECOMMENDED)
- **Package:** `pip install watchdog`
- **GitHub:** [gorakhargosh/watchdog](https://github.com/gorakhargosh/watchdog) -- ~7.2K stars
- **What it does:** Cross-platform filesystem event monitoring. Detects file creation, modification, deletion, and moves. Supports observers with custom event handlers. Latest version 6.0.0 (Nov 2024). Context manager support.
- **Project fit:** Monitor `raw/` directory for new/changed files and automatically trigger Ingest. Can watch for wiki page changes too. More responsive than polling-based approaches. The `content-hash-cache-pattern` (SHA-256 hash tracking) from `tooling-research.md` works well alongside watchdog: watchdog detects changes instantly, hashes confirm what actually changed.
- **Duplicates:** No overlap with installed packages. Complementary to the hash-based incremental compile pattern already planned.

### hashlib (BUILT-IN)
- Python's built-in `hashlib` module handles SHA-256 hashing for content-based change detection. No install needed. Already planned for use in the incremental compile system.

---

## 10. CLI Frameworks

### typer (ALREADY INSTALLED)
- Already installed and appropriate for building the `ingest`/`compile`/`query`/`lint` CLI commands. No additional CLI framework needed.

### cyclopts (ALREADY INSTALLED)
- Also installed per requirements.txt. Modern alternative to typer with config-based approach.

---

## 11. Lightweight Local Vector Search

### sqlite-vec (RECOMMENDED)
- **Package:** `pip install sqlite-vec`
- **GitHub:** [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec) -- ~5K+ stars
- **What it does:** Vector search as a SQLite extension. Zero external dependencies (pure C). Stores vectors inside the SQLite database itself. Supports KNN search via `MATCH` constraint on vec0 virtual tables. Works everywhere SQLite works (macOS, Linux, Windows, WASM).
- **Project fit:** The lightest possible vector search -- no server, no separate database, just SQLite. Perfect for optional semantic search over wiki pages without violating the "compile, not retrieve" philosophy. Could power the Query operation when exact wiki page matching falls short. Pairs well with Model2Vec for fast embedding generation.
- **Duplicates:** Does not overlap with installed packages. Much lighter than chromadb or lancedb.

### Model2Vec (RECOMMENDED -- pairs with sqlite-vec)
- **Package:** `pip install model2vec`
- **GitHub:** [MinishLab/model2vec](https://github.com/MinishLab/model2vec) -- ~2K+ stars
- **What it does:** Turns any sentence transformer into a static embedding model. 500x faster than the original model on CPU. Best model is ~30MB, smallest is ~8MB. Only dependency is numpy. Creates embeddings by forward-passing vocabulary through a sentence transformer.
- **Project fit:** Generate embeddings for wiki pages and raw sources with near-zero latency. Combined with sqlite-vec, creates a fully local, lightweight semantic search layer. No GPU needed, no API calls. The ~8MB model size is negligible.
- **Duplicates:** Does not overlap with installed packages. Much lighter than sentence-transformers for pure embedding (not NLI).

### LanceDB
- **Package:** `pip install lancedb`
- **GitHub:** [lancedb/lancedb](https://github.com/lancedb/lancedb) -- ~5.7K stars
- **What it does:** Serverless vector database built on Lance columnar format (Rust core). Supports vector search, full-text search, and SQL. Native Pandas/Polars/DuckDB integration.
- **Project fit:** More feature-rich than sqlite-vec but heavier. The Pandas integration is nice for analytics. Better choice if you need full-text search + vector search combined. But for this project, sqlite-vec's simplicity is preferable.
- **Duplicates:** Competes with sqlite-vec. Choose one.

### ChromaDB
- **Package:** `pip install chromadb`
- **GitHub:** [chroma-core/chroma](https://github.com/chroma-core/chroma) -- ~18K+ stars
- **What it does:** Open-source embedding database with vector search, full-text search, metadata filtering. Zero-config local setup. SQLite backend for persistence.
- **Project fit:** Popular and well-documented but significantly heavier than sqlite-vec. Includes its own embedding functions, which adds dependency weight. Degraded performance beyond a few million vectors (not a concern at wiki scale, but signals architectural overhead).
- **Duplicates:** Philosophically at odds with the "compile, not retrieve" approach. Skip unless RAG becomes necessary.

---

## 12. PKM + LLM Ecosystem (2025-2026)

### awesome-llm-knowledge-bases
- **GitHub:** [SingggggYee/awesome-llm-knowledge-bases](https://github.com/SingggggYee/awesome-llm-knowledge-bases)
- **What it is:** Curated list of tools for building LLM-powered personal knowledge bases, organized around Karpathy's workflow. Categories include document conversion, wiki compilation, knowledge organization, and quality control.
- **Project fit:** Reference resource. Check periodically for new tools in the ecosystem.

### wiki-compiler (Claude Code plugin)
- **GitHub:** [ussumant/llm-wiki-compiler](https://github.com/ussumant/llm-wiki-compiler)
- **What it does:** Claude Code plugin that compiles markdown knowledge files into a topic-based wiki. Uses Obsidian-style wikilinks. Incremental recompilation (only recompiles topics whose sources changed). Claims ~90% context cost reduction.
- **Project fit:** Reference implementation of the Compile operation. Study for patterns, but this project should build its own compiler for full control. The incremental recompile logic is worth borrowing.

### QMD (Query Markdown)
- **GitHub:** [tobi/qmd](https://github.com/tobi/qmd) and [ehc-io/qmd](https://github.com/ehc-io/qmd)
- **Install:** `npm install -g @tobilu/qmd` (Node.js, not Python)
- **What it does:** CLI search engine for markdown files. Hybrid BM25 + vector embeddings + LLM re-ranking. SQLite-based index. Available as MCP server for Claude Code/Cursor.
- **Project fit:** Directly recommended by the Karpathy ecosystem for searching markdown knowledge bases. The MCP server mode is particularly interesting -- could power the Query operation via Claude Code. However, it's Node.js-based, not Python. Consider as an external tool rather than a library dependency.

---

## Summary: Recommended Installs

### Tier 1 -- High Value, Install Now

| Package | Category | Install Command | Why |
|---|---|---|---|
| `obsidiantools` | Vault analysis / Link graphs | `pip install obsidiantools` | Wikilink parsing, orphan detection, NetworkX graph, Pandas metadata. Core Lint tool. |
| `textstat` | Text quality | `pip install textstat` | Lightweight readability scoring for wiki pages. One-liner per page. |
| `watchdog` | Incremental processing | `pip install watchdog` | Filesystem monitoring for `raw/` directory. Auto-trigger Ingest on file changes. |
| `sqlite-vec` | Vector search | `pip install sqlite-vec` | Lightest possible local vector search. SQLite-native. Zero dependencies. |
| `model2vec` | Embeddings | `pip install model2vec` | 500x faster CPU embeddings, ~8-30MB models. Pairs with sqlite-vec. |

### Tier 2 -- Strong Value, Install When Needed

| Package | Category | Install Command | Why |
|---|---|---|---|
| `semhash` | Semantic dedup | `pip install semhash` | Detect semantically similar wiki pages. Fast (7s for 130K samples). |
| `kg-gen` | Knowledge graph | `pip install kg-gen` | LLM-powered entity/relation extraction. Uses already-installed DSPy + LiteLLM. |
| `datasketch` | Near-duplicate detection | `pip install datasketch` | MinHash LSH for character-level dedup. Complements semhash. |
| `sentence-transformers` | Contradiction detection | `pip install sentence-transformers` | CrossEncoder NLI models for Lint contradiction checks. |
| `chonkie` | Semantic chunking | `pip install chonkie` | Multiple chunking strategies beyond semchunk. SemanticChunker for topic-aware splits. |

### Tier 3 -- Niche / Reference Only

| Package | Category | Notes |
|---|---|---|
| `obsidianmd-parser` | Vault parsing | Alternative to obsidiantools if it proves insufficient. More recently updated. |
| `text-dedup` | Dedup toolkit | Overkill for wiki scale. Better for large dataset cleaning. |
| `TextDescriptives` | Quality metrics | Adds coherence scoring but requires heavy spaCy dependency. |
| `graphrag` | Knowledge graph RAG | Architecturally redundant with compile-not-retrieve philosophy. |
| `papis` | Bibliography | YAML frontmatter already handles provenance. Only needed for BibTeX export. |
| `lancedb` | Vector DB | Heavier alternative to sqlite-vec. Use if full SQL+vector+FTS needed. |
| `chromadb` | Vector DB | Popular but heavy. Against compile-not-retrieve philosophy. |

---

## Key Architectural Decisions

1. **obsidiantools over custom wikilink parsing** -- The library handles all Obsidian markdown edge cases (aliases, header links, nested tags) and provides NetworkX integration for free.

2. **sqlite-vec + model2vec over chromadb/lancedb** -- Minimal footprint, zero-server, SQLite-native. Aligns with the local-first, compile-not-retrieve philosophy. Use for optional semantic search during Query, not as the primary retrieval layer.

3. **semhash over datasketch for wiki dedup** -- Semantic similarity catches paraphrased duplicates that character-level MinHash misses. At wiki scale (~100-1000 pages), the performance difference is negligible.

4. **sentence-transformers CrossEncoder over Claude API for contradiction detection** -- Local model avoids API costs during batch Lint runs. A single CrossEncoder model handles thousands of claim pairs in seconds.

5. **kg-gen over GraphRAG for knowledge graph** -- Lighter, focused on extraction rather than full RAG pipeline. Uses already-installed DSPy and LiteLLM backends.

6. **textstat over TextDescriptives** -- Avoids the ~500MB spaCy dependency. Readability scoring is sufficient for initial Lint quality checks. Upgrade to TextDescriptives only if coherence metrics become essential.

7. **watchdog for filesystem monitoring** -- More responsive than polling. Triggers Ingest automatically when files land in `raw/`.
