"""Git sync: local-first memory ↔ remote (push at session end, pull at boot).

The project dir (parent of project_memory/) is the git repo. Operations are
non-interactive (GIT_TERMINAL_PROMPT=0) and fail-closed with a clear message
(never blocks Claude Code — the hook degrades to a terminal note).
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mlagent.errors import MlagentError


def _git(repo_dir: Path, args: list[str], allow_fail: bool = False) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ["git", "-C", str(repo_dir)] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0 and not allow_fail:
        raise MlagentError(f"git {' '.join(args)} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def sync_push(repo_dir: Path, message: str | None = None) -> str:
    """git add -A && git commit && git push (one-click sync)."""
    _git(repo_dir, ["add", "-A"])
    msg = message or f"mlagent sync {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
    _git(repo_dir, ["commit", "-m", msg], allow_fail=True)  # "nothing to commit" is OK
    _git(repo_dir, ["push"])
    return msg


def sync_pull(repo_dir: Path) -> str:
    """git pull --ff-only (sync from remote at boot)."""
    return _git(repo_dir, ["pull", "--ff-only"])
