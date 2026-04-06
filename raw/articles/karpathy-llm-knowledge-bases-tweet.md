---
url: https://x.com/karpathy/status/2039805659525644595
fetched: 2026-04-06
---

LLM Knowledge Bases

Something I'm finding very useful recently: using LLMs to build personal knowledge bases for various topics of research interest. In this way, a large fraction of my recent token throughput is going less into manipulating code, and more into manipulating knowledge (stored as markdown and images). The latest LLMs are quite good at it.

Data ingest: I index source documents (articles, papers, repos, datasets, images, etc.) into a raw/ directory, then I use an LLM to incrementally "compile" a wiki, which is just a collection of .md files in a directory structure. The wiki includes summaries of all the data in raw/, backlinks, and then it categorizes data into concepts, writes articles for them, and links them all.

IDE: I use Obsidian as the IDE "frontend" where I can view the raw data, the compiled wiki, and the derived visualizations. Important to note that the LLM writes and maintains all of the data of the wiki, I rarely touch it directly.

Q&A: Once your wiki is big enough (e.g. ~100 articles and ~400K words), you can ask your LLM agent all kinds of complex questions against the wiki, and it will go off, research the answers, etc. I thought I had to reach for fancy RAG, but the LLM has been pretty good about auto-maintaining index files and brief summaries.

Output: Instead of getting answers in text/terminal, I like to have it render markdown files, slide shows (Marp format), or matplotlib images, all viewable in Obsidian. Often, I end up "filing" the outputs back into the wiki to enhance it for further queries.

Linting: LLM "health checks" over the wiki to find inconsistent data, impute missing data, find interesting connections for new article candidates, to incrementally clean up the wiki and enhance data integrity.

Extra tools: Additional tools to process the data, e.g. a small search engine over the wiki, usable directly or handed off to an LLM via CLI as a tool for larger queries.

TLDR: raw data from sources is collected, compiled by an LLM into a .md wiki, operated on by various CLIs by the LLM to do Q&A and incrementally enhance the wiki, all viewable in Obsidian.