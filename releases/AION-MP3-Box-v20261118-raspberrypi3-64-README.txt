AION AI MP3 Box image
Version: 20261118
Host: Raspberry Pi 3 (64-bit)
Image: AION-MP3-Box-v20261118-raspberrypi3-64.wic.bz2

Write with:
  bzcat AION-MP3-Box-v20261118-raspberrypi3-64.wic.bz2 | sudo dd of=/dev/mmcblk0 bs=4M status=progress conv=fsync

Verify:
  sha256sum -c AION-MP3-Box-v20261118-raspberrypi3-64.sha256

WARNING: This erases P1, P2, and P3. Back up the music library first.
