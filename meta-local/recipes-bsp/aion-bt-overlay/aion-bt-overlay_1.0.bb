SUMMARY = "AION Raspberry Pi 3 Bluetooth UART 460800 Overlay"
DESCRIPTION = "Bluetooth UART speed fix for BCM43430A1"
LICENSE = "CLOSED"

SRC_URI = "file://aion-bt-460800.dts"

S = "${WORKDIR}"

inherit deploy

DEPENDS = "dtc-native"

do_compile() {
    ${STAGING_BINDIR_NATIVE}/dtc \
        -@ -I dts -O dtb \
        -o ${B}/aion-bt-460800.dtbo \
        ${S}/aion-bt-460800.dts
}

do_deploy() {
    install -d ${DEPLOYDIR}

    install -m 0644 \
        ${B}/aion-bt-460800.dtbo \
        ${DEPLOYDIR}/aion-bt-460800.dtbo
}

addtask deploy after do_compile before do_build
