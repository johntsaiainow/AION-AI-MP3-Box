# AION Music and Internet Radio Box

AION Music and Internet Radio Box is a Yocto-based headless music player built around a
Raspberry Pi 3 and the Google AIY Voice HAT V1. The current interface
provides local music playback, playlists, internet radio, network/cloud
music, Bluetooth, Wi-Fi, storage, and system management.
## Current development status

- **Platform** — Raspberry Pi 3 Model B (ARM64), Yocto Scarthgap 5.0 LTS,
  and systemd.
- **Console** — kmscon on `tty1` with UTF-8/CJK display. The local
  setup wizard and player menu open as root without a login prompt.
  A standard getty on `tty2` provides recovery login.
  Login shells use `LANG=C.UTF-8`.
- **Audio** — The image enables the Google AIY Voice HAT V1 device-tree
  overlay, disables onboard Raspberry Pi audio, and uses ALSA/PulseAudio
  for speaker playback. Microphone capture and voice-processing features
  are not included.
- **Playback runtime** — The image includes mpv, Python 3, and Mutagen.
  The console provides local library browsing, playlists, shuffle, internet
  radio, Bluetooth output, and network/cloud music browsing.
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
writing the image. The optional music partition mounts by label at boot
and can be absent. To mount an existing P3 manually, open **Hardware &
system → Storage management → Mount Music Partition** on the local
console. P3 must be ext4 with the label `AION-MUSIC`.

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

## Music on an SMB share or Google Drive

Open **Network & cloud music → Set up SMB or Google Drive** to create an
rclone connection on the Pi.

- For an SMB share such as `//nas/Music`, choose the **SMB / CIFS**
  backend. Enter `nas` as the host and provide the share account in
  rclone's prompts. When opening this connection in AION, enter `Music`
  as the folder path. [Rclone SMB setup](https://rclone.org/smb/)
- For Google Drive, choose the **Google Drive** backend and
  `drive.readonly` access. Use your own Google OAuth client and follow
  rclone's prompts to authorize it from a computer with a web browser.
  [Google Drive setup](https://rclone.org/drive/#making-your-own-client-id)
  [Headless authorization](https://rclone.org/remote_setup/)

Select **Browse a music connection** to open the remote folder and play
MP3 or FLAC files. AION mounts the remote read-only while browsing and
detaches it when you leave. Rclone keeps credentials in its own
configuration file under the console user's home directory.

## Main menu

The main console menu is a music-only interface:

- Browse and play local albums
- Create, edit, and manage playlists
- Shuffle all music
- Play internet radio
- Manage hardware and system settings
- Browse network and cloud music
- Exit the player

AI connections, text prompts, microphone capture, offline transcription,
voice synthesis, Gemini/ChatGPT OAuth, Vosk, and Piper are not included.

## Roadmap

- Validate Voice HAT V1 speaker playback and Bluetooth output.
- Complete library indexing, playlists, shuffle, and playback controls.
- Improve remote SMB and Google Drive browsing.
- Add reproducible P1/P2/P3 backup and flash procedures.
- Document complete Raspberry Pi 3 hardware tests.

See [TODO.md](TODO.md) for platform build and validation tasks.

## Credits and licensing

Developed by AI-NOW TECHNOLOGY, INC. as part of the AION embedded AI
ecosystem. The local Yocto layer documents its license in
[COPYING.MIT](meta-local/COPYING.MIT). Upstream components carry their
respective licenses.
