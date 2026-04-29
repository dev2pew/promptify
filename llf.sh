#!/usr/bin/env sh

set -eu

echo "[i] linting and fixing..."
uv run ruff check --fix src/

echo "[i] formatting..."
uv run ruff format src/ tests/

echo "[+] all done."
