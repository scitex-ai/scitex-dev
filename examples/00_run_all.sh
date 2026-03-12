#!/bin/bash
# Run all scitex-dev examples
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Running scitex-dev examples ==="
echo

for script in "$SCRIPT_DIR"/[0-9][0-9]_*.py; do
    [ -f "$script" ] || continue
    echo "--- $(basename "$script") ---"
    python "$script"
    echo
done

echo "=== All examples completed ==="
