"""Unit tests for the PostToolUse hook (Issue #15 T4, AC#4)."""
from __future__ import annotations

from pathlib import Path

from src.agent.post_tool_use import evaluate_post_tool_use


class _Review:
    def __init__(self, changed, version=None):
        self.workspace_changed = changed
        self.active_revision = (
            type("R", (), {"version": version})() if version is not None else None
        )


class _FakeCore:
    def __init__(self, changed=True, version=1, code_id="baseline"):
        self._changed = changed
        self._version = version
        self._code_id = code_id

    def resolve_code_id(self, connection, root):
        return self._code_id

    def get_code_review(self, connection, root, code_id):
        return _Review(self._changed, self._version)


def _payload(tool="Write"):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {},
        "tool_response": {"content": "long terminal output that must NOT be copied"},
    }


def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(tmp_path / "conn.json"))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(tmp_path / "code"))


def test_post_tool_use_records_code_revision_change(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    out = evaluate_post_tool_use(_payload(), domain_core=_FakeCore(changed=True, version=2))
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "changed" in ctx and "v2" in ctx


def test_post_tool_use_does_not_copy_terminal_output(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    out = evaluate_post_tool_use(_payload(), domain_core=_FakeCore(changed=True))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "long terminal output" not in ctx


def test_post_tool_use_no_change_returns_none(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    assert evaluate_post_tool_use(_payload(), domain_core=_FakeCore(changed=False)) is None


def test_post_tool_use_ignores_non_capture_tool(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    assert evaluate_post_tool_use(_payload("Read"), domain_core=_FakeCore(changed=True)) is None


def test_post_tool_use_no_code_id_returns_none(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    assert evaluate_post_tool_use(_payload(), domain_core=_FakeCore(code_id=None)) is None
