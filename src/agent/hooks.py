from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.domain.models import AuthorizeTrainingCommand, TrainingAuthorization
from src.models import SafetyDecision


BLOCKED_COMMAND_PREFIXES = (
    ("rm", "-rf"),
    ("git", "reset", "--hard"),
    ("git", "checkout", "--"),
)


@dataclass(frozen=True)
class TrainingToolContext:
    connection_path: Path
    code_root: Path
    dataset_id: str
    dataset_version: int
    plan_id: str | None
    approval_id: str | None


def authorize_training_tool(
    context: TrainingToolContext,
    domain_core: object | None = None,
) -> TrainingAuthorization:
    if domain_core is None:
        from src.domain.core import DomainCore

        domain_core = DomainCore()
    return domain_core.authorize_training(
        AuthorizeTrainingCommand(
            connection_path=context.connection_path,
            code_root=context.code_root,
            entry_point="claude_pre_tool_use",
            dataset_id=context.dataset_id,
            dataset_version=context.dataset_version,
            plan_id=context.plan_id,
            approval_id=context.approval_id,
        )
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
