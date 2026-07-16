from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.domain.models import SyncStatusSnapshot


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
