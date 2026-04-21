# 🌪️ LLM Wiki Flywheel

**Language / 语言：** [English](README.md) · **简体中文**

![Python](https://img.shields.io/badge/python-3.12%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-2585-brightgreen) ![MCP Tools](https://img.shields.io/badge/MCP%20tools-26-blueviolet) ![Version](https://img.shields.io/badge/version-v0.10.0-orange)

**编译知识，而非检索碎片。**
丢入原始资料，剩下的交给 Claude——自动提取实体、构建维基页面、注入双向链接、追踪可信度、标记矛盾点。无需向量数据库，无需文本分块。生成的是完全由你掌控的纯 Markdown 文件，可直接在 Obsidian 中浏览。

灵感源自 [Karpathy 的 LLM 知识库构想](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)，并实现了**全自动化**。原生支持 Claude Code，内置 26 个 MCP 工具——无需配置 API Key 即可运行。

---

## 🎯 为什么用户选择它而非传统 RAG？

🧠 **重结构，轻分块**：基于实体、概念与维基链接构建真实知识图谱，告别不透明的向量检索。
⚡ **默认增量更新**：基于 SHA-256 变更检测，仅重新处理新增或修改的资料。
🔗 **回溯式链接**：摄入新主题时，已有页面会自动补充 `[[维基链接]]`。
🧪 **自我修复**：贝叶斯可信度评分、矛盾检测、内容过期标记、死链检查。
🦉 **Obsidian 原生兼容**：将 `wiki/` 目录作为 Vault 打开，免费享受图谱视图、反向链接与悬浮预览。
🔌 **MCP 优先**：在 Claude Code 中内置 26 个工具。用自然对话管理知识库："摄入这篇"、"关于 X 我们知道什么？"
📤 **一键发布**：单条命令即可生成 `/llms.txt`、`/llms-full.txt`、`/graph.jsonld`、站点地图及关联页面——完整支持 Karpathy Tier-1 机器可读标准。

### 为什么不用 RAG？
RAG 检索的是文本块，而本系统理解的是知识结构。

| 维度 | 传统 RAG | 本项目 |
|---|---|---|
| 存储方式 | 不可读的向量嵌入 (Embeddings) | 可在 Obsidian 中直接浏览的 Markdown 页面 |
| 知识形态 | 无关联的文本碎片 (Chunks) | 由实体、概念和维基链接构成的知识图谱 |
| 检索质量 | 依赖 Top-K 相关性，结果不稳定 | BM25 + PageRank 排序，结合可信度评分 |
| 维护成本 | 资料变更需重新向量化 | 增量编译——仅处理变更部分 |
| 矛盾处理 | 静默返回冲突片段 | Lint 工具自动跨源检测矛盾 |
| 知识盲区 | 无法感知缺失内容 | Evolve 工具自动分析覆盖盲区并建议新建页面 |

---

## 🆚 与 Karpathy 原始构想有何不同？

Karpathy 描述了一种手动让 LLM 编译页面的模式。而本项目是**全自动系统**：将文件丢入 `raw/`，运行 `kb compile`，整个流水线（提取、建页、交叉链接、索引更新、质量检查）无需人工干预。配合 Claude Code，甚至连 CLI 都不需要，直接说"摄入这篇"即可。

```
                    ┌──────────────────────────────────────┐
                    │           The Full Cycle              │
                    │                                      │
    raw/            │   Ingest ──→ Compile ──→ Query       │        Obsidian
  articles/   ────→ │     │                      │         │ ────→  Graph View
  papers/           │     │    Evolve ←── Lint   │         │        Browse
  videos/           │     │      │          │    │         │        Search
  repos/            │     └──────┘←─────────┘←───┘         │
                    │        continuous feedback loop       │
                    └──────────────────────────────────────┘
```

| Karpathy 模式（手动） | 本项目（全自动） |
|---|---|
| 手动提示 LLM 编写页面 | 一条命令 → 提取、建页、链接、索引全自动完成 |
| 扁平的页面列表 | 知识图谱（支持 PageRank 中心性分析与 Mermaid 导出） |
| 无变更检测 | 增量编译（SHA-256 哈希检测，仅处理新增/变更内容） |
| 无交叉链接 | 回溯式维基链接注入（新主题自动链接至历史页面） |
| 无质量检查 | 自我修复（Lint 捕获问题、可信度评分标记低质页面、矛盾检测） |
| 无盲区感知 | Evolve 自动识别覆盖缺口与连接机会 |
| 依赖外部 LLM API 调用 | MCP 原生集成（Claude Code 内置 26 个工具，无需 API Key） |
| 纯文本输出 | Obsidian 原生支持（打开 `wiki/` 即可免费使用可视化知识图谱） |

---

## ⚡ 30 秒快速演示

```bash
# 1. 抓取一篇文章
trafilatura -u https://example.com/ai-article > raw/articles/ai-article.md

# 2. 摄入资料 —— Claude 自动提取实体、概念与核心观点
kb ingest raw/articles/ai-article.md

# 3. 观察知识库自动生长
#    wiki/summaries/ai-article.md        ← 来源摘要
#    wiki/entities/openai.md             ← 自动创建的实体页
#    wiki/concepts/attention.md          ← 自动创建的概念页
#    + 已有页面中提及这些主题的地方会自动注入维基链接

# 4. 跨所有资料进行查询
kb query "注意力机制与 Transformer 有何关联？"
#    → 生成综合解答，并附带 [source: page_id] 引用溯源

# 5. 检查知识库健康度
kb lint     # 检测死链、孤立页面、过期内容、矛盾点
kb evolve   # 分析缺失哪些主题？哪些内容应该建立关联？
```

或者直接在 **Claude Code** 中对话：
- `"将这篇文章摄入我的知识库"`
- `"我的知识库中关于 Transformer 有哪些内容？"`
- `"展示知识图谱"`

---

## 🏗️ 系统架构

![LLM Knowledge Base Architecture](docs/architecture/architecture-diagram.png)

[查看详细架构图](docs/architecture/architecture-diagram-detailed.html)

人类负责筛选资料，其余全自动化——提取、编译、交叉链接、查询、健康检查与缺口分析均无需人工干预。

| 层级 | 路径 | 负责人 | 用途 |
|---|---|---|---|
| Raw（原始层） | `raw/` | 人类 | 不可变的原始资料（文章、论文、视频、代码库等） |
| Wiki（维基层） | `wiki/` | LLM | 自动生成并维护的 Markdown 页面（含 YAML 前置元数据） |
| Research（研究层） | `research/` | 人类 | 分析笔记、项目构思、元研究 |

---

## 🚀 快速开始

```bash
git clone https://github.com/Asun28/llm-wiki-flywheel.git
cd llm-wiki-flywheel

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix/macOS

pip install -r requirements.txt && pip install -e .
kb --version
```

**🔑 API Key 配置**：复制 `.env.example` 为 `.env`。`ANTHROPIC_API_KEY` 在 Claude Code/MCP 模式下为可选；仅在使用 CLI 直接调用 `compile/query`、MCP 设置 `use_api=True` 或 `kb_query --format=...` 输出适配器时才必需。

**🦉 Obsidian 集成**：将 `wiki/` 目录作为 Vault 打开。按 `Ctrl+G` 查看知识图谱。详见 [Obsidian 完整指南](docs/guides/quickstart-obsidian.md)（[HTML 版](docs/guides/quickstart-obsidian.html)）。

**💡 新手建议**：先浏览 `demo/` 文件夹。这是一个基于 Karpathy 推文与 Gist 编译的小型示例知识库，完整展示了目录结构与编译输出（摘要、实体、概念、对比分析、跨源综合）。在添加你自己的资料前，可以直观了解流水线的实际效果。

---

## 🛠️ 五大核心操作

| 操作 | 命令 | 功能说明 |
|---|---|---|
| 摄入 (Ingest) | `kb ingest <file>` | 提取实体/概念/核心观点 → 创建维基页 → 注入维基链接 → 更新索引 |
| 编译 (Compile) | `kb compile` | 批量摄入所有新增/变更资料（SHA-256 哈希检测，崩溃安全） |
| 查询 (Query) | `kb query "..."` | BM25 + PageRank 检索 → 生成带内联引用的综合解答 |
| 检查 (Lint) | `kb lint` | 检测死链、孤立页、过期内容、残页、元数据、来源覆盖、链接环、低可信度页面 |
| 演进 (Evolve) | `kb evolve` | 分析覆盖盲区、连接机会、缺失页面类型、断开图谱组件 |

---

## ✨ 核心特性

### 📥 摄入流水线 (Ingest Pipeline)
- 支持 10 种资料类型：文章、论文、视频、代码库、播客、书籍、数据集、对话、对比分析、综合报告
- 基于哈希的去重机制——相同内容不会重复摄入
- 回溯式维基链接注入——摄入新主题时，提及该主题的历史页面自动补全链接
- 级联追踪——返回受新摄入内容影响、可能需要复查的已有页面
- 短内容分级处理——小型资料（<1000 字符）延迟创建实体，避免生成"残页"(stubs)
- 对话捕获——`kb_capture` MCP 工具可将聊天/笔记/会话记录原子化为结构化知识项（决策、发现、修正、踩坑记录），内置密钥扫描安全拦截与进程级限流

### 🔍 检索与查询 (Search & Query)
- BM25 排序（支持标题加权与文档长度归一化）
- PageRank 融合——连接度高的页面排名更靠前
- 上下文智能截断至 80K 字符，精准筛选相关页面
- 内联引用溯源：`[source: concepts/attention]` 确保每个观点有据可查

### 🛡️ 质量保障系统 (Quality System)
- 贝叶斯可信度评分——基于查询反馈动态调整页面可信度。"错误"惩罚权重是"不完整"的 2 倍
- 语义 Lint 检查——深度保真校验（页面对比原始来源）与跨页面矛盾检测
- Actor-Critic 审查机制——结构化 6 项检查清单，完整审计追踪
- 质量趋势看板——按周统计 pass/fail/warning，可视化质量演进轨迹

### 🕸️ 知识图谱 (Knowledge Graph)
- 基于 NetworkX 从维基链接构建图谱
- 支持 PageRank 与介数中心性 (Betweenness Centrality) 分析
- Mermaid 图表导出（大图自动剪枝优化）
- Obsidian 原生兼容——直接通过 `wiki/` Vault 使用内置图谱视图

### 🤖 Claude Code 集成 (MCP Server)
原生支持 26 个工具，无需 API Key（Claude Code 作为默认 LLM）。
```json
{
  "mcpServers": {
    "kb": {
      "command": ".venv/Scripts/python.exe",
      "args": ["-m", "kb.mcp_server"]
    }
  }
}
```

**自然语言交互示例**：

| 你的需求 | 对话示例 |
|---|---|
| 摄入文件 | "将 raw/articles/file.md 摄入知识库" |
| 摄入网址 | "保存此链接到我的知识库：..." |
| 提问查询 | "我的知识库中关于 Transformer 有哪些内容？" |
| 健康检查 | "对知识库运行 lint 检查" |
| 发现盲区 | "我的知识库缺少哪些主题？" |
| 查看图谱 | "展示知识图谱" |

---

## 🧰 全部 26 个 MCP 工具

<details>
<summary><b>展开查看完整工具列表</b></summary>

### 核心操作

| 工具 | 说明 |
|---|---|
| `kb_query` | 查询知识库，返回上下文供 Claude Code 解答。添加 `use_api=true` 可启用 API 合成 |
| `kb_ingest` | 摄入源文件。可传入 `extraction_json` 自定义提取结果，省略则先获取提示词 |
| `kb_ingest_content` | 一步到位：提供原始内容 + 提取 JSON，自动保存至 `raw/` 并创建所有维基页 |
| `kb_save_source` | 仅保存内容至 `raw/` 不触发摄入。文件已存在时报错（除非 `overwrite=true`） |
| `kb_capture` | 将 ≤50KB 的聊天/笔记/转录文本原子化为 `raw/captures/*.md`。内置密钥扫描拦截 |
| `kb_compile_scan` | 列出需要 `kb_ingest` 的新增/变更资料 |

### 浏览与健康

| 工具 | 说明 |
|---|---|
| `kb_search` | 基于 BM25 + PageRank 的关键词检索 |
| `kb_read_page` | 按 ID 读取指定维基页面 |
| `kb_list_pages` | 列出所有页面（支持按类型过滤） |
| `kb_list_sources` | 列出所有原始资料文件 |
| `kb_stats` | 页面统计、图谱指标、覆盖率信息 |
| `kb_lint` | 健康检查（支持自动修复） |
| `kb_evolve` | 盲区分析与连接建议 |
| `kb_detect_drift` | 检测因原始资料变更而过期的维基页面 |
| `kb_compile` | 从原始资料编译知识库 |
| `kb_graph_viz` | 导出 Mermaid 知识图谱 |
| `kb_verdict_trends` | 基于历史审查的每周质量趋势 |

### 质量控制

| 工具 | 说明 |
|---|---|
| `kb_review_page` | 页面+来源+检查清单，用于质量审查 |
| `kb_refine_page` | 保留前置元数据更新页面，带审计追踪 |
| `kb_lint_deep` | 来源保真检查（页面对比原始资料） |
| `kb_lint_consistency` | 跨页面矛盾检测 |
| `kb_query_feedback` | 记录查询成功/失败，用于可信度评分 |
| `kb_reliability_map` | 基于反馈历史的页面可信度分布 |
| `kb_affected_pages` | 受变更影响的页面（反向链接+共享来源） |
| `kb_save_lint_verdict` | 记录 Lint/审查结果用于审计 |
| `kb_create_page` | 直接创建对比/综合/任意类型维基页 |

</details>

---

## ⚖️ 模型分级策略

三级 Claude 模型平衡成本与质量。可通过环境变量覆盖：

| 层级 | 默认模型 | 环境变量覆盖 | 适用场景 |
|---|---|---|---|
| scan（扫描） | Haiku 4.5 | `CLAUDE_SCAN_MODEL` | 索引读取、链接检查、差异比对 |
| write（撰写） | Sonnet 4.6 | `CLAUDE_WRITE_MODEL` | 信息提取、摘要生成、页面撰写 |
| orchestrate（编排） | Opus 4.7 | `CLAUDE_ORCHESTRATE_MODEL` | 查询合成、复杂任务编排 |

---

## 📚 支持的资料类型

| 类型 | 捕获方式 |
|---|---|
| 文章 (Article) | `trafilatura -u URL` 或 `crwl URL -o markdown` |
| 论文 (Paper) | `markitdown file.pdf` 或 `docling file.pdf` |
| 视频 (Video) | `yt-dlp --write-auto-sub --skip-download URL` |
| 代码库 (Repo) | 手动编写 Markdown 摘要 |
| 播客 (Podcast) | 转录文本 Markdown |
| 书籍 (Book) | 手动笔记或 `markitdown` |
| 数据集 (Dataset) | Schema 文档说明 |
| 对话 (Conversation) | 聊天/访谈转录文本 |

---

## 📁 项目目录结构

<details>
<summary><b>展开查看完整结构</b></summary>

```
llm-wiki-flywheel/
  raw/                     # 不可变的原始资料
    articles/papers/repos/videos/podcasts/books/datasets/conversations/assets/
  wiki/                    # LLM 生成的维基页面
    entities/concepts/comparisons/summaries/synthesis/
    index.md  _sources.md  _categories.md  log.md  contradictions.md
  templates/               # 10 套 YAML 提取模板
  src/kb/                  # Python 核心包（约 6,200 行）
    cli.py                 # Click CLI（6 个核心命令）
    config.py              # 路径、模型分级、调优常量
    mcp/                   # FastMCP 服务端（25 个工具）
    models/                # WikiPage, RawSource, 前置元数据校验
    ingest/                # 流水线 + 模板驱动提取器
    compile/               # 增量编译器 + 维基链接器
    query/                 # BM25 + PageRank 检索 + 引用生成
    lint/                  # 8 项检查 + 语义 Lint + 质量趋势
    evolve/                # 覆盖率分析 + 连接发现
    graph/                 # NetworkX 图谱 + 统计 + Mermaid 导出
    feedback/              # 贝叶斯可信度评分
    review/                # 页面-来源配对 + 优化器
    utils/                 # 哈希、LLM 调用、文本处理、I/O
  tests/                   # 2585 个测试用例（覆盖 215 个文件）
```

</details>

---

## 💻 开发指南

```bash
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Unix/macOS

pip install -r requirements.txt && pip install -e .
python -m pytest                # 运行 2585 个测试（7 个跳过）
ruff check src/ tests/ --fix    # 代码检查
ruff format src/ tests/         # 代码格式化
```

要求 Python 3.12+。使用 Ruff（行宽 100，规则 E/F/I/W/UP）。

---

## 🗺️ 路线图 (Roadmap)

- **Phase 4 (v0.10.0 已发布 2026-04-12)**：RRF 融合混合检索、4 层检索去重流水线、证据追踪模块、查询时过期事实标记、分层上下文组装、原始资料回退检索、摄入时自动矛盾检测、多轮查询重写。发布后审计已修复所有 HIGH (23) + MEDIUM (~30) + LOW (~30) 问题。
- **Phase 4.11 (未发布 2026-04-14)**：`kb_query --format={markdown|marp|html|chart|jupyter}` 输出适配器——将合成答案导出为 Markdown 文档、Marp 幻灯片、独立 HTML 页面、matplotlib Python 脚本（附 JSON 数据）或可执行 Jupyter Notebook。文件保存至 `outputs/{ts}-{slug}.{ext}`（已 gitignore），含来源前置元数据。响应 Karpathy Tier 1 #1 需求。
- **Phase 5.0 (未发布 2026-04-15)**：`kb lint --augment` 响应式盲区填充：Lint 发现残页 → 推荐权威链接（Wikipedia, arxiv）→ DNS 重绑定安全传输抓取 → 以 `confidence: speculative` 摄入。三阶段执行尊重人工审核：`propose → --execute → --auto-ingest`。含 G1-G7 资格门控、扫描层相关性检查、摄入后质量判定、回归 `[!gap]` 提示。跨进程限流：10次/运行 + 60次/小时 + 3次/主机/小时。
- **Phase 5 (延期)**：内联观点级可信度标签 + EXTRACTED Lint 验证、支持 URL 的 `kb_ingest`（5 状态适配器模型）、页面状态生命周期（seed→developing→mature→evergreen）、内联质量提示标记、Evolve 自主研究循环、`kb_capture` 对话捕获工具、块级 BM25 子页索引、图谱边类型化语义关系、交互式 vis.js HTML 图谱查看器、LLM 隐式关系推断、动态概览页、可操作盲区填充建议、两阶段编译流水线、多跳检索、对话→KB 提升、时间轴观点追踪、BM25 + LLM 重排序。
- **Phase 6 (未来规划)**：DSPy 优化、RAGAS 评估、蒙特卡洛证据采样。

**已完成版本**：
`v0.3.0` 5大操作+图谱+CLI+MCP(12) → `v0.4.0` 质量系统 → `v0.5.0` 鲁棒性 → `v0.6.0` DRY重构(180测试) → `v0.7.0` MCP拆分+PageRank(234) → `v0.8.0` BM25引擎(252) → `v0.9.x` 强化/审计/结构化输出(564~1033) → `v0.10.0` Phase4 混合检索+全量审计修复(1177测试)

---

## 🙏 特别致谢

| 项目 | 借鉴之处 |
|---|---|
| [Karpathy's LLM Knowledge Bases](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | 原创的"编译而非检索"范式 |
| [DocMason](https://github.com/JetXu-LLM/DocMason) | 验证门控、检索/追踪循环、答案溯源强制 |
| [Graphify](https://github.com/safishamsi/graphify) | 社区发现、逐观点可信度标记 |
| [Sirchmunk](https://github.com/modelscope/sirchmunk) | 蒙特卡洛采样、多轮查询重写 |
| [MemPalace](https://github.com/milla-jovovich/mempalace) | 分层上下文栈、时序知识图谱 |
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | 基于图谱的检索增强生成 |

**更多灵感来源**：`llm-wiki-compiler`、`rvk7895/llm-knowledge-bases`、`Ars Contexta`、`Remember.md`、`kepano/obsidian-skills`、`lean-ctx`、`DSPy optimization patterns`、`awesome-llm-knowledge-bases`、`qmd`、`Quartz`、`claude-obsidian`、`llm-wiki-skill`。（详见 [英文 README](README.md#more-inspirations) 完整对照表）

---

## 🤝 参与贡献

本项目正在积极开发中——⭐ **Star 仓库**以跟踪最新进展。每个版本都会带来实质性新功能（详见 [CHANGELOG.md](CHANGELOG.md)）。

- 🐛 发现 Bug？请在 [GitHub Issues](https://github.com/Asun28/llm-wiki-flywheel/issues) 提交。
- 💡 有新想法？先查看 [Roadmap](#️-路线图-roadmap)，若未涵盖，欢迎开 Issue 讨论。
- 👀 想持续关注？Star 仓库并留意 Release 通知。
- 📖 代码设计追求可读性：无魔法框架，纯 Python + BM25 + NetworkX + FastMCP。如果你有知识库、RAG 流水线或 LLM 工具链开发经验，30 分钟内即可熟悉代码结构。
- ⚠️ **暂不接受 PR**——架构仍在快速演进，合并外部代码成本较高。目前提交 Issue、反馈与建议是最佳贡献方式。

---

## 📜 许可证

[MIT License](LICENSE)
