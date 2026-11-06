# shellcheck shell=bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Helpers shared by virtual-bluetooth-setup.sh and
# virtual-bluetooth-teardown.sh.  Source this file, do not run it.

# BlueZ keeps the per-adapter settings, including paired device keys, in a
# directory named after the adapter address.
ADAPTER_SETTINGS_DIR="${KAITHEM_BT_ADAPTER_SETTINGS_DIR:-/var/lib/bluetooth}"

MAC_ADDRESS_PATTERN='^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$'

# Written into the settings directory of every controller this harness
# creates.  It is what proves later on that the directory is ours: the
# controller itself may be long gone, and then its bus type can no longer be
# read.  The settings are deletable because they are marked, not because the
# address is known in advance.
VIRTUAL_ADAPTER_MARKER="kaithem-virtual-adapter"

list_adapters() {
    find /sys/class/bluetooth -maxdepth 1 -name 'hci*' \
        -printf '%f\n' 2>/dev/null | grep -v ':' | sort
}

adapter_address() {
    hciconfig "$1" 2>/dev/null | awk '/BD Address/ {print $3; exit}'
}

adapter_bus() {
    # The first hciconfig line carries both the type and the bus, for example
    # "hci1:  Type: Primary  Bus: Virtual".
    hciconfig "$1" 2>/dev/null | awk '/Bus:/ {print $NF; exit}'
}

# Print "hciX ADDRESS" for every adapter on the virtual HCI bus.  Only btvirt
# creates those, so the BlueZ settings behind them always belong to the test
# harness.
#
# The bus type is the only reliable marker.  The address cannot be overridden
# to a known value: MGMT_OP_SET_PUBLIC_ADDRESS requires hdev->set_bdaddr, which
# the vhci driver does not implement, so `btmgmt public-addr` always fails
# with "Not Supported" and the controller keeps the address btvirt generated.
list_virtual_adapters() {
    local name address
    for name in $(list_adapters); do
        if [ "$(adapter_bus "$name")" != "Virtual" ]; then
            continue
        fi
        address="$(adapter_address "$name")"
        if [ -n "$address" ]; then
            printf '%s %s\n' "$name" "$address"
        fi
    done
}

# Print the address of every adapter that is registered right now.
live_addresses() {
    local name
    for name in $(list_adapters); do
        adapter_address "$name"
    done
}

is_live_address() {
    local address
    for address in $(live_addresses); do
        if [ "$address" = "$1" ]; then
            return 0
        fi
    done
    return 1
}

wait_for_virtual_adapters_to_disappear() {
    local attempt
    for attempt in $(seq 1 100); do
        if [ -z "$(list_virtual_adapters)" ]; then
            return 0
        fi
        sleep 0.1
    done
    echo "warning: a virtual controller is still registered with BlueZ" >&2
    return 0
}

wait_for_adapters_to_settle() {
    local previous current
    previous="$(list_adapters)"
    local attempt
    for attempt in $(seq 1 50); do
        sleep 0.1
        current="$(list_adapters)"
        if [ "$current" = "$previous" ]; then
            return 0
        fi
        previous="$current"
    done
    echo "warning: the adapter list keeps changing" >&2
    return 0
}

# Delete the BlueZ settings of one adapter.  Only call this with addresses
# that came from list_virtual_adapters or a marker directory; the shape check
# is a second guard against a garbled or empty value.
remove_adapter_settings() {
    local address="$1"
    if [[ ! "$address" =~ $MAC_ADDRESS_PATTERN ]]; then
        echo "refusing to remove settings for '$address'" >&2
        return 1
    fi
    rm -rf "${ADAPTER_SETTINGS_DIR:?}/$address"
}

# Record that a settings directory belongs to this harness.
mark_adapter_settings() {
    local address="$1"
    if [[ ! "$address" =~ $MAC_ADDRESS_PATTERN ]]; then
        echo "refusing to mark settings for '$address'" >&2
        return 1
    fi
    local directory="${ADAPTER_SETTINGS_DIR:?}/$address"
    # 0700 matches what BlueZ uses for adapter directories.
    mkdir -p -m 0700 "$directory"
    : >"$directory/$VIRTUAL_ADAPTER_MARKER"
}

# Delete the settings of every marked adapter that is not registered right
# now.  A marked adapter that is still live belongs to a run in progress, so
# its settings are left alone.  Addresses are compared, not hciN names,
# because the kernel reuses index numbers.
remove_marked_adapter_settings() {
    local marker address
    for marker in "${ADAPTER_SETTINGS_DIR:?}"/*/"$VIRTUAL_ADAPTER_MARKER"; do
        if [ ! -e "$marker" ]; then
            continue
        fi
        address="$(basename "$(dirname "$marker")")"
        if is_live_address "$address"; then
            continue
        fi
        remove_adapter_settings "$address"
    done
}

# Delete the BlueZ settings of each "hciX ADDRESS" line in the given listing,
# but only for adapters that are no longer present.  A virtual adapter that is
# still registered was not created by the run being cleaned up, so its
# settings are left alone.
remove_settings_for_gone() {
    local listing="$1"
    local address
    while read -r _ address; do
        if [ -z "$address" ]; then
            continue
        fi
        if is_live_address "$address"; then
            continue
        fi
        remove_adapter_settings "$address"
    done <<<"$listing"
}
