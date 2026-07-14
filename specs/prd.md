# MLagent_v2 · 产品需求文档 (PRD)

<!-- Product Requirements Document -->

---

## 1 文档信息 · Document Info

| 字段 | 内容 |
|------|------|
| 文档版本 | v0.1-draft |
| 创建日期 | 2026-05-22 |
| 状态 | Draft — 待工程评审 |
| 产品名称 | MLagent_v2 |
| 定位 | 内部工具，团队自用，不对外分发或商业化 |
| 上游依据 | `specs/research/04-决策汇总.md`（v2）、`06-架构基线决策.md`（Approved） |
| 架构基线 | 已锁定（AIDE fork + mem0 + MLflow + Claude Agent SDK），本文不重开 |
| 作者 | 由 Brainstorming Skill 收敛输出后生成 |

**版本历史**

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v0.1 | 2026-05-22 | 首版 Draft，基于 brainstorming 收敛 + 对抗调研 v2 |

---

## 2 项目背景与目标 · Background & Goals

### 2.1 背景：问题是什么

生物信息研究团队每周进行多次 NGS（Next-Generation Sequencing）机器学习实验，当前存在三类系统性损耗：

| 痛点 | 当前状态 | 影响 |
|------|---------|------|
| 手动调参 | 每次实验 1-2 天人工摸索 | 高效能工程师时间被低价值重复工作占用 |
| 经验孤岛 | 成功结论散落在各自 notebook，无法跨项目复用 | 新项目重复摸索相同失败路径 |
| 知识不可检索 | 历史实验无语义索引，只能靠个人记忆或文件搜索 | 团队知识随人员流动流失 |

**市场空白确认**：调研 14 个同类系统（AIDE、RD-Agent、MALMAS、CellAtria 等），无任何产品同时满足：
面向 NGS ML 训练 + 跨会话持久化经验库 + Skill 复用机制 + ipynb/文献导入 + 对话式交互迭代。

### 2.2 业务目标

- 将手动调参时间从"每次 1-2 天摸索"压缩至"一次设定 + Agent 自动跑完"
- 将成功实验范式沉淀为可复用 Skill，消除跨项目重复摸索的沉没成本
- 让历史实验经验可语义检索，而不是散落在各自 notebook

### 2.3 产品目标（MVP）

> 能在团队 NGS 特征矩阵上完成一次完整探索循环（≥ 10 轮、AUC 自动评估、
> 结果写入 SQLite），全程无人工干预。

### 2.4 Non-Goals（明确不做）

| 不做的事 | 原因 |
|---------|------|
| 多用户支持 / 登录 / 权限系统 | 内部单用户工具，超出 MVP 范围 |
| 原始测序数据处理（BAM/VCF 解析） | 输入边界是预处理后的特征矩阵 CSV |
| 模型推理部署（Serving） | 只做训练和特征选择 |
| 深度学习（GPU 训练） | 只做 sklearn / XGBoost 级别经典 ML |
| 商业化 / 计费 / SaaS 分发 | 内部工具定位 |
| 实时流数据处理 | 只做批处理 |

---

## 3 目标用户与画像 · Target Users

### 3.1 主画像 A：生物信息工程师（主要用户）

| 属性 | 描述 |
|------|------|
| 角色 | 负责 NGS 数据分析的工程师或计算生物学家 |
| 使用频率 | 每周跑 3-5 次 NGS ML 实验 |
| 技术背景 | 熟悉 Python、sklearn；可接受 CLI 和 Jupyter |
| 核心痛点 | 调参靠手动记录；换数据集后经验无法复用；notebook 结论难以检索 |
| 工具偏好 | CLI / Jupyter；不希望配置复杂 |
| 成功标准 | "不再需要手动搜索哪个特征组合曾经有效" |

### 3.2 主画像 B：PI / 高级研究员（次要用户）

| 属性 | 描述 |
|------|------|
| 角色 | Principal Investigator 或高级研究员 |
| 使用频率 | 每月 1-3 次，通常是新课题探索阶段 |
| 技术背景 | ML 实现能力有限；读文献多于写代码 |
| 核心痛点 | 看了文献想复现某特征工程策略，但实现成本高 |
| 工具偏好 | Web UI；需要可视化实验结果 |
| 成功标准 | "描述一个文献中的方法，Agent 帮我验证是否在本数据集上有效" |

### 3.3 反画像（不服务）

- 纯湿实验研究员（不接触计算数据）
- 需要 GPU 深度学习的 AI 研究员（超出 MVP 技术范围）
- 外部商业用户（架构决策已明确排除）

---

## 4 用户故事 · User Stories

以下 5 个用户故事采用 INVEST 格式，按优先级排序。

### US1 — 探索实验（Phase 1 核心）

```
As a bioinformatician,
I want to hand the agent a feature matrix + target metric + round budget,
so that it automatically explores feature-model-hyperparameter combinations
and returns the best configuration without manual iteration.
```

**场景**：工程师上传 NGS 特征矩阵 CSV，设置目标指标 AUC 和最大轮数，等待
Agent 自动完成探索并输出最优配置摘要。

