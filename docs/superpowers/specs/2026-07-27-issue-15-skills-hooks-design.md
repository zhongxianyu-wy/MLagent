# Issue #15 — 六 Skills 与四 Hooks 生命周期集成 设计

> 分支：`feat/issue-15-skills-hooks`（基于 issue-14 `713710c`）
> 日期：2026-07-27
> 状态：已实现，等待人工验收（`ready-for-human`）

## 1. 背景
把六个 Skills + 四个 Hooks 串成完整、可恢复、可审核的会话生命周期。此前 skills 缺 4（bootstrap-memory/intake-data/retrain-from-sop/instance-to-sop）、PostToolUse hook 完全缺失、SessionStart 缺 context restore；幂等/恢复已有（file-presence + Git team memory）。

## 2. 实现

### 四个 SKILL.md（mirror `design-and-explore` 模板）
新 `.claude/skills/{bootstrap-memory,intake-data,retrain-from-sop,instance-to-sop}/SKILL.md`，每个含 frontmatter(name/description) + Boundary + Workflow + Outputs + Failure。映射到 DomainCore 入口（bootstrap→`bootstrap_memory`、intake→`inspect/confirm_dataset`、retrain→`retrain_from_sop`、instance-to-sop→`create/reproduce/review_sop_candidate`）。

### `DomainCore.get_session_context`（AC#2 context restore，纯读）
聚合 latest plan（`exploration.latest`）、recent run（`list_run_statuses[0]`）、pending experiences（`list_experiences` state=pending）→ `SessionContextSnapshot`。`session_start.py` 把它写进 `additionalContext`（`bounded_session_context`）。

### PostToolUse hook（AC#4，新）
`.claude/hooks/mlagent-post-tool-use.sh` + `src/agent/post_tool_use.py` + settings.json matcher(`Write|Edit|MultiEdit|NotebookEdit`)。捕获 `get_code_review.workspace_changed` → additionalContext 提示"Code workspace changed; capture in Code Review"。**不复制终端/tool_response**。

### 生命周期（AC#6/#7/#8）
复用现有幂等：`start_session`/`complete_session` 的 file-presence（start.json/stop.json）；恢复 = 全状态在 Git team memory + LocalIndex.rebuild；现有 `test_git_sync_hooks` 覆盖 Start→Stop→candidate 提取。

## 3. 测试
`test_post_tool_use`（unit：捕获 change/不复制终端/非 capture 工具忽略）、`test_skills_lifecycle`（contract：6 SKILL.md + frontmatter + Boundary/Workflow）、`test_session_context`（restore + 只读）。
