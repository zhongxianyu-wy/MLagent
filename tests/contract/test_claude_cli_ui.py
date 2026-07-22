"""AppTest acceptance for the Claude CLI sub-panel (Issue #12 T6).

Drives the Code Review module through attach -> disconnect. The Send step is
NOT exercised here (it would spawn the real ``claude`` CLI); streaming and
capture logic are covered at the DomainCore layer in test_claude_session_domain.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.memory_repository import MemoryRepository


def _workspace(tmp_path: Path, monkeypatch) -> None:
    memory_root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1", clock=lambda: "2026-07-22T00:00:00Z"
    ).bootstrap(memory_root, actor_id="alice")
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return c\n")
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(
        json.dumps({"repository_path": str(memory_root), "actor_id": "alice"})
    )
    # pre-register code_id so the Claude panel renders
    DomainCore(clock=lambda: "2026-07-22T00:00:00Z").register_code_id(
        connection, code_root, "baseline"
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(code_root))


def test_claude_panel_renders_in_code_review(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=8).run()
    app = app.sidebar.radio[0].set_value("Code Review").run()
    assert not app.exception
    assert any("Attach" in b.label for b in app.button)


def test_claude_panel_attach_then_disconnect(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=8).run()
    app = app.sidebar.radio[0].set_value("Code Review").run()
    assert not app.exception

    attach = next(b for b in app.button if "Attach" in b.label)
    app = attach.click().run()
    assert not app.exception
    # after attach, Disconnect is available
    assert any("Disconnect" in b.label for b in app.button)

    disconnect = next(b for b in app.button if "Disconnect" in b.label)
    app = disconnect.click().run()
    assert not app.exception
    # back to the attach state
    assert any("Attach" in b.label for b in app.button)