---

### US2 — 经验检索（Phase 2）

```
As a bioinformatician,
I want to query past experiment outcomes by semantic similarity
(e.g., "methylation features for CNS classification"),
so that I don't repeat work that already failed or succeeded.
```

**场景**：工程师用自然语言描述新任务，Agent 检索历史相关实验并注入上下文。

---

### US3 — Skill 范式复用（Phase 2）

```
As a bioinformatician,
I want to invoke a proven pipeline Skill on a new dataset,
so that a successful configuration from a previous project
is reproduced without manual reconstruction.
```

**场景**：Agent 根据任务描述语义匹配合适 Skill，自动执行固定流程并记录结果。

---

### US4 — ipynb 导入（Phase 3）

```
As a researcher,
I want to upload a historical notebook and get a Skill draft extracted automatically,
so that documented experiments enter the team's reusable knowledge base.
```

**场景**：研究员上传历史 `.ipynb`，系统解析后生成 SKILL.md 草稿，用户确认后
写入知识库。

---

### US5 — 交互式方法探索（Phase 3）

```
As a researcher with a new hypothesis or methodological idea,
I want to describe a direction to the agent in natural language
(e.g., "explore whether promoter-region CpG features outperform
gene-body features for this tumor type"),
so that the agent researches the approach, executes targeted experiments,
and quickly reports whether the hypothesis holds.
```

**场景**：PI 描述一个方法学假设，Agent 可能调用 muyu-search 检索文献支撑，
规划并执行定向探索，输出假设成立与否的结论摘要。

---

## 5 功能列表与范围 · Feature Scope

### 5.1 In-Scope（做什么）

| # | 功能 | 对应 US | 优先级 |
|---|------|---------|-------|
| F1 | AIDE 树搜索探索引擎（harness 替换为 Claude Agent SDK） | US1 | Must |
| F2 | sklearn / XGBoost 训练脚本 Bash 调用 | US1 | Must |
| F3 | SQLite 情节记忆（实验记录：特征组合 / 参数 / AUC / 时间戳） | US1、US2 | Must |
| F4 | PreToolUse safety hooks（危险命令拦截） | US1-US5 | Must |
| F5 | CLI 交互入口（Claude Code CLI） | US1 | Must |
| F6 | mem0 语义记忆（insert-only 适配 + metadata 索引层） | US2、US3 | Should |
| F7 | MLflow autolog 实验追踪 | US1、US3 | Should |
| F8 | 初始 NGS Skill 库（手工编写 1-2 个） | US3 | Should |
| F9 | Streamlit 基础 UI（任务监控 + 实验列表 + AUC 曲线） | US1-US3 | Should |
| F10 | AIDE 模型路由配置化重写（OQ2 方案 B） | US1 | Could |
| F11 | ipynb → SKILL.md 解析管道（nbformat 自研） | US4 | Could |
| F12 | muyu-search 工具接入（联网检索文献 / 方法） | US5 | Could |
| F13 | 子 agent 并行超参数探索 | US1 | Could |
| F14 | Streamlit 记忆库浏览界面（语义检索 UI） | US2 | Could |
| F15 | 文献 URL 导入至 ChromaDB | US2、US5 | Could |

### 5.2 Out-of-Scope（明确不做，本轮）

| 项目 | 说明 |
|------|------|
| OpenFE / Featuretools 工具库 | Phase 4 评估，NGS 高维场景 OOM 风险未解决 |
| Skill 置信度回流 / 自动进化 | 架构缺口，需另立设计文档 |
| Docker 沙箱 / supervisord | Phase 4-5 硬化阶段 |
| 甲基化特征自优化二次接口 | Phase 5 预留 |
| 多用户支持 / 权限系统 | Non-Goal，已锁定 |
| GPU 深度学习训练 | 超出 MVP 技术范围 |
| 模型推理部署（Serving） | Non-Goal |
| 原始测序数据处理（BAM/VCF 解析） | 输入边界在特征矩阵 CSV 层 |

---

## 6 详细功能描述 · Feature Details

每个功能用**触发 / 输入 / 流程 / 输出 / 边界**五元组描述。

---

### F1 · AIDE 树搜索探索引擎

| 元素 | 内容 |
|------|------|
| **触发** | 用户在 CLI 或 Streamlit 发起"探索实验"任务 |
| **输入** | 特征矩阵 CSV（≥ 100 样本，≥ 100 特征）；目标指标（AUC）；最大轮数（≥ 10） |
| **流程** | 1. Agent 读取 CSV，检测缺失值（> 30% 写入元数据警告，执行 median imputation）<br>2. AIDE 树搜索生成候选特征子集 + 模型 + 超参组合<br>3. Bash 调用 sklearn/XGBoost 训练脚本，等待结果<br>4. 每轮结果立即写入 SQLite（`status=completed/oom/timeout`）<br>5. 循环至达到最大轮数或早停条件（连续 10 轮 AUC 提升 < 0.002）<br>6. 输出最优配置摘要 |
| **输出** | 最优特征子集 + 模型参数 + AUC；所有轮次写入 SQLite；可选生成 SKILL.md 草稿 |
| **边界** | 单轮超时（> 30 min）：kill subprocess，标记 `status=timeout`，继续下轮<br>单轮 OOM：捕获 MemoryError，标记 `status=oom`，跳过该节点<br>上下文膨胀：每轮立即持久化，触发 server-side compaction，不依赖 context 记忆 |

