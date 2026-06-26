# MLagent — Claude Code 插件设计 spec（重设计 v2）

Date: 2026-06-26
Status: Draft / 决策已定（见 §10）

> 本文档从零重设计，独立于任何历史调研结论。它只描述**目标系统本身**。

---

## 1. 定位

MLagent 是一个 **Claude Code 插件**。它只适配 Claude Code，不依赖、不嵌入任何外部 ML 平台（MLflow / DVC / W&B / 向量库等）。

它解决一个具体痛点：**在 Claude Code 自主探索/训练 ML 模型的过程中，人类对"脚本实际怎么写、怎么跑、结果如何"缺乏把控**。MLagent 通过三件事补上这个把控：

1. 把探索与训练过程**结构化记忆**下来，并沉淀为可复用的 **Skill-SOP 范式库**；
2. 在插件加载时开启一个**交互式 UI**，让人类实时看见脚本的写法、运行过程、性能结果，并能干预；
3. 提供适配 Claude Code 的 **skills + hooks**，把记忆、UI、SOP 转换串成一条工作流。

### 不做什么（scope 边界）

- 不做训练框架、不做超参优化器、不内置模型库。
- 不强制向量库 / workflow orchestrator / 远程 GPU 编排。
- UI 是**本地单用户**的查看与干预面，不是多用户协作平台、不是模型服务。
- 不自动把任何东西定为"正式 SOP"——所有 SOP 入库需人类确认。

---

## 2. 设计原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | **Claude Code 原生优先** | 能用 hook/skill/permission 解决的，不另造机制 |
| P2 | **人类在环是硬约束** | 训练执行高风险；人类通过 UI 实时可见+写回干预、及 Claude Code 自身 permission/plan 模式把控（MLagent 不另造命令级门禁） |
| P3 | **持久资产人类可读** | 一切落盘为 Markdown / YAML / 原始文件；索引可重建、非唯一来源 |
| P4 | **UI 是视图层，不是数据源** | UI 只读写已有文件/仓库；拔掉 UI，系统仍完整工作 |
| P5 | **最小自洽再扩展** | 先跑通"记忆→经验→SOP→重训"闭环，再加富功能 |

---

## 3. 总体架构

三个子系统 + 一条工作流主线：

```text
┌─────────────────────────────────────────────────────────────┐
│                       Claude Code                           │
│                                                             │
│  ┌─────────────── 子系统3：适配组件 ───────────────┐        │
│  │  skills:  bootstrap / explore-train /          │        │
│  │           distill-experience / instance-to-sop │        │
│  │           / retrain-from-sop                   │        │
│  │  hooks:   SessionStart / PostToolUse / Stop    │        │
│  │  bin:     mlagent (CLI: 确定性操作 + UI 启停)   │        │
│  └─────────────────────────────────────────────────┘        │
│         │ 写/读                    │ 注入上下文 + 启停 UI     │
│         ▼                          ▼                        │
│  ┌─────────── 子系统1：记忆/SOP ────────┐  ┌── 子系统2：UI ──┐│
│  │ raw_memory → experience → skill_lib │  │ 3 面板：       ││
│  │            （Skill-SOP 范式库）      │←→│ · 脚本结构     ││
│  │            YAML/MD, 可溯源、可版本化 │  │ · 运行日志     ││
│  └─────────────────────────────────────┘  │ · 性能表格     ││
│                                           │ (本地进程)     ││
│                                           └────────────────┘│
└─────────────────────────────────────────────────────────────┘
          ↑                               ↑
          └──── 项目训练文件 (script / manifest / log / metrics) ────┘
```

数据流约定：
- **Claude Code**（经 skills/hooks）是唯一写者，把过程写入 raw_memory、把脚本/清单/日志/指标写到项目文件。
- **UI** 只读这些文件 + 监听变化重渲染；人类经 UI 做的修改写回文件并打"人工干预"标记，Claude Code 下一步读到该标记即知需重新对齐。

