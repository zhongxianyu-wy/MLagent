# Issue #11 — Code Revision 实施计划

> 分支：`feat/issue-11-code-revision`（基于 `feat/issue-10-sop-retraining` @ `66cfc20`）
> 日期：2026-07-22
> 设计：`docs/superpowers/specs/2026-07-22-issue-11-code-revision-design.md`

## 实施顺序（TDD，先红后绿）

1. **models**（`src/domain/models.py`）：`_CODE_REVISION_ORIGINS`、读模型、`CodeRevisionSnapshot`、
   `EditedFile`、`SaveCodeRevisionCommand` → `tests/unit/test_code_revision_models.py`。
2. **repository**（`src/domain/code_revision_repository.py`，新增）：原子 tmp+rename、幂等、篡改
   检测、容量门禁 → `tests/integration/test_code_revision_repository.py`。
3. **core**（`src/domain/core.py`）：8 个方法 + `_code_revision_repository` helper +
   `_discover_managed_files` + `_find_instances_for_fingerprint` →
   `tests/integration/test_domain_core_code_review.py`。
4. **冻结隔离**：扩展 `tests/integration/test_run_repository.py`（AC#6）。
5. **shell**（`src/ui/shell.py`）：`GLOBAL_STATUS_VOCABULARY` 加 "Workspace changed"；
   `build_shell_state(code_review_status=...)`。
6. **app**（`src/ui/app.py`）：`_render_code_review` + dispatch 分支 + 顶层 `get_code_review`
   读取（独立 try，不阻塞其它模块）。
7. **contract**（`tests/contract/test_code_review_contract.py`）：UI 不直接 IO、写经 core、
   vocabulary 合法。
8. **AppTest 验收**（`tests/integration/test_code_review_ui.py`）：register → 文件树 → save →
   history 端到端。

## 测试清单（AC → 具名测试）

| AC | 测试 |
|---|---|
| 1 文件树/查看/编辑/jail | `test_list_managed_files_returns_only_python_under_root`、`test_list_managed_files_blocks_paths_outside_managed_root`、`test_read_managed_file_returns_bytes_and_blocks_escape`、`test_ui_reads_managed_code_only_through_domain_core` |
| 2 Active/Frozen 只读 | `test_active_revision_referenced_by_instance_is_marked_frozen` |
| 3 save→新版本不改 active | `test_save_creates_new_version_without_mutating_parent`、`test_repeated_save_with_same_fingerprint_returns_existing_v1`、`test_tampered_code_revision_file_is_rejected_on_reload`、`test_capacity_failure_leaves_no_partial_code_revision` |
| 4 diff/历史/作者/来源/run | `test_diff_code_revisions_reports_modified_file`、`test_history_lists_origin_author_time_and_related_run` |
| 5 自动刷新+明确冲突 | `test_workspace_change_is_detected_at_read_time`、`test_concurrent_save_raises_stale_code_revision` |
| 6 冻结隔离 | `test_training_instance_keeps_frozen_revision_after_candidate_edit` |
| 7 origin 审计/不存输入 | `test_manifest_records_origin_human_agent_system`、`test_manifest_does_not_store_editor_input_content` |
| 8 历史/回看 diff | `test_diff_against_older_version_renders_rollback_view` |

## 复用的现有机制（禁止重复实现）

- `_code_fingerprint` / `_fingerprint`（`exploration_repository.py`）→ 复制为
  `compute_code_fingerprint` 于新 repository。
- `DomainCore._require_managed_code_root`（`core.py`）。
- `RunRepository._validate_source_file` / `_safe_relative`（jail 范式）。
- `DatasetRepository`：原子写、幂等、篡改检测、`_version_numbers`、可注入 clock/id。
- `SopVersionSnapshot.__post_init__`（parent 链 + change_summary 规则）。
- 乐观并发 `expected_*_fingerprint` → `stale_*`；`WorkspaceError(code, message, next_action)`。
- UI 写入惯用语 `*Command` + `_render_action_error` + `st.rerun()`。

## 验证（HANDOFF §8）

```bash
cd /Volumes/exp/project/MLagent_v3/.claude/worktrees/issue-11
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```

UI：AppTest 程序化验收（register/save/history）通过；桌面/移动真实浏览器视觉与响应式
验收为人工门禁（`ready-for-human`）。
