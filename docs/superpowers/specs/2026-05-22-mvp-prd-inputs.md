# MLagent_v2 MVP PRD 输入项

> 生成日期：2026-05-22
> 来源：基于 specs/research/ 全量调研文件（01-06）的 Brainstorming 收敛输出
> 架构基线：已锁定（见 specs/research/06-架构基线决策.md），本文不重开架构讨论
> 定位：**内部工具**，团队自用，不对外分发或商业化
> 用途：作为 PRD 撰写的直接输入

---

## Q1 业务目标 + 产品目标 + Non-Goals

### 业务目标（内部效率型）

- 将研究员手动调参时间从"每次实验 1-2 天摸索"压缩到"一次设定 + Agent 自动跑完"
- 将成功实验范式沉淀为 Skill，消除跨项目重复摸索的沉没成本
- 让历史实验经验可语义检索，而不是散落在各自的 notebook 里

### 产品目标（MVP）

能在团队 NGS 特征矩阵上完成一次完整探索循环（≥ 10 轮，AUC 自动评估，结果写入 SQLite），全程无人工干预。

### Non-Goals（明确不做）

- 不做多用户支持、登录 / 权限系统
- 不做原始测序数据处理（BAM/VCF 解析），输入边界是预处理后的特征矩阵 CSV
- 不做模型推理部署（只做训练和特征选择）
- 不做深度学习（只做 sklearn/XGBoost 级别的经典 ML）
- 不做商业化、计费、SaaS 分发
- 不做实时流数据，只做批处理

---

## Q2 用户画像 + 反画像

### 主画像 A：生物信息工程师（主要用户）

- 每周跑 3-5 次 NGS ML 实验，熟悉 Python 和 sklearn
- 痛点：调参靠手动记录，换数据集后经验无法复用，notebook 里的结论难以检索
- 行为偏好：用 CLI 和 Jupyter，可接受新工具，但不希望配置复杂

### 主画像 B：PI / 高级研究员（次要用户）

- 看了文献想复现某个特征工程策略，但实现成本高
- 痛点：ML 实现能力有限，需要引导式入口
- 行为偏好：偏向 Web UI，需要可视化实验结果

### 反画像（不服务）

- 纯湿实验研究员（不接触计算数据）
- 需要 GPU 深度学习的 AI 研究员（超出 MVP 技术范围）
- 外部商业用户（架构决策已明确排除）

---

## Q3 核心用户故事（INVEST 格式）

**US1 — 探索实验**（Phase 1 核心）
> As a bioinformatician, I want to hand the agent a feature matrix + target metric + round budget, so that it automatically explores feature-model-hyperparameter combinations and returns the best configuration without manual iteration.

**US2 — 经验检索**（Phase 2）
> As a bioinformatician, I want to query past experiment outcomes by semantic similarity (e.g., "methylation features for CNS classification"), so that I don't repeat work that already failed or succeeded.

**US3 — Skill 范式复用**（Phase 2）
> As a bioinformatician, I want to invoke a proven pipeline Skill on a new dataset, so that a successful configuration from a previous project is reproduced without manual reconstruction.

**US4 — ipynb 导入**（Phase 3）
> As a researcher, I want to upload a historical notebook and get a Skill draft extracted automatically, so that documented experiments enter the team's reusable knowledge base.

**US5 — 交互式方法探索**（Phase 3）
> As a researcher with a new hypothesis or methodological idea, I want to describe a direction to the agent in natural language (e.g., "explore whether promoter-region CpG features outperform gene-body features for this tumor type"), so that the agent researches the approach, executes targeted experiments, and quickly reports whether the hypothesis holds — without me implementing it myself.

---

## Q4 MVP 功能列表 + Out-of-Scope

### Must-have（Phase 1，第 1-2 周）

| 功能 | 来源 | 改造成本 |
|------|------|---------|
| Claude Agent SDK 主循环（ReAct） | SDK 原生，零成本 | — |
| PreToolUse safety hooks | SDK 原生，零成本 | — |
| AIDE 树搜索探索引擎 | Fork MIT，harness 替换 + 路由修复 | 15-20 人天 |
| sklearn / XGBoost 训练脚本调用（Bash） | pip install，零成本 | — |
| SQLite 情节记忆（最小 schema） | 标准库，零成本 | — |
| CLI 交互入口 | Claude Code CLI，零成本 | — |

