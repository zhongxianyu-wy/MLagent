# Issue #12 — 真实 Claude Code CLI 接入 Code Review 设计

> 分支：`feat/issue-12-claude-cli`（基于 `feat/issue-11-code-revision` @ `99d4447`）
> 日期：2026-07-22
> 状态：已实现，等待人工验收（`ready-for-human`）

## 1. 背景与目标

把**一个真实 Claude Code CLI 会话**接入 Code Review：研究人员发提示词给真实 `claude`
子进程（v2.1.170，`-p` / `--output-format stream-json` / `--resume`），流式看文本/工具/错误
输出；Claude 对受管代码的修改经 DomainCore 转成 `origin="agent"` 的 Code Revision，进入
**同一** Diff/历史/审计界面。此前 MLagent 没有任何真实 `claude` CLI 调用（现有 LLM 是非流式
HTTP urllib）。

## 2. 测试策略（关键）

真实 CLI 调用是**人工验收门禁**（同 training 的真实 executor）。所有 8 AC 的自动化测试用
注入的 `DeterministicClaudeExecutor`（脚本化流式事件），不真调 claude——CI 完全 hermetic。

## 3. 不可违反的边界（HANDOFF §3）

UI 写经 DomainCore（§3.14）；失败不留半正式资产；冻结层不可变；PreToolUse 拦截越界写与
未批准训练；受管资产写入仍经 DomainCore。

## 4. 设计概要

### 4.1 `ClaudeCliExecutor`（新 `src/domain/claude_cli_executor.py`，可注入）

- `SubprocessClaudeExecutor`（生产）：复用 `SubprocessTrainingExecutor` 生命周期骨架
  （`Popen(start_new_session=True)` + 轮询 `stop_requested` + `time.monotonic()` 超时 +
  `os.killpg` 升级）。命令 `claude -p <prompt> --output-format stream-json [--resume <sid>]`，
  设 `env["CLAUDE_PROJECT_DIR"]=workspace`、`cwd=code_root`（让 PreToolUse hook 生效）。线程
  逐行读 NDJSON → `parse_stream_json_line` → `queue.Queue` → iterator 消费（真实转发器）。
  未知 `type` 归为 `system`（永不崩）。
- `DeterministicClaudeExecutor`（测试）：yield 脚本事件 + 返回脚本 `ClaudeCliResult`。
- 接口：`execute(prompt, *, cwd, workspace, session_id, allowed_tools, stop_requested,
  timeout_seconds) -> (Iterator[ClaudeStreamEvent], Callable[[], ClaudeCliResult])`。result
  用 callable（Subprocess 的 result 在流结束后才确定）。

### 4.2 DomainCore 会话方法（`src/domain/core.py`）

`start_claude_session` / `send_claude_prompt` / `capture_claude_changes` /
`release_claude_session` / `claude_session_status`，+ `claude_executor_factory` /
`claude_lease_store_factory` / `claude_epoch_clock` / `claude_lease_ttl_seconds` 注入参数。

- `capture_claude_changes`：`_discover_managed_files` → 为 `touched_files` 组装 `EditedFile`
  → **直接调 `save_code_revision`**（verbatim，`origin="agent"`，透传 `agent_prompt_hash`/
  `agent_tool_summary`）。
- `send_claude_prompt`：透传 executor，`stop_requested` 绑定 per-handle。

### 4.3 单写锁（AC#5）—— 复用 `IdleSchedulerLeaseStore`

复合 key `f"claude_write_session:{code_id}"`（store 无 workspace 列，code_id 已是稳定 key）。
TTL lease 跨进程存活（UI 崩溃 → TTL 到期自愈，AC#6）。只读 viewer 不取 lease。交接 =
release + acquire。

### 4.4 PreToolUse 写保护（AC#4）—— 新 adapter

`.claude/settings.json` 追加 `Write|Edit|MultiEdit|NotebookEdit` matcher →
`.claude/hooks/mlagent-write-jail.sh` → `src/agent/pre_tool_use_writes.py`（用新
`src/domain/code_path_guard.py` 纯谓词：从 `_require_managed_code_root` 提取 + Team Memory
命名空间拒绝）。Bash/explore matcher 不动（训练门禁不变）。子进程 claude 因
`CLAUDE_PROJECT_DIR=workspace` 读该 settings.json，hook 生效。

### 4.5 审计（AC#7）—— 挂在 Code Revision

扩展 `CodeRevisionSnapshot` + manifest + `SaveCodeRevisionCommand` 加 `agent_prompt_hash`
（提示 sha256）+ `agent_tool_summary`（可选，仅 origin=agent）。`ClaudeStreamEvent.text` 永不
持久化——AC#7"不存完整对话"在类型层保证。

### 4.6 UI（`src/ui/app.py`：`_render_claude_cli` 子面板）

不改 NAVIGATION。在 `_render_code_review` 末尾加子面板：`session_state["claude_handle"]` 持
会话；Attach / Prompt+Send(`st.write_stream`) / Capture / Disconnect；状态 caption（经
`claude_session_status`）。

## 5. 关键决策汇总

| 项 | 决策 | 理由 |
|---|---|---|
| 测试 | 全 `DeterministicClaudeExecutor`，真实 CLI 人工验收 | hermetic CI；同 training executor |
| 单写锁 | `IdleSchedulerLeaseStore` 复合 key | 跨进程存活（AC#6）；复用现有 |
| PreToolUse | 新 `pre_tool_use_writes.py`，不动 `pre_tool_use.py` | 单一职责；避免高冲突 |
| 写 jail | 新 `code_path_guard.py` 纯谓词 | hook 与 DomainCore 共享 |
| 审计 | Code Revision 加两字段 | 直接满足 AC#7，不动 run_repository |
| 流式 | `st.write_stream(generator)` | Streamlit 原生 |
| executor 返回 | `(iterator, result_getter)` | Subprocess result 流后才定 |

## 6. 复用现有机制（禁止重复实现）

`SubprocessTrainingExecutor` 生命周期；`training_executor_factory` 注入模式；
`save_code_revision`（capture sink）；`_require_managed_code_root`/`_discover_managed_files`；
`IdleSchedulerLeaseStore`；PreToolUse deny 形状；`_render_action_error` + `st.write_stream`。
