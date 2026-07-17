import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.domain.core import DomainCore
from src.domain.models import BootstrapMemoryCommand


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def git(
    root: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


@dataclass(frozen=True)
class ConfiguredHookWorkspace:
    root: Path
    memory: Path
    remote: Path
    connection: Path
    environment: dict[str, str]
    initial_head: str


@pytest.fixture
def configured_hook_workspace(tmp_path: Path) -> ConfiguredHookWorkspace:
    root = tmp_path / "workspace"
    root.mkdir()
    remote = tmp_path / "secret-token-team-memory.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        capture_output=True,
        text=True,
        check=True,
    )
    memory = tmp_path / "memory"
    connection = root / ".mlagent-workspace.json"
    DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory,
            actor_id="alice",
            remote_url=str(remote),
            connection_path=connection,
        )
    )
    branch = git(memory, "branch", "--show-current").stdout.strip()
    git(memory, "push", "--set-upstream", "origin", f"HEAD:{branch}")
    environment = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(PROJECT_ROOT),
        "MLAGENT_PYTHON": str(PROJECT_ROOT / ".venv/bin/python"),
        "MLAGENT_WORKSPACE_CONFIG": str(connection),
    }
    return ConfiguredHookWorkspace(
        root=root,
        memory=memory,
        remote=remote,
        connection=connection,
        environment=environment,
        initial_head=git(memory, "rev-parse", "HEAD").stdout.strip(),
    )


