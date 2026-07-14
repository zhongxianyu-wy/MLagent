# 集成评估报告：NGS ML 训练 AI 助手多项目复合工程可行性

> 评估角色：集成评估师（中立）
> 评估日期：2026-05-21
> 评估范围：8 个候选开源项目的组合集成可行性
> 数据来源：GitHub 原始 pyproject.toml / setup.py / requirements.txt + 已有调研文档

---

## 一、候选项目依赖基线（原始数据）

| 项目 | License | Stars | Python | numpy | pandas | scikit-learn | scipy | 关键约束 |
|------|---------|-------|--------|-------|--------|--------------|-------|----------|
| **AIDE** | MIT | 1,285 | >=3.10 | ==1.26.2 | ==2.1.4 | ==1.5.0 | ==1.11.4 | openai>=1.69, anthropic>=0.20, streamlit~=1.54 |
| **CAAFE** | Apache-2.0 | 192 | >=3.7 | 未显式约束 | 未显式约束 | 未显式约束 | 未显式约束 | openai==0.28, tabpfn, 无版本锁 |
| **mem0** | Apache-2.0 | 56,310 | >=3.10,<4.0 | 未显式约束 | 未显式约束 | 未显式约束 | 未显式约束 | qdrant-client>=1.12, pydantic>=2.7.3, sqlalchemy>=2.0.31 |
| **MLflow** | Apache-2.0 | 26,039 | >=3.10 | <3 | <3 | <2 | <2 | pydantic<3,>=2.0; Flask<4; protobuf<8 |
| **Notebook Intelligence** | GPL-3.0 | 301 | >=3.10 | 未显式约束 | 未显式约束 | 未显式约束 | 未显式约束 | litellm>=1.83.7, mcp>=1.27, claude-agent-sdk, anthropic>=0.22.1 |
| **Featuretools** | BSD-3 | 7,648 | >=3.9,<4 | >=1.25.0,<2.0 | >=2.0.0 | 未显式约束 | >=1.10.0 | woodwork>=0.28, cloudpickle>=1.5 |
| **OpenFE** | MIT | 870 | >=3.6 | >=1.19.3 | >=1.1.5 | >=0.24.2 | >=1.5.4 | lightgbm>=3.3.2 |
| **Jupyter AI** | BSD-3 | 4,237 | >=3.9 | 未显式约束 | 未显式约束 | 未显式约束 | 未显式约束 | jupyterlab>=4.0, 大量 jupyter 生态子包 |

### 依赖冲突矩阵（关键版本硬约束）

```
numpy:
  AIDE: ==1.26.2          ← 硬锁
  MLflow: <3               ← 上限
  Featuretools: >=1.25,<2  ← 范围
  OpenFE: >=1.19.3         ← 下限
  → 交集: 1.26.2 满足全部 (1.26.2 >=1.25, <2, <3, >=1.19.3) ✓

pandas:
  AIDE: ==2.1.4            ← 硬锁
  MLflow: <3               ← 上限
  Featuretools: >=2.0.0    ← 下限
  OpenFE: >=1.1.5          ← 下限
  → 交集: 2.1.4 满足全部 (2.1.4 >=2.0, <3, >=1.1.5) ✓

scikit-learn:
  AIDE: ==1.5.0            ← 硬锁
  MLflow: <2               ← 上限
  OpenFE: >=0.24.2         ← 下限
  Featuretools: 无约束
  → 交集: 1.5.0 满足全部 (1.5.0 <2, >=0.24.2) ✓

scipy:
  AIDE: ==1.11.4           ← 硬锁
  MLflow: <2               ← 上限
  Featuretools: >=1.10.0   ← 下限
  OpenFE: >=1.5.4          ← 下限
  → 交集: 1.11.4 满足全部 (1.11.4 <2, >=1.10, >=1.5.4) ✓

pydantic:
  mem0: >=2.7.3            ← v2 强制
  MLflow: <3,>=2.0         ← v2 强制
  → 一致: pydantic v2 生态 ✓

openai:
  AIDE: >=1.69.0           ← v1 新 SDK
  CAAFE: ==0.28            ← v0 旧 SDK ⚠️ 冲突
  mem0: >=1.90.0           ← v1 新 SDK
  → CAAFE 的 openai==0.28 与 AIDE/mem0 的 openai>=1.69 直接冲突

python-dotenv:
  AIDE requirements.txt: 无版本
  Notebook Intelligence: litellm 硬锁 ==1.0.1, 但 NBI 已移除 fastmcp 依赖绕过
  → 可解析，无直接冲突
```

