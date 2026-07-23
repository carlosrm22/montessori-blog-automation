#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Uso: $0 JOB_ID [RUTA_DE_IMAGEN]" >&2
  exit 2
fi

args=(--job "$1")
if [[ $# -eq 2 ]]; then
  args+=(--image "$2")
fi

exec "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/resume_manual_image.py" "${args[@]}"
