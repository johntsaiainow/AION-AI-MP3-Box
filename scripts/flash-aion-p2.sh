#!/usr/bin/env bash
set -Eeuo pipefail

DEVICE=/dev/mmcblk0
P1=/dev/mmcblk0p1
P2=/dev/mmcblk0p2
P3=/dev/mmcblk0p3

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="$ROOT/build/tmp/deploy/images/raspberrypi3-64/core-image-aion-mp3-raspberrypi3-64.rootfs.ext4"

EXPECTED_P2_SIZE=790626304
IMAGE_SIZE=0
EXPECTED_P3_UUID=da792082-ddb1-4896-b6fd-0a61a0cc7266

echo "=== AION v0.4.0 SAFE P2 FLASH ==="

# Validate device identity
[[ -b "$DEVICE" && -b "$P1" && -b "$P2" && -b "$P3" ]]

# Refuse to flash the disk containing the host root filesystem.
HOST_ROOT_SOURCE="$(findmnt -nro SOURCE /)"
HOST_ROOT_DEVICE="$(readlink -f "${HOST_ROOT_SOURCE%%[*}")"
TARGET_DEVICE="$(readlink -f "$DEVICE")"

if [[ ! -b "$HOST_ROOT_DEVICE" ]]; then
    echo "ERROR: Cannot identify host root block device"
    exit 1
fi

# Resolve the physical disk ancestry of the host root device.
# This also handles root filesystems on LVM or device-mapper.
if lsblk -snrpo NAME "$HOST_ROOT_DEVICE" |
    grep -Fx "$TARGET_DEVICE" >/dev/null; then
    echo "ERROR: Target contains the host root filesystem"
    exit 1
fi

echo "PASS: Target does not contain host root filesystem"

[[ "$(lsblk -bdno SIZE "$P2" | tr -d '[:space:]')" == "$EXPECTED_P2_SIZE" ]]
[[ "$(sudo blkid -s UUID -o value "$P3")" == "$EXPECTED_P3_UUID" ]]
[[ "$(sudo blkid -s LABEL -o value "$P3")" == "AION-MUSIC" ]]

# Verify partition table identity and boundaries
sudo sfdisk --dump "$DEVICE" |
    grep -q '^label-id: 0x076c4a2a$'

sudo sfdisk --dump "$DEVICE" |
    grep -Eq '^/dev/mmcblk0p2 : start= *278528, size= *1544192, type=83$'

# Verify image
[[ -f "$IMAGE" ]]
IMAGE_SIZE="$(stat -Lc %s "$IMAGE")"
[[ "$IMAGE_SIZE" -gt 0 ]]
[[ "$IMAGE_SIZE" -le "$EXPECTED_P2_SIZE" ]] || {
    echo "ERROR: RootFS image exceeds P2 capacity"
    exit 1
}

# Do not write to mounted partitions
for PART in "$P1" "$P2" "$P3"; do
    if findmnt -rn -S "$PART" >/dev/null; then
        echo "ERROR: $PART is mounted"
        exit 1
    fi
done

echo
echo "=== VERIFY IMAGE FILESYSTEM ==="

set +e
e2fsck -fn "$IMAGE"
FSCK_RC=$?
set -e

if (( FSCK_RC != 0 )); then
    echo "ERROR: Image filesystem check failed (code $FSCK_RC)"
    exit 1
fi

echo "PASS: Image filesystem clean"

echo
echo "=== TARGET ==="
lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS "$DEVICE"

echo
echo "WARNING: The existing P2 RootFS will be replaced."
echo "P1 Boot and P3 Music will not be written."

read -r -p 'Type FLASH-AION-P2 to continue: ' CONFIRM
[[ "$CONFIRM" == "FLASH-AION-P2" ]] || exit 1

umask 077
mkdir -p "$ROOT/backups"
BACKUP="$(mktemp -d "$ROOT/backups/p2-before-flash.XXXXXXXX")"
STAGING="$(mktemp -d)"
OLD_MOUNT="$STAGING/old"
NEW_MOUNT="$STAGING/new"
STAGED_IMAGE="$STAGING/rootfs.ext4"
mkdir "$OLD_MOUNT" "$NEW_MOUNT"
cleanup() {
    if mountpoint -q "$NEW_MOUNT"; then sudo umount "$NEW_MOUNT" || return; fi
    if mountpoint -q "$OLD_MOUNT"; then sudo umount "$OLD_MOUNT" || return; fi
    rm -f -- "$STAGED_IMAGE" "$STAGING/previous.ext4"
    rmdir -- "$OLD_MOUNT" "$NEW_MOUNT" "$STAGING"
}
trap cleanup EXIT

echo "Backing up current P2 to $BACKUP"
sudo sfdisk --dump "$DEVICE" > "$BACKUP/partition-table.sfdisk"
sudo install -m 0600 /dev/null "$BACKUP/rootfs.ext4"
sudo dd if="$P2" of="$BACKUP/rootfs.ext4" bs=4M iflag=fullblock conv=fsync status=none
sudo cmp -s "$P2" "$BACKUP/rootfs.ext4"
# Mount with normal recovery so a pending ext4 journal is replayed on a
# disposable copy rather than skipped or applied to the verified backup.
sudo cp --reflink=auto --sparse=always "$BACKUP/rootfs.ext4" "$STAGING/previous.ext4"
cp --reflink=auto --sparse=always "$IMAGE" "$STAGED_IMAGE"
sudo mount -o loop,rw,nodev,nosuid,noexec "$STAGING/previous.ext4" "$OLD_MOUNT"
sudo mount -o loop,rw,nodev,nosuid,noexec "$STAGED_IMAGE" "$NEW_MOUNT"

sudo bash -euo pipefail -s -- "$OLD_MOUNT" "$NEW_MOUNT" <<'PRESERVE_SETTINGS'
previous=$1
next=$2
paths=(var/lib/aion-audio etc/aiy-box-rebirth etc/NetworkManager/system-connections
       var/lib/NetworkManager var/lib/bluetooth etc/machine-id var/lib/systemd/timesync root/.ssh)
shopt -s nullglob
for key in "$previous"/etc/ssh/ssh_host_*; do
    paths+=("${key#"$previous/"}")
done
for path in "${paths[@]}"; do
    [[ -e "$previous/$path" || -L "$previous/$path" ]] || continue
    (cd "$previous" && cp -a --parents -- "$path" "$next")
    while IFS= read -r -d '' file; do
        target="$next/${file#"$previous/"}"
        cmp -s "$file" "$target"
        [[ $(stat -c '%u:%g:%a' "$file") == "$(stat -c '%u:%g:%a' "$target")" ]]
    done < <(find "$previous/$path" -type f -print0)
done
for path in var/lib/aion-audio/config.json etc/aiy-box-rebirth/tomtom.key; do
    if [[ -f "$previous/$path" ]]; then
        cmp -s "$previous/$path" "$next/$path"
        printf 'Verified saved settings file: %s\n' "$path"
    fi
done
PRESERVE_SETTINGS

sudo umount "$NEW_MOUNT"
sudo umount "$OLD_MOUNT"
sudo tune2fs -U "$(sudo blkid -s UUID -o value "$P2")" "$STAGED_IMAGE" >/dev/null
e2fsck -fn "$STAGED_IMAGE"
for PART in "$P1" "$P2" "$P3"; do
    if findmnt -rn -S "$PART" >/dev/null; then
        echo "ERROR: $PART became mounted during staging"
        exit 1
    fi
done
sudo cmp -s "$P2" "$BACKUP/rootfs.ext4"

echo
echo "=== FLASH P2 ONLY ==="
sudo dd if="$STAGED_IMAGE" of="$P2" \
    bs=4M status=progress conv=fsync
sudo cmp -s -n "$IMAGE_SIZE" "$STAGED_IMAGE" "$P2"

echo
echo "=== CHECK NEW ROOTFS ==="
sudo e2fsck -fy "$P2"

echo
echo "=== EXPAND ROOTFS ==="
sudo resize2fs "$P2"

echo
echo "=== FINAL CHECK ==="
sudo e2fsck -fy "$P2"

echo
echo "=== VERIFY MUSIC PARTITION ==="
sudo blkid "$P3"

echo
echo "AION v0.4.0 P2 FLASH COMPLETE"
