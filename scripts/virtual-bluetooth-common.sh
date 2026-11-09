# shellcheck shell=bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Helpers shared by virtual-bluetooth-setup.sh and
# virtual-bluetooth-teardown.sh.  Source this file, do not run it.

# BlueZ keeps the per-adapter settings, including paired device keys, in a
# directory named after the adapter address.
ADAPTER_SETTINGS_DIR="${KAITHEM_BT_ADAPTER_SETTINGS_DIR:-/var/lib/bluetooth}"

# One btvirt process owns both controllers.  The emulator keeps its controllers
# in a process-local table, so controllers started by separate processes sit on
# isolated radios and can never discover each other.  The symlink name is the
# process name (comm), which is what killall matches.
CONTROLLERS_NAME="km-bt-peers"
# Names used by setups that predate the single-process emulator; still killed so
# an interrupted old run cannot leave controllers behind.
LEGACY_CONTROLLER_NAMES="km-bt-host km-bt-target"

MAC_ADDRESS_PATTERN='^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$'

# What the kernel reports before the controller has told it its own address.
UNSET_ADDRESS="00:00:00:00:00:00"

# True for a real controller address, false for a garbled or not yet read one.
# Both cases would otherwise name the wrong settings directory.
is_real_address() {
    local address="$1"
    if [[ ! "$address" =~ $MAC_ADDRESS_PATTERN ]]; then
        return 1
    fi
    [ "$address" != "$UNSET_ADDRESS" ]
}

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

# Bits of features byte 4 that decide whether a controller is LE-only.
FEATURE_BR_EDR_NOT_SUPPORTED=0x20
FEATURE_LE_SUPPORTED=0x40

# Byte 4 of the local supported features, as the kernel holds it.  hciconfig
# reads that through HCIGETDEVINFO, which is the same data BlueZ uses to decide
# whether to register the audio profiles.  The line looks like
# "Features: 0x00 0x00 0x00 0x00 0x60 0x00 0x00 0x00", so the fifth byte is
# field 6.
local_features_byte4() {
    # hciconfig fails while the controller is still being registered, so a
    # missing answer is reported as an empty string instead of aborting the
    # caller (the scripts run with -e and -o pipefail).
    hciconfig -a "$1" 2>/dev/null |
        awk '/^[[:space:]]*Features:/ {print $6; exit}' || true
}

features_are_known() {
    local byte="$1"
    if [[ ! "$byte" =~ ^0x[[:xdigit:]]{2}$ ]]; then
        return 1
    fi
    local value=$((byte))
    (( value != 0 ))
}

is_le_only_features() {
    local byte="$1"
    if [[ ! "$byte" =~ ^0x[[:xdigit:]]{2}$ ]]; then
        return 1
    fi
    local value=$((byte))
    if (( (value & FEATURE_BR_EDR_NOT_SUPPORTED) == 0 )); then
        return 1
    fi
    if (( (value & FEATURE_LE_SUPPORTED) == 0 )); then
        return 1
    fi
}

# Abort unless the controller really is BR/EDR-less.  A controller that
# supports BR/EDR makes BlueZ register the audio profiles, and other machines
# then discover the virtual controller as a Bluetooth speaker with A2DP UUIDs.
# That is the system state we must never create.
#
# The check cannot be made the moment the controller appears: the kernel
# assumes BR/EDR support until it has read the local features during its
# asynchronous initialisation, and reports zeros before that.  Only a known,
# non-zero feature set may decide the outcome, so an unreadable one is waited
# for instead of being treated as a failure.
assert_le_only() {
    local name="$1"
    local features=""
    local attempt
    for attempt in $(seq 1 50); do
        features="$(local_features_byte4 "$name")"
        if is_le_only_features "$features"; then
            return 0
        fi
        if features_are_known "$features"; then
            break
        fi
        sleep 0.1
    done
    echo "$name is not LE-only (features: ${features:-unreadable}):" >&2
    hciconfig -a "$name" >&2 || true
    return 1
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
# that came from list_virtual_adapters or a marker directory; the address
# check is a second guard against a garbled or empty value.
remove_adapter_settings() {
    local address="$1"
    if ! is_real_address "$address"; then
        echo "refusing to remove settings for '$address'" >&2
        return 1
    fi
    rm -rf "${ADAPTER_SETTINGS_DIR:?}/$address"
}

# Record that a settings directory belongs to this harness.
mark_adapter_settings() {
    local address="$1"
    if ! is_real_address "$address"; then
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
