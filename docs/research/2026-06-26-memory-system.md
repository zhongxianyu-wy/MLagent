# 记忆系统设计参考调研

> Backref: [设计 spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md) · Date: 2026-06-26 · 来源: GitHub + 论文。**只借鉴设计（字段/schema/机制/prompt），不引入向量库/图谱 runtime**。
>
> 对标三层：raw_memory（证据层）/ experience（蒸馏层，按探索次数分阶段自动蒸馏有意义经验）/ skill_library（Skill-SOP 范式库，版本化、跑通测试才入库、人工确认）。

## 一、三层各自候选库总览

### raw_memory（结构化记录层）

| repo | URL | 借鉴点 | 是否绑重依赖 | 复用方式 |
|---|---|---|---|---|
| **Letta (MemGPT) / MemFS** | https://github.com/letta-ai/letta ，文档 https://docs.letta.com/letta-code/memory | "记忆即 markdown 目录 + git 版本史"；`system/` 常驻、其余按需加载；`core_memory_append/replace`；`/remember` 显式干预；dream（reflection）触发器=步数/压缩事件 | 中（MemFS 本身 git+md 可剥离） | **借鉴"文件即记忆 + git 版本 + 分级加载"范式** |
| **mem0** | https://github.com/mem0ai/mem0 ，API https://docs.mem0.ai/api-reference/memory/get-memory | 字段 `id/memory/user_id/agent_id/run_id/metadata/created_at/updated_at`；TAG scope 过滤；ADD/UPDATE/DELETE 事件 + 向量去重 | 重（向量库） | **借鉴字段命名 + scope 三件套 + 事件类型** |
| **A-MEM** | https://github.com/agiresearch/A-mem ，论文 arXiv 2502.12110 | Zettelkasten 原子笔记：`content/tags/context/keywords/category/timestamp`；写入即回链；可演化 | 重（ChromaDB） | **借鉴四字段 + 写入即建链**，link 用 YAML `related:` |
| **kernel-memory** | https://github.com/microsoft/kernel-memory | Citation 模型：`DocumentId/File/SourceUrl/Partition/Relevance/Tags`；`MemoryAnswer` 包 citations[] | 重（向量+pipeline） | **借鉴 Citation 字段结构**，给 evidence_links 结构化 |
| **cognee (DataPoint)** | https://github.com/topoteretes/cognee ，文档 https://docs.cognee.ai/core-concepts/building-blocks/datapoints | 原子知识单元：`id/version/topological_rank/metadata.index_fields/type/belongs_to_set`；显式 `update_version()`；identity_fields 去重 | 重 | **借鉴 version 显式版本 + topological_rank + identity_fields 去重** |

**raw_memory 重点 1 — Letta MemFS**（https://docs.letta.com/letta-code/memory）
记忆 = git 仓库下的 markdown 文件目录。`system/` 全量进系统提示；其余只暴露"文件名+描述"，内容按需读取（渐进式披露，与三层理念高度一致）。agent 用 bash 编辑 → commit → 推云端；完整版本史可 diff/回滚。dream 触发器：`Off`/`Step count`（每 N 条用户消息）/`Compaction event`（推荐）——**正是 v0.3 experience "按探索次数分阶段触发"的成熟先例**。借鉴：①文件目录即记忆、git 即版本；②分级加载；③dream 触发器。**只取思想，不引入 server。**

**raw_memory 重点 2 — A-MEM 原子笔记**（论文 https://arxiv.org/pdf/2502.12110）
字段（源码 `AgenticMemoryNote`）：`content/keywords[]/tags[]/context/category/timestamp/links[]`。写入：①LLM 生成 content + 抽 keywords/tags/context；②embedding 找历史相关；③建 links；④演化。借鉴：`context`（笔记"在什么情境下产生"）极好补充 raw 的 `goal/hypothesis`；`keywords/tags` 是检索入口；`links[]` → `related`。

### experience（蒸馏层）

