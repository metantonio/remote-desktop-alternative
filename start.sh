#!/usr/bin/env bash
# Desk - Remote Desktop Launcher for macOS and Linux

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[ERROR] Python 3 was not found!"
    echo "Please install Python 3 or create a virtual environment (.venv)."
    exit 1
fi

# Ensure local repository code is loaded first
export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"

echo "Starting Desk Remote Desktop Interface..."
exec "$PYTHON_BIN" -m desk gui "$@"
