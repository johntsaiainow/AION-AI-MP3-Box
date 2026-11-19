SUMMARY = "AION Raspberry Pi 3 ARM64 Embedded Linux"
DESCRIPTION = "CJK console with NetworkManager, Wi-Fi and SSH"

require core-image-base-cjk.bb

IMAGE_INSTALL:append = " \
    coreutils \
    glibc-utils \
    openssh \
    networkmanager \
    networkmanager-nmtui \
    networkmanager-nmcli \
    networkmanager-wifi \
    avahi-daemon \
    avahi-utils \
    linux-firmware-rpidistro-bcm43430 \
"

IMAGE_FEATURES:append = " ssh-server-openssh"

IMAGE_ROOTFS_EXTRA_SPACE = "262144"


# AION uses NetworkManager exclusively.
aion_mask_networkd() {
    install -d ${IMAGE_ROOTFS}${sysconfdir}/systemd/system

    for unit in \
        systemd-networkd.service \
        systemd-networkd.socket \
        systemd-networkd-wait-online.service
    do
        ln -sfn /dev/null \
            ${IMAGE_ROOTFS}${sysconfdir}/systemd/system/$unit
    done
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_mask_networkd; "

# ------------------------------------------------------------
# AION CJK Console
#
# tty1 : kmscon (UTF-8 / CJK)
# tty2 : standard Linux getty (recovery)
#
# Keep getty@tty1 unmasked so kmscon's OnFailure fallback works.
# ------------------------------------------------------------

aion_configure_console() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}${sysconfdir}/systemd/system"
    GETTY_WANTS="$SYSTEMD_DIR/getty.target.wants"

    install -d "$GETTY_WANTS"
    install -d "${IMAGE_ROOTFS}${sysconfdir}"

    # Default UTF-8 locale
    printf 'LANG=C.UTF-8\n' \
        > "${IMAGE_ROOTFS}${sysconfdir}/locale.conf"

    # Remove default tty1 getty boot activation.
    # Do NOT mask getty@tty1.service.
    rm -f "$GETTY_WANTS/getty@tty1.service"
    rm -f "$SYSTEMD_DIR/getty@tty1.service"

    # tty1: kmscon CJK console
    ln -sfn \
        /usr/lib/systemd/system/kmsconvt@.service \
        "$GETTY_WANTS/kmsconvt@tty1.service"

    # tty2: standard Linux getty fallback
    rm -f "$GETTY_WANTS/kmsconvt@tty2.service"

    ln -sfn \
        /usr/lib/systemd/system/getty@.service \
        "$GETTY_WANTS/getty@tty2.service"
}


# Apply the final console configuration after systemd presets and before
# any filesystem image is generated.
aion_finalize_console() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}${sysconfdir}/systemd/system"
    GETTY_WANTS="$SYSTEMD_DIR/getty.target.wants"

    install -d "$GETTY_WANTS"

    # tty1 must belong exclusively to kmscon.
    rm -f "$GETTY_WANTS/getty@tty1.service"

    # Keep getty@tty1 unmasked for kmscon OnFailure fallback.
    if [ -L "$SYSTEMD_DIR/getty@tty1.service" ]; then
        if [ "$(readlink "$SYSTEMD_DIR/getty@tty1.service")" = "/dev/null" ]; then
            rm -f "$SYSTEMD_DIR/getty@tty1.service"
        fi
    fi

    # tty1: CJK console
    ln -sfn \
        /usr/lib/systemd/system/kmsconvt@.service \
        "$GETTY_WANTS/kmsconvt@tty1.service"

    # tty2: traditional Linux getty
    rm -f "$GETTY_WANTS/kmsconvt@tty2.service"

    ln -sfn \
        /usr/lib/systemd/system/getty@.service \
        "$GETTY_WANTS/getty@tty2.service"

    printf 'LANG=C.UTF-8\n' \
        > "${IMAGE_ROOTFS}${sysconfdir}/locale.conf"

    # Fail the build if the tty1 conflict remains.
    if [ -e "$GETTY_WANTS/getty@tty1.service" ] ||
       [ -L "$GETTY_WANTS/getty@tty1.service" ]; then
        bbfatal "AION: tty1 getty conflict remains"
    fi

    bbnote "AION: tty1 kmscon / tty2 getty configuration verified"
}

do_image[postfuncs] += "aion_finalize_console"
