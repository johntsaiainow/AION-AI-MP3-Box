SUMMARY = "AION AI MP3 Box Headless Player Service"
DESCRIPTION = "Installs the AION player in RootFS; music storage is user-configurable"
LICENSE = "CLOSED"

inherit systemd

SRC_URI = "file://aion-player.service file://player.py file://aion-player-console.sh file://aion-setup.py file://aion-session.py"

S = "${WORKDIR}"

RDEPENDS:${PN} = " \
    python3-core \
    python3-modules \
    python3-mutagen \
    python3-gpiod \
    python3-pillow \
    python3-zoneinfo \
    tzdata-core tzdata-misc \
    tzdata-africa tzdata-americas tzdata-antarctica tzdata-arctic \
    tzdata-asia tzdata-atlantic tzdata-australia tzdata-europe tzdata-pacific \
    mpv \
    chafa \
    openssl-bin \
    aion-bluetooth \
"

SYSTEMD_SERVICE:${PN} = "aion-player.service"
SYSTEMD_AUTO_ENABLE = "enable"

do_install() {
    install -d "${D}${systemd_system_unitdir}"
    install -m 0644 \
        "${WORKDIR}/aion-player.service" \
        "${D}${systemd_system_unitdir}/aion-player.service"

    install -d "${D}${bindir}"
    install -m 0755 "${WORKDIR}/aion-player-console.sh" "${D}${bindir}/aion-player-console"
    install -m 0755 \
        "${WORKDIR}/player.py" \
        "${D}${bindir}/aion-player"
    install -m 0755 "${WORKDIR}/aion-setup.py" "${D}${bindir}/aion-setup"
    install -m 0755 "${WORKDIR}/aion-session.py" "${D}${bindir}/aion-session"
}

FILES:${PN} += "${systemd_system_unitdir}/aion-player.service ${bindir}/aion-player"

FILES:${PN} += "${bindir}/aion-player-console"
FILES:${PN} += "${bindir}/aion-setup"
FILES:${PN} += "${bindir}/aion-session"

SRC_URI:append = " file://aion_ui.py file://aion_translations.py file://aion_local_info.py file://aion_media_info.py file://aion_voice_button.py"
SRC_URI:append = " file://aion_traffic_map.py"
SRC_URI:append = " file://40-aion-journal.conf"
SRC_URI:append = " file://aion-wifi-menu"

SRC_URI:append = " file://aion-storage-menu"

do_install:append() {
    install -d "${D}${sysconfdir}/systemd/journald.conf.d"
    install -m 0644 "${WORKDIR}/40-aion-journal.conf" "${D}${sysconfdir}/systemd/journald.conf.d/"
    install -m 0644 "${WORKDIR}/aion_ui.py" "${D}${bindir}/aion_ui.py"
    install -m 0644 "${WORKDIR}/aion_local_info.py" "${D}${bindir}/aion_local_info.py"
    install -m 0644 "${WORKDIR}/aion_media_info.py" "${D}${bindir}/aion_media_info.py"
    install -m 0644 "${WORKDIR}/aion_voice_button.py" "${D}${bindir}/aion_voice_button.py"
    install -m 0644 "${WORKDIR}/aion_traffic_map.py" "${D}${bindir}/aion_traffic_map.py"
    install -m 0644 "${WORKDIR}/aion_translations.py" "${D}${bindir}/aion_translations.py"
    install -m 0755 "${WORKDIR}/aion-wifi-menu" "${D}${bindir}/aion-wifi-menu"
}

FILES:${PN}:append = " ${bindir}/aion-wifi-menu ${bindir}/aion-storage-menu ${sysconfdir}/systemd/journald.conf.d/40-aion-journal.conf"

RDEPENDS:${PN}:append = " networkmanager-nmtui util-linux-lsblk util-linux-blkid util-linux-findmnt util-linux-mountpoint util-linux-mount util-linux-umount"

RDEPENDS:${PN}:append = " python3-modules util-linux-sfdisk e2fsprogs-mke2fs e2fsprogs-e2fsck parted"