---

### F2 · sklearn / XGBoost 训练脚本调用

| 元素 | 内容 |
|------|------|
| **触发** | AIDE 引擎生成训练配置后，Agent 调用 Bash 工具 |
| **输入** | 特征子集列表、模型类型（sklearn estimator / XGBoost）、超参字典、CSV 路径 |
| **流程** | 1. 写入临时配置文件<br>2. 通过 subprocess 执行训练脚本（`n_jobs=-1`）<br>3. 捕获 stdout（AUC、特征重要性）<br>4. MLflow autolog 自动记录参数和指标 |
| **输出** | AUC、训练时长、特征重要性 Top-10；写入 MLflow + SQLite |
| **边界** | 30 min 超时硬限制；禁止 `rm -rf`、`chmod 777`、外网 curl（PreToolUse hook 拦截） |

---

### F3 · 三层记忆写入与检索

| 元素 | 内容 |
|------|------|
| **触发** | 每轮实验完成后自动写入；用户发起语义查询时检索 |
| **输入** | 实验结果（情节记忆写入）；自然语言查询字符串（语义检索） |
| **流程** | **写入**：实验结果 → SQLite `experiments` 表（情节）+ mem0 `add()`（语义，insert-only）<br>**检索**：查询文本 → ChromaDB 向量检索 → 返回 top-3 相关实验摘要 |
| **输出** | 写入：SQLite 记录 + ChromaDB 向量；检索：top-3 摘要（含 AUC、特征数、时间戳） |
| **边界** | ChromaDB 写入失败 → 降级纯 SQLite，标记 `memory_sync=pending`，下次启动重试<br>新旧结论矛盾 → 标记 `needs_review=true`，不自动覆盖 |

---

### F4 · Skill 加载与范式复用

| 元素 | 内容 |
|------|------|
| **触发** | 用户描述任务，Agent SDK 语义匹配 `.claude/skills/` 下的 SKILL.md |
| **输入** | 任务自然语言描述；已有 SKILL.md 文件（含 `name`、`description`、流程步骤） |
| **流程** | 1. Agent SDK 基于描述语义匹配最相关 Skill<br>2. 加载 SKILL.md 内容，按固定流程执行<br>3. 将执行结果写入 MLflow 和 SQLite |
| **输出** | Skill 执行结果（AUC、配置摘要）；写入 MLflow + SQLite |
| **边界** | 无匹配 Skill → 使用 system prompt 默认探索流程，不报错<br>Skill YAML 解析失败 → SDK 跳过，记录警告日志，不影响其他 Skill |

---

### F5 · ipynb → SKILL.md 解析管道（Phase 3）

| 元素 | 内容 |
|------|------|
| **触发** | 用户通过 Streamlit UI 上传 `.ipynb` 文件 |
| **输入** | Jupyter Notebook 文件（含特征选择代码 + 结论 Markdown） |
| **流程** | 1. nbformat 解析提取 code cell + markdown cell<br>2. LLM 结构化为 SKILL.md 草稿（`name`、`description`、步骤）<br>3. Streamlit UI 展示草稿供用户审核编辑<br>4. 用户确认后写入 `.claude/skills/<name>/SKILL.md` |
| **输出** | SKILL.md 文件（用户确认后才写入） |
| **边界** | 未确认前不写入；Skill 草稿质量差时展示给用户修改，不自动入库 |

---

### F6 · 交互式方法探索（Phase 3）

| 元素 | 内容 |
|------|------|
| **触发** | 用户在 Streamlit 交互模式或 CLI 描述一个方法学假设 |
| **输入** | 自然语言假设描述（如"探索 promoter-region CpG 特征是否优于 gene-body 特征"） |
| **流程** | 1. Agent 理解方向，必要时调用 muyu-search 检索文献支撑<br>2. 规划定向实验方案（≥ 3 轮）<br>3. 执行实验，每轮结果写入 SQLite<br>4. 汇总输出结论摘要 |
| **输出** | 结论摘要：假设是否成立 + 支撑 AUC 数据 + 关键特征发现 |
| **边界** | muyu-search 仅传输查询文本，不传输实验数据<br>OQ6：muyu-search 触发策略（自动 vs 显式）Phase 3 设计时决策 |

---

## 7 非功能需求 · Non-Functional Requirements

### 7.1 性能

| 指标 | 要求 | 测试条件 |
|------|------|---------|
| 单轮训练时长 | < 5 分钟 | 1000 样本 × 500 特征，XGBoost，`n_jobs=-1`，8 核 CPU |
| mem0 语义检索延迟 | < 2 秒 | ChromaDB，< 1000 条记忆 |
| SQLite 查询 | < 0.5 秒 | < 500 条记录，无大表 JOIN |
| Streamlit UI 初始加载 | < 3 秒 | 实验列表 < 500 条 |

