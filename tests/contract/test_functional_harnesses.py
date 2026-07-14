from pathlib import Path

from src.agent.slash_commands import (
    load_harnesses,
    parse_slash_command,
    resolve_harness_command,
)


def test_default_harness_config_contains_train_type1_alias():
    harnesses = load_harnesses(Path("config/harnesses.toml"))

    resolved = resolve_harness_command("/train_type1", harnesses)

    assert resolved is not None
    assert resolved.harness_id == "explore"
    assert resolved.domain_action == "explore"
    assert resolved.allow_plan_promotion is True


def test_parse_slash_command_uses_configured_harness_alias():
    parsed = parse_slash_command(
        "/train_type1 用 demo 做特征探索",
        harnesses=load_harnesses(Path("config/harnesses.toml")),
    )

    assert parsed.name == "train_type1"
    assert parsed.mode == "agent"
    assert parsed.domain_action == "explore"
    assert parsed.alias_source == "explore"
    assert parsed.natural_language_tail == "用 demo 做特征探索"
