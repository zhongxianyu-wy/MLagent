"""Unit tests for ClaudeCliExecutor: NDJSON parsing + Deterministic fake (Issue #12 T3).

The real ``SubprocessClaudeExecutor`` spawn is a human acceptance gate (it calls
the real ``claude`` CLI); these tests cover the pure NDJSON parser and the
deterministic fake used by all automated tests.
"""
from __future__ import annotations

from pathlib import Path

from src.domain.claude_cli_executor import (
    DeterministicClaudeExecutor,
    parse_stream_json_line,
    summarize_tool_input,
)
from src.domain.models import ClaudeCliResult, ClaudeStreamEvent


def _result(**over) -> ClaudeCliResult:
    base = dict(
        state="completed",
        tool_action_summary="Edited train.py",
        touched_files=("train.py",),
        started_at="2026-07-22T00:00:00Z",
        ended_at="2026-07-22T00:01:00Z",
    )
    base.update(over)
    return ClaudeCliResult(**base)


# --- NDJSON parsing --------------------------------------------------------


def test_parse_text_block():
    evs = parse_stream_json_line(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"hello"}]}}'
    )
    assert len(evs) == 1
    assert evs[0].kind == "text" and evs[0].text == "hello"


def test_parse_tool_use_block():
    evs = parse_stream_json_line(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Edit",'
        '"input":{"file_path":"train.py","new_string":"x"}}]}}'
    )
    assert evs[0].kind == "tool_use"
    assert evs[0].tool_name == "Edit"
    assert "train.py" in evs[0].tool_input_summary


def test_parse_tool_result_error_and_ok():
    err = parse_stream_json_line(
        '{"type":"user","message":{"content":[{"type":"tool_result","is_error":true,"content":"boom"}]}}'
    )
    assert err[0].kind == "tool_result" and err[0].tool_status == "error"
    ok = parse_stream_json_line(
        '{"type":"user","message":{"content":[{"type":"tool_result","is_error":false,"content":"ok"}]}}'
    )
    assert ok[0].tool_status == "ok"


def test_parse_system_init():
    evs = parse_stream_json_line('{"type":"system","subtype":"init","session_id":"sess-1"}')
    assert evs[0].kind == "system"


def test_parse_unknown_type_is_system_not_crash():
    evs = parse_stream_json_line('{"type":"something_new"}')
    assert evs[0].kind == "system"


def test_parse_garbage_returns_empty():
    assert parse_stream_json_line("not json") == []
    assert parse_stream_json_line("") == []


def test_parse_multiple_blocks_in_one_line():
    evs = parse_stream_json_line(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"a"},'
        '{"type":"tool_use","name":"Write","input":{"file_path":"f.py"}}]}}'
    )
    assert [e.kind for e in evs] == ["text", "tool_use"]


def test_summarize_tool_input_redacts_large_args():
    summary = summarize_tool_input({"file_path": "train.py", "new_string": "x" * 500})
    assert "train.py" in summary
    assert len(summary) < 120  # no full argument dump


# --- DeterministicClaudeExecutor -------------------------------------------


def test_deterministic_yields_events_in_order():
    events = (
        ClaudeStreamEvent(kind="text", sequence=1, text="a"),
        ClaudeStreamEvent(kind="text", sequence=2, text="b"),
    )
    ex = DeterministicClaudeExecutor(events=events, result=_result())
    iterator, get_result = ex.execute(
        "prompt",
        cwd=Path("/tmp/code"),
        workspace=Path("/tmp/ws"),
        session_id=None,
        allowed_tools=(),
        stop_requested=lambda: False,
        timeout_seconds=10,
    )
    assert [e.text for e in iterator] == ["a", "b"]
    assert get_result().touched_files == ("train.py",)


def test_deterministic_stop_breaks_iteration():
    events = (
        ClaudeStreamEvent(kind="text", sequence=1, text="a"),
        ClaudeStreamEvent(kind="text", sequence=2, text="b"),
        ClaudeStreamEvent(kind="text", sequence=3, text="c"),
    )
    ex = DeterministicClaudeExecutor(events=events, result=_result(state="stopped"))
    iterator, get_result = ex.execute(
        "prompt",
        cwd=Path("/tmp/code"),
        workspace=Path("/tmp/ws"),
        session_id=None,
        allowed_tools=(),
        stop_requested=lambda: True,
        timeout_seconds=10,
    )
    assert list(iterator) == []


def test_deterministic_passes_session_id_for_resume():
    ex = DeterministicClaudeExecutor(events=(), result=_result(session_id="sess-9"))
    _, get_result = ex.execute(
        "prompt",
        cwd=Path("/tmp/code"),
        workspace=Path("/tmp/ws"),
        session_id="sess-1",
        allowed_tools=("Read", "Edit"),
        stop_requested=lambda: False,
        timeout_seconds=5,
    )
    assert get_result().session_id == "sess-9"