### 7.2 可靠性

| 指标 | 要求 |
|------|------|
| 实验中断恢复 | 从 SQLite 最后一条 `status=completed` 记录继续，不从零重跑 |
| 崩溃时数据丢失 | 0 条已完成实验记录丢失（每轮结束立即落盘） |
| mem0 降级 | ChromaDB 不可用时自动降级为纯 SQLite，不阻塞探索主循环 |
| 上下文溢出 | 每轮立即持久化 + server-side compaction，不依赖 context 记忆 |

### 7.3 安全 / 合规

| 约束 | 要求 |
|------|------|
| NGS 数据隔离 | 数据不进入 Anthropic API context；Bash 工具调用本地 Python 脚本，数据留在本地进程 |
| API Key 管理 | 仅通过环境变量传入，禁止硬编码 |
| 本地部署隔离 | 数据不离开用户机器；muyu-search 仅传输查询文本 |
| PreToolUse hook | 禁止：`rm -rf`、`chmod 777`、`curl`（外网请求）、写入 `/etc/` 或 `~/.ssh/` |
| 文件写入范围 | 仅允许在 `experiments/` 指定目录内写文件 |

### 7.4 平台约束

| 约束 | 要求 |
|------|------|
| 操作系统 | macOS / Linux（Windows 不在支持范围） |
| Python 版本 | 3.10+（AIDE + mem0 + ChromaDB 兼容要求） |
| 硬件最低配置 | 16 GB RAM + 8 核 CPU |
| 磁盘 | 100 GB+（NGS 数据集可达数十 GB） |

---

## 8 UI / 交互说明 · UI & Interaction

### 8.1 双模并行入口

```
用户入口
  ├── Streamlit Web UI（主界面，localhost:8501）
  │     监控、记忆库、导入、可视化、交互指令
  └── Claude Code CLI（开发调试入口）
        直接发指令、开发 Skill、查看日志
```

### 8.2 Streamlit 主界面布局

```
┌──────────────────────────────────────────────────────────────┐
│  顶部导航：[新任务]  [实验历史]  [经验记忆库]  [Skill 管理]  [设置] │
├────────────────────┬─────────────────────────────────────────┤
│  左侧：当前任务面板  │  右侧：实时日志 + 实验进度                   │
│  ────────────────  │  ───────────────────────────────────    │
│  · 数据集路径       │  [Agent 正在探索特征组合 #12/50...]         │
│  · 目标指标 (AUC)   │  [当前最优: AUC=0.884，15 个特征]           │
│  · 模式选择         │  [尝试: +甲基化密度特征，AUC=0.891 ↑]       │
│    ○ 探索模式       │  ───────────────────────────────────    │
│    ○ Skill 范式     │  最近实验列表（来自 SQLite）                 │
│    ○ 交互模式       │  AUC 曲线图（st.line_chart）               │
├────────────────────┴─────────────────────────────────────────┤
│  底部：用户指令输入框（交互模式下激活）                              │
│  "继续探索 / 切换到 LightGBM / 重点优化召回率..."                  │
└──────────────────────────────────────────────────────────────┘
```

### 8.3 关键 Streamlit 组件映射

| 功能 | Streamlit 组件 |
|------|--------------|
| 文件上传（CSV / ipynb） | `st.file_uploader` |
| 实验记录列表 | `st.dataframe` |
| AUC 曲线 | `st.line_chart` |
| 任务进度 | `st.progress` + `st.status` |
| 交互指令 | `st.chat_input` |
| Skill 草稿展示 + 确认 | `st.text_area` + `st.button` |

### 8.4 CLI 交互模式

Phase 1 无 Streamlit UI，全部交互通过 Claude Code CLI 完成：
- 探索实验：直接发指令给 Agent
- Skill 草稿确认：terminal Y/N 提示（OQ7 决策点）
- 实验结果：输出到 stdout + SQLite

---

## 9 验收标准 · Acceptance Criteria

所有验收标准采用 Given / When / Then 格式，可机器验证。

---

### AC-US1 · 探索实验

**Given** 用户提供 `features.csv`（≥ 100 样本，≥ 100 特征）、目标指标 AUC、
最大轮数 ≥ 10

**When** 用户通过 CLI 或 Streamlit 执行探索命令

**Then**
- Agent 完成 ≥ 10 轮实验，全程无人工干预
- 每轮结果写入 SQLite（`status` = `completed` / `oom` / `timeout`）
- 输出最优配置摘要（特征子集 + 模型参数 + AUC）
- 最优 AUC 高于 baseline（默认 XGBoost 配置、无 Skill 注入的单轮 AUC）

---

### AC-US2 · 经验检索

**Given** SQLite 中已有 ≥ 5 条历史实验，ChromaDB 有对应语义摘要

**When** 用户输入自然语言查询（如"甲基化特征 CNS 分类"）

**Then**
- 返回 top-3 历史实验摘要（含 AUC、特征数量、时间戳）
- 响应延迟 < 2 秒

---

### AC-US3 · Skill 范式复用

