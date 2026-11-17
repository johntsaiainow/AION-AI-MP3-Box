SUMMARY = "AION AI MP3 Box Embedded Linux"
DESCRIPTION = "AION Raspberry Pi 3 with automatic local console login"

require core-image-aion.bb

aion_mp3_autologin() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}${sysconfdir}/systemd/system"
    DROPIN_DIR="$SYSTEMD_DIR/kmsconvt@tty1.service.d"

    install -d "$DROPIN_DIR"

    cat > "$DROPIN_DIR/10-autologin.conf" <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/bin/kmscon --vt=tty1 --seats=seat0 --no-switchvt --login -- /sbin/agetty --autologin root --noclear -- -
UNIT

    # Keep tty2 as the password-protected recovery console.
    # Enable a dedicated tty2 recovery console.
    GETTY_DIR="$SYSTEMD_DIR/getty.target.wants"
    GETTY_UNIT="${IMAGE_ROOTFS}${systemd_system_unitdir}/getty@.service"

    test -f "$GETTY_UNIT" ||
        bbfatal "AION MP3: getty@.service is missing"

    install -d "$GETTY_DIR"

    ln -sfn "${systemd_system_unitdir}/getty@.service"         "$GETTY_DIR/getty@tty2.service"

    test -L "$GETTY_DIR/getty@tty2.service" ||
        bbfatal "AION MP3: failed to enable tty2 recovery console"

    bbnote "AION MP3: tty1 automatic root login configured"
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_mp3_autologin; "

# Google AIY Voice HAT V1 playback and capture utilities
IMAGE_INSTALL:append = " alsa-utils-aplay"

# AION Python Music Player Runtime
IMAGE_INSTALL:append = " python3-core python3-misc python3-mutagen mpv coreutils"

# AION v0.3.0: generate an ext4 root filesystem
# Keep existing image formats available.
IMAGE_FSTYPES += " ext4"

# Mount the dedicated music partition at boot.
aion_music_mount() {
    install -d "${IMAGE_ROOTFS}/mnt/music"
    install -d "${IMAGE_ROOTFS}/boot"

    if ! grep -qE '^[^#]*[[:space:]]/boot[[:space:]]' "${IMAGE_ROOTFS}${sysconfdir}/fstab"; then
        printf '%s\n' '/dev/mmcblk0p1 /boot vfat defaults 0 0' \
            >> "${IMAGE_ROOTFS}${sysconfdir}/fstab"
    fi

    if ! grep -q 'LABEL=AION-MUSIC' "${IMAGE_ROOTFS}${sysconfdir}/fstab"; then
        printf '%s\n' \
            'LABEL=AION-MUSIC /mnt/music ext4 defaults,nofail 0 2' \
            >> "${IMAGE_ROOTFS}${sysconfdir}/fstab"
    fi
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_music_mount; "

# AION UTF-8 login shell environment.
# The base image already installs /etc/locale.conf.
aion_install_utf8_profile() {
    install -d "${IMAGE_ROOTFS}${sysconfdir}/profile.d"

    echo 'export LANG=C.UTF-8' \
        > "${IMAGE_ROOTFS}${sysconfdir}/profile.d/aion-locale.sh"

    chmod 0644 \
        "${IMAGE_ROOTFS}${sysconfdir}/profile.d/aion-locale.sh"
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_install_utf8_profile; "
