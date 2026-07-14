from src.agent.main import main


def test_explore_cli_runs_mock_exploration():
    requests = []

    exit_code = main(
        argv=[
            "explore",
            "--dataset-id",
            "dataset-1",
            "--max-rounds",
            "2",
        ],
        explore_factory=lambda request: requests.append(request) or 0,
    )

    assert exit_code == 0
    assert requests == [
        {
            "mode": "exploration",
            "dataset_id": "dataset-1",
            "max_rounds": 2,
        }
    ]