---

## 4. 子系统 1：记忆 / 经验 / Skill-SOP 系统

三层 + 一个库：

```text
project_memory/
  ├─ raw_memory/        证据层：探索/训练过程的原始结构化记录
  ├─ experience/        蒸馏层：从 raw_memory 提炼的经验
  └─ skill_library/     SOP 层：版本化的 Skill-SOP 范式库
       └─ <sop_name>/
            ├─ registry.yaml        该 SOP 的版本索引与状态
            └─ v001_*/              单个版本（一个完整的 skill）
                 ├─ SKILL.md         SOP 正文（可被 Claude Code 当 skill 调用）
                 ├─ scripts/         可复现脚本
                 ├─ sop.yaml         版本元数据（见 §8.3）
                 ├─ validation.md    "跑通测试"的证据
                 └─ performance.yaml 性能结果
```

### 4.1 raw_memory（证据层）

忠实记录过程，粒度标准、不过度美化。由 hooks/CLI 自动写。每条带溯源与人工干预标记。

关键字段：`id / type(session|exploration|run|human_note) / goal / hypothesis / actions / changed_files / commands(含 status) / results(metrics,artifacts) / failure_reason / human_interventions / evidence_links / next_steps`。

### 4.2 experience（蒸馏层）

从 raw_memory 蒸馏出的 **lessons / pitfalls / successful_patterns / failed_directions**。可自动入库，但每条必须带：`source_raw_records`（溯源）、`confidence`（low/medium/high）、`needs_review`、`applies_when / avoid_when`。低置信度经验默认折叠或带警示浮现。

**蒸馏机制（Q4 已定：自动产出）**：按"探索次数"分阶段触发（非每次都跑）；每次由 LLM 回顾"距上一阶段以来"的全部探索，只提炼**有意义的**经验——**带来性能提升的做法**或**踩过的坑（potential pitfalls）**——无新增意义的探索不产出噪声条目。产出仍带置信度/溯源/needs_review。

### 4.3 skill_library（Skill-SOP 范式库）

**核心概念**：每个 SOP 就是一个**版本化的 Claude Code skill**（有 SKILL.md + scripts），既是"可读的训练范式"，也是"可直接被调用的重训规程"。

**入库的唯一两条合法来源**：
1. 探索中产生的最佳实例（达到/超过目标且通过人工性能评审）；
2. 人工 notebook（通过人工性能 + 可复现性评审）。

**转换门禁（硬约束）**：实例 → SOP **必须先跑通测试**（端到端复现：无错 + 产出符合预期 + 指标被记录），才生成**候选版本**；候选经**人工确认**后才正式写入 `skill_library/<sop>/vXXX`。

**版本元数据（每个版本必填）**：`背景 background / 时间 created_at / 原因 reason / 关键参数 key_params / 关键优化点 key_optimizations`，外加 `source_evidence / human_review / performance`。版本只追加不覆盖：新版本标 `current`，旧版标 `superseded` 但保留（可溯源）。

---

## 5. 子系统 2：交互式 UI

### 5.1 生命周期（设计决策 D1）

- `SessionStart` hook → 运行 `mlagent ui start`：启动**本地进程**（监听 localhost），打开浏览器，并把 UI 地址 + 记忆状态注入 Claude Code 上下文。
- 运行期：UI 用**文件监听**（watchdog/watchman）跟踪项目训练文件，Claude 一改就重渲染——**UI 与 Claude Code 通过文件系统解耦，不直接通信**。
- `Stop` hook → `mlagent ui stop`：关闭进程。
- 失败非致命：UI 起不来时，hook 降级为"仅在终端提示记忆状态"，不阻塞 Claude Code 工作（P4：UI 是视图层）。

