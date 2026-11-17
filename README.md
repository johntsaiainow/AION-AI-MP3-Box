# AION AI MP3 Box

AION AI MP3 Box is an experimental Yocto-based music player built by
repurposing a Google AIY Voice Kit V1 with a Raspberry Pi 3. The project
aims to combine local music playback with
offline voice commands and spoken responses, with optional connections
to AI services on the home network or in the cloud.

## v0.3.0 development status

- **Platform** — Raspberry Pi 3 Model B (ARM64), Yocto Scarthgap 5.0 LTS,
  and systemd.
- **Console** — kmscon on `tty1` with UTF-8/CJK display and automatic
  local root login. A standard getty on `tty2` provides recovery login.
  Login shells use `LANG=C.UTF-8`.
- **Audio** — The image enables the Google AIY Voice HAT V1 device-tree
  overlay, disables onboard Raspberry Pi audio, and includes ALSA utilities
  for playback and recording. Speaker and microphone tests are part of
  hardware validation.
- **Playback runtime** — The image includes mpv, Python 3, and Mutagen.
  The music library interface, playlists, and button controls are planned.
- **Networking** — NetworkManager provides Wi-Fi management, OpenSSH
  provides remote access, and Avahi provides mDNS discovery.

## Hardware

The project repurposes the **Google AIY Voice Kit V1** as a music player.
The hardware setup uses a Raspberry Pi 3 Model B, the kit's **Voice HAT
V1**, a compatible microphone and speaker, and a microSD card. A display
and keyboard are useful for checking the local console. The current
device-tree configuration targets the Voice HAT V1. Voice Bonnet
compatibility and button and LED controls remain open.

### Planned hardware upgrades

- **128 × 64 SSD1306 OLED display** for track information and playback status.
- **RGB push button** for physical input and color-coded status indication.
  Wiring and LED control for the Voice HAT V1 still need validation. The
  [RGB arcade button rewiring discussion](https://electronics.stackexchange.com/questions/492397/rgb-led-arcade-button-rewiring-for-the-aiy-google-voice-bonnet)
  covers the Voice Kit V2 Voice Bonnet and serves as a design reference.

## Build the MP3 Box image

Use a Linux host with a Yocto Scarthgap build environment that includes
Poky, meta-raspberrypi, and meta-openembedded. The platform configuration
comes from [AION Embedded Linux](https://github.com/AI-Now-Inc/ai-now-yocto-rpi3).

From an initialized build environment, configure `MACHINE = "raspberrypi3-64"`
in `conf/local.conf` and register this repository's `meta-local` layer
in `conf/bblayers.conf`. If the build already has a layer named
`meta-local`, point that entry at this checkout.

The [Linux 6.6 recipe append](meta-local/recipes-kernel/linux/linux-raspberrypi_6.6.bbappend)
uses a machine-specific `file` URL for a Raspberry Pi kernel Git mirror.
Provide the mirror locally and adjust the URL for your host before
building. The mirror must contain the revision pinned in the recipe.

```sh
bitbake core-image-aion-mp3
```

The ext4 root filesystem is deployed under
`tmp/deploy/images/raspberrypi3-64/` in the build directory as
`core-image-aion-mp3-raspberrypi3-64.rootfs.ext4`.
The [MP3 Box image recipe](meta-local/recipes-core/images/core-image-aion-mp3.bb)
extends the base AION image with the console login, audio utilities,
playback runtime, and mount configuration.

## SD card layout

The MP3 Box image expects the following layout for an existing
three-partition card.

| Partition | Filesystem | Mount point | Purpose |
| --- | --- | --- | --- |
| P1 | FAT | `/boot` | Raspberry Pi firmware, kernel, and overlays |
| P2 | ext4 | `/` | AION MP3 Box root filesystem |
| P3 | ext4, label `AION-MUSIC` | `/mnt/music` | Local music library |

The ext4 build artifact replaces P2 on an existing card with compatible
boot files. Back up the card and verify the target partition before
writing the image. The optional music partition mounts by label and
can be absent at boot.

The repository's [flash-aion.sh](flash-aion.sh) writes the base
`core-image-aion` WIC image to an entire disk and erases its existing
partitions. It uses a fixed image path and target device.

## First boot checks

On the Pi, verify the login locale, music mount, and ALSA device lists.

```sh
locale
findmnt /mnt/music
aplay -l
arecord -l
```

On `tty1`, run `printf '%s\n' '中文 日本語 한국어'` to check CJK
display. After copying an MP3 to the music partition, test playback with
`mpv --no-video /mnt/music/example.mp3`, using the actual filename.

## Planned AI connectivity

| Mode | Intended use |
| --- | --- |
| On-device | Play local music and handle basic playback commands offline. |
| Home network | Connect to a self-hosted AI service on the local network for conversational requests. |
| Cloud | Connect to a cloud AI service over the internet for conversational requests. |

The player is intended to support basic playback with either external AI
connection disabled or unavailable. Provider selection and integration
are still open.

## Roadmap

- Validate Voice HAT V1 playback and capture, plus button and LED behavior.
- Implement library indexing, playlists, and playback controls.
- Evaluate Vosk for offline voice commands.
- Evaluate Piper and eSpeak NG for offline speech synthesis.
- Integrate configurable home-network and cloud AI connections.
- Document reproducible builds and complete Raspberry Pi 3 hardware tests.

See [TODO.md](TODO.md) for platform build and validation tasks.

## Credits and licensing

Developed by AI-NOW TECHNOLOGY, INC. as part of the AION embedded AI
ecosystem. The local Yocto layer documents its license in
[COPYING.MIT](meta-local/COPYING.MIT). Upstream components carry their
respective licenses.
