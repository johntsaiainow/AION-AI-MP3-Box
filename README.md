# AIY Box Rebirth

AIY Box Rebirth turns the Google AIY Voice Kit V1 into a networked music and internet radio player with Bluetooth hands-free calling. It runs Yocto Scarthgap 5.0 LTS on a Raspberry Pi 3 Model B (ARM64) and uses the Voice HAT V1 for its speaker and microphone.

| Name | Use |
| --- | --- |
| **AIY Box Rebirth** | Project name |
| `aiy-box-rebirth` | Default hostname on newly built Raspberry Pi 3 images |
| `aiy-box-rebirth.local` | Avahi mDNS name on the local network |
| `core-image-aion-mp3` | BitBake target and image filename prefix |
| `AION-MUSIC` | Optional music partition label |
| `aion-*` | Existing commands, services, and Yocto package names |

The default Bluetooth name follows the hostname. A box with a custom Bluetooth alias may appear under that alias. An existing installation keeps its hostname until you change it or install a new root filesystem.

## Current features

| Menu or subsystem | Features |
| --- | --- |
| Local music | Browse albums and tracks, display album art with Chafa during playback, play MP3 and FLAC, shuffle the library, and manage playlists |
| Internet radio | Play the built-in station presets |
| Network & cloud music | Browse and play from SMB shares or Google Drive through read-only rclone mounts |
| Bluetooth media | Receive phone music over A2DP or send player audio to Bluetooth headphones and speakers |
| Bluetooth phone calls | Use a paired phone's HFP connection with the Voice HAT microphone and speaker through BlueZ, oFono, and PulseAudio |
| Bluetooth SMS | Browse up to 30 inbox SMS from a paired phone that grants Bluetooth MAP access and open individual messages |
| Hardware & system | Manage Wi-Fi through NetworkManager's `nmtui`, pair Bluetooth devices, select audio output, view logs and system information, and configure language and device location |
| Console and remote access | First-run setup and a UTF-8/CJK kmscon menu on `tty1`, a recovery console on `tty2`, and OpenSSH access |

The current image carries the Vosk Mandarin runtime and model. The main menu exposes music, radio, Bluetooth calling, and system tools.

### Console dashboard

The left pane holds menus and music selections. Press **N** or **P** to
page through longer lists. On terminals at least 66 columns wide, the
right pane takes up about three quarters of the screen and shows a large
solid-block clock and date beside today's weather, with the seven-day
forecast below. The weather and traffic pages alternate every 20 seconds.
Both pages retain the date, time, current weather, and commute estimates.
The seven daily weather icons scale to the available terminal space.
The traffic map fills the available panel width and remaining rows.
The host status shows CPU
temperature and RAM usage. The network status shows the active interface
and IPv4 address and indicates when there is only a local connection.
Choose **Exit** and confirm to return to the shell prompt. Run
`aion-player-console` to reopen the menu.

The clock defaults to Pacific time. Use **Hardware & system → Time zone
and daylight saving** to choose a time zone and either follow its
daylight-saving rules or use standard time year-round.

In **Hardware & system → Device location**, choose **City and region**,
**Postal code / ZIP code**, or **Latitude and longitude**. Enter the country
code (for example `US`) and postal code in the dedicated postal-code
flow. For city search, enter the country, city, and state or region in
separate fields. For a precise point, enter coordinates such as `25.03, 121.56`.
The dashboard's weather page shows the next seven days directly. Each
day includes conditions, high and low temperatures, maximum precipitation
probability and total, and maximum wind and gust speeds.
Traffic shows the
current speed and a condition based on its ratio to free-flow speed for
the road nearest the geocoded location.
Chafa displays the TomTom map with a live traffic-flow overlay.
The commute to work is cyan, the return trip is violet, and amber
marks affected sections reported by TomTom. To enable it, open
**Hardware & system → TomTom traffic key** and paste your key. Input is
hidden, and the key is saved in `/etc/aiy-box-rebirth/tomtom.key` with
mode `0600`. An existing `TOMTOM_API_KEY` environment variable takes
precedence over that file.
Set **Hardware & system → Commute addresses** to calculate estimated
drive time and traffic delay in both directions. The estimated time
already includes the reported delay. The home and work
addresses are stored on the device and sent to TomTom for route
geocoding. Open-Meteo uses the separate device location setting. The
TomTom key must have Map Display and Traffic access, plus Geocoding
and Routing for commute estimates.
The traffic page lists reported crashes, roadwork, closures, and
congestion on the calculated routes, with incident delay and speed
when supplied by TomTom.
The console remains usable if either network source is unavailable.

