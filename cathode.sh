#!/usr/bin/env bash
# Cathode launcher — source venv and run
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"
exec python "$SCRIPT_DIR/main.py" "$@"