### Should（Phase 2，第 3-4 周）

| 功能 | 来源 | 改造成本 |
|------|------|---------|
| mem0 语义记忆（insert-only 适配）+ metadata 索引层 | pip install，需适配 | 3-5 人天 |
| MLflow autolog 实验追踪 | pip install | 1-2 人天 |
| 初始 NGS Skill 库（手工编写 1-2 个） | 原生 SKILL.md，需领域专家 | 3-5 人天 |
| Streamlit 基础 UI（任务监控 + 实验列表） | 自建 | 5-8 人天 |

### Could（Phase 3，第 5-6 周）

| 功能 | 来源 |
|------|------|
| AIDE 模型路由配置化重写（OQ2 方案 B） | Fork 改造 |
| ipynb → SKILL.md 解析管道 | 自建，参考 Jupyter AI |
| 文献 URL 导入（→ ChromaDB） | 自建，参考 RD-Agent |
| 子 agent 并行超参数探索 | SDK 原生 Agent 工具 |
| muyu-search 工具接入（交互式方法探索） | MCP 已配置，加入工具列表即可 |
| Streamlit 记忆库浏览界面 | 自建 |

### Out-of-Scope（Won't，本轮不做）

- OpenFE / Featuretools / pysam / pyranges 工具库（Phase 4）
- Skill 置信度回流 / 自动进化（架构缺口，需另立设计）
- Docker 沙箱 / supervisord / Qdrant 升级（Phase 4-5）
- 甲基化特征自优化二次接口（Phase 5 预留）
- 多用户支持 / 权限系统（Non-Goal）

---

## Q5 核心功能关键边界条件

### AIDE 探索引擎

| 场景 | 处理方式 |
|------|---------|
| 输入 CSV 含缺失值 | median imputation；插补率 > 30% 时写入实验元数据警告 |
| 单轮训练 OOM | 捕获 MemoryError，标记 `status=oom`，跳过该节点，继续循环 |
| 单轮训练超时（> 30 min） | subprocess 超时终止，标记 `status=timeout`，继续探索 |
| 上下文膨胀（50 轮后） | 每轮立即持久化 SQLite，触发 server-side compaction，不依赖 context 记忆 |
| AUC 连续 10 轮提升 < 0.002 | Agent 自动切换策略或早停（system prompt 规则） |

### 记忆层

| 场景 | 处理方式 |
|------|---------|
| mem0 metadata 静默丢失 | insert-only + 自建 metadata 索引层，关键字段不依赖 mem0 metadata |
| ChromaDB 写入失败 | 降级为纯 SQLite，标记 `memory_sync=pending`，下次启动重试 |
| 新旧经验结论矛盾 | 标记 `needs_review=true`，不自动覆盖，用户手动处理 |

### Skill 系统

| 场景 | 处理方式 |
|------|---------|
| 无匹配 Skill | 使用 system prompt 默认探索流程，不报错 |
| Skill 草稿质量差 | 展示给用户确认，未确认不写入 `.claude/skills/` |
| Skill 文件损坏（YAML 解析失败） | SDK 跳过该 Skill，记录警告日志，不影响其他 Skill |

### 安全边界（PreToolUse hook）

禁止：`rm -rf`、`chmod 777`、`curl`（外网请求）、写入 `/etc/` 或 `~/.ssh/`
允许：仅在 `experiments/` 指定目录内写文件

---

## Q6 非功能需求（数字）

### 性能

| 指标 | 要求 | 依据 |
|------|------|------|
| 单轮训练（1000 样本 × 500 特征，XGBoost） | < 5 分钟 | 8 核 CPU，16GB RAM，`n_jobs=-1` |
| mem0 语义检索延迟 | < 2 秒 | ChromaDB，< 1000 条记忆 |
| SQLite 查询（< 500 条记录） | < 0.5 秒 | 标准库，无大表 JOIN |
| Streamlit UI 初始加载 | < 3 秒 | 实验列表 < 500 条 |

