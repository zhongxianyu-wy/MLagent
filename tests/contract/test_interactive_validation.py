from src.agent.control_center import instruction_to_validation_request


def test_interactive_validation_request_preserves_user_instruction_and_dataset():
    request = instruction_to_validation_request(
        dataset_id="dataset-1",
        instruction="测试二元化甲基化特征是否提升 95% 特异性下的敏感性",
    )

    assert request == {
        "mode": "interactive_validation",
        "dataset_id": "dataset-1",
        "direction": "测试二元化甲基化特征是否提升 95% 特异性下的敏感性",
        "max_rounds": 1,
        "pause_after_result": True,
    }
