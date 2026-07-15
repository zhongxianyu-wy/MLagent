from src.agent.main import main


def test_explore_cli_passes_confirmed_manifest_to_exploration(confirmed_domain_core):
    requests = []

    exit_code = main(
        argv=[
            "explore",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
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
        }
    ]
