# AION AI MP3 Box - Google AIY Voice HAT V1
#
# The upstream Raspberry Pi 3 deploy append unconditionally enables
# onboard audio. Remove that setting after the upstream deploy step.

do_deploy:append:raspberrypi3-64() {
    sed -i '/^dtparam=audio=on$/d' \
        ${DEPLOYDIR}/${BOOTFILES_DIR_NAME}/config.txt
}

# AION T085 Bluetooth UART Overlay
# BCM43430A1 verified stable at 460800 baud.
RPI_EXTRA_CONFIG:append:raspberrypi3-64 = "\ndtoverlay=aion-bt-460800"
