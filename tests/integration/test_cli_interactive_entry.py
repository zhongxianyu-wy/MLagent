from src.agent.main import main


def test_no_argument_cli_starts_interactive_shell():
    started = []

    exit_code = main(argv=[], shell_factory=lambda: started.append("shell") or 0)

    assert exit_code == 0
    assert started == ["shell"]


def test_explicit_status_subcommand_does_not_start_shell():
    started = []

    exit_code = main(argv=["status"], shell_factory=lambda: started.append("shell") or 0)

    assert exit_code == 0
    assert started == []
