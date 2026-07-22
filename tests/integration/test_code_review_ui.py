"""Programmatic UI acceptance for the Code Review module (Issue #11).

Real desktop/mobile browser acceptance is a human gate; these AppTest runs
are the deterministic programmatic portion proving the module renders, can
register a code id, save a revision, and surface history through the shell.
"""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.domain.memory_repository import MemoryRepository


def _workspace(tmp_path: Path, monkeypatch) -> None:
    memory_root = tmp_path / "team-memory"
    MemoryRepository(
        id_factory=lambda: "tmr-1",
        clock=lambda: "2026-07-22T00:00:00Z",
    ).bootstrap(memory_root, actor_id="alice")
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_bytes(b"def build_estimator(c):\n    return c\n")
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(
        json.dumps({"repository_path": str(memory_root), "actor_id": "alice"})
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(code_root))


def _app(monkeypatch=None) -> AppTest:
    return AppTest.from_file(
        Path("src/ui/app.py").resolve(), default_timeout=8
    ).run()


def test_code_review_module_renders_register_prompt(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = _app()
    app = app.sidebar.radio[0].set_value("Code Review").run()
    assert not app.exception
    assert app.subheader[0].value == "Code Review"


def test_code_review_registers_and_lists_managed_files(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = _app()
    app = app.sidebar.radio[0].set_value("Code Review").run()
    # register a code id via the registration form
    app = app.text_input[0].set_value("baseline").run()
    register = next(b for b in app.button if "Register" in b.label)
    app = register.click().run()
    assert not app.exception
    # the managed file now appears in the File selectbox
    file_select = next(sb for sb in app.selectbox if sb.label == "File")
    assert "train.py" in file_select.value


def test_code_review_saves_revision_and_shows_history(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = _app()
    app = app.sidebar.radio[0].set_value("Code Review").run()
    app = app.text_input[0].set_value("baseline").run()
    app = next(b for b in app.button if "Register" in b.label).click().run()
    # fill change summary and save
    summary = next(t for t in app.text_input if t.label == "Change summary")
    app = summary.set_value("initial revision").run()
    save = next(b for b in app.button if "Save" in b.label)
    app = save.click().run()
    assert not app.exception
    # history table now present
    assert any(
        getattr(sub, "value", "") == "Revision history" for sub in app.subheader
    )
