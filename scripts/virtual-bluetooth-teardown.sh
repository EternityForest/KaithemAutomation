#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Tear down the virtual Bluetooth controllers created by
# virtual-bluetooth-setup.sh.  Run as root (the Makefile target uses sudo).
#
# Order matters.  BlueZ must forget the paired devices while the virtual
# adapters still exist, and the adapter settings are deleted only once the
# adapters are gone, so bluetoothd cannot write them back.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${KAITHEM_BT_RUNTIME_DIR:-/tmp/kaithem-bt}"
HOST_NAME="km-bt-host"
TARGET_NAME="km-bt-target"

# shellcheck source=scripts/virtual-bluetooth-common.sh
. "$ROOT_DIR/scripts/virtual-bluetooth-common.sh"

if [ "$(id -u)" -ne 0 ]; then
    echo "virtual-bluetooth-teardown.sh must run as root (use sudo)" >&2
    exit 1
fi

read_address() {
    if [ -f "$RUNTIME_DIR/$1" ]; then
        tr -d '[:space:]' <"$RUNTIME_DIR/$1"
    fi
}

HOST_ADDRESS="$(read_address host-address)"
TARGET_ADDRESS="$(read_address target-address)"

remove_paired_devices() {
    if [ -z "$HOST_ADDRESS" ] || [ -z "$TARGET_ADDRESS" ]; then
        return 0
    fi
    printf '%s\n' \
        "select $HOST_ADDRESS" "remove $TARGET_ADDRESS" \
        "select $TARGET_ADDRESS" "remove $HOST_ADDRESS" |
        timeout 20 bluetoothctl >/dev/null 2>&1 || true
}

# Collect the adapters before killing anything.  Afterwards the bus type can
# no longer be read, and the bus type is what proves that the BlueZ settings
# directories belong to the test harness.
VIRTUAL_ADAPTERS="$(list_virtual_adapters)"

remove_paired_devices

if [ -f "$RUNTIME_DIR/gatt.pid" ]; then
    kill "$(cat "$RUNTIME_DIR/gatt.pid")" 2>/dev/null || true
fi

# The symlink names are the process names (comm), so killall finds them.
killall -q "$HOST_NAME" "$TARGET_NAME" 2>/dev/null || true
# Leftover controllers from an earlier run are dual-mode by default, so they
# pollute the system with audio profiles.  Nothing else runs btvirt.
killall -q btvirt 2>/dev/null || true
killall -q -w "$HOST_NAME" "$TARGET_NAME" 2>/dev/null || true

wait_for_virtual_adapters_to_disappear
wait_for_adapters_to_settle
# The live-bus listing covers adapters without a marker, such as leftovers
# from runs that predate it.  The marker sweep covers adapters that were
# already gone when this script started.
remove_settings_for_gone "$VIRTUAL_ADAPTERS"
remove_marked_adapter_settings

rm -rf "$RUNTIME_DIR"
