from pathlib import Path

from src.agent.hooks import (
    TrainingToolContext,
    authorize_training_tool,
    validate_command,
    validate_write_path,
)
from src.domain.models import TrainingAuthorization


def test_validate_command_blocks_destructive_shell_commands():
    decision = validate_command(["rm", "-rf", "experiments/models"])

    assert decision.allowed is False
    assert decision.blocked_pattern == "rm -rf"
    assert decision.requires_user_approval is True


def test_validate_command_allows_python_module_execution():
    decision = validate_command(["python3", "-m", "src.agent.main", "status"])

    assert decision.allowed is True
    assert decision.blocked_pattern is None


def test_validate_write_path_blocks_paths_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside" / "model.pkl"

    decision = validate_write_path(str(outside), workspace_root=str(workspace))

    assert decision.allowed is False
    assert decision.requires_user_approval is True


def test_validate_write_path_allows_paths_inside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = workspace / "experiments" / "models" / "model.pkl"

    decision = validate_write_path(str(output), workspace_root=str(workspace))

    assert decision.allowed is True
    assert decision.blocked_pattern is None


def test_pre_tool_use_delegates_training_authorization_to_domain_core():
    core = RecordingCore()
    context = TrainingToolContext(
        connection_path=Path("/workspace/.mlagent-workspace.json"),
        code_root=Path("/workspace/code"),
        dataset_id="ds-1",
        dataset_version=1,
        plan_id="plan-1",
        approval_id="approval-1",
    )

    result = authorize_training_tool(context, domain_core=core)

    assert result.authorized is True
    assert len(core.commands) == 1
    assert core.commands[0].entry_point == "claude_pre_tool_use"
    assert core.commands[0].connection_path == context.connection_path
    assert core.commands[0].code_root == context.code_root
    assert core.commands[0].plan_id == "plan-1"


class RecordingCore:
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
            round_count=1,
            authorized_at="2026-07-15T00:00:00Z",
            authorized_by="alice",
        )
