#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCES="$ROOT/sources"

source "$ROOT/config/sources.lock"

mkdir -p "$SOURCES"

checkout_layer() {
    local name="$1"
    local url="$2"
    local revision="$3"
    local directory="$SOURCES/$name"

    echo "=== $name ==="

    if [[ ! -d "$directory/.git" ]]; then
        git clone "$url" "$directory"
    fi

    git -C "$directory" fetch origin "$revision"
    git -C "$directory" checkout --detach "$revision"

    test "$(git -C "$directory" rev-parse HEAD)" = "$revision"
}

checkout_layer poky "$POKY_URL" "$POKY_REV"
checkout_layer meta-raspberrypi "$RPI_URL" "$RPI_REV"
checkout_layer meta-openembedded "$OE_URL" "$OE_REV"

echo
echo "=== AION YOCTO SOURCES READY ==="
