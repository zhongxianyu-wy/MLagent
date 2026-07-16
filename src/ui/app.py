from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit executes this file as a script and otherwise omits the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.core import DomainCore
from src.domain.models import (
    ApproveExplorationPlanCommand,
    AuthorizeTrainingCommand,
    DatasetInspection,
    DatasetVersionSnapshot,
    ExplorationReviewSnapshot,
    InspectDatasetCommand,
    RecoverRunCommand,
    RequestRunStopCommand,
    RunStatusSnapshot,
    WorkspaceError,
)
from src.ui.shell import (
    CONTEXT_LABELS,
    build_shell_state,
    sync_detail,
    sync_display,
)


def main() -> None:
    st.set_page_config(
        page_title="MLagent",
        layout="wide",
        initial_sidebar_state="auto",
    )
    _apply_styles()

    connection_path = Path(
        os.environ.get("MLAGENT_WORKSPACE_CONFIG", ".mlagent-workspace.json")
    )
    code_root = Path(os.environ.get("MLAGENT_CODE_ROOT", str(PROJECT_ROOT)))
    try:
        core = DomainCore()
        snapshot = core.open_workspace(connection_path)
        dataset = core.get_dataset_overview(connection_path)
        exploration_review = core.get_exploration_review(
            connection_path,
            code_root,
        )
        run_statuses = core.list_run_statuses(connection_path)
    except WorkspaceError as error:
        st.error(error.message)
        st.caption(error.next_action)
        return

    inspection = st.session_state.get("dataset_inspection")
    shell = build_shell_state(
        snapshot,
        dataset,
        inspection,
        exploration_review,
        run_statuses,
    )
    with st.sidebar:
        st.title("MLagent")
        selected_module = st.radio(
            "Workspace modules",
            shell.navigation,
            label_visibility="collapsed",
        )
        st.caption(
            f"Schema {shell.schema_version} · "
            f"{shell.indexed_assets} indexed · {shell.capacity_text}"
        )

    context_columns = st.columns(5)
    for column, (key, value) in zip(context_columns, shell.context.items()):
        with column:
            if key == "git":
                _render_live_sync_status(
                    core,
                    connection_path,
                    value,
                    shell.git_detail,
                    snapshot.capacity.state,
                )
            else:
                st.metric(CONTEXT_LABELS[key], value)

    st.divider()
    st.subheader(selected_module, anchor=_module_anchor(selected_module))
    st.caption(shell.module_status[selected_module])

    if selected_module == "Dataset Overview":
        _render_dataset_overview(core, shell.dataset, shell.inspection)
    elif selected_module == "Run Status":
        _render_run_status(
            core,
            connection_path,
            code_root,
            shell.exploration_review,
            shell.run_statuses,
        )

    for issue in shell.issues:
        st.warning(f"{issue['message']} {issue['next_action']}")


def _module_anchor(module_name: str) -> str:
    return module_name.lower().replace(" ", "-")


