#!/usr/bin/env bash
set -Eeuo pipefail

DEVICE=/dev/mmcblk0
P1=/dev/mmcblk0p1
P2=/dev/mmcblk0p2
P3=/dev/mmcblk0p3

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="$ROOT/build/tmp/deploy/images/raspberrypi3-64/core-image-aion-mp3-raspberrypi3-64.rootfs.ext4"
BACKUP="$ROOT/backups/20261117-144643"

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

# Verify backups
(
    cd "$BACKUP"
    sha256sum -c SHA256SUMS
)

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

echo
echo "=== FLASH P2 ONLY ==="
sudo dd if="$IMAGE" of="$P2" \
    bs=4M status=progress conv=fsync

sync

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
