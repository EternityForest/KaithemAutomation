#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Create two virtual Bluetooth controllers for the E2E test.
#
#   host   - controller that runs the scan/pairing side
#   target - controller that advertises a battery GATT service
#
# Both are LE-only on purpose.  A dual-mode (BR/EDR) controller makes BlueZ
# register the audio profiles, which surfaces the virtual controller as a
# Bluetooth speaker in the system audio stack and can disturb other tests.
# The test only needs LE discovery, pairing, and GATT, and audio behaviour is
# covered at the OS level, so this script deliberately never brings up BR/EDR
# and refuses to continue if a controller still reports BR/EDR support.
#
# Run as root (the Makefile target uses sudo).  The runtime directory and
# env.json are handed back to the invoking user so Playwright can read them.
#
# The controller addresses are assigned by btvirt and reported in env.json.
# They cannot be pinned to fixed values, so nothing may depend on a specific
# address.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${KAITHEM_BT_RUNTIME_DIR:-/tmp/kaithem-bt}"
HOST_NAME="km-bt-host"
TARGET_NAME="km-bt-target"
PYTHON="${KAITHEM_PYTHON:-$ROOT_DIR/.venv/bin/python}"
BTMGMT_TIMEOUT=15

# shellcheck source=scripts/virtual-bluetooth-common.sh
. "$ROOT_DIR/scripts/virtual-bluetooth-common.sh"

if [ "$(id -u)" -ne 0 ]; then
    echo "virtual-bluetooth-setup.sh must run as root (use sudo)" >&2
    exit 1
fi

if ! command -v btvirt >/dev/null 2>&1; then
    echo "btvirt is not installed (bluez-test-tools)" >&2
    exit 1
fi
if [ ! -x "$PYTHON" ]; then
    echo "Python interpreter not found: $PYTHON" >&2
    exit 1
fi
if [ ! -e /dev/vhci ]; then
    echo "/dev/vhci is missing; the vhci kernel module is not loaded" >&2
    exit 1
fi

# Stop controllers left over from an earlier run and delete the BlueZ
# settings they created.  Leftovers are the usual reason the system shows
# virtual Bluetooth speakers: btvirt is dual-mode by default, so BlueZ
# registers the audio profiles and the audio stack picks the controller up as
# a speaker.  Nothing besides this test harness runs btvirt, so reclaiming
# them is safe and is the only way back to a clean state.
stop_leftover_controllers() {
    local leftover_settings
    leftover_settings="$(list_virtual_adapters)"
    if pgrep -x btvirt >/dev/null 2>&1; then
        echo "stopping leftover virtual controllers:" >&2
        pgrep -a -x btvirt >&2 || true
    fi
    # Our own controllers run under a symlink name, so `killall btvirt` does
    # not match them.
    killall -q btvirt "$HOST_NAME" "$TARGET_NAME" 2>/dev/null || true
    local attempt
    for attempt in $(seq 1 50); do
        if ! pgrep -x btvirt >/dev/null 2>&1 &&
            ! pgrep -x "$HOST_NAME" >/dev/null 2>&1 &&
            ! pgrep -x "$TARGET_NAME" >/dev/null 2>&1; then
            break
        fi
        sleep 0.1
    done
    if pgrep -x btvirt >/dev/null 2>&1 ||
        pgrep -x "$HOST_NAME" >/dev/null 2>&1 ||
        pgrep -x "$TARGET_NAME" >/dev/null 2>&1; then
        echo "could not stop the leftover virtual controllers" >&2
        return 1
    fi
    wait_for_virtual_adapters_to_disappear
    wait_for_adapters_to_settle
    remove_settings_for_gone "$leftover_settings"
    remove_marked_adapter_settings
}

# Remove leftovers from a previous run.
if [ -f "$RUNTIME_DIR/gatt.pid" ]; then
    kill "$(cat "$RUNTIME_DIR/gatt.pid")" 2>/dev/null || true
fi
stop_leftover_controllers
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR/bin" "$RUNTIME_DIR/log"

# Never leave virtual controllers behind when setup fails halfway through.
GATT_PID=""
cleanup_on_error() {
    local status=$?
    if [ "$status" -ne 0 ]; then
        if [ -n "$GATT_PID" ]; then
            kill "$GATT_PID" 2>/dev/null || true
        fi
        killall -q "$HOST_NAME" "$TARGET_NAME" 2>/dev/null || true
        killall -q -w "$HOST_NAME" "$TARGET_NAME" 2>/dev/null || true
        # Nothing may be left behind for a later run to trip over.
        wait_for_virtual_adapters_to_disappear
        remove_marked_adapter_settings
    fi
    return "$status"
}
trap cleanup_on_error EXIT

ln -s "$(command -v btvirt)" "$RUNTIME_DIR/bin/$HOST_NAME"
ln -s "$(command -v btvirt)" "$RUNTIME_DIR/bin/$TARGET_NAME"

start_controller() {
    local name="$1"
    # -l1 selects one local emulator; -L makes that emulator LE-only.  The two
    # are not interchangeable: plain "-L" creates no controller at all and
    # btvirt exits with "No emulator specified".
    nohup bash -c 'exec -a "$0" "$0" -l1 -L' "$RUNTIME_DIR/bin/$name" \
        >"$RUNTIME_DIR/log/$name.log" 2>&1 &
    echo "$!"
}

new_adapter() {
    local existing="$1"
    comm -13 <(printf '%s\n' "$existing") <(list_adapters)
}

