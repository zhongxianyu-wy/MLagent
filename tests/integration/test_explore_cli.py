from src.agent.main import main
from src.domain.models import WorkspaceError


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
            "max_rounds": 2,
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
                "authorized_at": "2026-07-15T00:00:00Z",
                "authorized_by": "alice",
            },
        }
    ]


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