---

## 二、逐对 / 逐组组合评估

### 组合 1：AIDE + mem0

| 维度 | 评估 |
|------|------|
| **集成边界** | AIDE 的 `aide/run.py` 主循环中，每轮实验结束后调用 mem0 的 `add()` API 写入经验；mem0 作为独立 Python 包通过函数调用集成，非进程间通信 |
| **数据流冲突** | AIDE 内部数据结构（ExperimentResult 等 dataclass）与 mem0 的 `Memory` 接口（dict/message 列表）需要一层 adapter：将 AIDE 的节点结果序列化为 mem0 的 `messages` 格式。adapter 约 50-80 行 |
| **版本/依赖冲突** | Python 均 >=3.10，无冲突。AIDE 的 pydantic 未显式约束，mem0 要求 >=2.7.3；AIDE 使用 dataclasses_json，与 pydantic v2 无冲突。✓ 兼容 |
| **总改造成本** | 低：AIDE fork 后，在 `tree_search.py` 的节点扩展/剪枝逻辑后插入 mem0 调用即可。约 1-2 人天 |
| **运维复杂度** | 低：mem0 pip install 即可，无需额外 infra（若用 ChromaDB 替代 Qdrant，则零配置） |
| **推荐分** | **9/10** |

**结论**：AIDE 无记忆系统，mem0 是插件式记忆层，两者天然互补。集成点清晰，改造成本低。

---

### 组合 2：AIDE + MLflow

| 维度 | 评估 |
|------|------|
| **集成边界** | AIDE 的评估循环（`evaluate_solution`）中，每轮实验调用 `mlflow.log_params()` / `mlflow.log_metrics()`；MLflow 作为 Python 库直接调用，或作为 MCP server 通过 Agent SDK 工具调用 |
| **数据流冲突** | AIDE 的指标输出是 Python dict（如 `{"auc": 0.88}`），MLflow 的 log_metrics 接收 dict，几乎无需 adapter。AIDE 的代码生成结果可写入 MLflow artifacts。数据模型高度对齐 |
| **版本/依赖冲突** | numpy/pandas/scipy/scikit-learn 交集均满足（见基线表）。MLflow 的 pydantic<3,>=2 与 AIDE 无冲突。✓ 兼容 |
| **总改造成本** | 极低：在 AIDE 的 benchmark 函数中插入 3-5 行 MLflow 调用即可。约 0.5 人天 |
| **运维复杂度** | 低：`mlflow ui --port 5000` 本地零配置运行，无需数据库 server |
| **推荐分** | **9/10** |

**结论**：AIDE 记录实验结果 + MLflow 结构化追踪 = 完美互补。数据流天然对齐。

---

### 组合 3：mem0 + MLflow

| 维度 | 评估 |
|------|------|
| **集成边界** | mem0 负责语义记忆（经验知识检索），MLflow 负责结构化实验追踪（参数/指标/模型）。两者通过 SQLite 中的实验 ID 关联：MLflow 的 run_id 作为 mem0 metadata 中的 `experiment_id` |
| **数据流冲突** | 无冲突——两者存储不同维度的数据。mem0 存语义向量（经验总结），MLflow 存标量指标和文件 artifacts。联合查询时先查 mem0 语义相似度，再用返回的 experiment_id 查 MLflow 精确指标 |
| **版本/依赖冲突** | mem0 的 sqlalchemy>=2.0.31 与 MLflow 的 sqlalchemy<3,>=1.4.0 兼容（2.0 在 [1.4, 3) 区间内）。✓ 兼容 |
| **总改造成本** | 低：设计联合查询接口（先语义后精确）约 1 人天 |
| **运维复杂度** | 低：ChromaDB（mem0 默认）本地文件存储 + MLflow 本地文件存储，无 server 依赖 |
| **推荐分** | **9/10** |

