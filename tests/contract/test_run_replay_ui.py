"""AppTest acceptance for the historical Run replay sub-view (Issue #13)."""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.domain.memory_repository import MemoryRepository
from tests.integration.test_sop_repository import build_sop_workspace
from tests.integration.test_domain_core_sop import write_connection


def _workspace(tmp_path: Path, monkeypatch) -> None:
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root, "alice")
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(tmp_path))


def test_run_replay_renders_in_run_status(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=8).run()
    app = app.sidebar.radio[0].set_value("Run Status").run()
    assert not app.exception
    assert any("Historical replay" in str(s.value) for s in app.subheader)


def test_run_replay_read_only_does_not_raise_on_second_view(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=8).run()
    app = app.sidebar.radio[0].set_value("Run Status").run()
    assert not app.exception
    # re-run (re-select) must stay clean — viewing never writes
    app = app.sidebar.radio[0].set_value("Run Status").run()
    assert not app.exception
