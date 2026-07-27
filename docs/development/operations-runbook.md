# MLagent v0.4 Operations Runbook

> 本地研究工作流运维手册：恢复、容量、安全、范围、非权威组件。

## 1. 恢复（Resilience）

| 故障 | 行为 | 恢复 |
|---|---|---|
| Git 冲突（同路径双分支） | `SyncStatusSnapshot.state="conflict"`，保留本地提交 | 人工审查两版本，经 DomainCore 工作流解决 |
| 远端不可用 | 本地提交保留，`state="pending_sync"` | 下次 SessionStart 自动重试（`GitSyncService`） |
| Claude 退出/崩溃 | 写会话 lease 在 TTL（900s）后过期 | 重新 Attach（`start_claude_session`），或等 TTL 自愈 |
| UI 重启/关闭 | 全状态在 Git team memory + 磁盘 lease/index | 新进程重读连接 + `LocalIndex.rebuild()` 恢复 |
| 训练中断 | Run `recovery_required`（`recover_run`） | `recover_run(action="resume"/"close")` 从冻结代码恢复 |
| Hook 重放 | `start.json`/`stop.json` file-presence 幂等 | 重复触发无害（返回缓存 outcome） |

**关键不变量**：已批准资产（SOP Version / Formal Model / sealed Instance）不可变，任何故障都不损坏它们。

## 2. 容量（Capacity）

- 单文件上限 **100 MB**（`MAX_FILE_BYTES`），仓库上限 **20 GB**（`MAX_REPOSITORY_BYTES`）——`src/domain/memory_repository.py:39-40`。
- 超限写 → `WorkspaceError(code="file_too_large"/"repository_capacity_exceeded")`，**不留半正式资产**（原子 tmp+rename）。
- 磁盘不足（ENOSPC）→ 同样不留 partial（`test_disk_full_leaves_no_partial_asset`）。
- 模型保留：超单文件限的模型 `model_retention_reasons=("rejected_too_large",)`，不进 Formal Model。

## 3. 安全（Security）

- **凭据**：API key 从 `.env`/env 读（`provider/config.py`），**不写入 team memory**（`test_bootstrapped_team_memory_has_no_credentials`）。
- **路径遍历/越界写**：`_require_managed_code_root` + `code_path_guard.validate_write_target` 拒绝 code_root 外写入；PreToolUse Write/Edit/MultiEdit/NotebookEdit matcher jail。
- **未授权审批**：`review_sop_candidate` 校验 reviewer-policy 指纹（`unauthorized_sop_reviewer`）；无自动审批（`_SOP_REVIEW_DECISIONS={approve,reject}`）。
- **单写会话**：`IdleSchedulerLeaseStore` 复合 key `claude_write_session:{code_id}`，第二写会话 `claude_session_busy`。

## 4. 范围排除（Out of MVP scope）

明确**不支持**（HANDOFF §3.15 / PRD §5.2）：
- 回归、深度学习、GPU 编排、分布式训练（`task_type` 仅 binary/multiclass；`unsupported_task`）。
- 原始 NGS 处理（FASTQ/BAM）。
- 自动批准 Experience/SOP/Formal Model。
- Git LFS、对象存储、多仓库联邦、公网远程 UI（`test_bootstrapped_repo_has_no_lfs`）。
- 无人值守梦境/持续自主实验。

## 5. 非权威组件（Non-authoritative）

LocalIndex / MLflow / mem0 / ChromaDB / AIDE **都不是权威**：
- **LocalIndex**：可删除重建（`LocalIndex.rebuild()`，`test_local_index_deletion_is_recoverable`）。
- **Git team memory** 是唯一事实来源；所有派生组件缺失/损坏都不丢失权威资产。

## 6. 验证命令

```bash
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```
