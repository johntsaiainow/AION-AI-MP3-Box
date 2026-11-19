#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-$(date -u +%Y%m%d)}"
TAG="v${VERSION}"
TITLE="AION MP3 Box ${TAG}"
ASSETS=("$ROOT/releases/AION-MP3-Box-v${VERSION}-raspberrypi3-64.wic.bz2"
        "$ROOT/releases/AION-MP3-Box-v${VERSION}-raspberrypi3-64.sha256"
        "$ROOT/releases/AION-MP3-Box-v${VERSION}-raspberrypi3-64-README.txt")

for asset in "${ASSETS[@]}"; do
  test -f "$asset" || {
    echo "ERROR: Missing release asset: $asset" >&2
    echo "Run: ./scripts/package-aion-image.sh $VERSION" >&2
    exit 1
  }
done

NOTES="$ROOT/releases/${TAG}-notes.md"
cat > "$NOTES" <<EOF
# AION MP3 Box $TAG

Full Raspberry Pi 3 64-bit SD card image.

## Downloads

- AION-MP3-Box-v${VERSION}-raspberrypi3-64.wic.bz2
- SHA256 checksum and flashing instructions are included.

## What is included

- Pure music player console
- Local MP3/FLAC library
- Playlists, internet radio, Bluetooth, Wi-Fi and storage management
- No AI, Vosk, Piper or voice input features

## Flash warning

The WIC image erases P1, P2 and P3. Back up /mnt/music before flashing.
EOF

REPO="johntsaiainow/AION-AI-MP3-Box"
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  gh release upload "$TAG" "${ASSETS[@]}" --repo "$REPO" --clobber
else
  gh release create "$TAG" "${ASSETS[@]}" --repo "$REPO" --title "$TITLE" --notes-file "$NOTES"
fi
