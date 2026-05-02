#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ -d "$SCRIPT_DIR/src" ] && [ -d "$SCRIPT_DIR/tests" ]; then
    REPO_ROOT=$SCRIPT_DIR
elif [ -d "$SCRIPT_DIR/../src" ] && [ -d "$SCRIPT_DIR/../tests" ]; then
    REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
else
    echo "Could not locate project root containing src/ and tests/." >&2
    exit 1
fi

DATA_DIR="$REPO_ROOT/data"
mkdir -p "$DATA_DIR"

OUTPUT_FILE="$DATA_DIR/problems.json"
RAW_OUTPUT_FILE=$(mktemp "${TMPDIR:-/tmp}/promptify-llc.XXXXXX")
trap 'rm -f "$RAW_OUTPUT_FILE"' EXIT

UV_BIN=uv
if ! command -v "$UV_BIN" >/dev/null 2>&1; then
    UV_BIN=uv.exe
fi

cd "$REPO_ROOT"

if ! "$UV_BIN" run --with basedpyright basedpyright --outputjson src tests > "$RAW_OUTPUT_FILE"; then
    if [ ! -s "$RAW_OUTPUT_FILE" ]; then
        exit 1
    fi
fi

REPORT_REPO_ROOT=$REPO_ROOT
if pwd -W >/dev/null 2>&1; then
    REPORT_REPO_ROOT=$(pwd -W)
fi

if "$UV_BIN" run python "$SCRIPT_DIR/c.py" "$RAW_OUTPUT_FILE" "$OUTPUT_FILE" "$REPORT_REPO_ROOT"; then
    exit 0
fi

exit 1
