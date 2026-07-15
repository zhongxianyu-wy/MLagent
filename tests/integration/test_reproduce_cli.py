from src.agent.main import main


def test_reproduce_cli_invokes_reproduction_factory(confirmed_domain_core):
    requests = []

    exit_code = main(
        argv=[
            "reproduce",
            "--skill-id",
            "ngs-xgboost-baseline",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
        ],
        reproduce_factory=lambda request: requests.append(request) or 0,
        domain_core_factory=lambda: confirmed_domain_core,
    )

    assert exit_code == 0
    assert requests == [
        {
            "skill_id": "ngs-xgboost-baseline",
            "dataset_id": "ds-1",
            "dataset_version": 1,
            "dataset_content_fingerprint": "fingerprint-ds-1-v1",
            "dataset_version_fingerprint": "version-fingerprint-ds-1-v1",
            "strict": True,
            "manifest_path": "/team-memory/datasets/ds-1/v0001/manifest.json",
        }
    ]
