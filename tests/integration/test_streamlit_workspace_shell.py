from pathlib import Path

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
