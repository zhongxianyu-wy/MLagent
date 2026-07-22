# Issue #12 — 真实 Claude CLI 接入 实施计划

> 分支：`feat/issue-12-claude-cli`（基于 `feat/issue-11-code-revision` @ `99d4447`）
> 设计：`docs/superpowers/specs/2026-07-22-issue-12-claude-cli-design.md`

## 实施顺序（TDD，先红后绿）

1. **models**（`src/domain/models.py`）：`ClaudeStreamEvent`/`ClaudeCliResult`/
   `ClaudeSessionHandle`/`Start|CaptureClaudeChangesCommand` + `CodeRevisionSnapshot`/
   `SaveCodeRevisionCommand` 加 `agent_prompt_hash`/`agent_tool_summary` →
   `tests/unit/test_claude_models.py`。
2. **code_path_guard**（新 `src/domain/code_path_guard.py`）：纯路径谓词 →
   `tests/unit/test_code_path_guard.py`。
3. **claude_cli_executor**（新 `src/domain/claude_cli_executor.py`）：
   `SubprocessClaudeExecutor` + `DeterministicClaudeExecutor` + NDJSON 解析 →
   `tests/unit/test_claude_cli_executor.py`。
4. **core**（`src/domain/core.py`）：会话方法 + lease + `claude_executor_factory` →
   `tests/integration/test_claude_session_domain.py`；repository 透传 agent_*。
5. **PreToolUse writes**（`.claude/settings.json` + `pre_tool_use_writes.py` + sh）→
   `tests/contract/test_pre_tool_use_writes.py`。
6. **UI**（`src/ui/app.py`：`_render_claude_cli` 子面板）→
   `tests/contract/test_claude_cli_ui.py`（AppTest）。

## 测试清单（8 AC → 具名测试，全 DeterministicClaudeExecutor）

| AC | 测试 |
|---|---|
| 1 真实会话/非模拟 | `test_claude_panel_attach_then_disconnect`（AppTest）+ `SubprocessClaudeExecutor` 真spawn 人工验收 |
| 2 流式/状态可识别 | `test_stream_json_text_events_yielded_in_order`、`test_tool_result_error_event_surfaced`、`test_deterministic_stop_breaks_iteration`、`test_reconnect_after_lease_expiry` |
| 3 Claude 改动→agent revision | `test_capture_changes_creates_agent_origin_revision`、`test_deterministic_touched_files`/`test_summarize_tool_input_redacts_large_args` |
| 4 PreToolUse 写保护 | `test_write_outside_code_root_denied`、`test_write_to_team_memory_namespace_denied`、`test_multiedit_one_bad_target_denies_whole_call`、`test_bash_not_handled_by_writes_hook` |
| 5 单写/交接 | `test_second_write_session_for_same_code_id_rejected`、`test_read_only_viewer_unaffected_by_lease`、`test_handoff_release_then_acquire_succeeds` |
| 6 断开/重连/不破坏 | `test_reconnect_after_lease_expiry`、`test_release_is_idempotent`、`test_capture_stale_parent_rejected`、`test_sealed_instance_not_mutated_by_agent_edit` |
| 7 审计/不存对话 | `test_capture_records_prompt_hash_and_tool_summary`、`test_no_conversation_text`（manifest 无 prompt body） |
| 8 测试覆盖 | 以上即覆盖（流式/工具错误/并发/交接/重连/文件变更） |

## 验证（HANDOFF §8）

```bash
cd /Volumes/exp/project/MLagent_v3/.claude/worktrees/issue-12
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q                       # 全量绿（容忍原 3 环境失败）
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check                            # 不加依赖
git diff --check
```

真实 CLI 人工验收：UI Attach → 发真实 prompt → 观察流式文本/工具状态 → Capture 成 agent revision。
