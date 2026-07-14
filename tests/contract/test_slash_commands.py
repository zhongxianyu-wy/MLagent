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


def test_parse_bootstrap_memory_routes_to_domain_core_workflow():
    parsed = parse_slash_command(
        "/bootstrap-memory /tmp/team-memory --actor alice"
    )

    assert parsed.name == "bootstrap-memory"
    assert parsed.domain_action == "bootstrap_memory"
    assert parsed.mode == "agent"


def test_parse_intake_data_routes_to_authoritative_domain_workflow():
    parsed = parse_slash_command(
        "/intake-data features.csv labels.csv"
    )

    assert parsed.name == "intake-data"
    assert parsed.domain_action == "intake_data"
    assert parsed.mode == "agent"