> **技术栈（Q1 已定）**：FastAPI 后端 + 独立前端工程。后端读脚本/manifest/日志/指标并做文件监听推送（WebSocket/SSE）；前端渲染三面板。

### 5.2 三个面板

#### 面板 A：脚本详情（结构化展示，实时渲染）

把训练脚本按语义步骤结构化展示：**特征处理 / 数据划分 / 模型定义 / 训练循环 / 评估 / 保存** 等。每个步骤显示：目的、关键代码段、关键参数。

**结构来源（设计决策 D2）**：脚本配一份**伴随清单** `<script>.manifest.yaml`，列出各 step（title / purpose / 代码位置 file+lines / key_params）。`explore-train` skill 保证：每次写/改训练脚本，同步维护这份清单。UI 同时读清单 + 代码渲染；任一变化即重渲染。
> 兜底：脚本内 section 标记（如 `# %% [mlagent:step=feature_eng]`）+ AST 解析。**Q2 已定：manifest 为主路径，标记为辅。**

#### 面板 B：运行过程记录

展示训练运行的 **stdout/stderr**，重点是**报错与 print**。实现：训练经 `explore-train` skill 用一个小 runner 执行，输出 tee 到 `runs/<run_id>/log.txt`；UI tail 该文件，错误高亮、可折叠。

#### 面板 C：运行结果性能

训练写出 `runs/<run_id>/metrics.json`；UI 读后渲染为**性能表格**，并支持**跨 run 对比**（同一 SOP 不同版本/不同数据）。

### 5.3 人类干预的闭环（设计决策 D3）

人类经 UI 的修改（改脚本参数、标注、审批候选 SOP）→ **写回文件** + 在 raw_memory 追加一条 `human_interventions`（或标 `needs_rereview`）。Claude Code 下一步读到该标记 → 知道人工动过手、需重新对齐再继续。**数据模型已天然支持，UI 只是更友好的操作面。**

---

## 6. 子系统 3：Claude Code 适配组件

### 6.1 通用 skills

| skill | 职责 | 何时触发 |
|---|---|---|
| **mlagent-bootstrap** | hook 在 SessionStart 注入的"主 skill"；告诉 Claude 整套流程、如何记 raw_memory、如何维护 manifest、UI 已开、当前 SOP 库状态 | 每次会话开始 |
| **explore-train** | 探索 + 训练编排；保证产出"结构化脚本 + manifest + 运行日志 + 指标"，并写 raw_memory | 用户发起探索/训练 |
| **distill-experience** | 按"探索次数"分阶段自动触发；LLM 回顾距上阶段以来的探索，提炼**有意义**经验（性能提升/潜在坑），无意义不产出；带置信度与溯源 | Stop hook 自动 / 按需 |
| **instance-to-sop** | 把实例（探索 run 或 notebook）→ **跑通测试** → 生成候选 SOP 版本（含 background/time/reason/key_params/key_optimizations） | 用户指定最佳实例转 SOP |
| **retrain-from-sop** | 选定 skill_library 某版本 → 严格依其 SKILL.md/scripts 重训 → 保存模型 + 性能结果 → 写 run 记录 | 用户指定版本重训 |

### 6.2 hooks（保守、可降级）

| hook | 动作 | 安全规则 |
|---|---|---|
| **SessionStart** | 注入 mlagent-bootstrap；`mlagent ui start`；显示记忆状态；提醒选项目 | UI 起不来则降级为终端提示，不阻塞 |
| **PostToolUse**（Write/Edit/Bash） | 捕获脚本改动 → 提示更新 manifest；捕获训练命令 → tee 日志；写 raw_memory 草稿 | 只记摘要+路径，不存全量 diff/log |
| **Stop** | 生成会话总结；触发 distill-experience（候选）；`mlagent ui stop` | distill 产出带置信度，低置信不自动定论 |

