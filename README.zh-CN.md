# 🌪️ LLM Wiki Flywheel

**Language / 语言：** [English](README.md) · **简体中文**

> **注意：** 英文版 [README.md](README.md) 是规范版本。中文镜像可能滞后 1-2 个开发周期；请通过 GitHub 查看最新状态。
> *Note: English [README.md](README.md) is canonical. This Chinese mirror may lag by 1-2 cycles; see GitHub for current state.*

![Python](https://img.shields.io/badge/python-3.12%2B-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Tests](https://img.shields.io/badge/tests-3461-brightgreen) ![MCP Tools](https://img.shields.io/badge/MCP%20tools-28-blueviolet) ![Version](https://img.shields.io/badge/version-v0.12.0-orange)

**编译知识，而非检索碎片。**
丢入原始资料，剩下的交给 Claude——自动提取实体、构建维基页面、注入双向链接、追踪可信度、标记矛盾点。以 Markdown 为核心，混合检索为可选项。生成的是完全由你掌控的纯 Markdown 文件，可直接在 Obsidian 中浏览。

灵感源自 [Karpathy 的 LLM 知识库构想](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)，并实现了**全自动化**。原生支持 Claude Code，内置 28 个 MCP 工具——无需配置 API Key 即可运行。同样支持通过 `KB_LLM_BACKEND` 接入本地 AI CLI 工具（Ollama、Gemini CLI、OpenCode、Codex CLI、Kimi Code、QWEN CODE CLI、DeepSeek Coder、GLM-4.5/ZAI CLI 等）。

---

## 🎯 为什么用户选择它而非传统 RAG？

🧠 **结构优先，向量可选**：基于实体、概念与维基链接构建真实知识图谱；BM25 + 向量混合检索按需启用，用于提升召回。
⚡ **默认增量更新**：基于 SHA-256 变更检测，仅重新处理新增或修改的资料。
🔗 **回溯式链接**：摄入新主题时，已有页面会自动补充 `[[维基链接]]`。
🧪 **自我修复**：贝叶斯可信度评分、矛盾检测、内容过期标记、死链检查。
🦉 **Obsidian 原生兼容**：将 `wiki/` 目录作为 Vault 打开，免费享受图谱视图、反向链接与悬浮预览。
🔌 **MCP 优先**：在 Claude Code 中内置 28 个工具。用自然对话管理知识库："摄入这篇"、"关于 X 我们知道什么？"
📤 **一键发布**：单条命令即可生成 `/llms.txt`、`/llms-full.txt`、`/graph.jsonld`、站点地图及关联页面——完整支持 Karpathy Tier-1 机器可读标准。

### 为什么不用 RAG？
RAG 检索的是文本块，而本系统理解的是知识结构。

| 维度 | 传统 RAG | 本项目 |
|---|---|---|
| 存储方式 | 不可读的向量嵌入 (Embeddings) | 可在 Obsidian 中直接浏览的 Markdown 页面 |
| 知识形态 | 无关联的文本碎片 (Chunks) | 由实体、概念和维基链接构成的知识图谱 |
| 检索质量 | 依赖 Top-K 相关性，结果不稳定 | BM25 + 向量混合排序，融合 PageRank 与页面可信度评分 |
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
| 依赖外部 LLM API 调用 | MCP 原生集成（Claude Code 内置 28 个工具，无需 API Key） |
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

**☁️ Obsidian + 远程存储（可选）**：安装 Obsidian 社区插件 [Remotely Save](https://github.com/remotely-save/remotely-save)（Apache 2.0 协议），可将 `wiki/` Vault 同步至 S3、Azure Blob、OneDrive 或 Dropbox。非技术用户无需命令行即可在任意设备上浏览已编译的知识库——`kb` 流水线写入存储桶，Remotely Save 自动同步至 Obsidian。

**💡 新手建议**：先浏览 `demo/` 文件夹。这是一个基于 Karpathy 推文与 Gist 编译的小型示例知识库，完整展示了目录结构与编译输出（摘要、实体、概念、对比分析、跨源综合）。在添加你自己的资料前，可以直观了解流水线的实际效果。

---

## 📄 支持的文件格式

将源文件放入对应的 `raw/` 子目录，然后运行 `kb ingest <file>` 或 `kb compile`。

| 格式 | 扩展名 | 说明 |
|---|---|---|
| Markdown | `.md` | 推荐用于网页剪藏、文章、笔记和已转换文档 |
| 纯文本 | `.txt` | 适合转录文本、笔记和简单导出 |
| reStructuredText | `.rst` | 适合 Python/项目文档 |
| 结构化数据 | `.json`, `.yaml`, `.yml`, `.csv` | 适合数据集、元数据和导出记录 |

> **PDF 文件：** 请先用 [`markitdown`](https://github.com/microsoft/markitdown) 或 [`docling`](https://github.com/DS4SD/docling) 转换为 Markdown，再将 `.md` 输出放入 `raw/papers/`。当前不支持直接摄入 `.pdf` 二进制文件。

对于 `.docx`、`.pptx` 或 `.xlsx` 等 Office 文档，请先转换为 Markdown 或 CSV，再放入 `raw/`。

### 转换命令

KB ingest 仅支持 `.md`、`.txt`、`.json`、`.yaml`、`.yml`、`.rst` 和 `.csv`。其他格式请先转换，再运行 `kb ingest`。

| 输入 | 转换命令 | KB 输出 |
|---|---|---|
| 网页文章 | `.\.venv\Scripts\python.exe -m trafilatura.cli -u URL > raw\articles\name.md` | `.md` |
| JavaScript 较重的网页 | `.\.venv\Scripts\python.exe -m crawl4ai.cli crawl URL -o markdown > raw\articles\name.md` | `.md` |
| PDF / DOCX / PPTX / XLSX | `.\.venv\Scripts\python.exe -m markitdown input.pdf -o raw\papers\name.md` | `.md` |
| 复杂 PDF / Office / 图片 / VTT | `.\.venv\Scripts\python.exe -m docling.cli.main input.pdf --to md --output raw\papers` | `.md` |
| YouTube | `.\.venv\Scripts\python.exe -m yt_dlp --write-auto-sub --skip-download URL -o raw\videos\name`，然后转换生成的 `.vtt` 文件 | `.md` / `.txt` |

对于 `yt-dlp` 生成的字幕文件，先将 `.vtt` 转为 Markdown，再摄入：

```powershell
.\.venv\Scripts\python.exe -m docling.cli.main raw\videos\video-name.en.vtt --from vtt --to md --output raw\videos
.\.venv\Scripts\python.exe -m kb.cli ingest raw\videos\video-name.en.md --type video
```

---

## 🛠️ 五大核心操作

| 操作 | 命令 | 功能说明 |
|---|---|---|
| 摄入 (Ingest) | `kb ingest <file>` | 提取实体/概念/核心观点 → 创建维基页 → 注入维基链接 → 更新索引 |
| 编译 (Compile) | `kb compile` | 批量摄入所有新增/变更资料（SHA-256 哈希检测，崩溃安全），成功后自动发布 |
| 查询 (Query) | `kb query "..."` | BM25 + 向量混合检索并融合 PageRank → 生成带内联引用的综合解答；`--format` 可将结果写入 `outputs/` |
| 检查 (Lint) | `kb lint` | 检测死链、孤立页、过期内容、残页、元数据、来源覆盖、链接环、重复 slug、低可信度页面；`--fix` 自动修复，`--augment` 从网络补全盲区 |
| 演进 (Evolve) | `kb evolve` | 分析覆盖盲区、连接机会、缺失页面类型、断开图谱组件 |

另有两条维护命令：

| 命令 | 功能说明 |
|---|---|
| `kb publish [--format all]` | 生成 `llms.txt`、`llms-full.txt`、`graph.jsonld`、`sitemap.xml` 与逐页关联文件至 `outputs/`（可用 `--out-dir` 覆盖） |
| `kb rebuild-indexes [--yes]` | 全量重置——删除哈希清单、向量库与进程内 LRU 缓存，使下次 `kb compile` 从零重新摄入 |

CLI 同时镜像了大部分 MCP 工具（`kb search`、`kb stats`、`kb read-page`、`kb lint-deep`、`kb detect-drift` 等），便于脱离 Claude Code 编写脚本。

---

## ✨ 核心特性

### 📥 摄入流水线 (Ingest Pipeline)
- 支持 9 种摄入资料类型：`article`、`paper`、`video`、`repo`、`podcast`、`book`、`dataset`、`conversation`、`capture`（`comparison` 与 `synthesis` 属于维基页面类型，请用 `kb_create_page` 创建）
- 基于哈希的去重机制——相同内容不会重复摄入
- 回溯式维基链接注入——摄入新主题时，提及该主题的历史页面自动补全链接
- 证据链 (Evidence Trail)——每个页面按倒序记录哪份资料在何时贡献了哪些内容，并由哨兵标记守护
- 摄入时自动矛盾检测——新资料与既有页面冲突时，即时写入 `wiki/contradictions.md`，而非等到查询时才暴露
- 级联追踪——返回受新摄入内容影响、可能需要复查的已有页面
- 短内容分级处理——小型资料（<1000 字符）延迟创建实体，避免生成"残页"(stubs)
- 对话捕获——`kb_capture` MCP 工具可将聊天/笔记/会话记录原子化为结构化知识项（决策、发现、修正、踩坑记录），内置密钥扫描安全拦截与进程级限流
- 结构化审计日志 `.data/ingest_log.jsonl`，全流程 `request_id` 关联

### 🔍 检索与查询 (Search & Query)
- 混合检索——BM25（标题加权 + 文档长度归一化）与向量检索通过 RRF 倒数排名融合；向量为可选依赖（`pip install -e '.[hybrid]'`），缺失时自动降级为纯 BM25
- PageRank 融合——连接度高的页面排名更靠前；`status: mature|evergreen` 与人工撰写的页面获得轻微加权
- 4 层去重流水线——避免同一观点占据三份上下文预算
- 多轮查询重写——追问自动继承上一轮的上下文
- 过期事实标记——当引用页面比其原始资料更旧时，答案会给出提示
- 原始资料回退——若没有维基页面覆盖该问题，引擎会直接检索 `raw/`，而不是凭空作答
- 上下文智能截断至 80K 字符；内联引用溯源 `[source: concepts/attention]` 确保每个观点有据可查
- 输出适配器——`kb query --format={markdown|marp|html|chart|jupyter}` 将答案写入 `outputs/`，可为文档、Marp 幻灯片、独立 HTML、matplotlib 脚本或可执行 Notebook

### 🛡️ 质量保障系统 (Quality System)
- 贝叶斯可信度评分——基于查询反馈动态调整页面可信度。"错误"惩罚权重是"不完整"的 2 倍
- 语义 Lint 检查——深度保真校验（页面对比原始来源）与跨页面矛盾检测
- Actor-Critic 审查机制——结构化 6 项检查清单，完整审计追踪
- 质量趋势看板——按周统计 pass/fail/warning，可视化质量演进轨迹
- 认知完整性元数据——可选的 `belief_state`（confirmed / uncertain / contradicted / stale / retracted）、`authored_by`（human / llm / hybrid）与 `status`（seed → developing → mature → evergreen）字段同时参与排序与发布过滤
- 响应式盲区填充——`kb lint --augment` 发现残页后推荐权威链接、经 DNS 重绑定安全传输抓取，并以 `confidence: speculative` 摄入。三道门控（`propose` → `--execute` → `--auto-ingest`）确保人工在环；限流 10 次/运行、60 次/小时、3 次/主机/小时

### 🕸️ 知识图谱 (Knowledge Graph)
- 基于 NetworkX 从维基链接构建图谱
- 支持 PageRank 与介数中心性 (Betweenness Centrality) 分析
- Mermaid 图表导出（大图自动剪枝优化）
- Obsidian 原生兼容——直接通过 `wiki/` Vault 使用内置图谱视图

### 📤 发布 (Publish)
`kb publish` 一次生成全部机器可读产物；`kb compile` 成功后也会自动触发：

| 产物 | 说明 |
|---|---|
| `llms.txt` | 面向 LLM 的精简维基索引 |
| `llms-full.txt` | 全部可发布页面的全文合集 |
| `graph.jsonld` | JSON-LD 知识图谱 |
| `sitemap.xml` | 标准站点地图 |
| 逐页关联文件 | 每个页面旁的同名 `.txt`，便于直接抓取 |

`belief_state: retracted|contradicted` 或 `confidence: speculative` 的页面会被跳过，未经核实的内容不会进入发布产物。

`kb publish` 默认写入 `outputs/`；编译成功后的自动发布则写入与 `wiki/` 同级的 `_publish/`（关闭开关 `KB_DISABLE_COMPILE_AUTO_PUBLISH=1`）。

### 🔒 安全与健壮性 (Safety & Robustness)
- 原子化加锁写入——所有维基页面修改都在可重入的页面级锁内进行；清单、日志与判定存储各自持有独立文件锁
- 路径安全——双锚点校验在任何读写前拦截路径穿越、Windows 非法字符与符号链接逃逸
- 提示注入围栏——所有维基与原始内容在进入 LLM 前均被包裹在 `<wiki_context>` 边界内；扫描层输出在进入编排层消费前于层级边界重新校验
- 崩溃安全编译——SHA-256 清单 + O_EXCL 建页，中断后可续跑而非损坏数据

### 🤖 Claude Code 集成 (MCP Server)
原生支持 28 个工具，无需 API Key（Claude Code 作为默认 LLM）。
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

## 🧰 全部 28 个 MCP 工具

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
| `kb_refine_list_stale` | 列出超时未完成的 pending 精炼行（仅查询，不修改） |
| `kb_refine_sweep` | 将过期 pending 行标记为失败或删除，带完整审计追踪 |

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

## 🤖 Vibe Coding CLI 后端支持

无需 Anthropic API Key，可直接使用任意**本地已安装的 AI CLI 工具**驱动 KB 的完整流水线。设置 `KB_LLM_BACKEND`，所有 `call_llm` / `call_llm_json` 调用将通过该工具的子进程（stdin 方式，防 Shell 注入；stdout/stderr 在记录前自动脱敏）执行：

```bash
export KB_LLM_BACKEND=ollama    # 可选：ollama | gemini | opencode | codex | kimi | qwen | deepseek | zai
kb query "什么是编译而非检索的模式？"
kb ingest raw/articles/my-notes.md
kb lint
```

| 后端 | 安装方式 | 默认分级模型 |
|------|---------|-------------|
| **Ollama** | [ollama.com](https://ollama.com) | `llama3.2` / `qwen2.5-coder:7b` / `qwen2.5-coder:32b` |
| **Gemini CLI** | `npm install -g @google/gemini-cli` | _（CLI 自动选择）_ |
| **OpenCode** | `npm install -g opencode-ai` | _（CLI 自动选择）_ |
| **Codex CLI** | `npm install -g @openai/codex` | _（CLI 自动选择）_ |
| **Kimi** | `pip install kimi-cli` | _（CLI 自动选择）_ |
| **QWEN** | `pip install qwen-cli` | _（CLI 自动选择）_ |
| **DeepSeek** | `pip install deepseek-cli` | _（CLI 自动选择）_ |
| **ZAI** | `pip install zhipuai-cli` | _（CLI 自动选择）_ |

可通过环境变量覆盖任意层级的模型：

```bash
export KB_CLI_MODEL_SCAN=llama3.2
export KB_CLI_MODEL_WRITE=qwen2.5-coder:7b
export KB_CLI_MODEL_ORCHESTRATE=qwen2.5-coder:32b
```

取消设置 `KB_LLM_BACKEND`（或设为 `anthropic`）即可恢复默认 Claude 路径。

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
| 捕获 (Capture) | `kb_capture` MCP 工具——将聊天或会话记录原子化为结构化知识项 |

如果捕获到的资料不是受支持的文本格式，请先使用上面的转换命令。

---

## 📁 项目目录结构

<details>
<summary><b>展开查看完整结构</b></summary>

```
llm-wiki-flywheel/
  raw/                     # 不可变的原始资料
    articles/papers/repos/videos/podcasts/books/datasets/conversations/captures/assets/
  wiki/                    # LLM 生成的维基页面
    entities/concepts/comparisons/summaries/synthesis/
    index.md  _sources.md  _categories.md  log.md  contradictions.md
  templates/               # 11 套 YAML 模板（9 种摄入类型 + comparison/synthesis）
  src/kb/                  # Python 核心包（约 21,400 行）
    cli.py                 # Click CLI（24 个命令）
    config.py              # 路径、模型分级、调优常量
    errors.py              # KBError 异常分类体系（ValidationError、StorageError 等）
    capture.py             # 聊天/会话记录原子化
    mcp/                   # FastMCP 服务端（28 个工具）+ 统一错误边界
    models/                # WikiPage, RawSource, 前置元数据校验
    ingest/                # 流水线 + 模板驱动提取器 + 证据链
    compile/               # 增量编译器 + 维基链接器 + 发布构建器
    query/                 # BM25 + 向量混合检索、RRF、去重、引用、formats/
    lint/                  # 8 项检查 + 语义 Lint + 判定存储 + augment/ 盲区填充
    evolve/                # 覆盖率分析 + 连接发现
    graph/                 # NetworkX 图谱 + 统计 + Mermaid 导出 + 缓存
    feedback/              # 贝叶斯可信度评分
    review/                # 页面-来源配对 + 优化器
    utils/                 # 哈希、LLM 调用、页面锁、路径安全、I/O
  tests/                   # 3461 个测试用例（覆盖 235 个文件）
```

</details>

---

## 💻 开发指南

```bash
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Unix/macOS

pip install -r requirements.txt && pip install -e .
python -m pytest                # 3421 通过，24 跳过，16 预期失败
ruff check src/ tests/ --fix    # 代码检查
ruff format src/ tests/         # 代码格式化
```

要求 Python 3.12+。使用 Ruff（行宽 100，规则 E/F/I/W/UP）。

---

## 🗺️ 路线图 (Roadmap)

### 已交付

| 阶段 | 核心内容 |
|---|---|
| **Phase 4**（v0.10.0） | RRF 融合混合检索、4 层去重流水线、证据追踪、查询时过期事实标记、摄入时自动矛盾检测 |
| **Phase 4.11** | `kb query --format={markdown\|marp\|html\|chart\|jupyter}`——答案导出为文档、Marp 幻灯片、独立 HTML、绘图脚本或 Notebook |
| **Phase 5.0** | `kb lint --augment` 响应式盲区填充：发现残页 → 推荐权威链接 → 安全抓取 → 以 `confidence: speculative` 摄入，全程三阶段人工审核门控 |
| **Phase 4.5** | 22 周期发布后审计：`kb.errors` 异常分类体系、`kb publish` Tier-1 发布格式、Epistemic-Integrity 2.0、8 个替代 LLM CLI 后端、60+ 安全威胁关闭 |
| **Cycle 23-82** | 持续加固：双锚点路径安全、MCP 错误边界、wiki 上下文边界围栏、层级边界校验、可重入页面级写锁 |

逐周期明细见 [`CHANGELOG.md`](CHANGELOG.md) 与 [`CHANGELOG-history.md`](CHANGELOG-history.md)。

### 下一步 — Phase 5（延期）

- **接地校验** — 内联观点级可信度标签 + EXTRACTED Lint；观点溯源 BM25 核验（事后幻觉检测）；多源确认门控（`belief_state: confirmed` 需 ≥ 2 个独立原始资料）
- **检索** — 块级 BM25 子页索引、多跳检索、BM25 + LLM 重排序
- **图谱** — 边类型化语义关系、LLM 隐式关系推断、交互式 vis.js 查看器、动态概览页
- **摄入** — 支持 URL 的 `kb_ingest`（5 状态适配器）、两阶段编译流水线、对话→KB 提升、时间轴观点追踪、Evolve 自主研究循环

### 远期 — Phase 6

DSPy 优化、RAGAS 评估、蒙特卡洛证据采样。

<details>
<summary><b>已完成版本</b></summary>


| 版本 | 核心内容 | 测试数 |
|---|---|---|
| v0.3.0 | 5大操作 + 图谱 + CLI + MCP (12 工具) | — |
| v0.4.0 | 质量系统：贝叶斯可信度、Actor-Critic 审查、语义 Lint | — |
| v0.5.0 | 鲁棒性：YAML 注入防护、路径规范化 | — |
| v0.6.0 | DRY 重构：共享工具函数、测试夹具 | 180 |
| v0.7.0 | MCP 拆包、PageRank、实体丰富、持久化审查记录 | 234 |
| v0.8.0 | BM25 检索引擎 | 252 |
| v0.9.0–v0.9.9 | 全面强化、综合审计、结构化输出、内容增长 | 564 |
| v0.9.10–v0.9.13 | 引用修复、编译扫描、BM25 去重、54 条 Backlog 修复 | 651 |
| v0.9.14 | Phase 3.95 — 38 条 Backlog 修复 | 692 |
| v0.9.15 | Phase 3.96 — 153 条修复（4 CRITICAL, 31 HIGH, 54 MEDIUM, 64 LOW） | 952 |
| v0.9.16 | Phase 3.97 — 62 条修复：原子写入、MCP 异常防护、slugify 符号映射、CRLF、整数标题强制转换 | 1033 |
| v0.10.0 | Phase 4 — RRF 混合检索、4 层去重、证据追踪、查询时过期标记、分层上下文、原始资料回退、自动矛盾检测、多轮重写；发布后修复全部 HIGH/MEDIUM/LOW | 1177（55 文件）|
| Phase 4.5（未发布） | v0.10.0 后持续审计，22 周期，异常分类体系、O_EXCL 防碰撞、新增 2 个 MCP 工具、批量链接注入、Epistemic-Integrity 2.0、`kb publish` 5 种格式、60+ 安全威胁关闭、8 提供商 CLI 子进程后端（Cycle 21）、wiki 路径摄入防护与提取接地提示（Cycle 22） | 2725（230 文件）|

</details>

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
