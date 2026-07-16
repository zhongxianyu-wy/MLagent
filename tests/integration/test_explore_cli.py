from src.agent.main import main
from src.domain.models import WorkspaceError


class FakeRunStatus:
    def __init__(self, state="completed"):
        self.state = state

    def to_dict(self):
        return {"run_id": "run-1", "state": self.state, "rounds": []}


def test_explore_cli_passes_approved_binding_to_issue_five_seam(
    confirmed_domain_core,
):
    requests = []

    exit_code = main(
        argv=[
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-id",
            "plan-1",
            "--approval-id",
            "approval-1",
            "--code-root",
            "/workspace/code",
            "--max-rounds",
            "2",
        ],
        explore_factory=lambda request: requests.append(request) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 0
    assert requests == [
        {
            "mode": "exploration",
            "dataset_id": "ds-1",
            "dataset_version": 1,
            "dataset_content_fingerprint": "fingerprint-ds-1-v1",
            "dataset_version_fingerprint": "version-fingerprint-ds-1-v1",
            "max_rounds": 1,
            "manifest_path": "/team-memory/datasets/ds-1/v0001/manifest.json",
            "experiment_id": "explore-ds-1-v0001",
            "guidance_metric_name": "auc",
            "random_seed": 42,
            "authorization": {
                "authorized": True,
                "entry_point": "cli_explore",
                "dataset_id": "ds-1",
                "dataset_version": 1,
                "dataset_version_fingerprint": "version-fingerprint-ds-1-v1",
                "plan_id": "plan-1",
                "plan_event_id": "plan-event-1",
                "approval_id": "approval-1",
                "plan_fingerprint": "plan-sha",
                "code_fingerprint": "code-sha",
                "round_count": 1,
                "authorized_at": "2026-07-15T00:00:00Z",
                "authorized_by": "alice",
            },
        }
    ]


def test_authoritative_explore_ignores_unapproved_cli_round_override(
    confirmed_domain_core,
):
    requests = []

    exit_code = main(
        [
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-id",
            "plan-1",
            "--approval-id",
            "approval-1",
            "--code-root",
            "/workspace/code",
            "--max-rounds",
            "not-an-approved-value",
        ],
        explore_factory=lambda request: requests.append(request) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 0
    assert requests[0]["max_rounds"] == 1


def test_explore_cli_never_calls_execution_seam_when_authorization_fails(
    confirmed_domain_core,
    capsys,
):
    requests = []

    def deny(_command):
        raise WorkspaceError(
            code="plan_approval_required",
            message="Approval required",
            next_action="Approve the current plan.",
        )

    confirmed_domain_core.authorize_training = deny
    exit_code = main(
        [
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-id",
            "plan-1",
            "--approval-id",
            "approval-1",
            "--code-root",
            "/workspace/code",
        ],
        explore_factory=lambda request: requests.append(request) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 2
    assert requests == []
    assert "plan_approval_required" in capsys.readouterr().out


def test_explore_cli_returns_structured_error_for_option_without_value(
    confirmed_domain_core,
    capsys,
):
    requests = []

    exit_code = main(
        [
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-id",
        ],
        explore_factory=lambda request: requests.append(request) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 2
    assert requests == []
    assert "invalid_arguments" in capsys.readouterr().out


def test_explore_cli_returns_structured_error_for_missing_dataset_version_value(
    confirmed_domain_core,
    capsys,
):
    requests = []

    exit_code = main(
        ["explore", "--dataset-id", "ds-1", "--dataset-version"],
        explore_factory=lambda request: requests.append(request) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 2
    assert requests == []
    assert "invalid_arguments" in capsys.readouterr().out


def test_authoritative_explore_executes_domain_run_by_default(
    confirmed_domain_core,
    capsys,
):
    commands = []
    confirmed_domain_core.execute_exploration = (
        lambda command: commands.append(command) or FakeRunStatus()
    )

    exit_code = main(
        [
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-id",
            "plan-1",
            "--approval-id",
            "approval-1",
            "--code-root",
            "/workspace/code",
            "--entrypoint",
            "estimator.py",
        ],
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 0
    assert len(commands) == 1
    assert commands[0].dataset_id == "ds-1"
    assert commands[0].dataset_version == 1
    assert commands[0].plan_id == "plan-1"
    assert commands[0].approval_id == "approval-1"
    assert commands[0].entrypoint_path == "estimator.py"
    assert '"state": "completed"' in capsys.readouterr().out


def test_authoritative_explore_returns_nonzero_for_failed_terminal_run(
    confirmed_domain_core,
    capsys,
):
    confirmed_domain_core.execute_exploration = (
        lambda command: FakeRunStatus("failed")
    )

    exit_code = main(
        [
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-id",
            "plan-1",
            "--approval-id",
            "approval-1",
            "--code-root",
            "/workspace/code",
        ],
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 2
    assert '"state": "failed"' in capsys.readouterr().out
