"""Claude Code CLI executor — injectable, streams parsed NDJSON events.

Production ``SubprocessClaudeExecutor`` spawns the real ``claude`` CLI
(``-p`` / ``--output-format stream-json``) and forwards parsed events through a
queue so the UI can render text/tool/error incrementally. The lifecycle
(spawn + poll ``stop_requested`` + timeout + ``killpg``) mirrors
``SubprocessTrainingExecutor``. Tests use ``DeterministicClaudeExecutor`` so the
whole suite is hermetic; the real spawn is a human acceptance gate.
"""
from __future__ import annotations

import json
import os
import queue as queue_mod
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from src.domain.models import ClaudeCliResult, ClaudeStreamEvent, WorkspaceError


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def summarize_tool_input(tool_input: object) -> str:
    """Short, non-sensitive summary of a tool_use input (never dumps full args)."""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value[:100]
    if tool_input:
        key = next(iter(tool_input))
        return f"{key}={str(tool_input[key])[:40]}"
    return ""


def parse_stream_json_line(line: str) -> list[ClaudeStreamEvent]:
    """Parse one NDJSON line of ``claude --output-format stream-json`` into events.

    Unknown shapes degrade to a ``system`` event rather than raising, so a CLI
    schema drift never crashes the stream.
    """
    stripped = line.strip()
    if not stripped:
        return []
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []

    events: list[ClaudeStreamEvent] = []

    def _seq() -> int:
        return len(events) + 1

    msg_type = obj.get("type")
    if msg_type == "system":
        events.append(
            ClaudeStreamEvent(
                kind="system",
                sequence=_seq(),
                text=str(obj.get("subtype", "system")),
            )
        )
    elif msg_type == "assistant":
        content = (obj.get("message") or {}).get("content") or []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                events.append(
                    ClaudeStreamEvent(
                        kind="text", sequence=_seq(), text=str(block.get("text", ""))
                    )
                )
            elif btype == "tool_use":
                events.append(
                    ClaudeStreamEvent(
                        kind="tool_use",
                        sequence=_seq(),
                        tool_name=block.get("name"),
                        tool_input_summary=summarize_tool_input(block.get("input", {})),
                        tool_status="running",
                    )
                )
    elif msg_type == "user":
        content = (obj.get("message") or {}).get("content") or []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            is_error = bool(block.get("is_error", False))
            text = str(block.get("content", ""))
            events.append(
                ClaudeStreamEvent(
                    kind="tool_result",
                    sequence=_seq(),
                    tool_status="error" if is_error else "ok",
                    text=(text[:200] or None),
                )
            )
    else:
        events.append(
            ClaudeStreamEvent(
                kind="system", sequence=_seq(), text=str(msg_type or "event")
            )
        )
    return events


class ClaudeCliExecutor(Protocol):
    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        workspace: Path,
        session_id: str | None,
        allowed_tools: tuple[str, ...],
        stop_requested: Callable[[], bool],
        timeout_seconds: float,
    ) -> tuple[Iterator[ClaudeStreamEvent], Callable[[], ClaudeCliResult]]:
        ...


class DeterministicClaudeExecutor:
    """Fake executor: yields scripted events, returns a scripted result.

    Mirrors ``DeterministicExecutor`` for training — lets every Claude-session
    test run without the real CLI.
    """

    def __init__(
        self,
        *,
        events: tuple[ClaudeStreamEvent, ...],
        result: ClaudeCliResult,
    ) -> None:
        self._events = tuple(events)
        self._result = result

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        workspace: Path,
        session_id: str | None,
        allowed_tools: tuple[str, ...],
        stop_requested: Callable[[], bool],
        timeout_seconds: float,
    ) -> tuple[Iterator[ClaudeStreamEvent], Callable[[], ClaudeCliResult]]:
        def _gen() -> Iterator[ClaudeStreamEvent]:
            for event in self._events:
                if stop_requested():
                    return
                yield event

        return _gen(), lambda: self._result


def _terminate(process: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def _summarize_actions(touched: tuple[str, ...]) -> str:
    if not touched:
        return "No file changes"
    return "Edited " + ", ".join(touched)


class SubprocessClaudeExecutor:
    """Production executor: spawns the real ``claude`` CLI under the workspace."""

    def __init__(
        self,
        claude_bin: str = "claude",
        poll_interval: float = 0.1,
    ) -> None:
        self.claude_bin = claude_bin
        self.poll_interval = poll_interval
        self._last_result: ClaudeCliResult | None = None

    def execute(
        self,
        prompt: str,
        *,
        cwd: Path,
        workspace: Path,
        session_id: str | None,
        allowed_tools: tuple[str, ...],
        stop_requested: Callable[[], bool],
        timeout_seconds: float,
    ) -> tuple[Iterator[ClaudeStreamEvent], Callable[[], ClaudeCliResult]]:
        settings = workspace / ".claude" / "settings.json"
        if not settings.exists():
            raise WorkspaceError(
                code="claude_hook_unavailable",
                message="The workspace has no .claude/settings.json; the PreToolUse jail cannot fire.",
                next_action="Attach the session from a configured MLagent workspace.",
            )
        cmd = [self.claude_bin, "-p", prompt, "--output-format", "stream-json"]
        if session_id:
            cmd += ["--resume", session_id]
        if allowed_tools:
            cmd += ["--allowedTools", ",".join(allowed_tools)]
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(workspace)}
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=True,
        )
        event_queue: queue_mod.Queue[ClaudeStreamEvent | None] = queue_mod.Queue()
        touched: list[str] = []

        def _drain() -> None:
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    for event in parse_stream_json_line(line):
                        if (
                            event.kind == "tool_use"
                            and event.tool_input_summary
                        ):
                            path = event.tool_input_summary.split(",")[0].strip()
                            if path and path not in touched:
                                touched.append(path)
                        event_queue.put(event)
            finally:
                event_queue.put(None)

        thread = threading.Thread(target=_drain, daemon=True)
        thread.start()
        started = _utc_now()

        def _gen() -> Iterator[ClaudeStreamEvent]:
            deadline = time.monotonic() + timeout_seconds
            terminal = "completed"
            error_summary: str | None = None
            while True:
                if stop_requested():
                    terminal = "stopped"
                    _terminate(process)
                    break
                if time.monotonic() > deadline:
                    terminal = "timed_out"
                    error_summary = "Claude CLI exceeded the timeout."
                    _terminate(process)
                    break
                try:
                    item = event_queue.get(timeout=self.poll_interval)
                except queue_mod.Empty:
                    continue
                if item is None:
                    break
                yield item
            thread.join(timeout=3)
            return_code = process.poll()
            if return_code not in (None, 0) and terminal == "completed":
                terminal = "failed"
                error_summary = f"Claude CLI exited with code {return_code}."
            self._last_result = ClaudeCliResult(
                state=terminal,
                session_id=session_id,
                tool_action_summary=_summarize_actions(tuple(touched)),
                touched_files=tuple(touched),
                error_code=None if terminal == "completed" else terminal,
                error_summary=error_summary,
                started_at=started,
                ended_at=_utc_now(),
            )

        def _get_result() -> ClaudeCliResult:
            if self._last_result is not None:
                return self._last_result
            return ClaudeCliResult(
                state="failed",
                tool_action_summary="(no result)",
                touched_files=(),
                started_at=started,
                ended_at=_utc_now(),
                error_code="no_result",
            )

        return _gen(), _get_result