> **人类把控（Q3 已定：不另设门禁）**：MLagent 不加 `PreToolUse` 命令拦截；人类在环通过 (a) UI 三面板实时可见+写回干预、(b) Claude Code 自身 permission/plan 模式适配实现，不重复造已有的命令级控制。

### 6.3 CLI（`bin/mlagent`）

确定性操作（Pydantic 校验 YAML）：
`init / status / record-raw / distill / convert-to-sop / approve-sop / list-sops / get-sop / retrain / assemble-context / ui start / ui stop`。

---

## 7. 关键工作流

### 7.1 探索-训练（带 UI 实时可见）
```text
SessionStart: 注入 bootstrap + 开 UI
→ 用户给目标 → explore-train skill
→ Claude 读代码、写/改脚本、同步 manifest、跑训练(runner tee 日志+指标)
→ UI 三面板实时刷新（脚本结构 / 日志 / 性能）
→ PostToolUse 写 raw_memory 草稿
→ 人工可在 UI 干预(改参数/标注) → 写回文件 + human_interventions
→ Claude 读标记重新对齐 → 结束生成 run 总结
```

### 7.2 实例 → SOP（带跑通门禁）
```text
人工指定最佳 run 或 notebook
→ instance-to-sop skill
→ 端到端复现跑通(无错 + 产出符合 + 指标记录) —— 失败则不转换
→ 生成候选 SOP 版本(含 background/time/reason/key_params/key_optimizations)
→ 人工确认性能与可复现性
→ approve-sop 写入 skill_library/<sop>/vXXX + 更新 registry
```

### 7.3 按指定 SOP 重训
```text
用户指定 SOP 版本 + 新数据
→ retrain-from-sop skill → 加载该版本 SKILL.md/scripts
→ 严格依规程重训 → 保存模型 + performance.yaml → 写 run
→ 更优结果仍须经 7.2 才能升为新版本（不自动覆盖）
```

---

## 8. 数据模型（YAML schema 摘要）

### 8.1 raw_memory（节选）
```yaml
id: raw_20260626_001
type: run
goal: "提升 AUC"
changed_files: [{path: train.py, summary: "..."}]
commands: [{command: "python train.py", status: success}]
results: {metrics: {auc: 0.91}, artifacts: [outputs/model.pkl]}
human_interventions: []          # UI/人工改动写这里
evidence_links: [runs/run_001/log.txt, runs/run_001/metrics.json]
```

### 8.2 experience（节选）
```yaml
id: exp_20260626_001
type: pitfall
summary: "..."
confidence: medium
needs_review: true
source_raw_records: [raw_memory/raw_20260626_001.yaml]
applies_when: ["sample size < 500"]
avoid_when: ["无外部验证集"]
```

### 8.3 Skill-SOP 版本元数据（核心）
```yaml
version: "v001"
name: "xgboost_baseline"
created_at: "2026-06-26T10:00:00+08:00"
background: "项目早期基线，特征经卡方筛选"
reason: "首次达到目标 AUC，作为后续对比基线"
key_params: {n_estimators: 500, max_depth: 6}
key_optimizations: ["卡方选 top-50 特征", "5-fold CV 早停"]
source_evidence: [raw_memory/raw_20260626_001.yaml, evidence/baseline.ipynb]
human_review: {reviewed: true, reviewer: "...", approval_note: "..."}
performance: {primary: {name: auc, value: 0.91}, dataset_version: data_v003}
status: current              # current | superseded
superseded_by: null
```

### 8.4 script manifest（UI 面板 A 用）
```yaml
script: train.py
steps:
  - id: feature_eng
    title: 特征处理
    purpose: "卡方筛选 top-50 特征"
    location: {file: train.py, lines: [12, 45]}
    key_params: {top_k: 50}
  - id: data_split
    title: 数据划分
    ...
```

---

## 9. 目录结构（插件 + 项目记忆）