**结论**：mem0（语义）+ MLflow（结构化）是调研文档中已论证的最佳记忆双层架构，无技术冲突。

---

### 组合 4：AIDE + mem0 + MLflow（Layer 2+3 核心组合）

| 维度 | 评估 |
|------|------|
| **集成边界** | AIDE 探索引擎 → 每轮结果同时写入 mem0（语义经验）和 MLflow（结构化指标）。三者形成「探索-记录-检索」闭环 |
| **数据流冲突** | 统一实验 ID 体系：AIDE 的 tree node ID → 映射为 MLflow run_id + mem0 memory_id。需要一层轻量 id-mapping adapter（约 30 行） |
| **版本/依赖冲突** | Python >=3.10，numpy/pandas/scipy/scikit-learn 交集均满足（1.26.2 / 2.1.4 / 1.5.0 / 1.11.4）。pydantic v2 一致。✓ 完全兼容 |
| **总改造成本** | 低：AIDE fork 后插入两处调用（mem0 + MLflow）+ id-mapping，约 2-3 人天 |
| **运维复杂度** | 低：全本地文件存储，无外部 server |
| **推荐分** | **9/10** |

**结论**：这是目标架构的核心三角，三者技术栈高度兼容，集成边界清晰，是风险最低的组合。

---

### 组合 5：AIDE + CAAFE

| 维度 | 评估 |
|------|------|
| **集成边界** | CAAFE 作为 AIDE 探索树中的一个「特征工程子节点」工具被调用：AIDE 的 agent 在需要特征生成时，调用 CAAFE 的 `generate_features()` API |
| **数据流冲突** | CAAFE 输入为 pandas DataFrame + 数据集描述字符串，输出为增强后的 DataFrame + 特征解释。与 AIDE 的数据流兼容。但 CAAFE 的 `openai==0.28` 与 AIDE 的 `openai>=1.69` 直接冲突 |
| **版本/依赖冲突** | **严重冲突**：CAAFE 硬锁 `openai==0.28`（旧 SDK），AIDE 要求 `openai>=1.69`（新 SDK）。同一环境无法共存两个 major 版本的 openai 包。OpenAI v0 与 v1 API 完全不兼容 |
| **总改造成本** | 高：必须二选一——(a) 改造 CAAFE 升级至 openai>=1.69（需重写其 LLM 调用层），或 (b) 将 CAAFE 隔离在独立虚拟环境/子进程中通过 IPC 调用。方案 (a) 约 3-5 人天，方案 (b) 约 2-3 人天但增加运维复杂度 |
| **运维复杂度** | 中：若采用子进程隔离，需维护进程间通信协议（如通过文件或 socket 传递 DataFrame） |
| **推荐分** | **4/10** |

**结论**：openai SDK 版本硬冲突是致命问题。CAAFE 的 LLM 调用层简单（仅生成特征代码），改造成本可控，但「拆出来用」比「直接集成」更现实。建议参考其设计模式自研，而非直接集成。

---

### 组合 6：AIDE + Featuretools

| 维度 | 评估 |
|------|------|
| **集成边界** | Featuretools 作为 AIDE agent 可调用的工具函数：在探索树的「特征工程」分支，agent 调用 `ft.dfs()` 生成关系型特征 |
| **数据流冲突** | Featuretools 需要 EntitySet（多表关系定义），AIDE 的通用数据流是单表 DataFrame。NGS 数据需先建模为关系型结构（如 sample × gene × annotation 多表），这要求一层数据建模 adapter。若 NGS 数据保持单表矩阵形式，Featuretools 价值有限 |
| **版本/依赖冲突** | numpy: Featuretools >=1.25,<2 与 AIDE ==1.26.2 兼容。pandas: Featuretools >=2.0 与 AIDE ==2.1.4 兼容。scipy: Featuretools >=1.10 与 AIDE ==1.11.4 兼容。✓ 兼容 |
| **总改造成本** | 中：数据建模 adapter（EntitySet 构建）+ agent 调用封装，约 2-3 人天。但 NGS 数据通常不是关系型，Featuretools 的 DFS 优势可能无法发挥 |
| **运维复杂度** | 低：pip install 即可 |
| **推荐分** | **6/10** |