def _render_dataset_overview(
    core: DomainCore,
    dataset: DatasetVersionSnapshot | None,
    inspection: DatasetInspection | None,
) -> None:
    if dataset is None:
        _render_dataset_inspection(core, inspection)
        return

    summary_columns = st.columns(4)
    summary = (
        ("Version", f"v{dataset.version}"),
        ("Samples", str(dataset.sample_count)),
        ("Features", str(dataset.feature_count)),
        ("Task", dataset.task_type),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)

    source_names = ", ".join(
        source["name"] for source in dataset.source_files
    )
    evaluation = (
        f"{dataset.primary_metric} · target {dataset.target_metric:g} · "
        f"{dataset.split_strategy} · seed {dataset.random_seed}"
    )
    if dataset.positive_class is not None:
        evaluation += f" · positive {dataset.positive_class}"
    st.caption(evaluation)
    st.caption(source_names)

    preview_rows = [list(row) for row in dataset.preview.rows]
    if dataset.preview.omitted_count:
        omission_row = ["..."] * len(dataset.preview.columns)
        preview_rows.insert(len(preview_rows) // 2, omission_row)
    st.dataframe(
        pd.DataFrame(preview_rows, columns=dataset.preview.columns),
        hide_index=True,
        width="stretch",
    )

    field_rows = [
        {
            "Field": field,
            "Type": dataset.dtypes[field],
            "Missing": dataset.missing_rates[field],
        }
        for field in dataset.dtypes
    ]
    st.dataframe(
        pd.DataFrame(field_rows),
        hide_index=True,
        width="stretch",
    )
    st.dataframe(
        pd.DataFrame([dataset.class_distribution]),
        hide_index=True,
        width="stretch",
    )
    for warning in dataset.warnings:
        st.warning(warning.replace("_", " ").capitalize())


def _render_dataset_inspection(
    core: DomainCore,
    inspection: DatasetInspection | None,
) -> None:
    feature_path = st.text_input("Feature CSV", key="dataset_feature_path")
    label_path = st.text_input("Label CSV", key="dataset_label_path")
    if st.button("Inspect dataset", type="primary"):
        try:
            inspected = core.inspect_dataset(
                InspectDatasetCommand(
                    feature_path=Path(feature_path),
                    label_path=Path(label_path),
                )
            )
        except WorkspaceError as error:
            st.error(error.message)
            st.caption(error.next_action)
        else:
            st.session_state["dataset_inspection"] = inspected
            st.rerun()

    if inspection is None:
        st.info("No dataset selected")
        return

    summary_columns = st.columns(4)
    summary = (
        ("Samples", str(inspection.sample_count)),
        ("Features", str(inspection.feature_count)),
        ("Task", inspection.inferred_task_type or "Pending confirmation"),
        ("Label", inspection.inferred_label_col or "Pending confirmation"),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)
    st.caption(inspection.content_fingerprint)
    if inspection.unresolved_fields:
        st.warning(", ".join(inspection.unresolved_fields))

    preview_rows = [list(row) for row in inspection.preview.rows]
    if inspection.preview.omitted_count:
        preview_rows.insert(
            len(preview_rows) // 2,
            ["..."] * len(inspection.preview.columns),
        )
    st.dataframe(
        pd.DataFrame(preview_rows, columns=inspection.preview.columns),
        hide_index=True,
        width="stretch",
    )
    field_rows = [
        {
            "Field": field,
            "Type": inspection.dtypes[field],
            "Missing": inspection.missing_rates[field],
        }
        for field in inspection.dtypes
    ]
    st.dataframe(
        pd.DataFrame(field_rows),
        hide_index=True,
        width="stretch",
    )
    st.dataframe(
        pd.DataFrame([inspection.class_distribution]),
        hide_index=True,
        width="stretch",
    )
    for blocker in inspection.blockers:
        st.error(blocker.replace("_", " ").capitalize())
    for warning in inspection.warnings:
        st.warning(warning.replace("_", " ").capitalize())


def _render_run_status(
    core: DomainCore,
    connection_path: Path,
    code_root: Path,
    review: ExplorationReviewSnapshot | None,
    run_statuses: tuple[RunStatusSnapshot, ...],
) -> None:
    if run_statuses:
        run_ids = tuple(status.run_id for status in run_statuses)
        labels = {
            status.run_id: (
                f"{status.run_id} · {_state_label(status.state)} · "
                f"{status.updated_at}"
            )
            for status in run_statuses
        }
        selected_run = st.selectbox(
            "Run",
            run_ids,
            format_func=lambda run_id: labels[run_id],
        )
        _render_live_run(core, connection_path, selected_run)
        st.divider()
    if review is None:
        if not run_statuses:
            st.info("No exploration plan recorded")
        return

    plan = review.plan
    approval_label = {
        "pending_review": "Pending review",
        "approved": "Approved",
        "approval_stale": "Approval stale",
    }.get(review.approval_state, "Failed")
    training_gate = review.training_gate_state.capitalize()
    summary_columns = st.columns(5)
    summary = (
        ("Approval", approval_label),
        ("Training gate", training_gate),
        ("Dataset", f"{plan.dataset_id} v{plan.dataset_version}"),
        ("Rounds", str(len(plan.rounds))),
        ("Target", f"{plan.target_metric:g}"),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)
    st.caption(f"{plan.primary_metric} · {plan.plan_id}")

    st.markdown("**User direction**")
    st.write(plan.user_direction)
    st.markdown("**Baseline hypothesis**")
    st.write(plan.baseline_hypothesis)

    st.markdown("**Exploration rounds**")
    for round_plan in plan.rounds:
        st.markdown(
            f"**Round {round_plan.round_number}: "
            f"{round_plan.optimization_direction}**"
        )
        st.write(round_plan.hypothesis)
        st.caption(" · ".join(round_plan.intended_changes))

    constraint_columns = st.columns(3)
    with constraint_columns[0]:
        st.markdown("**Stop conditions**")
        st.dataframe(
            pd.DataFrame({"Condition": list(plan.stop_conditions)}),
            hide_index=True,
            width="stretch",
        )
    with constraint_columns[1]:
        st.markdown("**Risks**")
        st.dataframe(
            pd.DataFrame({"Risk": list(plan.risks)}),
            hide_index=True,
            width="stretch",
        )
    with constraint_columns[2]:
        st.markdown("**Resource limits**")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Resource": key, "Limit": value}
                    for key, value in plan.resource_limits.items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    excluded = set(plan.excluded_pending_experience_ids)
    active_pending = tuple(
        item for item in plan.pending_experience_ids if item not in excluded
    )
    experience_columns = st.columns(3)
    with experience_columns[0]:
        _render_reference_group(
            "Trusted Experience",
            plan.trusted_experience_ids,
        )
    with experience_columns[1]:
        _render_reference_group(
            "Pending Experience (low confidence)",
            active_pending,
        )
    with experience_columns[2]:
        _render_reference_group(
            "Excluded Pending Experience",
            plan.excluded_pending_experience_ids,
        )

    st.markdown("**Candidate code**")
    previews = {item.path: item for item in review.code_previews}
    selected_path = st.selectbox("Candidate code file", tuple(previews))
    selected = previews[selected_path]
    st.code(
        selected.content,
        language="python" if selected.path.endswith(".py") else None,
    )
    st.caption(
        f"{selected.state} · recorded {selected.recorded_sha256[:12]} · "
        f"current {(selected.current_sha256 or 'unavailable')[:12]}"
    )
    code_is_current = all(item.state == "current" for item in review.code_previews)
    if not code_is_current:
        st.warning("Candidate code changed or is unavailable; record it again before approval.")
    elif review.approval_state == "approval_stale":
        st.warning("The prior approval is stale; approve the current plan and code again.")

    action_columns = st.columns(2)
    with action_columns[0]:
        if st.button(
            "Approve current plan and code",
            type="primary",
            disabled=(
                not code_is_current or review.approval_state == "approved"
            ),
        ):
            try:
                core.approve_exploration_plan(
                    ApproveExplorationPlanCommand(
                        connection_path=connection_path,
                        code_root=code_root,
                        plan_id=plan.plan_id,
                    )
                )
            except WorkspaceError as error:
                st.error(f"{error.code}: {error.message}")
                st.caption(error.next_action)
            else:
                st.rerun()
    with action_columns[1]:
        if st.button("Verify training readiness"):
            try:
                authorization = core.authorize_training(
                    AuthorizeTrainingCommand(
                        connection_path=connection_path,
                        code_root=code_root,
                        entry_point="ui_run_status",
                        dataset_id=plan.dataset_id,
                        dataset_version=plan.dataset_version,
                        plan_id=plan.plan_id,
                        approval_id=(
                            review.approval.asset_id
                            if review.approval is not None
                            else None
                        ),
                    )
                )
            except WorkspaceError as error:
                st.error(f"{error.code}: {error.message}")
                st.caption(error.next_action)
            else:
                st.success(
                    f"Authorized for Issue #5 execution: "
                    f"{authorization.approval_id}"
                )


@st.fragment(run_every=2.0)
def _render_live_sync_status(
    core: DomainCore,
    connection_path: Path,
    initial_status: str,
    initial_detail: str,
    capacity_state: str,
) -> None:
    try:
        status = core.get_sync_status(connection_path)
        value = sync_display(status.state)
        detail = sync_detail(status, capacity_state)
    except WorkspaceError:
        value = initial_status
        detail = initial_detail
    st.metric(
        "Git",
        value,
        delta=detail,
        delta_color="off",
    )


@st.fragment(run_every=2.0)
def _render_live_run(
    core: DomainCore,
    connection_path: Path,
    run_id: str,
) -> None:
    try:
        status = core.get_run_status(connection_path, run_id)
    except WorkspaceError as error:
        st.error(f"{error.code}: {error.message}")
        st.caption(error.next_action)
        return
    summary_columns = st.columns(5)
    summary = (
        ("Run state", _state_label(status.state)),
        ("Round", f"{status.current_round} / {len(status.rounds)}"),
        ("Elapsed", _format_duration(status.elapsed_ms)),
        (
            "Best",
            (
                "Not available"
                if status.best_primary_metric_value is None
                else f"{status.best_primary_metric_value:g}"
            ),
        ),
        ("Target", f"{status.target_metric_value:g}"),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)
    st.caption(
        f"{status.primary_metric_name} · updated {status.updated_at} · "
        f"{status.user_direction}"
    )

    if status.performance_points:
        trend = pd.DataFrame(
            [
                {
                    "Round": point.round_number,
                    status.primary_metric_name: point.primary_metric_value,
                    "Target": status.target_metric_value,
                }
                for point in status.performance_points
            ]
        )
        st.line_chart(
            trend,
            x="Round",
            y=[status.primary_metric_name, "Target"],
        )
    else:
        st.info("No completed performance point")

    round_rows = [
        {
            "Round": round_status.round_number,
            "Instance": round_status.instance_id,
            "Direction": round_status.optimization_direction,
            "Parent": round_status.parent_instance_id or "None",
            "State": _state_label(round_status.instance_state),
            "Duration": _format_duration(round_status.duration_ms),
            "Metric": round_status.primary_metric_value,
            "Model retention": (
                ", ".join(round_status.model_retention_reasons) or "None"
            ),
            "Error": round_status.error_code or "None",
        }
        for round_status in status.rounds
    ]
    if round_rows:
        st.dataframe(
            pd.DataFrame(round_rows),
            hide_index=True,
            width="stretch",
        )

    action_columns = st.columns(3)
    with action_columns[0]:
        if st.button(
            "Stop Run",
            key=f"stop_run_{run_id}",
            type="primary",
            disabled=(status.state != "running" or status.stop_requested),
        ):
            try:
                core.request_run_stop(
                    RequestRunStopCommand(
                        connection_path=connection_path,
                        run_id=run_id,
                    )
                )
            except WorkspaceError as error:
                st.error(f"{error.code}: {error.message}")
                st.caption(error.next_action)
            else:
                st.rerun()
    with action_columns[1]:
        if st.button(
            "Resume Run",
            key=f"resume_run_{run_id}",
            disabled=status.state != "recovery_required",
        ):
            _recover_run(core, connection_path, run_id, "resume")
    with action_columns[2]:
        if st.button(
            "Close Run",
            key=f"close_run_{run_id}",
            disabled=status.state != "recovery_required",
        ):
            _recover_run(core, connection_path, run_id, "close")


def _recover_run(
    core: DomainCore,
    connection_path: Path,
    run_id: str,
    action: str,
) -> None:
    try:
        core.recover_run(
            RecoverRunCommand(
                connection_path=connection_path,
                run_id=run_id,
                action=action,
            )
        )
    except WorkspaceError as error:
        st.error(f"{error.code}: {error.message}")
        st.caption(error.next_action)
    else:
        st.rerun()


def _state_label(state: str) -> str:
    return state.replace("_", " ").capitalize()


def _format_duration(duration_ms: int) -> str:
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(round(seconds), 60)
    return f"{minutes}m {remaining}s"


def _render_reference_group(label: str, references: tuple[str, ...]) -> None:
    st.markdown(f"**{label}**")
    if not references:
        st.caption("None")
        return
    for reference in references:
        st.write(reference)


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ml-text: #1b2528;
            --ml-muted: #657277;
            --ml-border: #d9e0e2;
            --ml-accent: #147d64;
            --ml-warn: #b66a00;
            --ml-fail: #b83b42;
        }
        html, body, [class*="st-"] {
            letter-spacing: 0;
        }
        [data-testid="stAppViewContainer"] {
            background: #f7f9f8;
            color: var(--ml-text);
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--ml-border);
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            min-height: 42px;
            border-radius: 6px;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: #e8f3ef;
            color: #0b5f4c;
        }
        [data-testid="stMetric"] {
            min-height: 76px;
            padding: 4px 0;
            border-bottom: 2px solid var(--ml-border);
        }
        [data-testid="stMetricValue"] {
            font-size: 1rem;
            line-height: 1.3;
            color: var(--ml-text);
        }
        [data-testid="stMetricLabel"] {
            color: var(--ml-muted);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


main()
