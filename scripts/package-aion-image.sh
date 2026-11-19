#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY="$ROOT/build/tmp/deploy/images/raspberrypi3-64"
OUT="$ROOT/releases"
VERSION="${1:-$(date -u +%Y%m%d)}"
IMAGE="$DEPLOY/core-image-aion-mp3-raspberrypi3-64.rootfs.wic"
BZ2="$IMAGE.bz2"

mkdir -p "$OUT"

if [[ ! -f "$BZ2" ]]; then
  echo "ERROR: Full WIC image not found: $BZ2" >&2
  echo "Run: ./build.sh full" >&2
  exit 1
fi

NAME="AION-MP3-Box-v${VERSION}-raspberrypi3-64"
cp -f "$BZ2" "$OUT/${NAME}.wic.bz2"
sha256sum "$OUT/${NAME}.wic.bz2" > "$OUT/${NAME}.sha256"
cat > "$OUT/${NAME}-README.txt" <<TXT
AION AI MP3 Box image
Version: $VERSION
Host: Raspberry Pi 3 (64-bit)
Image: ${NAME}.wic.bz2

Write with:
  bzcat ${NAME}.wic.bz2 | sudo dd of=/dev/mmcblk0 bs=4M status=progress conv=fsync

Verify:
  sha256sum -c ${NAME}.sha256

WARNING: This erases P1, P2, and P3. Back up the music library first.
TXT

ls -lh "$OUT/${NAME}"*