| repo | URL | 借鉴点 | 是否绑重依赖 | 复用方式 |
|---|---|---|---|---|
| **langmem** | https://github.com/langchain-ai/langmem ，Episode 指南 https://langchain-ai.github.io/langmem/guides/extract_episodic_memories/ ，概念 https://langchain-ai.github.io/langmem/concepts/conceptual_guide/ | **Episode schema：observation/thoughts/action/result**；semantic/episodic/procedural 三分类；schema 即 prompt；importance/strength 召回；background vs foreground 蒸馏 | 中（绑 LangGraph store，schema 纯 pydantic 可剥离） | **直接照搬 Episode 四字段** |
| **A-MEM** | 同上 | 原子化 + 自动回链演化 | 重 | 借鉴"经验原子化 + related 回链" |
| **mem0** | https://docs.mem0.ai/cookbooks/essentials/controlling-memory-ingestion | **dedup/contradiction pipeline**：写入前比对既有记忆，输出 ADD/UPDATE/DELETE/NONE | 重 | **借鉴去重/矛盾判定** → superseded_by |
| **Letta dream** | https://docs.letta.com/letta-code/memory | 后台 sleep-time subagent 周期回顾→提炼；触发器 step-count/compaction | 中 | **借鉴"后台 reflection + 触发器"**作自动产出机制 |
| **Sanity distillation** | https://www.sanity.io/blog/how-we-solved-the-agent-memory-problem | 监控 token 量，超阈值找连贯片段压缩；**不是每轮都跑** | 轻（博客） | 借鉴"阈值触发，非每轮" |

**experience 重点 1 — langmem Episode（强烈推荐直接借鉴）**（https://langchain-ai.github.io/langmem/guides/extract_episodic_memories/）
```python
class Episode(BaseModel):
    observation: str  # 上下文与设置 - 发生了什么
    thoughts: str     # 内部推理 "I ..."
    action: str       # 做了什么、怎么做 "I ..."
    result: str       # 结果与回顾。下次能怎么更好？ "I ..."
```
哲学：**第一人称、事后回顾、保存推理链**（"Write the episode from the perspective of the agent within it. Use hindsight... saving key internal thought process so it can learn over time."）——与"按阶段回顾距上一阶段以来的探索，只提炼有意义经验"完全同构。
概念三分类：semantic（事实 what）/ episodic（成功 expertise how）/ procedural（演化的指令）——**分别对应 raw事实 / experience经验 / skill-SOP，1:1 映射**。
蒸馏 prompt 原文：`"Extract exceptional examples of noteworthy problem-solving scenarios..."` → ML 版：`"Extract noteworthy ML exploration outcomes (performance gains / pitfalls), only when meaningful change occurred. Skip noise."`

**experience 重点 2 — Letta dream 触发器（解决"分阶段蒸馏"）**
dream = 后台 sleep-time subagent，周期回顾近期对话→决定是否写记忆。触发器：`Off`/`Step count`/`Compaction event`（推荐）。**不是每轮都跑**。直接映射：触发=累计探索次数达阈值（每 5/10 次）；范围=距上一阶段以来新增 raw_memory；产出=0..N 条（无意义则 0）。补：mem0 ADD/UPDATE/DELETE 用于冲突时旧经验 `superseded_by` 新经验（不删只标记）。

### skill_library（版本化 SOP 层）

| repo | URL | 借鉴点 | 是否绑重依赖 | 复用方式 |
|---|---|---|---|---|
| **Graphiti (Zep)** | https://github.com/getzep/graphiti ，论文 arXiv 2501.13956 ，博客 https://blog.getzep.com/beyond-static-knowledge-graphs/ | **bi-temporal 四字段**：valid_at/invalid_at/created_at/expired_at；事实变更=旧 invalidate 不 delete；episodic edge (MENTIONS) 连 raw↔entity | 重（Neo4j） | **借鉴 bi-temporal 语义**：valid_from/superseded_by + 补 valid_to |
| **MLEM** | https://github.com/iterative/mlem ，对象参考 https://github.com/iterative/mlem.ai/blob/main/content/docs/object-reference/mlem-objects.md ，CI/CD https://github.com/iterative/mlem.ai/blob/main/content/docs/use-cases/cicd.md | **MlemObject 落盘 YAML**：object_type/artifacts[]/requirements[]/params；Git 即 registry；CI/CD 发布门禁 | 轻（纯 YAML+Git） | **直接借鉴"资产即版本化 YAML + Git registry"** |
| **modelstore** | https://github.com/operatorai/modelstore ，CONTRIBUTING https://github.com/operatorai/modelstore/blob/main/modelstore/models/CONTRIBUTING.md | **meta summary 拆分**：model_type/code/framework/training_data/evaluation/parameters/storage/upload；**state 机** draft/pending/approved/archived；filesystem 后端 | 轻 | **借鉴 summary 段拆分 + state 机** |
| **HF Model Card** | https://huggingface.co/docs/hub/en/model-cards ，分析 arXiv 2402.05160 | 字段 model_details/intended_use/limitations/evaluation/training/model-index；**limitations 最值钱** | 无 | **借鉴 limitations + intended_use** |
| **SageMaker Model Registry** | https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry-approve.html | ApprovalStatus: Pending/Approved/Rejected，可 pipeline 自动化 | 重（AWS） | 借鉴"跑通测试→auto-approve 候选"思想 |