**结论**：技术兼容，但 NGS 数据形态（单样本×高维特征矩阵）与 Featuretools 的最优场景（多表关系型数据）不匹配。作为「可选工具」集成，非核心路径。

---

### 组合 7：AIDE + OpenFE

| 维度 | 评估 |
|------|------|
| **集成边界** | OpenFE 作为 AIDE agent 可调用的工具函数：agent 在特征工程阶段调用 `openfe.transform()` 批量生成特征 |
| **数据流冲突** | OpenFE 输入输出均为 pandas DataFrame，与 AIDE 数据流完全兼容。OpenFE 的 23 种操作符生成的新特征列可直接进入 AIDE 的后续模型训练节点 |
| **版本/依赖冲突** | numpy: OpenFE >=1.19.3 与 AIDE ==1.26.2 兼容。pandas: OpenFE >=1.1.5 与 AIDE ==2.1.4 兼容。scikit-learn: OpenFE >=0.24.2 与 AIDE ==1.5.0 兼容。scipy: OpenFE >=1.5.4 与 AIDE ==1.11.4 兼容。lightgbm: OpenFE >=3.3.2，AIDE 无版本约束（requirements.txt 中未版本化）。✓ 兼容 |
| **总改造成本** | 低：OpenFE 有标准 sklearn-style API（`fit_transform`），封装为 agent 工具约 0.5-1 人天 |
| **运维复杂度** | 低：pip install 即可 |
| **推荐分** | **8/10** |

**结论**：技术完全兼容，数据流对齐，API 简洁。OpenFE 的算法驱动特征生成与 AIDE 的 LLM 驱动探索形成互补（OpenFE 做广度生成，AIDE 做深度选择）。

---

### 组合 8：mem0 + Jupyter AI

| 维度 | 评估 |
|------|------|
| **集成边界** | Jupyter AI 提供 MCP server 暴露 notebook 操作能力；mem0 作为记忆层可被 Jupyter AI 的 agent 调用。但本项目以 Claude Code CLI 为 harness，Jupyter AI 是 JupyterLab 扩展，两者运行在不同的 runtime 中 |
| **数据流冲突** | Jupyter AI 的 MCP server 输出 notebook cell 内容（JSON），mem0 接收文本/消息。需要 adapter 将 notebook JSON 提取为文本经验。nbformat 库可完成此转换 |
| **版本/依赖冲突** | Python 均 >=3.9/3.10，无冲突。Jupyter AI 的 jupyterlab 生态与 mem0 无重叠依赖。✓ 兼容 |
| **总改造成本** | 中：Jupyter AI 是完整 JupyterLab 扩展，本项目不需要其 UI 层。仅需参考其 MCP server 设计，而非直接集成。实际改造为「自研 nbformat 解析器 + mem0 写入」约 2-3 人天 |
| **运维复杂度** | 低：不直接运行 Jupyter AI，仅参考其代码 |
| **推荐分** | **5/10**（作为「设计参考」而非「直接集成」） |

**结论**：Jupyter AI 的价值在于 MCP server 设计模式参考，而非代码复用。直接集成会引入大量不必要的 JupyterLab 依赖。

---

### 组合 9：mem0 + Notebook Intelligence

| 维度 | 评估 |
|------|------|
| **集成边界** | Notebook Intelligence（NBI）直接集成 claude-agent-sdk，与 mem0 同为 Python 包，可在同一进程内共存。NBI 的 JupyterLab 扩展层可调用 mem0 API 进行记忆读写 |
| **数据流冲突** | NBI 管理 notebook 的创建/编辑/执行，mem0 管理长期记忆。两者数据流正交：NBI 产出 notebook → nbformat 解析 → mem0 存储经验 |
| **版本/依赖冲突** | NBI 依赖 `litellm>=1.83.7`，mem0 可选依赖中也有 `litellm>=1.83.7`（extras 中），版本一致。NBI 的 `mcp>=1.27` 与 mem0 无冲突。✓ 兼容 |
| **总改造成本** | 中-高：NBI 是 GPL-3.0 的 JupyterLab 扩展，代码耦合度高。本项目仅需其「Claude Code + JupyterLab 集成模式」参考，而非完整复用。提取核心集成逻辑约 3-5 人天 |
| **运维复杂度** | 中：NBI 需要 Node.js/npm 构建 JupyterLab 扩展，增加构建链复杂度 |
| **推荐分** | **5/10** |

