SUMMARY = "AION headless PulseAudio service"
DESCRIPTION = "Dedicated audio user and PulseAudio service for AION"
LICENSE = "CLOSED"

inherit useradd systemd

SRC_URI = " \
    file://aion-pulseaudio.service \
    file://aion-ofono.conf \
    file://aion-bt-reconnect.service \
    file://aion-bt-reconnect.sh \
"

S = "${WORKDIR}"

USERADD_PACKAGES = "${PN}"

USERADD_PARAM:${PN} = "\
    --system \
    --home-dir /var/lib/aion-audio \
    --shell /sbin/nologin \
    --groups audio \
    aion-audio \
"

RDEPENDS:${PN} = "pulseaudio-server ofono"

SYSTEMD_SERVICE:${PN} = "aion-pulseaudio.service aion-bt-reconnect.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

do_install() {
    install -d ${D}${systemd_system_unitdir}
    install -d ${D}${bindir}
    install -d ${D}${datadir}/dbus-1/system.d
    install -m 0644 ${WORKDIR}/aion-ofono.conf ${D}${datadir}/dbus-1/system.d/

    install -m 0755 \
        ${WORKDIR}/aion-bt-reconnect.sh \
        ${D}${bindir}/aion-bt-reconnect.sh

    install -m 0644 \
        ${WORKDIR}/aion-bt-reconnect.service \
        ${D}${systemd_system_unitdir}/
    install -m 0644 \
        ${WORKDIR}/aion-pulseaudio.service \
        ${D}${systemd_system_unitdir}/
}

FILES:${PN} = "\
    ${systemd_system_unitdir}/aion-pulseaudio.service \
    ${systemd_system_unitdir}/aion-bt-reconnect.service \
    ${bindir}/aion-bt-reconnect.sh \
    ${datadir}/dbus-1/system.d/aion-ofono.conf \
"