**Given** `.claude/skills/` 中存在至少 1 个有效 Skill（YAML 解析正常）

**When** 用户描述与该 Skill description 语义相似的任务

**Then**
- Agent 自动加载并执行该 Skill，无需用户指定 Skill 名称
- 执行结果写入 MLflow 和 SQLite
- 输出结论摘要

---

### AC-US4 · ipynb 导入

**Given** 用户上传含特征选择代码 + 结论 Markdown 的 `.ipynb` 文件

**When** 用户通过 Streamlit UI 或 CLI 触发解析管道

**Then**
- 输出 SKILL.md 草稿（含 `name`、`description`、标准流程步骤）
- 草稿展示给用户确认
- 用户未确认前，`.claude/skills/` 目录无新文件写入

---

### AC-US5 · 交互式方法探索

**Given** 研究员有一个新的方法学假设，系统已配置 muyu-search（可选调用）

**When** 用户用自然语言描述该假设

**Then**
- Agent 理解方向（必要时调用 muyu-search 检索背景知识）
- 规划并执行 ≥ 3 轮定向探索
- 输出结论摘要（假设是否成立 + 支撑 AUC 数据）

---

## 10 优先级 / MVP 范围 · Priority & MVP Scope

### MoSCoW 优先级矩阵

| 优先级 | 功能 | Phase | 预估人天 |
|--------|------|-------|---------|
| **Must** | Claude Agent SDK 主循环（ReAct） | 1 | 2-3 |
| **Must** | AIDE fork + harness 替换 + 路由修复（OQ2 方案 A） | 1 | 15-20 |
| **Must** | sklearn / XGBoost Bash 工具调用 | 1 | — |
| **Must** | SQLite 情节记忆最小 schema | 1 | — |
| **Must** | PreToolUse safety hooks | 1 | 2-3 |
| **Must** | CLI 交互入口 | 1 | — |
| **Should** | mem0 insert-only 适配 + metadata 索引层 | 2 | 3-5 |
| **Should** | MLflow autolog 集成 | 2 | 1-2 |
| **Should** | 初始 NGS Skill 库（1-2 个，需领域专家） | 2 | 3-5 |
| **Should** | Streamlit 基础 UI（任务监控 + 实验列表） | 2 | 5-8 |
| **Could** | AIDE 模型路由配置化重写（OQ2 方案 B） | 3 | — |
| **Could** | ipynb → SKILL.md 解析管道 | 3 | 2-3 |
| **Could** | muyu-search 工具接入 | 3 | 0.5 |
| **Could** | 子 agent 并行超参数探索 | 3 | — |
| **Could** | Streamlit 记忆库浏览界面 | 3 | — |
| **Could** | 文献 URL 导入至 ChromaDB | 3 | — |
| **Won't** | OpenFE / Featuretools / pysam / pyranges | 4+ | — |
| **Won't** | Skill 置信度回流 / 自动进化 | 后续 | — |
| **Won't** | Docker 沙箱 / supervisord / Qdrant 升级 | 4-5 | — |
| **Won't** | 多用户支持 / 权限系统 | Non-Goal | — |

### MVP 最小可验证版本（Phase 1 结束）

> **能在团队 NGS 特征矩阵上完成一次完整探索循环（≥ 10 轮，AUC 自动评估，**
> **结果写入 SQLite），全程无人工干预。**

Phase 1 交付物：
- AIDE fork（接入 Claude Agent SDK，路由修复）
- 训练脚本 Bash 调用（sklearn + XGBoost）
- SQLite 最小 schema（实验记录 5 个核心字段）
- PreToolUse safety hooks
- CLI 交互入口

---

## 11 度量指标 · Metrics

### 11.1 北极星指标

**每周通过 Agent 完成的有效探索实验数**

- **定义**：一次探索完成 ≥ 10 轮，最优 AUC 高于 baseline
  （默认 XGBoost 配置、无 Skill 注入的单轮 AUC），结果写入 SQLite
- **目标**：上线 4 周内稳定达到 ≥ 3 次 / 周

### 11.2 辅助指标

| 指标 | 定义 | 目标 |
|------|------|------|
| Skill 库月净增数 | 每月新增并通过人工确认的 SKILL.md 数量 | Phase 2 起 ≥ 1 个 / 月 |
| 经验命中率 | 检索到历史相关实验并被 Agent 实际引用的比例 | Phase 2 起 ≥ 50% |
| AUC 达成率 | 有效探索实验中，最优 AUC > baseline 的比例 | ≥ 60%（8 周内） |

### 11.3 关停线（Kill Switch）

| 信号 | 阈值 | 触发动作 |
|------|------|---------|
| AUC 达成率 | 8 周内 < 50% | 评估探索引擎或领域知识注入根本问题 |
| AIDE fork 维护成本 | 超过 +13 人天预留缓冲 | 启动自研探索引擎可行性评估 |
| mem0 存储膨胀 | insert-only 模式 1 个月 > 10 GB | 触发 OQ1 决策点（MongoDB / Qdrant） |
| ChromaDB 检索退化 | 1K 条记忆后语义相关性明显下降 | 触发 Qdrant 迁移评估 |

