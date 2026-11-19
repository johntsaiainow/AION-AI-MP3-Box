#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POKY="$ROOT/sources/poky"
OE="$ROOT/sources/meta-openembedded"
RPI="$ROOT/sources/meta-raspberrypi"
BUILD="$ROOT/build"

if [[ ! -f "$POKY/oe-init-build-env" ]]; then
    echo "ERROR: Yocto sources missing."
    echo "Run ./bootstrap.sh first."
    exit 1
fi

for layer in \
    "$POKY/meta" \
    "$POKY/meta-poky" \
    "$POKY/meta-yocto-bsp" \
    "$RPI" \
    "$OE/meta-oe" \
    "$OE/meta-python" \
    "$OE/meta-networking" \
    "$OE/meta-filesystems" \
    "$ROOT/meta-local"
do
    test -f "$layer/conf/layer.conf" || {
        echo "ERROR: Missing layer: $layer"
        exit 1
    }
done

mkdir -p "$BUILD/conf"

if [[ ! -f "$BUILD/conf/bblayers.conf" ]]; then
cat > "$BUILD/conf/bblayers.conf" <<LAYERS
POKY_BBLAYERS_CONF_VERSION = "2"
BBPATH = "\${TOPDIR}"
BBFILES ?= ""

BBLAYERS ?= " \\
    $POKY/meta \\
    $POKY/meta-poky \\
    $POKY/meta-yocto-bsp \\
    $RPI \\
    $OE/meta-oe \\
    $OE/meta-python \\
    $OE/meta-networking \\
    $OE/meta-filesystems \\
    $ROOT/meta-local \\
"
LAYERS
fi

if [[ ! -f "$BUILD/conf/local.conf" ]]; then
cat > "$BUILD/conf/local.conf" <<'CONFIG'
MACHINE = "raspberrypi3-64"
DISTRO = "poky"
INIT_MANAGER = "systemd"

PACKAGE_CLASSES = "package_rpm"

EXTRA_IMAGE_FEATURES = "debug-tweaks"

IMAGE_FSTYPES:append = " wic.bz2"

LICENSE_FLAGS_ACCEPTED:append = " synaptics-killswitch commercial"

BB_NUMBER_THREADS = "4"
CONFIG
fi

echo "=== AION STANDALONE BUILD ==="

cd "$ROOT"

# Yocto initialization defines bitbake and required environment variables.
# Yocto initialization expects some optional shell variables to be unset.
set +u
source "$POKY/oe-init-build-env" "$BUILD"
set -u

if ! grep -Fq 'meta-filesystems' "$BUILD/conf/bblayers.conf"; then
    bitbake-layers add-layer "$OE/meta-filesystems"
fi

MODE="${1:-rootfs}"

case "$MODE" in
    rootfs)
        echo "=== Building and deploying AION ext4 RootFS ==="

        ROOTFS_CONFIG="$(mktemp /tmp/aion-rootfs-XXXXXXXX.conf)"
        trap 'rm -f "$ROOTFS_CONFIG"' EXIT

        cat > "$ROOTFS_CONFIG" <<'ROOTFS'
IMAGE_FSTYPES = "ext4"
IMAGE_FSTYPES:remove = "wic wic.bz2 wic.bmap ext3 tar.bz2"
ROOTFS

        bitbake -R "$ROOTFS_CONFIG" core-image-aion-mp3
        ;;
    full)
        echo "=== Building AION full image ==="
        bitbake core-image-aion-mp3
        ;;
    *)
        echo "Usage: $0 [rootfs|full]" >&2
        exit 2
        ;;
esac