### 可靠性

| 指标 | 要求 |
|------|------|
| 实验中断恢复 | 从 SQLite 最后一条 `status=completed` 记录继续，不从零重跑 |
| 崩溃时数据丢失 | 0 条已完成实验记录丢失（每轮结束立即落盘） |
| mem0 降级 | ChromaDB 不可用时自动降级为纯 SQLite，不阻塞探索主循环 |

### 安全 / 合规

| 约束 | 要求 |
|------|------|
| NGS 数据隔离 | 数据不进入 Anthropic API context |
| 密钥管理 | API Key 仅通过环境变量传入，禁止硬编码 |
| 本地部署 | 数据不离开用户机器 |

---

## Q7 验收标准（Given / When / Then）

**US1 — 探索实验**
- **Given** 用户提供 `features.csv`（≥ 100 样本，≥ 100 特征）、目标指标 AUC、最大轮数 ≥ 10
- **When** 执行探索命令
- **Then** Agent 完成 ≥ 10 轮，每轮结果写入 SQLite，输出最优配置摘要，全程无人工干预；最优 AUC 高于 baseline（默认 XGBoost 配置、无 Skill 注入的单轮 AUC）

**US2 — 经验检索**
- **Given** SQLite 中已有 ≥ 5 条历史实验，ChromaDB 有对应语义摘要
- **When** 用户输入自然语言查询
- **Then** 返回 top-3 历史实验摘要（含 AUC、特征数量、时间戳），延迟 < 2 秒

**US3 — Skill 范式复用**
- **Given** `.claude/skills/` 中存在至少 1 个有效 Skill
- **When** 用户描述与该 Skill description 语义相似的任务
- **Then** Agent 自动加载并执行 Skill，结果写入 MLflow 和 SQLite，无需用户指定 Skill 名

**US4 — ipynb 导入**
- **Given** 用户上传含特征选择代码 + 结论 Markdown 的 `.ipynb`
- **When** 触发解析管道
- **Then** 输出 SKILL.md 草稿（含 name、description、标准流程），等待用户确认；未确认前不写入

**US5 — 交互式方法探索**
- **Given** 研究员有一个新的方法学假设
- **When** 用户用自然语言描述该假设
- **Then** Agent 理解方向（必要时调用 muyu-search），规划并执行 ≥ 3 轮定向探索，输出结论摘要（假设是否成立 + 支撑 AUC 数据）

---

## Q8 优先级（MoSCoW）

### Must（Phase 1，第 1-2 周）
- AIDE fork + harness 替换（Claude Agent SDK）+ 路由修复（OQ2 方案 A）
- sklearn / XGBoost Bash 工具调用
- SQLite 情节记忆最小 schema
- PreToolUse safety hooks
- CLI 交互入口

### Should（Phase 2，第 3-4 周）
- mem0 insert-only 适配 + metadata 索引层
- MLflow autolog 集成
- 初始 NGS Skill 库（1-2 个，需领域专家配合）
- Streamlit 基础 UI（任务监控 + 实验列表）

### Could（Phase 3，第 5-6 周）
- ipynb → SKILL.md 解析管道
- 文献 URL 导入
- 子 agent 并行超参数探索
- muyu-search 工具接入（交互式方法探索）
- Streamlit 记忆库浏览界面

### Won't（本轮明确不做）
- OpenFE / Featuretools / pysam / pyranges 工具库
- Skill 置信度回流 / 自动进化
- Docker 沙箱 / supervisord / Qdrant 升级
- 多用户支持 / 权限系统

---

## Q9 北极星指标 + 关停线

### 北极星指标

**每周通过 Agent 完成的有效探索实验数**
- 定义：一次探索完成 ≥ 10 轮，最优 AUC 高于 baseline（默认 XGBoost 配置无 Skill 注入的单轮 AUC），结果写入 SQLite
- 目标：上线 4 周内稳定达到 ≥ 3 次 / 周

辅助指标：
- Skill 库月净增数（衡量经验沉淀速度）
- 经验命中率（检索到历史相关实验并被 Agent 实际引用的比例）

### 关停线