wait_for_adapter() {
    local existing="$1"
    local name="$2"
    local pid="$3"
    local index
    for _ in $(seq 1 100); do
        index="$(new_adapter "$existing")"
        if [ -n "$index" ]; then
            printf '%s\n' "$index" | head -n 1
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 0.1
    done
    echo "the $name controller did not appear:" >&2
    cat "$RUNTIME_DIR/log/$name.log" >&2
    return 1
}

configure_adapter() {
    local index="$1"
    # The address btvirt assigned is the one the test uses; there is no
    # supported way to override it (see list_virtual_adapters).
    timeout "$BTMGMT_TIMEOUT" btmgmt --index "$index" power on \
        >/dev/null 2>&1 || true
}

# Teardown deletes the BlueZ settings of every adapter on the virtual bus, so
# make sure these controllers really are virtual before the test starts.
assert_virtual_bus() {
    local index="$1"
    local bus
    bus="$(adapter_bus "$index")"
    if [ "$bus" != "Virtual" ]; then
        echo "hci$index is not on the virtual HCI bus ($bus)" >&2
        return 1
    fi
}

# Abort unless the controller really is BR/EDR-less.  A controller that
# supports BR/EDR makes BlueZ register the audio profiles, and the host then
# discovers the other virtual controller as a Bluetooth speaker with A2DP
# UUIDs.  That is the system state we must never create.
assert_le_only() {
    local index="$1"
    local info
    info="$(timeout 10 btmgmt --index "$index" info 2>/dev/null || true)"
    if [ -z "$info" ]; then
        echo "could not read the settings of hci$index" >&2
        return 1
    fi
    if printf '%s\n' "$info" | grep -q 'br/edr'; then
        echo "hci$index supports BR/EDR instead of being LE-only:" >&2
        printf '%s\n' "$info" >&2
        return 1
    fi
}

BEFORE="$(list_adapters)"
HOST_PID="$(start_controller "$HOST_NAME")"
HOST_INDEX="$(wait_for_adapter "$BEFORE" "$HOST_NAME" "$HOST_PID")" || exit 1

BEFORE="$(list_adapters)"
TARGET_PID="$(start_controller "$TARGET_NAME")"
TARGET_INDEX="$(wait_for_adapter "$BEFORE" "$TARGET_NAME" \
    "$TARGET_PID")" || exit 1

HOST_NUM="${HOST_INDEX#hci}"
TARGET_NUM="${TARGET_INDEX#hci}"

configure_adapter "$HOST_NUM"
configure_adapter "$TARGET_NUM"
HOST_ADDRESS="$(adapter_address "$HOST_INDEX")"
TARGET_ADDRESS="$(adapter_address "$TARGET_INDEX")"

if [ -z "$HOST_ADDRESS" ] || [ -z "$TARGET_ADDRESS" ]; then
    echo "could not read controller addresses" >&2
    exit 1
fi

assert_le_only "$HOST_NUM"
assert_le_only "$TARGET_NUM"
assert_virtual_bus "$HOST_INDEX"
assert_virtual_bus "$TARGET_INDEX"

# From here on the settings directories are ours and can be deleted by a later
# run even if this one dies without tearing anything down.
mark_adapter_settings "$HOST_ADDRESS"
mark_adapter_settings "$TARGET_ADDRESS"

"$PYTHON" "$ROOT_DIR/scripts/virtual_bluetooth_gatt.py" \
    --adapter "/org/bluez/$TARGET_INDEX" --battery 42 \
    >"$RUNTIME_DIR/log/gatt.log" 2>&1 &
GATT_PID=$!
echo "$GATT_PID" >"$RUNTIME_DIR/gatt.pid"

for _ in $(seq 1 100); do
    if grep -q '^ready' "$RUNTIME_DIR/log/gatt.log" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$GATT_PID" 2>/dev/null; then
        echo "the battery GATT helper exited:" >&2
        cat "$RUNTIME_DIR/log/gatt.log" >&2
        exit 1
    fi
    sleep 0.1
done

if ! grep -q '^ready' "$RUNTIME_DIR/log/gatt.log" 2>/dev/null; then
    echo "the battery GATT helper did not become ready" >&2
    cat "$RUNTIME_DIR/log/gatt.log" >&2
    exit 1
fi

cat >"$RUNTIME_DIR/env.json" <<EOF
{
  "host_index": "$HOST_INDEX",
  "host_address": "$HOST_ADDRESS",
  "host_path": "/org/bluez/$HOST_INDEX",
  "target_index": "$TARGET_INDEX",
  "target_address": "$TARGET_ADDRESS",
  "target_path": "/org/bluez/$TARGET_INDEX",
  "host_pid": $HOST_PID,
  "target_pid": $TARGET_PID,
  "gatt_pid": $GATT_PID,
  "battery": 42
}
EOF
printf '%s\n' "$HOST_ADDRESS" >"$RUNTIME_DIR/host-address"
printf '%s\n' "$TARGET_ADDRESS" >"$RUNTIME_DIR/target-address"

if [ -n "${SUDO_UID:-}" ]; then
    chown -R "$SUDO_UID:${SUDO_GID:-$SUDO_UID}" "$RUNTIME_DIR"
fi
chmod -R u+rwX,go+rX "$RUNTIME_DIR"

echo "Bluetooth test controllers ready:"
echo "  host   $HOST_INDEX $HOST_ADDRESS"
echo "  target $TARGET_INDEX $TARGET_ADDRESS"
