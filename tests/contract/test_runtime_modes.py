from src.agent.modes import classify_runtime_mode
from src.agent.slash_commands import parse_slash_command


def test_slash_commands_force_runtime_mode():
    assert classify_runtime_mode("/ask 什么是 AUC？") == "ask"
    assert classify_runtime_mode("/plan 设计一个验证方案") == "plan"
    assert classify_runtime_mode("/explore 用 demo 做训练") == "agent"


def test_natural_language_can_be_classified_without_slash_command():
    assert classify_runtime_mode("解释一下特定特异性下的灵敏度") == "ask"
    assert classify_runtime_mode("帮我设计一个 AUC 特征探索方案") == "plan"
    assert classify_runtime_mode("运行 demo 数据的特征探索") == "agent"


def test_unknown_slash_command_does_not_fall_back_to_agent():
    assert parse_slash_command("/unknown 运行 demo") is None
    assert classify_runtime_mode("/unknown 运行 demo") == "ask"
