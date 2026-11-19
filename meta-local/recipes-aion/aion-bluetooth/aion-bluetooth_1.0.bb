SUMMARY = "AION Bluetooth management terminal utilities"
LICENSE = "CLOSED"
SRC_URI = "file://aion-bluetooth.py file://aion-bluetooth-menu.py"
S = "${WORKDIR}"
# bluez5 and PulseAudio are already installed by the AION image recipe.
RDEPENDS:${PN} = "python3-core bluez5 pulseaudio-server"
do_install() {
    install -d "${D}${bindir}"
    install -m 0755 "${WORKDIR}/aion-bluetooth.py" "${D}${bindir}/aion-bluetooth"
    install -m 0755 "${WORKDIR}/aion-bluetooth-menu.py" "${D}${bindir}/aion-bluetooth-menu"
}
