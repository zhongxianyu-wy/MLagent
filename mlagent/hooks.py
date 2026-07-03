"""Hook helpers (stdlib-only so hook scripts self-bootstrap without third-party deps).

T1 skeleton: only the stdin/stdout JSON plumbing. T10 wires the real behavior
(SessionStart: git pull + bootstrap inject + UI start; PostToolUse: capture;
Stop: distill + git sync + UI stop).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def read_hook_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def hook_output(event_name: str, additional_context: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": additional_context[:10000],
                }
            }
        )
    )


def cwd_memory_root(data: dict) -> Path:
    cwd = Path(data.get("cwd") or ".")
    return cwd / "project_memory"
