from __future__ import annotations

import json
import sys
from pathlib import Path


def read_hook_input() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return data


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
