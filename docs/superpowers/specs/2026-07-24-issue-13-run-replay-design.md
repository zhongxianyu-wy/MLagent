# Issue #13 — 历史 Run 回放与性能比较 设计

> 分支：`feat/issue-13-run-replay`（基于 `feat/issue-12-claude-cli` @ `b479b35`）
> 日期：2026-07-24
> 状态：已实现，等待人工验收（`ready-for-human`）

## 1. 背景与目标

Run Status 模块此前只显示当前 run 的实时状态。#13 加**历史回放**：选已封存 Run，沿时间轴还原
每轮（计划/代码/实例/状态/指标），性能曲线 + SOP 基线叠加，展示最佳/目标/差异，失败或不完整
Run 显示**缺失区段而非推断**。全部**只读**。

## 2. 关键发现（Explore）

`RunStatusSnapshot`（`models.py:1629`）**已是聚合快照**：`rounds`（`RunRoundSnapshot`：round/
instance/direction/parent/state/metric/error）、`performance_points`、`best_primary_metric_value`、
`target_metric_value`、`target_gap`、`stop_reason`、`recovery_reason`。`RunRepository.status()` 纯读
不写。失败 round 在模型层强制 `primary_metric_value=None`+`error_code`（缺失区段天然可表示）。
所以 #13 = **一个纯读 aggregator + 一个 UI 子视图**。

## 3. 设计

### `DomainCore.get_run_replay(connection_path, run_id) -> RunReplaySnapshot`（纯读 aggregator）

复用现有读组合（仿 `get_exploration_review`/`get_code_review`）：
- `run = get_run_status(run_id)`
- `start = run_repository.load_run_start(run_id)` → `plan_id`/`code_fingerprint`
- `plan = exploration.load_plan_event(...)`；`code_entrypoint = run_repository.load_code_revision(...).entrypoint_path`
- `sop_baselines = [v for v in sop.list_sop_versions() if v.primary_metric_name == run.primary_metric_name and v.dataset_id == run.dataset_id and v.dataset_version == run.dataset_version]`（无 run→SOP 外键，按 metric+dataset 派生匹配，AC#4）

### `RunReplaySnapshot`（`models.py`）

`run: RunStatusSnapshot`、`plan: ExplorationPlanSnapshot | None`、`code_revision_fingerprint: str | None`、
`code_entrypoint: str | None`、`sop_baselines: tuple[SopVersionSnapshot, ...]`。

### UI `_render_run_replay`（`src/ui/app.py`，挂 `_render_run_status` 内 `selected_run` 后）

- 最佳/目标/差异：`st.metric` ×4（State/Best/Target/Target gap）
- 时间轴表：`run.rounds`（Round/Direction/Parent/State/Metric/Error；失败轮 Metric="missing"，不推断）
- 性能曲线：`st.line_chart`（performance_points + Target）
- SOP 基线表（区分 SOP 结果/复现/正式）
- plan/code 摘要 caption
- 非 completed → `st.warning(stop_reason/recovery_reason)`；无 performance_points → `st.info`

## 4. 复用

`get_run_status`/`list_sop_versions`/`load_run_start`/`load_plan_event`/`load_code_revision`；
`st.line_chart`+`st.metric`+`_state_label`+`_render_action_error`+`st.info`/`st.warning` 缺失模式。

## 5. 测试（AC#7）

`test_get_run_replay_returns_aggregated_snapshot`、`test_sop_baselines_matched_by_metric_and_dataset`、
`test_replay_does_not_mutate_run_or_instance_files`（只读）、`test_failed_round_shows_missing_metric_not_inferred`、
`test_replay_for_unknown_run_raises` + AppTest（`test_run_replay_renders_in_run_status`、
`test_run_replay_read_only_does_not_raise_on_second_view`）。