**skill_library 重点 1 — Graphiti bi-temporal（版本语义黄金范式）**（https://blog.getzep.com/beyond-static-knowledge-graphs/ ）
每条事实/边携带四时间字段：`valid_at`/`invalid_at`（valid time，现实世界何时为真）；`created_at`/`expired_at`（transaction time，系统何时记录/弃用）。事实变更=旧事实置 invalid_at（保留为历史），新事实生效——**不删除、只追加**，正是"版本只追加不覆盖"的学术化表达。episodic edge(MENTIONS) 连 raw episode↔抽取 entity，对应 raw_memory↔skill 溯源边。**只借鉴语义、不引入图谱**——用 YAML `superseded_by` + `valid_from/to` 表达。

**skill_library 重点 2 — MLEM + modelstore（资产即版本化 YAML + 门禁）**
MLEM MlemObject YAML：object_type/artifacts[]（文件列表）/requirements[]（pip 依赖）/params（超参）。Git 仓库即 registry（每个 mlem 文件=一个版本化对象）。CI/CD 门禁（mlem publish/deploy 在 GitHub Actions 中）。modelstore meta 拆分：summary 含 model_type/code/framework/training_data/evaluation/parameters/storage/upload；state 机 draft→pending→approved→archived（filesystem 后端原生支持）。三者共同支撑**"测试作为入库前置门禁"是成熟范式**（MLEM CI + modelstore 每框架有 tests/ + SageMaker condition step）。

## 二、溯源/谱系（lineage）专项

| 来源 | URL | 设计要点 | 复用方式 |
|---|---|---|---|
| Graphiti | 同上 | episodic MENTIONS 边=raw↔entity 双向溯源；bi-temporal 让"事实从哪次 episode、何时失效"可查 | YAML source_evidence + derived_from |
| cognee | https://docs.cognee.ai/core-concepts/building-blocks/datapoints | DataPoint 携带 provenance；belongs_to_set 分组；topological_rank 依赖层级 | raw→experience→skill 用 topological_rank（raw=0,exp=1,skill=2） |
| kernel-memory | 同上 | Citation 带 DocumentId/File/SourceUrl/PartitionNumber | evidence_links 结构化 |
| langmem | 同上 | Episode 带 created_at/updated_at + namespace ("memories","episodes") | experience 带命名空间分层 |

**链路表达**：不引入图谱，用 YAML frontmatter 静态字段表达 raw→experience→skill：
- experience.`source_raw_records: [raw_id...]`（=Graphiti episodic edge）
- skill_version.`source_evidence: [raw_id/run_id/experience_id...]`（混合 id）
- 反向链：raw.`derived_experiences: [exp_id...]` / `derived_skills: [skill_v...]`（新增）
- bi-temporal：每层带 `valid_from/valid_to/superseded_by`

## 三、复用结论 + YAML schema 草案

### 三层各自最该借鉴谁

