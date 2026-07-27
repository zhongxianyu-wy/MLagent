"""PostToolUse hook (Issue #15, AC#4).

Captures Code Revision changes after a managed-code edit and surfaces a short
reminder — WITHOUT copying terminal output or tool responses. Read-only.
"""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.domain.models import WorkspaceError

CAPTURE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def evaluate_post_tool_use(
    payload: dict[str, Any],
    domain_core: object | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
    if payload.get("hook_event_name") != "PostToolUse":
        return None
    if payload.get("tool_name") not in CAPTURE_TOOLS:
        return None
    if domain_core is None:
        return None
    env = environment or os.environ
    connection = env.get("MLAGENT_WORKSPACE_CONFIG")
    code_root = env.get("MLAGENT_CODE_ROOT") or payload.get("cwd")
    if not connection or not code_root:
        return None
    try:
        code_id = domain_core.resolve_code_id(Path(connection), Path(code_root))
        if not code_id:
            return None
        review = domain_core.get_code_review(
            Path(connection), Path(code_root), code_id
        )
    except (WorkspaceError, OSError, ValueError, TypeError):
        return None
    if not review.workspace_changed:
        return None
    version = review.active_revision.version if review.active_revision else None
    label = f"v{version}" if version is not None else "(none yet)"
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"Code workspace changed since Code Revision {label}. "
                "Capture it in Code Review to persist a new candidate revision."
            ),
        }
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    output = evaluate_post_tool_use(payload)
    if output is not None:
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
