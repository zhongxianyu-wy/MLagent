from src.agent.hooks import validate_command, validate_write_path


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