**结论**：NBI 的 GPL-3.0 在内部使用场景下无 copyleft 风险，但其 JupyterLab 扩展架构与本项目的 Streamlit + CLI 双入口不匹配。建议「研读其代码，自研简化版 ipynb 接口」，而非直接 fork 集成。

---

### 组合 10：AIDE + Jupyter AI + Notebook Intelligence（ipynb 接口层）

| 维度 | 评估 |
|------|------|
| **集成边界** | Jupyter AI 提供 MCP server 规范，NBI 提供 Claude Code 集成先例，AIDE 需要 ipynb 导入能力。三者不直接代码集成，而是「AIDE 自研 ipynb 接口，参考后两者设计」 |
| **数据流冲突** | ipynb（JSON）→ nbformat 解析 → 结构化经验 → AIDE 记忆系统。数据流一致，无需跨项目 adapter |
| **版本/依赖冲突** | AIDE 已依赖 nbformat（requirements.txt 中列出）。Jupyter AI 和 NBI 的 jupyterlab 生态与 AIDE 无直接冲突（AIDE 不运行 JupyterLab）。✓ 兼容 |
| **总改造成本** | 中：自研 nbformat 解析器（参考 Jupyter AI/NBI 的实现模式）约 2-3 人天。无需直接集成两个项目 |
| **运维复杂度** | 低：不引入 JupyterLab 运行时 |
| **推荐分** | **7/10**（作为「设计参考组合」，非代码集成） |

**结论**：ipynb 接口的最佳路径是「自研 + 参考」，而非「集成」。Jupyter AI 和 NBI 提供的是设计模式价值，不是代码复用价值。

---

### 组合 11：Featuretools + OpenFE + CAAFE（特征工具库组合）

| 维度 | 评估 |
|------|------|
| **集成边界** | 三者均为 agent 可调用的独立工具函数，通过统一接口（如 `ToolRegistry`）注册。agent 根据任务类型选择调用哪个工具 |
| **数据流冲突** | 输入均为 pandas DataFrame，输出均为增强后的 DataFrame。数据流完全对齐。但 CAAFE 的 openai==0.28 与 Featuretools/OpenFE 无直接冲突（后两者不依赖 openai） |
| **版本/依赖冲突** | Featuretools: numpy>=1.25,<2, pandas>=2.0; OpenFE: numpy>=1.19, pandas>=1.1; CAAFE: 无显式约束。三者无直接冲突。但 CAAFE 的 openai==0.28 若与 AIDE/mem0 同环境则冲突 ⚠️ |
| **总改造成本** | 低：统一工具注册接口约 1 人天。但 CAAFE 的隔离成本额外 +2 人天（子进程/独立环境） |
| **运维复杂度** | 低-中：Featuretools + OpenFE 直接 pip 安装；CAAFE 需隔离部署 |
| **推荐分** | **6/10**（含 CAAFE 隔离成本）/ **8/10**（不含 CAAFE，仅 Featuretools + OpenFE） |

**结论**：Featuretools + OpenFE 是零冲突组合。CAAFE 的 openai 版本冲突使其集成成本陡增，建议降级为「设计参考」而非「直接集成」。

---

### 组合 12：全 8 项目大集成（目标架构）

| 维度 | 评估 |
|------|------|
| **集成边界** | Layer 1（Harness）→ Layer 2（AIDE）→ Layer 3（mem0+MLflow）→ Layer 4（Featuretools+OpenFE+CAAFE）+ UI（Streamlit）+ ipynb 参考（Jupyter AI/NBI） |
| **数据流冲突** | 核心数据流（AIDE → mem0/MLflow）对齐。边缘数据流（Featuretools 需 EntitySet）需要 adapter。ipynb 解析管道自研 |
| **版本/依赖冲突** | **关键冲突点**：(1) CAAFE 的 openai==0.28 与 AIDE/mem0 的 openai>=1.69 冲突；(2) AIDE 的 numpy/pandas/scipy 硬锁版本需验证与所有工具库的兼容性。经矩阵分析，numpy 1.26.2 / pandas 2.1.4 / scipy 1.11.4 / sklearn 1.5.0 满足全部约束 ✓ |
| **总改造成本** | 中：核心三角（AIDE+mem0+MLflow）3 人天；工具库封装 1 人天；CAAFE 隔离/改造 2-3 人天；ipynb 自研 2 人天；Streamlit UI 5-8 人天。合计约 13-17 人天 |
| **运维复杂度** | 中：本地部署需管理 Streamlit(8501) + MLflow(5000) + Agent 进程。若 CAAFE 隔离部署，额外管理一个子环境 |
| **推荐分** | **7/10** |

