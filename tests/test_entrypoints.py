"""Regression tests for executable entrypoint scripts (bin + hooks).

These scripts must self-bootstrap the plugin root onto ``sys.path`` so they work
without ``mlagent_memory`` being pre-installed on the interpreter's path.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
BIN_PATH = REPO_ROOT / "bin" / "mlagent-memory"

HOOK_CASES = [
    ("session-start", '{"cwd":"."}', "SessionStart"),
    ("post-tool-use", '{"tool_name":"Bash"}', "PostToolUse"),
    ("post-tool-batch", '{"tool_calls":[{"name":"Bash"}]}', "PostToolBatch"),
    ("stop", "", "Stop"),
]


def test_hook_scripts_self_bootstrap_via_shebang():
    """Each hook executes via its shebang and emits the expected hook event."""
    for name, stdin_payload, expected_event in HOOK_CASES:
        hook_path = HOOKS_DIR / name
        result = subprocess.run(
            [str(hook_path.resolve())],
            input=stdin_payload,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{name} exited {result.returncode}; stderr:\n{result.stderr}"
        )
        payload = json.loads(result.stdout)
        assert payload["hookSpecificOutput"]["hookEventName"] == expected_event, (
            f"{name}: expected {expected_event}, got {payload}"
        )


def test_bin_wrapper_version():
    """The bin wrapper prints the package version using the test interpreter."""
    result = subprocess.run(
        [sys.executable, str(BIN_PATH.resolve()), "version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}"
    assert "mlagent-memory 0.1.0" in result.stdout