| 层 | 主借鉴 | 辅借鉴 |
|---|---|---|
| raw_memory | **A-MEM**（content/context/keywords/tags）+ **Letta MemFS**（文件即记忆 + git + system/分级） | kernel-memory Citation + cognee version/topological_rank |
| experience | **langmem Episode**（observation/thoughts/action/result 直接照搬）+ **Letta dream 触发器**（step-count/compaction） | mem0 ADD/UPDATE/DELETE（→ superseded_by） |
| skill_library | **MLEM**（资产即 YAML + Git registry + artifacts/requirements/params）+ **Graphiti bi-temporal**（只取语义不入图谱） | modelstore state 机 + HF Model Card limitations/intended_use |

### raw_memory 字段草案
```yaml
id: raw_20260626_001
type: exploration            # session/exploration/run/human_note
created_at: "2026-06-26T14:03:00+08:00"
session_id: sess_abc
goal: "提升 AUC 至 0.90"
hypothesis: "加入交互特征可能有效"
# A-MEM 四字段补强
context: "二分类 tabular，基线 AUC 0.85，特征工程阶段"
keywords: [interaction-features, xgboost, auc]
tags: [feat-engineering, xgb]
# 过程记录（保留）
actions: [...]
changed_files: [{path, sha256, diff_summary}]   # kernel-memory Citation 风格
commands: [{command, summary, status}]
results: {auc: 0.87}
failure_reason: null
human_interventions: []                         # 对标 Letta /remember
evidence_links: [{document_id, file, source_url, partition, relevance}]
next_steps: [...]
# 溯源/版本补强
version: 1
derived_experiences: []                         # 反向链（新增）
derived_skills: []                              # 反向链（新增）
```

### experience 字段草案（Episode 四字段作 detail 子结构）
```yaml
id: exp_20260626_001
type: successful_pattern       # lesson/pitfall/successful_pattern/failed_direction
summary: "交互特征 + 目标编码稳定提升 AUC"
# langmem Episode 四字段（替换单字段 detail）
detail:
  observation: "基线 AUC 0.85，加入 f1×f2 交互 + target encoding"
  thoughts: "交互项捕获非线性；目标编码需防泄漏，用 5-fold"
  action: "xgboost + 5-fold target encoding，lr 0.05"
  result: "AUC 0.85→0.87，验证集稳定；过采样无效"
# 召回/治理（保留并细化）
confidence: high
needs_review: false
source_raw_records: [raw_20260626_001, raw_20260626_002]
applies_when: [tabular, 有类别特征]
avoid_when: [小样本, target 泄漏风险高]
related: [exp_20260620_005]                     # A-MEM 回链
# bi-temporal（补 valid_to）
valid_from: "2026-06-26T14:10:00+08:00"
valid_to: null
superseded_by: null
created_at: "2026-06-26T14:10:00+08:00"
```

### sop-version 字段草案（MLEM 风格 + Graphiti bi-temporal + HF Card）
```yaml
version: "1.2.0"
name: retrain-xgb-with-interactions
object_type: skill_version
# MLEM/modelstore 三段式
artifacts: [{path: skills/retrain-from-memory/SKILL.md, sha256: ...}]
requirements: {python: "3.11", deps: [xgboost, scikit-learn]}
params: {lr: 0.05, n_fold: 5}
# state 机
state: approved                # draft/pending_review/approved/rejected/archived
# 入库门禁（新增显式字段）
gate:
  tests_passed: true
  test_log: evidence/tests/run_20260626.log
  test_command: "pytest tests/test_retrain.py"
source_type: best_run
source_evidence: [run_20260626_best, exp_20260626_001]
# HF Model Card 补强
background: "交互特征稳定提升 AUC，固化成 SOP"
intended_use: [tabular 二分类, AUC 优化]
limitations: [样本 <1万 时目标编码易泄漏]
key_params: {lr: 0.05}
key_optimizations: [5-fold target encoding]
# 评审/性能
human_review: {reviewed: true, reviewer: zhongxianyu, reviewed_at: "...", approval_note: "..."}
performance: {primary_metric: {name: auc, value: 0.87}, dataset_version: v3, validation_protocol: 5-fold-cv}
reproducibility: {seed: 42, commit: abc123}
# bi-temporal
valid_from: "2026-06-26T15:00:00+08:00"
valid_to: null
superseded_by: null
```

