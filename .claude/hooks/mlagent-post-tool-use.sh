#!/bin/sh
set -u

cd "${CLAUDE_PROJECT_DIR:?CLAUDE_PROJECT_DIR is required}"
if [ -n "${MLAGENT_PYTHON:-}" ]; then
    python_command=$MLAGENT_PYTHON
elif [ -x "$CLAUDE_PROJECT_DIR/.venv/bin/python" ]; then
    python_command="$CLAUDE_PROJECT_DIR/.venv/bin/python"
else
    python_command=python3
fi

"$python_command" -m src.agent.post_tool_use || true
