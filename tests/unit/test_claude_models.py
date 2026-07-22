"""Unit tests for Claude CLI session models + Code Revision audit fields (Issue #12 T1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.domain.models import (
    CandidateCodeFile,
    CaptureClaudeChangesCommand,
    ClaudeCliResult,
    ClaudeSessionHandle,
    ClaudeStreamEvent,
    CodeRevisionSnapshot,
    EditedFile,
    SaveCodeRevisionCommand,
    StartClaudeSessionCommand,
)

_SHA = "a" * 64


def _file(path: str = "train.py") -> CandidateCodeFile:
    return CandidateCodeFile(path=path, sha256=_SHA, size_bytes=10)


def _revision(**overrides) -> CodeRevisionSnapshot:
    base: dict = dict(
        asset_id="baseline-v1",
        asset_path="code-revisions/baseline/v0001/manifest.json",
        code_id="baseline",
        version=1,
        revision_fingerprint=_SHA,
        parent_revision_id=None,
        parent_revision_fingerprint=None,
        code_fingerprint=_SHA,
        entrypoint_path="train.py",
        files=(_file(),),
        origin="human",
        source_run_id=None,
        source_instance_id=None,
        change_summary="",
        created_at="2026-07-22T00:00:00Z",
        created_by="alice",
    )
    base.update(overrides)
    return CodeRevisionSnapshot(**base)


# --- Claude stream / result / handle / commands ----------------------------


def test_claude_stream_event_constructs():
    ev = ClaudeStreamEvent(kind="text", sequence=1, text="hello")
    assert ev.kind == "text" and ev.sequence == 1
    err = ClaudeStreamEvent(
        kind="tool_result", sequence=2, tool_name="Edit", tool_status="error"
    )
    assert err.tool_status == "error"


def test_claude_stream_event_rejects_unknown_kind():
    with pytest.raises(ValueError, match="kind"):
        ClaudeStreamEvent(kind="bogus", sequence=0)


def test_claude_stream_event_rejects_bad_tool_status():
    with pytest.raises(ValueError, match="tool_status"):
        ClaudeStreamEvent(kind="tool_use", sequence=1, tool_status="bogus")


def test_claude_cli_result_constructs():
    res = ClaudeCliResult(
        state="completed",
        tool_action_summary="Edited train.py",
        touched_files=("train.py",),
        started_at="2026-07-22T00:00:00Z",
        ended_at="2026-07-22T00:01:00Z",
        session_id="sess-1",
    )
    assert res.state == "completed"
    assert res.touched_files == ("train.py",)


def test_claude_cli_result_rejects_unknown_state():
    with pytest.raises(ValueError, match="state"):
        ClaudeCliResult(
            state="bogus",
            tool_action_summary="x",
            touched_files=(),
            started_at="t",
            ended_at="t",
        )


def test_claude_session_handle_constructs():
    h = ClaudeSessionHandle(
        handle_id="h-1",
        code_id="baseline",
        code_root="code",
        operator="alice",
        acquired_at="2026-07-22T00:00:00Z",
    )
    assert h.state == "connected"


def test_claude_session_handle_rejects_unknown_state():
    with pytest.raises(ValueError, match="state"):
        ClaudeSessionHandle(
            handle_id="h-1",
            code_id="baseline",
            code_root="code",
            operator="alice",
            acquired_at="t",
            state="bogus",
        )


def test_start_claude_session_command_constructs():
    cmd = StartClaudeSessionCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        operator="alice",
    )
    assert cmd.operator == "alice"


def test_capture_claude_changes_command_constructs():
    cmd = CaptureClaudeChangesCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        code_id="baseline",
        handle_id="h-1",
        change_summary="Edited train.py",
        touched_files=("train.py",),
        entrypoint_path="train.py",
        prompt_hash=_SHA,
        operator="alice",
    )
    assert cmd.prompt_hash == _SHA


def test_capture_command_requires_touched_files():
    with pytest.raises(ValueError, match="touched_files"):
        CaptureClaudeChangesCommand(
            connection_path=Path(".mlagent-workspace.json"),
            code_root=Path("code"),
            code_id="baseline",
            handle_id="h-1",
            change_summary="x",
            touched_files=(),
            entrypoint_path="train.py",
            prompt_hash=_SHA,
            operator="alice",
        )


# --- Code Revision audit fields (AC#7) -------------------------------------


def test_revision_defaults_agent_fields_none():
    rev = _revision()
    assert rev.agent_prompt_hash is None
    assert rev.agent_tool_summary is None


def test_revision_records_agent_audit_fields():
    rev = _revision(
        origin="agent",
        agent_prompt_hash=_SHA,
        agent_tool_summary="Edited train.py",
    )
    assert rev.agent_prompt_hash == _SHA
    assert rev.agent_tool_summary == "Edited train.py"


def test_revision_rejects_invalid_prompt_hash():
    with pytest.raises(ValueError, match="agent_prompt_hash"):
        _revision(origin="agent", agent_prompt_hash="not-a-hash")


def test_save_command_accepts_agent_fields():
    cmd = SaveCodeRevisionCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        code_id="baseline",
        entrypoint_path="train.py",
        edited_files=(EditedFile(path="train.py", content=b"x"),),
        expected_parent_fingerprint=None,
        change_summary="agent edit",
        created_by="alice",
        origin="agent",
        agent_prompt_hash=_SHA,
        agent_tool_summary="Edited train.py",
    )
    assert cmd.origin == "agent"
    assert cmd.agent_tool_summary == "Edited train.py"
