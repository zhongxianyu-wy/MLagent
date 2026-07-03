"""UI launch/stop: detached uvicorn + port-seek + PID via lsof."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

PORT_FILE = Path.home() / ".mlagent" / "ui.port"
_MARKER = "x-mlagent-ui"


def _find_port(start: int = 8688, count: int = 20) -> int | None:
    for port in range(start, start + count):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def _is_ours(port: int) -> bool:
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/health")
        resp = urllib.request.urlopen(req, timeout=1)
        return resp.headers.get(_MARKER) is not None
    except Exception:
        return False


def launch(memory_root: Path, port: int | None = None) -> int:
    """Launch the UI server detached. Returns the port."""
    PORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    if PORT_FILE.exists():
        old = int(PORT_FILE.read_text().strip())
        if _is_ours(old):
            return old

    port = port or _find_port()
    if not port:
        raise RuntimeError("无可用端口")

    env = {**os.environ, "MLAGENT_MEMORY_ROOT": str(memory_root)}
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mlagent.ui.server:app",
         "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(20):
        if _is_ours(port):
            break
        time.sleep(0.5)

    PORT_FILE.write_text(str(port))
    return port


def stop() -> bool:
    """Stop the UI server. Returns True if stopped."""
    if not PORT_FILE.exists():
        return False
    port = int(PORT_FILE.read_text().strip())
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        )
        for pid_str in result.stdout.strip().split():
            if pid_str:
                os.kill(int(pid_str), signal.SIGTERM)
    except Exception:
        pass
    PORT_FILE.unlink(missing_ok=True)
    return True
