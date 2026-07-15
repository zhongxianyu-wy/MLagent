from __future__ import annotations

from collections.abc import Callable

from src.agent.hooks import validate_command
from src.domain.models import (
    AuthorizeTrainingCommand,
    TrainingAuthorization,
    WorkspaceError,
)
from src.models import SafetyDecision


Executor = Callable[[list[str]], int]


def run_command_with_safety(
    command: list[str],
    workspace_root: str,
    executor: Executor,
) -> SafetyDecision:
    decision = validate_command(command)
    if not decision.allowed:
        return decision

    executor(command)
    return SafetyDecision(
        allowed=True,
        reason=f"Command allowed in {workspace_root}",
        blocked_pattern=None,
        requires_user_approval=False,
    )


def run_command_with_training_gate(
    command: list[str],
    workspace_root: str,
    authorization_command: AuthorizeTrainingCommand,
    domain_core: object,
    executor: Executor,
) -> TrainingAuthorization:
    authorization = domain_core.authorize_training(authorization_command)
    if not authorization.authorized:
        raise WorkspaceError(
            code="training_not_authorized",
            message="The Domain Core did not authorize formal training.",
            next_action="Review the current plan approval before retrying.",
        )
    decision = validate_command(command)
    if not decision.allowed:
        raise WorkspaceError(
            code="unsafe_training_command",
            message=decision.reason,
            next_action="Use a non-destructive training command inside the workspace.",
        )
    executor(command)
    return authorization
