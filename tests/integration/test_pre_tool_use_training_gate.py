import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from src.agent.pre_tool_use import (
    evaluate_pre_tool_use,
    evaluate_pre_tool_use_with_timeout,
)
from src.domain.models import WorkspaceError


class RecordingCore:
    def __init__(self, error=None):
        self.commands = []
        self.error = error

    def authorize_training(self, command):
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return object()


def test_pre_tool_use_routes_authoritative_explore_through_domain_core():
    core = RecordingCore()

    output = evaluate_pre_tool_use(
        bash_payload(
            "python -m src.agent.main explore "
            "--workspace-config /workspace/.mlagent-workspace.json "
            "--dataset-id ds-1 --dataset-version 1 "
            "--plan-id plan-1 --approval-id approval-1 "
            "--code-root /workspace/code"
        ),
        domain_core=core,
    )

    assert output is None
    command = core.commands[0]
    assert command.entry_point == "claude_pre_tool_use"
    assert command.connection_path == Path("/workspace/.mlagent-workspace.json")
    assert command.code_root == Path("/workspace/code")
    assert command.dataset_id == "ds-1"
    assert command.dataset_version == 1
    assert command.plan_id == "plan-1"
    assert command.approval_id == "approval-1"


def test_pre_tool_use_denies_formal_explore_when_domain_gate_rejects():
    core = RecordingCore(
        WorkspaceError(
            code="approval_stale",
            message="The approved code changed.",
            next_action="Review and approve the current code again.",
        )
    )

    output = evaluate_pre_tool_use(
        bash_payload(
            "python -m src.agent.main explore --dataset-id ds-1 "
            "--dataset-version 1 --plan-id plan-1 --approval-id approval-1"
        ),
        domain_core=core,
    )

    decision = output["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "approval_stale" in decision["permissionDecisionReason"]


@pytest.mark.parametrize("separator", ("; ", "\n"))
def test_pre_tool_use_checks_every_explore_in_one_bash_call(separator):
    class SelectiveCore(RecordingCore):
        def authorize_training(self, command):
            self.commands.append(command)
            if command.plan_id == "plan-unapproved":
                raise WorkspaceError(
                    code="plan_approval_required",
                    message="The second plan is not approved.",
                    next_action="Approve it before training.",
                )
            return object()

    core = SelectiveCore()
    common = "--dataset-id ds-1 --dataset-version 1 --code-root /workspace/code"

    output = evaluate_pre_tool_use(
        bash_payload(
            "python -m src.agent.main explore "
            f"{common} --plan-id plan-approved --approval-id approval-1"
            f"{separator}"
            "python -m src.agent.main explore "
            f"{common} --plan-id plan-unapproved --approval-id approval-2"
        ),
        domain_core=core,
    )

    assert [command.plan_id for command in core.commands] == [
        "plan-approved",
        "plan-unapproved",
    ]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_pre_tool_use_denies_legacy_explore_after_approved_newline_command():
    core = RecordingCore()

    output = evaluate_pre_tool_use(
        bash_payload(
            "python -m src.agent.main explore --dataset-id ds-1 "
            "--dataset-version 1 --plan-id plan-1 --approval-id approval-1\n"
            "python -m src.agent.main explore --manifest-path /tmp/legacy.json"
        ),
        domain_core=core,
    )

    assert len(core.commands) == 1
    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "invalid_hook_arguments" in decision["permissionDecisionReason"]


def test_pre_tool_use_denies_nested_explore_it_cannot_bind_directly():
    core = RecordingCore()

    output = evaluate_pre_tool_use(
        bash_payload(
            "bash -c 'python -m src.agent.main explore "
            "--manifest-path /tmp/legacy.json'"
        ),
        domain_core=core,
    )

    assert core.commands == []
    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "invalid_hook_arguments" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    (
        "python -m src.agent.main ex\"plore\" --manifest-path /tmp/legacy.json",
        "MODE=explore; python -m src.agent.main \"$MODE\" "
        "--manifest-path /tmp/legacy.json",
        "python -m src.agent.main \"$(printf explore)\" "
        "--manifest-path /tmp/legacy.json",
    ),
)
def test_pre_tool_use_denies_nonliteral_mlagent_subcommands(command):
    core = RecordingCore()

    output = evaluate_pre_tool_use(bash_payload(command), domain_core=core)

    assert core.commands == []
    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "invalid_hook_arguments" in decision["permissionDecisionReason"]


def test_pre_tool_use_allows_literal_non_training_mlagent_subcommand():
    core = RecordingCore()

    output = evaluate_pre_tool_use(
        bash_payload("python -m src.agent.main status"),
        domain_core=core,
    )

    assert output is None
    assert core.commands == []


def test_pre_tool_use_ignores_non_training_bash_calls():
    core = RecordingCore()

    assert evaluate_pre_tool_use(
        bash_payload("pytest -q"),
        domain_core=core,
    ) is None
    assert core.commands == []


def test_pre_tool_use_internal_watchdog_denies_before_outer_hook_timeout():
    class SlowCore:
        def authorize_training(self, command):
            time.sleep(0.2)

    output = evaluate_pre_tool_use_with_timeout(
        bash_payload(
            "python -m src.agent.main explore --dataset-id ds-1 "
            "--dataset-version 1 --plan-id plan-1 --approval-id approval-1"
        ),
        domain_core=SlowCore(),
        timeout_seconds=0.01,
    )

    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "training_gate_timeout" in decision["permissionDecisionReason"]


def test_project_registers_real_claude_pre_tool_use_hook():
    project_root = Path(__file__).resolve().parents[2]
    settings = json.loads(
        (project_root / ".claude/settings.json").read_text(encoding="utf-8")
    )
    groups = settings["hooks"]["PreToolUse"]

    assert groups[0]["matcher"] == "Bash"
    handler = groups[0]["hooks"][0]
    command = handler["command"]
    assert ".claude/hooks/mlagent-training-gate.sh" in command
    assert handler["timeout"] >= 60
    assert (project_root / ".claude/hooks/mlagent-training-gate.sh").is_file()


def test_hook_wrapper_fails_closed_when_python_adapter_crashes():
    project_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        ["sh", str(project_root / ".claude/hooks/mlagent-training-gate.sh")],
        input=json.dumps(bash_payload("pytest -q")),
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(project_root),
            "MLAGENT_PYTHON": "/usr/bin/false",
        },
        check=False,
    )

    assert completed.returncode == 2
    assert "training approval hook failed" in completed.stderr.lower()


def bash_payload(command: str) -> dict:
    return {
        "session_id": "session-1",
        "cwd": "/workspace",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
