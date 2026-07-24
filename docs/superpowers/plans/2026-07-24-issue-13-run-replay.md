# Issue #13 — 历史 Run 回放 实施计划

> 分支：`feat/issue-13-run-replay`（基于 issue-12 `b479b35`）
> 设计：`docs/superpowers/specs/2026-07-24-issue-13-run-replay-design.md`

## 实施顺序（TDD）
1. models：`RunReplaySnapshot`（`src/domain/models.py`）
2. core：`get_run_replay`（`src/domain/core.py`）→ `tests/integration/test_domain_core_run_replay.py`
3. ui：`_render_run_replay` 挂 `_render_run_status` → `tests/contract/test_run_replay_ui.py`（AppTest）
4. 验证 + 推送 + Issue 证据

## 测试清单（AC#7）
| AC | 测试 |
|---|---|
| 1 选择器/只读 | `test_get_run_replay_returns_aggregated_snapshot`、`test_replay_does_not_mutate_run_or_instance_files`、`test_replay_read_only_does_not_raise_on_second_view` |
| 2 时间轴 | `test_get_run_replay_returns_aggregated_snapshot`（rounds + plan/code） |
| 3 性能曲线标注 | UI `st.line_chart`（performance_points + Target） |
| 4 SOP 基线 | `test_sop_baselines_matched_by_metric_and_dataset` + UI SOP 表 |
| 5 最佳/目标/差异 | UI `st.metric` ×4 |
| 6 失败/缺失 | `test_failed_round_shows_missing_metric_not_inferred` |
| 7 覆盖 | 以上 + `test_replay_for_unknown_run_raises` |

## 验证（HANDOFF §8）
```bash
cd /Volumes/exp/project/MLagent_v3/.claude/worktrees/issue-13
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m pytest -q
/Volumes/exp/project/MLagent_v3/.venv/bin/python -m compileall -q src tests
UV_CACHE_DIR=/private/tmp/mlagent-uv-cache uv lock --check
git diff --check
```
