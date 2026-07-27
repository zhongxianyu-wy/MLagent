# Issue #15 — Skills/Hooks 生命周期 实施计划

> 分支：`feat/issue-15-skills-hooks`（基于 issue-14 `713710c`）
> 设计：`docs/superpowers/specs/2026-07-27-issue-15-skills-hooks-design.md`

## 顺序
1. models：`SessionContextSnapshot`
2. core：`get_session_context`（聚合 plan/run/experience）
3. session_start + sync_output：context restore 进 additionalContext
4. PostToolUse：`post_tool_use.py` + `.sh` + settings.json
5. Skills：4 SKILL.md
6. 测试 + 验证 + 推送

## 测试（AC）
- AC#1 六 Skills：`test_six_skills_exist_with_required_sections`
- AC#2 SessionStart 恢复：`test_session_context_*`
- AC#3 PreToolUse 不扰只读：现有 training-gate + writes 回归
- AC#4 PostToolUse：`test_post_tool_use_*`
- AC#5 Stop：现有 `test_stop_hook_extracts_current_session_training_candidate`
- AC#6/#7 恢复/幂等：现有 start.json/stop.json file-presence + test_git_sync_hooks
- AC#8 端到端：test_git_sync_hooks（Start→Stop→candidate）

## 验证
```bash
cd /Volumes/exp/project/MLagent_v3/.claude/worktrees/issue-15
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```