| 信号 | 阈值 | 含义 |
|------|------|------|
| AUC 达成率 | 8 周内 < 50% | 探索引擎或领域知识注入有根本问题 |
| AIDE fork 维护成本 | 超过 +13 人天预留缓冲 | 评估自研探索引擎可行性 |
| mem0 存储膨胀 | insert-only 模式 1 个月 > 10GB | 触发 OQ1 决策点 |
| ChromaDB 检索退化 | 1K 条记忆后语义相关性明显下降 | 触发 Qdrant 迁移评估 |

---

## Q10 Open Questions

### 继承自 06-架构基线决策（全部保留）

| # | 问题 | 当前倾向 | 决策时机 |
|---|------|---------|---------|
| OQ1 | mem0 metadata 丢失长期方案：A 定期清理 / B MongoDB / C 自建索引层 | Phase 2 先上 A+C | Phase 2 启动时 |
| OQ2 | AIDE 模型路由修复：A 扩展 regex / B 配置化映射表 | Phase 1 用 A | Phase 1 第一周 |
| OQ3 | OpenFE NGS 高维数据内存问题：A Agent 层限制 / B 自研算子 / C 放弃 | Phase 1 跳过，Phase 3 评估 B | Phase 3 启动时 |
| OQ4 | MLflow 本地部署：A 继续用 / B 自研极简追踪层 | Phase 1 用 A | Phase 4 评估点 |
| OQ5 | NGS 领域知识注入：A system prompt / B 工具库 / C 两者结合 | Phase 1 用 A，Phase 2 开始 B | Phase 2 启动时 |

### 新增产品级 OQ

| # | 问题 | 影响范围 | 决策时机 |
|---|------|---------|---------|
| OQ6 | muyu-search 触发策略：自动触发（用户指令模糊时）vs 显式触发？自动触发引入 2-5s 延迟 | Phase 3 US5 实现 | Phase 3 设计时 |
| OQ7 | Phase 1 CLI 阶段 Skill 草稿确认形式：terminal Y/N，还是等 Phase 2 Streamlit UI？ | Phase 1 Skill 生命周期 | Phase 1 第二周 |
| OQ8 | 初始 Skill 库由谁编写？领域专家介入时间点和配合形式？Phase 2 需 3-5 人天领域专家 | Phase 2 交付质量 | Phase 2 启动前 |
| OQ9 | 实验中断恢复粒度：SQLite 最后一条记录为断点，还是 AIDE 树节点为断点？影响 Phase 1 SQLite schema 设计 | Phase 1 schema | Phase 1 第一周 |

---

## Q11 依赖与约束（产品级）

### 外部 API 依赖

| 依赖 | 现状 | 风险 |
|------|------|------|
| Anthropic API（Sonnet 4.6 + Haiku 4.5） | 按量付费，无硬上限 | 多子 agent 高频探索时成本需监控；建议设置每日消费告警 |
| Tavily API（muyu-search MCP 搜索后端） | Key 已在 `.mcp.json`，免费配额 | Phase 3 上线前确认免费配额满足内部使用量 |

### 数据安全约束

| 约束 | 说明 |
|------|------|
| NGS 基因组数据隐私 | 数据不进入 Anthropic API context；需团队确认数据使用协议与此架构兼容 |
| 本地部署隔离 | muyu-search 仅传输查询文本，不传输实验数据 |

### 人力约束

| 角色 | 投入 | 何时需要 |
|------|------|---------|
| 高级 Python 工程师 | 全职 8-10 周 | Phase 1 起 |
| NGS 领域专家 | 3-5 人天 | Phase 2 启动时（Skill 编写 + 生物学合理性 review） |

### 平台硬约束

| 约束 | 要求 |
|------|------|
| 硬件最低配置 | 16GB RAM + 8 核 CPU |
| 操作系统 | macOS / Linux（Windows 不在支持范围） |
| Python 版本 | 3.10+（AIDE + mem0 + ChromaDB 兼容要求） |

---

*本文档由 Brainstorming Skill 收敛自 specs/research/ 全量调研文件，作为 PRD 撰写的直接输入。*
*架构基线参考：specs/research/06-架构基线决策.md*
