from __future__ import annotations

from dataclasses import dataclass

from src.domain.models import (
    DatasetInspection,
    DatasetVersionSnapshot,
    ExplorationReviewSnapshot,
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
    "Pending sync",
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
    issues: tuple[dict[str, str], ...]
    dataset: DatasetVersionSnapshot | None
    inspection: DatasetInspection | None
    exploration_review: ExplorationReviewSnapshot | None


def build_shell_state(
    snapshot: WorkspaceSnapshot,
    dataset: DatasetVersionSnapshot | None = None,
    inspection: DatasetInspection | None = None,
    exploration_review: ExplorationReviewSnapshot | None = None,
) -> ShellState:
    git_status = {
        "reachable": "Success",
        "not_configured": "Pending confirmation",
        "unreachable": "Failed",
        "invalid": "Failed",
    }.get(snapshot.remote.state, "Failed")
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
        issues=tuple(issue.to_dict() for issue in snapshot.issues),
        dataset=dataset,
        inspection=inspection,
        exploration_review=exploration_review,
    )


def _format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1000 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1000
    return f"{value} B"
