#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Run only the Bluetooth console Playwright test against two virtual
# controllers.  Needs root for the controller setup, so the privileged steps
# go through sudo; everything else runs as the invoking user.
#
# The trap is the whole point of this script: the setup must always be undone,
# or leftover virtual controllers keep showing up in the system Bluetooth and
# audio stacks between test runs.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_TITLE="km-bt-test-server"
SERVER_LOG="/dev/shm/${SERVER_TITLE}.log"
SERVER_URL="http://127.0.0.1:8002"
PYTHON="${KAITHEM_PYTHON:-$ROOT_DIR/.venv/bin/python}"
SERVER_PID=""

stop_server() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        SERVER_PID=""
    fi
    killall -q "$SERVER_TITLE" 2>/dev/null || true
}

teardown() {
    local status=$?
    stop_server
    echo "Stopping virtual Bluetooth controllers"
    sudo bash "$ROOT_DIR/scripts/virtual-bluetooth-teardown.sh" || true
    exit "$status"
}
trap teardown EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

wait_for_server() {
    local attempt
    for attempt in $(seq 1 120); do
        if curl -fsS --max-time 2 "$SERVER_URL" >/dev/null 2>&1; then
            return 0
        fi
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "the test server exited:" >&2
            tail -n 50 "$SERVER_LOG" >&2
            return 1
        fi
        sleep 1
    done
    echo "the test server did not become ready:" >&2
    tail -n 50 "$SERVER_LOG" >&2
    return 1
}

if [ ! -x "$PYTHON" ]; then
    echo "Python interpreter not found: $PYTHON" >&2
    exit 1
fi

echo "Starting virtual Bluetooth controllers"
sudo bash "$ROOT_DIR/scripts/virtual-bluetooth-setup.sh"

echo "Starting the test server"
killall -q "$SERVER_TITLE" 2>/dev/null || true
"$PYTHON" "$ROOT_DIR/testing_server.py" --process-title "$SERVER_TITLE" \
    >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
wait_for_server

cd "$ROOT_DIR"
echo "Running the Bluetooth Playwright test"
npx playwright test playwright/test-bluetooth-console.spec.ts \
    --reporter=list --workers 1
