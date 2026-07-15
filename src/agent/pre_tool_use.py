from __future__ import annotations

import json
import re
import shlex
import signal
import sys
from pathlib import Path
from typing import Any

from src.domain.models import AuthorizeTrainingCommand, WorkspaceError


SHELL_OPERATORS = {";", "&&", "||", "|", "&"}
INTERNAL_GATE_TIMEOUT_SECONDS = 15.0


class _TrainingGateTimeout(RuntimeError):
    pass


def evaluate_pre_tool_use(
    payload: dict[str, Any],
    domain_core: object | None = None,
) -> dict[str, Any] | None:
    if payload.get("hook_event_name") != "PreToolUse":
        return None
    if payload.get("tool_name") != "Bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return _deny("invalid_hook_input", "Bash tool input is missing.")
    command_text = tool_input.get("command")
    if not isinstance(command_text, str):
        return _deny("invalid_hook_input", "Bash command text is missing.")

    try:
        argument_sets = _authoritative_explore_arguments(command_text)
        if argument_sets is None:
            return None
        cwd = Path(str(payload.get("cwd") or ".")).expanduser().resolve()
        if domain_core is None:
            from src.domain.core import DomainCore

            domain_core = DomainCore()
        for arguments in argument_sets:
            connection_path = _resolve_from(
                cwd,
                _option(
                    arguments,
                    "--workspace-config",
                    ".mlagent-workspace.json",
                ),
            )
            code_root = _resolve_from(
                cwd,
                _option(arguments, "--code-root", "."),
            )
            dataset_id = _required_option(arguments, "--dataset-id")
            dataset_version = int(
                _required_option(arguments, "--dataset-version")
            )
            plan_id = _option(arguments, "--plan-id")
            approval_id = _option(arguments, "--approval-id")
            domain_core.authorize_training(
                AuthorizeTrainingCommand(
                    connection_path=connection_path,
                    code_root=code_root,
                    entry_point="claude_pre_tool_use",
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    plan_id=plan_id,
                    approval_id=approval_id,
                )
            )
    except (TypeError, ValueError) as error:
        return _deny("invalid_hook_arguments", str(error))
    except WorkspaceError as error:
        return _deny(error.code, f"{error.message} {error.next_action}")
    return None


def evaluate_pre_tool_use_with_timeout(
    payload: dict[str, Any],
    domain_core: object | None = None,
    timeout_seconds: float = INTERNAL_GATE_TIMEOUT_SECONDS,
) -> dict[str, Any] | None:
    if timeout_seconds <= 0:
        return _deny(
            "training_gate_timeout",
            "Training approval watchdog must have a positive timeout.",
        )

    def _raise_timeout(signum: int, frame: object) -> None:
        raise _TrainingGateTimeout

    try:
        previous_handler = signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    except (AttributeError, ValueError):
        return _deny(
            "training_gate_timeout",
            "Training approval watchdog is unavailable; blocking execution.",
        )
    try:
        return evaluate_pre_tool_use(payload, domain_core=domain_core)
    except _TrainingGateTimeout:
        return _deny(
            "training_gate_timeout",
            "Training approval did not finish before the internal deadline.",
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps(_deny("invalid_hook_input", str(error))))
        return 0
    if not isinstance(payload, dict):
        print(json.dumps(_deny("invalid_hook_input", "Hook input must be an object.")))
        return 0
    output = evaluate_pre_tool_use_with_timeout(payload)
    if output is not None:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


def _authoritative_explore_arguments(
    command_text: str,
) -> list[list[str]] | None:
    normalized_command = _normalize_shell_newlines(command_text)
    lexer = shlex.shlex(
        normalized_command,
        posix=True,
        punctuation_chars=";&|",
    )
    lexer.whitespace_split = True
    tokens = list(lexer)
    segment: list[str] = []
    matches: list[list[str]] = []
    marker_count = len(
        re.findall(r"\bsrc\.agent\.main\s+explore\b", normalized_command)
    )
    for token in (*tokens, ";"):
        if token not in SHELL_OPERATORS:
            segment.append(token)
            continue
        arguments = _python_explore_segment(segment)
        if arguments is not None:
            matches.append(arguments)
        segment = []
    if matches:
        if len(matches) == marker_count:
            return matches
        raise ValueError(
            "Formal explore must use literal, unspliced module and subcommand tokens."
        )
    if marker_count:
        raise ValueError(
            "Formal explore must be a direct 'python -m src.agent.main explore' command."
        )
    return None


def _normalize_shell_newlines(command_text: str) -> str:
    text = command_text.replace("\r\n", "\n").replace("\r", "\n")
    output: list[str] = []
    quote: str | None = None
    escaped = False
    for character in text:
        if escaped:
            if character == "\n":
                output.pop()
                output.append(" ")
            else:
                output.append(character)
            escaped = False
            continue
        if character == "\\" and quote != "'":
            output.append(character)
            escaped = True
            continue
        if character in {"'", '"'}:
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            output.append(character)
            continue
        if character == "\n" and quote is None:
            output.append(";")
        else:
            output.append(character)
    return "".join(output)


def _python_explore_segment(segment: list[str]) -> list[str] | None:
    start = 0
    while start < len(segment) and "=" in segment[start]:
        start += 1
    invocation = segment[start:]
    if len(invocation) < 3:
        return None
    executable = Path(invocation[0]).name
    if not executable.startswith("python"):
        return None
    if invocation[1:3] != ["-m", "src.agent.main"]:
        return None
    if len(invocation) < 4:
        raise ValueError("MLagent requires a literal subcommand.")
    subcommand = invocation[3]
    if any(marker in subcommand for marker in ("$", "`")):
        raise ValueError("MLagent subcommands cannot use shell expansion.")
    if subcommand != "explore":
        return None
    return invocation[4:]


def _required_option(arguments: list[str], name: str) -> str:
    value = _option(arguments, name)
    if value is None or not value.strip():
        raise ValueError(f"Required formal-training argument is missing: {name}.")
    return value


def _option(
    arguments: list[str],
    name: str,
    default: str | None = None,
) -> str | None:
    if name not in arguments:
        return default
    index = arguments.index(name)
    if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
        raise ValueError(f"Option requires a value: {name}.")
    return arguments[index + 1]


def _resolve_from(cwd: Path, value: str | None) -> Path:
    if value is None:
        raise ValueError("A required path value is missing.")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (cwd / path).resolve()


def _deny(code: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{code}: {reason}",
        }
    }


if __name__ == "__main__":
    raise SystemExit(main())
