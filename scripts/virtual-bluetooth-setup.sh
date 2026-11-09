#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Create two virtual Bluetooth controllers for the E2E test.
#
#   host   - controller that runs the scan/pairing side
#   target - controller that advertises a battery GATT service
#
# Both controllers come from one btvirt process.  The emulator keeps its
# controllers in a process-local table and only forwards radio traffic between
# them there, so two separate btvirt processes would never discover each other.
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
PYTHON="${KAITHEM_PYTHON:-$ROOT_DIR/.venv/bin/python}"

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

# True while any emulator this harness may have started is still running.
controllers_running() {
    if pgrep -x btvirt >/dev/null 2>&1; then
        return 0
    fi
    local name
    for name in "$CONTROLLERS_NAME" $LEGACY_CONTROLLER_NAMES; do
        if pgrep -x "$name" >/dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

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
    # not match them.  The legacy names come from setups that predate the
    # single-process emulator.
    killall -q btvirt "$CONTROLLERS_NAME" $LEGACY_CONTROLLER_NAMES \
        2>/dev/null || true
    local attempt
    for attempt in $(seq 1 50); do
        if ! controllers_running; then
            break
        fi
        sleep 0.1
    done
    if controllers_running; then
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
        killall -q "$CONTROLLERS_NAME" $LEGACY_CONTROLLER_NAMES \
            2>/dev/null || true
        killall -q -w "$CONTROLLERS_NAME" $LEGACY_CONTROLLER_NAMES \
            2>/dev/null || true
        # Nothing may be left behind for a later run to trip over.
        wait_for_virtual_adapters_to_disappear
        remove_marked_adapter_settings
    fi
    return "$status"
}
trap cleanup_on_error EXIT

ln -s "$(command -v btvirt)" "$RUNTIME_DIR/bin/$CONTROLLERS_NAME"

start_controllers() {
    # One process, two controllers.  btvirt keeps its emulated controllers in a
    # process-local table, so controllers started by separate processes are on
    # isolated radios and would never discover each other.  -l2 selects two
    # local emulators; -L makes them LE-only.  The two options are not
    # interchangeable: plain "-L" creates no controller at all and btvirt exits
    # with "No emulator specified".
    nohup bash -c 'exec -a "$0" "$0" -l2 -L' \
        "$RUNTIME_DIR/bin/$CONTROLLERS_NAME" \
        >"$RUNTIME_DIR/log/$CONTROLLERS_NAME.log" 2>&1 &
    echo "$!"
}

new_adapters() {
    local existing="$1"
    comm -13 <(printf '%s\n' "$existing") <(list_adapters)
}

count_lines() {
    local text="$1"
    if [ -z "$text" ]; then
        echo 0
        return 0
    fi
    printf '%s\n' "$text" | grep -c .
}

# Print the names of the adapters created since the given listing, in the order
# the kernel registered them.
wait_for_adapters() {
    local existing="$1"
    local expected="$2"
    local pid="$3"
    local adapters attempt
    for attempt in $(seq 1 100); do
        adapters="$(new_adapters "$existing")"
        if [ "$(count_lines "$adapters")" -ge "$expected" ]; then
            printf '%s\n' "$adapters" | head -n "$expected"
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 0.1
    done
    echo "the virtual controllers did not appear:" >&2
    cat "$RUNTIME_DIR/log/$CONTROLLERS_NAME.log" >&2
    return 1
}

configure_adapter() {
    local name="$1"
    # Bringing the controller up makes the kernel wait for its pending
    # initialisation and then complete it, so the local features are read.  The
    # address btvirt assigned is the one the test uses; there is no supported
    # way to override it (see list_virtual_adapters).
    hciconfig "$name" up >/dev/null 2>&1 || true
}

# Teardown deletes the BlueZ settings of every adapter on the virtual bus, so
# make sure these controllers really are virtual before the test starts.
assert_virtual_bus() {
    local name="$1"
    local bus
    bus="$(adapter_bus "$name")"
    if [ "$bus" != "Virtual" ]; then
        echo "$name is not on the virtual HCI bus ($bus)" >&2
        return 1
    fi
}

BEFORE="$(list_adapters)"
CONTROLLERS_PID="$(start_controllers)"
ADAPTER_LIST="$(wait_for_adapters "$BEFORE" 2 "$CONTROLLERS_PID")" || exit 1
# `mapfile` keeps the kernel's registration order, which is also btvirt's
# creation order, so the host can never be swapped with the target.
mapfile -t ADAPTERS <<<"$ADAPTER_LIST"
HOST_INDEX="${ADAPTERS[0]}"
TARGET_INDEX="${ADAPTERS[1]}"

# Refuse to power anything up, or to delete settings for it later, before both
# controllers are known to be ours.
assert_virtual_bus "$HOST_INDEX"
assert_virtual_bus "$TARGET_INDEX"

configure_adapter "$HOST_INDEX"
configure_adapter "$TARGET_INDEX"
HOST_ADDRESS="$(adapter_address "$HOST_INDEX")"
TARGET_ADDRESS="$(adapter_address "$TARGET_INDEX")"

if [ -z "$HOST_ADDRESS" ] || [ -z "$TARGET_ADDRESS" ]; then
    echo "could not read controller addresses" >&2
    exit 1
fi

# A controller that keeps BR/EDR support would make BlueZ register the audio
# profiles, and the host would then see the other virtual controller as a
# Bluetooth speaker.  Never let the run get that far.
assert_le_only "$HOST_INDEX"
assert_le_only "$TARGET_INDEX"

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

echo "Writing $RUNTIME_DIR/env.json with the virtual controller addresses"
echo "and PIDs"
cat >"$RUNTIME_DIR/env.json" <<EOF
{
  "host_index": "$HOST_INDEX",
  "host_address": "$HOST_ADDRESS",
  "host_path": "/org/bluez/$HOST_INDEX",
  "target_index": "$TARGET_INDEX",
  "target_address": "$TARGET_ADDRESS",
  "target_path": "/org/bluez/$TARGET_INDEX",
  "controllers_pid": $CONTROLLERS_PID,
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
