#!/usr/bin/env bash
set -Eeuo pipefail

DEVICE=/dev/mmcblk0
P1=/dev/mmcblk0p1
P2=/dev/mmcblk0p2
P3=/dev/mmcblk0p3

BACKUP="$HOME/Projects/AION-AI-MP3-Box/backups/$(date +%Y%m%d-%H%M%S)"

trap 'echo "ERROR: Backup failed at line $LINENO" >&2' ERR

echo "=== AION SD CARD BACKUP ==="

test -b "$DEVICE"
test -b "$P1"
test -b "$P2"
test -b "$P3"

SIZE=$(lsblk -bdno SIZE "$P2" | tr -d '[:space:]')
LABEL=$(sudo blkid -s LABEL -o value "$P3")
UUID=$(sudo blkid -s UUID -o value "$P3")

echo "P2 size: $SIZE"
echo "P3 label: $LABEL"
echo "P3 UUID: $UUID"

[[ "$SIZE" == "790626304" ]] || {
    echo "ERROR: Unexpected P2 size"
    exit 1
}

[[ "$LABEL" == "AION-MUSIC" ]] || {
    echo "ERROR: Unexpected P3 label"
    exit 1
}

[[ "$UUID" == "da792082-ddb1-4896-b6fd-0a61a0cc7266" ]] || {
    echo "ERROR: Unexpected P3 UUID"
    exit 1
}

mkdir -p "$BACKUP"

echo
echo "=== BACKUP PARTITION TABLE ==="
sudo sfdisk --dump "$DEVICE" > "$BACKUP/partition-table.sfdisk"

echo
echo "=== BACKUP BOOT PARTITION ==="
sudo dd if="$P1" of="$BACKUP/aion-boot-p1.img" \
    bs=4M status=progress conv=fsync

echo
echo "=== BACKUP ROOTFS PARTITION ==="
sudo dd if="$P2" of="$BACKUP/aion-rootfs-p2-before-v030.img" \
    bs=4M status=progress conv=fsync

echo
echo "=== VERIFY BACKUPS ==="
(
    cd "$BACKUP"
    sha256sum aion-boot-p1.img aion-rootfs-p2-before-v030.img > SHA256SUMS
    sha256sum -c SHA256SUMS
)

echo
echo "BACKUP COMPLETE: $BACKUP"
