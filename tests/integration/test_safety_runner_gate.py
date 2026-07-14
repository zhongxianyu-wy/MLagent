from src.training.runner import run_command_with_safety


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
