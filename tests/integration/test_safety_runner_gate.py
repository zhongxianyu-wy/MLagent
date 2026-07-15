import pytest

from src.domain.models import (
    AuthorizeTrainingCommand,
    TrainingAuthorization,
    WorkspaceError,
)
from src.training.runner import (
    run_command_with_safety,
    run_command_with_training_gate,
)


def test_blocked_commands_never_reach_training_executor(tmp_path):
    calls = []

    result = run_command_with_safety(
        command=["rm", "-rf", "experiments/models"],
        workspace_root=str(tmp_path),
        executor=lambda command: calls.append(command) or 0,
    )

    assert result.allowed is False
    assert calls == []


def test_allowed_commands_reach_training_executor(tmp_path):
    calls = []

    result = run_command_with_safety(
        command=["python3", "-m", "src.training.scripts.train_sklearn"],
        workspace_root=str(tmp_path),
        executor=lambda command: calls.append(command) or 0,
    )

    assert result.allowed is True
    assert calls == [["python3", "-m", "src.training.scripts.train_sklearn"]]


def test_training_gate_never_invokes_executor_when_domain_core_denies(tmp_path):
    calls = []

    with pytest.raises(WorkspaceError) as caught:
        run_command_with_training_gate(
            command=["python3", "train.py"],
            workspace_root=str(tmp_path),
            authorization_command=authorization_command(tmp_path),
            domain_core=DenyingCore(),
            executor=lambda command: calls.append(command) or 0,
        )

    assert caught.value.code == "plan_approval_required"
    assert calls == []


def test_training_gate_invokes_executor_only_after_exact_authorization(tmp_path):
    calls = []
    core = ApprovingCore()
    command = authorization_command(tmp_path)

    result = run_command_with_training_gate(
        command=["python3", "train.py"],
        workspace_root=str(tmp_path),
        authorization_command=command,
        domain_core=core,
        executor=lambda value: calls.append(value) or 0,
    )

    assert result.authorized is True
    assert core.commands == [command]
    assert calls == [["python3", "train.py"]]


def authorization_command(tmp_path):
    return AuthorizeTrainingCommand(
        connection_path=tmp_path / ".mlagent-workspace.json",
        code_root=tmp_path / "code",
        entry_point="claude_pre_tool_use",
        dataset_id="ds-1",
        dataset_version=1,
        plan_id="plan-1",
        approval_id="approval-1",
    )


class DenyingCore:
    def authorize_training(self, _command):
        raise WorkspaceError(
            code="plan_approval_required",
            message="Approval required",
            next_action="Approve the current plan.",
        )


class ApprovingCore:
    def __init__(self):
        self.commands = []

    def authorize_training(self, command):
        self.commands.append(command)
        return TrainingAuthorization(
            authorized=True,
            entry_point=command.entry_point,
            dataset_id=command.dataset_id,
            dataset_version=command.dataset_version,
            dataset_version_fingerprint="dataset-sha",
            plan_id=command.plan_id,
            plan_event_id="plan-event-1",
            approval_id=command.approval_id,
            plan_fingerprint="plan-sha",
            code_fingerprint="code-sha",
            authorized_at="2026-07-15T00:00:00Z",
            authorized_by="alice",
        )
