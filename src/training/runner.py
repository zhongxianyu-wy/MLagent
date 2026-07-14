from __future__ import annotations

from collections.abc import Callable

from src.agent.hooks import validate_command
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
