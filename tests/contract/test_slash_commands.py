from src.agent.slash_commands import parse_slash_command


def test_parse_slash_command_preserves_natural_language_tail():
    parsed = parse_slash_command("/plan 用 demo 数据设计 AUC 探索方案")

    assert parsed.name == "plan"
    assert parsed.natural_language_tail == "用 demo 数据设计 AUC 探索方案"
    assert parsed.mode == "plan"
    assert parsed.domain_action is None


def test_parse_agent_wrapped_functional_command():
    parsed = parse_slash_command("/agent /explore 用 demo 做特征探索")

    assert parsed.name == "explore"
    assert parsed.natural_language_tail == "用 demo 做特征探索"
    assert parsed.mode == "agent"
    assert parsed.domain_action == "explore"


def test_parse_unknown_slash_command_returns_none():
    assert parse_slash_command("/unknown hello") is None
