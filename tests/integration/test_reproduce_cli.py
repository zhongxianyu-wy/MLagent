from src.agent.main import main


def test_reproduce_cli_invokes_reproduction_factory():
    requests = []

    exit_code = main(
        argv=[
            "reproduce",
            "--skill-id",
            "ngs-xgboost-baseline",
            "--dataset-id",
            "dataset-1",
        ],
        reproduce_factory=lambda request: requests.append(request) or 0,
    )

    assert exit_code == 0
    assert requests == [
        {
            "skill_id": "ngs-xgboost-baseline",
            "dataset_id": "dataset-1",
            "strict": True,
        }
    ]
