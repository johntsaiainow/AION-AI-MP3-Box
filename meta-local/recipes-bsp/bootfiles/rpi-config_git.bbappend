# AION AI MP3 Box - Google AIY Voice HAT V1
#
# The upstream Raspberry Pi 3 deploy append unconditionally enables
# onboard audio. Remove that setting after the upstream deploy step.

do_deploy:append:raspberrypi3-64() {
    sed -i '/^dtparam=audio=on$/d' \
        ${DEPLOYDIR}/${BOOTFILES_DIR_NAME}/config.txt
}
