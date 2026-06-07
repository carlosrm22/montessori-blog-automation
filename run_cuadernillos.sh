#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Genera el lote diario de cuadernillos (tope = CUADERNILLOS_MAX_PER_RUN).
exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/run_cuadernillos.py"
