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

if ! "$python_command" -m src.agent.pre_tool_use_writes; then
    echo "MLagent write-jail hook failed; blocking the write." >&2
    exit 2
fi
