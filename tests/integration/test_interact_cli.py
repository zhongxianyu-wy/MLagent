from src.agent.main import main


def test_interact_cli_invokes_interactive_validation_factory():
    requests = []

    exit_code = main(
        argv=[
            "interact",
            "--dataset-id",
            "dataset-1",
            "--instruction",
            "测试标准化后低方差过滤",
        ],
        interact_factory=lambda request: requests.append(request) or 0,
    )

    assert exit_code == 0
    assert requests == [
        {
            "mode": "interactive_validation",
            "dataset_id": "dataset-1",
            "direction": "测试标准化后低方差过滤",
            "max_rounds": 1,
            "pause_after_result": True,
        }
    ]
