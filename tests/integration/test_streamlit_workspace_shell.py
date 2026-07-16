from pathlib import Path
import json
import os
import subprocess
import sys

from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.models import BootstrapMemoryCommand
from src.ui.shell import NAVIGATION


def test_streamlit_shell_renders_domain_core_workspace_context(tmp_path, monkeypatch):
    connection_path = tmp_path / ".mlagent-workspace.json"
    DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-14T00:00:00Z",
    ).bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()

    assert not app.exception
    assert tuple(app.sidebar.radio[0].options) == NAVIGATION
    assert app.sidebar.radio[0].value == "Code Review"
    assert [(metric.label, metric.value) for metric in app.metric[:5]] == [
        ("Workspace", "tmr-1"),
        ("Dataset", "Not started"),
        ("Run", "Not started"),
        ("Git", "Pending confirmation"),
        ("Writer", "alice"),
    ]
    assert app.subheader[0].value == "Code Review"


def test_streamlit_shell_renders_saved_git_conflict_projection(
    tmp_path,
    monkeypatch,
):
    connection_path = tmp_path / ".mlagent-workspace.json"
    workspace = DomainCore(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-16T00:00:00Z",
    ).bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    state_path = workspace.repository_path / ".mlagent-local/sync-state.json"
    state_path.write_text(
        json.dumps(
            {
                "state": "conflict",
                "branch": "main",
                "local_head": "local-sha",
                "remote_head": "remote-sha",
                "ahead_count": 1,
                "behind_count": 1,
                "changed_managed_paths": [],
                "conflict_paths": ["experiences/shared.json"],
                "last_attempt_at": "2026-07-16T00:00:00Z",
                "last_success_at": None,
                "sync_commit": "local-sha",
                "message": "The same path changed on both branches.",
                "next_action": "Review both committed versions.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=5,
    ).run()

    assert not app.exception
    assert [(metric.label, metric.value) for metric in app.metric[:5]] == [
        ("Workspace", "tmr-1"),
        ("Dataset", "Not started"),
        ("Run", "Not started"),
        ("Git", "Conflict"),
        ("Writer", "alice"),
    ]


def test_streamlit_script_resolves_project_package_when_run_as_entrypoint(
    tmp_path,
):
    connection_path = tmp_path / ".mlagent-workspace.json"
    DomainCore().bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    environment = os.environ.copy()
    environment["MLAGENT_WORKSPACE_CONFIG"] = str(connection_path)

    result = subprocess.run(
        [sys.executable, "src/ui/app.py"],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
