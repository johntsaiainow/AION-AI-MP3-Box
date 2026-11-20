SUMMARY = "AION Bluetooth management terminal utilities"
LICENSE = "CLOSED"
SRC_URI = "file://aion-bluetooth.py file://aion-bluetooth-menu.py file://aion-bluetooth-sms.py"
S = "${WORKDIR}"
RDEPENDS:${PN} = "python3-core python3-dbus-next dbus bluez5 bluez5-obex pulseaudio-server"
do_install() {
    install -d "${D}${bindir}"
    install -m 0755 "${WORKDIR}/aion-bluetooth.py" "${D}${bindir}/aion-bluetooth"
    install -m 0755 "${WORKDIR}/aion-bluetooth-menu.py" "${D}${bindir}/aion-bluetooth-menu"
    install -m 0755 "${WORKDIR}/aion-bluetooth-sms.py" "${D}${bindir}/aion-bluetooth-sms"
    sed -i "s|@LIBEXECDIR@|${libexecdir}|g" "${D}${bindir}/aion-bluetooth-sms"
}
