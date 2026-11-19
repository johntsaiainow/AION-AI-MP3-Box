SUMMARY = "Offline Mandarin speech recognition for AION"
HOMEPAGE = "https://alphacephei.com/vosk/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

SRC_URI = " \
    https://github.com/alphacep/vosk-api/releases/download/v${PV}/vosk-linux-aarch64-${PV}.zip;name=engine \
    https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip;name=model \
"
SRC_URI[engine.sha256sum] = "45e95d37755deb07568e79497d7feba8c03aee5a9e071df29961aa023fd94541"
SRC_URI[model.sha256sum] = "3af8b0e7e0f835ae9d414ce5df580237a3cfb08d586c9fbbb0f7ff29ad5b14ba"
S = "${WORKDIR}/vosk-linux-aarch64-${PV}"
COMPATIBLE_HOST = "aarch64.*-linux"
INHIBIT_PACKAGE_STRIP = "1"
INHIBIT_PACKAGE_DEBUG_SPLIT = "1"
# The upstream ARM64 binary was built with the System V ELF hash.
INSANE_SKIP:${PN} += "already-stripped ldflags"
RDEPENDS:${PN} += "libatomic"

do_install() {
    install -Dm 0644 "${S}/libvosk.so" "${D}${libdir}/aion-vosk/libvosk.so"
    install -d "${D}${datadir}/aion-vosk/mandarin"
    cp -R --no-preserve=ownership "${WORKDIR}/vosk-model-small-cn-0.22/." "${D}${datadir}/aion-vosk/mandarin/"
}

FILES:${PN} = "${libdir}/aion-vosk ${datadir}/aion-vosk"