def run_hook(
    relative: str,
    payload: dict,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(PROJECT_ROOT / relative)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def test_session_start_hook_delegates_and_emits_bounded_context(
    configured_hook_workspace,
):
    result = run_hook(
        ".claude/hooks/mlagent-session-start.sh",
        {
            "session_id": "session-1",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "SessionStart",
            "source": "startup",
            "model": "claude-test",
        },
        configured_hook_workspace.environment,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    output = payload["hookSpecificOutput"]
    assert output["hookEventName"] == "SessionStart"
    assert "Synced" in output["additionalContext"]
    assert "session-1" in output["additionalContext"]
    assert len(output["additionalContext"]) <= 800
    assert str(configured_hook_workspace.remote) not in result.stdout
    assert "secret-token" not in result.stdout
    assert (
        configured_hook_workspace.memory
        / "raw-records/sessions/session-1/start.json"
    ).is_file()


def test_stop_hook_commits_managed_changes_without_blocking_stop(
    configured_hook_workspace,
):
    started = run_hook(
        ".claude/hooks/mlagent-session-start.sh",
        {
            "session_id": "session-1",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
        configured_hook_workspace.environment,
    )
    assert started.returncode == 0

    result = run_hook(
        ".claude/hooks/mlagent-session-stop.sh",
        {
            "session_id": "session-1",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "last_assistant_message": "Done",
            "background_tasks": [],
            "session_crons": [],
        },
        configured_hook_workspace.environment,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload.get("decision") is None
    assert "Synced" in payload["systemMessage"]
    assert "no reusable experience" in payload["systemMessage"].lower()
    assert len(payload["systemMessage"]) <= 800
    assert (
        git(configured_hook_workspace.memory, "rev-parse", "HEAD").stdout.strip()
        != configured_hook_workspace.initial_head
    )
    assert str(configured_hook_workspace.remote) not in result.stdout
    stop_record = json.loads(
        (
            configured_hook_workspace.memory
            / "raw-records/sessions/session-1/stop.json"
        ).read_text(encoding="utf-8")
    )
    assert stop_record["outcome"] == "no_op"


def test_stop_hook_extracts_current_session_training_candidate(
    configured_hook_workspace,
):
    seed_hook_parent(configured_hook_workspace.memory)
    git(configured_hook_workspace.memory, "add", "--", "datasets", "runs", "raw-records")
    git(
        configured_hook_workspace.memory,
        "-c",
        "user.name=alice",
        "-c",
        "user.email=mlagent@local",
        "commit",
        "-m",
        "test: seed parent training evidence",
    )
    git(configured_hook_workspace.memory, "push")
    started = run_hook(
        ".claude/hooks/mlagent-session-start.sh",
        {
            "session_id": "session-training",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "SessionStart",
            "source": "startup",
        },
        configured_hook_workspace.environment,
    )
    assert started.returncode == 0
    seed_hook_child(
        configured_hook_workspace.memory,
        "session-training",
    )

    result = run_hook(
        ".claude/hooks/mlagent-session-stop.sh",
        {
            "session_id": "session-training",
            "cwd": str(configured_hook_workspace.root),
            "hook_event_name": "Stop",
            "stop_hook_active": False,
        },
        configured_hook_workspace.environment,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "Created 1" in payload["systemMessage"]
    candidates = tuple(
        configured_hook_workspace.memory.glob("experiences/*/*.json")
    )
    assert len(candidates) == 1
    candidate = json.loads(candidates[0].read_text(encoding="utf-8"))
    assert candidate["state"] == "pending"
    assert candidate["extraction_session_id"] == "session-training"


@pytest.mark.parametrize(
    ("hook", "event"),
    (
        (".claude/hooks/mlagent-session-start.sh", "SessionStart"),
        (".claude/hooks/mlagent-session-stop.sh", "Stop"),
    ),
)
def test_sync_hooks_make_malformed_input_visible_without_blocking(
    configured_hook_workspace,
    hook,
    event,
):
    result = run_hook(
        hook,
        {"hook_event_name": f"Not{event}"},
        configured_hook_workspace.environment,
    )

    assert result.returncode == 0
    assert "failed" in result.stdout.lower()
    assert "failed" in result.stderr.lower()
    assert json.loads(result.stdout).get("decision") is None


def test_project_registers_session_lifecycle_hooks():
    settings = json.loads(
        (PROJECT_ROOT / ".claude/settings.json").read_text(encoding="utf-8")
    )

    start = settings["hooks"]["SessionStart"][0]
    assert start["matcher"] == "startup|resume|clear|compact"
    start_handler = start["hooks"][0]
    assert ".claude/hooks/mlagent-session-start.sh" in start_handler["command"]
    assert start_handler["timeout"] >= 60

    stop = settings["hooks"]["Stop"][0]
    assert "matcher" not in stop
    stop_handler = stop["hooks"][0]
    assert ".claude/hooks/mlagent-session-stop.sh" in stop_handler["command"]
    assert stop_handler["timeout"] >= 60


@pytest.mark.parametrize(
    ("hook", "output_key"),
    (
        (".claude/hooks/mlagent-session-start.sh", "hookSpecificOutput"),
        (".claude/hooks/mlagent-session-stop.sh", "systemMessage"),
    ),
)
def test_sync_hook_wrappers_fail_visible_and_nonblocking_when_python_crashes(
    configured_hook_workspace,
    hook,
    output_key,
):
    environment = {
        **configured_hook_workspace.environment,
        "MLAGENT_PYTHON": "/usr/bin/false",
    }

    result = run_hook(
        hook,
        {"hook_event_name": "unused"},
        environment,
    )

    assert result.returncode == 0
    assert output_key in json.loads(result.stdout)
    assert "failed" in result.stderr.lower()


def seed_hook_parent(memory: Path) -> None:
    write_json(
        memory / "datasets/ds-1/v0001/manifest.json",
        {
            "asset_type": "dataset_version",
            "asset_id": "ds-1:v1",
            "dataset_id": "ds-1",
        },
    )
    write_json(
        memory / "raw-records/runs/run-1/event-start.json",
        {
            "asset_type": "run_event",
            "asset_id": "event-start",
            "run_id": "run-1",
            "event_type": "run_started",
        },
    )
    write_hook_instance(
        memory,
        "instance-parent",
        "event-parent",
        metric=0.7,
        parent_id=None,
        planning_session_id="session-historical",
    )


def seed_hook_child(memory: Path, session_id: str) -> None:
    write_hook_instance(
        memory,
        "instance-child",
        "event-child",
        metric=0.8,
        parent_id="instance-parent",
        planning_session_id=session_id,
    )


def write_hook_instance(
    memory: Path,
    instance_id: str,
    event_id: str,
    *,
    metric: float,
    parent_id: str | None,
    planning_session_id: str,
) -> None:
    root = memory / f"runs/run-1/instances/{instance_id}"
    write_json(
        root / "input.json",
        {
            "run_id": "run-1",
            "instance_id": instance_id,
            "dataset_asset_path": "datasets/ds-1/v0001/manifest.json",
            "planning_session_id": planning_session_id,
            "optimization_direction": "feature_filtering",
        },
    )
    write_json(
        root / "manifest.json",
        {
            "asset_type": "training_instance",
            "asset_id": instance_id,
            "run_id": "run-1",
            "state": "completed",
            "parent_instance_id": parent_id,
            "primary_metric_name": "roc_auc",
            "primary_metric_value": metric,
            "optimization_direction": "feature_filtering",
        },
    )
    write_json(
        memory / f"raw-records/runs/run-1/{event_id}.json",
        {
            "asset_type": "run_event",
            "asset_id": event_id,
            "run_id": "run-1",
            "event_type": "instance_completed",
            "state": "completed",
            "instance_id": instance_id,
        },
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
