from __future__ import annotations

from dataclasses import dataclass

from src.domain.models import (
    DatasetInspection,
    DatasetVersionSnapshot,
    ExperienceSnapshot,
    ExplorationReviewSnapshot,
    RunStatusSnapshot,
    SyncStatusSnapshot,
    WorkspaceSnapshot,
)


NAVIGATION = (
    "Code Review",
    "Dataset Overview",
    "Run Status",
    "SOP Overview",
    "Experience Review",
    "Lineage Trace",
)
GLOBAL_STATUS_VOCABULARY = (
    "Not started",
    "Pending confirmation",
    "Running",
    "Success",
    "Failed",
    "Pending review",
    "Approved",
    "Rejected",
    "Synced",
    "Syncing",
    "Pending Sync",
    "Conflict",
)
CONTEXT_LABELS = {
    "workspace": "Workspace",
    "dataset": "Dataset",
    "run": "Run",
    "git": "Git",
    "writer": "Writer",
}


@dataclass(frozen=True)
class ShellState:
    navigation: tuple[str, ...]
    context: dict[str, str]
    module_status: dict[str, str]
    schema_version: int
    indexed_assets: int
    capacity_text: str
    git_detail: str
    issues: tuple[dict[str, str], ...]
    dataset: DatasetVersionSnapshot | None
    inspection: DatasetInspection | None
    exploration_review: ExplorationReviewSnapshot | None
    run_statuses: tuple[RunStatusSnapshot, ...]
    experiences: tuple[ExperienceSnapshot, ...]


def build_shell_state(
    snapshot: WorkspaceSnapshot,
    dataset: DatasetVersionSnapshot | None = None,
    inspection: DatasetInspection | None = None,
    exploration_review: ExplorationReviewSnapshot | None = None,
    run_statuses: tuple[RunStatusSnapshot, ...] = (),
    experiences: tuple[ExperienceSnapshot, ...] = (),
) -> ShellState:
    git_status = sync_display(snapshot.sync.state)
    module_status = {module: "Not started" for module in NAVIGATION}
    if dataset is not None:
        module_status["Dataset Overview"] = "Success"
    elif inspection is not None:
        module_status["Dataset Overview"] = inspection.status
    run_status = "Not started"
    if exploration_review is not None:
        run_status = {
            "pending_review": "Pending review",
            "approved": "Approved",
            "approval_stale": "Failed",
        }.get(exploration_review.approval_state, "Failed")
        module_status["Run Status"] = run_status
    if run_statuses:
        latest_run = run_statuses[0]
        run_status = {
            "running": "Running",
            "completed": "Success",
            "failed": "Failed",
            "timed_out": "Failed",
            "stopped": "Failed",
            "recovery_required": "Pending confirmation",
        }.get(latest_run.state, "Failed")
        module_status["Run Status"] = run_status
    experience_states = {experience.state for experience in experiences}
    if experience_states & {"pending", "conflict"}:
        module_status["Experience Review"] = "Pending review"
    elif "trusted" in experience_states:
        module_status["Experience Review"] = "Approved"
    elif experience_states:
        module_status["Experience Review"] = "Rejected"
    return ShellState(
        navigation=NAVIGATION,
        context={
            "workspace": snapshot.repository_id,
            "dataset": (
                f"{dataset.dataset_id} v{dataset.version}"
                if dataset is not None
                else (
                    inspection.status
                    if inspection is not None
                    else "Not started"
                )
            ),
            "run": run_status,
            "git": git_status,
            "writer": snapshot.actor_id,
        },
        module_status=module_status,
        schema_version=snapshot.schema_version,
        indexed_assets=snapshot.indexed_assets,
        capacity_text=(
            f"{_format_bytes(snapshot.capacity.bytes_used)} of "
            f"{_format_bytes(snapshot.capacity.max_repository_bytes)}"
        ),
        git_detail=sync_detail(snapshot.sync, snapshot.capacity.state),
        issues=tuple(issue.to_dict() for issue in snapshot.issues),
        dataset=dataset,
        inspection=inspection,
        exploration_review=exploration_review,
        run_statuses=run_statuses,
        experiences=experiences,
    )


def sync_display(state: str) -> str:
    return {
        "not_configured": "Pending confirmation",
        "synced": "Synced",
        "syncing": "Syncing",
        "pending_sync": "Pending Sync",
        "conflict": "Conflict",
    }.get(state, "Failed")


def sync_detail(
    status: SyncStatusSnapshot,
    capacity_state: str,
) -> str:
    if capacity_state == "warning":
        return "Capacity warning"
    if capacity_state == "blocked":
        return "Capacity blocked"
    if status.state == "not_configured":
        return "Origin not configured"
    if status.state == "conflict":
        path = status.conflict_paths[0]
        suffix = "" if len(status.conflict_paths) == 1 else " + more"
        return f"{path}{suffix}"
    branch = status.branch or "No branch"
    return (
        f"{branch} · {status.ahead_count} ahead · "
        f"{status.behind_count} behind · "
        f"{len(status.changed_managed_paths)} managed changes"
    )


def _format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1000 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1000
    return f"{value} B"
