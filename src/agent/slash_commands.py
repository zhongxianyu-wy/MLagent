from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BUILTIN_MODES = {
    "ask": "ask",
    "plan": "plan",
    "agent": "agent",
}

DOMAIN_ACTIONS = {
    "bootstrap-memory": "bootstrap_memory",
    "intake": "intake",
    "explore": "explore",
    "reproduce": "reproduce",
    "interact": "interactive_validate",
    "validate": "interactive_validate",
    "distill": "distill",
    "research": "research",
    "skill_opt": "skill_opt",
}


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    mode: str
    natural_language_tail: str
    domain_action: str | None
    alias_source: str | None = None


@dataclass(frozen=True)
class FunctionalHarness:
    harness_id: str
    commands: list[str]
    domain_action: str
    required_inputs: list[str]
    allow_plan_promotion: bool
    source: str
    description: str


def load_harnesses(path: Path) -> list[FunctionalHarness]:
    data = _load_simple_harness_toml(path.read_text())
    return [
        FunctionalHarness(
            harness_id=item["harness_id"],
            commands=list(item["commands"]),
            domain_action=item["domain_action"],
            required_inputs=list(item["required_inputs"]),
            allow_plan_promotion=bool(item["allow_plan_promotion"]),
            source=item["source"],
            description=item["description"],
        )
        for item in data.get("harnesses", [])
    ]


def _load_simple_harness_toml(text: str) -> dict[str, list[dict]]:
    harnesses: list[dict] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[[harnesses]]":
            current = {}
            harnesses.append(current)
            continue
        if current is None or "=" not in line:
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        current[key] = _parse_simple_toml_value(value)
    return {"harnesses": harnesses}


def _parse_simple_toml_value(value: str) -> object:
    if value in {"true", "false"}:
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [
            item.strip().strip('"')
            for item in inner.split(",")
        ]
    return value.strip('"')


def resolve_harness_command(
    command: str, harnesses: list[FunctionalHarness]
) -> FunctionalHarness | None:
    for harness in harnesses:
        if command in harness.commands:
            return harness
    return None


def parse_slash_command(
    user_text: str, harnesses: list[FunctionalHarness] | None = None
) -> ParsedCommand | None:
    text = user_text.strip()
    if not text.startswith("/"):
        return None

    command, tail = _split_command(text)
    command_name = command.removeprefix("/")
    harnesses = harnesses or []

    if command_name == "agent" and tail.strip().startswith("/"):
        nested_command, nested_tail = _split_command(tail.strip())
        nested_name = nested_command.removeprefix("/")
        harness = resolve_harness_command(nested_command, harnesses)
        if harness is not None:
            return ParsedCommand(
                name=nested_name,
                mode="agent",
                natural_language_tail=nested_tail,
                domain_action=harness.domain_action,
                alias_source=harness.harness_id,
            )
        domain_action = DOMAIN_ACTIONS.get(nested_name)
        if domain_action is None:
            return None
        return ParsedCommand(
            name=nested_name,
            mode="agent",
            natural_language_tail=nested_tail,
            domain_action=domain_action,
        )

    if command_name in BUILTIN_MODES:
        return ParsedCommand(
            name=command_name,
            mode=BUILTIN_MODES[command_name],
            natural_language_tail=tail,
            domain_action=None,
        )

    harness = resolve_harness_command(command, harnesses)
    if harness is not None:
        return ParsedCommand(
            name=command_name,
            mode="agent",
            natural_language_tail=tail,
            domain_action=harness.domain_action,
            alias_source=harness.harness_id,
        )

    domain_action = DOMAIN_ACTIONS.get(command_name)
    if domain_action is not None:
        return ParsedCommand(
            name=command_name,
            mode="agent",
            natural_language_tail=tail,
            domain_action=domain_action,
        )

    return None


def _split_command(text: str) -> tuple[str, str]:
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]