### 分阶段有意义蒸馏的实现（综合 Letta dream + langmem + mem0）
1. **触发器**（Letta dream）：累计 raw_memory 探索次数达阈值（每 N=5/10 次）触发一次，或 `/distill` 手动触发（对应 `/remember`）。**不是每轮都跑。**
2. **回顾范围**：仅看"距上一阶段以来"新增 raw_memory（`created_at > last_distill_at`）。
3. **蒸馏 prompt**（langmem Episode）：要求 LLM 以 Episode 四字段回顾这批 raw，**只在出现"有意义变化"时产出**：性能提升（primary_metric 显著改善）/ 潜在坑（failure_reason 非空且可泛化）；否则返回 0 条（不产噪声）。
4. **去重/矛盾**（mem0 Control Ingestion）：新 experience 与既有同主题比对，输出 `ADD`（新建）/`UPDATE`（补既有）/`SUPERSEDE`（矛盾且更可信→旧 `superseded_by` 新 + `valid_to` 置当前，不删）/`NONE`（重复丢弃）。
5. **每条带溯源**：`source_raw_records` 指向本次回顾的 raw id 列表。

## 四、关键提醒（避免踩坑）

1. **别引入向量库/图谱 runtime**：A-MEM/Graphiti/cognee/mem0/langmem 都默认绑 ChromaDB/Neo4j/Postgres——**只借 schema 和机制，落盘 YAML/MD**。检索用简单文本索引。
2. **Episode 四字段是 experience 最大增益点**：单字符串 detail 改成 observation/thoughts/action/result 后蒸馏质量与可读性显著提升——性价比最高。
3. **bi-temporal 补 `valid_to`**：现有只有 valid_from/superseded_by，加 valid_to 才完整表达"事实何时失效"（区别于 superseded_by 的系统层弃用）。
4. **入库门禁做成显式字段**：`gate.tests_passed/test_log/test_command`，把"跑通测试才入库"从口头流程变 schema 级强制。
5. **HF limitations 字段**：arXiv 2402.05160 实证 limitations 是最常缺失但最值钱的字段——SkillVersion 必须强制填。

## Sources
- langmem Episode: https://langchain-ai.github.io/langmem/guides/extract_episodic_memories/ · 概念 https://langchain-ai.github.io/langmem/concepts/conceptual_guide/ · repo https://github.com/langchain-ai/langmem
- A-MEM: https://github.com/agiresearch/A-mem · 论文 https://arxiv.org/pdf/2502.12110
- Letta MemFS: https://docs.letta.com/letta-code/memory · repo https://github.com/letta-ai/letta · MemGPT 论文 https://ar5iv.labs.arxiv.org/html/2310.08560
- mem0: https://github.com/mem0ai/mem0 · Add Memory https://docs.mem0.ai/core-concepts/memory-operations/add · Control Ingestion https://docs.mem0.ai/cookbooks/essentials/controlling-memory-ingestion
- Graphiti: https://github.com/getzep/graphiti · 博客 https://blog.getzep.com/beyond-static-knowledge-graphs/ · Zep 论文 https://arxiv.org/html/2501.13956v1
- MLEM: https://github.com/iterative/mlem · 对象参考 https://github.com/iterative/mlem.ai/blob/main/content/docs/object-reference/mlem-objects.md · CI/CD https://github.com/iterative/mlem.ai/blob/main/content/docs/use-cases/cicd.md
- modelstore: https://github.com/operatorai/modelstore · CONTRIBUTING https://github.com/operatorai/modelstore/blob/main/modelstore/models/CONTRIBUTING.md · Key Concepts https://modelstore.readthedocs.io/en/latest/concepts/modelstore.html
- HF Model Cards: https://huggingface.co/docs/hub/en/model-cards · 分析论文 https://arxiv.org/html/2402.05160v1
- SageMaker Model Registry: https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry-approve.html
- cognee DataPoints: https://docs.cognee.ai/core-concepts/building-blocks/datapoints · repo https://github.com/topoteretes/cognee
- kernel-memory: https://github.com/microsoft/kernel-memory · Citation 详解 https://medium.com/globant/indexing-and-querying-data-and-documents-using-llm-models-and-natural-language-with-kernel-memory-66804e219de5
- Sanity distillation: https://www.sanity.io/blog/how-we-solved-the-agent-memory-problem
