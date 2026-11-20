SUMMARY = "AION AI MP3 Box Embedded Linux"
DESCRIPTION = "AION Raspberry Pi 3 with dedicated music console"

require core-image-aion.bb

aion_mp3_autologin() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}${sysconfdir}/systemd/system"
    DROPIN_DIR="$SYSTEMD_DIR/kmsconvt@tty1.service.d"

    install -d "$DROPIN_DIR"

    cat > "$DROPIN_DIR/10-autologin.conf" <<'UNIT'
[Unit]
Wants=aion-pulseaudio.service
After=aion-pulseaudio.service mnt-music.mount

[Service]
ExecStart=
ExecStart=/usr/bin/kmscon --vt=tty1 --seats=seat0 --no-switchvt --login -- /usr/bin/python3 -u /usr/bin/aion-session --console-prompt
UNIT

    # Enable a dedicated tty2 recovery console.
    GETTY_DIR="$SYSTEMD_DIR/getty.target.wants"
    GETTY_UNIT="${IMAGE_ROOTFS}${systemd_system_unitdir}/getty@.service"

    test -f "$GETTY_UNIT" ||
        bbfatal "AION MP3: getty@.service is missing"

    install -d "$GETTY_DIR"

    ln -sfn "${systemd_system_unitdir}/getty@.service"         "$GETTY_DIR/getty@tty2.service"

    test -L "$GETTY_DIR/getty@tty2.service" ||
        bbfatal "AION MP3: failed to enable tty2 recovery console"

    bbnote "AION MP3: tty1 AION session configured"
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_mp3_autologin; "

# Google AIY Voice HAT V1 playback and capture utilities
IMAGE_INSTALL:append = " alsa-utils-aplay"

# AION Python Music Player Runtime
IMAGE_INSTALL:append = " python3-core python3-misc python3-mutagen mpv coreutils"

# AION v0.3.0: generate an ext4 root filesystem
# Keep existing image formats available.
IMAGE_FSTYPES += " ext4"

# Prepare optional music storage directory and mount Boot.
aion_music_mount() {
    install -d "${IMAGE_ROOTFS}/mnt/music"
    install -d "${IMAGE_ROOTFS}/boot"

    if ! grep -qE '^[^#]*[[:space:]]/boot[[:space:]]' "${IMAGE_ROOTFS}${sysconfdir}/fstab"; then
        printf '%s\n' '/dev/mmcblk0p1 /boot vfat defaults 0 0' \
            >> "${IMAGE_ROOTFS}${sysconfdir}/fstab"
    fi

    if ! grep -qE '^[^#]*[[:space:]]/mnt/music[[:space:]]' "${IMAGE_ROOTFS}${sysconfdir}/fstab"; then
        printf '%s\n' 'LABEL=AION-MUSIC /mnt/music ext4 nofail,x-systemd.device-timeout=5s 0 2' \
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

# Bluetooth media and phone calls through the Voice HAT.
aion_bluetooth_audio() {
    PULSE_CONFIG="${IMAGE_ROOTFS}${sysconfdir}/pulse/default.pa"
    sed -i \
        -e 's/^load-module module-bluetooth-discover$/& headset=auto/' \
        -e 's/^load-module module-bluetooth-policy$/& ag_local_card=alsa_card.platform-soc_sound/' \
        "$PULSE_CONFIG"

    grep -qx 'load-module module-bluetooth-discover headset=auto' "$PULSE_CONFIG" &&
        grep -qx 'load-module module-bluetooth-policy ag_local_card=alsa_card.platform-soc_sound' "$PULSE_CONFIG" ||
        bbfatal "AION MP3: failed to configure Bluetooth call audio"
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_bluetooth_audio; "

IMAGE_INSTALL:append = " \
    pulseaudio-server \
    pulseaudio \
    pulseaudio-misc \
    pulseaudio-module-bluetooth-discover \
    pulseaudio-module-bluetooth-policy \
    pulseaudio-module-bluez5-discover \
    pulseaudio-module-bluez5-device \
    pulseaudio-module-loopback \
    pulseaudio-module-native-protocol-unix \
    pulseaudio-module-alsa-sink \
    pulseaudio-module-alsa-source \
    pulseaudio-module-udev-detect \
    pulseaudio-module-always-sink \
    pulseaudio-module-device-restore \
    pulseaudio-module-stream-restore \
    pulseaudio-module-card-restore \
    pulseaudio-module-default-device-restore \
    pulseaudio-module-switch-on-connect \
"


# AION v0.4.0 — Headless PulseAudio service
IMAGE_INSTALL:append = " aion-audio"

# AION T085 WIC Bluetooth Overlay
# Install the custom DTBO in the Raspberry Pi FAT boot partition.
IMAGE_BOOT_FILES:append = " aion-bt-460800.dtbo;overlays/aion-bt-460800.dtbo"

# Ensure the custom overlay is deployed before WIC image creation.
do_image_wic[depends] += " aion-bt-overlay:do_deploy"

IMAGE_INSTALL:append = " aion-player aion-rclone aion-vosk"
# Keep the ext4 image within the existing 754 MiB P2 layout.
IMAGE_ROOTFS_EXTRA_SPACE = "40960"

# Keep the system journal on RootFS instead of the volatile tmpfs.
aion_persistent_journal() {
    AION_LOG_DIR="${IMAGE_ROOTFS}${localstatedir}/log"
    if [ -L "$AION_LOG_DIR" ] && [ "$(readlink "$AION_LOG_DIR")" = "volatile/log" ]; then
        rm "$AION_LOG_DIR"
    fi
    install -d -m 0755 "$AION_LOG_DIR"
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_persistent_journal; "

# AION factory SD image: Boot + RootFS
WKS_FILE = "aion-mp3.wks"
WKS_SEARCH_PATH:prepend = "${THISDIR}/../../wic:"

IMAGE_INSTALL:append = " aion-bluetooth"


# T085-DE-39L-8R: Development access only.
# Remove before production deployment.

aion_developer_access() {
    SYSTEMD_DIR="${IMAGE_ROOTFS}${sysconfdir}/systemd/system"

    # tty2 automatic root login.
    DROPIN="$SYSTEMD_DIR/getty@tty2.service.d"
    install -d "$DROPIN"

    cat > "$DROPIN/10-aion-autologin.conf" <<'UNIT'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
UNIT

    # Development SSH: allow root password authentication.
    SSH_DIR="${IMAGE_ROOTFS}${sysconfdir}/ssh/sshd_config.d"
    install -d "$SSH_DIR"

    cat > "$SSH_DIR/00-aion-development.conf" <<'SSH'
PermitRootLogin yes
PasswordAuthentication yes
PermitEmptyPasswords yes
SSH

    # Development root account: empty password.
    SHADOW="${IMAGE_ROOTFS}${sysconfdir}/shadow"
    test -f "$SHADOW" || bbfatal "AION: shadow file missing"

    sed -i 's/^root:[^:]*:/root::/' "$SHADOW"

    grep -q '^root::' "$SHADOW" ||
        bbfatal "AION: failed to enable development root login"
}

ROOTFS_POSTPROCESS_COMMAND:append = " aion_developer_access; "

IMAGE_INSTALL:append = " util-linux-lsblk util-linux-blkid"