---

## 12 依赖与约束 · Dependencies & Constraints

### 12.1 外部 API 依赖

| 依赖 | 现状 | 风险 |
|------|------|------|
| Anthropic API（Sonnet 4.6 主推理 + Haiku 4.5 轻量子 Agent） | 按量付费，无硬上限 | 多子 agent 高频探索时成本需监控；建议设置每日消费告警 |
| Tavily API（muyu-search MCP 搜索后端） | Key 已在 `.mcp.json`，免费配额 | Phase 3 上线前确认免费配额满足内部使用量 |

### 12.2 数据安全约束

| 约束 | 说明 |
|------|------|
| NGS 基因组数据隐私 | 数据不进入 Anthropic API context；Bash 工具调用本地脚本，数据留在本地进程 |
| 本地部署隔离 | muyu-search 仅传输查询文本，不传输实验数据 |
| 数据使用协议 | 需团队确认 NGS 数据使用协议与本地部署架构兼容 |

### 12.3 人力约束

| 角色 | 投入 | 何时需要 |
|------|------|---------|
| 高级 Python 工程师 | 全职 8-10 周（建议按 10-12 周规划，留 20% buffer） | Phase 1 起 |
| NGS 领域专家 | 3-5 人天 | Phase 2 启动时（Skill 编写 + 生物学合理性 review） |

### 12.4 开源许可证约束

| 组件 | License | 约束 |
|------|---------|------|
| AIDE fork | MIT | 保留 MIT 声明，fork 自由 |
| mem0 | Apache-2.0 | 内部使用无限制 |
| MLflow | Apache-2.0 | 内部使用无限制 |
| Notebook Intelligence | GPL-3.0 | **仅参考设计模式，不复用代码** |
| AutoML-Agent | CC BY-NC 4.0 | **完全排除，连参考都要谨慎** |

---

## 13 风险与对策 / 开放问题 · Risks & Open Questions

### 13.1 风险登记册

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|---------|
| R1 | NGS 领域知识空白导致 Agent 犯生物信息基础错误 | 高 | 高 | NGS 专属工具库；system prompt 注入领域知识；领域专家 review 每个自动生成 Skill 草稿 |
| R2 | Context Window 在长实验（50+ 轮）中膨胀 | 高 | 高 | server-side compaction；`clear_tool_uses_20250919` beta；每轮立即持久化 SQLite |
| R3 | 记忆污染：坏经验被错误提炼并复用 | 中 | 高 | 置信度标签（`source=agent/notebook/paper`）；冲突标记 `needs_review`；Streamlit 人工审核界面 |
| R4 | ipynb 格式不统一导致解析质量参差 | 中 | 中 | **强制人工审核**（Skill 草稿确认后才写入）；推荐 notebook 结构规范 |
| R5 | License 合规（GPL-3.0 / CC BY-NC） | 低 | 高 | NBI 仅设计参考；AutoML-Agent 完全排除 |
| R6 | mem0 metadata 丢失（Issue #5160） | 中 | 高 | insert-only 模式；自建 metadata 索引层；关键字段不依赖 mem0 metadata |
| R7 | AIDE fork 维护成本超预期（社区活跃度低） | 中 | 中 | 优先修复模型路由层；将探索逻辑与 harness 解耦；建立内部维护能力 |
| R8 | 开发工作量低估（当前 38-57 人天） | 中 | 中 | 按 10-12 周规划（20% buffer）；容易低估项：路由修复、mem0 膨胀、NGS 工具库、Skill 初始库 |

### 13.2 开放问题（Open Questions）

继承自 `06-架构基线决策.md`：

| # | 问题 | 当前倾向 | 决策时机 |
|---|------|---------|---------|
| OQ1 | mem0 metadata 丢失长期方案：A 定期清理 / B MongoDB / C 自建索引层 | Phase 2 先上 A+C | Phase 2 启动时 |
| OQ2 | AIDE 模型路由修复：A 扩展 regex / B 配置化映射表 | Phase 1 用 A | Phase 1 第一周 |
| OQ3 | OpenFE NGS 高维数据内存问题：A Agent 层限制 / B 自研算子 / C 放弃 | Phase 1 跳过，Phase 3 评估 | Phase 3 启动时 |
| OQ4 | MLflow 本地部署：A 继续用 / B 自研极简追踪层 | Phase 1 用 A | Phase 4 评估点 |
| OQ5 | NGS 领域知识注入：A system prompt / B 工具库 / C 两者结合 | Phase 1 用 A，Phase 2 开始 B | Phase 2 启动时 |

新增产品级 OQ：

