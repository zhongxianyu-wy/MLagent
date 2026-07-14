from __future__ import annotations

from pathlib import Path

from src.models import SafetyDecision


BLOCKED_COMMAND_PREFIXES = (
    ("rm", "-rf"),
    ("git", "reset", "--hard"),
    ("git", "checkout", "--"),
)


def validate_command(command: list[str]) -> SafetyDecision:
    for blocked in BLOCKED_COMMAND_PREFIXES:
        if tuple(command[: len(blocked)]) == blocked:
            return SafetyDecision(
                allowed=False,
                reason="Command requires explicit approval",
                blocked_pattern=" ".join(blocked),
                requires_user_approval=True,
            )

    return SafetyDecision(
        allowed=True,
        reason="Command allowed",
        blocked_pattern=None,
        requires_user_approval=False,
    )


def validate_write_path(path: str, workspace_root: str) -> SafetyDecision:
    target = Path(path).resolve()
    workspace = Path(workspace_root).resolve()

    try:
        target.relative_to(workspace)
    except ValueError:
        return SafetyDecision(
            allowed=False,
            reason="Write path is outside workspace",
            blocked_pattern=str(target),
            requires_user_approval=True,
        )

    return SafetyDecision(
        allowed=True,
        reason="Write path allowed",
        blocked_pattern=None,
        requires_user_approval=False,
    )
