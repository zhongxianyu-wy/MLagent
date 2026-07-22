# Issue #11 — Code Revision 设计

> 分支：`feat/issue-11-code-revision`（基于 `feat/issue-10-sop-retraining` @ `66cfc20`）
> 日期：2026-07-22
> 状态：已实现，等待人工验收（`ready-for-human`）

## 1. 背景与目标

"Code Review" UI 模块此前是空壳（`shell.py` 注册了导航，但 `app.py` 无 dispatch 分支）。
冻结层 `FrozenCodeRevisionSnapshot` 已经保证 Training Instance 的代码不可变，但**没有
可编辑、可版本化的 revision 层**——研究人员无法在 UI 中查看受管代码、直接编辑，也无法
理解每次修改的 diff、历史与来源。

本 Issue 在**不动冻结层**的前提下，新增一层"可编辑 Code Revision"：人工 / 智能体 / 系统
编辑产生新的不可变 revision（带 parent 链 + origin + 审计），形成版本族；Active/Frozen
状态、Run/Instance 关联均为**派生**事实。

## 2. 不可违反的产品边界（HANDOFF §3）

- UI 所有读写都经 DomainCore（§3.14）；UI 不得直接读写 Team Memory 文件。
- 业务规则只在 DomainCore / 领域服务实现一次。
- 不可变资产须有 schema_version / id / actor / timestamp / provenance。
- 失败、中断、权限不足不留半正式资产。
- 冻结层 `FrozenCodeRevisionSnapshot` 与 `freeze_code_revision` **保持原样**。

## 3. 数据模型（`src/domain/models.py`）

复用 `CandidateCodeFile`（`{path, sha256, size_bytes}`），**不**新建别名类型。

- `CodeRevisionSnapshot`（不可变，parent 链）：`asset_id, asset_path, code_id, version,
  revision_fingerprint, parent_revision_id, parent_revision_fingerprint, code_fingerprint
  (= revision_fingerprint，镜像冻结层词汇), entrypoint_path, files: tuple[CandidateCodeFile,...],
  origin, source_run_id, source_instance_id, change_summary, created_at, created_by,
  asset_type="code_revision"`。`__post_init__` 校验 safe_id/sha256/origin；v1 禁 parent +
  允许空 change_summary；v>1 要求 parent + change_summary；entrypoint 必须是 files 中已登记
  的 `.py`；files 非空。
- 读模型：`ManagedFileEntry`、`CodeFileDelta`、`CodeReviewSnapshot`、`CodeRevisionDiff`。
- 命令：`EditedFile(path, content: bytes)`、`SaveCodeRevisionCommand`。
- 新 enum：`_CODE_REVISION_ORIGINS = frozenset({"human", "agent", "system"})`；
  `CODE_REVISION_SCHEMA_VERSION = 1`。

**关键决策：revision 上不存 `state`。** AC#2 的 "Active/Frozen" 是派生 UI 事实——某 revision
被 instance 引用（`code_fingerprint` 匹配）即为 frozen；存 state 会迫使 run 启动时改 revision（违规）。

## 4. 存储（`src/domain/code_revision_repository.py`，新增）

```
<team-memory>/code-revisions/<code_id>/v<NNNN>/{manifest.json, files/<rel>}
<team-memory>/code-revisions/.bindings/<rel-path-hash>.json   # code_id 绑定（唯一可变指针）
```

顶层 `code-revisions/` 与冻结层 `runs/<run_id>/code-revisions/` 命名空间不冲突。镜像
`DatasetRepository`：原子 tmp+rename 写、幂等（同 `revision_fingerprint` 返回已有）、加载
篡改检测（重算 `_code_fingerprint` 与 manifest 指纹）、容量门禁、可注入 clock/id。

## 5. DomainCore 方法（全部经 `_require_managed_code_root`）

`get_code_review / save_code_revision / list_code_revisions / diff_code_revisions /
read_managed_file / list_managed_files / resolve_code_id / register_code_id`。

- `save_code_revision` 单步原子：门禁 → family 级乐观并发（`expected_parent_fingerprint`
  → `stale_code_revision`）→ jail 内写编辑字节回工作区 → 重读全部受管 `.py` 算指纹 → 创建
  revision。失败回滚不留半正式资产。
- `get_code_review` 派生：`active_revision = history[0]`；`workspace_changed`（工作区指纹 ≠
  active）；`active_instance_refs`（扫 `runs/*/instances/*/manifest.json` 的 `code_fingerprint`
  匹配 active）。**AC#4 Run/Instance 关联是派生，不存储。**
- `diff_code_revisions` 用 `difflib.unified_diff`（stdlib）。

## 6. `code_id` 身份

`sop_id`/`dataset_id` 是用户提供的稳定 slug。照此：**`code_id` = 用户首次输入的 slug**，绑定
存 `code-revisions/.bindings/<sha256(rel-path)[:16]>.json`。键用相对路径（绝对工作区移动不破
坏）。binding 丢失 → UI 重新提示输入相同 slug 即可重关联磁盘上的 revision（无数据丢失）。

## 7. 冲突与自动刷新（AC#5）

- family 级：`expected_parent_fingerprint` 比对最新 revision → `stale_code_revision`，UI 经
  `_render_action_error` 显示且**不** `st.rerun()`（用户须明确重载）。
- 自动刷新：`get_code_review` 每次读时重算工作区指纹与 active 比对 → `workspace_changed`；
  **不依赖** `GitSyncService`（避免第二真相源）。

## 8. 关键决策汇总

| 项 | 决策 | 理由 |
|---|---|---|
| 编辑器 | `st.text_area`（不加 streamlit-ace） | 无 `uv lock` churn、移动端兼容、最小范围 |
| 范围 | 不改 freeze 源；不含 "从 revision 启动 run" | AC 未要求；高冲突 |
| Run/Instance 关联 | 派生（指纹匹配），不存储 | revision 无需知道 run |
| AC#6 冻结隔离 | 目录命名空间隔离天然成立 | `runs/<run>/code-revisions/` ≠ `code-revisions/<code_id>/` |
| revision.state | 不存 | 派生事实；存则违不可变 |
| save 流程 | 单步原子 | 原子性 + 最小 UI 状态 |