| # | 问题 | 影响范围 | 决策时机 |
|---|------|---------|---------|
| OQ6 | muyu-search 触发策略：自动触发（用户指令模糊时）vs 显式触发？自动触发引入 2-5s 延迟 | Phase 3 US5 实现 | Phase 3 设计时 |
| OQ7 | Phase 1 CLI 阶段 Skill 草稿确认形式：terminal Y/N，还是等 Phase 2 Streamlit UI？ | Phase 1 Skill 生命周期 | Phase 1 第二周 |
| OQ8 | 初始 Skill 库由谁编写？领域专家介入时间点和配合形式？Phase 2 需 3-5 人天 | Phase 2 交付质量 | Phase 2 启动前 |
| OQ9 | 实验中断恢复粒度：SQLite 最后一条记录为断点，还是 AIDE 树节点为断点？影响 Phase 1 SQLite schema 设计 | Phase 1 schema | Phase 1 第一周 |

---

## 14 里程碑 / 时间计划 · Milestones

> 基准：1 名全职高级 Python 工程师；按 10-12 周规划（含 20% buffer）。

### 14.1 Phase 计划

| Phase | 时间 | 目标 | 关键交付物 | 验收里程碑 |
|-------|------|------|----------|----------|
| **Phase 1** | 第 1-2 周 | MVP — CLI 探索可用 | AIDE fork；Bash 训练调用；SQLite 最小 schema；PreToolUse hooks；CLI 入口 | 完成一次完整探索循环（≥ 10 轮，结果写入 SQLite）✓ |
| **Phase 2** | 第 3-4 周 | 记忆 + Skill | mem0 insert-only + metadata 索引层；MLflow autolog；初始 NGS Skill 库；Streamlit 基础 UI | 能从历史经验检索相关结论并注入 Agent ✓ |
| **Phase 3** | 第 5-6 周 | 完整输入管道 | AIDE 路由修复（OQ2 方案 B）；ipynb 解析管道；子 agent 并行探索；Streamlit 记忆库界面 | 全部 4 种模式（探索/检索/Skill/交互）均可运行 ✓ |
| **Phase 4** | 第 7-8 周 | 工具库 + 硬化 | OpenFE/Featuretools 封装 + 内存限制；NGS 工具库（pysam/pyranges/biopython）；错误恢复 | 工具链完整，可无人值守运行 48h ✓ |
| **Phase 5** | 第 9-10 周 | 生产硬化 | 甲基化特征接口预留；supervisord；Skill 自动生成完整流程 | 生产可用，所有 OQ 有明确决策 ✓ |

### 14.2 关键决策时间节点

| 日期 | 事项 |
|------|------|
| Phase 1 第一周 | OQ2（AIDE 路由修复方案）、OQ9（中断恢复粒度）决策 |
| Phase 1 第二周 | OQ7（Skill 草稿确认形式）决策 |
| Phase 2 启动前 | OQ8（领域专家资源确认）、OQ1（mem0 长期方案）决策 |
| Phase 2 启动时 | OQ5（NGS 知识注入方式）决策 |
| Phase 3 设计时 | OQ6（muyu-search 触发策略）决策 |
| Phase 3 启动时 | OQ3（OpenFE 内存问题处理方式）决策 |
| Phase 4 评估点 | OQ4（MLflow 继续 vs 自研追踪层）决策 |

---

## 下一步

本 PRD 已完成全量 14 章撰写（基于 brainstorming 收敛结果 + specs/research/ 全量调研）。

继续走 Step 4 技术方案设计：
- 使用 Spec-kit 或 `/plan` 命令基于本 PRD 生成 `specs/plan.md`（架构 / 数据模型 / API 契约 / 部署方案）
- 或基于本 PRD 启动 Phase 1 任务拆解：AIDE fork + SQLite schema + PreToolUse hooks

关注点：Phase 1 的 OQ2（路由修复）和 OQ9（中断恢复粒度）是 schema 设计的前置决策，建议 **Phase 1 第一周内确定**。

---

*PRD 来源：`docs/superpowers/specs/2026-05-22-mvp-prd-inputs.md` + `specs/research/` 全量调研文件（01-06）*
*架构基线：`specs/research/06-架构基线决策.md`（已锁定，不在本文重开）*

---

## 15 v0.2 需求澄清补丁 · Requirement Clarification Patch

> 日期：2026-05-25
> 状态：Approved for downstream plan/tasks update
> 目的：将输入理解、多运行模式、Skill 沉淀、调研工具、评估终止条件补齐为可实现约束。

### 15.1 标准输入理解：自动探查 + 苏格拉底式澄清

输入不再假设为单一标准 CSV。用户可以提供一个路径，路径下可能包含一个或多个特征矩阵、分组标签、训练集、测试集或说明文件。

系统先自动探查文件，再通过苏格拉底式提问确认关键规范：

| 需要确认的问题 | 典型确认内容 |
|---------------|-------------|
| 特征矩阵在哪里 | 文件路径、sheet、分隔符、样本 ID 列、特征列范围 |
| 标签在哪里 | 单独标签文件或矩阵内标签列、标签列名、阳性/阴性编码 |
| 数据是否已划分 | 已有 train/test/validation，或需要按比例随机划分 |
| 是否使用测试集指导性能 | 有独立测试集则最终参考测试集；无测试集则参考训练集 k-fold 验证均值 |
| 是否需要验证集 | 默认不单独划验证集，统一使用训练集 k-fold；除非用户明确要求 |
| 标准化输出 | 生成项目标准输入：特征数据 + 样本标签 + 可选测试集 + `dataset_manifest` |

