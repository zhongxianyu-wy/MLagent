from __future__ import annotations

import json
import os
import sys
from typing import Any, Mapping

from src.agent.sync_output import (
    bounded_failure_message,
    bounded_sync_message,
    resolve_connection_path,
)
from src.domain.models import WorkspaceError


def handle(
    payload: dict[str, Any],
    domain_core: object | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    if payload.get("hook_event_name") != "SessionStart":
        raise ValueError("hook_event_name must be SessionStart")
    if domain_core is None:
        from src.domain.core import DomainCore

        domain_core = DomainCore()
    status = domain_core.sync_session_start(
        resolve_connection_path(payload, environment or os.environ)
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": bounded_sync_message(status),
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Hook input must be an object.")
        output = handle(payload)
    except WorkspaceError as error:
        output = _failure_output(error.code)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        output = _failure_output("invalid_hook_input")
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


def _failure_output(code: str) -> dict[str, object]:
    message = bounded_failure_message(code)
    print(message, file=sys.stderr)
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": message,
        }
    }
if __name__ == "__main__":
    raise SystemExit(main())
