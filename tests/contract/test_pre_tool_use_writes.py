"""Contract tests for the PreToolUse write jail (Issue #12 T5, AC#4)."""
from __future__ import annotations

from pathlib import Path

from src.agent.pre_tool_use_writes import evaluate_pre_tool_use_writes


def _payload(tool_name: str, tool_input: dict, cwd: Path) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": str(cwd),
    }


def _denied(result) -> bool:
    return (
        result is not None
        and result["hookSpecificOutput"]["permissionDecision"] == "deny"
    )


def test_write_inside_code_root_allowed(tmp_path: Path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload("Write", {"file_path": "train.py", "content": "x"}, code)
    assert evaluate_pre_tool_use_writes(payload) is None


def test_write_outside_code_root_denied(tmp_path: Path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload("Write", {"file_path": "../escape.py", "content": "x"}, code)
    assert _denied(evaluate_pre_tool_use_writes(payload))


def test_absolute_path_outside_denied(tmp_path: Path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload("Write", {"file_path": "/etc/passwd", "content": "x"}, code)
    assert _denied(evaluate_pre_tool_use_writes(payload))


def test_write_to_team_memory_namespace_denied(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    # code_root == workspace: a broad config; writing to runs/ is protected
    payload = _payload(
        "Write", {"file_path": "runs/r1/manifest.json", "content": "x"}, tmp_path
    )
    assert _denied(evaluate_pre_tool_use_writes(payload))


def test_multiedit_one_bad_target_denies_whole_call(tmp_path: Path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload(
        "MultiEdit",
        {
            "edits": [
                {"file_path": "train.py", "new_string": "x"},
                {"file_path": "../escape.py", "new_string": "y"},
            ]
        },
        code,
    )
    assert _denied(evaluate_pre_tool_use_writes(payload))


def test_notebook_edit_jailed(tmp_path: Path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload(
        "NotebookEdit", {"notebook_path": "../escape.ipynb", "new_source": "x"}, code
    )
    assert _denied(evaluate_pre_tool_use_writes(payload))


def test_edit_uses_file_path(tmp_path: Path, monkeypatch):
    code = tmp_path / "code"
    code.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload(
        "Edit", {"file_path": "sub/mod.py", "old_string": "a", "new_string": "b"}, code
    )
    assert evaluate_pre_tool_use_writes(payload) is None


def test_non_write_tool_ignored(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload("Read", {"file_path": "/etc/passwd"}, tmp_path / "code")
    assert evaluate_pre_tool_use_writes(payload) is None


def test_bash_not_handled_by_writes_hook(tmp_path: Path, monkeypatch):
    """The writes hook must NOT touch Bash — the training gate owns it (AC#4)."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    payload = _payload(
        "Bash", {"command": "python -m src.agent.main explore"}, tmp_path / "code"
    )
    assert evaluate_pre_tool_use_writes(payload) is None
