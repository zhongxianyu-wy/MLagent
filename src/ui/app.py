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
    CreateSopCandidateCommand,
    DatasetInspection,
    DatasetVersionSnapshot,
    ExperienceContent,
    ExperienceSnapshot,
    ExplorationReviewSnapshot,
    InspectDatasetCommand,
    RecoverRunCommand,
    ReproduceSopCandidateCommand,
    RequestRunStopCommand,
    ReviewExperienceCommand,
    ReviewSopCandidateCommand,
    RunStatusSnapshot,
    SopCandidateStatus,
    SopVersionSnapshot,
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
        experiences = core.list_experiences(connection_path)
        sop_candidates = core.list_sop_candidate_statuses(connection_path)
        sop_versions = core.list_sop_versions(connection_path)
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
        experiences,
        sop_candidates,
        sop_versions,
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
    elif selected_module == "Experience Review":
        _render_experience_review(
            core,
            connection_path,
            shell.experiences,
        )
    elif selected_module == "SOP Overview":
        _render_sop_overview(
            core,
            connection_path,
            shell.run_statuses,
            shell.sop_candidates,
            shell.sop_versions,
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


def _render_sop_overview(
    core: DomainCore,
    connection_path: Path,
    run_statuses: tuple[RunStatusSnapshot, ...],
    candidates: tuple[SopCandidateStatus, ...],
    versions: tuple[SopVersionSnapshot, ...],
) -> None:
    candidate_tab, version_tab = st.tabs(
        ("Candidates", "Approved Versions")
    )
    with candidate_tab:
        _render_sop_candidate_workspace(
            core,
            connection_path,
            run_statuses,
            candidates,
        )
    with version_tab:
        _render_sop_versions(core, connection_path, versions)


def _render_sop_candidate_workspace(
    core: DomainCore,
    connection_path: Path,
    run_statuses: tuple[RunStatusSnapshot, ...],
    candidates: tuple[SopCandidateStatus, ...],
) -> None:
    eligible = tuple(
        (status.run_id, round_status.instance_id)
        for status in run_statuses
        for round_status in status.rounds
        if round_status.instance_state == "completed"
        and bool(round_status.model_retention_reasons)
        and "sop_reproduction"
        not in round_status.model_retention_reasons
    )
    source_labels = {
        source: f"{source[0]} · {source[1]}" for source in eligible
    }
    with st.form("create_sop_candidate"):
        source = st.selectbox(
            "Source Training Instance",
            eligible,
            format_func=lambda value: source_labels[value],
            index=0 if eligible else None,
            placeholder="Select a retained successful instance",
            disabled=not eligible,
        )
        identity_columns = st.columns(2)
        with identity_columns[0]:
            sop_id = st.text_input("SOP ID")
        with identity_columns[1]:
            name = st.text_input("SOP name")
        strategy_summary = st.text_area("Strategy summary")
        optimization_background = st.text_area(
            "Optimization background"
        )
        steps_text = st.text_area("Steps")
        change_summary = st.text_area("Change summary")
        create = st.form_submit_button(
            "Create candidate",
            type="primary",
            disabled=source is None,
        )
    if create and source is not None:
        steps = tuple(
            line.strip()
            for line in steps_text.splitlines()
            if line.strip()
        )
        try:
            core.create_sop_candidate(
                CreateSopCandidateCommand(
                    connection_path=connection_path,
                    sop_id=sop_id,
                    name=name,
                    source_run_id=source[0],
                    source_instance_id=source[1],
                    strategy_summary=strategy_summary,
                    optimization_background=optimization_background,
                    steps=steps,
                    change_summary=change_summary,
                )
            )
        except (ValueError, WorkspaceError) as error:
            _render_action_error(error)
        else:
            st.rerun()

    if not candidates:
        st.info("No SOP candidates")
        return
    labels = {
        item.candidate.asset_id: (
            f"{item.candidate.name} · {_state_label(item.state)} · "
            f"{item.candidate.created_at}"
        )
        for item in candidates
    }
    selected_id = st.selectbox(
        "SOP candidate",
        tuple(labels),
        format_func=lambda value: labels[value],
    )
    selected = next(
        item for item in candidates if item.candidate.asset_id == selected_id
    )
    candidate = selected.candidate
    summary_columns = st.columns(4)
    summary = (
        ("State", _state_label(selected.state)),
        ("Dataset", f"{candidate.dataset_id} v{candidate.dataset_version}"),
        ("Metric", candidate.primary_metric_name),
        ("Source value", f"{candidate.source_metric_value:.6f}"),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)
    st.markdown(f"**{candidate.asset_id}**")
    st.caption(
        f"{candidate.source_run_id} · {candidate.source_instance_id} · "
        f"seed {candidate.random_seed}"
    )
    st.markdown("**Strategy summary**")
    st.write(candidate.strategy_summary)
    st.markdown("**Optimization background**")
    st.write(candidate.optimization_background)
    st.dataframe(
        pd.DataFrame(
            {
                "Step": list(range(1, len(candidate.steps) + 1)),
                "Method": list(candidate.steps),
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Role": item.role,
                    "Asset": item.asset_id,
                    "Path": item.asset_path,
                    "SHA-256": item.sha256,
                }
                for item in candidate.evidence
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    if selected.gate is not None:
        gate = selected.gate
        st.markdown(f"**Reproduction gate: {_state_label(gate.outcome)}**")
        gate_columns = st.columns(3)
        gate_summary = (
            ("Source", gate.source_metric_six_decimals),
            (
                "Reproduction",
                gate.reproduction_metric_six_decimals or "Unavailable",
            ),
            ("Run", gate.reproduction_run_id),
        )
        for column, (label, value) in zip(gate_columns, gate_summary):
            with column:
                st.metric(label, value)
    if selected.state == "pending_reproduction":
        if st.button("Run independent reproduction", type="primary"):
            try:
                with st.spinner("Running independent reproduction"):
                    core.reproduce_sop_candidate(
                        ReproduceSopCandidateCommand(
                            connection_path=connection_path,
                            candidate_id=candidate.asset_id,
                            expected_candidate_fingerprint=(
                                candidate.candidate_fingerprint
                            ),
                        )
                    )
            except (ValueError, WorkspaceError) as error:
                _render_action_error(error)
            else:
                st.rerun()
    elif selected.state == "pending_review" and selected.gate is not None:
        review_columns = st.columns(2)
        with review_columns[0]:
            approve = st.button("Approve SOP", type="primary")
        with review_columns[1]:
            reject = st.button("Reject SOP")
        decision = "approve" if approve else "reject" if reject else None
        if decision is not None:
            try:
                core.review_sop_candidate(
                    ReviewSopCandidateCommand(
                        connection_path=connection_path,
                        candidate_id=candidate.asset_id,
                        expected_candidate_fingerprint=(
                            candidate.candidate_fingerprint
                        ),
                        expected_gate_fingerprint=(
                            selected.gate.gate_fingerprint
                        ),
                        decision=decision,
                    )
                )
            except (ValueError, WorkspaceError) as error:
                _render_action_error(error)
            else:
                st.rerun()


def _render_sop_versions(
    core: DomainCore,
    connection_path: Path,
    versions: tuple[SopVersionSnapshot, ...],
) -> None:
    if not versions:
        st.info("No approved SOP Versions")
        return
    labels = {
        item.asset_id: (
            f"{item.sop_id} v{item.version} · "
            f"{item.primary_metric_value:.6f} · {item.created_at}"
        )
        for item in versions
    }
    selected_id = st.selectbox(
        "Approved SOP Version",
        tuple(labels),
        format_func=lambda value: labels[value],
    )
    selected = next(item for item in versions if item.asset_id == selected_id)
    model = core.get_formal_model(connection_path, selected.formal_model_id)
    st.markdown(f"**{selected.asset_id}**")
    st.markdown(
        f"Source `{selected.source_instance_id}` · Reproduction "
        f"`{selected.reproduction_instance_id}`"
    )
    summary_columns = st.columns(4)
    summary = (
        ("Dataset", f"{selected.dataset_id} v{selected.dataset_version}"),
        ("Metric", selected.primary_metric_name),
        ("Value", f"{selected.primary_metric_value:.6f}"),
        ("Approved by", selected.created_by),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)
    st.markdown("**Training strategy**")
    st.write(selected.strategy_summary)
    st.markdown("**Optimization background**")
    st.write(selected.optimization_background)
    if selected.change_summary:
        st.markdown("**Version change**")
        st.write(selected.change_summary)
    st.dataframe(
        pd.DataFrame(
            {
                "Step": list(range(1, len(selected.steps) + 1)),
                "Method": list(selected.steps),
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"Formal Model {model.asset_id} · {model.model_fingerprint} · "
        f"Approval {selected.approval_id}"
    )
    trend = pd.DataFrame(
        [
            {
                "Version": item.version,
                "Primary metric": item.primary_metric_value,
            }
            for item in versions
            if item.sop_id == selected.sop_id
        ]
    )
    version_min = float(trend["Version"].min())
    version_max = float(trend["Version"].max())
    if version_min == version_max:
        version_min -= 0.5
        version_max += 0.5
    metric_min = float(trend["Primary metric"].min())
    metric_max = float(trend["Primary metric"].max())
    metric_padding = max(
        (metric_max - metric_min) * 0.1,
        abs(metric_max) * 0.02,
        0.001,
    )
    st.vega_lite_chart(
        trend,
        {
            "mark": (
                {"type": "point", "filled": True, "size": 100}
                if len(trend) == 1
                else {
                    "type": "line",
                    "point": {"filled": True, "size": 70},
                }
            ),
            "encoding": {
                "x": {
                    "field": "Version",
                    "type": "quantitative",
                    "scale": {"domain": [version_min, version_max]},
                    "axis": {"title": "SOP Version", "tickMinStep": 1},
                },
                "y": {
                    "field": "Primary metric",
                    "type": "quantitative",
                    "scale": {
                        "domain": [
                            metric_min - metric_padding,
                            metric_max + metric_padding,
                        ],
                        "zero": False,
                    },
                    "axis": {"title": selected.primary_metric_name},
                },
                "tooltip": [
                    {"field": "Version", "type": "quantitative"},
                    {
                        "field": "Primary metric",
                        "type": "quantitative",
                        "format": ".6f",
                    },
                ],
            },
        },
        height=260,
        width="stretch",
    )


def _render_action_error(error: ValueError | WorkspaceError) -> None:
    if isinstance(error, WorkspaceError):
        st.error(f"{error.code}: {error.message}")
        st.caption(error.next_action)
    else:
        st.error(str(error))


def _render_experience_review(
    core: DomainCore,
    connection_path: Path,
    experiences: tuple[ExperienceSnapshot, ...],
) -> None:
    state_groups = (
        ("pending", "Pending"),
        ("trusted", "Trusted"),
        ("rejected", "Rejected"),
        ("conflict", "Conflict"),
        ("superseded", "Superseded"),
    )
    grouped = {
        state: tuple(item for item in experiences if item.state == state)
        for state, _ in state_groups
    }
    tabs = st.tabs(
        [
            f"{label} ({len(grouped[state])})"
            for state, label in state_groups
        ]
    )
    for tab, (state, label) in zip(tabs, state_groups):
        with tab:
            items = grouped[state]
            if not items:
                st.info(f"No {label.lower()} Experience")
                continue
            labels = {
                item.asset_id: (
                    f"{item.asset_id} · {item.content.conclusion[:72]}"
                )
                for item in items
            }
            selected_id = st.selectbox(
                f"{label} Experience",
                tuple(labels),
                format_func=lambda experience_id: labels[experience_id],
                key=f"experience_select_{state}",
            )
            selected = next(
                item for item in items if item.asset_id == selected_id
            )
            _render_experience_detail(
                core,
                connection_path,
                selected,
                experiences,
            )


def _render_experience_detail(
    core: DomainCore,
    connection_path: Path,
    experience: ExperienceSnapshot,
    all_experiences: tuple[ExperienceSnapshot, ...],
) -> None:
    summary_columns = st.columns(4)
    summary = (
        ("State", _state_label(experience.state)),
        ("Confidence", f"{experience.content.confidence:.2f}"),
        ("Source", _state_label(experience.source_kind)),
        ("Current event", experience.event_id),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)
    st.caption(
        f"Extracted in {experience.extraction_session_id} · "
        f"created {experience.created_at} by {experience.created_by}"
    )

    if experience.state in {"pending", "conflict"}:
        _render_experience_review_form(
            core,
            connection_path,
            experience,
            all_experiences,
        )
    else:
        _render_experience_content(experience.content)
        if experience.state == "trusted":
            _render_supersede_form(
                core,
                connection_path,
                experience,
                all_experiences,
            )

    st.markdown("**Evidence**")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Role": item.role,
                    "Asset": item.asset_id,
                    "Path": item.asset_path,
                    "SHA-256": item.sha256,
                }
                for item in experience.evidence
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.markdown("**Immutable history**")
    try:
        history = core.get_experience_history(
            connection_path,
            experience.asset_id,
        )
    except WorkspaceError as error:
        st.error(f"{error.code}: {error.message}")
        st.caption(error.next_action)
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Event": item.event_id,
                    "State": _state_label(item.state),
                    "Decision": item.decision or "Extracted",
                    "Reviewer": item.reviewed_by or item.created_by,
                    "Timestamp": item.reviewed_at or item.created_at,
                    "Relation": (
                        f"{item.relation_type}: "
                        f"{item.related_experience_id}"
                        if item.relation_type is not None
                        else "None"
                    ),
                }
                for item in history
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def _render_experience_review_form(
    core: DomainCore,
    connection_path: Path,
    experience: ExperienceSnapshot,
    all_experiences: tuple[ExperienceSnapshot, ...],
) -> None:
    content = experience.content
    with st.form(f"review_experience_{experience.asset_id}"):
        conclusion = st.text_area(
            "Conclusion",
            content.conclusion,
            key=f"conclusion_{experience.event_id}",
        )
        applicability = st.text_area(
            "Applicability",
            content.applicability,
            key=f"applicability_{experience.event_id}",
        )
        recommended_action = st.text_area(
            "Recommended action",
            content.recommended_action,
            key=f"recommended_action_{experience.event_id}",
        )
        failure_boundary = st.text_area(
            "Failure boundary",
            content.failure_boundary,
            key=f"failure_boundary_{experience.event_id}",
        )
        risk = st.text_area(
            "Risk",
            content.risk,
            key=f"risk_{experience.event_id}",
        )
        confidence = st.slider(
            "Confidence",
            min_value=0.0,
            max_value=1.0,
            value=float(content.confidence),
            step=0.05,
            key=f"confidence_{experience.event_id}",
        )
        relation_candidates = tuple(
            item.asset_id
            for item in all_experiences
            if item.asset_id != experience.asset_id
            and item.state not in {"rejected", "superseded"}
        )
        conflict_target = st.selectbox(
            "Conflicts with",
            relation_candidates,
            index=None,
            placeholder="Select related Experience",
            disabled=not relation_candidates,
            key=f"conflict_target_{experience.event_id}",
        )
        action_columns = st.columns(3)
        with action_columns[0]:
            approve = st.form_submit_button("Approve", type="primary")
        with action_columns[1]:
            reject = st.form_submit_button("Reject")
        with action_columns[2]:
            conflict = st.form_submit_button(
                "Mark conflict",
                disabled=(
                    experience.state != "pending"
                    or conflict_target is None
                ),
            )
    decision = (
        "approve"
        if approve
        else "reject"
        if reject
        else "conflict"
        if conflict
        else None
    )
    if decision is None:
        return
    try:
        edited = ExperienceContent(
            conclusion=conclusion,
            applicability=applicability,
            recommended_action=recommended_action,
            failure_boundary=failure_boundary,
            risk=risk,
            confidence=confidence,
        )
        command = ReviewExperienceCommand(
            connection_path=connection_path,
            experience_id=experience.asset_id,
            decision=decision,
            content=edited,
            related_experience_id=(
                conflict_target if decision == "conflict" else None
            ),
        )
    except ValueError as error:
        st.error(str(error))
        return
    _submit_experience_review(
        core,
        command,
    )


def _render_experience_content(content: ExperienceContent) -> None:
    rows = (
        ("Conclusion", content.conclusion),
        ("Applicability", content.applicability),
        ("Recommended action", content.recommended_action),
        ("Failure boundary", content.failure_boundary),
        ("Risk", content.risk),
    )
    for label, value in rows:
        st.markdown(f"**{label}**")
        st.write(value)


def _render_supersede_form(
    core: DomainCore,
    connection_path: Path,
    experience: ExperienceSnapshot,
    all_experiences: tuple[ExperienceSnapshot, ...],
) -> None:
    replacements = tuple(
        item.asset_id
        for item in all_experiences
        if item.asset_id != experience.asset_id and item.state == "trusted"
    )
    with st.form(f"supersede_experience_{experience.asset_id}"):
        replacement = st.selectbox(
            "Trusted replacement",
            replacements,
            index=None,
            placeholder="Select replacement Experience",
            disabled=not replacements,
            key=f"replacement_{experience.event_id}",
        )
        supersede = st.form_submit_button(
            "Supersede",
            disabled=replacement is None,
        )
    if supersede:
        _submit_experience_review(
            core,
            ReviewExperienceCommand(
                connection_path=connection_path,
                experience_id=experience.asset_id,
                decision="supersede",
                content=experience.content,
                related_experience_id=replacement,
            ),
        )


def _submit_experience_review(
    core: DomainCore,
    command: ReviewExperienceCommand,
) -> None:
    try:
        core.review_experience(command)
    except (ValueError, WorkspaceError) as error:
        if isinstance(error, WorkspaceError):
            st.error(f"{error.code}: {error.message}")
            st.caption(error.next_action)
        else:
            st.error(str(error))
    else:
        st.rerun()


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
