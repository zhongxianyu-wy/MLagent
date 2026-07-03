"""Entry-point smoke tests: bin/mlagent wrapper (real shebang) + hook scripts emit valid JSON."""
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_bin_wrapper_version_via_real_shebang():
    """Execute bin/mlagent via its shebang (the real deployed invocation)."""
    proc = subprocess.run([str((_REPO_ROOT / "bin" / "mlagent").resolve()), "version"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "mlagent 0.1.0" in proc.stdout


def test_hook_scripts_emit_valid_json():
    for name, event in [("session-start", "SessionStart"), ("post-tool-use", "PostToolUse"), ("stop", "Stop")]:
        proc = subprocess.run(
            [str((_REPO_ROOT / "hooks" / name).resolve())],
            input='{"cwd":"."}',
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        data = json.loads(proc.stdout)
        assert data["hookSpecificOutput"]["hookEventName"] == event
