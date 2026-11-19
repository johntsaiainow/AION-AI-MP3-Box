SUMMARY = "Rclone for network and cloud music libraries"
HOMEPAGE = "https://rclone.org/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://rclone-${PV}-COPYING;md5=bed161b82a1ecab65ff7ba3c3b960439"

SRC_URI = " \
    https://downloads.rclone.org/v${PV}/rclone-v${PV}-linux-arm64.zip;name=release \
    https://raw.githubusercontent.com/rclone/rclone/v${PV}/COPYING;downloadfilename=rclone-${PV}-COPYING;subdir=rclone-v${PV}-linux-arm64;name=license \
"
SRC_URI[release.sha256sum] = "ee169016675e23a69d77240565133ff7dbc9b33d16fa8f7053d4af39f1eaeb78"
SRC_URI[license.sha256sum] = "8cd2e9e750b90a04b7d82dbbca3930c696ae0309d7c10464f90a44f45754cd04"
S = "${WORKDIR}/rclone-v${PV}-linux-arm64"

COMPATIBLE_HOST = "aarch64.*-linux"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
INSANE_SKIP:${PN} += "already-stripped"
RDEPENDS:${PN} = "fuse3-utils ca-certificates"

do_install() {
    install -Dm 0755 "${S}/rclone" "${D}${bindir}/rclone"
}