**结论**：大集成可行，但 CAAFE 是唯一显著拖分项。若将 CAAFE 从「直接集成」降级为「设计参考」，推荐分升至 **8/10**。

---

### 组合 13：全自建（对照组）

| 维度 | 评估 |
|------|------|
| **集成边界** | 自研树搜索探索引擎 + 自研记忆层 + 自研实验追踪 + 自研特征工具 |
| **数据流冲突** | 无（全自研可统一数据模型） |
| **版本/依赖冲突** | 无（完全控制依赖） |
| **总改造成本** | **极高**：树搜索探索引擎（参考 AIDE 的 MLE-Bench 验证，自研需 4-6 周）；记忆层（mem0 56K Stars 的成熟度，自研需 3-4 周）；实验追踪（MLflow 级别的功能，自研需 2-3 周）；特征工具（OpenFE 的 23 种操作符，自研需 2-3 周）。合计 **11-16 周**，远超 fork/集成方案的 7-8 周 |
| **运维复杂度** | 低（代码全掌控），但维护成本高（无社区支持） |
| **推荐分** | **3/10** |

**结论**：全自建在工程上不经济。AIDE 的 MLE-Bench 验证成果、mem0 的 56K Stars 成熟度、MLflow 的行业标准地位，均无法在短期内自研替代。

---

## 三、综合排序（按推荐分降序）

| 排名 | 组合 | 推荐分 | 核心理由 |
|------|------|--------|----------|
| 1 | **AIDE + mem0 + MLflow** | **9/10** | 核心三角，零依赖冲突，数据流对齐，改造成本低 |
| 2 | **AIDE + OpenFE** | **8/10** | 技术完全兼容，API 简洁，算法+LLM 互补 |
| 3 | **AIDE + mem0** | **9/10** | 同上（但缺少结构化追踪层，不如三元组完整） |
| 4 | **AIDE + MLflow** | **9/10** | 同上（但缺少语义记忆层，不如三元组完整） |
| 5 | **mem0 + MLflow** | **9/10** | 记忆双层完美互补，但缺少探索引擎（不完整方案） |
| 6 | **Featuretools + OpenFE**（不含 CAAFE）| **8/10** | 零冲突工具组合，但仅为 Layer 4 子集 |
| 7 | **AIDE + Jupyter AI + NBI**（设计参考）| **7/10** | ipynb 接口设计参考组合，非代码集成 |
| 8 | **全 8 项目大集成**（含 CAAFE）| **7/10** | 可行但 CAAFE 拖分，需隔离/改造 |
| 9 | **AIDE + Featuretools** | **6/10** | NGS 数据形态与 Featuretools 最优场景不匹配 |
| 10 | **mem0 + Jupyter AI** | **5/10** | 设计参考价值，非代码集成价值 |
| 11 | **mem0 + NBI** | **5/10** | GPL 可接受但架构不匹配，建议参考而非集成 |
| 12 | **特征工具库含 CAAFE** | **6/10** | openai 版本冲突需隔离，成本增加 |
| 13 | **AIDE + CAAFE** | **4/10** | openai 硬冲突，改造成本高 |
| 14 | **全自建** | **3/10** | 工程上不经济，周期过长 |

---

## 四、Top 3 推荐组合详解

### Top 1：AIDE + mem0 + MLflow（核心架构三角）

