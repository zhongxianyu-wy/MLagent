# Issue #16 — MVP 安全/恢复/容量/性能/全量验收 实施计划（含验收矩阵）

> 分支：`feat/issue-16-mvp-acceptance`（基于 issue-15 `2596c5a`）
> 运行手册：`docs/development/operations-runbook.md`

## Context
v0.4 MVP 收尾。Explore 审计确认 AC#2-7 大部分已被 #2-#15 测试覆盖；#16 补明确缺口 + 端到端演示 + 运行手册。

## 验收矩阵（8 AC → 证据）

| AC | 证据（测试/文档） |
|---|---|
| 1 六 UI 模块/导航/状态词汇 | `test_ui_shell.py`（#2-#8）+ 各模块 AppTest（#9-#14） |
| 2 性能（Run<2s/Dataset<3s） | `test_run_status_renders_within_budget`（#16）+ `test_dataset_overview_ui.py:187`（<3s） |
| 3 安全（凭据/路径/越界/未授权/第二写） | `test_bootstrapped_team_memory_has_no_credentials`、`test_claude_exit_releases_session`（#16）+ `test_code_path_guard`/`test_pre_tool_use_writes`/`test_unauthorized_approval`/`test_second_write_session_*`（#11/#12） |
| 4 容量（100MB/20GB/磁盘/保留） | `test_disk_full_leaves_no_partial_asset`（#16）+ `test_capacity_failure_leaves_no_partial_*`/`test_model_at_single_file_limit`（#2/#5） |
| 5 恢复（冲突/远端/退出/重启/中断/重放） | `test_complete_session_double_fire_is_idempotent`（#16）+ `test_same_path_divergence_*`/`test_unavailable_remote_*`/`test_recovery_resume_*`/`test_domain_core_reopens_*`（#5/#6） |
| 6 非权威（LocalIndex/MLflow/mem0/AIDE） | `test_local_index_deletion_is_recoverable`（#16）+ `test_local_index_rebuild.py`（#2） |
| 7 范围排除（回归/DL/GPU/NGS/auto/LFS/公开） | `test_bootstrapped_repo_has_no_lfs`、`test_regression_task_type_rejected`（#16）+ `test_unsupported_task`（#3） |
| 8 端到端/演示/运行手册 | `test_mvp_lifecycle_e2e`（#16）+ `docs/development/operations-runbook.md` |

## 实现
1. `test_mvp_acceptance.py`（AC#2/3/4/5/6/7 缺口）
2. `test_mvp_lifecycle_e2e.py`（AC#8）
3. `docs/development/operations-runbook.md`
4. 验证 + 推送

## 验证
```bash
cd /Volumes/exp/project/MLagent_v3/.claude/worktrees/issue-16
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```
