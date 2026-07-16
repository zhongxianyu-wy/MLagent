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

if ! "$python_command" -m src.agent.session_stop; then
    echo "MLagent Team Memory Stop sync failed." >&2
    printf '%s\n' '{"systemMessage":"MLagent Team Memory sync failed. Managed assets remain local; review Git status in the MLagent UI and retry synchronization."}'
fi
exit 0
