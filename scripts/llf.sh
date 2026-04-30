#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"
CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
    CHECK_ONLY=1
    shift
fi

if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "[i] linting..."
    uv run ruff check src/ tests/ "$@"

    echo "[i] checking formatting..."
    uv run ruff format --check src/ tests/ "$@"
    echo "[+] all done"
    exit 0
fi

echo "[i] linting and fixing..."
uv run ruff check --fix src/ "$@"

echo "[i] formatting..."
uv run ruff format src/ tests/ "$@"

echo "[+] all done"