澄清问题应一次只问一个关键阻塞点。若自动探查置信度足够高，可向用户给出确认式问题，而不是开放式询问。

### 15.2 运行模式重新定义

| 模式 | 触发 | Agent 行为 | 终点 |
|------|------|------------|------|
| 数据标准化模式 | 用户指定路径或文件 | 探查文件、苏格拉底式确认、生成标准输入 manifest | 标准输入可用于训练 |
| 特征探索模式 | 用户要求探索，未指定固定 Skill | 参考记忆经验库与 Skill 库，优先探索未完成方向 | 达标、到达最大轮数、超时或用户停止 |
| 复现模式 | 用户指定 Skill | 严格按 Skill 范式训练、验证并输出模型 | 完成一次可复现实验 |
| 交互验证模式 | 用户提出验证方向 | 执行用户指定方向，每轮返回结果后等待下一条指令 | 用户继续、停止或转 Skill 沉淀 |
| Skill 沉淀模式 | 用户触发沉淀 | 从 ipynb 或当前最优探索结果生成 Skill 草稿 | darwin-skill 迭代后进入人工审核 |
| 文献/项目调研模式 | 用户指定文献/项目，或启动自动调研 | 使用本地 muyu-search-mcp 调研方法学、代码与近半年算法进展 | 知识进入语义知识库 |

### 15.3 特征工程优先级与顺序

特征探索模式中，探索资源分配原则为：

- 90% 放在特征工程。
- 特征工程中，标准化、二元化、缺失值处理等预处理策略在特征子集选择之前执行。
- 特征子集选择包含低方差过滤、相关性过滤、统计检验筛选、模型重要性筛选、递归选择、稳定性选择等过滤或选择方式。
- 10% 放在模型与超参数优化，且应在特征工程方向相对稳定后再启动。

### 15.4 Skill 沉淀策略

Skill 沉淀必须同时满足三层约束：

1. 参考记忆经验库：只从经过实验验证、来源明确、性能记录完整的经验中提炼。
2. 严格遵循 `skill-creator` 范式：Skill 必须包含标准 YAML frontmatter（`name`、`description`）、简洁 SKILL.md、必要时使用 `scripts/` 或 `references/` 分层资源，并通过基础校验。
3. 使用 `alchaincyf/darwin-skill` 思路进行迭代：对 SKILL.md 进行评估、改进、测试、保留或回滚；只有迭代后版本进入人工审核。

Skill 沉淀来源：

- 用户指定 `.ipynb` 文件：解析 notebook 代码、参数、结论，生成 Skill 草稿。
- 当前探索/交互结果：识别当前最优模型训练范式，生成 Skill 草稿。

未通过人工审核的 Skill 只能作为 `SkillCandidate`，不得进入正式 Skill 库。

### 15.5 文献与项目调研

调研能力统一使用 `/Users/zhongxianyu/Desktop/muyu-search-mcp` 的方法：

- 简单事实：可用低复杂度搜索。
- 方法学综述、项目分析、近半年自动调研：必须走 muyu-search-mcp 的规划状态机。
- 指定文献或项目时，应分析方法学原理、训练流程、特征工程、模型结构、评估指标、可迁移代码片段。
- 自动调研模式聚焦近半年机器学习在特征工程与模型训练上的前沿算法。

调研结果默认进入语义知识库，不自动进入 Skill 库。只有经实验验证或人工确认后，才可生成 SkillCandidate。

### 15.6 训练评估与终止条件

所有运行模式必须配置终止条件：

- 达到预期性能。
- 达到最大迭代次数。
- 达到最长运行时间。
- 连续 N 轮无有效提升。
- 用户手动停止。

性能指导指标支持：

- AUC
- Accuracy
- 指定特异性下的灵敏度

评估规则：

- 所有训练集均采用 k-fold 训练，`k` 可配置。
- 若有独立测试集，最终指导性能参考测试集。
- 若无独立测试集，指导性能参考训练集 k-fold 验证平均性能。
- 阈值不得由测试集选择。
- 阈值由训练集 k-fold 各验证折预测结果拼接后的数据确定。
- 阈值策略支持最优 Youden index 或目标特异性下最大灵敏度。

### 15.7 前端可观测性要求

每轮探索必须保留结构化 trace，供后续前端展示：

| 字段 | 含义 |
|------|------|
| `round_id` | 轮次 ID |
| `mode` | 运行模式 |
| `exploration_direction` | 本轮探索方向 |
| `preprocessing_strategy` | 标准化、二元化、缺失值等策略 |
| `feature_subset_strategy` | 特征子集选择策略 |
| `model_type` | 模型类型 |
| `params_json` | 参数 |
| `cv_metrics_json` | k-fold 验证指标 |
| `threshold_policy` | 阈值策略 |
| `selected_threshold` | 训练集验证预测确定的阈值 |
| `test_metrics_json` | 测试集指标，可为空 |
| `status` | completed / failed / timeout / stopped |
| `llm_rationale_summary` | LLM 对本轮方向的简要理由 |