```text
mlagent-plugin/                      # Claude Code 插件（安装一次）
  ├─ .claude-plugin/plugin.json
  ├─ skills/  (bootstrap / explore-train / distill-experience / instance-to-sop / retrain-from-sop)
  ├─ hooks/hooks.json  +  hooks/session-start / post-tool-use / stop
  ├─ bin/mlagent                     # CLI + ui 启停
  └─ ui/                             # 本地 UI 进程代码（子系统2）

<project>/project_memory/            # 随项目迁移
  ├─ raw_memory/  experience/  skill_library/  indexes/(sqlite, 可重建)
<project>/runs/<run_id>/             # log.txt + metrics.json（UI 读）
<project>/<script>.py + <script>.manifest.yaml
```

---

## 10. 设计决策（均已定）

| 编号 | 决策 | 最终选择 | 备注 |
|---|---|---|---|
| D1 | UI 生命周期 | SessionStart 启 / Stop 停，本地进程，可降级 | 你要求"加载即开" |
| Q1 | UI 技术栈 | **FastAPI 后端 + 独立前端工程** | 后端读文件+监听推送(WS/SSE)，前端渲染三面板 |
| D2 | 脚本结构来源 | **伴随 manifest（skill 维护）为主** | 脚本内标记+AST 解析作兜底 |
| D3 | 人工干预闭环 | 写回文件 + human_interventions 标记 | 契合 P4 解耦 |
| Q3 | 训练命令审核门禁 | **不另设门禁**，随 Claude Code permission/plan 模式适配 + UI 可见性把控 | 不重复造 Claude Code 已有的命令级控制 |
| Q4 | distill 自动化 | **自动产出**：按探索次数分阶段，LLM 回顾距上阶段以来探索，提炼有意义经验（性能提升/潜在坑），无意义不产出 | 仍带置信度/溯源 |

---

## 11. MVP 范围（分期）

**MVP（P0，必须）**
1. project_memory 初始化 + raw_memory 结构化记录（hooks 自动）。
2. UI 三面板跑通：脚本结构（manifest）+ 运行日志（tee）+ 性能表格（metrics.json），文件监听实时刷新。
3. experience 自动蒸馏（按探索次数分阶段，带置信度/溯源）。
4. instance-to-sop 全流程（含跑通门禁 + 人工确认 + 版本元数据）。
5. retrain-from-sop + list/get-sop。
6. SessionStart/PostToolUse/Stop 三 hook + bootstrap 主 skill + UI 启停。

**Stage-2（P1，可选）**
- 跨 run/SOP 版本性能对比、metrics 曲线。
- 知识文档导入 + FTS5 检索（context 组装）。
- UI 内直接编辑脚本 + 审批候选 SOP 的完整闭环。

---

## 12. 验收标准（端到端）

1. **探索可见**：插件加载即开 UI；Claude 改脚本，UI 面板 A 实时变；跑训练，面板 B 出日志、面板 C 出性能表。
2. **记忆沉淀**：一次会话产出 raw_memory；Stop 后 experience 自动产出候选条目（带置信度/溯源）。
3. **SOP 转换有门禁**：指定实例 → 跑通测试 → 通过才生成候选 → 人工确认入 skill_library；版本元数据齐全（背景/时间/原因/关键参数/关键优化点）。
4. **可重训**：指定 SOP 版本重训 → 保存模型 + performance → 写 run；更优结果不自动覆盖，须走转换门禁。
5. **可降级**：UI 进程挂掉，Claude Code 仍能正常工作（仅终端提示）。

核心成功声明：
```text
插件加载即开 UI，人类实时看见脚本怎么写、怎么跑、结果如何，并能干预；
探索过程结构化沉淀为 raw_memory，蒸馏为 experience；
跑通的人工确认实例/notebook 成为版本化 Skill-SOP，记录背景/原因/关键参数/优化点；
指定 SOP 版本可严格重训并保存模型与性能；
全程人类在环、资产可读可溯源、UI 可拔可降级。
```
