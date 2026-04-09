#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: $PYTHON_BIN is not available on PATH." >&2
  exit 1
fi

if ! command -v llama-server >/dev/null 2>&1; then
  echo "Error: llama-server is required but not available on PATH." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$ROOT_DIR/computer_use_agent.py" "$@"