When updating the current SD card, `scripts/flash-aion-p2.sh` makes a
private backup of P2 and carries the saved device location, commute
addresses, and TomTom key into the new filesystem. It checks the copied
files and their permissions before writing P2, then compares the written
image with the staged copy.
[Open-Meteo documentation](https://open-meteo.com/en/docs) · [TomTom Traffic Flow documentation](https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data)

### Album covers

The player uses Chafa to render covers as colored terminal characters.
It looks for embedded MP3 or FLAC art, then for JPEG or PNG files named
`cover`, `folder`, `front`, or `album` in the track's directory.
When local art is missing, the player looks up the album's cover using
MusicBrainz and Cover Art Archive. It searches individual releases if
the release group lacks a cover and uses the recording when album tags
are missing.

Timed lyrics follow the playback position. The player uses a matching
`.lrc` file or embedded lyrics and queries LRCLIB when local lyrics are
unavailable, with a track search if the exact lookup fails. Press **L**
during playback to see the lyrics, including
plain lyrics without timestamps. Online requests use music tags such as
title, artist, album, and duration, and do not modify the audio files.
[Cover Art Archive](https://musicbrainz.org/doc/Cover_Art_Archive/API) · [LRCLIB](https://lrclib.net/docs)

The playback screen keeps artwork, metadata, progress, and the current
lyric in fixed positions. In the full lyrics view, press **J/K** to
scroll and **L** to return. On a Voice Kit V1 with its original top
button attached, a short press pauses or resumes playback. The lamp is
on during playback and turns off while paused or when playback ends.

## Hardware and first boot

Use a Raspberry Pi 3 Model B, Google AIY Voice HAT V1, compatible microphone and speaker, and a microSD card. A display and keyboard provide access to the local setup wizard and player. The image enables the Voice HAT overlay and disables Raspberry Pi onboard audio. The player can use direct ALSA for the Voice HAT or PulseAudio for Bluetooth output.

Use **Hardware & system → Wi-Fi management** to open `nmtui`. Once the Pi is connected, use its mDNS name from the same network, or use its IP address if your client cannot resolve `.local` names.

```sh
ssh root@aiy-box-rebirth.local
```

On the Pi, verify the hostname, locale, music mount, and audio devices.

```sh
hostname
locale
findmnt /mnt/music
aplay -l
arecord -l
```

## Bluetooth

Open **Hardware & system → Bluetooth management**. Choose **Play music from a phone** for A2DP input, **Connect headphones or a speaker** for Bluetooth output, or **Phone speakerphone** for calls. For player output to a Bluetooth speaker or headphones, select the PulseAudio backend in **Audio output settings** and the device in the Bluetooth menu's **Audio output**.

To pair a phone, type `default-agent` at the box's Bluetooth prompt, select **aiy-box-rebirth** on the phone, and confirm the same code on both devices. Type `exit` to close pairing mode. On an older installation, use the Bluetooth name shown by `bluetoothctl show`.

For calls, enable **Phone calls** for the box if the phone shows that option. Place or answer a call on the phone and select the box as the call audio output. If direct ALSA playback is using the Voice HAT, stop it before testing the call. After hanging up, play phone music again to check the return to A2DP.

The custom `aion-bt-460800.dtbo` overlay sets the Bluetooth UART limit to **460800 baud** and carries SCO call audio over HCI UART. On Raspberry Pi 3, a Pixel 7 Pro was verified to reconnect after re-pairing, expose an HFP device in oFono, and connect with the A2DP profile active. To verify both call-audio directions, make a call and check the speaker and microphone while HFP is active.

If an upgrade produces `PIN or Key Missing` or `Authentication Failed`, remove the old pairing on both devices and pair again. Use these commands to inspect the adapter and audio services.

```sh
bluetoothctl show
systemctl status bluetooth ofono aion-pulseaudio
journalctl -b -u bluetooth -u ofono -u aion-pulseaudio
```

To read SMS, choose **Bluetooth management → Phone SMS**, select a paired
phone, and approve its message access prompt if one appears. The box lists
senders and times and fetches the text of the selected SMS. Messages are
shown in the console and the temporary download is removed after reading.

## Music on SMB or Google Drive

Open **Network & cloud music → Set up SMB or Google Drive** to configure an rclone connection.

- For a share such as `//nas/Music`, use **SMB / CIFS**, enter `nas` as the host, and enter `Music` as the folder when opening the connection. [rclone SMB setup](https://rclone.org/smb/)
- For Google Drive, choose **Google Drive** and use `drive.readonly` access. Follow the rclone authorization prompts using a browser on another computer. [rclone Google Drive setup](https://rclone.org/drive/) · [Headless authorization](https://rclone.org/remote_setup/)

Choose **Browse a music connection** to play tracks. The box mounts the remote read-only and detaches it when you leave the browser.

## Build the image

Use a Linux host with Yocto Scarthgap, Poky, meta-raspberrypi, and meta-openembedded. Set `MACHINE = "raspberrypi3-64"` in `conf/local.conf` and register this checkout's `meta-local` in `conf/bblayers.conf`. The platform configuration is based on AION Embedded Linux. [AION Embedded Linux](https://github.com/AI-Now-Inc/ai-now-yocto-rpi3)

The Linux 6.6 recipe append points to a machine-specific local Raspberry Pi kernel Git mirror. Supply the mirror and adjust its `file` URL for your build host. The mirror must contain the pinned revision. [Kernel recipe append](meta-local/recipes-kernel/linux/linux-raspberrypi_6.6.bbappend)

```sh
bitbake core-image-aion-mp3
```

The build places the following files in `tmp/deploy/images/raspberrypi3-64/`.

| File | Use |
| --- | --- |
| `core-image-aion-mp3-raspberrypi3-64.rootfs.wic.bz2` | Factory SD image with boot and root filesystem partitions |
| `core-image-aion-mp3-raspberrypi3-64.rootfs.ext4` | Root filesystem for updating P2 |
| `aion-bt-460800.dtbo` | Bluetooth overlay for P1 |

## SD card layout and upgrades

| Partition | Filesystem | Mount point | Purpose |
| --- | --- | --- | --- |
| P1 | FAT | `/boot` | Raspberry Pi firmware, kernel, and overlays |
| P2 | ext4 | `/` | System, Wi-Fi settings, and Bluetooth pairings |
| P3 (optional) | ext4, label `AION-MUSIC` | `/mnt/music` | Local music library, mounted by label at boot |

For an existing card, back up P1 and P2 before updating. Use the ext4 image for P2 and copy the matching `aion-bt-460800.dtbo` to `overlays/` on P1. Confirm P1's `config.txt` includes `dtoverlay=aion-bt-460800`. Overwriting P2 replaces device settings and pairing records stored there. A whole-disk WIC write replaces the partition table, including any existing P3.

## Roadmap and credits

The planned hardware extensions are a 128 × 64 SSD1306 OLED display and an RGB button. Voice Bonnet compatibility, button and LED wiring, and repeatable cold-boot testing remain open. See [TODO.md](TODO.md) for platform validation tasks.

Developed by AI-NOW TECHNOLOGY, INC. as part of the AION embedded AI ecosystem. The local layer's license is documented in [COPYING.MIT](meta-local/COPYING.MIT). Upstream components carry their own licenses.
