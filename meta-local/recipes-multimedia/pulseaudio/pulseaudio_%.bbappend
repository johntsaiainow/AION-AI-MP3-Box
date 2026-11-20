FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append = " file://aion-bluetooth-call-routing.patch"

PACKAGECONFIG:append = " ofono"
