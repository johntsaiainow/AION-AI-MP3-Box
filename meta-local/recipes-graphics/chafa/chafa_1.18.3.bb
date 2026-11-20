SUMMARY = "Render images as terminal graphics"
HOMEPAGE = "https://hpjansson.org/chafa/"
LICENSE = "LGPL-3.0-or-later & MIT & Zlib"
LIC_FILES_CHKSUM = " \
    file://COPYING.LESSER;md5=3000208d539ec061b899bce1d9ce9404 \
    file://libnsgif/COPYING;md5=c2a9ab68244f5d67e9d721dd1a2722e2 \
    file://lodepng/LICENSE;md5=0a21ed93a5d78a5a771d718fe4a4ebc5 \
"

SRC_URI = "https://hpjansson.org/chafa/releases/${BP}.tar.xz"
SRC_URI[sha256sum] = "fb995ef21dce6c73dd0dd454ba3e0f7fac08e053ea16060a2e5ce69a3746ee27"

DEPENDS = "glib-2.0 freetype jpeg"

inherit autotools gtk-doc pkgconfig

GTKDOC_ENABLED = "False"

# PNG is built in. Enable JPEG for embedded and folder album art.
EXTRA_OECONF = " \
    --with-jpeg --without-avif --without-heif --without-jxl \
    --without-svg --without-tiff --without-webp \
    --disable-man \
"

BBCLASSEXTEND = "native"
