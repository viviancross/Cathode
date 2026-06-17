#!/usr/bin/env bash
# Cathode launcher — run the venv's Python directly (no `source activate`, which
# avoids the shebang-length pitfall on long install paths).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/main.py" "$@"
