"""PreToolUse hook for managed-code writes (Issue #12, AC#4).

Jails ``Write``/``Edit``/``MultiEdit``/``NotebookEdit`` tool calls to the
managed code root and blocks any write into a protected Team Memory namespace
(those must go through DomainCore, e.g. ``save_code_revision``). The Bash
training gate (``src.agent.pre_tool_use``) is untouched and still owns
``explore`` approval — this hook only handles file-writing tools.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from src.domain.code_path_guard import validate_write_target

WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def _extract_targets(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path")
        return [path] if isinstance(path, str) and path else []
    if tool_name == "MultiEdit":
        targets: list[str] = []
        for entry in tool_input.get("edits") or []:
            if isinstance(entry, dict):
                path = entry.get("file_path")
                if isinstance(path, str) and path:
                    targets.append(path)
        return targets
    if tool_name == "NotebookEdit":
        path = tool_input.get("notebook_path")
        return [path] if isinstance(path, str) and path else []
    return []


def _deny(code: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{code}: {reason}",
        }
    }


def evaluate_pre_tool_use_writes(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if payload.get("hook_event_name") != "PreToolUse":
        return None
    tool_name = payload.get("tool_name")
    if tool_name not in WRITE_TOOLS:
        return None
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return _deny("invalid_hook_input", "tool_input must be an object")
    targets = _extract_targets(tool_name, tool_input)
    if not targets:
        return None  # no path to jail
    cwd = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
    workspace = os.environ.get("CLAUDE_PROJECT_DIR")
    if not cwd or not workspace:
        return _deny(
            "hook_misconfigured",
            "cwd and CLAUDE_PROJECT_DIR must be set so the managed root is known.",
        )
    for target in targets:
        reason = validate_write_target(target, Path(cwd), Path(workspace))
        if reason is not None:
            return _deny(
                reason,
                f"{target} is outside the managed code root or is a protected Team Memory asset.",
            )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps(_deny("invalid_hook_input", str(error))))
        return 0
    if not isinstance(payload, dict):
        print(json.dumps(_deny("invalid_hook_input", "Hook input must be an object.")))
        return 0
    output = evaluate_pre_tool_use_writes(payload)
    if output is not None:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
