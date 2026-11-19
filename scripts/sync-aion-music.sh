#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE="${AION_MUSIC_SOURCE:-$HOME/Music}"
DEVICE="${AION_MUSIC_DEVICE:-/dev/mmcblk0p3}"
MODE="${1:---dry-run}"

if [[ "$MODE" != "--dry-run" && "$MODE" != "--apply" ]]; then
    echo "Usage: $0 [--dry-run|--apply]"
    exit 2
fi

echo "=== AION MUSIC SYNC ==="
echo "Mode:   $MODE"
echo "Source: $SOURCE"
echo "Device: $DEVICE"

[[ -d "$SOURCE" ]] || {
    echo "ERROR: Music source not found"
    exit 1
}

[[ -b "$DEVICE" ]] || {
    echo "ERROR: Device is not a block device"
    exit 1
}

[[ "$(lsblk -dn -o TYPE "$DEVICE" | xargs)" == "part" ]] || {
    echo "ERROR: Target must be a partition"
    exit 1
}

LABEL="$(lsblk -dn -o LABEL "$DEVICE" | xargs)"
FSTYPE="$(lsblk -dn -o FSTYPE "$DEVICE" | xargs)"

[[ "$LABEL" == "AION-MUSIC" ]] || {
    echo "ERROR: Expected AION-MUSIC label; found '$LABEL'"
    exit 1
}

[[ "$FSTYPE" == "ext4" ]] || {
    echo "ERROR: Expected ext4; found '$FSTYPE'"
    exit 1
}

if findmnt -rn -S "$DEVICE" >/dev/null; then
    echo "ERROR: Target partition is already mounted"
    exit 1
fi

MOUNT="$(mktemp -d /tmp/aion-music-sync.XXXXXX)"

cleanup() {
    if mountpoint -q "$MOUNT"; then
        sudo umount "$MOUNT"
    fi
    rmdir "$MOUNT" 2>/dev/null || true
}

trap cleanup EXIT

sudo mount "$DEVICE" "$MOUNT"

RSYNC_OPTIONS=(
    -a
    --no-owner
    --no-group
    --exclude=/player.py
    --exclude=/.git/
    --info=stats2
)

if [[ "$MODE" == "--dry-run" ]]; then
    RSYNC_OPTIONS+=(--dry-run --itemize-changes)
fi

echo
echo "=== RSYNC ==="

sudo rsync "${RSYNC_OPTIONS[@]}" \
    "$SOURCE/" "$MOUNT/"

if [[ "$MODE" == "--apply" ]]; then
    sync
    echo
    echo "PASS: Music synchronized"
else
    echo
    echo "PASS: Dry-run completed; no music files copied"
fi

echo "=== AION MUSIC SYNC COMPLETE ==="