```
集成方式：AIDE fork 后内嵌调用
  AIDE tree_search node → mem0.add(memory_id=node_id, ...)
                        → mlflow.log_metrics(metrics, run_id=node_id)
                        → sqlite 记录 node_id ↔ run_id 映射

数据流：
  探索结果 ─┬─→ mem0（语义："甲基化特征 X 在 CNS 有效"）
            └─→ MLflow（结构化：{auc: 0.88, features: [...]}）
                └─→ SQLite（情节：实验元数据索引）

改造成本：2-3 人天
运维：本地零配置
风险：无
```

### Top 2：AIDE + OpenFE（探索引擎 + 算法特征生成）

```
集成方式：工具注册表模式
  AIDE agent → ToolRegistry.get("feature_engineering") 
             → OpenFE.fit_transform(df) → 增强 df → 继续探索

数据流：pandas DataFrame 端到端
改造成本：0.5-1 人天
运维：pip install openfe
风险：无
```

### Top 3：Featuretools + OpenFE（Layer 4 工具库，不含 CAAFE）

```
集成方式：统一工具接口
  agent → 判断数据类型 → 多表关系型？→ Featuretools.dfs()
                        → 单表矩阵？   → OpenFE.transform()

改造成本：1 人天（统一接口封装）
运维：pip install featuretools openfe
风险：无
注意：Featuretools 在 NGS 场景价值有限，作为「可选工具」保留
```

---

## 五、关键风险与缓解

| 风险 | 严重度 | 影响组合 | 缓解措施 |
|------|--------|----------|----------|
| CAAFE openai==0.28 冲突 | **高** | AIDE+CAAFE, 全集成 | 将 CAAFE 降级为「设计参考」，自研 LLM 特征生成循环（代码量 <200 行） |
| Featuretools EntitySet 建模成本 | 中 | AIDE+Featuretools | 仅在 NGS 数据已有多表关系时使用，默认路径用 OpenFE |
| NBI GPL-3.0 法律风险 | 低 | mem0+NBI | 内部使用不触发 copyleft，但建议仅参考代码不直接 fork |
| AIDE numpy/pandas 硬锁 | 低 | 全组合 | 经矩阵验证 1.26.2/2.1.4/1.5.0/1.11.4 满足全部约束 |
| OpenFE 维护停滞 | 中 | AIDE+OpenFE | 2024-05 后无更新，但功能稳定。作为工具调用，可被替换 |

---

## 六、评估师结论

**工程事实总结：**

1. **核心三角（AIDE + mem0 + MLflow）是技术风险最低、集成成本最小的组合**，三者 Python >=3.10、关键依赖版本交集非空、pydantic v2 一致，无硬冲突。

2. **CAAFE 是 8 项目中唯一的「硬冲突源」**——其 `openai==0.28` 与目标架构的 `openai>=1.69` 无法在同一 Python 环境共存。CAAFE 的核心价值是「LLM→生成特征→CV评估→反馈」的设计模式，而非代码本身。建议自研实现（<200 行）。

3. **Jupyter AI 和 Notebook Intelligence 的设计参考价值 > 代码复用价值**。两者均为 JupyterLab 扩展，与本项目的 Streamlit + CLI 架构不匹配。提取其 MCP server 和 nbformat 解析的设计模式即可。

4. **Featuretools 的 NGS 适用性存疑**。NGS 数据通常是「样本 × 高维特征」单表矩阵，而非 Featuretools 最优的多表关系型数据。作为「可选工具」保留，非核心路径。

5. **全自建对照组在工程上不经济**。AIDE 的 MLE-Bench 验证成果、mem0 的 56K Stars 生态、MLflow 的行业标准地位，均无法以 7-8 周周期自研替代。

**最终推荐架构（工程最优）：**

```
Layer 1: Claude Code CLI + Agent SDK（已定）
Layer 2: AIDE（fork MIT）—— 树搜索探索引擎
Layer 3: mem0（pip Apache-2.0）+ MLflow（pip Apache-2.0）—— 语义+结构化记忆
Layer 4: OpenFE（pip MIT）+ Featuretools（pip BSD-3，可选）—— 特征工具
ipynb 接口: 自研（参考 Jupyter AI MCP server + NBI 集成模式）
CAAFE: 设计参考，不自研集成
```

**推荐分：8/10**（若完全排除 CAAFE 直接集成，并自研 ipynb 接口）。
