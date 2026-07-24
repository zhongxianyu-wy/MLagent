# Issue #14 — 谱系图和时间线 设计

> 分支：`feat/issue-14-lineage`（基于 issue-13 `f537f7a`）
> 日期：2026-07-24
> 状态：已实现，等待人工验收（`ready-for-human`）

## 1. 背景

"Lineage Trace" 是 NAVIGATION 第 6 模块，此前空壳。#14 填充：跨资产血缘图 + 时间线，
让研究人员从任意节点（Dataset/Plan/Run/Instance/Experience/Notebook/SOP/Code Revision/Formal Model）
回溯来源关系；Formal Model ≤3 跳回溯到 SOP→来源 Instance→Raw Record；**检测断裂引用并阻止
正式审批**（AC#7）。

## 2. 设计

### 模型（`models.py`）
`LineageNode(node_type, asset_id, version, state, primary_metric_value, missing_evidence, created_at, label)` + `.key`；
`LineageEdge(source_key, target_key, kind, detail)`；`LineageGraph(nodes, edges, broken_refs)`。
7 种边类型（source/used/produced/reproduced/approved/superseded/model_registered），9 种节点类型。

### `DomainCore.get_lineage(connection_path) -> LineageGraph`（纯读 aggregator）
枚举资产（dataset/plan/run/instance/sop_candidate/sop_version/formal_model/experience/notebook）+
从 FK 字段建边（照 Explore 映射表）+ `broken_refs`（edge target 不在 nodes）。复用 `get_run_replay`
模式；invalid SOP version（source 缺失）容忍跳过。

### `verify_lineage_integrity` / `_verify_candidate_lineage`（AC#7）
返回 broken_refs；`review_sop_candidate` 前置检查，若 candidate 来源链 broken →
`WorkspaceError(code="lineage_broken")` 阻止审批。

### UI `_render_lineage`（`app.py`，新 dispatch 分支）
DOT 字串 → `st.graphviz_chart`（零依赖，前端 viz.js）+ 类型过滤 `st.selectbox` + 时间线表
（按 created_at）+ broken 警告（`st.warning`）+ missing 节点红色。图渲染失败退化为边表。

## 3. 边界保证
- **AC#5**：Experience 无字段指向 SOP（只 used 边到 run/instance/dataset），结构上不可能成为 SOP 来源。
- **AC#6**：SOP retrain = 新 Run+Instance，不改 SOP version（独立 run 节点分支，不合并 version 链）。

## 4. 测试（AC#8）
`test_lineage_links_dataset_through_run_instance_to_sop_and_model`（完整链，Formal Model ≤3 跳）、
`test_experience_only_used_never_sop_source`（AC#5）、
`test_broken_ref_detected_and_review_blocked`（AC#7）、
`test_retrain_run_branches_not_merges_into_sop_version`（AC#6）+ AppTest。
