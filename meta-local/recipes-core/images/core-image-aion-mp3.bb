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
