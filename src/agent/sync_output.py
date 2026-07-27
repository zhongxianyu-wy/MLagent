from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.domain.models import SessionContextSnapshot, SessionExperienceOutcome, SyncStatusSnapshot


STATE_LABELS = {
    "not_configured": "Not Configured",
    "synced": "Synced",
    "syncing": "Syncing",
    "pending_sync": "Pending Sync",
    "conflict": "Conflict",
}
OUTPUT_LIMIT = 800


def bounded_sync_message(status: SyncStatusSnapshot) -> str:
    parts = [f"MLagent Team Memory: {STATE_LABELS[status.state]}."]
    if status.branch:
        parts.append(f"Branch {_clean(status.branch, 120)}.")
    parts.append(
        f"Ahead {status.ahead_count}; behind {status.behind_count}; "
        f"managed changes {len(status.changed_managed_paths)}."
    )
    if status.conflict_paths:
        conflicts = ", ".join(
            _clean(path, 160) for path in status.conflict_paths[:3]
        )
        suffix = "" if len(status.conflict_paths) <= 3 else ", ..."
        parts.append(f"Conflicts: {conflicts}{suffix}.")
    if status.next_action:
        parts.append(f"Next: {_clean(status.next_action, 260)}")
    return _bounded(" ".join(parts))


def bounded_session_context(context: SessionContextSnapshot | None) -> str:
    if context is None:
        return ""
    parts = []
    if context.latest_plan_id:
        parts.append(f"Plan {context.latest_plan_id}.")
    if context.recent_run_id:
        metric = (
            f" best {context.recent_best_metric:.4f}"
            if context.recent_best_metric is not None
            else ""
        )
        parts.append(
            f"Run {context.recent_run_id} ({context.recent_run_state}{metric})."
        )
    if context.pending_experience_count:
        parts.append(f"Pending experience: {context.pending_experience_count}.")
    return _bounded(" ".join(parts))


def bounded_session_start_message(
    outcome: SessionExperienceOutcome,
    context: SessionContextSnapshot | None = None,
) -> str:
    restore = bounded_session_context(context)
    restore_clause = f" {restore}" if restore else ""
    return _bounded(
        f"Session {_clean(outcome.session_id, 100)}. "
        f"Experience Review: {outcome.pending_review_count} pending. "
        f"{bounded_sync_message(_require_sync(outcome))}{restore_clause}"
    )


def bounded_session_stop_message(
    outcome: SessionExperienceOutcome,
) -> str:
    if outcome.outcome == "created":
        experience = (
            f"Created {len(outcome.candidate_ids)} low-confidence "
            "Experience candidate(s) for human review."
        )
    elif outcome.outcome == "no_op":
        experience = "No reusable Experience found; recorded no-op."
    else:
        experience = "Experience extraction was already completed."
    return _bounded(
        f"{experience} {bounded_sync_message(_require_sync(outcome))}"
    )


def bounded_failure_message(code: str) -> str:
    safe_code = _clean(code, 80)
    return _bounded(
        f"MLagent Team Memory sync failed ({safe_code}). "
        "Managed assets remain local; review Git status in the MLagent UI "
        "and retry synchronization."
    )


def resolve_connection_path(
    payload: dict[str, Any],
    environment: Mapping[str, str],
) -> Path:
    configured = Path(
        environment.get(
            "MLAGENT_WORKSPACE_CONFIG",
            ".mlagent-workspace.json",
        )
    ).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    base = Path(
        environment.get("CLAUDE_PROJECT_DIR")
        or str(payload.get("cwd") or ".")
    ).expanduser()
    return (base / configured).resolve()


def _clean(value: str, limit: int) -> str:
    return " ".join(str(value).split())[:limit]


def _bounded(value: str) -> str:
    return value[:OUTPUT_LIMIT]


def _require_sync(
    outcome: SessionExperienceOutcome,
) -> SyncStatusSnapshot:
    if outcome.sync is None:
        raise ValueError("Session outcome requires synchronization status")
    return outcome.sync
